"""
Respaldo de la base de datos y simulacro de restauración (hallazgo PRE-10
de la auditoría RiC; OAIS Gestión de Datos y Almacenamiento; NDSA
Almacenamiento y Metadatos).

En la base viven la descripción RiC, los vocabularios, la auditoría y las
huellas de referencia contra las que se verifica la fijeza. Por eso:

1. Respaldo: dentro de una transacción REPEATABLE READ se exporta una
   instantánea (pg_export_snapshot), se cuentan las filas de las tablas
   clave y se calcula una huella de las huellas de fijeza; `pg_dump -Fc
   --snapshot` vuelca exactamente esa misma instantánea. El volcado lleva
   su SHA-256 en un archivo hermano «.sha256».
2. Simulacro: el volcado se restaura (pg_restore) en una base efímera del
   mismo servidor PostgreSQL, se cuentan de nuevo las filas, se recalcula
   la huella y se compara con lo esperado. La base efímera se elimina al
   terminar. Un respaldo cuyo simulacro falla genera una alerta alta.
3. Copia fuera del servidor: el administrador descarga el último respaldo
   probado a su equipo. Si pasan más días de los configurados sin hacerlo,
   hay alerta: un respaldo en el mismo disco no sobrevive a la pérdida del
   disco.

La contraseña nunca va en la línea de órdenes: se pasa por PGPASSWORD.
"""

import hashlib
import logging
import os
import subprocess
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.db.session import engine
from app.models.preservacion import RespaldoBaseDatos
from app.servicios import alertas, parametros
from app.servicios.auditoria import registrar

log = logging.getLogger("ricora.respaldo")

# Lo que debe sobrevivir a una restauración, tabla por tabla.
TABLAS_CLAVE = ("recursos_documentales", "instanciaciones", "entidades_vocabulario", "relaciones", "fechas",
                "registro_auditoria", "declaraciones_derechos", "verificaciones_integridad", "segundas_copias",
                "hallazgos_conformidad", "usuarios")
# Huella de las huellas: si una sola huella de referencia de la fijeza cambia, cambia esta.
HUELLA_FIJEZA = ("SELECT coalesce(md5(string_agg(id::text || ':' || coalesce(huella, ''), ',' ORDER BY id)), '') "
                 "FROM instanciaciones")
REINTENTO_TRAS_FALLO = timedelta(hours=1)


class ErrorRespaldo(RuntimeError):
    pass


def _entorno_pg(url) -> dict:
    entorno = dict(os.environ)
    if url.password:
        entorno["PGPASSWORD"] = url.password
    return entorno


def _argumentos_conexion(url, base: str | None = None) -> list[str]:
    args = ["--dbname", base or url.database]
    if url.host:
        args += ["--host", url.host]
    if url.port:
        args += ["--port", str(url.port)]
    if url.username:
        args += ["--username", url.username]
    return args


def _medir(con) -> dict:
    conteos = {t: con.execute(text(f'SELECT count(*) FROM "{t}"')).scalar() for t in TABLAS_CLAVE}
    return {"tablas": conteos, "huella_fijeza": con.execute(text(HUELLA_FIJEZA)).scalar()}


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def respaldar(db: Session, origen: str = "periodico", usuario_id: uuid.UUID | None = None,
              en_instantanea=None) -> RespaldoBaseDatos:
    """Vuelca la base y deja el registro. No lanza: un fallo queda como
    respaldo «fallido» con su error y su alerta."""
    url = make_url(settings.database_url)
    destino = settings.directorio_respaldo
    r = RespaldoBaseDatos(id=uuid.uuid4(), origen=origen, estado="en_curso", iniciado_en=ahora())
    db.add(r)
    db.flush()
    archivo = destino / f"ricora-{r.iniciado_en:%Y%m%dT%H%M%S}-{str(r.id)[:8]}.dump"
    try:
        destino.mkdir(parents=True, exist_ok=True)
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as con:
            with con.begin():
                instantanea = con.execute(text("SELECT pg_export_snapshot()")).scalar()
                medidas = _medir(con)
                # Lo que otro proceso necesite leer de esta misma instantánea
                # (el paquete de recuperación: sus archivos y el sello de la auditoría).
                extra = en_instantanea(con) if en_instantanea else None
                proceso = subprocess.run(
                    [settings.pg_dump, "--format=custom", "--no-owner", "--no-acl", f"--snapshot={instantanea}",
                     "--file", str(archivo), *_argumentos_conexion(url)],
                    env=_entorno_pg(url), capture_output=True, text=True, timeout=3600)
        if proceso.returncode != 0:
            raise ErrorRespaldo(proceso.stderr.strip()[-900:] or "pg_dump terminó con error.")
        r.archivo, r.tamano_bytes, r.huella = str(archivo), archivo.stat().st_size, _sha256(archivo)
        Path(f"{archivo}.sha256").write_text(f"{r.huella}  {archivo.name}\n", encoding="utf-8")
        r.conteos, r.estado = medidas, "correcto"
        r.extra_instantanea = extra
    except (OSError, subprocess.SubprocessError, ErrorRespaldo, Exception) as exc:  # noqa: BLE001
        r.estado, r.error = "fallido", str(exc)[:1000]
        _alertar_fallo(db, r, "El respaldo de la base de datos falló")
    r.terminado_en = ahora()
    registrar(db, modulo="preservacion", accion="respaldo_bd", usuario_id=usuario_id, entidad_tipo="respaldo_bd",
              entidad_id=r.id, detalle=f"Respaldo {origen} de la base de datos: {r.estado}",
              nuevo={"estado": r.estado, "archivo": Path(r.archivo).name if r.archivo else None,
                     "tamano_bytes": r.tamano_bytes, "huella": r.huella, "error": r.error})
    db.flush()
    return r


def simulacro(db: Session, r: RespaldoBaseDatos, usuario_id: uuid.UUID | None = None) -> RespaldoBaseDatos:
    """Restaura el volcado en una base efímera y compara. No lanza."""
    url = make_url(settings.database_url)
    efimera = f"ricora_simulacro_{uuid.uuid4().hex[:12]}"
    detalle: dict = {"base_efimera": efimera}
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        if r.estado != "correcto" or not r.archivo:
            raise ErrorRespaldo("No hay un volcado correcto que restaurar.")
        archivo = Path(r.archivo)
        if not archivo.exists():
            raise ErrorRespaldo("El archivo del volcado ya no está en el servidor.")
        huella = _sha256(archivo)
        detalle["huella_volcado"] = {"esperada": r.huella, "obtenida": huella}
        if huella != r.huella:
            raise ErrorRespaldo("El volcado cambió desde que se hizo (su SHA-256 no coincide).")
        with admin.connect() as con:
            con.execute(text(f'CREATE DATABASE "{efimera}"'))
        proceso = subprocess.run(
            [settings.pg_restore, "--no-owner", "--no-acl", "--exit-on-error", *_argumentos_conexion(url, efimera),
             str(archivo)], env=_entorno_pg(url), capture_output=True, text=True, timeout=3600)
        if proceso.returncode != 0:
            raise ErrorRespaldo(proceso.stderr.strip()[-900:] or "pg_restore terminó con error.")
        restaurada = create_engine(url.set(database=efimera))
        try:
            with restaurada.connect() as con:
                obtenido = _medir(con)
        finally:
            restaurada.dispose()
        esperado = r.conteos or {}
        diferencias = {t: {"esperado": esperado.get("tablas", {}).get(t), "obtenido": n}
                       for t, n in obtenido["tablas"].items() if esperado.get("tablas", {}).get(t) != n}
        if obtenido["huella_fijeza"] != esperado.get("huella_fijeza"):
            diferencias["huella_fijeza"] = {"esperado": esperado.get("huella_fijeza"),
                                           "obtenido": obtenido["huella_fijeza"]}
        detalle["tablas"] = obtenido["tablas"]
        detalle["diferencias"] = diferencias
        r.simulacro_estado = "fallido" if diferencias else "correcto"
        if diferencias:
            _alertar_fallo(db, r, "El simulacro de restauración no reprodujo la base")
    except (OSError, subprocess.SubprocessError, ErrorRespaldo, Exception) as exc:  # noqa: BLE001
        detalle["error"] = str(exc)[:900]
        r.simulacro_estado = "fallido"
        _alertar_fallo(db, r, "El simulacro de restauración falló")
    finally:
        try:
            with admin.connect() as con:
                con.execute(text(f'DROP DATABASE IF EXISTS "{efimera}" WITH (FORCE)'))
        except Exception:  # noqa: BLE001
            log.warning("No se pudo eliminar la base efímera %s", efimera)
        admin.dispose()
    r.simulacro_en, r.simulacro_detalle = ahora(), detalle
    if r.simulacro_estado == "correcto":
        for tipo in ("respaldo_fallido", "respaldo_atrasado"):
            pendiente = alertas.pendiente(db, tipo, "base_de_datos")
            if pendiente is not None:
                alertas.atender(db, pendiente, None, "Resuelta sola: hay un respaldo nuevo con simulacro correcto.")
    registrar(db, modulo="preservacion", accion="simulacro_restauracion", usuario_id=usuario_id,
              entidad_tipo="respaldo_bd", entidad_id=r.id,
              detalle=f"Simulacro de restauración del respaldo del {r.iniciado_en:%Y-%m-%d %H:%M}: {r.simulacro_estado}",
              nuevo={"estado": r.simulacro_estado, "diferencias": detalle.get("diferencias"),
                     "error": detalle.get("error")})
    db.flush()
    return r


def _alertar_fallo(db: Session, r: RespaldoBaseDatos, mensaje: str) -> None:
    alertas.crear(db, tipo="respaldo_fallido", severidad="alta", modulo="preservacion", entidad_tipo="respaldo_bd",
                  entidad_id="base_de_datos", mensaje=f"{mensaje}. Revise el registro del respaldo.",
                  detalle={"respaldo_id": str(r.id), "error": (r.error or "")[:300]})


def respaldar_y_probar(db: Session, origen: str = "periodico", usuario_id: uuid.UUID | None = None) -> RespaldoBaseDatos:
    r = respaldar(db, origen, usuario_id)
    if r.estado == "correcto":
        simulacro(db, r, usuario_id)
    depurar(db)
    return r


def ultimo_probado(db: Session) -> RespaldoBaseDatos | None:
    return db.scalars(select(RespaldoBaseDatos).where(RespaldoBaseDatos.simulacro_estado == "correcto")
                      .order_by(RespaldoBaseDatos.iniciado_en.desc()).limit(1)).first()


def periodico(db: Session) -> RespaldoBaseDatos | None:
    """La llama el trabajador en cada vuelta. Respalda si pasó la frecuencia
    desde el último respaldo probado (o una hora desde el último intento
    fallido) y revisa los atrasos. Devuelve el respaldo hecho, o None."""
    revisar_atrasos(db)
    db.commit()  # las alertas de atraso quedan aunque no toque respaldar
    horas = int(parametros.leer(db, "respaldo_frecuencia_horas"))
    probado = ultimo_probado(db)
    ultimo_intento = db.scalar(select(func.max(RespaldoBaseDatos.iniciado_en)))
    if probado is not None and ahora() - probado.iniciado_en < timedelta(hours=horas):
        return None
    if ultimo_intento is not None and ahora() - ultimo_intento < REINTENTO_TRAS_FALLO:
        return None
    r = respaldar_y_probar(db)
    db.commit()
    return r


def revisar_atrasos(db: Session) -> None:
    horas = int(parametros.leer(db, "respaldo_frecuencia_horas"))
    probado = ultimo_probado(db)
    if probado is not None and ahora() - probado.iniciado_en > timedelta(hours=2 * horas):
        alertas.crear(db, tipo="respaldo_atrasado", severidad="alta", modulo="preservacion",
                      entidad_tipo="respaldo_bd", entidad_id="base_de_datos",
                      mensaje=f"No hay un respaldo de la base con simulacro correcto desde el "
                              f"{probado.iniciado_en:%Y-%m-%d}. Revise que el trabajador esté en marcha.")
    dias = int(parametros.leer(db, "respaldo_dias_copia_externa"))
    ultima_descarga = db.scalar(select(func.max(RespaldoBaseDatos.descargado_en)))
    primero = db.scalar(select(func.min(RespaldoBaseDatos.iniciado_en)).where(
        RespaldoBaseDatos.simulacro_estado == "correcto"))
    referencia = ultima_descarga or primero
    if referencia is not None and ahora() - referencia > timedelta(days=dias):
        alertas.crear(db, tipo="respaldo_sin_copia_externa", severidad="media", modulo="preservacion",
                      entidad_tipo="respaldo_bd", entidad_id="base_de_datos",
                      mensaje=f"Hace más de {dias} días que nadie descarga el respaldo de la base a un equipo fuera "
                              "del servidor. Descárguelo desde Preservación › Respaldos.")


def registrar_descarga(db: Session, r: RespaldoBaseDatos, usuario_id: uuid.UUID, ip: str | None = None) -> None:
    r.descargado_en, r.descargado_por_id = ahora(), usuario_id
    pendiente = alertas.pendiente(db, "respaldo_sin_copia_externa", "base_de_datos")
    if pendiente is not None:
        alertas.atender(db, pendiente, usuario_id, "Se descargó el respaldo fuera del servidor.")
    registrar(db, modulo="preservacion", accion="respaldo_descargado", usuario_id=usuario_id,
              entidad_tipo="respaldo_bd", entidad_id=r.id, ip=ip,
              detalle=f"Respaldo del {r.iniciado_en:%Y-%m-%d %H:%M} descargado fuera del servidor",
              nuevo={"huella": r.huella})


def depurar(db: Session) -> int:
    """Retira del disco los volcados más allá de la retención. La fila del
    respaldo queda, con la fecha en que se retiró su archivo."""
    conservar = int(parametros.leer(db, "respaldo_retencion"))
    con_archivo = db.scalars(select(RespaldoBaseDatos).where(
        RespaldoBaseDatos.estado == "correcto", RespaldoBaseDatos.depurado_en.is_(None))
        .order_by(RespaldoBaseDatos.iniciado_en.desc())).all()
    n = 0
    for r in con_archivo[conservar:]:
        for ruta in (Path(r.archivo), Path(f"{r.archivo}.sha256")):
            ruta.unlink(missing_ok=True)
        r.depurado_en = ahora()
        n += 1
    return n


def out(r: RespaldoBaseDatos) -> dict:
    return {"id": str(r.id), "iniciado_en": r.iniciado_en, "terminado_en": r.terminado_en, "origen": r.origen,
            "estado": r.estado, "archivo": Path(r.archivo).name if r.archivo else None,
            "tamano_bytes": r.tamano_bytes, "huella": r.huella, "error": r.error,
            "tablas": (r.conteos or {}).get("tablas"), "simulacro_en": r.simulacro_en,
            "simulacro_estado": r.simulacro_estado,
            "simulacro_diferencias": (r.simulacro_detalle or {}).get("diferencias"),
            "simulacro_error": (r.simulacro_detalle or {}).get("error"),
            "descargado_en": r.descargado_en, "depurado_en": r.depurado_en,
            "destino": str(settings.directorio_respaldo)}
