"""Subgrafo navegable centrado en una entidad, como nodos/aristas para
Cytoscape.js (T052). Mismo alcance que `ric.rdf.grafo_de_entidad` — el
vecindario a un salto, solo con relaciones ya validadas — pero en el
formato que espera Cytoscape.js en vez de RDF.
"""

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from . import reglas
from .models import RelacionRiC


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
