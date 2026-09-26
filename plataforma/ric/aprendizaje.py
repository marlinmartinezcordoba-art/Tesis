"""Aprendizaje asistido simple (Fase 6, T060-T061): recuperación de
ejemplos ya validados por la persona archivista, para inyectarlos como
contexto en el prompt de ProveedorClaude — RAG (retrieval-augmented
generation) sin fine-tuning, tal como lo pedía la matriz maestra.

T060 ("almacenar ejemplos validados: fragmento, ric_id propuesto, decisión
final") no necesita una tabla nueva: cada `PropuestaRiC` ya validada ES ese
ejemplo — su `Evidencia.fragmento` es el fragmento, `relacion_id` es la
relación propuesta, `estado` es la decisión final. Duplicarlo en otra
tabla violaría la única fuente de verdad que ya existe; este módulo solo
agrega la forma de consultarlo.

`ProveedorLocal` (spaCy, reconocimiento de entidades por reglas) no tiene
un prompt de texto libre que se pueda enriquecer con ejemplos — a
diferencia de lo que asumía la planeación original, la recuperación de
T061 solo tiene sentido para `ProveedorClaude`.
"""

from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import TrigramSimilarity

from .models import PropuestaRiC

UMBRAL_SIMILITUD = 0.12


def ejemplos_validados(estados=(PropuestaRiC.Estado.ACEPTADA, PropuestaRiC.Estado.MODIFICADA)):
    """Las propuestas que una persona ya validó (no un auto-rechazo del
    motor de reglas) y que tienen evidencia real — la "tabla de ejemplos"
    de T060, reutilizando `PropuestaRiC` en vez de duplicarla."""
    return (
        PropuestaRiC.objects.filter(estado__in=estados, evidencia__isnull=False)
        .exclude(validado_por__isnull=True)
        .select_related("evidencia")
    )


def ejemplos_similares(texto, origen_modelo=None, limite=5):
    """Los `limite` ejemplos ya validados cuyo fragmento de evidencia es
    más parecido a `texto`, por similitud de trigramas de PostgreSQL
    (`pg_trgm`) — no es una búsqueda por embeddings, pero a diferencia de
    la búsqueda de texto completo (`ric.busqueda`, pensada para encontrar
    coincidencias exactas de palabra) da un puntaje continuo de parecido
    aunque `texto` sea un documento largo y el fragmento un puñado de
    palabras, que es exactamente el caso de uso de la recuperación (T061)."""
    if not texto.strip():
        return []
    qs = (
        ejemplos_validados()
        .annotate(similitud=TrigramSimilarity("evidencia__fragmento", texto))
        .filter(similitud__gt=UMBRAL_SIMILITUD)
    )
    if origen_modelo is not None:
        qs = qs.filter(origen_content_type=ContentType.objects.get_for_model(origen_modelo))
    return list(qs.order_by("-similitud")[:limite])


def formatear_ejemplos(ejemplos):
    """Los ejemplos recuperados, como texto para inyectar en el prompt de
    ProveedorClaude: fragmento -> relación -> tipo/nombre propuesto ->
    decisión final de la persona archivista."""
    lineas = []
    for p in ejemplos:
        decision = {
            PropuestaRiC.Estado.ACEPTADA: "aceptada tal cual",
            PropuestaRiC.Estado.MODIFICADA: "aceptada, pero corregida por la persona archivista",
        }.get(p.estado, p.estado)
        lineas.append(
            f'- Fragmento: "{p.evidencia.fragmento}"\n'
            f"  Propuesta: {p.relacion_id} -> {p.entidad_tipo} \"{p.entidad_nombre}\" ({decision})"
        )
    return "\n".join(lineas)
