"""
Expertas participantes de la evaluación (pregunta problema: humano frente a máquina).

La comparación solo responde la pregunta si se sabe quién hizo la descripción
humana de referencia y por qué es experta. Por eso cada participante se
registra con su cuenta de usuario (la que firma sus anotaciones), su nombre,
su profesión, su nivel de formación, sus años de experiencia y su
consentimiento informado.

Reglas:
- Solo participa quien está registrada, activa y con consentimiento.
  Cada rol hace una sola cosa: la descriptora describe a ciegas, la
  validadora trabaja con la propuesta del motor delante y no ve la
  referencia, la adjudicadora consolida la referencia, la calificadora
  califica y la de la prueba piloto ensaya el protocolo con documentos
  que no entran en los resultados. «Ambas» conserva el flujo anterior.
- No se inicia una evaluación sin al menos una experta con consentimiento.
- Cada experta recibe un código (E1, E2…) en el orden de registro. Los
  resultados exportados usan el código, nunca el nombre (Ley 1581
  de 2012). El nombre lo ve solo quien administra la evaluación.
- Nada se borra: una participante se retira (queda la fecha) y sus
  anotaciones ya enviadas siguen contando, con su código.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import ahora
from app.models.evaluacion import FORMACION, ROL_PARTICIPANTE, Evaluacion, Participante
from app.models.usuario import Usuario
from app.servicios.auditoria import registrar
from app.servicios.evaluacion import ErrorEvaluacion

FORMACION_NOMBRE = {"tecnica": "Técnica", "tecnologica": "Tecnológica", "profesional": "Profesional",
                    "especializacion": "Especialización", "maestria": "Maestría", "doctorado": "Doctorado"}
ROL_NOMBRE = {"descriptora": "Describe a ciegas (referencia)", "calificadora": "Califica la propuesta",
              "ambas": "Describe y califica", "validadora": "Valida las propuestas del motor (sin ver la referencia)",
              "adjudicadora": "Consolida la referencia a partir de las descripciones ciegas",
              "piloto": "Prueba piloto del protocolo (no entra en los resultados)"}
# Qué puede hacer cada rol. «ambas» conserva el flujo anterior: describe a ciegas, describe con la
# propuesta delante y califica.
PERMITE = {"describir": ("descriptora", "ambas", "piloto"), "validar": ("validadora", "ambas", "piloto"),
           "calificar": ("calificadora", "ambas"), "adjudicar": ("adjudicadora",)}
ROL_VERBO = {"descriptora": "describir a ciegas", "calificadora": "calificar la propuesta",
             "ambas": "describir y calificar", "validadora": "validar las propuestas del motor",
             "adjudicadora": "consolidar la referencia", "piloto": "la prueba piloto"}
QUE_HACE = {"describir": "describir a ciegas", "validar": "trabajar con la propuesta del motor delante",
            "calificar": "calificar la propuesta", "adjudicar": "consolidar la referencia"}
CAMPOS = ("nombre", "profesion", "formacion", "anios_experiencia", "anios_descripcion", "cargo", "institucion", "rol",
          "consentimiento")


class ErrorParticipante(ErrorEvaluacion):
    """Un error de evaluación: el router lo traduce igual."""


def _validar(datos: dict) -> None:
    if datos.get("formacion") not in FORMACION:
        raise ErrorParticipante("Elija el nivel de formación.")
    if datos.get("rol") not in ROL_PARTICIPANTE:
        raise ErrorParticipante("Elija el rol en la evaluación.")
    if not (datos.get("nombre") or "").strip() or not (datos.get("profesion") or "").strip():
        raise ErrorParticipante("El nombre y la profesión son obligatorios.")
    for campo in ("anios_experiencia", "anios_descripcion"):
        v = datos.get(campo)
        if v is not None and not (0 <= int(v) <= 70):
            raise ErrorParticipante("Los años de experiencia deben estar entre 0 y 70.")
    if datos.get("anios_experiencia") is None:
        raise ErrorParticipante("Indique los años de experiencia en archivos.")


def out(p: Participante, con_nombre: bool = True) -> dict:
    return {"id": str(p.id), "usuario_id": str(p.usuario_id), "codigo": p.codigo,
            "nombre": p.nombre if con_nombre else None, "profesion": p.profesion, "formacion": p.formacion,
            "formacion_nombre": FORMACION_NOMBRE[p.formacion], "anios_experiencia": p.anios_experiencia,
            "anios_descripcion": p.anios_descripcion, "cargo": p.cargo, "institucion": p.institucion, "rol": p.rol,
            "rol_nombre": ROL_NOMBRE[p.rol], "consentimiento": p.consentimiento, "consentimiento_en": p.consentimiento_en,
            "registrado_en": p.registrado_en, "retirado_en": p.retirado_en, "activa": p.retirado_en is None}


def listar(db: Session, ev: Evaluacion) -> list[Participante]:
    return list(db.scalars(select(Participante).where(Participante.evaluacion_id == ev.id)
                           .order_by(Participante.registrado_en, Participante.codigo)).all())


def codigos(db: Session, ev: Evaluacion) -> dict[uuid.UUID, Participante]:
    return {p.usuario_id: p for p in listar(db, ev)}


def registrar_participante(db: Session, ev: Evaluacion, datos: dict, usuario_id: uuid.UUID) -> Participante:
    if ev.estado == "cerrada":
        raise ErrorParticipante("La evaluación está cerrada.", 409)
    _validar(datos)
    cuenta = db.get(Usuario, uuid.UUID(str(datos.get("usuario_id"))))
    if cuenta is None or not cuenta.activo:
        raise ErrorParticipante("La cuenta elegida no existe o está inactiva. Créela en Usuarios y permisos.")
    if db.scalar(select(Participante.id).where(Participante.evaluacion_id == ev.id,
                                               Participante.usuario_id == cuenta.id)):
        raise ErrorParticipante("Esa persona ya está registrada en esta evaluación.", 409)
    n = int(db.scalar(select(func.count()).select_from(Participante).where(Participante.evaluacion_id == ev.id)) or 0)
    p = Participante(id=uuid.uuid4(), evaluacion_id=ev.id, usuario_id=cuenta.id, codigo=f"E{n + 1}",
                     registrado_por_id=usuario_id,
                     **{c: (datos.get(c).strip() if isinstance(datos.get(c), str) else datos.get(c)) for c in CAMPOS
                        if c != "consentimiento"},
                     consentimiento=bool(datos.get("consentimiento")),
                     consentimiento_en=ahora() if datos.get("consentimiento") else None)
    db.add(p)
    db.flush()
    registrar(db, modulo="evaluacion", accion="participante_registrada", usuario_id=usuario_id,
              entidad_tipo="evaluacion", entidad_id=ev.id, nuevo=out(p) | {"consentimiento_en": None, "registrado_en": None})
    return p


def actualizar(db: Session, ev: Evaluacion, participante_id: uuid.UUID, datos: dict, usuario_id: uuid.UUID) -> Participante:
    p = db.get(Participante, participante_id)
    if p is None or p.evaluacion_id != ev.id:
        raise ErrorParticipante("Esa participante no está en la evaluación.", 404)
    _validar({c: datos.get(c, getattr(p, c)) for c in CAMPOS})
    anterior = out(p)
    for c in CAMPOS:
        if c in datos and c != "consentimiento":
            setattr(p, c, datos[c].strip() if isinstance(datos[c], str) else datos[c])
    if "consentimiento" in datos and bool(datos["consentimiento"]) != p.consentimiento:
        p.consentimiento = bool(datos["consentimiento"])
        p.consentimiento_en = ahora() if p.consentimiento else None
    if datos.get("retirar") and p.retirado_en is None:
        p.retirado_en = ahora()
    db.flush()
    registrar(db, modulo="evaluacion", accion="participante_actualizada", usuario_id=usuario_id,
              entidad_tipo="evaluacion", entidad_id=ev.id,
              anterior={k: v for k, v in anterior.items() if k in CAMPOS or k == "codigo"},
              nuevo={k: v for k, v in out(p).items() if k in CAMPOS or k in ("codigo", "activa")})
    return p


def exigir(db: Session, ev: Evaluacion, usuario_id: uuid.UUID, para: str) -> Participante:
    """La participante que puede describir («describir») o calificar («calificar»), o un error claro."""
    p = db.scalar(select(Participante).where(Participante.evaluacion_id == ev.id, Participante.usuario_id == usuario_id))
    if p is None or p.retirado_en is not None:
        raise ErrorParticipante("Usted no está registrada como experta en esta evaluación. Pida a quien la administra "
                                "que la registre.", 403)
    if not p.consentimiento:
        raise ErrorParticipante("Falta registrar su consentimiento informado para participar.", 403)
    if p.rol not in PERMITE[para]:
        raise ErrorParticipante(f"Su rol en esta evaluación es {ROL_VERBO[p.rol]}: no le permite {QUE_HACE[para]}.", 403)
    return p


def rol_de(db: Session, ev: Evaluacion, usuario_id: uuid.UUID) -> str | None:
    p = db.scalar(select(Participante).where(Participante.evaluacion_id == ev.id, Participante.usuario_id == usuario_id))
    return p.rol if p is not None and p.retirado_en is None else None


def listas_para_iniciar(db: Session, ev: Evaluacion) -> int:
    return sum(1 for p in listar(db, ev) if p.retirado_en is None and p.consentimiento)
