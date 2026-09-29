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
from django.db.models import Q

UMBRAL_SIMILITUD = 0.5
LIMITE_POR_DEFECTO = 5


def candidatos_similares(modelo, nombre, excluir_pk=None, limite=LIMITE_POR_DEFECTO, identificador=""):
    """Instancias ya guardadas de `modelo` cuyo nombre es parecido (no
    idéntico) a `nombre`, de más a menos parecidas. Lista vacía si `nombre`
    está vacío o si nada supera el umbral.

    Si la entidad tiene código oficial (`identificador`, RiC-A22), las
    entradas con OTRO código no cuentan como duplicado: dos series de la TRD
    con el mismo nombre en oficinas distintas son dos series."""
    if not nombre.strip():
        return []
    qs = (
        modelo.objects.exclude(nombre__iexact=nombre)
        .annotate(similitud=TrigramSimilarity("nombre", nombre))
        .filter(similitud__gte=UMBRAL_SIMILITUD)
    )
    if excluir_pk is not None:
        qs = qs.exclude(pk=excluir_pk)
    if identificador and any(f.name == "identificador" for f in modelo._meta.fields):
        qs = qs.exclude(~Q(identificador="") & ~Q(identificador=identificador))
    return list(qs.order_by("-similitud")[:limite])


def pares_similares(modelo, limite=50):
    """Todos los pares de instancias YA EXISTENTES de `modelo` que se
    parecen entre sí — el lado "sola, sin que nadie proponga nada nuevo"
    de F10: encuentra duplicados que ya estaban en la base antes de que
    esto existiera. Cada par aparece una sola vez (a, b) con a.pk < b.pk,
    los más parecidos primero.

    Es una sola consulta con auto-join sobre la tabla que guarda `nombre`
    (en herencia multitabla es la del ancestro concreto, p. ej. ric_event
    para Activity) restringida a las filas propias del modelo: con un
    vocabulario real (cientos de series, más de mil formas documentales)
    una consulta por entidad tardaba segundos en cada carga de pantalla."""
    from django.db import connection

    from . import tipos

    campo = modelo._meta.get_field("nombre")
    tabla = connection.ops.quote_name(campo.model._meta.db_table)
    columna_pk = connection.ops.quote_name(campo.model._meta.pk.column)
    columnas = [columna_pk, "nombre"]
    # Dos entradas con código oficial distinto (RiC-A22, p. ej. dos series de
    # la TRD con el mismo nombre en oficinas distintas) no son duplicados.
    con_identificador = any(f.name == "identificador" for f in campo.model._meta.fields)
    if con_identificador:
        columnas.append("identificador")
    propias = tipos.instancias_propias(modelo).order_by().values("pk").query
    sql_propias, params_propias = propias.sql_with_params()
    filtro_codigo = (
        " AND NOT (a.identificador <> '' AND b.identificador <> '' AND a.identificador <> b.identificador)"
        if con_identificador else ""
    )
    sql = (
        f"WITH p AS (SELECT {', '.join(columnas)} FROM {tabla} WHERE {columna_pk} IN ({sql_propias})) "
        f"SELECT a.{columna_pk}, b.{columna_pk}, similarity(a.nombre, b.nombre) AS sim "
        f"FROM p a JOIN p b ON a.{columna_pk} < b.{columna_pk} "
        # Prefiltro barato antes de calcular trigramas sobre cada par: dos
        # variantes del mismo nombre empiezan por la misma letra.
        f"AND left(lower(a.nombre), 1) = left(lower(b.nombre), 1) "
        f"WHERE lower(a.nombre) <> lower(b.nombre){filtro_codigo} "
        f"AND similarity(a.nombre, b.nombre) >= %s "
        f"ORDER BY sim DESC, a.{columna_pk}, b.{columna_pk} LIMIT %s"
    )
    with connection.cursor() as cursor:
        cursor.execute(sql, (*params_propias, UMBRAL_SIMILITUD, limite))
        filas = cursor.fetchall()
    if not filas:
        return []
    pks = {pk for fila in filas for pk in fila[:2]}
    entidades = modelo.objects.in_bulk(pks)
    return [(entidades[a], entidades[b]) for a, b, _ in filas if a in entidades and b in entidades]
