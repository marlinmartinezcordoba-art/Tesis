"""
Parametrización de la TRD y el CCD (orden de los SGDEA): versiones,
dependencias productoras, banco terminológico, matriz por dependencia y
aplicación validada en RiC-O.

- Consultar: quien lee la descripción.
- Parametrizar y aplicar: solo la administración.
"""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permisos import Actor, acceso_modulo, solo_administrador
from app.db.session import get_db
from app.models.trd import DependenciaTrd, TerminoBanco
from app.routers.fondos import fondo_o_404
from app.schemas import respuestas_trd as rt
from app.servicios import parametrizacion_trd as p

router = APIRouter(prefix="/api/trd", tags=["Parametrización de la TRD y el CCD"])
lectura = acceso_modulo("descripcion")


def _error(exc: p.ErrorTrd) -> HTTPException:
    return HTTPException(exc.codigo, detail=str(exc))


def _de_fondo(db: Session, modelo, ident: uuid.UUID, nombre: str):
    x = db.get(modelo, ident)
    if x is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{nombre} no existe.")
    return x


# --- Versiones -----------------------------------------------------------------------------------------


class VersionIn(BaseModel):
    nombre: str | None = Field(default=None, max_length=300)
    acto_aprobacion: str | None = Field(default=None, max_length=300)
    fecha_aprobacion: date | None = None
    convalidacion: str | None = Field(default=None, max_length=300)
    fecha_convalidacion: date | None = None
    vigente_desde: date | None = None
    observaciones: str | None = Field(default=None, max_length=5000)


class NuevaVersionIn(VersionIn):
    fondo_id: uuid.UUID
    copiar_vigente: bool = True


class AnularIn(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)


@router.get("/versiones", response_model=list[rt.VersionTrdOut], summary="Versiones de la TRD del fondo")
def versiones(fondo_id: uuid.UUID, _: Actor = Depends(lectura), db: Session = Depends(get_db)):
    return p.versiones(db, fondo_o_404(db, fondo_id))


@router.post("/versiones", response_model=rt.VersionTrdOut, status_code=status.HTTP_201_CREATED,
             summary="Abrir una versión de la TRD en borrador (copia de la vigente, si la hay)")
def crear_version(datos: NuevaVersionIn, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    fondo = fondo_o_404(db, datos.fondo_id)
    try:
        v = p.crear_version(db, fondo, datos.model_dump(exclude={"fondo_id", "copiar_vigente"}), actor.id,
                            datos.copiar_vigente)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return p._version_dict(db, v)


@router.patch("/versiones/{version_id}", response_model=rt.VersionTrdOut,
              summary="Corregir los datos de una versión en borrador (acto, convalidación, vigencia)")
def editar_version(version_id: uuid.UUID, datos: VersionIn, actor: Actor = Depends(solo_administrador),
                   db: Session = Depends(get_db)):
    try:
        v = p.editar_version(db, p.version_de(db, version_id), datos.model_dump(exclude_unset=True), actor.id)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return p._version_dict(db, v)


@router.post("/versiones/{version_id}/anular", response_model=rt.VersionTrdOut,
             summary="Anular una versión en borrador (no se borra)")
def anular_version(version_id: uuid.UUID, datos: AnularIn, actor: Actor = Depends(solo_administrador),
                   db: Session = Depends(get_db)):
    try:
        v = p.version_de(db, version_id)
        p.anular_version(db, v, actor.id, datos.motivo)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return p._version_dict(db, v)


def _aplicar(version_id: uuid.UUID, actor: Actor, db: Session, crear: bool) -> dict:
    try:
        v = p.version_de(db, version_id)
        informe, validacion = p.aplicar(db, v, actor.id, crear)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    aplicada = crear and validacion["conforme"]
    if crear and not aplicada:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="La versión no es conforme con RiC-O 1.1 y no se aplicó: "
                                   + "; ".join((validacion["problemas_owl"] + [r.get("mensaje") or "" for r in
                                                                               validacion["resultados_shacl"]])[:3]))
    salida = {"aplicada": aplicada, "version": p._version_dict(db, v), "informe": informe, "validacion": validacion}
    if aplicada:
        db.commit()
    else:
        db.rollback()
    return salida


@router.post("/versiones/{version_id}/validar", response_model=rt.AplicacionTrd,
             summary="Validar en RiC-O 1.1 lo que crearía aplicar la versión, sin crear nada")
def validar_version(version_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    return _aplicar(version_id, actor, db, crear=False)


@router.post("/versiones/{version_id}/aplicar", response_model=rt.AplicacionTrd,
             summary="Aplicar la versión: arma el cuadro y las reglas en RiC-O y queda vigente (solo si es conforme)")
def aplicar_version(version_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    return _aplicar(version_id, actor, db, crear=True)


class ImportarIn(BaseModel):
    filas: list[dict] = Field(min_length=1, max_length=3000)


@router.post("/versiones/{version_id}/importar", response_model=rt.ImportacionTrd,
             summary="Llenar el borrador con las filas confirmadas en la vista previa de un archivo")
def importar(version_id: uuid.UUID, datos: ImportarIn, actor: Actor = Depends(solo_administrador),
             db: Session = Depends(get_db)):
    try:
        informe = p.importar(db, p.version_de(db, version_id), datos.filas, actor.id)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return informe


# --- Dependencias --------------------------------------------------------------------------------------


class DependenciaIn(BaseModel):
    codigo: str = Field(max_length=40)
    nombre: str = Field(max_length=300)
    superior_id: uuid.UUID | None = None


class NuevaDependenciaIn(DependenciaIn):
    fondo_id: uuid.UUID


@router.get("/dependencias", response_model=list[rt.DependenciaTrdOut],
            summary="Dependencias productoras (secciones y subsecciones) del fondo")
def dependencias(fondo_id: uuid.UUID, incluir_anuladas: bool = False, _: Actor = Depends(lectura),
                 db: Session = Depends(get_db)):
    return p.dependencias(db, fondo_o_404(db, fondo_id), incluir_anuladas)


@router.post("/dependencias", response_model=rt.DependenciaTrdOut, status_code=status.HTTP_201_CREATED,
             summary="Registrar una sección o subsección")
def crear_dependencia(datos: NuevaDependenciaIn, actor: Actor = Depends(solo_administrador),
                      db: Session = Depends(get_db)):
    fondo = fondo_o_404(db, datos.fondo_id)
    try:
        d = p.guardar_dependencia(db, fondo, datos.model_dump(), actor.id)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return next(x for x in p.dependencias(db, fondo) if x["id"] == str(d.id))


@router.patch("/dependencias/{dependencia_id}", response_model=rt.DependenciaTrdOut,
              summary="Corregir el código o el nombre de una dependencia")
def editar_dependencia(dependencia_id: uuid.UUID, datos: DependenciaIn, actor: Actor = Depends(solo_administrador),
                       db: Session = Depends(get_db)):
    d = _de_fondo(db, DependenciaTrd, dependencia_id, "La dependencia")
    fondo = fondo_o_404(db, d.fondo_id)
    try:
        p.guardar_dependencia(db, fondo, datos.model_dump(), actor.id, d)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return next(x for x in p.dependencias(db, fondo) if x["id"] == str(d.id))


@router.post("/dependencias/{dependencia_id}/anular", status_code=status.HTTP_204_NO_CONTENT,
             summary="Anular una dependencia (no se borra)")
def anular_dependencia(dependencia_id: uuid.UUID, actor: Actor = Depends(solo_administrador),
                       db: Session = Depends(get_db)):
    try:
        p.anular_dependencia(db, _de_fondo(db, DependenciaTrd, dependencia_id, "La dependencia"), actor.id)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()


# --- Banco terminológico -------------------------------------------------------------------------------


class TerminoIn(BaseModel):
    codigo: str | None = Field(default=None, max_length=40)
    nombre: str = Field(max_length=300)
    definicion: str | None = Field(default=None, max_length=5000)


class NuevoTerminoIn(TerminoIn):
    fondo_id: uuid.UUID
    clase: Literal["serie", "subserie", "tipo_documental"]
    superior_id: uuid.UUID | None = None


@router.get("/banco", response_model=list[rt.TerminoBancoOut],
            summary="Banco terminológico del fondo: series, subseries y tipos documentales")
def banco(fondo_id: uuid.UUID, clase: Literal["serie", "subserie", "tipo_documental"] | None = None,
          incluir_anulados: bool = False, _: Actor = Depends(lectura), db: Session = Depends(get_db)):
    return p.banco(db, fondo_o_404(db, fondo_id), clase, incluir_anulados)


@router.post("/banco", response_model=rt.TerminoBancoOut, status_code=status.HTTP_201_CREATED,
             summary="Registrar una serie, subserie o tipo documental en el banco terminológico")
def crear_termino(datos: NuevoTerminoIn, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    fondo = fondo_o_404(db, datos.fondo_id)
    try:
        t = p.guardar_termino(db, fondo, datos.model_dump(), actor.id)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return next(x for x in p.banco(db, fondo) if x["id"] == str(t.id))


@router.patch("/banco/{termino_id}", response_model=rt.TerminoBancoOut,
              summary="Corregir un término del banco terminológico")
def editar_termino(termino_id: uuid.UUID, datos: TerminoIn, actor: Actor = Depends(solo_administrador),
                   db: Session = Depends(get_db)):
    t = _de_fondo(db, TerminoBanco, termino_id, "El término")
    fondo = fondo_o_404(db, t.fondo_id)
    try:
        p.guardar_termino(db, fondo, datos.model_dump(), actor.id, t)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return next(x for x in p.banco(db, fondo) if x["id"] == str(t.id))


@router.post("/banco/{termino_id}/anular", status_code=status.HTTP_204_NO_CONTENT,
             summary="Anular un término del banco terminológico (no se borra)")
def anular_termino(termino_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    try:
        p.anular_termino(db, _de_fondo(db, TerminoBanco, termino_id, "El término"), actor.id)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()


# --- Matriz --------------------------------------------------------------------------------------------


class FilaIn(BaseModel):
    dependencia_id: uuid.UUID
    serie_id: uuid.UUID
    subserie_id: uuid.UUID | None = None
    tipos: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    gestion: int | None = Field(default=None, ge=0, le=100)
    central: int | None = Field(default=None, ge=0, le=100)
    disposicion: Literal["ct", "e", "s", "m"] | None = None
    otras_disposiciones: list[Literal["ct", "e", "s", "m"]] = Field(default_factory=list)
    soporte: Literal["fisico", "electronico", "hibrido"] | None = None
    procedimiento: str | None = Field(default=None, max_length=5000)
    funcion: str | None = Field(default=None, max_length=300)


@router.get("/versiones/{version_id}/filas", response_model=list[rt.FilaTrdOut],
            summary="La matriz de la TRD: series y subseries por dependencia")
def filas(version_id: uuid.UUID, _: Actor = Depends(lectura), db: Session = Depends(get_db)):
    try:
        return p.filas(db, p.version_de(db, version_id))
    except p.ErrorTrd as exc:
        raise _error(exc) from exc


def _fila_out(db: Session, fila_id: uuid.UUID, version) -> dict:
    return next(x for x in p.filas(db, version) if x["id"] == str(fila_id))


@router.post("/versiones/{version_id}/filas", response_model=rt.FilaTrdOut, status_code=status.HTTP_201_CREATED,
             summary="Agregar una serie o subserie de una dependencia a la matriz del borrador")
def crear_fila(version_id: uuid.UUID, datos: FilaIn, actor: Actor = Depends(solo_administrador),
               db: Session = Depends(get_db)):
    try:
        v = p.version_de(db, version_id)
        f = p.guardar_fila(db, v, datos.model_dump(), actor.id)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return _fila_out(db, f.id, v)


@router.put("/filas/{fila_id}", response_model=rt.FilaTrdOut, summary="Corregir una fila de la matriz del borrador")
def editar_fila(fila_id: uuid.UUID, datos: FilaIn, actor: Actor = Depends(solo_administrador),
                db: Session = Depends(get_db)):
    try:
        f, v = p.fila_de(db, fila_id)
        p.guardar_fila(db, v, datos.model_dump(), actor.id, f)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return _fila_out(db, f.id, v)


@router.post("/filas/{fila_id}/anular", status_code=status.HTTP_204_NO_CONTENT,
             summary="Quitar una fila de la matriz del borrador (queda anulada)")
def anular_fila(fila_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    try:
        f, v = p.fila_de(db, fila_id)
        p.anular_fila(db, f, v, actor.id)
    except p.ErrorTrd as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
