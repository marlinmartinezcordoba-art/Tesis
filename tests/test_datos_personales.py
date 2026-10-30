"""
Posibles datos personales (Ley 1581 de 2012), fase A de los requerimientos.

- Las reglas encuentran cédulas, tarjetas de identidad, correos, celulares,
  cuentas, datos de salud y menciones de menores, y no confunden «el menor
  impacto», «El Niño» ni el diagnóstico ambiental con datos de personas.
- Cada hallazgo dice tipo, categoría, página, confianza, fragmento y qué
  hacer; el dato no se guarda completo fuera del texto del archivo.
- La descripción no se publica con hallazgos pendientes; confirmar, corregir
  o descartar (con motivo) queda en la auditoría, y lo confirmado fija el
  nivel de datos personales de la descripción.
- Los datos sensibles o de menores levantan una alerta sin el dato.
"""

import uuid

from sqlalchemy import select

from app.models.alerta import Alerta
from app.models.auditoria import RegistroAuditoria
from app.models.dato_personal import DatoPersonalDetectado
from app.models.evidencia_ia import PaginaTexto
from app.models.recurso_documental import RecursoDocumental
from app.servicios import datos_personales as dp
from tests.test_descripcion import (aceptar_todo, archivista, documento, fondo, iniciar,  # noqa: F401
                                    motor_prueba)

TEXTO = ("Bogotá, 3 de marzo de 2024. Señor Juan Pérez, identificado con cédula de ciudadanía No. 79.123.456, "
         "celular 310 555 1234, correo juan.perez@gmail.com. Copia a notificaciones@minambiente.gov.co.\n\f"
         "El menor Andrés, con T.I. 1.023.456.789, aporta su historia clínica con diagnóstico F32.1. "
         "Se repite la cédula 79123456.")


def _con_paginas(db, fondo, texto, nombre="oficio.pdf"):  # noqa: F811
    d = documento(db, fondo, nombre, texto)
    corte = texto.index("\f")
    db.add(PaginaTexto(id=uuid.uuid4(), instanciacion_id=d.id, numero=1, inicio=0, fin=corte, origen="ocr"))
    db.add(PaginaTexto(id=uuid.uuid4(), instanciacion_id=d.id, numero=2, inicio=corte + 1, fin=len(texto), origen="ocr"))
    db.commit()
    return d


def test_reglas_y_falsos_positivos():
    tipos = {h.regla.clave: h for h in dp.detectar(TEXTO)}
    assert set(tipos) == {"cedula", "celular", "correo", "menor_de_edad", "tarjeta_identidad", "historia_clinica",
                          "diagnostico_cie"}
    assert len(tipos["cedula"].ocurrencias) == 2  # el mismo número, con y sin puntos, es un solo hallazgo
    assert tipos["tarjeta_identidad"].regla.categoria == "menores" and tipos["diagnostico_cie"].regla.categoria == "sensible"
    limpio = ("El fenómeno de El Niño y el menor impacto ambiental. Diagnóstico ambiental de alternativas. "
              "Radicado 20241234567890123. Valor $ 3.105.551.234,00. Escriba a contacto@entidad.gov.co.")
    assert dp.detectar(limpio) == []


def test_muestra_enmascarada():
    assert dp.enmascarar("79.123.456") == "••.•••.456"
    assert dp.enmascarar("juan.perez@gmail.com").endswith("@gmail.com") and "juan" not in dp.enmascarar("juan.perez@gmail.com")


def test_revision_por_paginas_sin_copiar_el_dato(db, fondo):  # noqa: F811
    d = _con_paginas(db, fondo, TEXTO)
    nuevos = dp.revisar(db, d)
    cedula = next(x for x in nuevos if x.tipo == "cedula")
    assert cedula.muestra == "••.•••.456" and len(cedula.huella_valor) == 64
    assert [o["pagina"] for o in cedula.ocurrencias] == [1, 2]
    assert next(x for x in nuevos if x.tipo == "tarjeta_identidad").ocurrencias[0]["pagina"] == 2
    # Sin cambios en el texto ni en las reglas, no se vuelve a revisar.
    assert dp.revisar(db, d) == []


def test_publicar_exige_revisar_y_fija_el_nivel(cliente, db, fondo, archivista, motor_prueba):  # noqa: F811
    d = _con_paginas(db, fondo, TEXTO)
    espacio = iniciar(cliente, archivista, [d.id])
    dp_ = espacio["datos_personales"]
    assert dp_["pendientes"] == 7
    hallazgos = {h["tipo"]: h for h in dp_["documentos"][0]["hallazgos"]}
    cedula = hallazgos["cedula"]
    assert cedula["paginas"] == [1, 2] and cedula["veces"] == 2 and cedula["confianza"] == 0.95
    assert cedula["contexto"]["valor"] == "79.123.456" and "identificado con" in cedula["contexto"]["antes"]
    assert "no lo transcriba" in cedula["recomendacion"]

    # Con pendientes, no se publica.
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio))
    assert r.status_code == 422 and "sin revisar" in r.json()["detail"]

    def decidir(h, **cuerpo):
        r = cliente.post(f"/api/descripcion/datos-personales/{h['id']}/decision", headers=archivista,
                         json={"trabajo_id": espacio["trabajo_id"], **cuerpo})
        return r

    assert decidir(hallazgos["correo"], accion="descartar").status_code == 422  # sin motivo
    assert decidir(hallazgos["correo"], accion="descartar", motivo="Es de un abogado externo ya público").status_code == 200
    assert decidir(hallazgos["telefono"], accion="corregir", categoria="personal").status_code == 422  # no cambia nada
    estado = decidir(hallazgos["telefono"], accion="corregir", categoria="sensible").json()
    assert next(h for h in estado["documentos"][0]["hallazgos"] if h["tipo"] == "telefono")["estado"] == "corregido"
    for h in estado["documentos"][0]["hallazgos"]:
        if h["estado"] == "pendiente":
            estado = decidir(h, accion="confirmar").json()
    assert estado["pendientes"] == 0 and estado["nivel_propuesto"] == "menores"

    # Declarar menos de lo confirmado no se permite.
    datos = aceptar_todo(espacio)
    datos["proteccion"] = {"datos_personales": "personales", "nota_accesibilidad": None}
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=datos)
    assert r.status_code == 422 and "declara menos" in r.json()["detail"]
    # Sin declararlo, se toma el de los hallazgos confirmados: hay de menores.
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio))
    assert r.status_code == 201, r.text
    recurso = db.get(RecursoDocumental, uuid.UUID(r.json()["id"]))
    assert recurso.datos_personales == "menores"

    # La auditoría guarda la muestra, nunca el dato.
    eventos = db.scalars(select(RegistroAuditoria).where(RegistroAuditoria.accion == "dato_personal_revisado")).all()
    assert eventos and not any("79.123.456" in (e.detalle or "") or "79123456" in str(e.valor_nuevo) for e in eventos)
    descartado = db.scalar(select(DatoPersonalDetectado).where(DatoPersonalDetectado.tipo == "correo"))
    assert descartado.estado == "descartado" and descartado.motivo.startswith("Es de un abogado")


def test_alerta_sin_el_dato_y_revision_del_fondo(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    d = _con_paginas(db, fondo, TEXTO)
    cab = cabeceras_admin
    r = cliente.post(f"/api/descripcion/datos-personales/revisar-fondo?fondo_id={fondo.id}", headers=cab)
    assert r.status_code == 200, r.text
    assert r.json() == {"archivos": 1, "hallazgos_nuevos": 7, "sensibles_o_menores": 4}
    alerta = db.scalar(select(Alerta).where(Alerta.tipo == "datos_personales_sensibles", Alerta.entidad_id == str(d.id)))
    assert alerta.severidad == "alta" and "niños, niñas o adolescentes" in alerta.mensaje
    assert "1.023" not in alerta.mensaje and "79.123" not in alerta.mensaje
    # Una segunda vez no repite nada.
    assert cliente.post(f"/api/descripcion/datos-personales/revisar-fondo?fondo_id={fondo.id}",
                        headers=cab).json()["hallazgos_nuevos"] == 0


def test_salto_de_pagina_no_parte_el_literal_del_grafo():
    """Regresión: el texto con \\f (salto de página) se partía en dos líneas al ordenar las N-Triples."""
    from rdflib import Graph, Literal, URIRef

    from app.servicios.grafo_rdf import ntriples

    g = Graph()
    g.add((URIRef("urn:a"), URIRef("urn:b"), Literal("página 1\n\fpágina 2")))
    copia = Graph()
    copia.parse(data=ntriples(g).decode("utf-8"), format="nt")
    assert len(copia) == 1 and str(next(iter(copia))[2]) == "página 1\n\fpágina 2"
