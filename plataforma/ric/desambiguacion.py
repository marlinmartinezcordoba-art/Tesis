"""F10 (Desambiguación): detectar sola cuando una entidad nueva podría ser
duplicado de una que ya existe, y sugerirlo — nunca decide por su cuenta,
"sugerir" es el límite: fusionar sigue siendo una decisión del archivista
(ver ric.fusion, F08).

No reemplaza la coincidencia EXACTA de nombre que ya usa
`PropuestaRiC.validar()` (`modelo.objects.get_or_create(nombre=...)`): esa
ya evita crear un duplicado cuando el nombre propuesto es idéntico letra
por letra a uno existente. Esto cubre el caso que esa coincidencia exacta
no detecta: nombres escritos ligeramente distinto ("Cabildo de Santafé"
vs. "Cabildo de Santa Fe"), con similitud de trigramas de PostgreSQL
(`pg_trgm`, ya habilitado desde F11/T061 — ver ric.aprendizaje).

UMBRAL_SIMILITUD se calibró con pares reales, no al azar: variantes
verdaderas de un mismo nombre (con/sin tilde, con/sin apellido agregado)
dieron 0.57-0.77 de similitud; pares de entidades reamente distintas que
solo comparten un prefijo institucional común ("Cabildo de Cartagena" vs.
"Cabildo de Santafé", "Notaría Primera" vs. "Notaría Segunda") se quedaron
en 0.33-0.41 — 0.5 separa limpio a los dos grupos.
"""

from django.contrib.postgres.search import TrigramSimilarity

UMBRAL_SIMILITUD = 0.5
LIMITE_POR_DEFECTO = 5


def candidatos_similares(modelo, nombre, excluir_pk=None, limite=LIMITE_POR_DEFECTO):
    """Instancias ya guardadas de `modelo` cuyo nombre es parecido (no
    idéntico) a `nombre`, de más a menos parecidas. Lista vacía si `nombre`
    está vacío o si nada supera el umbral."""
    if not nombre.strip():
        return []
    qs = (
        modelo.objects.exclude(nombre__iexact=nombre)
        .annotate(similitud=TrigramSimilarity("nombre", nombre))
        .filter(similitud__gte=UMBRAL_SIMILITUD)
    )
    if excluir_pk is not None:
        qs = qs.exclude(pk=excluir_pk)
    return list(qs.order_by("-similitud")[:limite])


def pares_similares(modelo, limite=50):
    """Todos los pares de instancias YA EXISTENTES de `modelo` que se
    parecen entre sí — el lado "sola, sin que nadie proponga nada nuevo"
    de F10: encuentra duplicados que ya estaban en la base antes de que
    esto existiera. Cada par aparece una sola vez (a, b) con a.pk < b.pk."""
    vistos = set()
    pares = []
    for entidad in modelo.objects.order_by("pk"):
        for similar in candidatos_similares(modelo, entidad.nombre, excluir_pk=entidad.pk, limite=limite):
            clave = tuple(sorted((entidad.pk, similar.pk)))
            if clave in vistos:
                continue
            vistos.add(clave)
            a, b = (entidad, similar) if entidad.pk < similar.pk else (similar, entidad)
            pares.append((a, b))
        if len(pares) >= limite:
            break
    return pares[:limite]
