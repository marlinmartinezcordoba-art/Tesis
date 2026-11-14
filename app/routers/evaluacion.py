"""
Evaluación ciega del motor frente a archivistas.

- Administración (solo administrador): crear la evaluación, agregar
  documentos, generar las propuestas del motor, iniciarla, cerrarla, ver
  los resultados y anular una anotación.
- Archivistas (permiso de escribir en Descripción): sus tareas, describir
  a ciegas, describir con la propuesta (asistida), y calificar la propuesta.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permisos import Actor, sin_permiso, solo_administrador, usuario_actual
from app.db.session import get_db
from app.models.evaluacion import Anotacion, Evaluacion
from app.routers.fondos import fondo_o_404
from app.schemas import respuestas_evaluacion as re_
from app.servicios import evaluacion
from app.servicios.auditoria import registrar

router = APIRouter(prefix="/api/evaluacion", tags=["Evaluación ciega"])


def evaluador(actor: Actor = Depends(usuario_actual)) -> Actor:
    if not (actor.es_administrador or actor.puede("descripcion", "escribir")):
        raise sin_permiso()
    return actor


def _error(exc: evaluacion.ErrorEvaluacion) -> HTTPException:
    return HTTPException(exc.codigo, detail=str(exc))


def _ev(db: Session, evaluacion_id: uuid.UUID) -> Evaluacion:
    try:
        return evaluacion._evaluacion(db, evaluacion_id)
    except evaluacion.ErrorEvaluacion as exc:
        raise _error(exc) from exc


class EvaluacionIn(BaseModel):
    fondo_id: uuid.UUID
    nombre: str = Field(min_length=3, max_length=200)
    protocolo: str | None = Field(default=None, max_length=10000)
    umbral_similitud: float = Field(default=0.85, ge=0.5, le=1)


class DocumentosIn(BaseModel):
    instanciacion_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    # Documentos de la prueba piloto: ensayan el protocolo y no entran en los resultados.
    piloto: bool = False


class EstadoIn(BaseModel):
    estado: Literal["en_curso", "cerrada"]


class AnotarIn(BaseModel):
    condicion: Literal["ciega", "asistida", "adjudicada"]


class DatosIn(BaseModel):
    titulo: str | None = Field(default=None, max_length=300)
    alcance: str | None = Field(default=None, max_length=5000)
    entidades: list[dict] = Field(default_factory=list, max_length=200)
    # Tripletas RiC: {origen, propiedad, destino}; «documento» es el documento que se describe.
    relaciones: list[dict] | None = Field(default=None, max_length=400)
    # Solo en la referencia adjudicada: cómo se resolvieron las diferencias entre las descripciones ciegas.
    justificacion: str | None = Field(default=None, max_length=20000)
    enviar: bool = False


class CriterioIn(BaseModel):
    """Criterio de comparabilidad (objetivo 3), fijado antes de iniciar."""
    margen_f: float = Field(default=0.10, ge=0, le=0.5)
    minimo_casos: int = Field(default=10, ge=1, le=1000)
    rubrica_minima: float = Field(default=3.0, ge=1, le=5)
    conformidad_asistida: float = Field(default=1.0, ge=0, le=1)


class ClasificacionIn(BaseModel):
    tipo_error: str = Field(min_length=3, max_length=20)
    ronda: Literal["individual", "consenso"] = "individual"
    nota: str | None = Field(default=None, max_length=2000)


class CalificacionIn(BaseModel):
    exactitud: int = Field(ge=1, le=5)
    completitud: int = Field(ge=1, le=5)
    pertinencia: int = Field(ge=1, le=5)


def _hecho(db: Session, funcion, *args, **kwargs):
    try:
        resultado = funcion(*args, **kwargs)
    except evaluacion.ErrorEvaluacion as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return resultado


@router.get("", responses={200: {"model": list[re_.EvaluacionOut], "description": "Evaluaciones del fondo"}},
    summary="Evaluaciones: todas para la administración; las en curso para quien anota")
def listar(fondo_id: uuid.UUID, actor: Actor = Depends(evaluador), db: Session = Depends(get_db)):
    consulta = select(Evaluacion).where(Evaluacion.fondo_id == fondo_id).order_by(Evaluacion.creada_en.desc())
    if not actor.es_administrador:  # quien anota ve solo las evaluaciones en curso en que está registrada
        from app.models.evaluacion import Participante

        consulta = consulta.where(Evaluacion.estado == "en_curso", Evaluacion.id.in_(
            select(Participante.evaluacion_id).where(Participante.usuario_id == actor.id,
                                                     Participante.retirado_en.is_(None))))
    return [evaluacion.evaluacion_out(db, e) for e in db.scalars(consulta).all()]


@router.get("/propiedades", responses={200: {"model": list[re_.PropiedadRic], "description": "Propiedades de RiC-O disponibles"}},
    summary="Las relaciones de RiC-O con que se describe, y qué extremos admite cada una")
def propiedades(actor: Actor = Depends(evaluador)):
    from app.servicios import evaluacion_ric

    return evaluacion_ric.catalogo()


@router.post("", status_code=status.HTTP_201_CREATED, responses={201: {"model": re_.EvaluacionOut, "description": "Evaluación creada"}},
    summary="Crear una evaluación")
def crear(datos: EvaluacionIn, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    fondo_o_404(db, datos.fondo_id)
    ev = _hecho(db, evaluacion.crear, db, fondo_id=datos.fondo_id, nombre=datos.nombre, protocolo=datos.protocolo,
                umbral=datos.umbral_similitud, usuario_id=actor.id)
    return evaluacion.evaluacion_out(db, ev)


@router.post("/{evaluacion_id}/documentos", responses={200: {"model": re_.EvaluacionOut, "description": "Evaluación con los documentos agregados"}},
    summary="Agregar documentos aún no descritos")
def documentos(evaluacion_id: uuid.UUID, datos: DocumentosIn, actor: Actor = Depends(solo_administrador),
               db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    _hecho(db, evaluacion.agregar_documentos, db, ev, datos.instanciacion_ids, actor.id, datos.piloto)
    return evaluacion.evaluacion_out(db, ev)


@router.post("/{evaluacion_id}/propuestas", responses={200: {"model": re_.PropuestasGeneradasOut, "description": "Propuestas generadas y avisos"}},
    summary="Generar, sin mostrarlas, las propuestas del motor")
def propuestas(evaluacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    """Empieza a generarlas en segundo plano (cada documento puede tardar minutos con dos motores)
    y responde de una vez; el avance se consulta con GET /{id}/propuestas."""
    from app.servicios import evaluacion_generacion

    from app.core.config import settings

    ev = _ev(db, evaluacion_id)
    if not settings.propuestas_en_segundo_plano:
        resultado = _hecho(db, evaluacion.generar_propuestas, db, ev, actor.id)
        return resultado | {"generando": False, "evaluacion": evaluacion.evaluacion_out(db, ev)}
    if ev.estado != "preparacion":
        raise _error(evaluacion.ErrorEvaluacion("Las propuestas se generan antes de iniciar la evaluación.", 409))
    out = evaluacion.evaluacion_out(db, ev)
    estado = evaluacion_generacion.empezar(ev.id, actor.id, out.get("documentos") or 0)
    return {"generadas": estado["hechas"], "avisos": estado["avisos"], "generando": estado["estado"] == "generando",
            "total": estado["total"], "evaluacion": out}


@router.get("/{evaluacion_id}/propuestas", responses={200: {"model": re_.PropuestasGeneradasOut,
                                                               "description": "Avance de la generación"}},
            summary="Avance de la generación de propuestas: cuántas van y cuántas faltan")
def avance_propuestas(evaluacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    from app.servicios import evaluacion_generacion

    ev = _ev(db, evaluacion_id)
    e = evaluacion_generacion.avance(ev.id) or {"estado": "listo", "hechas": 0, "total": 0, "avisos": [], "error": None}
    return {"generadas": e["hechas"], "avisos": e["avisos"], "generando": e["estado"] == "generando",
            "total": e["total"], "error": e.get("error"), "evaluacion": evaluacion.evaluacion_out(db, ev)}


@router.put("/{evaluacion_id}/criterio", responses={200: {"model": re_.EvaluacionOut, "description": "Evaluación con su criterio"}},
    summary="Fijar el criterio de comparabilidad (solo en preparación)")
def criterio(evaluacion_id: uuid.UUID, datos: CriterioIn, actor: Actor = Depends(solo_administrador),
             db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    _hecho(db, evaluacion.fijar_criterio, db, ev, datos.model_dump(), actor.id)
    return evaluacion.evaluacion_out(db, ev)


@router.post("/{evaluacion_id}/estado", responses={200: {"model": re_.EvaluacionOut, "description": "Evaluación con su nuevo estado"}},
    summary="Iniciar o cerrar la evaluación")
def estado(evaluacion_id: uuid.UUID, datos: EstadoIn, actor: Actor = Depends(solo_administrador),
           db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    _hecho(db, evaluacion.cambiar_estado, db, ev, datos.estado, actor.id)
    return evaluacion.evaluacion_out(db, ev)


@router.get("/{evaluacion_id}/tareas", responses={200: {"model": re_.TareasOut, "description": "Tareas de la persona en la evaluación"}},
    summary="Los documentos de la evaluación y lo que la persona ya hizo")
def tareas(evaluacion_id: uuid.UUID, actor: Actor = Depends(evaluador), db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    return {"evaluacion": evaluacion.evaluacion_out(db, ev), "tareas": evaluacion.tareas(db, ev, actor.id)}


@router.post("/{evaluacion_id}/documentos/{inst_id}/anotar", responses={200: {"model": re_.AnotacionOut, "description": "Anotación iniciada o retomada"}},
    summary="Empezar (o retomar) una descripción ciega o asistida")
def anotar(evaluacion_id: uuid.UUID, inst_id: uuid.UUID, datos: AnotarIn, actor: Actor = Depends(evaluador),
           db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    a = _hecho(db, evaluacion.iniciar_anotacion, db, ev, inst_id, datos.condicion, actor.id)
    return evaluacion.anotacion_out(db, a)


@router.put("/anotaciones/{anotacion_id}", responses={200: {"model": re_.AnotacionOut, "description": "Anotación guardada o enviada"}},
    summary="Guardar o enviar una descripción")
def guardar(anotacion_id: uuid.UUID, datos: DatosIn, actor: Actor = Depends(evaluador), db: Session = Depends(get_db)):
    a = db.get(Anotacion, anotacion_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La anotación no existe.")
    a = _hecho(db, evaluacion.guardar, db, a, datos.model_dump(exclude={"enviar", "justificacion"}, exclude_none=True),
               actor.id, datos.enviar, datos.justificacion)
    return evaluacion.anotacion_out(db, a)


@router.post("/{evaluacion_id}/documentos/{inst_id}/propuesta",
             responses={200: {"model": re_.DescripcionEvaluada, "description": "Propuesta del motor para calificarla"}},
    summary="Ver la propuesta del motor para calificarla (desde ahí ya no se describe a ciegas)")
def ver_propuesta(evaluacion_id: uuid.UUID, inst_id: uuid.UUID, actor: Actor = Depends(evaluador),
                  db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    return _hecho(db, evaluacion.ver_propuesta, db, ev, inst_id, actor.id)


@router.put("/{evaluacion_id}/documentos/{inst_id}/calificacion", responses={200: {"model": re_.CalificadoOut, "description": "Calificación registrada"}},
    summary="Calificar la propuesta con la rúbrica 1–5")
def calificar(evaluacion_id: uuid.UUID, inst_id: uuid.UUID, datos: CalificacionIn, actor: Actor = Depends(evaluador),
              db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    _hecho(db, evaluacion.calificar, db, ev, inst_id, datos.model_dump(), actor.id)
    return {"calificado": True}


@router.post("/anotaciones/{anotacion_id}/anular", responses={200: {"model": re_.EstadoAnulacionOut, "description": "Anotación anulada"}},
    summary="Anular una anotación (no se borra)")
def anular(anotacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    a = db.get(Anotacion, anotacion_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La anotación no existe.")
    anterior, a.estado = a.estado, "anulada"
    registrar(db, modulo="evaluacion", accion="anotacion_anulada", usuario_id=actor.id, entidad_tipo="instanciacion",
              entidad_id=a.instanciacion_id, anterior={"estado": anterior},
              nuevo={"estado": "anulada", "anotacion_id": str(a.id), "condicion": a.condicion})
    db.commit()
    return {"estado": a.estado}


@router.get("/{evaluacion_id}/resultados", responses={200: {"model": re_.ResultadosOut, "description": "Resultados de la evaluación"}},
    summary="Precisión, exhaustividad y F1 de entidades y relaciones RiC, conformidad RiC-O, acuerdo, tiempos y rúbrica")
def resultados(evaluacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    return _hecho(db, evaluacion.resultados, db, ev, actor.id)


@router.get("/{evaluacion_id}/desacuerdos", responses={200: {"model": re_.DesacuerdosOut, "description": "Desacuerdos entre el motor y las referencias ciegas"}},
    summary="Cada diferencia entre el motor y una referencia ciega, para clasificarla con la taxonomía de errores")
def desacuerdos(evaluacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    return _hecho(db, evaluacion.desacuerdos, db, ev, actor.id)


@router.put("/{evaluacion_id}/desacuerdos/{clave}", responses={200: {"model": re_.ClasificadoOut, "description": "Clasificación registrada"}},
    summary="Clasificar un desacuerdo (individual o, si dos difieren, por consenso)")
def clasificar(evaluacion_id: uuid.UUID, clave: str, datos: ClasificacionIn, actor: Actor = Depends(solo_administrador),
               db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    _hecho(db, evaluacion.clasificar_desacuerdo, db, ev, clave, datos.tipo_error, datos.ronda, datos.nota, actor.id)
    return {"clasificado": True}


@router.get("/{evaluacion_id}/resultados/hoja-de-calculo", responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}, "description": "Hoja de cálculo con los resultados"}},
    summary="Los resultados en una hoja de cálculo")
def resultados_xlsx(evaluacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    datos = _hecho(db, evaluacion.resultados, db, ev, actor.id)
    from app.servicios import evaluacion_referencia

    datos["instrumento_1"] = evaluacion_referencia.instrumento_1(db, ev, datos)
    return Response(evaluacion.hoja_de_calculo(datos),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="evaluacion-ciega.xlsx"'})


@router.get("/{evaluacion_id}/documentos/{inst_id}/referencias",
            responses={200: {"model": list[re_.ReferenciaCiega], "description": "Descripciones ciegas del documento"}},
            summary="Las descripciones ciegas de un documento, para que la adjudicadora consolide la referencia")
def referencias(evaluacion_id: uuid.UUID, inst_id: uuid.UUID, actor: Actor = Depends(evaluador),
                db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    return _hecho(db, evaluacion.referencias_para_adjudicar, db, ev, inst_id, actor.id)


@router.get("/{evaluacion_id}/resultados/coincidencias",
            responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}},
                             "description": "Coincidencias por aserción para recalcular las métricas fuera del sistema"}},
            summary="Coincidencias por aserción, tiempos y versión, para la verificación independiente")
def coincidencias_xlsx(evaluacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    from app.servicios import evaluacion_referencia

    ev = _ev(db, evaluacion_id)
    datos = _hecho(db, evaluacion.resultados, db, ev, actor.id)
    contenido = evaluacion_referencia.hoja_coincidencias(db, ev, datos)
    registrar(db, modulo="evaluacion", accion="coincidencias_exportadas", usuario_id=actor.id, entidad_tipo="evaluacion",
              entidad_id=ev.id)
    db.commit()
    return Response(contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="coincidencias.xlsx"'})


@router.get("/{evaluacion_id}/hoja-ciega",
            responses={200: {"content": {"application/zip": {}},
                             "description": "Hoja de calificación ciega y llave de códigos, en archivos separados"}},
            summary="Descripciones con un código al azar, sin origen ni certeza, y la llave en otro archivo")
def hoja_ciega(evaluacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    from app.servicios import evaluacion_referencia

    ev = _ev(db, evaluacion_id)
    contenido = evaluacion_referencia.hoja_ciega(db, ev)
    registrar(db, modulo="evaluacion", accion="hoja_ciega_generada", usuario_id=actor.id, entidad_tipo="evaluacion",
              entidad_id=ev.id)
    db.commit()
    return Response(contenido, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="calificacion-ciega.zip"'})


# --- Expertas participantes (pregunta problema: humano frente a máquina) ------------------------------


class ParticipanteIn(BaseModel):
    usuario_id: uuid.UUID
    nombre: str = Field(min_length=3, max_length=200)
    profesion: str = Field(min_length=3, max_length=200)
    formacion: Literal["tecnica", "tecnologica", "profesional", "especializacion", "maestria", "doctorado"]
    anios_experiencia: int = Field(ge=0, le=70)
    anios_descripcion: int | None = Field(default=None, ge=0, le=70)
    cargo: str | None = Field(default=None, max_length=200)
    institucion: str | None = Field(default=None, max_length=200)
    rol: Literal["descriptora", "calificadora", "ambas", "validadora", "adjudicadora", "piloto"] = "descriptora"
    consentimiento: bool = False


class ParticipanteCambioIn(BaseModel):
    nombre: str | None = Field(default=None, min_length=3, max_length=200)
    profesion: str | None = Field(default=None, min_length=3, max_length=200)
    formacion: Literal["tecnica", "tecnologica", "profesional", "especializacion", "maestria", "doctorado"] | None = None
    anios_experiencia: int | None = Field(default=None, ge=0, le=70)
    anios_descripcion: int | None = Field(default=None, ge=0, le=70)
    cargo: str | None = Field(default=None, max_length=200)
    institucion: str | None = Field(default=None, max_length=200)
    rol: Literal["descriptora", "calificadora", "ambas", "validadora", "adjudicadora", "piloto"] | None = None
    consentimiento: bool | None = None
    retirar: bool = False


@router.get("/{evaluacion_id}/participantes",
            responses={200: {"model": list[re_.ParticipanteOut], "description": "Expertas registradas"}},
            summary="Expertas que participan: quiénes son, su formación, su experiencia y su consentimiento")
def participantes(evaluacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    from app.servicios import evaluacion_participantes as p

    return [p.out(x) for x in p.listar(db, _ev(db, evaluacion_id))]


@router.post("/{evaluacion_id}/participantes", status_code=status.HTTP_201_CREATED,
             responses={201: {"model": re_.ParticipanteOut, "description": "Experta registrada"}},
             summary="Registrar una experta (con su cuenta de usuario)")
def registrar_participante(evaluacion_id: uuid.UUID, datos: ParticipanteIn, actor: Actor = Depends(solo_administrador),
                           db: Session = Depends(get_db)):
    from app.servicios import evaluacion_participantes as p

    ev = _ev(db, evaluacion_id)
    return p.out(_hecho(db, p.registrar_participante, db, ev, datos.model_dump(), actor.id))


@router.put("/{evaluacion_id}/participantes/{participante_id}",
            responses={200: {"model": re_.ParticipanteOut, "description": "Experta actualizada"}},
            summary="Corregir los datos de una experta, registrar su consentimiento o retirarla (no se borra)")
def actualizar_participante(evaluacion_id: uuid.UUID, participante_id: uuid.UUID, datos: ParticipanteCambioIn,
                            actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    from app.servicios import evaluacion_participantes as p

    ev = _ev(db, evaluacion_id)
    return p.out(_hecho(db, p.actualizar, db, ev, participante_id, datos.model_dump(exclude_none=True), actor.id))
