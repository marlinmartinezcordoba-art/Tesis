"""
Vista de consulta pública de una descripción.

Punto final de la regla de procedencia: se arma con una lista cerrada de
campos permitidos (nunca quitando campos de la vista interna), así que un
campo interno nuevo no puede colarse por descuido. Origen, confianza,
motor, estado de revisión y fragmentos citados no salen jamás de aquí.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import derechos
from app.servicios.descripcion import detalle

CAMPOS_PROHIBIDOS = {"origen", "confianza", "motor", "estado_revision", "origen_titulo", "origen_alcance",
                     "confianza_alcance", "fragmento", "documento_id", "origen_idiomas", "confianza_idiomas"}


def ficha_publica(db: Session, recurso: RecursoDocumental, visibles: set[uuid.UUID],
                  ver_restringidos: bool) -> dict:
    """`visibles`: las descripciones que quien consulta puede ver (el árbol
    del catálogo con su regla de publicación y de reserva). Las partes, la
    secuencia y el nivel superior solo se nombran si están entre ellas, y
    un archivo bajo reserva vigente no se lista a quien no es archivista:
    el título de una parte reservada o el nombre de un archivo reservado
    pueden ser, en sí mismos, información reservada (Ley 1712, art. 19)."""
    d = detalle(db, recurso)

    def archivo_visible(i: dict) -> bool:
        if ver_restringidos:
            return True
        inst = db.get(Instanciacion, uuid.UUID(i["id"]))
        return inst is not None and not derechos.instanciacion_restringida(db, inst)

    d["instanciaciones"] = [i for i in d["instanciaciones"] if archivo_visible(i)]
    d["partes"] = [{**p, "instanciaciones": [i for i in p["instanciaciones"] if archivo_visible(i)]}
                   for p in d["partes"] if uuid.UUID(p["id"]) in visibles]
    d["secuencia"] = [x for x in d["secuencia"] if uuid.UUID(x["id"]) in visibles]
    if d["parte_de"] and uuid.UUID(d["parte_de"]["id"]) not in visibles:
        d["parte_de"] = None
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
                                  "fecha_fin", "calendario", "contexto", "expedicion", "periodo", "periodo_legible",
                                  "nota") if k in e}}
            for e in d["entidades"]
        ],
        "instanciaciones": d["instanciaciones"],
        # Versión 3: idioma, condiciones de acceso y de uso, partes y secuencia.
        "idiomas": d["idiomas"],
        "condiciones_acceso": d["condiciones_acceso"],
        "historia_archivistica": d["historia_archivistica"],
        "condiciones_uso": d["condiciones_uso"],
        # Ley 1680 de 2013 (AGN, principio 3): quien consulta sabe si hay versión accesible.
        "nota_accesibilidad": d["proteccion"]["nota_accesibilidad"],
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
