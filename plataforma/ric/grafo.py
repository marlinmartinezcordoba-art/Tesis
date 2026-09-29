"""Subgrafo navegable centrado en una entidad, como nodos/aristas para
Cytoscape.js (T052). Mismo alcance que `ric.rdf.grafo_de_entidad` — el
vecindario a un salto, solo con relaciones ya validadas — pero en el
formato que espera Cytoscape.js en vez de RDF.
"""

from functools import lru_cache

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from . import reglas
from .models import PropuestaRiC, RelacionRiC

# M4 (RF-M4-01): las cuatro categorías de relación del documento de
# especificación, asignadas por el nombre verificado de cada relación
# RiC-CM. Es una agrupación para leer y colorear el grafo, no una
# propiedad de RiC-CM (que no clasifica así sus relaciones).
CATEGORIAS = {
    "procedencia": ("Procedencia", "#c08a3e"),
    "temporal": ("Temporal", "#7046d9"),
    "inclusion": ("Inclusión", "#1f6f8b"),
    "asociacion": ("Asociación", "#6b8cae"),
}
# Procedencia = quién produjo, creó, acumuló o firmó el documento (CC-03).
# "addressee" (destinatario) y "subject" son asociación: recibir o ser tema
# de un documento no es producirlo.
_PALABRAS_CATEGORIA = (
    ("procedencia", ("provenance", "creator", "accumulat", "author", "sender", "collector", "publisher")),
    ("temporal", ("date", "precede", "follow", "existence", "beginning", "end")),
    ("inclusion", ("include", "constituent", "part", "member", "subdivision", "subordinate", "contain", "component")),
)


def categoria_relacion(relacion_id):
    nombre = reglas.cargar_matriz()["relaciones"].get(relacion_id, {}).get("nombre", "").lower()
    for categoria, palabras in _PALABRAS_CATEGORIA:
        if any(p in nombre for p in palabras):
            return categoria
    return "asociacion"


@lru_cache(maxsize=256)
def _relaciones_validas_entre_nombres(nombre_origen, nombre_destino):
    from django.apps import apps

    origen = apps.get_model("ric", nombre_origen)
    destino = apps.get_model("ric", nombre_destino)
    validas = []
    for rid, datos in reglas.cargar_matriz()["relaciones"].items():
        try:
            dominio, rango = reglas.entidades_para(rid)
        except reglas.RelacionInvalida:
            continue
        if dominio is not None and not issubclass(origen, dominio):
            continue
        if rango is not None and not issubclass(destino, rango):
            continue
        validas.append({"id": rid, "nombre": datos["nombre"], "categoria": categoria_relacion(rid)})
    return validas


def relaciones_validas_entre(origen, destino):
    """RF-M4-03: la lista controlada de tipos de relación que RiC-CM 1.0
    permite entre estas dos entidades concretas (dominio/rango verificados)."""
    return _relaciones_validas_entre_nombres(type(origen).__name__, type(destino).__name__)


def _id_nodo(entidad):
    return f"{type(entidad).__name__}:{entidad.pk}"


def _nodo(entidad, central=False):
    return {
        "data": {
            "id": _id_nodo(entidad),
            "label": str(entidad),
            "tipo": type(entidad).__name__,
            "central": central,
        }
    }


def subgrafo_json(entidad):
    content_type = ContentType.objects.get_for_model(entidad)
    relaciones = (
        RelacionRiC.objects.filter(
            Q(origen_content_type=content_type, origen_object_id=entidad.pk)
            | Q(destino_content_type=content_type, destino_object_id=entidad.pk),
            estado__in=(RelacionRiC.Estado.ACEPTADA, RelacionRiC.Estado.MODIFICADA),
        )
        .select_related("origen_content_type", "destino_content_type")
    )

    nodos = {_id_nodo(entidad): _nodo(entidad, central=True)}
    aristas = []
    matriz = reglas.cargar_matriz()["relaciones"]
    for r in relaciones:
        origen, destino = r.origen, r.destino
        if origen is None or destino is None:
            continue  # la entidad referenciada se borró; no hay nada que dibujar
        for e in (origen, destino):
            nodos.setdefault(_id_nodo(e), _nodo(e))
        etiqueta = matriz.get(r.relacion_id, {}).get("nombre", r.relacion_id)
        aristas.append({
            "data": {
                "id": f"rel:{r.pk}",
                "source": _id_nodo(origen),
                "target": _id_nodo(destino),
                "label": etiqueta,
            }
        })
    return {"nodes": list(nodos.values()), "edges": aristas}


def subgrafo_documento(record):
    """M4: el lienzo de un documento — el Record como nodo central, sus
    relaciones ya validadas (línea continua, editables) y las propuestas
    todavía pendientes (línea punteada, se deciden en M3). Cada arista
    validada trae la lista controlada de tipos válidos para corregirla."""
    content_type = ContentType.objects.get_for_model(record)
    matriz = reglas.cargar_matriz()["relaciones"]
    nodos = {_id_nodo(record): _nodo(record, central=True)}
    aristas = []

    relaciones = RelacionRiC.objects.filter(
        Q(origen_content_type=content_type, origen_object_id=record.pk)
        | Q(destino_content_type=content_type, destino_object_id=record.pk),
        estado__in=(RelacionRiC.Estado.ACEPTADA, RelacionRiC.Estado.MODIFICADA),
    )
    for r in relaciones:
        origen, destino = r.origen, r.destino
        if origen is None or destino is None:
            continue
        for e in (origen, destino):
            nodos.setdefault(_id_nodo(e), _nodo(e))
        categoria = categoria_relacion(r.relacion_id)
        aristas.append({"data": {
            "id": f"rel:{r.pk}", "pk": r.pk, "source": _id_nodo(origen), "target": _id_nodo(destino),
            "label": matriz.get(r.relacion_id, {}).get("nombre", r.relacion_id),
            "relacion_id": r.relacion_id, "estado": r.estado, "categoria": categoria,
            "color": CATEGORIAS[categoria][1], "opciones": relaciones_validas_entre(origen, destino),
        }})

    pendientes = PropuestaRiC.objects.filter(
        origen_content_type=content_type, origen_object_id=record.pk, estado=PropuestaRiC.Estado.PENDIENTE,
    )
    for p in pendientes:
        id_nodo = f"prop:{p.pk}"
        nodos[id_nodo] = {"data": {"id": id_nodo, "label": p.entidad_nombre, "tipo": p.entidad_tipo, "propuesta": True}}
        categoria = categoria_relacion(p.relacion_id)
        aristas.append({"data": {
            "id": f"prop-rel:{p.pk}", "pk": p.pk, "source": _id_nodo(record), "target": id_nodo,
            "label": matriz.get(p.relacion_id, {}).get("nombre", p.relacion_id) + " (propuesta)",
            "relacion_id": p.relacion_id, "estado": "pendiente", "propuesta": True,
            "categoria": categoria, "color": CATEGORIAS[categoria][1],
        }})
    return {"nodes": list(nodos.values()), "edges": aristas}
