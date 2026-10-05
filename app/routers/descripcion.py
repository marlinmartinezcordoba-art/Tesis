"""
Módulo 2 · Descripción multinivel asistida por inteligencia artificial.

Flujo: cola «por describir» → iniciar (marca en edición + propuesta del
motor) → validar cada entidad (con verificación de vocabulario) →
publicar (una sola transacción). Una descripción publicada se reabre y
corrige con auditoría de valores anteriores y nuevos.
"""

import json
import uuid
from typing import Literal

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
from app.schemas.respuestas_descripcion import (
    AtributoCatalogo, CustodiosOut, DetalleDescripcionOut, EspacioTrabajoOut, FichaIsadgOut, FichaPublicaOut, PaginasOut,
    PrevisualizacionOut, ProductividadOut, PropuestaIAOut, ReabrirOut, ReferenciaBreve, VersionCompleta, VersionResumen,
)
from app.servicios import consulta, descripcion, motor, parametros, propuestas_ia, vocabulario
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


@router.get("/buscar-publicadas", responses={200: {"model": list[ReferenciaBreve], "description": "Descripciones publicadas que coinciden con el título"}},
            summary="Descripciones publicadas del fondo por título (para declarar la secuencia)")
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


@router.post("/iniciar", responses={200: {"model": EspacioTrabajoOut, "description": "El espacio de trabajo con la propuesta del motor"}},
             summary="Marcar en edición y obtener la propuesta del motor")
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
    # Evidencia (RF-AI-002 y RF-OCR-001): página y zona de cada fragmento, y la
    # propuesta guardada como registro inalterable.
    propuestas_ia.ubicar_fragmentos(db, propuesta)
    registro = propuestas_ia.registrar(db, propuesta, origen="descripcion", fondo_id=trabajo.fondo_id,
                                       nivel=trabajo.nivel, instanciaciones=[d.id for d in documentos],
                                       solicitada_por_id=actor.id, trabajo_id=trabajo.id)
    datos = propuesta.a_dict()
    if registro is not None:
        trabajo.propuesta_id = registro.id
        datos["propuesta_id"] = str(registro.id)
    trabajo.propuesta = json.dumps(datos, ensure_ascii=False)
    descripcion.latido(db, trabajo)
    db.commit()
    return _espacio(db, trabajo)


@router.get("/propuestas/{propuesta_id}", responses={200: {"model": PropuestaIAOut, "description": "La propuesta completa: entrada, respuesta y contenido controlado"}},
            summary="Una propuesta del motor completa, con su huella verificada (RF-AI-002)")
def ver_propuesta(propuesta_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")),
                  db: Session = Depends(get_db)):
    """Lo que el motor recibió, lo que respondió tal cual y la propuesta ya
    controlada. Solo el equipo que describe: contiene fragmentos del texto,
    también de documentos reservados."""
    from app.models.evidencia_ia import PropuestaIA

    if not actor.puede("descripcion", "escribir"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Su rol no tiene permiso para esta acción.")
    p = db.get(PropuestaIA, propuesta_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La propuesta no existe.")
    return propuestas_ia.out(p, completa=True)


@router.get("/trabajos/{trabajo_id}", responses={200: {"model": EspacioTrabajoOut, "description": "El espacio de trabajo en curso"}},
            summary="Reabrir la pantalla de un trabajo en curso")
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


FUNDAMENTO_PUBLICA = "Ley 1712 de 2014, art. 2 (principio de máxima publicidad)"


def _clasificar(db: Session, recurso, c, usuario_id) -> None:
    """Declara el acceso del Record Resource en la misma transacción de la
    publicación (Ley 1712 de 2014, arts. 18, 19 y 22)."""
    from datetime import date

    from app.servicios import derechos

    fundamento = (c.fundamento or "").strip()
    if c.acceso != "publico" and len(fundamento) < 5:
        raise descripcion.ErrorDescripcion(
            "Indique el fundamento legal de la clasificación o la reserva (por ejemplo, «Ley 1712 de 2014, art. 18, "
            "literal a: derecho a la intimidad»).")
    if c.acceso == "reservado":
        if c.vigente_hasta is None:
            raise descripcion.ErrorDescripcion("Indique hasta cuándo dura la reserva: la Ley 1712 (art. 22) no permite "
                                               "una reserva sin plazo.")
        hoy = date.today()
        if c.vigente_hasta <= hoy or c.vigente_hasta > date(hoy.year + 15, hoy.month, min(hoy.day, 28)):
            raise descripcion.ErrorDescripcion("La reserva debe vencer en el futuro y en no más de 15 años "
                                               "(Ley 1712 de 2014, art. 22).")
    derechos.declarar(db, entidad_tipo="recurso_documental", entidad_id=recurso.id, base="estatuto", acceso=c.acceso,
                      reproduccion=c.reproduccion, fundamento=fundamento or FUNDAMENTO_PUBLICA, nota=None,
                      vigente_hasta=c.vigente_hasta if c.acceso == "reservado" else None, usuario_id=usuario_id)


def _proteger(db: Session, recurso, p, usuario_id) -> None:
    """Datos personales (Ley 1581) y accesibilidad (Ley 1680) del perfil AGN."""
    if p is None:
        return
    anterior = {"datos_personales": recurso.datos_personales, "nota_accesibilidad": recurso.nota_accesibilidad}
    if p.datos_personales is not None:
        recurso.datos_personales = p.datos_personales
    if p.nota_accesibilidad is not None:
        recurso.nota_accesibilidad = p.nota_accesibilidad.strip() or None
    nuevo = {"datos_personales": recurso.datos_personales, "nota_accesibilidad": recurso.nota_accesibilidad}
    if nuevo != anterior:
        registrar(db, modulo="descripcion", accion="proteccion_datos_declarada", usuario_id=usuario_id,
                  entidad_tipo="recurso_documental", entidad_id=recurso.id,
                  detalle=f"Datos personales y accesibilidad de «{recurso.titulo}»",
                  anterior={k: v for k, v in anterior.items() if nuevo[k] != v},
                  nuevo={k: v for k, v in nuevo.items() if anterior[k] != v})


@router.post("/publicar", status_code=status.HTTP_201_CREATED, responses={201: {"model": DetalleDescripcionOut, "description": "La descripción publicada, vista interna"}},
             summary="Publicar la descripción (una sola transacción)")
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
        if datos.clasificacion is not None:
            _clasificar(db, recurso, datos.clasificacion, actor.id)
        _proteger(db, recurso, datos.proteccion, actor.id)
        descripcion.versionar(db, recurso, "publicacion", actor.id)
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
            responses={200: {"model": PaginasOut, "description": "Si se puede mostrar como imagen y cuántas páginas tiene"}},
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
            responses={200: {"content": {"image/png": {}}, "description": "Imagen PNG de la página"}},
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


@router.get("/{instanciacion_id}/previsualizar", responses={200: {"model": PrevisualizacionOut, "description": "Datos del visor"}},
            summary="Datos del visor: páginas que se pueden mostrar y texto extraído")
def previsualizar(instanciacion_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    from app.servicios import previsualizacion

    try:
        return previsualizacion.info(db, actor, instanciacion_id)
    except previsualizacion.ErrorPrevisualizacion as exc:
        raise HTTPException(exc.codigo, detail=str(exc)) from exc


@router.get("/{instanciacion_id}/previsualizar/{pagina}", responses={200: {"content": {"image/png": {}}, "description": "Imagen PNG de la página"}},
            summary="Una página como imagen PNG (nunca el original)")
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


@router.get("/publicadas/exportar", responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}, "description": "Hoja de cálculo con las descripciones publicadas"}},
            summary="Todas las descripciones publicadas del fondo, en Excel (más recientes primero)")
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


@router.get("/productividad", responses={200: {"model": ProductividadOut, "description": "Lo descrito hoy y el total del fondo"}},
            summary="Lo descrito hoy por quien consulta y el total del fondo (dato del panel consolidado)")
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


@router.get("/registros/{recurso_id}", responses={200: {"model": DetalleDescripcionOut, "description": "La descripción publicada, vista interna"}},
            summary="Descripción publicada, vista interna (con origen y confianza)")
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
             responses={201: {"model": DetalleDescripcionOut, "description": "La agrupación creada, vista interna"}},
             summary="Crear una sección, subsección, serie, subserie o expediente sin archivos propios")
def crear_agrupacion(datos: AgrupacionIn, actor: Actor = Depends(acceso_modulo("descripcion")),
                     db: Session = Depends(get_db)):
    fondo_o_404(db, datos.fondo_id)
    try:
        r = descripcion.crear_agrupacion(
            db, fondo_id=datos.fondo_id, nivel=datos.nivel, titulo=datos.titulo, incluido_en_id=datos.incluido_en_id,
            usuario_id=actor.id, codigo_referencia=datos.codigo_referencia, fechas_extremas=datos.fechas_extremas,
            alcance=datos.alcance_contenido, productor_id=datos.productor_id)
        descripcion.versionar(db, r, "agrupacion", actor.id)
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        return _error(exc)
    return descripcion.detalle(db, r)


class InclusionIn(BaseModel):
    conjunto_id: uuid.UUID


@router.post("/registros/{recurso_id}/inclusiones", status_code=status.HTTP_201_CREATED,
             responses={201: {"model": DetalleDescripcionOut, "description": "La descripción con su nueva inclusión"}},
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
             responses={201: {"model": DetalleDescripcionOut, "description": "El nuevo Record del documento individualizado"}},
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


class DatosFisicosAgn(BaseModel):
    """Esquema de Metadatos del AGN v1.4, tabla 4: estado de conservación y signatura topográfica."""
    estado_conservacion: Literal["bueno", "regular", "malo", "restaurado"] | None = None
    deposito: str | None = Field(default=None, max_length=40)
    estante: str | None = Field(default=None, max_length=40)
    entrepano: str | None = Field(default=None, max_length=40)


class OriginalFisicoIn(DatosFisicosAgn):
    soporte: str
    ubicacion: str | None = Field(default=None, max_length=300)
    caracteristicas_fisicas: str | None = Field(default=None, max_length=5000)  # ISAD-G 3.4.4


class OriginalFisicoEditarIn(DatosFisicosAgn):
    ubicacion: str | None = Field(default=None, max_length=300)
    caracteristicas_fisicas: str | None = Field(default=None, max_length=5000)


@router.get("/registros/{recurso_id}/isadg", responses={200: {"model": FichaIsadgOut, "description": "Ficha ISAD(G) con los 26 elementos"}},
            summary="Ficha ISAD(G) completa: los 26 elementos y su fuente")
def ficha_isadg(recurso_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.servicios import isadg

    recurso = db.get(RecursoDocumental, recurso_id)
    if recurso is None or (recurso.publicado_en is None and recurso.nivel != "fondo"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La descripción no existe.")
    elementos = isadg.ficha(db, recurso)
    return {"id": str(recurso.id), "titulo": recurso.titulo, "elementos": elementos,
            "con_dato": sum(1 for e in elementos if e["valor"]), "total": len(elementos)}


@router.post("/registros/{recurso_id}/original-fisico", status_code=status.HTTP_201_CREATED,
             responses={201: {"model": DetalleDescripcionOut, "description": "La descripción con el original físico registrado"}},
             summary="Registrar el original físico (papel…) como instanciación")
def original_fisico(recurso_id: uuid.UUID, datos: OriginalFisicoIn, actor: Actor = Depends(acceso_modulo("descripcion")),
                    db: Session = Depends(get_db)):
    recurso = _recurso_o_404(db, recurso_id)
    try:
        descripcion.registrar_original_fisico(db, recurso, soporte=datos.soporte, ubicacion=datos.ubicacion,
                                              usuario_id=actor.id, caracteristicas=datos.caracteristicas_fisicas,
                                              datos_agn=datos.model_dump(include=set(DatosFisicosAgn.model_fields)))
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        return _error(exc)
    return descripcion.detalle(db, recurso)


@router.patch("/registros/{recurso_id}/original-fisico/{instanciacion_id}",
              responses={200: {"model": DetalleDescripcionOut, "description": "La descripción con el original físico corregido"}},
              summary="Corregir la ubicación, la signatura o el estado de conservación del original físico")
def editar_original_fisico(recurso_id: uuid.UUID, instanciacion_id: uuid.UUID, datos: OriginalFisicoEditarIn,
                           actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    recurso = _recurso_o_404(db, recurso_id)
    inst = db.get(Instanciacion, instanciacion_id)
    try:
        if inst is None:
            raise descripcion.ErrorDescripcion("Ese original físico no existe.", 404)
        descripcion.actualizar_original_fisico(db, recurso, inst, usuario_id=actor.id, ubicacion=datos.ubicacion,
                                               caracteristicas=datos.caracteristicas_fisicas,
                                               datos_agn=datos.model_dump(include=set(DatosFisicosAgn.model_fields)))
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
             responses={201: {"model": CustodiosOut, "description": "El tramo registrado y la cadena de custodia"}},
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


@router.post("/registros/{recurso_id}/reabrir", responses={200: {"model": ReabrirOut, "description": "El trabajo de corrección y la descripción actual"}},
             summary="Reabrir una descripción publicada para corregirla")
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


@router.patch("/{recurso_id}", responses={200: {"model": DetalleDescripcionOut, "description": "La descripción corregida, vista interna"}},
              summary="Corregir una descripción publicada (queda en auditoría)")
def editar(recurso_id: uuid.UUID, datos: EditarIn, actor: Actor = Depends(acceso_modulo("descripcion")),
           db: Session = Depends(get_db)):
    recurso = _recurso_o_404(db, recurso_id)
    try:
        trabajo = descripcion.trabajo_propio(db, datos.trabajo_id, actor.id)
        cambio = descripcion.editar(
            db, recurso=recurso, trabajo=trabajo, usuario_id=actor.id, titulo=datos.titulo,
            alcance=datos.alcance_contenido, incluido_en_id=datos.incluido_en_id, anular=datos.anular_relaciones,
            quitar_forma=datos.quitar_forma_documental,
            agregar=[descripcion.EntidadConfirmada(**e.model_dump()) for e in datos.agregar_entidades],
            control=datos.control.model_dump() if datos.control else None,
            idiomas=datos.idiomas, condiciones_acceso=datos.condiciones_acceso, condiciones_uso=datos.condiciones_uso,
            precede_a_id=datos.precede_a_id, sigue_a_id=datos.sigue_a_id,
            agregar_partes=_partes_de(datos.agregar_partes), historia_archivistica=datos.historia_archivistica,
            isadg_textos=datos.isadg, escrituras=datos.escrituras)
        if datos.clasificacion is not None:
            _clasificar(db, recurso, datos.clasificacion, actor.id)
        elif datos.clasificacion_hereda:
            _volver_a_heredar(db, recurso, actor.id)
        _proteger(db, recurso, datos.proteccion, actor.id)
        descripcion.versionar(db, recurso, "edicion", actor.id, hubo_cambio=cambio)
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


# --- Versiones y atributos (RF-RIC-001 y RF-RIC-002) ----------------------------------------------


@router.get("/atributos", responses={200: {"model": list[AtributoCatalogo], "description": "Catálogo de atributos de la descripción"}},
            summary="Catálogo de atributos: tipo, cardinalidad, ISAD(G), RiC-O y procedencia")
def catalogo_atributos(actor: Actor = Depends(acceso_modulo("descripcion"))):
    from app.servicios import atributos

    return atributos.catalogo()


@router.get("/registros/{recurso_id}/versiones", responses={200: {"model": list[VersionResumen], "description": "Versiones de la descripción, la más reciente primero"}},
            summary="Versiones de la descripción, con autor y cambios")
def versiones_de(recurso_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")),
                 db: Session = Depends(get_db)):
    from app.servicios import versiones

    return versiones.historial(db, _recurso_o_404(db, recurso_id))


@router.get("/registros/{recurso_id}/versiones/{numero}", responses={200: {"model": VersionCompleta, "description": "La versión completa con su huella verificada"}},
            summary="Una versión completa (atributos y contexto)")
def version(recurso_id: uuid.UUID, numero: int, actor: Actor = Depends(acceso_modulo("descripcion")),
            db: Session = Depends(get_db)):
    from app.servicios import versiones

    try:
        v = versiones.una(db, _recurso_o_404(db, recurso_id), numero)
    except versiones.ErrorVersion as exc:
        return JSONResponse({"detail": str(exc)}, status_code=exc.codigo)
    return {"numero": v.numero, "motivo": v.motivo, "creada_en": v.creada_en.isoformat(), "huella": v.huella,
            "integra": versiones.integra(db, v), "contenido": v.contenido}


@router.post("/registros/{recurso_id}/versiones/{numero}/restaurar",
             responses={200: {"model": DetalleDescripcionOut, "description": "La descripción con la versión restaurada"}},
             summary="Volver a los atributos de una versión anterior (crea una versión nueva)")
def restaurar_version(recurso_id: uuid.UUID, numero: int, request: Request,
                      actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    from app.servicios import versiones

    recurso = _recurso_o_404(db, recurso_id)
    try:
        nueva = versiones.restaurar(db, recurso, numero, actor.id)
    except versiones.ErrorVersion as exc:
        db.rollback()
        return JSONResponse({"detail": str(exc)}, status_code=exc.codigo)
    registrar(db, modulo="descripcion", accion="descripcion_restaurada", usuario_id=actor.id,
              entidad_tipo="recurso_documental", entidad_id=recurso.id, request=request,
              detalle=f"«{recurso.titulo}»: restaurada la versión {numero} como versión {nueva.numero}",
              nuevo={"restaurada_de": numero, "version_nueva": nueva.numero})
    db.commit()
    return descripcion.detalle(db, recurso)


def _volver_a_heredar(db: Session, recurso, usuario_id) -> None:
    """Deja sin efecto la clasificación propia (no se borra: queda en la
    historia) y la descripción vuelve a regirse por la del nivel superior."""
    from app.db.base import ahora
    from app.servicios import derechos

    propia = derechos._vigente(db, recurso.id)
    if propia is None:
        return
    propia.vigente, propia.reemplazada_en = False, ahora()
    registrar(db, modulo="preservacion", accion="derechos_declarados", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=recurso.id, detalle=recurso.titulo,
              anterior={"acceso": propia.acceso, "fundamento": propia.fundamento},
              nuevo={"acceso": "hereda del nivel superior"})


# --- Consulta pública (base del catálogo del módulo 4) ------------------------------------------------

catalogo = APIRouter(prefix="/api/catalogo", tags=["Catálogo de consulta"])


@catalogo.get("/registros/{recurso_id}", responses={200: {"model": FichaPublicaOut, "description": "Ficha de consulta de la descripción"}},
              summary="Ficha de consulta de una descripción publicada")
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
