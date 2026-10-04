"""
Módulo transversal de auditoría: consulta del registro.

- Trazabilidad por entidad y trazabilidad propia: roles con auditoría
  «propia» (solo sus acciones) o «todo».
- Panel consolidado semanal y desglose por persona: solo quien ve toda la
  auditoría (el administrador, y el rol al que él le dé ese permiso).
- Decisiones de IA, hallazgos de conformidad y etiquetas de versión de la
  instrucción: solo administrador (prompt v7).

El registro no se escribe por HTTP: los módulos llaman a
servicios/auditoria.registrar() dentro del mismo proceso. Ninguna ruta de
este archivo modifica ni borra eventos. La única que agrega uno es la
constancia de revisión del consolidado semanal (NDSA, Control, nivel 4;
hallazgo PRE-13): un evento nuevo, no un cambio de los existentes.
"""

import uuid
from datetime import date

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permisos import Actor, acceso_modulo, sin_permiso, solo_administrador, usuario_actual
from app.db.base import ahora
from app.db.session import get_db
from app.models.hallazgo import COMPONENTES, HallazgoConformidad
from app.models.usuario import Usuario
from app.servicios import decisiones_ia, hallazgos, trazabilidad
from app.servicios.auditoria import ip_de, registrar

router = APIRouter(prefix="/api/auditoria", tags=["Auditoría (transversal)"],
                   dependencies=[Depends(acceso_modulo("auditoria"))])
# Lo único que se escribe en este módulo no es el registro sino los
# hallazgos de conformidad y las etiquetas de versión (prompt v7): solo el
# administrador, fuera de la regla «la auditoría solo se lee».
gestion = APIRouter(prefix="/api/auditoria", tags=["Auditoría (transversal)"],
                    dependencies=[Depends(solo_administrador)])


def ve_todo(actor: Actor = Depends(usuario_actual)) -> Actor:
    if not actor.ve_toda_la_auditoria:
        raise sin_permiso()
    return actor


def _solo_de(actor: Actor) -> uuid.UUID | None:
    """Principio de visibilidad: quien no ve toda la auditoría solo ve lo
    que hizo él mismo, en cualquier consulta."""
    return None if actor.ve_toda_la_auditoria else actor.id


@router.get("/acciones", summary="Tipos de acción disponibles para filtrar")
def acciones(actor: Actor = Depends(usuario_actual), db: Session = Depends(get_db)):
    return trazabilidad.acciones_de(db, _solo_de(actor))


@router.get("/mi-trazabilidad", summary="Acciones del usuario autenticado, filtrables por tipo, módulo y fechas")
def mi_trazabilidad(accion: str | None = None, modulo: str | None = None, desde: date | None = None,
                    hasta: date | None = None, antes_de: int | None = None, limite: int = Query(200, ge=1, le=500),
                    actor: Actor = Depends(usuario_actual), db: Session = Depends(get_db)):
    if desde and hasta and desde > hasta:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La fecha inicial es posterior a la final.")
    return trazabilidad.propia(db, actor.id, accion=accion, modulo=modulo, desde=desde, hasta=hasta, antes_de=antes_de,
                               limite=limite)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(contenido: bytes, nombre: str) -> Response:
    return Response(contenido, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/trazabilidad/exportar", summary="Toda la trazabilidad propia que cumple los filtros, en Excel")
def mi_trazabilidad_xlsx(accion: str | None = None, modulo: str | None = None, desde: date | None = None,
                         hasta: date | None = None, actor: Actor = Depends(usuario_actual), db: Session = Depends(get_db)):
    if desde and hasta and desde > hasta:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La fecha inicial es posterior a la final.")
    return _xlsx(trazabilidad.hoja_propia(db, actor.id, accion=accion, modulo=modulo, desde=desde, hasta=hasta),
                 "mi-trazabilidad.xlsx")


@router.get("/entidad/{entidad_id}", summary="Historial de auditoría de una entidad")
def entidad(entidad_id: str, tipo: str = Query(..., max_length=60), actor: Actor = Depends(usuario_actual),
            db: Session = Depends(get_db)):
    if tipo not in trazabilidad.MODULO_DE_ENTIDAD:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tipo de entidad desconocido.")
    modulo = trazabilidad.MODULO_DE_ENTIDAD[tipo]
    # Hay que tener acceso a la entidad (su módulo) además de a la auditoría.
    if modulo and not (actor.puede(modulo) or (tipo == "instanciacion" and actor.puede("preservacion"))):
        raise sin_permiso()
    return {"entidad_tipo": tipo, "entidad_id": entidad_id, "solo_propias": not actor.ve_toda_la_auditoria,
            "eventos": trazabilidad.entidad(db, tipo, entidad_id[:64], solo_de=_solo_de(actor))}


def _dia(semana: date | None) -> date:
    return semana or ahora().astimezone(trazabilidad._zona()).date()


@router.get("/consolidado", summary="Panel semanal por persona: días, horas conectadas y acciones")
def consolidado(semana: date | None = None, _: Actor = Depends(ve_todo), db: Session = Depends(get_db)):
    datos = trazabilidad.consolidado(db, _dia(semana))
    return datos | {"revisiones": trazabilidad.revisiones_de(db, trazabilidad.lunes_de(_dia(semana)))}


class RevisionIn(BaseModel):
    semana: date | None = None
    nota: str | None = Field(default=None, max_length=1000)


def _revisor_del_registro(actor: Actor = Depends(ve_todo)) -> Actor:
    if not actor.puede("auditoria", "leer"):
        raise sin_permiso()
    return actor


# La constancia de revisión no escribe en el módulo (que es de solo lectura
# para todos los roles): la deja quien lee todo el registro.
revision = APIRouter(prefix="/api/auditoria", tags=["Auditoría (transversal)"],
                     dependencies=[Depends(_revisor_del_registro)])


@revision.post("/consolidado/revisado", summary="Dejar constancia de que se revisó el registro de la semana")
def marcar_revisado(datos: RevisionIn, request: Request, actor: Actor = Depends(_revisor_del_registro),
                    db: Session = Depends(get_db)):
    from app.servicios.auditoria import verificar_cadena

    lunes = trazabilidad.lunes_de(_dia(datos.semana))
    # Quien revisa deja constancia también del sello de la cadena en ese
    # momento: si después alguien rehace la cadena entera, el sello anotado
    # (y exportado fuera del sistema) ya no coincide.
    cadena = verificar_cadena(db)
    registrar(db, modulo="auditoria", accion="consolidado_revisado", usuario_id=actor.id, entidad_tipo="semana",
              entidad_id=lunes.isoformat(), ip=ip_de(request), detalle=f"Semana del {lunes.isoformat()}",
              nuevo={"semana": lunes.isoformat(), "nota": datos.nota, "cadena_integra": cadena["integra"],
                     "sello": cadena["sello"]})
    db.commit()
    return {"revisiones": trazabilidad.revisiones_de(db, lunes)}


@router.get("/cadena", summary="Verificar la cadena de huellas del registro de auditoría y obtener su sello")
def cadena(_: Actor = Depends(ve_todo), db: Session = Depends(get_db)):
    from app.servicios.auditoria import verificar_cadena

    return verificar_cadena(db)


@router.get("/panel-consolidado/exportar", summary="La semana seleccionada completa (personas y sesiones), en Excel")
def consolidado_xlsx(semana: date | None = None, _: Actor = Depends(ve_todo), db: Session = Depends(get_db)):
    dia = _dia(semana)
    return _xlsx(trazabilidad.hoja_consolidado(db, dia), f"panel-consolidado-{trazabilidad.lunes_de(dia).isoformat()}.xlsx")


@router.get("/consolidado/{usuario_id}", summary="Desglose sesión por sesión de una persona en la semana")
def desglose(usuario_id: uuid.UUID, semana: date | None = None, _: Actor = Depends(ve_todo),
             db: Session = Depends(get_db)):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La persona no existe.")
    return trazabilidad.desglose(db, usuario, _dia(semana))


# --- Decisiones de validación asistida por IA (solo administrador) -----------------------------------

TipoDecision = Literal["agente", "lugar", "fecha", "forma_documental", "actividad", "tipo_actividad", "mandato",
                       "titulo", "alcance", "idioma"]
Decision = Literal["aceptada", "corregida", "rechazada", "agregada"]


def _filtros(tipo, decision, desde, hasta, fondo_id) -> dict:
    if desde and hasta and desde > hasta:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La fecha inicial es posterior a la final.")
    return {"tipo": tipo, "decision": decision, "desde": desde, "hasta": hasta, "fondo_id": fondo_id}


@router.get("/decisiones-ia", summary="Cada propuesta del motor frente a lo que quedó confirmado")
def decisiones(tipo: TipoDecision | None = None, decision: Decision | None = None, desde: date | None = None,
               hasta: date | None = None, fondo_id: uuid.UUID | None = None, limite: int = Query(500, ge=1, le=500),
               _: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    return decisiones_ia.consultar(db, limite=limite, **_filtros(tipo, decision, desde, hasta, fondo_id))


@router.get("/decisiones-ia/exportar", summary="Todas las decisiones que cumplen los filtros, con los conteos, en Excel")
@router.get("/decisiones-ia/hoja-de-calculo", summary="Las mismas decisiones en una hoja de cálculo (evaluación)")
def decisiones_xlsx(tipo: TipoDecision | None = None, decision: Decision | None = None, desde: date | None = None,
                    hasta: date | None = None, fondo_id: uuid.UUID | None = None,
                    _: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    contenido = decisiones_ia.hoja_de_calculo(db, **_filtros(tipo, decision, desde, hasta, fondo_id))
    return Response(contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="decisiones-ia.xlsx"'})


# --- Hallazgos de conformidad (solo administrador) ---------------------------------------------

EstadoHallazgo = Literal["abierto", "en_correccion", "cerrado"]
Componente = Literal[COMPONENTES]  # type: ignore[valid-type]


class HallazgoIn(BaseModel):
    titulo: str = Field(min_length=3, max_length=300)
    descripcion: str = Field(min_length=3, max_length=5000)
    componentes: list[Componente] = Field(min_length=1)
    accion: str | None = Field(default=None, max_length=5000)


class HallazgoCambio(BaseModel):
    """Del hallazgo creado solo cambian estos campos (prompt v7, §8)."""
    estado: EstadoHallazgo | None = None
    cerrado_en: date | None = None
    accion: str | None = Field(default=None, max_length=5000)

    model_config = {"extra": "forbid"}  # el título y la descripción originales no se editan


def _error(exc: hallazgos.ErrorHallazgo) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/hallazgos", summary="Hallazgos de conformidad con RiC, filtrables por estado y componente")
def ver_hallazgos(estado: EstadoHallazgo | None = None, componente: Componente | None = None,
                  _: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    return hallazgos.listar(db, estado=estado, componente=componente)


@router.get("/hallazgos/hoja-de-calculo", summary="Los mismos hallazgos, con los mismos filtros, en una hoja de cálculo")
def hallazgos_xlsx(estado: EstadoHallazgo | None = None, componente: Componente | None = None,
                   _: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    return Response(hallazgos.hoja_de_calculo(db, estado=estado, componente=componente),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="hallazgos-de-conformidad.xlsx"'})


@gestion.post("/hallazgos", status_code=status.HTTP_201_CREATED, summary="Registrar un hallazgo de conformidad")
def crear_hallazgo(datos: HallazgoIn, request: Request, actor: Actor = Depends(solo_administrador),
                   db: Session = Depends(get_db)):
    try:
        h = hallazgos.crear(db, titulo=datos.titulo, descripcion=datos.descripcion, componentes=datos.componentes,
                            accion=datos.accion, usuario_id=actor.id, ip=ip_de(request))
    except hallazgos.ErrorHallazgo as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return hallazgos.out(h)


@gestion.patch("/hallazgos/{hallazgo_id}", summary="Cambiar el estado, la fecha de cierre o la acción de un hallazgo")
def cambiar_hallazgo(hallazgo_id: uuid.UUID, datos: HallazgoCambio, request: Request,
                     actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    h = db.get(HallazgoConformidad, hallazgo_id)
    if h is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El hallazgo no existe.")
    try:
        hallazgos.actualizar(db, h, estado=datos.estado, accion=datos.accion, cerrado_en=datos.cerrado_en,
                             usuario_id=actor.id, ip=ip_de(request))
    except hallazgos.ErrorHallazgo as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return hallazgos.out(h)


# --- Versiones de la instrucción del motor (etiqueta legible opcional) -----------------------------


class EtiquetaIn(BaseModel):
    etiqueta: str = Field(min_length=1, max_length=40)
    nota: str | None = Field(default=None, max_length=300)


@router.get("/versiones-prompt", summary="Versiones de la instrucción presentes en las decisiones, con su etiqueta")
def ver_versiones(_: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    return hallazgos.versiones(db)


@gestion.put("/versiones-prompt/{version}", summary="Poner o cambiar la etiqueta legible de una versión")
def etiquetar_version(version: str, datos: EtiquetaIn, request: Request, actor: Actor = Depends(solo_administrador),
                      db: Session = Depends(get_db)):
    try:
        hallazgos.etiquetar(db, version, datos.etiqueta, datos.nota, actor.id, ip=ip_de(request))
    except hallazgos.ErrorHallazgo as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return hallazgos.versiones(db)
