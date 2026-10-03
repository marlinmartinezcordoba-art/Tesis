"""
Módulo 2 · Descripción multinivel asistida por inteligencia artificial.

Flujo: cola «por describir» → iniciar (marca en edición + propuesta del
motor) → validar cada entidad (con verificación de vocabulario) →
publicar (una sola transacción). Una descripción publicada se reabre y
corrige con auditoría de valores anteriores y nuevos.
"""

import json
import uuid

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.permisos import Actor, acceso_modulo, lectura_catalogo
from app.db.session import get_db
from app.models.descripcion import Relacion, TrabajoDescripcion
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import NIVEL_DESCRIPCION, RecursoDocumental
from app.models.usuario import Usuario
from app.routers.fondos import fondo_o_404
from app.schemas.descripcion import (
    CoincidenciaOut, EditarIn, ElementoPorDescribir, IniciarIn, NivelSuperiorOut, PublicadaOut, PublicarIn, VerificarIn,
)
from app.servicios import consulta, descripcion, motor, parametros, vocabulario
from app.servicios.auditoria import registrar

router = APIRouter(prefix="/api/descripcion", tags=["Módulo 2 · Descripción"],
                   dependencies=[Depends(acceso_modulo("descripcion"))])


def _error(exc: descripcion.ErrorDescripcion) -> JSONResponse:
    return JSONResponse({"detail": str(exc), **(exc.datos or {})}, status_code=exc.codigo)


def _espacio(db: Session, trabajo: TrabajoDescripcion) -> dict:
    """Todo lo que la pantalla de trabajo necesita, para abrirla o recargarla."""
    documentos = descripcion.documentos_de(db, trabajo)
    fondo = db.get(RecursoDocumental, trabajo.fondo_id)
    return {
        "trabajo_id": str(trabajo.id),
        "nivel": trabajo.nivel,
        "fondo": {"id": str(fondo.id), "titulo": fondo.titulo},
        "recurso_id": str(trabajo.recurso_id) if trabajo.recurso_id else None,
        "documentos": [{"id": str(d.id), "nombre": d.nombre_original, "texto": d.texto_extraido or "",
                        "origen_texto": d.origen_texto, "confianza_ocr": d.confianza_ocr,
                        "ocr_baja_confianza": d.ocr_baja_confianza,
                        "expediente_destino_id": str(d.expediente_destino_id) if d.expediente_destino_id else None}
                       for d in documentos],
        "umbral_ocr": int(parametros.leer(db, "ingesta_umbral_ocr")),
        "propuesta": json.loads(trabajo.propuesta) if trabajo.propuesta else None,
        "minutos_bloqueo": settings.minutos_bloqueo_descripcion,
        "umbral_confianza": settings.umbral_confianza,
    }


# --- Cola --------------------------------------------------------------------------------


@router.get("/cola", response_model=list[ElementoPorDescribir], summary="Documentos listos y todavía sin describir")
def cola(fondo_id: uuid.UUID, db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    filas = descripcion.cola(db, fondo_id)
    db.commit()  # por si venció alguna marca de edición
    expedientes = {e.id: e.titulo for e in db.scalars(select(RecursoDocumental).where(
        RecursoDocumental.fondo_id == fondo_id, RecursoDocumental.nivel == "expediente"))}
    return [ElementoPorDescribir(
        id=i.id, nombre=i.nombre_original, tamano_bytes=i.tamano_bytes, formato=i.formato_nombre,
        expediente=expedientes.get(i.expediente_destino_id), origen_texto=i.origen_texto,
        confianza_ocr=i.confianza_ocr, ocr_baja_confianza=i.ocr_baja_confianza, cargado_en=i.cargado_en,
        en_edicion_por=quien) for i, quien in filas]


@router.get("/buscar-publicadas", summary="Descripciones publicadas del fondo por título (para declarar la secuencia)")
def buscar_publicadas(fondo_id: uuid.UUID, q: str = "", db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    consulta = select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo_id,
                                               RecursoDocumental.publicado_en.isnot(None),
                                               RecursoDocumental.nivel.in_(("expediente", "unidad_documental")))
    if q.strip():
        consulta = consulta.where(RecursoDocumental.titulo.ilike(f"%{q.strip()}%"))
    return [{"id": str(r.id), "titulo": r.titulo, "nivel": r.nivel}
            for r in db.scalars(consulta.order_by(RecursoDocumental.titulo).limit(20))]


@router.get("/niveles-superiores", response_model=list[NivelSuperiorOut],
            summary="Dónde puede quedar incluido lo que se describe")
def niveles_superiores(fondo_id: uuid.UUID, nivel: str, db: Session = Depends(get_db)):
    if nivel not in NIVEL_DESCRIPCION:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Nivel desconocido.")
    fondo_o_404(db, fondo_id)
    filas = db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo_id)).all()
    posibles = [r for r in filas if descripcion.rango(r.nivel) < descripcion.rango(nivel)]
    posibles.sort(key=lambda r: (descripcion.rango(r.nivel), r.titulo))
    return [NivelSuperiorOut(id=r.id, titulo=r.titulo, nivel=r.nivel) for r in posibles]


# --- Espacio de trabajo -----------------------------------------------------------------------


@router.post("/iniciar", summary="Marcar en edición y obtener la propuesta del motor")
async def iniciar(datos: IniciarIn, request: Request, actor: Actor = Depends(acceso_modulo("descripcion")),
                  db: Session = Depends(get_db)):
    try:
        trabajo = await run_in_threadpool(
            descripcion.abrir, db, usuario_id=actor.id, instanciacion_ids=datos.instanciacion_ids, nivel=datos.nivel)
        registrar(db, modulo="descripcion", accion="descripcion_iniciada", usuario_id=actor.id,
                  entidad_tipo="trabajo_descripcion", entidad_id=trabajo.id,
                  nuevo={"nivel": trabajo.nivel, "documentos": [str(i) for i in datos.instanciacion_ids]}, request=request)
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        return _error(exc)
    except IntegrityError:
        db.rollback()
        return JSONResponse({"detail": "Otra persona acaba de abrir alguno de estos documentos."}, status_code=409)

    # El motor se consulta con la marca ya tomada (puede tardar unos segundos).
    documentos = [motor.Documento(id=d.id, nombre=d.nombre_original, texto=d.texto_extraido or "")
                  for d in descripcion.documentos_de(db, trabajo)]
    # El motor no propone a ciegas: recibe las entidades del vocabulario del
    # fondo que ya aparecen en el texto, para poder reutilizarlas.
    contexto = vocabulario.contexto_para_motor(db, trabajo.fondo_id, "\n".join(d.texto for d in documentos))
    propuesta = await run_in_threadpool(motor.proponer, documentos, trabajo.nivel, contexto)
    trabajo.propuesta = json.dumps(propuesta.a_dict(), ensure_ascii=False)
    descripcion.latido(db, trabajo)
    db.commit()
    return _espacio(db, trabajo)


@router.get("/trabajos/{trabajo_id}", summary="Reabrir la pantalla de un trabajo en curso")
def ver_trabajo(trabajo_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    try:
        trabajo = descripcion.trabajo_propio(db, trabajo_id, actor.id)
    except descripcion.ErrorDescripcion as exc:
        db.commit()
        return _error(exc)
    return _espacio(db, trabajo)


@router.post("/trabajos/{trabajo_id}/latido", status_code=status.HTTP_204_NO_CONTENT,
             summary="Mantener la marca «en edición» mientras se trabaja")
def mantener(trabajo_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    try:
        trabajo = descripcion.trabajo_propio(db, trabajo_id, actor.id)
    except descripcion.ErrorDescripcion as exc:
        db.commit()
        return _error(exc)
    descripcion.latido(db, trabajo)
    db.commit()


@router.post("/{trabajo_id}/cancelar", status_code=status.HTTP_204_NO_CONTENT,
             summary="Salir sin publicar: libera la marca «en edición»")
def cancelar(trabajo_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    try:
        trabajo = descripcion.trabajo_propio(db, trabajo_id, actor.id)
    except descripcion.ErrorDescripcion as exc:
        db.commit()
        return _error(exc)
    descripcion.cancelar(db, trabajo, actor.id)
    db.commit()


@router.post("/verificar-vocabulario", response_model=list[CoincidenciaOut],
             summary="¿Ya existe en el vocabulario del fondo? (delegado al servicio de vocabularios)")
def verificar(datos: VerificarIn, db: Session = Depends(get_db)):
    fondo_o_404(db, datos.fondo_id)
    # Una actividad es un ejercicio concreto, no la competencia (hallazgo CM-14):
    # dos ejercicios del mismo trámite no se deben fusionar por parecerse.
    aviso = (AVISO_ACTIVIDAD if datos.tipo == "actividad" else None)
    return [CoincidenciaOut(**c.__dict__, aviso=aviso)
            for c in vocabulario.verificar(db, datos.fondo_id, datos.tipo, datos.valor)]


AVISO_ACTIVIDAD = ("Una actividad es un ejercicio concreto (la expedición de licencias de 1948), no la competencia "
                   "(eso es el tipo de actividad). Reutilícela solo si es el mismo ejercicio; si es otro año u otro "
                   "trámite, cree una nueva y asígnele el mismo tipo de actividad.")


def _partes_de(partes) -> list[descripcion.ParteConfirmada]:
    return [descripcion.ParteConfirmada(
        titulo=p.titulo, alcance=p.alcance, recorte=p.recorte.model_dump(mode="json") if p.recorte else None,
        tipo_parte=descripcion.EntidadConfirmada(tipo="tipo_parte", valor=p.tipo_parte.valor,
                                                 reutilizar_id=p.tipo_parte.reutilizar_id,
                                                 crear_nueva=p.tipo_parte.crear_nueva) if p.tipo_parte else None)
        for p in partes]


def _deshacer_recortes(db: Session) -> None:
    """Si la transacción no se confirmó, los archivos de recorte que alcanzó
    a escribir no forman parte del fondo: se borran."""
    from app.servicios import recorte

    for inst in db.info.pop("recortes_nuevos", []):
        recorte.borrar_archivo(inst)


def _confirmar_recortes(db: Session) -> None:
    """Segunda copia de cada recorte, como de cualquier instanciación nueva."""
    from app.servicios import segunda_copia

    nuevos = db.info.pop("recortes_nuevos", [])
    for inst in nuevos:
        segunda_copia.asegurar(db, inst, "recorte")
    if nuevos:
        db.commit()


@router.post("/publicar", status_code=status.HTTP_201_CREATED, summary="Publicar la descripción (una sola transacción)")
def publicar(datos: PublicarIn, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    try:
        trabajo = descripcion.trabajo_propio(db, datos.trabajo_id, actor.id)
        if trabajo.recurso_id is not None:
            raise descripcion.ErrorDescripcion("Este trabajo es una corrección: use la edición de la descripción.", 409)
        recurso = descripcion.publicar(
            db, trabajo=trabajo, usuario_id=actor.id, titulo=datos.titulo, alcance=datos.alcance_contenido,
            incluido_en_id=datos.incluido_en_id,
            entidades=[descripcion.EntidadConfirmada(**e.model_dump()) for e in datos.entidades],
            idiomas=datos.idiomas, condiciones_acceso=datos.condiciones_acceso, condiciones_uso=datos.condiciones_uso,
            precede_a_id=datos.precede_a_id, sigue_a_id=datos.sigue_a_id, partes=_partes_de(datos.partes),
            historia_archivistica=datos.historia_archivistica, isadg_textos=datos.isadg, escrituras=datos.escrituras)
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        _deshacer_recortes(db)
        # La marca sigue tomada: el archivista corrige y vuelve a publicar.
        return _error(exc)
    except Exception:
        db.rollback()
        _deshacer_recortes(db)
        raise
    _confirmar_recortes(db)
    return descripcion.detalle(db, recurso)


# --- Páginas del documento (para ver y recortar partes documentales) ---------------------------------


def _documento_del_trabajo(db: Session, trabajo_id: uuid.UUID, instanciacion_id: uuid.UUID, usuario_id: uuid.UUID):
    trabajo = descripcion.trabajo_propio(db, trabajo_id, usuario_id)
    inst = next((d for d in descripcion.instanciaciones_del_trabajo(db, trabajo) if d.id == instanciacion_id), None)
    if inst is None:
        raise descripcion.ErrorDescripcion("Ese documento no es de este espacio de trabajo.", 404)
    return inst


@router.get("/trabajos/{trabajo_id}/documentos/{instanciacion_id}/paginas",
            summary="Cuántas páginas tiene el documento y si se puede mostrar como imagen")
def paginas(trabajo_id: uuid.UUID, instanciacion_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")),
            db: Session = Depends(get_db)):
    from app.servicios import recorte

    try:
        inst = _documento_del_trabajo(db, trabajo_id, instanciacion_id, actor.id)
    except descripcion.ErrorDescripcion as exc:
        return _error(exc)
    if not recorte.admite_paginas(inst):
        return {"admite": False, "total": 0}
    try:
        return {"admite": True, "total": recorte.total_paginas(inst)}
    except (OSError, ValueError):
        return {"admite": False, "total": 0}


@router.get("/trabajos/{trabajo_id}/documentos/{instanciacion_id}/paginas/{pagina}",
            summary="Imagen PNG de una página del documento")
def pagina(trabajo_id: uuid.UUID, instanciacion_id: uuid.UUID, pagina: int,
           actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    from fastapi.responses import Response

    from app.servicios import recorte

    try:
        inst = _documento_del_trabajo(db, trabajo_id, instanciacion_id, actor.id)
        contenido = recorte.pagina_png(inst, pagina)
    except descripcion.ErrorDescripcion as exc:
        return _error(exc)
    except recorte.ErrorRecorte as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    return Response(contenido, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


# --- Previsualización (visor sin descarga), el mismo de la cola de ingesta --------------------------------------------------------


@router.get("/{instanciacion_id}/previsualizar", summary="Datos del visor: páginas que se pueden mostrar y texto extraído")
def previsualizar(instanciacion_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    from app.servicios import previsualizacion

    try:
        return previsualizacion.info(db, actor, instanciacion_id)
    except previsualizacion.ErrorPrevisualizacion as exc:
        raise HTTPException(exc.codigo, detail=str(exc)) from exc


@router.get("/{instanciacion_id}/previsualizar/{pagina}", summary="Una página como imagen PNG (nunca el original)")
def previsualizar_pagina(instanciacion_id: uuid.UUID, pagina: int, actor: Actor = Depends(acceso_modulo("descripcion")),
                         db: Session = Depends(get_db)):
    from fastapi.responses import Response

    from app.servicios import previsualizacion

    try:
        contenido = previsualizacion.pagina(db, actor, instanciacion_id, pagina)
    except previsualizacion.ErrorPrevisualizacion as exc:
        raise HTTPException(exc.codigo, detail=str(exc)) from exc
    return Response(contenido, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


# --- Descripciones publicadas: consulta interna y corrección ------------------------------------------


def _recurso_o_404(db: Session, recurso_id: uuid.UUID) -> RecursoDocumental:
    recurso = db.get(RecursoDocumental, recurso_id)
    if recurso is None or recurso.publicado_en is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La descripción no existe.")
    return recurso


@router.get("/publicadas", response_model=list[PublicadaOut], summary="Descripciones publicadas del fondo")
def publicadas(fondo_id: uuid.UUID, db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    descripcion.expirar(db)
    db.commit()
    filas = db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo_id,
                                                       RecursoDocumental.publicado_en.isnot(None))
                       .order_by(RecursoDocumental.publicado_en.desc()).limit(500)).all()
    documentos = dict(db.execute(select(Relacion.origen_id, func.count(Relacion.id)).where(
        Relacion.codigo_ric == "has_or_had_instantiation", Relacion.estado == "vigente").group_by(Relacion.origen_id)).all())
    editores = dict(db.execute(select(TrabajoDescripcion.recurso_id, Usuario.nombre)
                               .join(Usuario, Usuario.id == TrabajoDescripcion.usuario_id)
                               .where(TrabajoDescripcion.estado == "abierto", TrabajoDescripcion.recurso_id.isnot(None))).all())
    return [PublicadaOut(id=r.id, titulo=r.titulo, nivel=r.nivel, documentos=documentos.get(r.id, 0),
                         publicado_en=r.publicado_en, actualizado_en=r.actualizado_en,
                         en_edicion_por=editores.get(r.id)) for r in filas]


@router.get("/publicadas/exportar", summary="Todas las descripciones publicadas del fondo, en Excel (más recientes primero)")
def publicadas_xlsx(fondo_id: uuid.UUID, db: Session = Depends(get_db)):
    from fastapi.responses import Response

    from app.servicios.hoja import libro

    fondo_o_404(db, fondo_id)
    filas = db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo_id,
                                                       RecursoDocumental.publicado_en.isnot(None))
                       .order_by(RecursoDocumental.publicado_en.desc())).all()
    documentos = dict(db.execute(select(Relacion.origen_id, func.count(Relacion.id)).where(
        Relacion.codigo_ric == "has_or_had_instantiation", Relacion.estado == "vigente").group_by(Relacion.origen_id)).all())
    contenido = libro([("Descritas", ["Título", "Nivel", "Código de referencia", "Documentos", "Publicada el",
                                      "Actualizada el", "Identificador interno"],
                        [[r.titulo, r.nivel.replace("_", " "), r.codigo_referencia, documentos.get(r.id, 0), r.publicado_en,
                          r.actualizado_en, str(r.id)] for r in filas])])
    return Response(contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="descripciones-publicadas.xlsx"'})


@router.get("/productividad", summary="Lo descrito hoy por quien consulta y el total del fondo (dato del panel consolidado)")
def productividad(fondo_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    from datetime import timedelta

    from app.db.base import ahora
    from app.models.auditoria import RegistroAuditoria
    from app.servicios import trazabilidad

    fondo_o_404(db, fondo_id)
    hoy = ahora().astimezone(trazabilidad._zona()).date()
    acciones = [a for a in trazabilidad.ACCIONES if trazabilidad.grupo(a) == "Descripciones validadas"]
    por_mi = db.scalar(select(func.count(RegistroAuditoria.id)).where(
        RegistroAuditoria.usuario_id == actor.id, RegistroAuditoria.accion.in_(acciones),
        RegistroAuditoria.fecha >= trazabilidad._inicio_local(hoy),
        RegistroAuditoria.fecha < trazabilidad._inicio_local(hoy + timedelta(days=1))))
    total = db.scalar(select(func.count(RecursoDocumental.id)).where(
        RecursoDocumental.fondo_id == fondo_id, RecursoDocumental.nivel != "fondo", RecursoDocumental.publicado_en.isnot(None)))
    return {"hoy_por_mi": por_mi, "total_fondo": total}


@router.get("/registros/{recurso_id}", summary="Descripción publicada, vista interna (con origen y confianza)")
def ver(recurso_id: uuid.UUID, db: Session = Depends(get_db)):
    return descripcion.detalle(db, _recurso_o_404(db, recurso_id))


class AgrupacionIn(BaseModel):
    fondo_id: uuid.UUID
    nivel: str
    titulo: str = Field(max_length=500)
    incluido_en_id: uuid.UUID | None = None
    codigo_referencia: str | None = Field(default=None, max_length=100)
    fechas_extremas: str | None = Field(default=None, max_length=60)
    alcance_contenido: str | None = Field(default=None, max_length=5000)
    productor_id: uuid.UUID | None = None


@router.post("/agrupaciones", status_code=status.HTTP_201_CREATED,
             summary="Crear una sección, subsección, serie, subserie o expediente sin archivos propios")
def crear_agrupacion(datos: AgrupacionIn, actor: Actor = Depends(acceso_modulo("descripcion")),
                     db: Session = Depends(get_db)):
    fondo_o_404(db, datos.fondo_id)
    try:
        r = descripcion.crear_agrupacion(
            db, fondo_id=datos.fondo_id, nivel=datos.nivel, titulo=datos.titulo, incluido_en_id=datos.incluido_en_id,
            usuario_id=actor.id, codigo_referencia=datos.codigo_referencia, fechas_extremas=datos.fechas_extremas,
            alcance=datos.alcance_contenido, productor_id=datos.productor_id)
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        return _error(exc)
    return descripcion.detalle(db, r)


class InclusionIn(BaseModel):
    conjunto_id: uuid.UUID


@router.post("/registros/{recurso_id}/inclusiones", status_code=status.HTTP_201_CREATED,
             summary="Incluir además en otro conjunto (p. ej. una colección facticia)")
def agregar_inclusion(recurso_id: uuid.UUID, datos: InclusionIn,
                      actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    recurso = _recurso_o_404(db, recurso_id)
    conjunto = _recurso_o_404(db, datos.conjunto_id)
    try:
        descripcion.agregar_inclusion(db, recurso, conjunto, actor.id)
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        return _error(exc)
    return descripcion.detalle(db, recurso)


class IndividualizarIn(BaseModel):
    instanciacion_id: uuid.UUID
    titulo: str | None = Field(default=None, max_length=500)


@router.post("/registros/{recurso_id}/individualizar", status_code=status.HTTP_201_CREATED,
             summary="Dar a un documento del conjunto su propio Record (luego se describe al reabrirlo)")
def individualizar(recurso_id: uuid.UUID, datos: IndividualizarIn, actor: Actor = Depends(acceso_modulo("descripcion")),
                   db: Session = Depends(get_db)):
    conjunto = _recurso_o_404(db, recurso_id)
    inst = db.get(Instanciacion, datos.instanciacion_id)
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El archivo no existe.")
    try:
        r = descripcion.individualizar(db, conjunto, inst, actor.id, datos.titulo)
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        return _error(exc)
    return descripcion.detalle(db, r)


class OriginalFisicoIn(BaseModel):
    soporte: str
    ubicacion: str | None = Field(default=None, max_length=300)
    caracteristicas_fisicas: str | None = Field(default=None, max_length=5000)  # ISAD-G 3.4.4


@router.get("/registros/{recurso_id}/isadg", summary="Ficha ISAD(G) completa: los 26 elementos y su fuente")
def ficha_isadg(recurso_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.servicios import isadg

    recurso = db.get(RecursoDocumental, recurso_id)
    if recurso is None or (recurso.publicado_en is None and recurso.nivel != "fondo"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La descripción no existe.")
    elementos = isadg.ficha(db, recurso)
    return {"id": str(recurso.id), "titulo": recurso.titulo, "elementos": elementos,
            "con_dato": sum(1 for e in elementos if e["valor"]), "total": len(elementos)}


@router.post("/registros/{recurso_id}/original-fisico", status_code=status.HTTP_201_CREATED,
             summary="Registrar el original físico (papel…) como instanciación")
def original_fisico(recurso_id: uuid.UUID, datos: OriginalFisicoIn, actor: Actor = Depends(acceso_modulo("descripcion")),
                    db: Session = Depends(get_db)):
    recurso = _recurso_o_404(db, recurso_id)
    try:
        descripcion.registrar_original_fisico(db, recurso, soporte=datos.soporte, ubicacion=datos.ubicacion,
                                              usuario_id=actor.id, caracteristicas=datos.caracteristicas_fisicas)
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        return _error(exc)
    return descripcion.detalle(db, recurso)


class CustodioIn(BaseModel):
    agente_id: uuid.UUID
    fecha_edtf: str | None = Field(default=None, max_length=200)
    nota: str | None = Field(default=None, max_length=500)


@router.post("/instanciaciones/{instanciacion_id}/custodios", status_code=status.HTTP_201_CREATED,
             summary="Un tramo de la custodia de un archivo o de un original físico (RiC-R039i)")
def custodio_de_instanciacion(instanciacion_id: uuid.UUID, datos: CustodioIn,
                              actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    inst = db.get(Instanciacion, instanciacion_id)
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El archivo no existe.")
    try:
        r = descripcion.custodio_de_instanciacion(db, inst, datos.agente_id, datos.fecha_edtf, datos.nota, actor.id)
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        return _error(exc)
    return {"relacion_id": str(r.id), "custodios": descripcion.custodios_de(db, inst.id)}


@router.post("/registros/{recurso_id}/reabrir", summary="Reabrir una descripción publicada para corregirla")
def reabrir(recurso_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    recurso = _recurso_o_404(db, recurso_id)
    try:
        trabajo = descripcion.reabrir(db, recurso, actor.id)
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        return _error(exc)
    except IntegrityError:
        db.rollback()
        return JSONResponse({"detail": "Otra persona acaba de abrir esta descripción."}, status_code=409)
    return {"trabajo_id": str(trabajo.id), "descripcion": descripcion.detalle(db, recurso)}


@router.patch("/{recurso_id}", summary="Corregir una descripción publicada (queda en auditoría)")
def editar(recurso_id: uuid.UUID, datos: EditarIn, actor: Actor = Depends(acceso_modulo("descripcion")),
           db: Session = Depends(get_db)):
    recurso = _recurso_o_404(db, recurso_id)
    try:
        trabajo = descripcion.trabajo_propio(db, datos.trabajo_id, actor.id)
        descripcion.editar(
            db, recurso=recurso, trabajo=trabajo, usuario_id=actor.id, titulo=datos.titulo,
            alcance=datos.alcance_contenido, incluido_en_id=datos.incluido_en_id, anular=datos.anular_relaciones,
            quitar_forma=datos.quitar_forma_documental,
            agregar=[descripcion.EntidadConfirmada(**e.model_dump()) for e in datos.agregar_entidades],
            control=datos.control.model_dump() if datos.control else None,
            idiomas=datos.idiomas, condiciones_acceso=datos.condiciones_acceso, condiciones_uso=datos.condiciones_uso,
            precede_a_id=datos.precede_a_id, sigue_a_id=datos.sigue_a_id,
            agregar_partes=_partes_de(datos.agregar_partes), historia_archivistica=datos.historia_archivistica,
            isadg_textos=datos.isadg, escrituras=datos.escrituras)
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        _deshacer_recortes(db)
        return _error(exc)
    except Exception:
        db.rollback()
        _deshacer_recortes(db)
        raise
    _confirmar_recortes(db)
    return descripcion.detalle(db, recurso)


# --- Consulta pública (base del catálogo del módulo 4) ------------------------------------------------

catalogo = APIRouter(prefix="/api/catalogo", tags=["Catálogo de consulta"])


@catalogo.get("/registros/{recurso_id}", summary="Ficha de consulta de una descripción publicada")
def ficha(recurso_id: uuid.UUID, actor: Actor = Depends(lectura_catalogo), db: Session = Depends(get_db)):
    from app.routers.instrumentos import ve_restringidos
    from app.servicios import instrumentos

    recurso = _recurso_o_404(db, recurso_id)
    fondo = db.get(RecursoDocumental, recurso.fondo_id or recurso.id)
    # La misma regla del catálogo: lo clasificado o reservado no sale a quien no es archivista.
    ver = ve_restringidos(actor)
    nodos = instrumentos.arbol(db, fondo, ver).nodos
    if recurso.id not in nodos:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La descripción no existe o no se puede consultar.")
    return consulta.ficha_publica(db, recurso, set(nodos), ver)
