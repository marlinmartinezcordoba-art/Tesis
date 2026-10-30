"""
Autoridades compartidas entre fondos (RiC: cualquier entidad es punto de acceso de primer nivel).

- Una persona, familia, entidad o cargo es una sola en la institución: al
  describir en otro fondo, el sistema la encuentra y la reutiliza.
- Conserva su fondo de registro (allí vive su fila en el grafo de control);
  el otro fondo la cita, la exporta en su grafo RiC-O y la muestra en su
  vocabulario. Los dos grafos siguen coincidiendo con las tablas.
- Las fichas duplicadas en fondos distintos se sugieren y se fusionan.
- Los mecanismos (programas con su versión) y el resto del vocabulario
  siguen siendo de cada fondo.
- Lo reservado sigue sin salir: una autoridad que otro fondo solo conoce
  por documentos reservados no se nombra en el grafo público de ese fondo.
"""

import uuid

from rdflib import URIRef
from sqlalchemy import select

from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico, grafo_rdf, vocabulario
from tests.test_descripcion import (OFICIO_114, aceptar_todo, archivista, documento, fondo, iniciar,  # noqa: F401
                                    motor_prueba)


def _otro_fondo(db, admin):
    f = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Archivo de la Gobernación", creado_por_id=admin.id)
    f.fondo_id = f.id
    db.add(f)
    db.commit()
    return f


def _publicar(cliente, db, fnd, cab, nombre, reutilizar=None):
    d = documento(db, fnd, nombre, OFICIO_114)
    espacio = iniciar(cliente, cab, [d.id])
    datos = aceptar_todo(espacio)
    if reutilizar:
        for e in datos["entidades"]:
            if e["valor"] in reutilizar:
                e["reutilizar_id"], e["crear_nueva"] = str(reutilizar[e["valor"]]), False
    r = cliente.post("/api/descripcion/publicar", headers=cab, json=datos)
    assert r.status_code == 201, r.text
    return r.json()


def _agente(db, fnd, nombre):
    return db.scalar(select(EntidadVocabulario).where(EntidadVocabulario.fondo_id == fnd.id,
                                                      EntidadVocabulario.nombre == nombre))


def test_una_autoridad_para_toda_la_institucion(cliente, db, fondo, admin, archivista, motor_prueba,  # noqa: F811
                                                cabeceras_admin):
    _publicar(cliente, db, fondo, archivista, "a.pdf")
    alcaldia = _agente(db, fondo, "Alcaldía Municipal")
    lugar = _agente(db, fondo, "Boyacá")
    otro = _otro_fondo(db, admin)

    # Al describir en el otro fondo, la autoridad aparece con su fondo de registro; el lugar no (es de cada fondo).
    r = cliente.post("/api/vocabulario/verificar", headers=archivista,
                     json={"fondo_id": str(otro.id), "tipo": "agente", "valor": "Alcaldía Municipal"})
    assert r.status_code == 200 and r.json()[0]["id"] == str(alcaldia.id)
    assert r.json()[0]["fondo"] == "Correspondencia municipal"
    assert cliente.post("/api/vocabulario/verificar", headers=archivista,
                        json={"fondo_id": str(otro.id), "tipo": "lugar", "valor": "Boyacá"}).json() == []

    publicada = _publicar(cliente, db, otro, archivista, "b.pdf", reutilizar={"Alcaldía Municipal": alcaldia.id})
    assert _agente(db, otro, "Alcaldía Municipal") is None  # no se duplicó
    assert db.scalar(select(Relacion).where(Relacion.origen_id == uuid.UUID(publicada["id"]),
                                            Relacion.destino_id == alcaldia.id)) is not None

    # El grafo del otro fondo la cita con su URI; los dos grafos coinciden con las tablas.
    db.expire_all()
    for fnd in (fondo, otro):
        for alcance in grafo_rdf.ALCANCES:
            grafo_rdf.sincronizar(db, fnd, alcance)
    db.commit()
    assert grafo_rdf.comparar(db, fondo.id) == [] and grafo_rdf.comparar(db, otro.id) == []
    publico = exportacion_rico.exportar(db, otro).grafo
    assert (URIRef(exportacion_rico.base() + str(alcaldia.id)), None, None) in publico

    # En el vocabulario del otro fondo aparece, con su fondo de registro.
    lista = cliente.get("/api/vocabulario", headers=archivista, params={"fondo_id": str(otro.id), "clase": "agente"}).json()
    citada = next(e for e in lista if e["id"] == str(alcaldia.id))
    assert citada["fondo_registro"]["titulo"] == "Correspondencia municipal"
    assert lugar.id not in {uuid.UUID(e["id"]) for e in lista}

    # Su URI se resuelve, y su ficha EAC-CPF es pública.
    assert cliente.get(f"/id/{alcaldia.id}", headers=cabeceras_admin).status_code == 200


def test_fusionar_duplicados_de_fondos_distintos(cliente, db, fondo, admin, archivista, motor_prueba,  # noqa: F811
                                                 cabeceras_admin):
    _publicar(cliente, db, fondo, archivista, "a.pdf")
    otro = _otro_fondo(db, admin)
    _publicar(cliente, db, otro, archivista, "b.pdf")  # sin reutilizar: queda una ficha duplicada
    a, b = _agente(db, fondo, "Alcaldía Municipal"), _agente(db, otro, "Alcaldía Municipal")
    assert a and b and a.id != b.id

    # La detección propone el par entre fondos, y aparece en las sugerencias de los dos.
    assert vocabulario.detectar_candidatos(db, otro.id) >= 1
    db.commit()
    for fnd in (fondo, otro):
        sugerencias = cliente.get("/api/vocabulario/sugerencias-fusion", headers=archivista,
                                  params={"fondo_id": str(fnd.id)}).json()
        assert any({e["id"] for e in s["entidades"]} == {str(a.id), str(b.id)} for s in sugerencias)

    r = cliente.post("/api/vocabulario/fusionar", headers=cabeceras_admin,
                     json={"definitiva_id": str(a.id), "absorbida_id": str(b.id)})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(EntidadVocabulario, b.id).estado == "fusionada"
    # La descripción del otro fondo ahora cita la autoridad única.
    assert db.scalar(select(Relacion).where(Relacion.destino_id == b.id, Relacion.estado == "vigente")) is None
    assert db.scalar(select(Relacion).where(Relacion.destino_id == a.id, Relacion.destino_original_id == b.id))
    # Y la URI de la ficha absorbida redirige, para siempre, a la definitiva.
    r = cliente.get(f"/id/{b.id}", headers=cabeceras_admin, follow_redirects=False)
    assert r.status_code == 301 and str(a.id) in r.headers["location"]


def test_lo_que_sigue_siendo_de_cada_fondo(db, fondo, admin):  # noqa: F811
    otro = _otro_fondo(db, admin)
    usuario = admin.id
    lugar = vocabulario.crear(db, fondo_id=fondo.id, clase="lugar", nombre="Tunja", subtipo=None, origen="persona",
                              confianza=None, motor=None, usuario_id=usuario)
    lugar2 = vocabulario.crear(db, fondo_id=otro.id, clase="lugar", nombre="Tunja", subtipo=None, origen="persona",
                               confianza=None, motor=None, usuario_id=usuario)
    db.commit()
    assert not vocabulario.mismo_ambito(lugar, lugar2)
    with __import__("pytest").raises(vocabulario.ErrorFusion):
        vocabulario.fusionar(db, definitiva=lugar, absorbida=lugar2, usuario_id=usuario)
    assert not vocabulario.compartida("agente", "mecanismo") and vocabulario.compartida("agente", "persona")


def test_reservado_en_un_fondo_no_nombra_la_autoridad(cliente, db, fondo, admin, archivista, motor_prueba):  # noqa: F811
    _publicar(cliente, db, fondo, archivista, "a.pdf")
    alcaldia = _agente(db, fondo, "Alcaldía Municipal")
    otro = _otro_fondo(db, admin)
    # Una autoridad nueva, registrada en el primer fondo pero citada solo por una descripción reservada del otro.
    secreta = vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Comité Reservado", subtipo="entidad_corporativa",
                                origen="persona", confianza=None, motor=None, usuario_id=admin.id)
    db.commit()
    publicada = _publicar(cliente, db, otro, archivista, "b.pdf", reutilizar={"Alcaldía Municipal": alcaldia.id})
    recurso = db.get(RecursoDocumental, uuid.UUID(publicada["id"]))
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=recurso.id, destino_tipo="entidad_vocabulario",
                    destino_id=secreta.id, tipo_relacion="procedencia", codigo_ric="has_creator", origen="persona"))
    from app.servicios import derechos

    derechos.declarar(db, entidad_tipo="recurso_documental", entidad_id=recurso.id, base="estatuto", acceso="reservado",
                      reproduccion="no_permitida", fundamento="Ley 1712 de 2014, art. 19", nota=None,
                      vigente_hasta=__import__("datetime").date(2030, 1, 1), usuario_id=admin.id)
    db.commit()
    publico = exportacion_rico.exportar(db, otro).grafo
    assert (URIRef(exportacion_rico.base() + str(secreta.id)), None, None) not in publico
    assert secreta.id in exportacion_rico._entidades_vedadas(db, otro, exportacion_rico._recursos(
        db, otro, False, __import__("collections").Counter()))
