"""
Vista de consulta pública de una descripción.

Punto final de la regla de procedencia: se arma con una lista cerrada de
campos permitidos (nunca quitando campos de la vista interna), así que un
campo interno nuevo no puede colarse por descuido. Origen, confianza,
motor, estado de revisión y fragmentos citados no salen jamás de aquí.
"""

from sqlalchemy.orm import Session

from app.models.recurso_documental import RecursoDocumental
from app.servicios.descripcion import detalle

CAMPOS_PROHIBIDOS = {"origen", "confianza", "motor", "estado_revision", "origen_titulo", "origen_alcance",
                     "confianza_alcance", "fragmento", "documento_id"}


def ficha_publica(db: Session, recurso: RecursoDocumental) -> dict:
    d = detalle(db, recurso)
    return {
        "id": d["id"],
        "nivel": d["nivel"],
        "titulo": d["titulo"],
        "alcance_contenido": d["alcance_contenido"],
        "incluido_en": d["incluido_en"],
        "forma_documental": d["forma_documental"]["nombre"] if d["forma_documental"] else None,
        "entidades": [
            {"entidad_id": e["entidad_id"], "tipo": e["tipo"], "valor": e["valor"], "subtipo": e["subtipo"],
             "rol": e["rol"], "codigo_ric": e["codigo_ric"], "uri_rico": e["uri_rico"],
             **({"fecha_normalizada": e["fecha_normalizada"]} if "fecha_normalizada" in e else {})}
            for e in d["entidades"]
        ],
        "instanciaciones": d["instanciaciones"],
        "publicado_en": d["publicado_en"],
    }
