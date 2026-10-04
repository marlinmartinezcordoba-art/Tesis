"""
Recuperación ante desastres (brechas NFR-04, NFR-07 y RF-OPS-001 de la
matriz maestra v3.0).

El respaldo de la base (PRE-10) no basta para levantar el sistema en otro
servidor: faltan los archivos del almacén, que son los documentos mismos.
El **paquete de recuperación** es un solo archivo .tar con todo lo necesario:

    base/ricora.dump            volcado probado de la base (pg_dump -Fc)
    base/ricora.dump.sha256
    archivos/<ruta del almacén> cada documento digital, tal como está guardado
    manifiesto.json             fecha, migración, conteos, sello de la
                                auditoría y la huella SHA-256 de cada archivo
    LEEME.txt                   cómo restaurarlo

El **simulacro integral** lo restaura entero en una base de datos y una
carpeta nuevas (como si fuera otro servidor), verifica que cada archivo
tenga la huella que dice la base, que las tablas tengan las filas
esperadas y que la cadena de la auditoría siga íntegra, y mide cuánto
tarda: ese es el tiempo de recuperación (RTO) real, no uno supuesto.

Las contraseñas y claves no van en el paquete: se restauran desde el
gestor de secretos del despliegue (el .env o los secretos de GitHub).
"""

import json
import logging
import shutil
import subprocess
import tarfile
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.preservacion import PaqueteRecuperacion, RespaldoBaseDatos
from app.servicios import alertas, parametros, respaldo
from app.servicios.auditoria import registrar

log = logging.getLogger("ricora.recuperacion")

# Variables que el servidor nuevo necesita (solo los nombres; los valores
# están en el gestor de secretos, nunca en el paquete).
VARIABLES_REQUERIDAS = ("DATABASE_URL", "RICORA_SECRET_KEY", "RICORA_URL_PUBLICA", "DIRECTORIO_ALMACENAMIENTO",
                        "RICORA_RESPALDO", "RICORA_SEGUNDA_COPIA", "RICORA_ADMIN_CORREO", "RICORA_ADMIN_PASSWORD")

LEEME = """RICORA · Paquete de recuperación ante desastres
=================================================

Contiene la base de datos, todos los documentos digitales del almacén y un
manifiesto con la huella SHA-256 de cada archivo. No contiene contraseñas
ni claves: tómelas del gestor de secretos del despliegue.

Restaurar en un servidor nuevo
------------------------------
1. Instale RICORA (docker compose) con las mismas variables de entorno:
   {variables}.
2. Cree una base de datos vacía y deje vacía la carpeta del almacén.
3. Copie este archivo al servidor y ejecute:
       docker compose run --rm web python -m app.cli restaurar-paquete /ruta/al/paquete.tar
   La orden restaura la base, copia los archivos al almacén y verifica que
   cada uno tenga su huella, que las tablas tengan sus filas y que la cadena
   de la auditoría esté íntegra. Si algo no coincide, lo dice y se detiene.
4. Levante el servicio (docker compose up -d) y consulte /api/salud.

Generado: {fecha} · migración {migracion} · {archivos} archivos ({megas} MB).
"""


class ErrorRecuperacion(RuntimeError):
    pass


def _lo_de_la_instantanea(con) -> tuple[list, dict, str]:
    """Cada archivo digital del almacén (no los originales en papel), el
    último eslabón de la auditoría y la migración, en la instantánea del volcado."""
    filas = con.execute(text("SELECT id, ruta, huella, algoritmo_huella, nombre_original FROM instanciaciones "
                             "WHERE ruta IS NOT NULL ORDER BY cargado_en, id")).all()
    version = con.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return [tuple(f) for f in filas], _sello(con), version


def _sello(con) -> dict:
    fila = con.execute(text("SELECT orden, huella FROM registro_auditoria WHERE orden IS NOT NULL "
                            "ORDER BY orden DESC LIMIT 1")).first()
    return {"orden": fila[0], "huella": fila[1]} if fila else {"orden": None, "huella": None}


def generar(db: Session, origen: str = "periodico", usuario_id: uuid.UUID | None = None) -> PaqueteRecuperacion:
    """Arma el paquete con el último respaldo probado (o hace uno si no hay
    uno reciente). No lanza: un fallo queda como paquete «fallido» con su alerta."""
    p = PaqueteRecuperacion(id=uuid.uuid4(), origen=origen, estado="en_curso", creado_en=ahora(), creado_por_id=usuario_id)
    db.add(p)
    db.flush()
    destino = Path(settings.directorio_respaldo) / f"recuperacion-{p.creado_en:%Y%m%dT%H%M%S}-{str(p.id)[:8]}.tar"
    try:
        # Un volcado propio: la lista de archivos, el sello de la auditoría y
        # la migración se leen en la misma instantánea que se vuelca, así lo
        # restaurado y los archivos empaquetados coinciden exactamente.
        base = respaldo.respaldar(db, "recuperacion", usuario_id, en_instantanea=_lo_de_la_instantanea)
        if base.estado != "correcto":
            raise ErrorRecuperacion(f"El volcado de la base falló: {base.error}")
        p.respaldo_id = base.id
        filas, sello, version = base.extra_instantanea
        raiz = Path(settings.directorio_almacenamiento)
        archivos, ausentes, total = [], [], 0
        for instancia_id, ruta_rel, huella, algoritmo, nombre in filas:
            ruta = raiz / ruta_rel
            if not ruta.is_file():
                # Un archivo perdido no deja al archivo sin paquete de
                # recuperación: se empaca lo que hay, el faltante queda en el
                # manifiesto y se avisa (se repone desde la segunda copia).
                ausentes.append({"instanciacion": str(instancia_id), "ruta": ruta_rel, "nombre": nombre})
                continue
            tamano = ruta.stat().st_size
            archivos.append({"instanciacion": str(instancia_id), "ruta": ruta_rel, "huella": huella,
                             "algoritmo": algoritmo, "bytes": tamano})
            total += tamano
        manifiesto = {
            "formato": "ricora-recuperacion/1", "generado_en": p.creado_en.isoformat(), "migracion": version,
            "respaldo": {"id": str(base.id), "fecha": base.iniciado_en.isoformat(), "huella": base.huella,
                         "conteos": base.conteos},
            "auditoria": sello, "archivos": archivos, "ausentes": ausentes,
            "parametros": {k: parametros.leer(db, k) for k in parametros.DEFINICIONES},
            "variables_requeridas": list(VARIABLES_REQUERIDAS),
        }
        destino.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(destino, "w") as tar:
            tar.add(base.archivo, arcname="base/ricora.dump")
            _agregar_texto(tar, "base/ricora.dump.sha256", f"{base.huella}  ricora.dump\n")
            for a in archivos:
                tar.add(raiz / a["ruta"], arcname=f"archivos/{a['ruta']}")
            _agregar_texto(tar, "manifiesto.json", json.dumps(manifiesto, ensure_ascii=False, indent=2, default=str))
            _agregar_texto(tar, "LEEME.txt", LEEME.format(
                variables=", ".join(VARIABLES_REQUERIDAS), fecha=p.creado_en.isoformat(), migracion=version,
                archivos=len(archivos), megas=round(total / 1_000_000, 1)))
        p.archivo, p.tamano_bytes, p.huella = str(destino), destino.stat().st_size, respaldo._sha256(destino)
        p.archivos, p.bytes_archivos, p.estado = len(archivos), total, "correcto"
        p.simulacro_detalle = {"ausentes": ausentes}
        if ausentes:
            alertas.crear(db, tipo="recuperacion_fallida", severidad="alta", modulo="preservacion",
                          entidad_tipo="paquete_recuperacion", entidad_id="recuperacion",
                          mensaje=f"{len(ausentes)} archivo(s) del almacén no están en el disco y no entraron al paquete "
                                  "de recuperación. Repóngalos desde la segunda copia (Preservación).",
                          detalle={"paquete_id": str(p.id), "ausentes": [a["nombre"] for a in ausentes][:20]})
    except Exception as exc:  # noqa: BLE001
        destino.unlink(missing_ok=True)
        p.estado, p.error = "fallido", str(exc)[:1000]
        alertas.crear(db, tipo="recuperacion_fallida", severidad="alta", modulo="preservacion",
                      entidad_tipo="paquete_recuperacion", entidad_id="recuperacion",
                      mensaje="No se pudo generar el paquete de recuperación. Revise Preservación › Recuperación.",
                      detalle={"paquete_id": str(p.id), "error": p.error[:300]})
    p.terminado_en = ahora()
    registrar(db, modulo="preservacion", accion="paquete_recuperacion", usuario_id=usuario_id,
              entidad_tipo="paquete_recuperacion", entidad_id=p.id, detalle=f"Paquete de recuperación {origen}: {p.estado}",
              nuevo={"estado": p.estado, "archivos": p.archivos, "tamano_bytes": p.tamano_bytes, "huella": p.huella,
                     "error": p.error})
    db.flush()
    return p


def _agregar_texto(tar: tarfile.TarFile, nombre: str, contenido: str) -> None:
    datos = contenido.encode("utf-8")
    info = tarfile.TarInfo(nombre)
    info.size, info.mtime = len(datos), int(time.time())
    import io

    tar.addfile(info, io.BytesIO(datos))


def _extraer_seguro(tar: tarfile.TarFile, destino: Path) -> None:
    """Solo archivos regulares dentro del destino (un paquete alterado no
    puede escribir fuera de la carpeta ni crear enlaces)."""
    destino = destino.resolve()
    for m in tar.getmembers():
        if not m.isfile():
            continue
        final = (destino / m.name).resolve()
        if destino not in final.parents:
            raise ErrorRecuperacion(f"El paquete trae una ruta no permitida: {m.name}")
        final.parent.mkdir(parents=True, exist_ok=True)
        with tar.extractfile(m) as origen, final.open("wb") as salida:
            shutil.copyfileobj(origen, salida)


def restaurar(paquete: Path, url_destino: str, almacen_destino: Path) -> dict:
    """Restaura el paquete en una base vacía y una carpeta vacía y lo
    verifica todo. Devuelve el informe con el tiempo de cada paso. Lanza
    ErrorRecuperacion si algo no coincide (la restauración no sirve)."""
    inicio = time.monotonic()
    pasos: dict[str, float] = {}
    url = make_url(url_destino)
    almacen_destino = Path(almacen_destino)
    if almacen_destino.exists() and any(almacen_destino.iterdir()):
        raise ErrorRecuperacion("La carpeta del almacén de destino no está vacía.")
    motor = create_engine(url)
    try:
        with motor.connect() as con:
            tablas = con.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")).scalar()
        if tablas:
            raise ErrorRecuperacion("La base de datos de destino no está vacía: la restauración solo se hace en una base nueva.")
        with tempfile.TemporaryDirectory(prefix="ricora-recuperacion-") as tmp:
            trabajo = Path(tmp)
            with tarfile.open(paquete, "r") as tar:
                _extraer_seguro(tar, trabajo)
            manifiesto = json.loads((trabajo / "manifiesto.json").read_text(encoding="utf-8"))
            volcado = trabajo / "base" / "ricora.dump"
            if respaldo._sha256(volcado) != manifiesto["respaldo"]["huella"]:
                raise ErrorRecuperacion("El volcado de la base no tiene la huella del manifiesto.")
            pasos["abrir_paquete"] = round(time.monotonic() - inicio, 2)
            t = time.monotonic()
            proceso = subprocess.run(
                [settings.pg_restore, "--no-owner", "--no-acl", "--exit-on-error",
                 *respaldo._argumentos_conexion(url, url.database), str(volcado)],
                env=respaldo._entorno_pg(url), capture_output=True, text=True, timeout=7200)
            if proceso.returncode != 0:
                raise ErrorRecuperacion(proceso.stderr.strip()[-900:] or "pg_restore terminó con error.")
            pasos["restaurar_base"] = round(time.monotonic() - t, 2)
            t = time.monotonic()
            almacen_destino.mkdir(parents=True, exist_ok=True)
            fuente = trabajo / "archivos"
            for a in manifiesto["archivos"]:
                final = almacen_destino / a["ruta"]
                final.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(fuente / a["ruta"]), final)
            pasos["copiar_archivos"] = round(time.monotonic() - t, 2)
        t = time.monotonic()
        informe = verificar(motor, almacen_destino, manifiesto)
        pasos["verificar"] = round(time.monotonic() - t, 2)
    finally:
        motor.dispose()
    informe |= {"pasos_segundos": pasos, "segundos": round(time.monotonic() - inicio, 2),
                "migracion": manifiesto["migracion"], "generado_en": manifiesto["generado_en"]}
    if informe["problemas"]:
        raise ErrorRecuperacion("La restauración no reprodujo el sistema: " + "; ".join(informe["problemas"][:5]))
    return informe


def verificar(motor, almacen: Path, manifiesto: dict) -> dict:
    """Lo restaurado frente a lo esperado: filas de las tablas clave, huella
    de cada archivo contra la base restaurada y cadena de la auditoría."""
    problemas: list[str] = []
    with motor.connect() as con:
        medidas = respaldo._medir(con)
        esperado = manifiesto["respaldo"]["conteos"] or {}
        for tabla, n in medidas["tablas"].items():
            if esperado.get("tablas", {}).get(tabla) != n:
                problemas.append(f"la tabla {tabla} tiene {n} filas y debía tener {esperado.get('tablas', {}).get(tabla)}")
        if medidas["huella_fijeza"] != esperado.get("huella_fijeza"):
            problemas.append("las huellas de referencia de los archivos cambiaron")
        huellas = dict(con.execute(text("SELECT ruta, huella FROM instanciaciones WHERE ruta IS NOT NULL")).all())
        roto = con.execute(text("""
            WITH c AS (SELECT r.orden, r.huella, r.huella_anterior,
                              lag(r.huella) OVER (ORDER BY r.orden) AS previa,
                              auditoria_huella(r, lag(r.huella) OVER (ORDER BY r.orden)) AS calculada
                       FROM registro_auditoria r WHERE r.orden IS NOT NULL)
            SELECT min(orden) FROM c WHERE huella IS DISTINCT FROM calculada OR huella_anterior IS DISTINCT FROM previa
        """)).scalar()
        if roto is not None:
            problemas.append(f"la cadena de la auditoría se rompe en el evento {roto}")
        sello = _sello(con)
    if manifiesto["auditoria"]["huella"] and sello["huella"] != manifiesto["auditoria"]["huella"]:
        problemas.append("el sello de la auditoría no coincide con el del manifiesto")
    verificados = 0
    for a in manifiesto["archivos"]:
        ruta = almacen / a["ruta"]
        if not ruta.is_file():
            problemas.append(f"falta el archivo {a['ruta']}")
            continue
        obtenida = respaldo._sha256(ruta)
        if a["huella"] and obtenida != a["huella"]:
            problemas.append(f"el archivo {a['ruta']} no tiene la huella esperada")
        elif huellas.get(a["ruta"]) != obtenida and a["huella"]:
            problemas.append(f"la base restaurada no reconoce la huella de {a['ruta']}")
        else:
            verificados += 1
    return {"tablas": medidas["tablas"], "archivos_verificados": verificados, "archivos": len(manifiesto["archivos"]),
            "auditoria": sello, "problemas": problemas}


def simulacro(db: Session, p: PaqueteRecuperacion, usuario_id: uuid.UUID | None = None) -> PaqueteRecuperacion:
    """Restaura el paquete en una base efímera y una carpeta temporal del
    mismo servidor, como si fuera otro, y lo borra todo al terminar. No lanza."""
    url = make_url(settings.database_url)
    efimera = f"ricora_simulacro_{uuid.uuid4().hex[:12]}"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    detalle: dict = dict(p.simulacro_detalle or {}) | {"base_efimera": efimera}
    carpeta = Path(tempfile.mkdtemp(prefix="ricora-simulacro-almacen-"))
    try:
        if p.estado != "correcto" or not p.archivo or not Path(p.archivo).exists():
            raise ErrorRecuperacion("No hay un paquete correcto que restaurar.")
        if respaldo._sha256(Path(p.archivo)) != p.huella:
            raise ErrorRecuperacion("El paquete cambió desde que se hizo (su SHA-256 no coincide).")
        with admin.connect() as con:
            con.execute(text(f'CREATE DATABASE "{efimera}"'))
        informe = restaurar(Path(p.archivo), url.set(database=efimera).render_as_string(hide_password=False),
                            carpeta / "almacen")
        detalle |= informe
        p.simulacro_estado, p.simulacro_segundos = "correcto", int(round(informe["segundos"]))
        pendiente = alertas.pendiente(db, "recuperacion_fallida", "recuperacion")
        if pendiente is not None and not detalle.get("ausentes"):
            alertas.atender(db, pendiente, None, "Resuelta sola: el último paquete se restauró completo.")
    except Exception as exc:  # noqa: BLE001
        detalle["error"] = str(exc)[:900]
        p.simulacro_estado = "fallido"
        alertas.crear(db, tipo="recuperacion_fallida", severidad="alta", modulo="preservacion",
                      entidad_tipo="paquete_recuperacion", entidad_id="recuperacion",
                      mensaje="El simulacro de recuperación completa falló. Revise Preservación › Recuperación.",
                      detalle={"paquete_id": str(p.id), "error": detalle["error"][:300]})
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
        try:
            with admin.connect() as con:
                con.execute(text(f'DROP DATABASE IF EXISTS "{efimera}" WITH (FORCE)'))
        except Exception:  # noqa: BLE001
            log.warning("No se pudo eliminar la base efímera %s", efimera)
        admin.dispose()
    p.simulacro_en, p.simulacro_detalle = ahora(), detalle
    registrar(db, modulo="preservacion", accion="simulacro_recuperacion", usuario_id=usuario_id,
              entidad_tipo="paquete_recuperacion", entidad_id=p.id,
              detalle=f"Simulacro de recuperación completa: {p.simulacro_estado}"
                      + (f" en {p.simulacro_segundos} s" if p.simulacro_segundos is not None else ""),
              nuevo={"estado": p.simulacro_estado, "segundos": p.simulacro_segundos,
                     "archivos_verificados": detalle.get("archivos_verificados"), "error": detalle.get("error")})
    db.flush()
    return p


def generar_y_probar(db: Session, origen: str = "periodico", usuario_id: uuid.UUID | None = None) -> PaqueteRecuperacion:
    p = generar(db, origen, usuario_id)
    if p.estado == "correcto":
        simulacro(db, p, usuario_id)
    depurar(db)
    return p


def ultimo_probado(db: Session) -> PaqueteRecuperacion | None:
    return db.scalars(select(PaqueteRecuperacion).where(PaqueteRecuperacion.simulacro_estado == "correcto")
                      .order_by(PaqueteRecuperacion.creado_en.desc()).limit(1)).first()


def periodico(db: Session) -> PaqueteRecuperacion | None:
    """La llama el trabajador. Cada `recuperacion_frecuencia_dias` (0 = solo a mano)."""
    dias = int(parametros.leer(db, "recuperacion_frecuencia_dias"))
    if dias == 0:
        return None
    ultimo = db.scalar(select(func.max(PaqueteRecuperacion.creado_en)))
    if ultimo is not None and ahora() - ultimo < timedelta(days=dias):
        return None
    p = generar_y_probar(db)
    db.commit()
    return p


def registrar_descarga(db: Session, p: PaqueteRecuperacion, usuario_id: uuid.UUID, ip: str | None = None) -> None:
    p.descargado_en, p.descargado_por_id = ahora(), usuario_id
    # El paquete lleva el volcado de la base: también cuenta como copia externa del respaldo.
    base = db.get(RespaldoBaseDatos, p.respaldo_id) if p.respaldo_id else None
    if base is not None:
        respaldo.registrar_descarga(db, base, usuario_id, ip)
    registrar(db, modulo="preservacion", accion="paquete_recuperacion_descargado", usuario_id=usuario_id,
              entidad_tipo="paquete_recuperacion", entidad_id=p.id, ip=ip,
              detalle=f"Paquete de recuperación del {p.creado_en:%Y-%m-%d %H:%M} descargado fuera del servidor",
              nuevo={"huella": p.huella})


def depurar(db: Session) -> int:
    """Solo se conservan los dos últimos paquetes en el servidor (cada uno
    ocupa tanto como el almacén entero). Las filas quedan."""
    vivos = db.scalars(select(PaqueteRecuperacion).where(PaqueteRecuperacion.estado == "correcto",
                                                         PaqueteRecuperacion.depurado_en.is_(None))
                       .order_by(PaqueteRecuperacion.creado_en.desc())).all()
    n = 0
    for p in vivos[2:]:
        Path(p.archivo).unlink(missing_ok=True)
        p.depurado_en = ahora()
        n += 1
    return n


# --- Objetivos de recuperación por escenario (NFR-04) -------------------------------------------

ESCENARIOS = (
    {"clave": "archivo_danado", "escenario": "Un archivo se daña o se borra en el almacén",
     "mecanismo": "Verificación periódica de fijeza y reposición desde la segunda copia",
     "rpo": "0 (la segunda copia se hace al ingresar)", "rto": "Minutos (reposición desde Preservación)"},
    {"clave": "error_humano", "escenario": "Una persona corrige mal una descripción",
     "mecanismo": "Nada se borra: lo quitado queda anulado y la auditoría guarda el valor anterior",
     "rpo": "0", "rto": "Minutos (se reabre y se corrige)"},
    {"clave": "base_corrupta", "escenario": "La base de datos se corrompe",
     "mecanismo": "Respaldo periódico con simulacro de restauración", "rpo": "frecuencia del respaldo",
     "rto": "tiempo medido del simulacro"},
    {"clave": "perdida_servidor", "escenario": "Se pierde el disco o el servidor completo",
     "mecanismo": "Paquete de recuperación descargado fuera del servidor y restaurado en uno nuevo",
     "rpo": "días desde la última descarga del paquete", "rto": "tiempo medido del simulacro integral + aprovisionar"},
    {"clave": "secuestro", "escenario": "Secuestro de datos (ransomware) o cuenta comprometida",
     "mecanismo": "Copia descargada fuera de línea, segundo factor y cadena de la auditoría",
     "rpo": "días desde la última descarga del paquete", "rto": "igual que la pérdida del servidor"},
)

APROVISIONAR_HORAS = 2  # instalar Docker y RICORA en un servidor nuevo, estimado y documentado


def estado(db: Session) -> dict:
    """Objetivos (parámetros) frente a lo que hay hoy, escenario por escenario."""
    rpo_obj = int(parametros.leer(db, "rpo_horas"))
    rto_obj = int(parametros.leer(db, "rto_horas"))
    ahora_ = ahora()
    base = respaldo.ultimo_probado(db)
    paquete = ultimo_probado(db)
    descarga = db.scalar(select(func.max(PaqueteRecuperacion.descargado_en)))
    horas = lambda f: round((ahora_ - f).total_seconds() / 3600, 1) if f else None  # noqa: E731
    # La base queda probada por su simulacro propio o por el simulacro integral del paquete.
    fechas_base = [f for f in (base.iniciado_en if base else None, paquete.creado_en if paquete else None) if f]
    rpo_base = horas(max(fechas_base)) if fechas_base else None
    rpo_fuera = horas(descarga)
    rto_base = round((base.simulacro_detalle or {}).get("segundos", 0) / 3600, 2) if base and base.simulacro_detalle \
        and "segundos" in base.simulacro_detalle else None
    # Al menos un minuto: un simulacro de segundos no significa que volver no cueste nada.
    rto_restaurar = round(max(paquete.simulacro_segundos, 60) / 3600, 2) if paquete and \
        paquete.simulacro_segundos is not None else None
    rto_integral = round(rto_restaurar + APROVISIONAR_HORAS, 2) if rto_restaurar is not None else None
    medidos = {
        "archivo_danado": (0, 0.25), "error_humano": (0, 0.25),
        "base_corrupta": (rpo_base, rto_restaurar if rto_restaurar is not None else rto_base),
        "perdida_servidor": (rpo_fuera, rto_integral), "secuestro": (rpo_fuera, rto_integral),
    }
    filas = []
    for e in ESCENARIOS:
        rpo, rto = medidos[e["clave"]]
        cumple = rpo is not None and rto is not None and rpo <= rpo_obj and rto <= rto_obj
        filas.append(e | {"rpo_actual_horas": rpo, "rto_medido_horas": rto, "cumple": cumple})
    return {"objetivos": {"rpo_horas": rpo_obj, "rto_horas": rto_obj, "aprovisionar_horas": APROVISIONAR_HORAS},
            "escenarios": filas, "ultimo_paquete": out(paquete) if paquete else None,
            "paquetes": [out(p) for p in db.scalars(select(PaqueteRecuperacion)
                                                    .order_by(PaqueteRecuperacion.creado_en.desc()).limit(5)).all()],
            "frecuencia_dias": int(parametros.leer(db, "recuperacion_frecuencia_dias"))}


def out(p: PaqueteRecuperacion) -> dict:
    d = p.simulacro_detalle or {}
    return {"id": str(p.id), "creado_en": p.creado_en, "origen": p.origen, "estado": p.estado,
            "tamano_bytes": p.tamano_bytes, "huella": p.huella, "archivos": p.archivos, "bytes_archivos": p.bytes_archivos,
            "error": p.error, "simulacro_en": p.simulacro_en, "simulacro_estado": p.simulacro_estado,
            "simulacro_segundos": p.simulacro_segundos, "simulacro_pasos": d.get("pasos_segundos"),
            "archivos_verificados": d.get("archivos_verificados"), "simulacro_error": d.get("error"),
            "ausentes": [a["nombre"] for a in d.get("ausentes", [])],
            "descargado_en": p.descargado_en, "depurado_en": p.depurado_en}
