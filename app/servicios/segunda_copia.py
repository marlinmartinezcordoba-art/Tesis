"""
Segunda copia de cada instanciación (OAIS: Almacenamiento de Archivo;
PREMIS: evento «replication»).

La copia se escribe primero con un nombre temporal en el lugar
configurado, se le calcula la huella y solo si coincide con la registrada
en la ingesta se le da su nombre definitivo. Nunca se borra una copia: si
se rehace o si el administrador cambia el lugar, la anterior queda
«reemplazada» con su archivo intacto.
"""

import hashlib
import logging
import os
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.instanciacion import Instanciacion
from app.models.preservacion import SegundaCopia
from app.servicios import almacen, parametros
from app.servicios.auditoria import registrar

log = logging.getLogger("ricora.segunda_copia")


class ErrorSegundaCopia(Exception):
    pass


def _dentro_de(ruta: Path, raiz: Path) -> bool:
    ruta, raiz = ruta.resolve(), raiz.resolve()
    return ruta == raiz or raiz in ruta.parents


def ubicaciones() -> list[Path]:
    """Los lugares declarados por quien opera el servidor, sin los que
    caen dentro del almacenamiento primario (no serían una segunda copia)."""
    return [u for u in settings.ubicaciones_segunda_copia
            if not _dentro_de(u, almacen.raiz()) and not _dentro_de(almacen.raiz(), u)]


def ubicacion_actual(db: Session) -> Path:
    elegida = parametros.leer(db, "preservacion_segunda_ubicacion")
    disponibles = ubicaciones()
    for u in disponibles:
        if str(u) == elegida:
            return u
    if not disponibles:
        raise ErrorSegundaCopia("No hay ningún lugar declarado para la segunda copia (RICORA_SEGUNDA_COPIA).")
    return disponibles[0]


def estado_ubicacion(u: Path) -> dict:
    existe = u.is_dir()
    libre = shutil.disk_usage(u).free if existe else None
    return {"ruta": str(u), "existe": existe, "escribible": existe and os.access(u, os.W_OK), "libre_bytes": libre,
            "mismo_disco_que_primaria": existe and almacen.raiz().exists()
            and os.stat(u).st_dev == os.stat(almacen.raiz()).st_dev}


def ruta_absoluta(copia: SegundaCopia) -> Path:
    raiz = Path(copia.ubicacion)
    destino = (raiz / copia.ruta).resolve()
    if raiz.resolve() not in destino.parents:
        raise ValueError("Ruta fuera de la ubicación de la segunda copia.")
    return destino


def vigente(db: Session, inst_id: uuid.UUID) -> SegundaCopia | None:
    return db.scalar(select(SegundaCopia).where(SegundaCopia.instanciacion_id == inst_id,
                                                SegundaCopia.estado != "reemplazada")
                     .order_by(SegundaCopia.creada_en.desc()).limit(1))


def _huella(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while bloque := f.read(almacen.TAMANO_BLOQUE):
            h.update(bloque)
    return h.hexdigest()


def comprobar(copia: SegundaCopia | None, huella_esperada: str) -> tuple[str, str | None]:
    """(resultado, huella calculada) de la segunda copia frente a la huella
    de la ingesta: integra, alterada, ausente o sin_copia."""
    if copia is None:
        return "sin_copia", None
    try:
        calculada = _huella(ruta_absoluta(copia))
    except (FileNotFoundError, ValueError):
        return "ausente", None
    return ("integra" if calculada == huella_esperada else "alterada"), calculada


def crear(db: Session, inst: Instanciacion, motivo: str, usuario_id: uuid.UUID | None = None,
          ip: str | None = None) -> SegundaCopia:
    """Copia la primaria al lugar configurado. Si la copia escrita no tiene
    la huella de la ingesta (la primaria cambió), no se guarda nada y se
    lanza ErrorSegundaCopia: nunca se replica un archivo alterado."""
    raiz = ubicacion_actual(db)
    copia = SegundaCopia(id=uuid.uuid4(), instanciacion_id=inst.id, ubicacion=str(raiz), motivo=motivo,
                         creada_por_id=usuario_id, algoritmo=inst.algoritmo_huella, estado="sincronizada")
    copia.ruta = f"{inst.fondo_id}/{inst.id}/{copia.id}{almacen.extension_segura(inst.ruta)}"
    destino = ruta_absoluta(copia)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".parcial")
    try:
        almacen.copiar_a(inst.ruta, temporal)
        huella = _huella(temporal)
        if huella != inst.huella:
            raise ErrorSegundaCopia("La copia primaria ya no tiene la huella de la ingesta: no se replica.")
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)  # la copia parcial nunca llegó a ser segunda copia
    copia.huella, copia.tamano_bytes, copia.ultima_verificacion_en = huella, destino.stat().st_size, ahora()
    from app.servicios import mecanismos  # aquí: mecanismos importa vocabulario

    copia.mecanismo_id = mecanismos.del_sistema(db, inst.fondo_id).id
    anterior = vigente(db, inst.id)
    if anterior is not None:
        anterior.estado, anterior.reemplazada_en = "reemplazada", ahora()
    db.add(copia)
    registrar(db, modulo="preservacion", accion="segunda_copia_creada", usuario_id=usuario_id,
              entidad_tipo="instanciacion", entidad_id=inst.id, ip=ip, detalle=inst.nombre_original,
              nuevo={"segunda_copia_id": str(copia.id), "ubicacion": copia.ubicacion, "motivo": motivo,
                     "reemplaza": str(anterior.id) if anterior else None})
    db.flush()
    return copia


def asegurar(db: Session, inst: Instanciacion, motivo: str, usuario_id: uuid.UUID | None = None) -> SegundaCopia | None:
    """Crea la segunda copia si no hay una vigente en el lugar configurado.
    Si no se puede, deja la alerta propia de segunda copia y no detiene lo
    demás (la ingesta o la migración ya terminaron bien)."""
    from app.servicios import alertas

    try:
        actual = vigente(db, inst.id)
        if actual is not None and actual.ubicacion == str(ubicacion_actual(db)):
            return actual
        return crear(db, inst, motivo if actual is None else "cambio_de_ubicacion", usuario_id)
    except (ErrorSegundaCopia, OSError) as exc:
        log.warning("Segunda copia de %s no creada: %s", inst.id, exc)
        alertas.crear(db, tipo="segunda_copia_alterada", severidad="alta", modulo="preservacion",
                      entidad_tipo="instanciacion", entidad_id=inst.id, fondo_id=inst.fondo_id,
                      mensaje=f"«{inst.nombre_original}»: no se pudo crear la segunda copia ({exc}).",
                      detalle={"resultado": "no_creada", "motivo": str(exc)[:300]})
        return None
