"""
Requisitos 2 y 5, como se acordaron.

2. Tipo de contenido: varios a la vez (un oficio con fotografías es «texto» e
   «imagen fija»; rico:hasContentOfType admite varios valores). La
   administración agrega tipos sin tocar el código; uno en uso no se retira.
5. Digitalización: un estado aparte del estado del documento. «Digitalizado»
   no es «verificado»: la verificación la declara una persona, comprobación
   por comprobación, y queda con su nombre, su fecha y su historial.
"""

from datetime import date, timedelta

from rdflib import Namespace

from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico
from tests.test_descripcion import archivista, documento, fondo, iniciar  # noqa: F401
from tests.test_descripcion_v3 import TEXTO, publicar, sin_motor  # noqa: F401

RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")


def test_varios_tipos_de_contenido_y_tipos_propios(cliente, db, fondo, archivista, sin_motor, cabeceras_admin):  # noqa: F811
    d = documento(db, fondo, "oficio.pdf", TEXTO)
    espacio = iniciar(cliente, archivista, [d.id])
    r = publicar(cliente, archivista, espacio, titulo="Oficio con fotografías", tipos_contenido=["texto", "imagen_fija"])
    assert r.status_code == 201, r.text
    oficio = r.json()
    assert oficio["tipos_contenido"] == ["texto", "imagen_fija"]
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    assert len(list(g.objects(exportacion_rico.uri(oficio["id"]), RICO.hasContentOfType))) == 2

    # Un tipo desconocido no entra; la administración lo agrega y queda disponible.
    d2 = documento(db, fondo, "maqueta.pdf", TEXTO)
    espacio2 = iniciar(cliente, archivista, [d2.id])
    assert publicar(cliente, archivista, espacio2, titulo="Maqueta", tipos_contenido=["objeto_3d"]).status_code == 422
    assert cliente.put("/api/descripcion/tipos-contenido", headers=archivista,
                       json=[{"clave": "objeto_3d", "nombre": "Objeto tridimensional"}]).status_code == 403
    r = cliente.put("/api/descripcion/tipos-contenido", headers=cabeceras_admin,
                    json=[{"clave": "objeto_3d", "nombre": "Objeto tridimensional"}])
    assert r.status_code == 200 and {"clave": "objeto_3d", "nombre": "Objeto tridimensional", "propio": True} in r.json()
    assert publicar(cliente, archivista, espacio2, titulo="Maqueta", tipos_contenido=["objeto_3d"]).status_code == 201
    # En uso: no se retira.
    assert cliente.put("/api/descripcion/tipos-contenido", headers=cabeceras_admin, json=[]).status_code == 409
    # Una clave de RiC-CM no se repite.
    assert cliente.put("/api/descripcion/tipos-contenido", headers=cabeceras_admin,
                       json=[{"clave": "objeto_3d", "nombre": "Objeto tridimensional"},
                             {"clave": "texto", "nombre": "Otro texto"}]).status_code == 422


def test_digitalizado_no_es_verificado(cliente, db, fondo, archivista, sin_motor):  # noqa: F811
    d = documento(db, fondo, "acta.pdf", TEXTO)
    espacio = iniciar(cliente, archivista, [d.id])
    acta = publicar(cliente, archivista, espacio, titulo="Acta 12").json()
    url = f"/api/descripcion/registros/{acta['id']}/digitalizacion"
    assert cliente.get(url, headers=archivista).json()["estado"] == "nacido_digital"

    # Con el original en papel registrado, el archivo queda como su digitalización: digitalizado, sin verificar.
    cliente.post(f"/api/descripcion/registros/{acta['id']}/original-fisico", headers=archivista,
                 json={"soporte": "papel", "ubicacion": "Caja 3"})
    e = cliente.get(url, headers=archivista).json()
    assert e["estado"] == "digitalizado" and e["estado_nombre"] == "Digitalizado, sin verificar"
    rel = e["digitalizaciones"][0]["relacion_id"]

    # Quién, cuándo, con qué equipo y a qué resolución.
    base = f"/api/descripcion/digitalizaciones/{rel}"
    manana = (date.today() + timedelta(days=1)).isoformat()
    assert cliente.put(base, headers=archivista, json={"fecha": manana}).status_code == 422
    assert cliente.put(base, headers=archivista, json={"resolucion_ppp": 10}).status_code == 422
    e = cliente.put(base, headers=archivista, json={"responsable": "Laura Gómez", "fecha": "2026-09-01",
                                                    "equipo": "Escáner planetario", "resolucion_ppp": 300}).json()
    assert e["digitalizaciones"][0]["datos"]["responsable"] == "Laura Gómez" and e["estado"] == "digitalizado"

    # Verificar: cada comprobación; con problemas exige decir cuál.
    todas = {"completa": True, "legible": True, "fiel": True, "integra": True}
    assert cliente.post(f"{base}/verificaciones", headers=archivista, json={"comprobaciones": {"completa": True}}).status_code == 422
    falla = {**todas, "completa": False}
    assert cliente.post(f"{base}/verificaciones", headers=archivista, json={"comprobaciones": falla}).status_code == 422
    e = cliente.post(f"{base}/verificaciones", headers=archivista,
                     json={"comprobaciones": falla, "nota": "Faltan los folios 12 y 13"}).json()
    assert e["estado"] == "con_problemas"
    e = cliente.post(f"{base}/verificaciones", headers=archivista, json={"comprobaciones": todas}).json()
    assert e["estado"] == "verificado" and len(e["digitalizaciones"][0]["verificaciones"]) == 2
    assert e["digitalizaciones"][0]["verificaciones"][0]["verificado_por"] == "Catalina Torres"

    # En RiC-O: la digitalización con su fecha y sus datos, y la verificación como otra actividad sobre la copia.
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    textos = " ".join(str(o) for o in g.objects(None, RICO.generalDescription))
    assert "Digitalizó: Laura Gómez" in textos and "300 ppp" in textos and "Verificada" in textos
    verificaciones = [s for s in g.subjects(RICO.affectsOrAffected, exportacion_rico.uri(d.id))
                      if "/verificacion/" in str(s)]
    assert len(verificaciones) == 2
