"""
Punto SPARQL de solo lectura (hallazgo INS-04).

La fuente es siempre el grafo público guardado de un fondo en el almacén de
tripletas (grafo_rdf), el mismo de /id/ y de la descarga sin sesión: nunca
la base de datos ni el grafo completo. Solo consultas de
lectura (SELECT, ASK, CONSTRUCT, DESCRIBE), sin SERVICE (que haría al
servidor consultar otros sitios), con límite de tiempo y de resultados.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as Agotado

from rdflib.plugins.sparql import prepareQuery

SEGUNDOS = 10
MAXIMO_FILAS = 10_000
_PROHIBIDO = re.compile(r"\b(SERVICE|LOAD|INSERT|DELETE|CLEAR|DROP|CREATE|COPY|MOVE|ADD)\b", re.I)
_LECTURA = {"SelectQuery", "AskQuery", "ConstructQuery", "DescribeQuery"}
_HILOS = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sparql")


class ErrorSparql(ValueError):
    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.codigo = codigo


def _sin_literales(consulta: str) -> str:
    """La consulta sin cadenas ni IRI, para buscar palabras clave sin confundirlas con datos."""
    return re.sub(r'"[^"]*"|\'[^\']*\'|<[^>\s]*>', " ", consulta)


def validar(consulta: str) -> None:
    """Solo lectura, SPARQL válido y de tamaño razonable; si no, ErrorSparql."""
    if not consulta or not consulta.strip():
        raise ErrorSparql("Falta la consulta.")
    if len(consulta) > 20_000:
        raise ErrorSparql("La consulta es demasiado larga.")
    if _PROHIBIDO.search(_sin_literales(consulta)):
        raise ErrorSparql("Solo se admiten consultas de lectura sobre este fondo (sin SERVICE, LOAD ni actualizaciones).",
                          403)
    try:
        preparada = prepareQuery(consulta)
    except Exception as exc:  # noqa: BLE001 — el analizador da muchos tipos de error
        raise ErrorSparql(f"La consulta no es SPARQL válido: {exc}") from exc
    if preparada.algebra.name not in _LECTURA:
        raise ErrorSparql("Solo se admiten SELECT, ASK, CONSTRUCT y DESCRIBE.", 403)


def consultar(db, fondo, consulta: str) -> tuple[bytes, str]:
    """La consulta se resuelve en el almacén de tripletas, sobre el grafo público guardado del fondo."""
    from app.servicios import grafo_rdf

    validar(consulta)
    futuro = _HILOS.submit(grafo_rdf.consultar, db, fondo, consulta, MAXIMO_FILAS)
    try:
        return futuro.result(timeout=SEGUNDOS)
    except Agotado as exc:
        raise ErrorSparql(f"La consulta tardó más de {SEGUNDOS} segundos.", 503) from exc
    except grafo_rdf.ErrorGrafo as exc:
        mensaje = str(exc)
        raise ErrorSparql(mensaje, 413 if "supera" in mensaje else 503) from exc
    except (SyntaxError, ValueError, OSError) as exc:
        raise ErrorSparql(f"La consulta no se pudo resolver: {exc}") from exc
