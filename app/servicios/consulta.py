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
                     "confianza_alcance", "fragmento", "documento_id", "origen_idiomas", "confianza_idiomas"}


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
             **{k: e[k] for k in ("fecha_normalizada", "fecha_subtipo", "edtf", "fecha_legible", "fecha_inicio",
                                  "fecha_fin", "calendario", "contexto", "expedicion") if k in e}}
            for e in d["entidades"]
        ],
        "instanciaciones": d["instanciaciones"],
        # Versión 3: idioma, condiciones de acceso y de uso, partes y secuencia.
        "idiomas": d["idiomas"],
        "condiciones_acceso": d["condiciones_acceso"],
        "condiciones_uso": d["condiciones_uso"],
        "tipo_parte": d["tipo_parte"]["nombre"] if d["tipo_parte"] else None,
        "partes": [{"id": p["id"], "titulo": p["titulo"], "tipo_parte": p["tipo_parte"],
                    "alcance_contenido": p["alcance_contenido"],
                    "instanciaciones": [{"id": i["id"], "nombre": i["nombre"]} for i in p["instanciaciones"]]}
                   for p in d["partes"]],
        "parte_de": {k: d["parte_de"][k] for k in ("id", "titulo", "nivel")} if d["parte_de"] else None,
        "secuencia": [{"id": x["id"], "titulo": x["titulo"], "posicion": x["posicion"], "uri_rico": x["uri_rico"]}
                      for x in d["secuencia"]],
        "publicado_en": d["publicado_en"],
    }
