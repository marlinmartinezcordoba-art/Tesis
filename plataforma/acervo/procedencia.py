"""Sugerencia de procedencia para una unidad del cuadro de clasificación.

No es una llamada a un modelo de lenguaje: es una propuesta basada en datos
que ya existen en el grafo (qué productor aparece más entre los documentos
ya clasificados en esta serie). MAZUCA ya trata proveedores así de simples
como "IA" en otras partes (por ejemplo, ProveedorClasificacionLocal, que
compara palabras clave), así que esto sigue la misma lógica: es una
propuesta, no una escritura automática. La persona archivista sigue
teniendo que confirmarla a mano en el inline del admin — el sistema nunca
crea la relación de procedencia por sí solo.
"""

from collections import Counter


def sugerir_productor_unidad(unidad):
    """Devuelve (entidad, coincidencias, total) o None si no hay información
    suficiente entre los documentos ya clasificados en esta unidad."""
    productores = []
    for documento in unidad.documentos.all():
        relacion = documento.relacionentidaddocumento_set.filter(tipo_relacion="productor").first()
        if relacion:
            productores.append(relacion.entidad)

    if not productores:
        return None

    conteo = Counter(productores)
    entidad, coincidencias = conteo.most_common(1)[0]
    return entidad, coincidencias, len(productores)
