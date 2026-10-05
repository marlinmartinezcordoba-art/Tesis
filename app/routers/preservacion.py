"""
Módulo 5 · Preservación digital.

Panel, ficha técnica, verificación de integridad (copia primaria y segunda
copia), migración de formato, restauración, declaración de derechos y
exportación del paquete de información de archivo (permiso del módulo
«preservacion»: consultar para ver, trabajar para actuar). La configuración
es solo del administrador.
"""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.permisos import Actor, acceso_modulo, solo_administrador
from app.db.session import get_db
from app.models.preservacion import Migracion
from app.models.recurso_documental import RecursoDocumental
from app.routers.fondos import fondo_o_404
from app.schemas import respuestas_preservacion as R
from app.servicios import (comprobaciones, derechos, ndsa, paquete, parametros, preservacion, recuperacion, respaldo,
                           segunda_copia)
from app.servicios.auditoria import ip_de

router = APIRouter(prefix="/api/preservacion", tags=["Módulo 5 · Preservación"])
modulo = acceso_modulo("preservacion")


class MigrarIn(BaseModel):
    destino: str = Field(max_length=40)
    # La aprobación es explícita: sin esta marca no se migra nada.
    aprobada: bool


class FilaFormato(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    origen: str = Field(min_length=1, max_length=80)
    origen_mime: list[str] = Field(min_length=1, max_length=20)
    destino: str
    conversor: str
    activo: bool


class ConfiguracionIO(BaseModel):
    frecuencia_dias: int
    formatos: list[FilaFormato]
    segunda_ubicacion: str | None = Field(default=None, max_length=500)


class AprobacionIn(BaseModel):
    aprobada: bool


class DerechosIn(BaseModel):
    entidad_tipo: Literal["instanciacion", "recurso_documental"]
    entidad_id: uuid.UUID
    base: Literal["estatuto", "licencia", "derecho_de_autor", "politica_institucional", "otra"]
    acceso: Literal["publico", "clasificado", "reservado"]
    reproduccion: Literal["permitida", "condicionada", "no_permitida"]
    fundamento: str = Field(min_length=3, max_length=500)
    nota: str | None = Field(default=None, max_length=500)
    vigente_hasta: date | None = None


def _error(exc: preservacion.ErrorPreservacion) -> HTTPException:
    return HTTPException(exc.codigo, detail=str(exc))


def _inst(db: Session, inst_id: uuid.UUID):
    try:
        return preservacion.instanciacion_o_error(db, inst_id)
    except preservacion.ErrorPreservacion as exc:
        raise _error(exc) from exc


@router.get("/panel", summary="Resumen por nivel de riesgo e instanciaciones que requieren atención",
             responses={200: {"model": R.PanelPreservacion,
                             "description": "Resumen del fondo e instanciaciones que requieren atención"}})
def panel(fondo_id: uuid.UUID, _: Actor = Depends(modulo), db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    datos = preservacion.panel(db, fondo_id)
    db.commit()  # las alertas de riesgo que se hayan creado o cerrado al evaluar
    return datos


@router.get("/eventos-recientes", summary="Línea de tiempo: última verificación, migración y restauración del fondo",
             responses={200: {"model": R.EventosRecientes, "description": "Últimos eventos de preservación del fondo"}})
def eventos_recientes(fondo_id: uuid.UUID, _: Actor = Depends(modulo), db: Session = Depends(get_db)):
    from sqlalchemy import func, select

    from app.models.instanciacion import Instanciacion
    from app.models.preservacion import Restauracion, VerificacionIntegridad

    fondo_o_404(db, fondo_id)
    del_fondo = select(Instanciacion.id).where(Instanciacion.fondo_id == fondo_id)
    ultima = db.scalar(select(func.max(VerificacionIntegridad.fecha)).where(
        VerificacionIntegridad.instanciacion_id.in_(del_fondo)))
    verificacion = None
    if ultima is not None:
        # Todo lo verificado en esa misma ronda (el mismo día).
        filas = db.execute(select(VerificacionIntegridad.resultado, func.count()).where(
            VerificacionIntegridad.instanciacion_id.in_(del_fondo),
            func.date(VerificacionIntegridad.fecha) == func.date(ultima)).group_by(VerificacionIntegridad.resultado)).all()
        verificacion = {"fecha": ultima, "resultados": dict(filas)}
    m = db.scalars(select(Migracion).where(Migracion.instanciacion_origen_id.in_(del_fondo))
                   .order_by(Migracion.aprobada_en.desc()).limit(1)).first()
    r = db.scalars(select(Restauracion).where(Restauracion.instanciacion_id.in_(del_fondo))
                   .order_by(Restauracion.fecha.desc()).limit(1)).first()
    return {
        "verificacion": verificacion,
        "migracion": {"fecha": m.terminada_en or m.aprobada_en, "estado": m.estado, "destino": m.destino_nombre,
                      "archivo": db.get(Instanciacion, m.instanciacion_origen_id).nombre_original} if m else None,
        "restauracion": {"fecha": r.fecha, "estado_previo": r.estado_previo,
                         "archivo": db.get(Instanciacion, r.instanciacion_id).nombre_original} if r else None,
        # El último respaldo de la base con simulacro de restauración (PRE-10).
        "simulacro_base_de_datos": _simulacro_reciente(db),
    }


def _simulacro_reciente(db: Session) -> dict | None:
    from sqlalchemy import select

    from app.models.preservacion import RespaldoBaseDatos

    r = db.scalars(select(RespaldoBaseDatos).where(RespaldoBaseDatos.simulacro_en.is_not(None))
                   .order_by(RespaldoBaseDatos.simulacro_en.desc()).limit(1)).first()
    if r is None:
        return None
    return {"fecha": r.simulacro_en, "estado": r.simulacro_estado, "respaldo_en": r.iniciado_en,
            "tablas": (r.simulacro_detalle or {}).get("tablas"), "descargado_en": r.descargado_en}


# --- Respaldo de la base de datos y simulacro de restauración (PRE-10) ------------------------------


@router.get("/respaldos", summary="Respaldos de la base de datos y sus simulacros de restauración",
             responses={200: {"model": R.ListaRespaldos, "description": "Respaldos recientes de la base de datos"}})
def respaldos(_: Actor = Depends(modulo), db: Session = Depends(get_db)):
    from sqlalchemy import select

    from app.models.preservacion import RespaldoBaseDatos

    filas = db.scalars(select(RespaldoBaseDatos).order_by(RespaldoBaseDatos.iniciado_en.desc()).limit(60)).all()
    return {"respaldos": [respaldo.out(r) for r in filas],
            "frecuencia_horas": parametros.leer(db, "respaldo_frecuencia_horas"),
            "dias_copia_externa": parametros.leer(db, "respaldo_dias_copia_externa")}


@router.post("/respaldos", summary="Respaldar la base ahora y probar su restauración (administrador)",
             responses={200: {"model": R.RespaldoBaseDatosOut,
                             "description": "Respaldo hecho y su simulacro de restauración"}})
async def respaldar_ahora(request: Request, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    r = await run_in_threadpool(respaldo.respaldar_y_probar, db, "manual", actor.id)
    db.commit()
    return respaldo.out(r)


@router.get("/respaldos/{respaldo_id}/descargar", summary="Descargar un respaldo fuera del servidor (administrador)",
             responses={200: {"content": {"application/octet-stream": {}},
                             "description": "Archivo del respaldo; su huella SHA-256 va en X-Huella-SHA256"}})
def descargar_respaldo(respaldo_id: uuid.UUID, request: Request, actor: Actor = Depends(solo_administrador),
                       db: Session = Depends(get_db)):
    from pathlib import Path

    from app.models.preservacion import RespaldoBaseDatos

    r = db.get(RespaldoBaseDatos, respaldo_id)
    if r is None or r.estado != "correcto" or r.depurado_en is not None or not r.archivo or not Path(r.archivo).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ese respaldo no está disponible en el servidor.")
    respaldo.registrar_descarga(db, r, actor.id, ip_de(request))
    db.commit()
    # La huella va en el encabezado: quien lo guarde puede comprobar que llegó entero.
    return FileResponse(r.archivo, filename=Path(r.archivo).name, media_type="application/octet-stream",
                        headers={"X-Huella-SHA256": r.huella or ""})


# --- Recuperación ante desastres (NFR-04, NFR-07) ----------------------------------------------


@router.get("/recuperacion", summary="Objetivos RPO/RTO por escenario frente a lo medido, y paquetes de recuperación",
             responses={200: {"model": R.EstadoRecuperacion,
                             "description": "Objetivos de recuperación frente a lo medido"}})
def estado_recuperacion(_: Actor = Depends(modulo), db: Session = Depends(get_db)):
    return recuperacion.estado(db)


@router.post("/recuperacion", summary="Armar el paquete de recuperación y restaurarlo de prueba completo (administrador)",
             responses={200: {"model": R.PaqueteRecuperacionOut,
                             "description": "Paquete de recuperación armado y su simulacro"}})
async def generar_recuperacion(actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    p = await run_in_threadpool(recuperacion.generar_y_probar, db, "manual", actor.id)
    db.commit()
    return recuperacion.out(p)


class ObjetivosIn(BaseModel):
    rpo_horas: int = Field(ge=1, le=8760)
    rto_horas: int = Field(ge=1, le=720)
    frecuencia_dias: int = Field(ge=0, le=365)


@router.put("/recuperacion/objetivos", summary="Fijar los objetivos de recuperación (administrador)",
             responses={200: {"model": R.EstadoRecuperacion,
                             "description": "Estado de la recuperación con los objetivos nuevos"}})
def objetivos_recuperacion(datos: ObjetivosIn, request: Request, actor: Actor = Depends(solo_administrador),
                           db: Session = Depends(get_db)):
    for clave, valor in (("rpo_horas", datos.rpo_horas), ("rto_horas", datos.rto_horas),
                         ("recuperacion_frecuencia_dias", datos.frecuencia_dias)):
        parametros.cambiar(db, clave, valor, actor.id, "preservacion", ip=ip_de(request))
    db.commit()
    return recuperacion.estado(db)


@router.get("/recuperacion/{paquete_id}/descargar", summary="Descargar el paquete de recuperación fuera del servidor (administrador)",
             responses={200: {"content": {"application/x-tar": {}},
                             "description": "Paquete de recuperación (.tar); su huella SHA-256 va en X-Huella-SHA256"}})
def descargar_recuperacion(paquete_id: uuid.UUID, request: Request, actor: Actor = Depends(solo_administrador),
                           db: Session = Depends(get_db)):
    from pathlib import Path

    from app.models.preservacion import PaqueteRecuperacion

    p = db.get(PaqueteRecuperacion, paquete_id)
    if p is None or p.estado != "correcto" or p.depurado_en is not None or not p.archivo or not Path(p.archivo).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ese paquete no está disponible en el servidor.")
    recuperacion.registrar_descarga(db, p, actor.id, ip_de(request))
    db.commit()
    return FileResponse(p.archivo, filename=Path(p.archivo).name, media_type="application/x-tar",
                        headers={"X-Huella-SHA256": p.huella or ""})


@router.get("/instanciacion/{inst_id}", summary="Ficha técnica, historial de verificaciones y de migraciones",
             responses={200: {"model": R.DetalleInstanciacion,
                             "description": "Ficha técnica de preservación de la instanciación"}})
def detalle(inst_id: uuid.UUID, _: Actor = Depends(modulo), db: Session = Depends(get_db)):
    return preservacion.detalle(db, _inst(db, inst_id))


@router.get("/instanciacion/{inst_id}/premis", summary="PREMIS 3.0 de la instanciación (XML, validado contra el XSD)",
             responses={200: {"content": {"application/xml": {}},
                             "description": "Metadatos PREMIS 3.0 de la instanciación"}})
def premis(inst_id: uuid.UUID, _: Actor = Depends(modulo), db: Session = Depends(get_db)):
    from app.servicios.preservacion import aplicacion_creadora

    inst = _inst(db, inst_id)
    xml = paquete.premis_xml(db, inst, paquete.eventos_de(db, inst), derechos.aplicable(db, inst),
                             aplicacion_creadora(db, inst))
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": f'inline; filename="premis-{inst.id}.xml"'})


@router.get("/instanciacion/{inst_id}/comprobaciones", summary="Antivirus y validación de formato de la instanciación",
             responses={200: {"model": list[R.ComprobacionTecnicaOut],
                             "description": "Últimas comprobaciones de antivirus y de validación"}})
def ver_comprobaciones(inst_id: uuid.UUID, _: Actor = Depends(modulo), db: Session = Depends(get_db)):
    inst = _inst(db, inst_id)
    return [{"tipo": c.tipo, "herramienta": c.herramienta, "resultado": c.resultado, "perfil": c.perfil,
             "resumen": c.resumen, "detalle": c.detalle, "origen": c.origen, "realizada_en": c.realizada_en}
            for c in (comprobaciones.ultima(db, inst.id, t) for t in ("antivirus", "validacion")) if c is not None]


@router.get("/ndsa", summary="Niveles NDSA 2.0 por área, calculados del estado real del sistema",
             responses={200: {"model": R.NivelesNdsa, "description": "Niveles NDSA 2.0 alcanzados por área"}})
def niveles_ndsa(_: Actor = Depends(modulo), db: Session = Depends(get_db)):
    return {"version": "NDSA Levels of Digital Preservation 2.0 (2019)",
            "regla": "Un nivel cuenta solo si se cumplen todos sus requisitos y los de los niveles inferiores.",
            "areas": ndsa.niveles(db)}


@router.post("/instanciacion/{inst_id}/verificar", summary="Verificar la integridad ahora",
             responses={200: {"model": R.ResultadoVerificacion,
                             "description": "Resultado de la verificación de integridad"}})
def verificar(inst_id: uuid.UUID, request: Request, actor: Actor = Depends(modulo), db: Session = Depends(get_db)):
    inst = _inst(db, inst_id)
    v = preservacion.verificar(db, inst, origen="manual", usuario_id=actor.id, ip=ip_de(request))
    db.commit()
    return {"resultado": v.resultado, "fecha": v.fecha, "huella_registrada": v.huella_registrada,
            "huella_calculada": v.huella_calculada, "segunda_copia": v.segunda_copia_resultado,
            "huella_segunda_copia": v.segunda_copia_huella}


def _migracion_out(db: Session, m: Migracion) -> dict:
    return {"id": str(m.id), "estado": m.estado, "modo": m.modo, "destino": m.destino, "destino_nombre": m.destino_nombre,
            "mensaje": m.mensaje, "herramienta": preservacion.herramienta_de(db, m),
            "mecanismo": preservacion.mecanismos.resumen(db, m.mecanismo_id), "parametros": m.parametros,
            "nueva_instanciacion": preservacion.detalle(db, db.get(preservacion.Instanciacion, m.instanciacion_resultado_id))
            if m.instanciacion_resultado_id else None}


@router.post("/instanciacion/{inst_id}/migrar", summary="Aprobar la migración a un formato destino",
             responses={200: {"model": R.MigracionOut, "description": "Migración aprobada y su resultado"}})
def migrar(inst_id: uuid.UUID, datos: MigrarIn, request: Request, actor: Actor = Depends(modulo),
           db: Session = Depends(get_db)):
    if not datos.aprobada:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="La migración necesita la aprobación explícita de la archivista.")
    inst = _inst(db, inst_id)
    try:
        m = preservacion.migrar(db, inst, datos.destino, actor.id, ip=ip_de(request))
    except preservacion.ErrorPreservacion as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return _migracion_out(db, m)


@router.post("/instanciacion/{inst_id}/migrar/cargar", summary="Cargar el archivo convertido por fuera",
             responses={200: {"model": R.MigracionOut, "description": "Migración con el archivo convertido cargado"}})
async def cargar(inst_id: uuid.UUID, request: Request, actor: Actor = Depends(modulo), db: Session = Depends(get_db)):
    # Como en la ingesta: el archivo se lee solo después de verificar sesión y permiso.
    formulario = await request.form(max_files=1)
    try:
        archivo = formulario.get("archivo")
        migracion_id = formulario.get("migracion_id")
        if not isinstance(archivo, StarletteUploadFile) or not migracion_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Falta el archivo o la migración.")
        return await run_in_threadpool(_cargar, db, request, actor, inst_id, str(migracion_id), archivo)
    finally:
        await formulario.close()


def _cargar(db: Session, request: Request, actor: Actor, inst_id: uuid.UUID, migracion_id: str,
            archivo: StarletteUploadFile) -> dict:
    try:
        m = db.get(Migracion, uuid.UUID(migracion_id))
    except ValueError:
        m = None
    if m is None or m.instanciacion_origen_id != inst_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Esa migración no existe para esta instanciación.")
    nombre = (archivo.filename or "convertido").replace("\\", "/").rsplit("/", 1)[-1][:500] or "convertido"
    try:
        preservacion.cargar_convertido(db, m, archivo.file, nombre, actor.id, ip=ip_de(request))
    except preservacion.ErrorPreservacion as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return _migracion_out(db, m)


def _aprobada(datos: AprobacionIn, que: str) -> None:
    if not datos.aprobada:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{que} necesita la aprobación explícita.")


@router.post("/instanciacion/{inst_id}/restaurar", summary="Restaurar la copia primaria desde la segunda copia",
             responses={200: {"model": R.DetalleInstanciacion, "description": "Ficha técnica tras la restauración"}})
def restaurar(inst_id: uuid.UUID, datos: AprobacionIn, request: Request, actor: Actor = Depends(modulo),
              db: Session = Depends(get_db)):
    _aprobada(datos, "La restauración")
    inst = _inst(db, inst_id)
    try:
        preservacion.restaurar(db, inst, actor.id, ip=ip_de(request))
    except preservacion.ErrorPreservacion as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return preservacion.detalle(db, inst)


@router.post("/instanciacion/{inst_id}/segunda-copia/reponer", summary="Rehacer la segunda copia desde la primaria",
             responses={200: {"model": R.DetalleInstanciacion,
                             "description": "Ficha técnica con la segunda copia rehecha"}})
def reponer(inst_id: uuid.UUID, datos: AprobacionIn, request: Request, actor: Actor = Depends(modulo),
            db: Session = Depends(get_db)):
    _aprobada(datos, "Rehacer la segunda copia")
    inst = _inst(db, inst_id)
    try:
        preservacion.reponer_segunda_copia(db, inst, actor.id, ip=ip_de(request))
    except preservacion.ErrorPreservacion as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return preservacion.detalle(db, inst)


@router.put("/derechos", summary="Declarar los derechos de una instanciación o de un Record Resource",
             responses={200: {"model": R.DerechosDeclarados, "description": "Declaración de derechos registrada"}})
def declarar_derechos(datos: DerechosIn, request: Request, actor: Actor = Depends(modulo), db: Session = Depends(get_db)):
    try:
        d = derechos.declarar(db, **datos.model_dump(), usuario_id=actor.id, ip=ip_de(request))
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    db.commit()
    return derechos.out(d)


def _descarga(ruta, nombre: str) -> FileResponse:
    return FileResponse(ruta, media_type="application/zip", filename=nombre,
                        background=BackgroundTask(ruta.unlink, missing_ok=True))


@router.post("/instanciacion/{inst_id}/exportar-paquete",
             summary="Paquete de información de archivo (AIP, BagIt + PREMIS) de una instanciación",
             responses={200: {"content": {"application/zip": {}},
                             "description": "Paquete de información de archivo (BagIt + PREMIS) en .zip"}})
def exportar_paquete(inst_id: uuid.UUID, request: Request, actor: Actor = Depends(modulo),
                     db: Session = Depends(get_db)):
    inst = _inst(db, inst_id)
    try:
        ruta, nombre = paquete.exportar_instanciacion(db, inst, actor.id, ip=ip_de(request))
    except paquete.ErrorPaquete as exc:
        db.rollback()
        raise HTTPException(exc.codigo, detail=str(exc)) from exc
    db.commit()
    return _descarga(ruta, nombre)


@router.post("/expediente/{recurso_id}/exportar-paquete",
             summary="Paquete consolidado (AIP) de todas las instanciaciones de un expediente",
             responses={200: {"content": {"application/zip": {}},
                             "description": "Paquete consolidado del expediente en .zip"}})
def exportar_paquete_expediente(recurso_id: uuid.UUID, request: Request, actor: Actor = Depends(modulo),
                                db: Session = Depends(get_db)):
    expediente = db.get(RecursoDocumental, recurso_id)
    if expediente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El expediente no existe.")
    try:
        ruta, nombre = paquete.exportar_expediente(db, expediente, actor.id, ip=ip_de(request))
    except paquete.ErrorPaquete as exc:
        db.rollback()
        raise HTTPException(exc.codigo, detail=str(exc)) from exc
    db.commit()
    return _descarga(ruta, nombre)


# --- Configuración (solo administrador) ---------------------------------------------------------


def _configuracion(db: Session) -> dict:
    return {"frecuencia_dias": int(parametros.leer(db, "preservacion_frecuencia_dias")),
            "formatos": preservacion.formatos_soportados(db),
            "conversores": [{"clave": c.clave, "nombre": c.nombre, "destino": c.destino}
                            for c in preservacion.CONVERSORES.values()],
            "destinos": [{"clave": d.clave, "nombre": d.nombre} for d in preservacion.DESTINOS.values()],
            "herramientas": preservacion.herramientas_disponibles(),
            "segunda_copia": _segunda_copia_configuracion(db)}


def _segunda_copia_configuracion(db: Session) -> dict:
    try:
        actual = str(segunda_copia.ubicacion_actual(db))
    except segunda_copia.ErrorSegundaCopia:
        actual = None
    return {"actual": actual, "primaria": str(segunda_copia.almacen.raiz()),
            "ubicaciones": [segunda_copia.estado_ubicacion(u) for u in segunda_copia.ubicaciones()],
            "pendientes": len(preservacion.sin_segunda_copia(db))}


@router.get("/configuracion", summary="Frecuencia de verificación y tabla de formatos soportados",
             responses={200: {"model": R.ConfiguracionPreservacion,
                             "description": "Configuración de preservación vigente"}})
def ver_configuracion(_: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    return _configuracion(db)


@router.put("/configuracion", summary="Cambiar la frecuencia y la tabla de formatos soportados",
             responses={200: {"model": R.ConfiguracionPreservacion,
                             "description": "Configuración de preservación actualizada"}})
def cambiar_configuracion(datos: ConfiguracionIO, request: Request, actor: Actor = Depends(solo_administrador),
                          db: Session = Depends(get_db)):
    try:
        parametros.cambiar(db, "preservacion_frecuencia_dias", datos.frecuencia_dias, actor.id, "preservacion",
                           ip=ip_de(request))
        parametros.cambiar(db, "preservacion_formatos", [f.model_dump() for f in datos.formatos], actor.id,
                           "preservacion", ip=ip_de(request))
        if datos.segunda_ubicacion is not None:
            # Las copias en el lugar nuevo las crea el trabajador, de a pocas;
            # las del lugar anterior se conservan.
            parametros.cambiar(db, "preservacion_segunda_ubicacion", datos.segunda_ubicacion, actor.id,
                               "preservacion", ip=ip_de(request))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return _configuracion(db)
