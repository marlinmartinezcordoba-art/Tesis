"""
Cierre de ING-01, ING-02 e ING-06: lote de transferencia con su procedencia
(remitente, dependencia de origen, acta), paquete de envío (SIP) en BagIt
al confirmarlo, validado con el validador de la Library of Congress
(bagit-python), custodia anterior registrada y acuse de recibo.
"""

import uuid
from pathlib import Path

import bagit
import pytest
from sqlalchemy import select

from app.models.descripcion import Relacion
from app.models.instanciacion import Instanciacion
from app.models.lote import LoteIngesta
from app.servicios import almacen, procesamiento, vocabulario
from tests import archivos
from tests.test_ingesta import archivista, eventos, fondo, inst  # noqa: F401


@pytest.fixture()
def procedencia(db, fondo):
    secretaria = vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Secretaría de Gobierno",
                                   subtipo="entidad_corporativa", origen="persona", confianza=None, motor=None,
                                   usuario_id=None)
    jefe = vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Ana Ruiz", subtipo="persona",
                             origen="persona", confianza=None, motor=None, usuario_id=None)
    db.commit()
    return secretaria, jefe


def abrir(cliente, cabeceras, fondo, secretaria, jefe, **extra):
    datos = {"fondo_id": str(fondo.id), "forma_ingreso": "transferencia_primaria", "remitente_id": str(jefe.id),
             "dependencia_origen_id": str(secretaria.id), "acta_numero": "AT-014", "acta_fecha_edtf": "2026-09-30",
             "observaciones": "Transferencia anual según TRD."} | extra
    return cliente.post("/api/ingesta/lotes", headers=cabeceras, json=datos)


def cargar_en_lote(cliente, cabeceras, fondo, lote_id, *archivos_):
    r = cliente.post("/api/ingesta/cargar", headers=cabeceras, data={"fondo_id": str(fondo.id), "lote_id": lote_id},
                     files=[("archivos", (n, c, "application/octet-stream")) for n, c in archivos_])
    assert r.status_code == 200, r.text
    return r.json()["resultados"]


def test_el_lote_guarda_la_procedencia_y_sus_archivos(cliente, db, fondo, archivista, procedencia):
    secretaria, jefe = procedencia
    r = abrir(cliente, archivista, fondo, secretaria, jefe)
    assert r.status_code == 201, r.text
    lote = r.json()
    assert lote["numero"].startswith("L-") and lote["estado"] == "abierto"
    assert lote["dependencia_origen"]["nombre"] == "Secretaría de Gobierno" and lote["remitente"]["nombre"] == "Ana Ruiz"
    assert lote["acta_numero"] == "AT-014" and lote["acta_fecha_legible"] == "30 de septiembre de 2026"
    resultados = cargar_en_lote(cliente, archivista, fondo, lote["id"], ("oficio.pdf", archivos.pdf_con_texto()))
    assert inst(db, resultados[0]["id"]).lote_id == uuid.UUID(lote["id"])
    assert eventos(db, "documento_cargado")[0].valor_nuevo["lote"] == lote["numero"]
    assert eventos(db, "lote_creado")[0].valor_nuevo["dependencia_origen"] == "Secretaría de Gobierno"


def test_una_transferencia_exige_dependencia_y_acta(cliente, db, fondo, archivista, procedencia):
    secretaria, jefe = procedencia
    assert abrir(cliente, archivista, fondo, secretaria, jefe, acta_numero=None).status_code == 422
    assert abrir(cliente, archivista, fondo, secretaria, jefe, dependencia_origen_id=None).status_code == 422
    assert abrir(cliente, archivista, fondo, secretaria, jefe, acta_fecha_edtf="treinta de sept").status_code == 422
    # Una donación no la exige.
    assert abrir(cliente, archivista, fondo, secretaria, jefe, forma_ingreso="donacion", acta_numero=None,
                 dependencia_origen_id=None).status_code == 201


def test_confirmar_arma_un_sip_bagit_valido_con_la_procedencia(cliente, db, fondo, archivista, procedencia):
    secretaria, jefe = procedencia
    lote = abrir(cliente, archivista, fondo, secretaria, jefe).json()
    res = cargar_en_lote(cliente, archivista, fondo, lote["id"], ("oficio.pdf", archivos.pdf_con_texto()),
                         ("acta.pdf", archivos.pdf_con_texto("ACTA DE TRANSFERENCIA AT-014")))
    # Con archivos aún en proceso no se confirma.
    assert cliente.post(f"/api/ingesta/lotes/{lote['id']}/confirmar", headers=archivista).status_code == 422
    procesamiento.procesar_pendientes(db)
    assert cliente.put(f"/api/ingesta/lotes/{lote['id']}/acta", headers=archivista,
                       json={"instanciacion_id": res[1]["id"]}).status_code == 200
    r = cliente.post(f"/api/ingesta/lotes/{lote['id']}/confirmar", headers=archivista)
    assert r.status_code == 200, r.text
    acuse = r.json()["acuse"]
    assert acuse["total_archivos"] == 2 and acuse["acta"] == "AT-014"
    assert {a["sha256"] for a in acuse["archivos"]} == {inst(db, x["id"]).huella for x in res}
    lote_db = db.get(LoteIngesta, uuid.UUID(lote["id"]))
    bolsa = almacen.raiz() / lote_db.sip_ruta
    bag = bagit.Bag(str(bolsa))
    bag.validate()  # validador de la Library of Congress: huellas, Payload-Oxum, tagmanifest
    assert bag.info["Source-Organization"] == "Secretaría de Gobierno"
    assert bag.info["Contact-Name"] == "Ana Ruiz"
    assert bag.info["External-Identifier"] == "Acta AT-014"
    assert bag.info["Bag-Group-Identifier"] == lote["numero"]
    assert sorted(Path(p).name for p in bag.payload_files()) == ["acta.pdf", "oficio.pdf"]
    # Enlaces duros: el paquete no duplica el espacio en disco.
    original = almacen.ruta_absoluta(inst(db, res[0]["id"]).ruta)
    assert (bolsa / "data" / "oficio.pdf").stat().st_ino == original.stat().st_ino
    # Ya confirmado, no recibe más archivos ni se anula.
    r = cliente.post("/api/ingesta/cargar", headers=archivista, data={"fondo_id": str(fondo.id), "lote_id": lote["id"]},
                     files=[("archivos", ("otro.pdf", archivos.pdf_con_texto(), "application/pdf"))])
    assert r.status_code == 422
    assert cliente.post(f"/api/ingesta/lotes/{lote['id']}/anular", headers=archivista,
                        json={"motivo": "x"}).status_code == 422


def test_confirmar_registra_la_custodia_anterior_y_el_acuse(cliente, db, fondo, archivista, procedencia):
    secretaria, jefe = procedencia
    lote = abrir(cliente, archivista, fondo, secretaria, jefe).json()
    [r] = cargar_en_lote(cliente, archivista, fondo, lote["id"], ("oficio.pdf", archivos.pdf_con_texto()))
    procesamiento.procesar_pendientes(db)
    assert cliente.post(f"/api/ingesta/lotes/{lote['id']}/confirmar", headers=archivista).status_code == 200
    [custodia] = db.scalars(select(Relacion).where(Relacion.origen_id == uuid.UUID(r["id"]),
                                                    Relacion.codigo_ric == "has_or_had_holder")).all()
    assert custodia.destino_id == secretaria.id and custodia.fecha_edtf == "/2026-09-30"
    assert "AT-014" in custodia.nota
    [ev] = eventos(db, "lote_confirmado")
    assert ev.valor_nuevo["acuse"]["paquete_bagit_sha256"] == ev.valor_nuevo["sip_huella"]
    acuse = cliente.get(f"/api/ingesta/lotes/{lote['id']}/acuse", headers=archivista).json()
    assert acuse["dependencia_origen"] == "Secretaría de Gobierno" and acuse["recibido_en"]


def test_un_lote_abierto_se_anula_con_motivo_y_sus_archivos_quedan_sin_lote(cliente, db, fondo, archivista,
                                                                            procedencia):
    secretaria, jefe = procedencia
    lote = abrir(cliente, archivista, fondo, secretaria, jefe).json()
    [r] = cargar_en_lote(cliente, archivista, fondo, lote["id"], ("oficio.pdf", archivos.pdf_con_texto()))
    assert cliente.post(f"/api/ingesta/lotes/{lote['id']}/anular", headers=archivista,
                        json={"motivo": " "}).status_code == 422
    r2 = cliente.post(f"/api/ingesta/lotes/{lote['id']}/anular", headers=archivista,
                      json={"motivo": "Se abrió en el fondo equivocado."})
    assert r2.status_code == 200 and r2.json()["estado"] == "anulado"
    assert inst(db, r["id"]).lote_id is None
    assert db.get(LoteIngesta, uuid.UUID(lote["id"])) is not None  # nada se borra


def test_el_revisor_consulta_lotes_pero_no_los_abre_ni_confirma(cliente, db, fondo, archivista, procedencia):
    """ING-08: lectura para el revisor (decisión documentada), escritura solo
    para archivista y administrador, también en los lotes."""
    from tests.conftest import crear_usuario, ingresar

    secretaria, jefe = procedencia
    lote = abrir(cliente, archivista, fondo, secretaria, jefe).json()
    crear_usuario(db, "julian@correo.com", "revisor")
    revisor = ingresar(cliente, "julian@correo.com")
    assert cliente.get("/api/ingesta/lotes", headers=revisor, params={"fondo_id": str(fondo.id)}).status_code == 200
    assert abrir(cliente, revisor, fondo, secretaria, jefe).status_code == 403
    assert cliente.post(f"/api/ingesta/lotes/{lote['id']}/confirmar", headers=revisor).status_code == 403
    assert cliente.post(f"/api/ingesta/lotes/{lote['id']}/anular", headers=revisor,
                        json={"motivo": "x"}).status_code == 403


def test_cada_tipo_de_alerta_tiene_nombre_y_las_de_ingesta_enlazan_a_descripcion():
    """ING-07: la interfaz nombra cada alerta del servidor y enlaza las dos de la ingesta."""
    import re

    from app.models.alerta import TIPO_ALERTA
    from tests.conftest import RAIZ

    fuente = Path(RAIZ, "frontend", "src", "lib", "alertas.ts").read_text(encoding="utf-8")
    nombrados = set(re.findall(r"^\s+(\w+): \"", fuente, re.M))
    assert set(TIPO_ALERTA) <= nombrados, set(TIPO_ALERTA) - nombrados
    assert '"formato_no_identificado", "ocr_baja_confianza"' in fuente
