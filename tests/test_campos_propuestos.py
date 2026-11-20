"""La descripción exhaustiva: RICORA propone los campos además de las entidades, con su
evidencia, y la persona los aprueba. Nada decide el acceso."""

import uuid
from types import SimpleNamespace

from app.db.base import ahora
from app.models.recurso_documental import RecursoDocumental
from app.servicios import campos_propuestos

TEXTO = ("RESOLUCIÓN No. 2001 por la cual se resuelve el recurso de reposición contra la Resolución 0818 del 18 de "
         "junio de 2025, expedida por el Ministerio de Ambiente y Desarrollo Sostenible, sobre la sustracción temporal.")


def _doc(texto=TEXTO, paginas=3):
    return SimpleNamespace(texto_extraido=texto, paginas=paginas)


def test_propone_cada_campo_con_su_evidencia(db):
    fondo = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Fondo de prueba")
    fondo.fondo_id = fondo.id
    db.add(fondo)
    db.flush()
    citada = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", fondo_id=fondo.id, incluido_en_id=fondo.id,
                               titulo="Resolución 818 de 2025 sobre sustracción", publicado_en=ahora())
    otra = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", fondo_id=fondo.id, incluido_en_id=fondo.id,
                             titulo="Resolución No. 1919 contra la Resolución 0818", publicado_en=ahora())
    db.add_all([citada, otra])
    db.flush()
    propuesta = {"idiomas": ["spa"], "confianza_idiomas": 0.95,
                 "documentos_citados": [{"valor": "Resolución 0818 del 18 de junio de 2025", "fragmento": "contra la Resolución 0818"}]}
    salida = campos_propuestos.proponer(db, fondo_id=fondo.id, nivel="unidad_documental", documentos=[_doc()],
                                        propuesta=propuesta, completitud={"nota_propuesta": "Faltan las páginas 2 y 3."})
    por_campo = {c["campo"]: c for c in salida}
    assert por_campo["idiomas"]["valor"] == ["spa"] and por_campo["idiomas"]["origen"] == "motor"
    assert por_campo["tipos_contenido"]["valor"] == ["texto"]
    assert por_campo["folios"]["valor"] == 3
    assert por_campo["nota_integridad"]["valor"] == "Faltan las páginas 2 y 3."
    # El documento citado es el que lleva ese número propio, no el que solo lo menciona.
    assert por_campo["asociado_a"]["valor"]["id"] == str(citada.id)
    assert "estado_documento" not in por_campo  # sin evidencia no se propone
    assert all(c["evidencia"] for c in salida) and "acceso" not in por_campo


def test_estado_solo_con_evidencia_y_folios_solo_si_se_conocen(db):
    salida = campos_propuestos.proponer(db, fondo_id=uuid.uuid4(), nivel="unidad_documental",
                                        documentos=[_doc("ES FIEL COPIA DEL ORIGINAL. " + TEXTO, paginas=None)],
                                        propuesta=None, completitud=None)
    por_campo = {c["campo"]: c for c in salida}
    assert por_campo["estado_documento"]["valor"] == "copia_autentica"
    assert "FIEL COPIA" in por_campo["estado_documento"]["evidencia"]
    assert "folios" not in por_campo


from tests.test_descripcion import archivista, documento, fondo, iniciar  # noqa: E402,F401
from tests.test_descripcion_v3 import publicar, sin_motor  # noqa: E402,F401


def test_la_pantalla_los_trae_y_la_decision_queda_en_la_auditoria(cliente, db, fondo, archivista, sin_motor):  # noqa: F811
    from sqlalchemy import select

    from app.models.auditoria import RegistroAuditoria

    espacio = iniciar(cliente, archivista, [documento(db, fondo, "campos.pdf", TEXTO).id])
    campos = {c["campo"] for c in espacio["campos_propuestos"]}
    assert "tipos_contenido" in campos
    r = publicar(cliente, archivista, espacio, titulo="Resolución con campos",
                 campos_ia=[{"campo": "tipos_contenido", "origen": "regla", "decision": "aceptada"}])
    assert r.status_code in (200, 201), r.text
    ev = db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "campos_propuestos_decididos"))
    assert ev is not None and ev.valor_nuevo["campos"][0]["decision"] == "aceptada"
