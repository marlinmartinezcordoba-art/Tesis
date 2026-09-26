"""Búsqueda contextual (T053 / F14): texto completo de PostgreSQL sobre las
páginas ya extraídas, con ranking, más coincidencia de nombre sobre las
entidades del grafo — cada resultado de entidad enlaza a su grafo de
relaciones ya validadas (ric.grafo), que es lo que le da a F14 su parte de
"navegación por relaciones".

Aclaración honesta: esto NO es búsqueda semántica por embeddings (eso
requeriría un modelo de embeddings, fuera de alcance de este ciclo) sino
la búsqueda de texto completo en español que ya trae PostgreSQL —
encuentra variantes de la palabra (conjugaciones, plurales), no solo la
cadena exacta, y ordena por relevancia.
"""

from django.apps import apps
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

from . import tipos
from .models import PaginaTexto


def _tipos_buscables():
    """Los modelos de entidad que de verdad se instancian por sí solos: se
    excluyen las categorías RiC-CM que solo existen como base de herencia
    multitabla (RecordResource, Agent, Group, Event, Rule) — buscar sobre
    ellas duplicaría cada fila ya contada bajo su subtipo concreto."""
    modelos = [apps.get_model("ric", nombre) for nombre in tipos.RIC_ID_A_MODELO_NOMBRE.values()]
    con_hijos = {m.__bases__[0] for m in modelos if m.__bases__[0] in modelos}
    return [m for m in modelos if m not in con_hijos]


def buscar_texto(q, limite=20):
    """Páginas cuyo texto extraído coincide con `q` (texto completo en
    español, con ranking), la más relevante primero."""
    vector = SearchVector("texto", config="spanish")
    query = SearchQuery(q, config="spanish")
    return (
        PaginaTexto.objects.annotate(busqueda=vector, rank=SearchRank(vector, query))
        .filter(busqueda=query)
        .select_related("instanciacion", "instanciacion__record_resource")
        .order_by("-rank")[:limite]
    )


def buscar_entidades(q, limite=20):
    """Entidades del grafo cuyo nombre coincide con `q`, de cualquier tipo
    concreto (Person, CorporateBody, Record...), para poder navegar de ahí
    a sus relaciones ya validadas."""
    resultados = []
    for modelo in _tipos_buscables():
        resultados.extend(modelo.objects.filter(nombre__icontains=q)[:limite])
    return resultados[:limite]
