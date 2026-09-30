"""
Módulo 3 · Vocabularios y control de autoridad.

Registro único por fondo de agentes, lugares y formas documentales. Las
entidades las crea el módulo de descripción; aquí se navegan, se revisan
las sugerencias de fusión que detecta el sistema y se fusionan (siempre
con aprobación humana, nunca solas).
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.permisos import Actor, acceso_modulo, solo_administrador
from app.db.base import ahora
from app.db.session import get_db
from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import EntidadVocabulario, SugerenciaFusion
from app.models.usuario import Usuario
from app.routers.fondos import fondo_o_404
from app.servicios import parametros, vocabulario
from app.servicios.auditoria import ip_de, registrar

router = APIRouter(prefix="/api/vocabulario", tags=["Módulo 3 · Vocabularios"],
                   dependencies=[Depends(acceso_modulo("vocabularios"))])

Clase = Literal["agente", "lugar", "forma_documental"]


class EntidadOut(BaseModel):
    id: uuid.UUID
    clase: str
    subtipo: str | None
    nombre: str
    estado: str
    conexiones: int
    fusionada_en: dict | None = None


class VerificarIn(BaseModel):
    fondo_id: uuid.UUID
    tipo: Clase
    valor: str = Field(min_length=1, max_length=300)


class FusionarIn(BaseModel):
    definitiva_id: uuid.UUID
    absorbida_id: uuid.UUID


class AprobarIn(BaseModel):
    definitiva_id: uuid.UUID | None = None  # si no se indica, queda la de más conexiones


class ParametrosFusion(BaseModel):
    similitud_pct: int
    max_conexiones: int
    horas_deteccion: int


def _entidad_out(db: Session, e: EntidadVocabulario, conexiones: int) -> EntidadOut:
    destino = db.get(EntidadVocabulario, e.fusionada_en_id) if e.fusionada_en_id else None
    return EntidadOut(id=e.id, clase=e.clase, subtipo=e.subtipo, nombre=e.nombre, estado=e.estado, conexiones=conexiones,
                      fusionada_en={"id": str(destino.id), "nombre": destino.nombre} if destino else None)


def _entidad_o_404(db: Session, entidad_id: uuid.UUID) -> EntidadVocabulario:
    e = db.get(EntidadVocabulario, entidad_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La entidad no existe.")
    return e


# --- Navegación -----------------------------------------------------------------------------


@router.get("", response_model=list[EntidadOut], summary="Vocabulario del fondo, con búsqueda y filtro por tipo")
def listar(fondo_id: uuid.UUID, clase: Clase | None = None, q: str | None = None,
           estado: Literal["activa", "fusionada"] = "activa",
           orden: Literal["conexiones_desc", "conexiones_asc", "nombre"] = "conexiones_desc",
           db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    consulta = select(EntidadVocabulario).where(EntidadVocabulario.fondo_id == fondo_id, EntidadVocabulario.estado == estado)
    if clase:
        consulta = consulta.where(EntidadVocabulario.clase == clase)
    if q and q.strip():
        buscado = vocabulario.normalizar(q)
        consulta = consulta.where(or_(EntidadVocabulario.nombre_normalizado.contains(buscado),
                                      func.similarity(EntidadVocabulario.nombre_normalizado, buscado) >= 0.3))
    filas = db.scalars(consulta.limit(2000)).all()
    conexiones = vocabulario.conexiones_de(db, [e.id for e in filas])
    if orden == "nombre":
        filas = sorted(filas, key=lambda e: e.nombre_normalizado)
    else:
        filas = sorted(filas, key=lambda e: (conexiones[e.id] * (-1 if orden == "conexiones_desc" else 1), e.nombre_normalizado))
    return [_entidad_out(db, e, conexiones[e.id]) for e in filas]


@router.get("/sugerencias-fusion", summary="Candidatos a fusión detectados, pendientes de revisión")
def sugerencias(fondo_id: uuid.UUID, db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    filas = db.scalars(select(SugerenciaFusion).where(SugerenciaFusion.fondo_id == fondo_id,
                                                      SugerenciaFusion.estado == "pendiente")
                       .order_by(SugerenciaFusion.similitud.desc())).all()
    ids = [i for s in filas for i in (s.entidad_a_id, s.entidad_b_id)]
    conexiones = vocabulario.conexiones_de(db, ids)
    return [{"id": str(s.id), "clase": s.clase, "similitud": s.similitud, "creada_en": s.creada_en,
             "entidades": [_entidad_out(db, db.get(EntidadVocabulario, i), conexiones[i]).model_dump(mode="json")
                           for i in (s.entidad_a_id, s.entidad_b_id)]} for s in filas]


@router.get("/parametros", response_model=ParametrosFusion, summary="Criterios de la detección de candidatos")
def ver_parametros(db: Session = Depends(get_db)):
    return ParametrosFusion(similitud_pct=parametros.leer(db, "fusion_similitud_pct"),
                            max_conexiones=parametros.leer(db, "fusion_max_conexiones"),
                            horas_deteccion=parametros.leer(db, "fusion_horas_deteccion"))


@router.put("/parametros", response_model=ParametrosFusion, summary="Cambiar los criterios (solo administrador)")
def cambiar_parametros(datos: ParametrosFusion, request: Request, actor: Actor = Depends(solo_administrador),
                       db: Session = Depends(get_db)):
    try:
        for clave, valor in (("fusion_similitud_pct", datos.similitud_pct), ("fusion_max_conexiones", datos.max_conexiones),
                             ("fusion_horas_deteccion", datos.horas_deteccion)):
            parametros.cambiar(db, clave, valor, actor.id, "vocabularios", ip=ip_de(request))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return ver_parametros(db)


@router.get("/{entidad_id}", summary="Detalle: documentos conectados e historial de fusiones")
def detalle(entidad_id: uuid.UUID, db: Session = Depends(get_db)):
    e = _entidad_o_404(db, entidad_id)
    documentos = vocabulario.documentos_conectados(db, e.id)
    absorbidas = db.scalars(select(EntidadVocabulario).where(EntidadVocabulario.fusionada_en_id == e.id)
                            .order_by(EntidadVocabulario.nombre)).all()
    eventos = db.scalars(select(RegistroAuditoria).where(
        RegistroAuditoria.accion == "fusion_vocabulario",
        or_(RegistroAuditoria.entidad_id == str(e.id),
            *[RegistroAuditoria.entidad_id == str(a.id) for a in absorbidas],
            RegistroAuditoria.valor_anterior["absorbida"]["id"].astext == str(e.id)))
        .order_by(RegistroAuditoria.fecha.desc())).all()
    nombres = dict(db.execute(select(Usuario.id, Usuario.nombre)).all())
    return {
        "entidad": _entidad_out(db, e, len(documentos)).model_dump(mode="json"),
        "creada_en": e.creado_en,
        "documentos": [{"id": str(d.id), "titulo": d.titulo, "nivel": d.nivel} for d in documentos],
        # Documentos que la citaban antes de fusionarse en otra (si es una fusionada).
        "documentos_historicos": [{"id": str(d.id), "titulo": d.titulo, "nivel": d.nivel}
                                  for d in vocabulario.documentos_conectados(db, e.id, historicos=True)],
        "absorbidas": [{"id": str(a.id), "nombre": a.nombre} for a in absorbidas],
        "historial": [{"fecha": ev.fecha, "por": nombres.get(ev.usuario_id), "detalle": ev.detalle,
                       "relaciones_movidas": (ev.valor_nuevo or {}).get("relaciones_movidas"),
                       "origen": (ev.valor_nuevo or {}).get("origen")} for ev in eventos],
    }


@router.post("/verificar", summary="Servicio de verificación por similitud (el que usa descripción)")
def verificar(datos: VerificarIn, db: Session = Depends(get_db)):
    fondo_o_404(db, datos.fondo_id)
    return [c.__dict__ for c in vocabulario.verificar(db, datos.fondo_id, datos.tipo, datos.valor)]


# --- Fusión -----------------------------------------------------------------------------------


@router.post("/detectar", summary="Buscar candidatos a fusión ahora, sin esperar la búsqueda periódica")
def detectar(fondo_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("vocabularios")), db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    nuevas = vocabulario.detectar_candidatos(db, fondo_id)
    db.commit()
    return {"nuevas": nuevas}


@router.post("/sugerencias-fusion/{sugerencia_id}/aprobar", summary="Aprobar una sugerencia: ejecuta la fusión")
def aprobar(sugerencia_id: uuid.UUID, datos: AprobarIn, request: Request,
            actor: Actor = Depends(acceso_modulo("vocabularios")), db: Session = Depends(get_db)):
    s = db.scalar(select(SugerenciaFusion).where(SugerenciaFusion.id == sugerencia_id).with_for_update())
    if s is None or s.estado != "pendiente":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="La sugerencia ya no está pendiente.")
    a, b = db.get(EntidadVocabulario, s.entidad_a_id), db.get(EntidadVocabulario, s.entidad_b_id)
    if datos.definitiva_id not in (None, a.id, b.id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La definitiva debe ser una de las dos entidades.")
    if datos.definitiva_id is None:
        conexiones = vocabulario.conexiones_de(db, [a.id, b.id])
        definitiva = a if conexiones[a.id] >= conexiones[b.id] else b
    else:
        definitiva = a if datos.definitiva_id == a.id else b
    absorbida = b if definitiva is a else a
    try:
        movidas = vocabulario.fusionar(db, definitiva=definitiva, absorbida=absorbida, usuario_id=actor.id,
                                       sugerencia=s, ip=ip_de(request))
    except vocabulario.ErrorFusion as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return {"definitiva": str(definitiva.id), "absorbida": str(absorbida.id), "relaciones_movidas": movidas}


@router.post("/sugerencias-fusion/{sugerencia_id}/descartar", summary="Descartar una sugerencia (no cambia nada)")
def descartar(sugerencia_id: uuid.UUID, request: Request, actor: Actor = Depends(acceso_modulo("vocabularios")),
              db: Session = Depends(get_db)):
    s = db.get(SugerenciaFusion, sugerencia_id)
    if s is None or s.estado != "pendiente":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="La sugerencia ya no está pendiente.")
    s.estado, s.resuelta_en, s.resuelta_por_id = "descartada", ahora(), actor.id
    registrar(db, modulo="vocabularios", accion="sugerencia_fusion_descartada", usuario_id=actor.id,
              entidad_tipo="sugerencia_fusion", entidad_id=s.id, request=request,
              detalle=f"Son distintas: {db.get(EntidadVocabulario, s.entidad_a_id).nombre} / "
                      f"{db.get(EntidadVocabulario, s.entidad_b_id).nombre}")
    db.commit()
    return {"estado": "descartada"}


@router.post("/fusionar", summary="Fusión manual iniciada desde el detalle")
def fusionar(datos: FusionarIn, request: Request, actor: Actor = Depends(acceso_modulo("vocabularios")),
             db: Session = Depends(get_db)):
    definitiva, absorbida = _entidad_o_404(db, datos.definitiva_id), _entidad_o_404(db, datos.absorbida_id)
    try:
        movidas = vocabulario.fusionar(db, definitiva=definitiva, absorbida=absorbida, usuario_id=actor.id, ip=ip_de(request))
    except vocabulario.ErrorFusion as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return {"definitiva": str(definitiva.id), "absorbida": str(absorbida.id), "relaciones_movidas": movidas}
