"""
Servicio de vocabularios y control de autoridad.

verificar() es el servicio único de comparación por similitud: lo usa el
módulo de descripción antes de confirmar un agente, un lugar o una forma
documental, y lo usará la detección periódica de candidatos a fusión del
módulo de vocabularios. Nadie más compara nombres por su cuenta.

Comparación: trigramas de PostgreSQL (pg_trgm) sobre el nombre en
minúsculas y sin tildes (decisión documentada en
documentacion/modulo-2-descripcion.md).
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental


def normalizar(texto: str) -> str:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


@dataclass
class Coincidencia:
    id: uuid.UUID
    nombre: str
    subtipo: str | None
    similitud: float
    conexiones: int


def _documentos_por_entidad(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, set[uuid.UUID]]:
    """Descripciones (Record Resources) conectadas a cada entidad: las que la
    citan directamente, las que la usan como forma documental y, para un tipo
    de actividad, un mandato o el agente que ejerce una actividad, las que
    documentan esa actividad (RiC-R033). Una actividad o un mandato no son
    documentos: no se cuentan como tales."""
    from sqlalchemy.orm import aliased

    docs: dict[uuid.UUID, set[uuid.UUID]] = {i: set() for i in ids}
    if not ids:
        return docs
    for entidad, recurso in db.execute(select(Relacion.destino_id, Relacion.origen_id).where(
            Relacion.destino_id.in_(ids), Relacion.origen_tipo == "recurso_documental", Relacion.estado == "vigente")):
        docs[entidad].add(recurso)
    for entidad, recurso in db.execute(select(RecursoDocumental.forma_documental_id, RecursoDocumental.id)
                                       .where(RecursoDocumental.forma_documental_id.in_(ids))):
        docs[entidad].add(recurso)
    # Entidades unidas a una actividad (en cualquier sentido) y documentos de esa actividad.
    act = aliased(EntidadVocabulario)
    vecinas = db.execute(
        select(Relacion.origen_id, Relacion.destino_id).join(act, act.id == Relacion.destino_id)
        .where(Relacion.origen_id.in_(ids), act.clase == "actividad", Relacion.estado == "vigente")
        .union_all(select(Relacion.destino_id, Relacion.origen_id).join(act, act.id == Relacion.origen_id)
                   .where(Relacion.destino_id.in_(ids), act.clase == "actividad", Relacion.estado == "vigente"))).all()
    if vecinas:
        actividades = {a for _, a in vecinas}
        por_actividad: dict[uuid.UUID, set[uuid.UUID]] = {}
        for a, recurso in db.execute(select(Relacion.destino_id, Relacion.origen_id).where(
                Relacion.destino_id.in_(actividades), Relacion.codigo_ric == "documents", Relacion.estado == "vigente")):
            por_actividad.setdefault(a, set()).add(recurso)
        for entidad, a in vecinas:
            docs[entidad] |= por_actividad.get(a, set())
    return docs


def conexiones(db: Session, entidad_id: uuid.UUID) -> int:
    """Documentos conectados a la entidad."""
    return len(_documentos_por_entidad(db, [entidad_id])[entidad_id])


def verificar(db: Session, fondo_id: uuid.UUID, clase: str, valor: str, limite: int = 5) -> list[Coincidencia]:
    """Entidades activas del mismo tipo en el fondo que se parecen al valor
    propuesto, de mayor a menor coincidencia."""
    buscado = normalizar(valor)
    if not buscado:
        return []
    similitud = func.similarity(EntidadVocabulario.nombre_normalizado, buscado)
    filas = db.execute(
        select(EntidadVocabulario, similitud.label("s"))
        .where(EntidadVocabulario.fondo_id == fondo_id,
               EntidadVocabulario.clase == clase,
               EntidadVocabulario.estado == "activa",
               or_(similitud >= settings.umbral_similitud, EntidadVocabulario.nombre_normalizado == buscado))
        .order_by(similitud.desc(), EntidadVocabulario.nombre)
        .limit(limite)
    ).all()
    return [Coincidencia(id=e.id, nombre=e.nombre, subtipo=e.subtipo, similitud=round(float(s), 2),
                         conexiones=conexiones(db, e.id)) for e, s in filas]


def crear(db: Session, *, fondo_id: uuid.UUID, clase: str, nombre: str, subtipo: str | None, origen: str,
          confianza: float | None, motor: str | None, usuario_id: uuid.UUID) -> EntidadVocabulario:
    entidad = EntidadVocabulario(
        id=uuid.uuid4(), fondo_id=fondo_id, clase=clase, subtipo=subtipo, nombre=" ".join(nombre.split()),
        nombre_normalizado=normalizar(nombre), origen=origen, confianza=confianza, motor=motor,
        estado_revision="validado", creado_por_id=usuario_id,
    )
    db.add(entidad)
    return entidad


# --- Módulo 3: navegación, detección de candidatos y fusión -------------------------------------------

def conexiones_de(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Conexiones de varias entidades a la vez (para listados)."""
    return {i: len(d) for i, d in _documentos_por_entidad(db, list(ids)).items()}


def documentos_conectados(db: Session, entidad_id: uuid.UUID, historicos: bool = False) -> list[RecursoDocumental]:
    """Descripciones conectadas hoy a la entidad; con `historicos`, las que
    la citaban antes de que se fusionara en otra."""
    if historicos:
        ids = set(db.scalars(select(Relacion.origen_id).where(Relacion.destino_original_id == entidad_id,
                                                              Relacion.estado == "vigente")))
    else:
        ids = _documentos_por_entidad(db, [entidad_id])[entidad_id]
    if not ids:
        return []
    return list(db.scalars(select(RecursoDocumental).where(RecursoDocumental.id.in_(ids))
                           .order_by(RecursoDocumental.titulo)))


class ErrorFusion(Exception):
    pass


def fusionar(db: Session, *, definitiva: EntidadVocabulario, absorbida: EntidadVocabulario, usuario_id: uuid.UUID,
             sugerencia=None, ip: str | None = None) -> int:
    """Fusiona `absorbida` en `definitiva` en una sola transacción. Las
    relaciones se redirigen (guardando a quién apuntaban), la absorbida no se
    borra: queda «fusionada» y enlazada a la definitiva. Devuelve cuántas
    relaciones se movieron."""
    from sqlalchemy import update

    from app.db.base import ahora
    from app.models.descripcion import SugerenciaFusion
    from app.servicios.auditoria import registrar

    if definitiva.id == absorbida.id:
        raise ErrorFusion("Elija dos entidades distintas.")
    if definitiva.fondo_id != absorbida.fondo_id or definitiva.clase != absorbida.clase:
        raise ErrorFusion("Solo se fusionan entidades del mismo tipo y del mismo fondo.")
    if definitiva.estado != "activa" or absorbida.estado != "activa":
        raise ErrorFusion("Alguna de las dos entidades ya fue fusionada antes.")
    conexiones_antes = conexiones_de(db, [definitiva.id, absorbida.id])
    movidas = db.execute(
        update(Relacion).where(Relacion.destino_id == absorbida.id, Relacion.estado == "vigente")
        .values(destino_id=definitiva.id, destino_original_id=func.coalesce(Relacion.destino_original_id, absorbida.id))
    ).rowcount
    # Y donde la entidad es el origen (el agente que ejerce una actividad,
    # el mandato que la regula, la actividad con su tipo).
    movidas += db.execute(
        update(Relacion).where(Relacion.origen_id == absorbida.id, Relacion.estado == "vigente")
        .values(origen_id=definitiva.id, origen_original_id=func.coalesce(Relacion.origen_original_id, absorbida.id))
    ).rowcount
    formas = db.execute(update(RecursoDocumental).where(RecursoDocumental.forma_documental_id == absorbida.id)
                        .values(forma_documental_id=definitiva.id)).rowcount
    # Las que ya se habían fusionado en la absorbida pasan a apuntar a la definitiva.
    db.execute(update(EntidadVocabulario).where(EntidadVocabulario.fusionada_en_id == absorbida.id)
               .values(fusionada_en_id=definitiva.id))
    absorbida.estado = "fusionada"
    absorbida.fusionada_en_id = definitiva.id
    momento = ahora()
    pendientes = db.scalars(select(SugerenciaFusion).where(
        SugerenciaFusion.estado == "pendiente",
        (SugerenciaFusion.entidad_a_id == absorbida.id) | (SugerenciaFusion.entidad_b_id == absorbida.id))).all()
    for s in pendientes:
        if sugerencia is not None and s.id == sugerencia.id:
            continue
        s.estado, s.resuelta_en = "obsoleta", momento
    if sugerencia is not None:
        sugerencia.estado, sugerencia.resuelta_en = "aprobada", momento
        sugerencia.resuelta_por_id, sugerencia.definitiva_id = usuario_id, definitiva.id
    registrar(db, modulo="vocabularios", accion="fusion_vocabulario", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=definitiva.id, ip=ip,
              anterior={"absorbida": {"id": str(absorbida.id), "nombre": absorbida.nombre,
                                      "conexiones": conexiones_antes[absorbida.id]},
                        "definitiva": {"id": str(definitiva.id), "nombre": definitiva.nombre,
                                       "conexiones": conexiones_antes[definitiva.id]}},
              nuevo={"definitiva": str(definitiva.id), "relaciones_movidas": movidas + formas,
                     "origen": "sugerencia" if sugerencia is not None else "manual"},
              detalle=f"«{absorbida.nombre}» se fusionó en «{definitiva.nombre}».")
    return movidas + formas


def detectar_candidatos(db: Session, fondo_id: uuid.UUID | None = None) -> int:
    """Compara entre sí las entidades activas del mismo tipo y fondo con el
    mismo criterio de similitud que verificar(), y registra una sugerencia
    por cada par muy parecido en el que ambas tienen pocas conexiones. No
    fusiona nada. Un par ya sugerido (en cualquier estado) no se repite."""
    from sqlalchemy.orm import aliased

    from app.models.descripcion import SugerenciaFusion
    from app.servicios import parametros

    umbral = int(parametros.leer(db, "fusion_similitud_pct")) / 100
    maximo = int(parametros.leer(db, "fusion_max_conexiones"))
    a, b = aliased(EntidadVocabulario), aliased(EntidadVocabulario)
    similitud = func.similarity(a.nombre_normalizado, b.nombre_normalizado)
    consulta = (select(a, b, similitud.label("s"))
                .join(b, (a.fondo_id == b.fondo_id) & (a.clase == b.clase) & (a.id < b.id))
                .where(a.estado == "activa", b.estado == "activa", similitud >= umbral))
    if fondo_id is not None:
        consulta = consulta.where(a.fondo_id == fondo_id)
    pares = db.execute(consulta).all()
    if not pares:
        return 0
    conexiones = conexiones_de(db, list({x.id for p in pares for x in p[:2]}))
    existentes = set(db.execute(select(SugerenciaFusion.entidad_a_id, SugerenciaFusion.entidad_b_id)).all())
    nuevas = 0
    for x, y, s in pares:
        if (x.id, y.id) in existentes or conexiones[x.id] > maximo or conexiones[y.id] > maximo:
            continue
        db.add(SugerenciaFusion(fondo_id=x.fondo_id, clase=x.clase, entidad_a_id=x.id, entidad_b_id=y.id,
                                similitud=round(float(s), 2)))
        nuevas += 1
    return nuevas


CLAVE_ULTIMA_DETECCION = "fusion_ultima_deteccion"


def deteccion_periodica(db: Session) -> int | None:
    """La llama el trabajador en cada vuelta: si ya pasó el intervalo
    configurado desde la última búsqueda, busca candidatos en todos los
    fondos. Devuelve cuántas sugerencias nuevas creó, o None si no tocaba."""
    from datetime import datetime, timedelta

    from app.db.base import ahora
    from app.models.parametro import Parametro
    from app.servicios import parametros

    horas = int(parametros.leer(db, "fusion_horas_deteccion"))
    fila = db.get(Parametro, CLAVE_ULTIMA_DETECCION)
    if fila is not None and ahora() - datetime.fromisoformat(fila.valor) < timedelta(hours=horas):
        return None
    nuevas = detectar_candidatos(db)
    if fila is None:
        db.add(Parametro(clave=CLAVE_ULTIMA_DETECCION, valor=ahora().isoformat()))
    else:
        fila.valor = ahora().isoformat()
    db.commit()
    return nuevas


# --- Relaciones entre agentes (catálogo curado, verificadas en RiC-O 1.1) -----------------------------

RELACION_AGENTES = {
    "subordinado": ("has_or_had_subordinate", "jerarquía: tiene o tuvo como subordinado", "está o estuvo subordinado a"),
    "sucesor": ("has_successor", "temporal: tiene como sucesor", "es sucesor de"),
    "asociado": ("is_agent_associated_with_agent", "asociativa: está asociado con", "está asociado con"),
}


class ErrorRelacionAgentes(Exception):
    pass


def relacionar_agentes(db: Session, *, origen: EntidadVocabulario, destino: EntidadVocabulario, tipo: str,
                       usuario_id: uuid.UUID, ip: str | None = None) -> Relacion:
    """Relación declarada entre dos agentes del mismo fondo. Se guarda una
    sola fila; su inversa (owl:inverseOf en RiC-O) se lee de ella, nunca se
    duplica, para que anular una anule las dos lecturas a la vez."""
    from app.servicios.auditoria import registrar

    if tipo not in RELACION_AGENTES:
        raise ErrorRelacionAgentes("Tipo de relación entre agentes desconocido.")
    if origen.clase != "agente" or destino.clase != "agente" or origen.fondo_id != destino.fondo_id:
        raise ErrorRelacionAgentes("Solo se relacionan agentes del mismo fondo.")
    if origen.id == destino.id:
        raise ErrorRelacionAgentes("Un agente no se relaciona consigo mismo.")
    codigo = RELACION_AGENTES[tipo][0]
    existente = db.scalar(select(Relacion).where(
        Relacion.codigo_ric == codigo, Relacion.estado == "vigente",
        ((Relacion.origen_id == origen.id) & (Relacion.destino_id == destino.id))
        | ((Relacion.origen_id == destino.id) & (Relacion.destino_id == origen.id) if tipo == "asociado" else False)))
    if existente is not None:
        raise ErrorRelacionAgentes("Esa relación ya existe.")
    r = Relacion(origen_tipo="entidad_vocabulario", origen_id=origen.id, destino_tipo="entidad_vocabulario",
                 destino_id=destino.id, tipo_relacion="temporal" if tipo == "sucesor" else "asociacion",
                 codigo_ric=codigo, origen="persona", confirmada_por_id=usuario_id)
    db.add(r)
    db.flush()
    registrar(db, modulo="vocabularios", accion="agentes_relacionados", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=origen.id, ip=ip,
              nuevo={"relacion_id": str(r.id), "tipo": tipo, "codigo_ric": codigo, "con": str(destino.id)},
              detalle=f"«{origen.nombre}» {RELACION_AGENTES[tipo][1].split(': ')[1]} «{destino.nombre}»")
    return r


def relaciones_de_agente(db: Session, agente_id: uuid.UUID) -> list[dict]:
    """Las relaciones del agente leídas en los dos sentidos, con la inversa
    cuando el agente es el destino."""
    from app.models.enums import INVERSA_RICO, URI_RICO

    codigos = [c for c, _, _ in RELACION_AGENTES.values()]
    filas = db.scalars(select(Relacion).where(Relacion.codigo_ric.in_(codigos), Relacion.estado == "vigente",
                                              (Relacion.origen_id == agente_id) | (Relacion.destino_id == agente_id))).all()
    por_codigo = {c: (t, directa, inversa) for t, (c, directa, inversa) in RELACION_AGENTES.items()}
    salida = []
    for r in filas:
        tipo, directa, inversa = por_codigo[r.codigo_ric]
        es_origen = r.origen_id == agente_id
        otro = db.get(EntidadVocabulario, r.destino_id if es_origen else r.origen_id)
        salida.append({"relacion_id": str(r.id), "tipo": tipo, "codigo_ric": r.codigo_ric,
                       "etiqueta": directa.split(": ")[1] if es_origen else inversa,
                       "uri_rico": URI_RICO[r.codigo_ric] if es_origen else INVERSA_RICO[r.codigo_ric],
                       "con": {"id": str(otro.id), "nombre": otro.nombre, "subtipo": otro.subtipo} if otro else None})
    return salida
