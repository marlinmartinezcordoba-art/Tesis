"""
Módulo 1 · Ingesta y digitalización.

Recibe cualquier archivo, lo guarda y crea su Instantiation en estado
«procesando»; el trabajador hace el resto. La cola muestra solo lo que
todavía necesita algo del archivista (procesando, posible duplicado, con
error); lo que queda listo pasa solo a descripción por su estado.
"""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as StarletteUploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permisos import Actor, acceso_modulo, solo_administrador
from app.db.base import ahora
from app.db.session import get_db
from app.models.instanciacion import ESTADOS_COLA, Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.models.usuario import Usuario
from app.routers.fondos import fondo_o_404
from app.schemas.ingesta import CargaOut, ColaOut, ElementoCola, LimiteIn, LimiteOut, Referencia, ResultadoCarga
from app.servicios import almacen, parametros, procesamiento
from app.servicios.auditoria import ip_de, registrar

router = APIRouter(prefix="/api/ingesta", tags=["Módulo 1 · Ingesta"],
                   dependencies=[Depends(acceso_modulo("ingesta"))])


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + " MB"


# --- Límite de tamaño ------------------------------------------------------------


@router.get("/limite", response_model=LimiteOut, summary="Tamaño máximo por archivo")
def limite(db: Session = Depends(get_db)):
    mb = int(parametros.leer(db, "ingesta_limite_mb"))
    return LimiteOut(limite_mb=mb, limite_bytes=mb * 1024 * 1024)


@router.put("/limite", response_model=LimiteOut, summary="Cambiar el tamaño máximo (solo administrador)")
def cambiar_limite(datos: LimiteIn, request: Request, actor: Actor = Depends(solo_administrador),
                   db: Session = Depends(get_db)):
    try:
        parametros.cambiar(db, "ingesta_limite_mb", datos.limite_mb, actor.id, "ingesta", ip=ip_de(request))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return limite(db)


# --- Carga -------------------------------------------------------------------------


def _uuid(valor, campo: str, obligatorio: bool) -> uuid.UUID | None:
    if valor in (None, ""):
        if obligatorio:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Falta {campo}.")
        return None
    try:
        return uuid.UUID(str(valor))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{campo} no es válido.") from exc


@router.post("/cargar", response_model=CargaOut,
             summary="Cargar uno o varios archivos (multipart: archivos, fondo_id, expediente_id opcional)")
async def cargar(request: Request, actor: Actor = Depends(acceso_modulo("ingesta")), db: Session = Depends(get_db)):
    # El formulario se lee aquí, después de verificar sesión y rol: nadie
    # sin permiso puede hacer que el servidor reciba un archivo, y una
    # subida larga no queda rechazada porque el token venció a mitad.
    formulario = await request.form(max_files=1000)
    try:
        fondo_id = _uuid(formulario.get("fondo_id"), "el fondo", True)
        expediente_id = _uuid(formulario.get("expediente_id"), "el expediente", False)
        archivos = [a for a in formulario.getlist("archivos") if isinstance(a, StarletteUploadFile)]
        if not archivos:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No llegó ningún archivo.")
        return await run_in_threadpool(_cargar, db, request, actor, fondo_id, expediente_id, archivos)
    finally:
        await formulario.close()


def _cargar(db: Session, request: Request, actor: Actor, fondo_id: uuid.UUID, expediente_id: uuid.UUID | None,
            archivos: list[StarletteUploadFile]) -> CargaOut:
    fondo = fondo_o_404(db, fondo_id)
    expediente = None
    if expediente_id is not None:
        expediente = db.get(RecursoDocumental, expediente_id)
        if expediente is None or expediente.nivel != "expediente" or expediente.fondo_id != fondo.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El expediente no pertenece a este fondo.")
    limite_bytes = parametros.limite_ingesta_bytes(db)
    resultados = []
    for archivo in archivos:
        nombre = (archivo.filename or "sin nombre").replace("\\", "/").rsplit("/", 1)[-1][:500] or "sin nombre"
        motivo = None
        if archivo.size is not None and archivo.size > limite_bytes:
            motivo = f"Excede el límite de {_mb(limite_bytes)} ({_mb(archivo.size)})."
        elif archivo.size == 0:
            motivo = "El archivo está vacío."
        if motivo is None:
            nuevo_id = uuid.uuid4()
            try:
                ruta, tamano = almacen.guardar(archivo.file, fondo.id, nuevo_id, nombre, limite_bytes)
            except almacen.ExcedeLimite:
                motivo = f"Excede el límite de {_mb(limite_bytes)}."
            except OSError:
                motivo = "No se pudo guardar el archivo en el servidor (¿disco lleno?). Avise al administrador."
            else:
                if tamano == 0:
                    almacen.borrar(ruta)
                    motivo = "El archivo está vacío."
        if motivo is not None:
            registrar(db, modulo="ingesta", accion="carga_rechazada", usuario_id=actor.id, entidad_tipo="archivo",
                      nuevo={"nombre": nombre, "fondo": str(fondo.id)}, detalle=motivo, request=request)
            resultados.append(ResultadoCarga(nombre=nombre, aceptado=False, motivo=motivo))
            continue
        inst = Instanciacion(id=nuevo_id, fondo_id=fondo.id, expediente_destino_id=expediente.id if expediente else None,
                             nombre_original=nombre, ruta=ruta, tamano_bytes=tamano,
                             tipo_declarado=(archivo.content_type or "")[:200] or None,
                             estado="procesando", paso="en_espera", cargado_por_id=actor.id)
        db.add(inst)
        registrar(db, modulo="ingesta", accion="documento_cargado", usuario_id=actor.id, entidad_tipo="instanciacion",
                  entidad_id=inst.id, request=request,
                  nuevo={"nombre": nombre, "tamano_bytes": tamano, "fondo": fondo.titulo,
                         "expediente": expediente.titulo if expediente else None})
        db.commit()
        resultados.append(ResultadoCarga(nombre=nombre, aceptado=True, id=inst.id))
    db.commit()
    return CargaOut(resultados=resultados)


# --- Cola -------------------------------------------------------------------------------


def _elemento(db: Session, inst: Instanciacion, nombres: dict) -> ElementoCola:
    referencia = None
    if inst.duplicado_de_id:
        original = db.get(Instanciacion, inst.duplicado_de_id)
        if original is not None:
            referencia = Referencia(id=original.id, nombre=original.nombre_original, cargado_en=original.cargado_en,
                                    estado=original.estado)
    expediente = db.get(RecursoDocumental, inst.expediente_destino_id) if inst.expediente_destino_id else None
    return ElementoCola(
        id=inst.id, nombre=inst.nombre_original, tamano_bytes=inst.tamano_bytes, estado=inst.estado, paso=inst.paso,
        progreso=inst.progreso, detalle_paso=inst.detalle_paso, mensaje_error=inst.mensaje_error,
        cargado_en=inst.cargado_en, cargado_por=nombres.get(inst.cargado_por_id),
        expediente=expediente.titulo if expediente else None, duplicado_de=referencia,
    )


@router.get("/cola", response_model=ColaOut, summary="Lo que todavía necesita algo del archivista")
def cola(fondo_id: uuid.UUID, db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    filas = db.scalars(select(Instanciacion).where(Instanciacion.fondo_id == fondo_id,
                                                   Instanciacion.estado.in_(ESTADOS_COLA))
                       .order_by(Instanciacion.cargado_en)).all()
    nombres = dict(db.execute(select(Usuario.id, Usuario.nombre)).all())
    elementos = [_elemento(db, f, nombres) for f in filas]
    listos_hoy = db.scalar(select(func.count(Instanciacion.id)).where(
        Instanciacion.fondo_id == fondo_id, Instanciacion.estado == "listo_para_descripcion",
        Instanciacion.procesado_en > ahora() - timedelta(hours=24))) or 0
    return ColaOut(
        procesando=[e for e in elementos if e.estado == "procesando"],
        duplicados=[e for e in elementos if e.estado == "duplicado_pendiente"],
        errores=[e for e in elementos if e.estado == "error"],
        listos_hoy=listos_hoy,
    )


# --- Decisiones del archivista ---------------------------------------------------------


def _bloquear(db: Session, instanciacion_id: uuid.UUID, estados: tuple[str, ...], accion: str) -> Instanciacion:
    inst = db.scalar(select(Instanciacion).where(Instanciacion.id == instanciacion_id).with_for_update())
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El documento no existe o ya fue descartado.")
    if inst.estado not in estados:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Este documento ya no está en un estado que permita {accion}.")
    return inst


def _datos(inst: Instanciacion) -> dict:
    return {"nombre": inst.nombre_original, "tamano_bytes": inst.tamano_bytes, "huella": inst.huella,
            "estado": inst.estado, "duplicado_de": str(inst.duplicado_de_id) if inst.duplicado_de_id else None,
            "mensaje_error": inst.mensaje_error}


@router.post("/{instanciacion_id}/confirmar-duplicado", response_model=ElementoCola,
             summary="Es distinto: continuar el procesamiento")
def confirmar_duplicado(instanciacion_id: uuid.UUID, request: Request, actor: Actor = Depends(acceso_modulo("ingesta")),
                        db: Session = Depends(get_db)):
    inst = _bloquear(db, instanciacion_id, ("duplicado_pendiente",), "confirmarlo")
    anterior = _datos(inst)
    inst.estado = "procesando"
    inst.duplicado_confirmado = True
    inst.tomado_en = None
    registrar(db, modulo="ingesta", accion="duplicado_confirmado", usuario_id=actor.id, entidad_tipo="instanciacion",
              entidad_id=inst.id, anterior=anterior, nuevo={"estado": "procesando", "duplicado_confirmado": True},
              request=request)
    db.commit()
    return _elemento(db, inst, {})


@router.delete("/{instanciacion_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Cancelar un duplicado o descartar un error (elimina el documento y su archivo)")
def descartar(instanciacion_id: uuid.UUID, request: Request, actor: Actor = Depends(acceso_modulo("ingesta")),
              db: Session = Depends(get_db)):
    inst = _bloquear(db, instanciacion_id, ("duplicado_pendiente", "error"), "descartarlo")
    accion = "carga_cancelada" if inst.estado == "duplicado_pendiente" else "carga_descartada"
    registrar(db, modulo="ingesta", accion=accion, usuario_id=actor.id, entidad_tipo="instanciacion",
              entidad_id=inst.id, anterior=_datos(inst), request=request,
              detalle="Eliminación real: el archivo nunca llegó a integrarse al fondo.")
    ruta = inst.ruta
    db.delete(inst)
    db.commit()
    # El archivo se borra después de confirmar el registro: si algo falla
    # antes, el documento sigue existiendo con su archivo.
    almacen.borrar(ruta)


@router.post("/{instanciacion_id}/reintentar", response_model=ElementoCola,
             summary="Volver a procesar desde el principio")
def reintentar(instanciacion_id: uuid.UUID, request: Request, actor: Actor = Depends(acceso_modulo("ingesta")),
               db: Session = Depends(get_db)):
    inst = _bloquear(db, instanciacion_id, ("error",), "reintentarlo")
    anterior = _datos(inst)
    procesamiento.reiniciar(inst)
    registrar(db, modulo="ingesta", accion="reintento", usuario_id=actor.id, entidad_tipo="instanciacion",
              entidad_id=inst.id, anterior=anterior, nuevo={"estado": "procesando"}, request=request)
    db.commit()
    return _elemento(db, inst, {})
