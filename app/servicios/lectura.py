"""
La consulta lee del grafo RiC-O (arquitectura híbrida, paso A).

El catálogo, la ficha de consulta, el resumen, el índice, el inventario FUID,
la guía y el buscador no leen las tablas de trabajo: leen una **proyección
rehecha desde el grafo guardado** en el almacén de tripletas (el grafo
completo más el de control, `grafo_control.filas_desde_grafo`). La proyección
vive en el esquema `lectura` de PostgreSQL, con las mismas tablas de la
descripción, y se rehace cuando el grafo del fondo cambia.

Así, lo que ve un lector sale del grafo: si las tablas de trabajo y el grafo
difieren (alguien cambió una tabla por fuera del sistema), la consulta muestra
lo que dice el grafo, que es la fuente de verdad.

Por qué una proyección y no consultas SPARQL en cada pantalla: el código de
consulta (reserva de la Ley 1712, fechas heredadas, retención, conteos) ya
existe y está probado sobre tablas; reescribirlo en SPARQL duplicaría las
reglas y su riesgo. La proyección mantiene una sola implementación de las
reglas y cambia de dónde vienen los datos.

Uso:

    lectura.preparar(db, fondo)       # rehace la proyección si el grafo cambió
    with lectura.sesion(db) as ldb:   # misma conexión, esquema «lectura» primero
        ...                           # las consultas leen la proyección

Las tablas que no son descripción (usuarios, alertas, auditoría, TRD en
trabajo, preservación) no están en la proyección: el esquema público responde
por ellas.
"""

import logging
import time
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.recurso_documental import RecursoDocumental
from app.servicios import grafo_control

log = logging.getLogger("ricora.lectura")

ESQUEMA = "lectura"
# Las dos tablas con índice de texto completo (migración 0035): la proyección
# lo recalcula con las mismas funciones.
DISPARADORES = {
    "recursos_documentales": ("recursos_indexar", "public.ricora_indexar_recurso()",
                              "INSERT OR UPDATE"),
    "instanciaciones": ("instanciaciones_indexar", "public.ricora_indexar_instanciacion()", "INSERT OR UPDATE"),
}


def _tablas() -> list[str]:
    return [m.__tablename__ for m in grafo_control.TABLAS]


def _columnas(conexion) -> dict[tuple[str, str], list[str]]:
    """(esquema, tabla) → columnas en orden, de las tablas de la descripción, en una consulta."""
    salida: dict[tuple[str, str], list[str]] = {}
    for esquema, tabla, columna in conexion.execute(text(
            "SELECT table_schema, table_name, column_name FROM information_schema.columns "
            "WHERE table_schema IN ('public', :e) AND table_name = ANY(:t) ORDER BY ordinal_position"),
            {"e": ESQUEMA, "t": _tablas()}):
        salida.setdefault((esquema, tabla), []).append(columna)
    return salida


def asegurar_esquema(conexion) -> bool:
    """Crea el esquema y sus tablas, o rehace la tabla cuyas columnas ya no son las
    de la tabla pública (una migración posterior la cambió). Devuelve si rehízo algo:
    entonces toda la proyección se marca para rehacer."""
    conexion.execute(text(f"CREATE SCHEMA IF NOT EXISTS {ESQUEMA}"))
    conexion.execute(text(f"""CREATE TABLE IF NOT EXISTS {ESQUEMA}.estado (
        fondo_id uuid PRIMARY KEY, version integer NOT NULL, actualizada_en timestamptz NOT NULL DEFAULT now(),
        segundos double precision)"""))
    rehizo = False
    columnas = _columnas(conexion)
    for tabla in _tablas():
        if columnas.get((ESQUEMA, tabla)) == columnas.get(("public", tabla)):
            continue
        conexion.execute(text(f"DROP TABLE IF EXISTS {ESQUEMA}.{tabla}"))
        # Mismas columnas, valores por defecto e índices (también los de texto completo);
        # sin claves foráneas ni disparadores de la tabla de trabajo.
        conexion.execute(text(f"CREATE TABLE {ESQUEMA}.{tabla} "
                              f"(LIKE public.{tabla} INCLUDING DEFAULTS INCLUDING INDEXES INCLUDING GENERATED)"))
        if tabla in DISPARADORES:
            nombre, funcion, eventos = DISPARADORES[tabla]
            conexion.execute(text(f"CREATE TRIGGER {nombre} BEFORE {eventos} ON {ESQUEMA}.{tabla} "
                                  f"FOR EACH ROW EXECUTE FUNCTION {funcion}"))
        rehizo = True
    if rehizo:
        conexion.execute(text(f"DELETE FROM {ESQUEMA}.estado"))
    return rehizo


@contextmanager
def _ruta(conexion):
    """El esquema de la proyección primero, mientras dura el bloque."""
    previa = conexion.execute(text("SHOW search_path")).scalar()
    conexion.execute(text("SELECT set_config('search_path', :r, true)"), {"r": f"{ESQUEMA}, {previa}"})
    try:
        yield
    finally:
        conexion.execute(text("SELECT set_config('search_path', :r, true)"), {"r": previa})


@contextmanager
def sesion(db: Session):
    """Una sesión de solo lectura sobre la proyección, en la misma conexión y
    transacción de `db` (con su propio mapa de identidad: los objetos de la
    proyección no se mezclan con los de las tablas de trabajo)."""
    conexion = db.connection()
    with _ruta(conexion):
        lectora = Session(bind=conexion, join_transaction_mode="create_savepoint", autoflush=False,
                          expire_on_commit=False)
        lectora.info["desde_grafo"] = True  # nada de lo que haga marca el grafo como cambiado
        try:
            yield lectora
        finally:
            lectora.close()


def _version(db: Session, fondo: RecursoDocumental) -> int:
    from app.servicios import grafo_rdf

    return grafo_rdf.al_dia(db, fondo, "completo").version_sincronizada


def preparar(db: Session, fondo: RecursoDocumental) -> dict:
    """Deja la proyección del fondo igual al grafo guardado. Si el grafo no cambió
    desde la última vez, no hace nada. Confirma la transacción de `db`."""
    from app.servicios import exportacion_rico, grafo_rdf

    conexion = db.connection()
    asegurar_esquema(conexion)
    version = _version(db, fondo)
    conexion.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"lectura:{fondo.id}"})
    actual = conexion.execute(text(f"SELECT version FROM {ESQUEMA}.estado WHERE fondo_id = :f"),
                              {"f": fondo.id}).scalar()
    if actual == version:
        db.commit()
        return {"rehecha": False, "version": version}
    inicio = time.monotonic()
    completo, control = grafo_rdf._desde_almacen(fondo.id)
    filas = grafo_control.filas_desde_grafo(completo, control, exportacion_rico.base())
    with sesion(db) as ldb:
        # Lo que la proyección tenía del fondo y el grafo ya no dice, se quita;
        # lo demás se inserta o actualiza tal como lo dice el grafo.
        antes = grafo_control.foto(ldb, fondo.id)
        for modelo in reversed(grafo_control.TABLAS):
            tabla = modelo.__tablename__
            sobran = set(antes.get(tabla, {})) - set(filas.get(tabla, {}))
            if sobran:
                ldb.execute(modelo.__table__.delete().where(modelo.__table__.c.id.in_(list(sobran))))
        grafo_control.cargar(ldb, filas)
        ldb.commit()  # suelta su punto de guardado dentro de la transacción de `db`
    segundos = round(time.monotonic() - inicio, 3)
    conexion.execute(text(f"""INSERT INTO {ESQUEMA}.estado (fondo_id, version, actualizada_en, segundos)
        VALUES (:f, :v, now(), :s) ON CONFLICT (fondo_id) DO UPDATE
        SET version = EXCLUDED.version, actualizada_en = now(), segundos = EXCLUDED.segundos"""),
                     {"f": fondo.id, "v": version, "s": segundos})
    db.commit()
    log.info("Proyección de lectura del fondo %s rehecha desde el grafo en %.3f s", fondo.id, segundos)
    return {"rehecha": True, "version": version, "segundos": segundos,
            "filas": {t: len(v) for t, v in filas.items()}}


@contextmanager
def desde_el_grafo(db: Session, fondo: RecursoDocumental):
    """Atajo para las rutas de consulta: prepara la proyección y abre la sesión.

    Si el almacén de tripletas no responde, la consulta no se cae: lee las tablas
    de trabajo y lo deja en el registro del servidor (la salud del sistema ya
    avisa que el almacén falla)."""
    from app.servicios import grafo_rdf

    try:
        preparar(db, fondo)
    except grafo_rdf.ErrorGrafo as exc:
        db.rollback()
        log.warning("Consulta del fondo %s desde las tablas: el grafo no está disponible (%s)", fondo.id, exc)
        yield db
        return
    with sesion(db) as ldb:
        yield ldb


@contextmanager
def de_los_fondos(db: Session, fondos: list[RecursoDocumental]):
    """Como `desde_el_grafo`, para una consulta que recorre varios fondos (el buscador)."""
    from app.servicios import grafo_rdf

    try:
        for fondo in fondos:
            preparar(db, fondo)
    except grafo_rdf.ErrorGrafo as exc:
        db.rollback()
        log.warning("Búsqueda desde las tablas: el grafo no está disponible (%s)", exc)
        yield db
        return
    with sesion(db) as ldb:
        yield ldb


def en(ldb: Session, objeto):
    """El mismo registro, leído de la proyección (o el de trabajo si la consulta cayó a las tablas)."""
    if objeto is None:
        return None
    return ldb.get(type(objeto), objeto.id) or objeto
