"""Motor de reglas: valida que una RelacionRiC respete el dominio/rango
verificado contra RiC-CM 1.0 / RiC-O 1.1 (ric/fixtures/ric_matrix.json).

No es un diccionario mantenido a mano: lee siempre el fixture, así que una
corrección futura en la matriz verificada se propaga sin tocar código.
"""

import json
from pathlib import Path
from threading import Lock

from . import tipos

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "ric_matrix.json"
_cache = None
_lock = Lock()


class RelacionInvalida(Exception):
    """La relación propuesta no respeta el dominio/rango de RiC-CM 1.0."""


def cargar_matriz():
    """La matriz verificada completa (entidades, relaciones, atributos);
    ver ric/fixtures/ric_matrix.json."""
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                with open(_FIXTURE_PATH, encoding="utf-8") as f:
                    _cache = json.load(f)
    return _cache


def _tipos_permitidos(expresion_dominio_o_rango):
    """'Record Resource or Instantiation' -> (modelo RecordResource, modelo Instantiation).
    'Thing' -> None (comodín: cualquier tipo es válido)."""
    partes = [p.strip() for p in expresion_dominio_o_rango.replace(" or ", ",").split(",")]
    if "Thing" in partes:
        return None
    modelos = []
    for parte in partes:
        modelo = tipos.nombre_cm_a_modelo(parte)
        if modelo is None:
            raise RelacionInvalida(f"Tipo RiC-CM desconocido en la matriz: {parte!r}")
        modelos.append(modelo)
    return tuple(modelos)


def entidades_para(relacion_id):
    """Devuelve (modelos_dominio, modelos_rango) para un ID de relación, o
    (None, None) si el dominio/rango es 'Thing' (cualquier entidad)."""
    matriz = cargar_matriz()
    datos = matriz["relaciones"].get(relacion_id)
    if datos is None:
        raise RelacionInvalida(
            f"'{relacion_id}' no está en el inventario verificado de RiC-CM 1.0 "
            "(ric/fixtures/ric_matrix.json). Si es 'R043': no existe en la norma, confirmado."
        )
    return _tipos_permitidos(datos["dominio_cm"]), _tipos_permitidos(datos["rango_cm"])


def validar_relacion(relacion_id, origen, destino):
    """Lanza RelacionInvalida si `origen` u `destino` no encajan en el
    dominio/rango oficial de `relacion_id`. No hace nada si son válidos."""
    modelos_dominio, modelos_rango = entidades_para(relacion_id)
    nombre = cargar_matriz()["relaciones"][relacion_id]["nombre"]

    if modelos_dominio is not None and not isinstance(origen, modelos_dominio):
        permitidos = ", ".join(m.__name__ for m in modelos_dominio)
        raise RelacionInvalida(
            f"'{relacion_id}' ({nombre}): el origen debe ser {permitidos}, "
            f"no {type(origen).__name__}."
        )
    if modelos_rango is not None and not isinstance(destino, modelos_rango):
        permitidos = ", ".join(m.__name__ for m in modelos_rango)
        raise RelacionInvalida(
            f"'{relacion_id}' ({nombre}): el destino debe ser {permitidos}, "
            f"no {type(destino).__name__}."
        )


def info_relacion(relacion_id):
    """Nombre, dominio, rango, URI RiC-O e inversa tal como se verificaron."""
    matriz = cargar_matriz()
    datos = matriz["relaciones"].get(relacion_id)
    if datos is None:
        raise RelacionInvalida(f"'{relacion_id}' no está en el inventario verificado.")
    return datos
