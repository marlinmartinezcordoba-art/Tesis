"""
Descripción multinivel: marca «en edición», publicación transaccional del
Record Resource con sus relaciones, y corrección posterior.

Relaciones que crea (catálogo curado, códigos oficiales RiC-CM 1.0):

| Qué                          | Código RiC-R                           | Sentido               |
|------------------------------|----------------------------------------|-----------------------|
| Productor                    | has_creator (R027)                     | documento → agente    |
| Remitente                    | has_sender (R031)                      | documento → agente    |
| Destinatario                 | has_addressee (R032)                   | documento → agente    |
| Autor (persona, grupo, cargo)| has_author (R079), solo un documento   | documento → agente    |
| Acumulador                   | has_accumulator (R028)                 | documento → agente    |
| Agente o lugar mencionado    | has_or_had_subject (R019)              | documento → entidad   |
| Fecha de creación            | is_creation_date_of (R080)             | fecha → documento     |
| Actividad documentada        | documents (R033)                       | documento → actividad |
| Tipo de la actividad         | has_activity_type (rico:hasActivityType)| actividad → tipo     |
| Agente que ejerce            | performs_or_performed (R060i)          | agente → actividad    |
| Mandato que la regula        | regulates_or_regulated (R063)          | mandato → actividad   |
| Mandato que autoriza         | authorizes (R067)                      | mandato → agente      |
| Periodo de la actividad      | is_date_associated_with (R068)         | fecha → actividad     |
| Expedición del mandato       | is_date_associated_with (R068), rol «expedicion» | fecha → mandato |
| Mandato citado sin actividad | has_or_had_subject (R019)              | documento → mandato   |
| Custodio (no productor)      | has_or_had_holder (R039i)              | documento → agente    |
| Sub-actividad                | has_direct_subevent (rico)             | mayor → sub-actividad |
| Secuencia en la serie        | precedes_or_preceded (R008)            | anterior → siguiente  |
| Parte documental             | has_or_had_constituent (R003)          | documento → parte     |
| Inclusión en nivel superior  | includes_or_included (R024)            | superior → documento  |
| Archivo técnico              | has_or_had_instantiation (R025)        | documento → archivo   |

La forma documental no es una relación sino un atributo (RiC-A17), que
apunta a una entrada del vocabulario. RiC-O 1.1 define «authorizes» del
mandato al agente, no a la actividad: por eso la actividad se une a su
mandato con R063 y el agente que la ejerce recibe además el R067.

Al publicar, cada propuesta del motor deja en auditoría un evento
«decision_ia» (aceptada, corregida o rechazada; y «agregada» para lo que
la archivista puso y el motor no propuso), con el valor propuesto, el
final, el modelo y la versión de las instrucciones. Es la evidencia del
capítulo de evaluación de la tesis.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.descripcion import (
    EntidadVocabulario, Fecha, Relacion, TrabajoDescripcion, TrabajoInstanciacion,
)
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import NIVEL_DESCRIPCION, RecursoDocumental
from app.models.usuario import Usuario
from app.servicios import evidencia as servicio_evidencia, fechas, mecanismos, ric_o, vocabulario
from app.servicios.auditoria import registrar

NIVELES_CONJUNTO = ("expediente", "subserie", "serie")
CLASES_VOCABULARIO = ("agente", "lugar", "forma_documental", "actividad", "tipo_actividad", "mandato")
TIPOS_ENTIDAD = CLASES_VOCABULARIO + ("fecha",)
from app.models.descripcion import SUBTIPO_AGENTE as SUBTIPOS_AGENTE  # noqa: E402
SUBTIPOS_MANDATO = ("ley", "decreto", "ordenanza", "acuerdo", "resolucion", "otro")

ROLES_AGENTE = ("productor", "autor", "remitente", "destinatario", "acumulador", "mencionado", "custodio")

# (tipo, rol) → (código RiC, categoría amplia, sentido)
RELACION_POR_ROL = {
    ("agente", "productor"): ("has_creator", "procedencia"),
    ("agente", "remitente"): ("has_sender", "procedencia"),
    ("agente", "destinatario"): ("has_addressee", "procedencia"),
    # Brecha 8 de la auditoría de especialización: autoría y acumulación.
    ("agente", "autor"): ("has_author", "procedencia"),
    ("agente", "acumulador"): ("has_accumulator", "procedencia"),
    ("agente", "mencionado"): ("has_or_had_subject", "asociacion"),
    # Quien tiene o tuvo la custodia sin haberlo producido (RiC-R039i).
    ("agente", "custodio"): ("has_or_had_holder", "procedencia"),
    ("lugar", None): ("has_or_had_subject", "espacial"),
    # Lugar donde se expidió o produjo el documento (RiC-R075, desde el lugar).
    ("lugar", "expedicion"): ("is_or_was_location_of", "espacial"),
    ("fecha", None): ("is_creation_date_of", "temporal"),
    ("actividad", None): ("documents", "asociacion"),
    ("mandato", None): ("has_or_had_subject", "asociacion"),
}


class ErrorDescripcion(Exception):
    def __init__(self, mensaje: str, codigo: int = 422, datos: dict | None = None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.datos = datos


def rango(nivel: str) -> int:
    return NIVEL_DESCRIPCION.index(nivel)


# --- Marca «en edición» --------------------------------------------------------------------


def expirar(db: Session) -> None:
    """Libera las marcas sin actividad durante más del tiempo configurado."""
    limite = ahora() - timedelta(minutes=settings.minutos_bloqueo_descripcion)
    vencidos = db.scalars(select(TrabajoDescripcion).where(
        TrabajoDescripcion.estado == "abierto", TrabajoDescripcion.ultima_actividad < limite)).all()
    for t in vencidos:
        _cerrar(db, t, "expirado")
        registrar(db, modulo="descripcion", accion="edicion_liberada", usuario_id=t.usuario_id,
                  entidad_tipo="trabajo_descripcion", entidad_id=t.id, detalle="Sin actividad: la marca venció sola.")


def _cerrar(db: Session, trabajo: TrabajoDescripcion, estado: str) -> None:
    from app.servicios import propuestas_ia

    trabajo.estado = estado
    trabajo.cerrado_en = ahora()
    # La propuesta del motor se conserva siempre; solo cambia su estado.
    propuestas_ia.cerrar(db, trabajo.propuesta_id, estado)
    db.execute(update(TrabajoInstanciacion).where(TrabajoInstanciacion.trabajo_id == trabajo.id)
               .values(abierto=False))


def trabajo_propio(db: Session, trabajo_id: uuid.UUID, usuario_id: uuid.UUID) -> TrabajoDescripcion:
    expirar(db)
    trabajo = db.get(TrabajoDescripcion, trabajo_id)
    if trabajo is None or trabajo.usuario_id != usuario_id:
        raise ErrorDescripcion("Este espacio de trabajo no existe o es de otra persona.", 404)
    if trabajo.estado != "abierto":
        raise ErrorDescripcion("La marca «en edición» ya se liberó (por inactividad o porque se cerró). "
                               "Vuelva a abrir el documento desde la cola.", 409)
    return trabajo


def latido(db: Session, trabajo: TrabajoDescripcion) -> None:
    trabajo.ultima_actividad = ahora()


def instanciaciones_del_trabajo(db: Session, trabajo: TrabajoDescripcion) -> list[Instanciacion]:
    """Los documentos que se ven en la pantalla: los del trabajo o, en una
    corrección, los de la descripción reabierta."""
    if trabajo.recurso_id is None:
        return documentos_de(db, trabajo)
    return list(db.scalars(select(Instanciacion).join(Relacion, Relacion.destino_id == Instanciacion.id).where(
        Relacion.origen_id == trabajo.recurso_id, Relacion.codigo_ric == "has_or_had_instantiation",
        Relacion.estado == "vigente")))


def documentos_de(db: Session, trabajo: TrabajoDescripcion) -> list[Instanciacion]:
    filas = db.execute(select(Instanciacion).join(
        TrabajoInstanciacion, TrabajoInstanciacion.instanciacion_id == Instanciacion.id)
        .where(TrabajoInstanciacion.trabajo_id == trabajo.id).order_by(TrabajoInstanciacion.orden)).scalars().all()
    return list(filas)


def _derivadas(db: Session, ids: list[uuid.UUID]) -> list[Instanciacion]:
    """Instanciaciones que salieron por migración de estas (y de sus
    derivadas): se describen junto con su original."""
    salida, pendientes = [], list(ids)
    while pendientes:
        hijas = db.scalars(select(Instanciacion).where(Instanciacion.derivada_de_id.in_(pendientes))).all()
        salida.extend(hijas)
        pendientes = [h.id for h in hijas]
    return salida


def _sin_descripcion():
    return ~exists().where(Relacion.destino_id == Instanciacion.id, Relacion.estado == "vigente",
                           Relacion.codigo_ric == "has_or_had_instantiation")


def cola(db: Session, fondo_id: uuid.UUID) -> list[tuple[Instanciacion, str | None]]:
    """Instanciaciones listas para describir y sin Record Resource, con el
    nombre de quien las tiene en edición (si alguien)."""
    expirar(db)
    filas = db.scalars(select(Instanciacion).where(
        Instanciacion.fondo_id == fondo_id, Instanciacion.estado == "listo_para_descripcion", _sin_descripcion(),
        # Una instanciación que salió de una migración no se describe aparte:
        # hereda la descripción de su original (módulo 5).
        Instanciacion.derivada_de_id.is_(None),
        # Un recorte nace ya como instanciación de su parte documental.
        Instanciacion.recorte_de_id.is_(None))
        .order_by(Instanciacion.cargado_en)).all()
    en_edicion = dict(db.execute(
        select(TrabajoInstanciacion.instanciacion_id, Usuario.nombre)
        .join(TrabajoDescripcion, TrabajoDescripcion.id == TrabajoInstanciacion.trabajo_id)
        .join(Usuario, Usuario.id == TrabajoDescripcion.usuario_id)
        .where(TrabajoInstanciacion.abierto.is_(True))).all())
    return [(i, en_edicion.get(i.id)) for i in filas]


def abrir(db: Session, *, usuario_id: uuid.UUID, instanciacion_ids: list[uuid.UUID], nivel: str | None) -> TrabajoDescripcion:
    """Marca los documentos «en edición» para esta persona. Falla si otra
    persona ya tiene alguno abierto (el índice único de la base de datos lo
    garantiza aunque dos pulsen al mismo tiempo)."""
    expirar(db)
    ids = list(dict.fromkeys(instanciacion_ids))
    if not ids:
        raise ErrorDescripcion("Seleccione al menos un documento.")
    if len(ids) == 1:
        nivel = "unidad_documental"
    elif nivel not in NIVELES_CONJUNTO:
        raise ErrorDescripcion("Para describir varios documentos juntos, elija si son un expediente, una subserie o una serie.")
    documentos = db.scalars(select(Instanciacion).where(Instanciacion.id.in_(ids), _sin_descripcion())).all()
    if len(documentos) != len(ids) or any(d.estado != "listo_para_descripcion" or d.derivada_de_id for d in documentos):
        raise ErrorDescripcion("Alguno de los documentos ya no está disponible para describir (quizá ya se describió).", 409)
    if len({d.fondo_id for d in documentos}) != 1:
        raise ErrorDescripcion("Todos los documentos de un conjunto deben ser del mismo fondo.")
    ocupados = db.execute(
        select(Instanciacion.nombre_original, Usuario.nombre)
        .join(TrabajoInstanciacion, TrabajoInstanciacion.instanciacion_id == Instanciacion.id)
        .join(TrabajoDescripcion, TrabajoDescripcion.id == TrabajoInstanciacion.trabajo_id)
        .join(Usuario, Usuario.id == TrabajoDescripcion.usuario_id)
        .where(TrabajoInstanciacion.abierto.is_(True), Instanciacion.id.in_(ids))).first()
    if ocupados:
        raise ErrorDescripcion(f"«{ocupados[0]}» está en edición por {ocupados[1]}.", 409)
    trabajo = TrabajoDescripcion(id=uuid.uuid4(), usuario_id=usuario_id, fondo_id=documentos[0].fondo_id, nivel=nivel)
    db.add(trabajo)
    db.flush()
    orden = {i: n for n, i in enumerate(ids)}
    for d in documentos:
        db.add(TrabajoInstanciacion(trabajo_id=trabajo.id, instanciacion_id=d.id, abierto=True, orden=orden[d.id]))
    db.flush()  # aquí salta el índice único si otra persona ganó la carrera
    return trabajo


def cancelar(db: Session, trabajo: TrabajoDescripcion, usuario_id: uuid.UUID) -> None:
    _cerrar(db, trabajo, "cancelado")
    registrar(db, modulo="descripcion", accion="descripcion_cancelada", usuario_id=usuario_id,
              entidad_tipo="trabajo_descripcion", entidad_id=trabajo.id)


# --- Publicación ----------------------------------------------------------------------------


@dataclass
class EntidadConfirmada:
    tipo: str
    valor: str
    subtipo: str | None = None
    rol: str | None = None
    fecha_normalizada: str | None = None
    edtf: str | None = None  # fecha, periodo de la actividad, expedición del mandato o tramo de la custodia
    nota: str | None = None
    fecha_subtipo: str | None = None
    tipo_clave: str | None = None  # actividad → su tipo de actividad (clave de otra entidad del envío)
    agente_clave: str | None = None  # actividad → agente que la ejerce
    mandato_clave: str | None = None  # actividad → mandato que la regula
    # Actividad mayor de la que esta es sub-actividad: una ya existente en el
    # vocabulario del fondo, o la clave de otra actividad del mismo envío.
    actividad_mayor_id: uuid.UUID | None = None
    actividad_mayor_clave: str | None = None
    fragmento: str | None = None
    documento_id: str | None = None
    inicio: int | None = None
    clave: str | None = None  # clave de la entidad (la de la propuesta del motor, si viene de ahí)
    reutilizar_id: uuid.UUID | None = None
    crear_nueva: bool = False


def _propuesta(trabajo: TrabajoDescripcion) -> dict:
    try:
        return json.loads(trabajo.propuesta or "{}")
    except ValueError:
        return {}


def _procedencia(valor: str, propuesto: str | None, confianza: float | None) -> tuple[str, float | None]:
    """El origen lo decide el servidor comparando con la propuesta guardada,
    no lo que diga el navegador."""
    if propuesto is None:
        return "persona", None
    if " ".join((valor or "").split()) == " ".join((propuesto or "").split()):
        return "motor", confianza
    return "motor_editado", confianza


def _nodo_vocabulario(db: Session, fondo_id: uuid.UUID, e: EntidadConfirmada, indice: int, origen: str,
                      confianza: float | None, motor: str | None, usuario_id: uuid.UUID) -> EntidadVocabulario:
    if e.reutilizar_id:
        existente = db.get(EntidadVocabulario, e.reutilizar_id)
        if existente is None or existente.fondo_id != fondo_id or existente.clase != e.tipo:
            raise ErrorDescripcion(f"La entidad elegida para reutilizar «{e.valor}» no existe en el vocabulario del fondo.")
        while existente.estado == "fusionada" and existente.fusionada_en_id:
            existente = db.get(EntidadVocabulario, existente.fusionada_en_id)
        return existente
    # Dependencia real del servicio de vocabularios: si hay parecidos y la
    # persona no confirmó que es distinta, no se crea nada.
    parecidas = vocabulario.verificar(db, fondo_id, e.tipo, e.valor)
    if parecidas and not e.crear_nueva:
        raise ErrorDescripcion(
            f"«{e.valor}» se parece a entidades que ya están en el vocabulario. Indique si es la misma o una nueva.",
            409, {"indice": indice, "coincidencias": [c.__dict__ | {"id": str(c.id)} for c in parecidas]})
    return vocabulario.crear(db, fondo_id=fondo_id, clase=e.tipo, nombre=e.valor, subtipo=e.subtipo,
                             origen=origen, confianza=confianza, motor=motor, usuario_id=usuario_id)


def _interpretar_fecha(e: EntidadConfirmada, que: str) -> fechas.Interpretacion | None:
    if not e.edtf and e.tipo != "fecha":
        return None
    if not e.edtf and e.fecha_normalizada:  # pantallas de la versión anterior
        e.edtf = e.fecha_normalizada
    if not e.edtf:
        raise ErrorDescripcion(f"Complete la fecha de «{e.valor}»: elija si es simple, rango o conjunto y su precisión.")
    try:
        return fechas.interpretar(e.edtf, e.fecha_subtipo if e.tipo == "fecha" else None)
    except fechas.FechaInvalida as exc:
        raise ErrorDescripcion(f"{que} de «{e.valor}»: {exc}") from exc


def _crear_fecha(db: Session, expresion: str, i: fechas.Interpretacion, origen: str, confianza: float | None,
                 motor: str | None) -> Fecha:
    nodo = Fecha(id=uuid.uuid4(), expresion=expresion[:200], subtipo=i.subtipo, edtf=i.edtf, inicio=i.inicio, fin=i.fin,
                 normalizada=i.exacta, origen=origen, confianza=confianza, motor=motor)
    db.add(nodo)
    return nodo


def _relacionar(db: Session, origen: tuple[str, uuid.UUID], destino: tuple[str, uuid.UUID], codigo: str, categoria: str,
                usuario_id: uuid.UUID, procedencia: tuple[str, float | None, str | None], **extra) -> None:
    """Relación del grafo de contexto; si ya existe vigente (entidades
    reutilizadas entre documentos), no se duplica."""
    if db.scalar(select(Relacion.id).where(Relacion.origen_id == origen[1], Relacion.destino_id == destino[1],
                                           Relacion.codigo_ric == codigo, Relacion.estado == "vigente").limit(1)):
        return
    db.add(Relacion(origen_tipo=origen[0], origen_id=origen[1], destino_tipo=destino[0], destino_id=destino[1],
                    tipo_relacion=categoria, codigo_ric=codigo, origen=procedencia[0], confianza=procedencia[1],
                    motor=procedencia[2], confirmada_por_id=usuario_id, **extra))


def _agregar_entidades(db: Session, recurso: RecursoDocumental, entidades: list[EntidadConfirmada],
                       propuesta: dict, usuario_id: uuid.UUID, documentos: set[str]) -> dict[str, dict]:
    """Crea los nodos y relaciones de lo confirmado. Devuelve, por clave, lo
    que quedó de verdad (para comparar con la propuesta del motor)."""
    propuestas = {p["clave"]: p for p in propuesta.get("entidades", []) if p.get("clave")}
    motor = propuesta.get("motor")
    mecanismos.preparar_motor(db, recurso.fondo_id or recurso.id, motor, usuario_id)
    formas = [e for e in entidades if e.tipo == "forma_documental"]
    if len(formas) > 1:
        raise ErrorDescripcion("Un documento o conjunto tiene una sola forma documental; deje solo una.")
    por_clave = {e.clave: e for e in entidades if e.clave}
    nodos: dict[str, EntidadVocabulario] = {}
    finales: dict[str, dict] = {}
    # Las actividades van al final: necesitan los nodos de su tipo, su agente y su mandato.
    orden = sorted(range(len(entidades)), key=lambda k: entidades[k].tipo == "actividad")
    for i in orden:
        e = entidades[i]
        e.valor = " ".join((e.valor or "").split())
        if not e.valor:
            raise ErrorDescripcion("Hay una entidad sin valor; escríbalo o descártela.")
        if e.tipo not in TIPOS_ENTIDAD:
            raise ErrorDescripcion(f"Tipo de entidad desconocido: {e.tipo}.")
        base = propuestas.get(e.clave) if e.clave else None
        origen, confianza = _procedencia(e.valor, base.get("valor") if base else None, base.get("confianza") if base else None)
        motor_e = motor if base else None
        procedencia = (origen, confianza, motor_e)
        fragmento = e.fragmento if e.documento_id in documentos else None
        instanciacion_fragmento = uuid.UUID(e.documento_id) if fragmento else None
        # Página y zona del fragmento, calculadas aquí con el texto guardado
        # (no con lo que diga el navegador) y fijadas en la relación (RF-OCR-001).
        zona = servicio_evidencia.ubicar(db, instanciacion_fragmento, e.inicio, fragmento) if fragmento else None
        evidencia = {"fragmento": fragmento, "fragmento_instanciacion_id": instanciacion_fragmento,
                     "fragmento_inicio": e.inicio if fragmento else None,
                     "fragmento_pagina": zona["pagina"] if zona else None, "fragmento_zona": zona,
                     "propuesta_id": uuid.UUID(propuesta["propuesta_id"]) if base and propuesta.get("propuesta_id") else None}
        documento = ("recurso_documental", recurso.id)

        if e.tipo == "fecha":
            interpretacion = _interpretar_fecha(e, "La fecha")
            nodo_fecha = _crear_fecha(db, e.valor, interpretacion, origen, confianza, motor_e)
            db.flush()
            db.add(Relacion(origen_tipo="fecha", origen_id=nodo_fecha.id, destino_tipo="recurso_documental",
                            destino_id=recurso.id, tipo_relacion="temporal", codigo_ric="is_creation_date_of",
                            origen=origen, confianza=confianza, motor=motor_e, confirmada_por_id=usuario_id, **evidencia))
            if e.clave:
                finales[e.clave] = {"valor": e.valor, "edtf": interpretacion.edtf, "fecha_subtipo": interpretacion.subtipo,
                                    "codigo_ric": "is_creation_date_of"}
            continue

        if e.tipo == "agente":
            if e.rol not in ROLES_AGENTE:
                raise ErrorDescripcion(f"Indique el rol de «{e.valor}»: productor, autor, remitente, destinatario, "
                                       "acumulador, mencionado o custodio.")
            if e.subtipo not in SUBTIPOS_AGENTE and e.reutilizar_id:
                existente = db.get(EntidadVocabulario, uuid.UUID(str(e.reutilizar_id)))
                e.subtipo = existente.subtipo if existente is not None else None
            if e.subtipo not in SUBTIPOS_AGENTE:
                raise ErrorDescripcion(f"Indique qué tipo de agente es «{e.valor}»: persona, entidad corporativa, "
                                       "grupo, familia, cargo o mecanismo.")
        elif e.tipo == "mandato":
            e.subtipo = e.subtipo if e.subtipo in SUBTIPOS_MANDATO else "otro"
        else:
            e.subtipo = None
        if e.tipo == "lugar":
            # Tema del documento, o lugar donde se expidió (hallazgo CM-12).
            e.rol = "expedicion" if e.rol == "expedicion" else None
        if e.tipo == "tipo_actividad" and not any(x.tipo == "actividad" and x.tipo_clave == e.clave for x in entidades):
            raise ErrorDescripcion(f"El tipo de actividad «{e.valor}» no está asignado a ninguna actividad: "
                                   "asígneselo a una o descártelo. Un documento no se conecta a un tipo en abstracto.")
        if e.tipo == "agente" and e.rol == "autor":
            # RiC-O 1.1: rico:hasAuthor va de un Record a una persona, un grupo o un cargo.
            if recurso.nivel != "unidad_documental":
                raise ErrorDescripcion("El autor se declara en una unidad documental: en RiC, la autoría es de un "
                                       "documento, no de una agrupación ni de una parte. Para el conjunto, use productor.")
            if e.subtipo not in ("persona", "grupo", "cargo"):
                raise ErrorDescripcion(f"«{e.valor}» no puede ser autor: en RiC el autor es una persona, un grupo o un "
                                       "cargo. Una entidad corporativa o una familia van como productor.")
        nodo = _nodo_vocabulario(db, recurso.fondo_id, e, i, origen, confianza, motor_e, usuario_id)
        db.flush()
        if e.clave:
            nodos[e.clave] = nodo
            finales[e.clave] = {"valor": nodo.nombre, "rol": e.rol, "subtipo": e.subtipo}
        nodo_ref = ("entidad_vocabulario", nodo.id)

        if e.tipo == "forma_documental":
            recurso.forma_documental_id = nodo.id
        elif e.tipo == "lugar" and e.rol == "expedicion":
            codigo, categoria = RELACION_POR_ROL[("lugar", "expedicion")]
            db.add(Relacion(origen_tipo="entidad_vocabulario", origen_id=nodo.id, destino_tipo="recurso_documental",
                            destino_id=recurso.id, tipo_relacion=categoria, codigo_ric=codigo, rol="expedicion",
                            origen=origen, confianza=confianza, motor=motor_e, confirmada_por_id=usuario_id, **evidencia))
            if e.clave in finales:
                finales[e.clave]["codigo_ric"] = codigo
        elif e.tipo in ("agente", "lugar"):
            codigo, categoria = RELACION_POR_ROL[(e.tipo, e.rol if e.tipo == "agente" else None)]
            if e.tipo == "agente" and e.rol in ("productor", "custodio"):
                otro_rol = "productor" if e.rol == "custodio" else "custodio"
                if db.scalar(select(Relacion.id).where(
                        Relacion.origen_id == recurso.id, Relacion.destino_id == nodo.id, Relacion.estado == "vigente",
                        Relacion.codigo_ric == ("has_creator" if otro_rol == "productor" else "has_or_had_holder"))):
                    raise ErrorDescripcion(f"«{nodo.nombre}» ya es el {otro_rol} de este documento: el custodio se "
                                           "registra solo cuando es distinto del productor.")
            tramo = None
            if e.tipo == "agente" and e.rol == "custodio" and e.edtf:
                # Un tramo de la cadena de custodia, con sus fechas (hallazgo DES-05).
                tramo = _interpretar_fecha(e, "El periodo de la custodia").edtf
            db.add(Relacion(origen_tipo="recurso_documental", origen_id=recurso.id, destino_tipo="entidad_vocabulario",
                            destino_id=nodo.id, tipo_relacion=categoria, codigo_ric=codigo,
                            rol=e.rol if e.tipo == "agente" else "lugar", origen=origen, confianza=confianza, motor=motor_e,
                            confirmada_por_id=usuario_id, fecha_edtf=tramo,
                            nota=(e.nota or "").strip()[:500] or None if e.rol == "custodio" else None, **evidencia))
            if e.clave in finales:
                finales[e.clave]["codigo_ric"] = codigo
        elif e.tipo == "mandato":
            if e.edtf:
                expedicion = _interpretar_fecha(e, "La fecha de expedición")
                f = _crear_fecha(db, expedicion.legible, expedicion, origen, confianza, motor_e)
                db.flush()
                # R080 isCreationDateOf solo admite Record Resource o Instantiation
                # (hallazgo O-29): la expedición de un mandato es una fecha asociada.
                _relacionar(db, ("fecha", f.id), nodo_ref, "is_date_associated_with", "temporal", usuario_id,
                            procedencia, rol="expedicion")
                finales[e.clave or ""] = finales.get(e.clave or "", {}) | {"edtf": expedicion.edtf}
            regula = any(x.tipo == "actividad" and x.mandato_clave == e.clave for x in entidades)
            if e.clave in finales:
                finales[e.clave]["codigo_ric"] = "regulates_or_regulated" if regula else "has_or_had_subject"
            if not regula:
                # Citado sin una actividad que regule: queda como mencionado.
                db.add(Relacion(origen_tipo="recurso_documental", origen_id=recurso.id, destino_tipo="entidad_vocabulario",
                                destino_id=nodo.id, tipo_relacion="asociacion", codigo_ric="has_or_had_subject",
                                rol="mandato", origen=origen, confianza=confianza, motor=motor_e,
                                confirmada_por_id=usuario_id, **evidencia))
        elif e.tipo == "actividad":
            if e.clave in finales:
                finales[e.clave]["codigo_ric"] = "documents"
            db.add(Relacion(origen_tipo="recurso_documental", origen_id=recurso.id, destino_tipo="entidad_vocabulario",
                            destino_id=nodo.id, tipo_relacion="asociacion", codigo_ric="documents",
                            origen=origen, confianza=confianza, motor=motor_e, confirmada_por_id=usuario_id, **evidencia))
            enlaces = {}
            for campo, tipo_esperado in (("tipo_clave", "tipo_actividad"), ("agente_clave", "agente"),
                                         ("mandato_clave", "mandato")):
                clave = getattr(e, campo)
                if not clave:
                    continue
                if clave not in nodos or por_clave[clave].tipo != tipo_esperado:
                    raise ErrorDescripcion(f"La actividad «{e.valor}» apunta a una entidad que no está entre las "
                                           "confirmadas (quizá se descartó). Revise su tipo, agente o mandato.")
                enlaces[campo] = clave
            if "tipo_clave" in enlaces:
                _relacionar(db, nodo_ref, ("entidad_vocabulario", nodos[enlaces["tipo_clave"]].id),
                            "has_activity_type", "asociacion", usuario_id, procedencia)
            if "agente_clave" in enlaces:
                _relacionar(db, ("entidad_vocabulario", nodos[enlaces["agente_clave"]].id), nodo_ref,
                            "performs_or_performed", "asociacion", usuario_id, procedencia)
            if "mandato_clave" in enlaces:
                mandato = ("entidad_vocabulario", nodos[enlaces["mandato_clave"]].id)
                _relacionar(db, mandato, nodo_ref, "regulates_or_regulated", "asociacion", usuario_id, procedencia)
                if "agente_clave" in enlaces:
                    _relacionar(db, mandato, ("entidad_vocabulario", nodos[enlaces["agente_clave"]].id),
                                "authorizes", "asociacion", usuario_id, procedencia)
            mayor = None
            if e.actividad_mayor_clave:
                if e.actividad_mayor_clave not in nodos or por_clave[e.actividad_mayor_clave].tipo != "actividad":
                    raise ErrorDescripcion(f"La actividad mayor de «{e.valor}» no está entre las confirmadas.")
                mayor = nodos[e.actividad_mayor_clave]
            elif e.actividad_mayor_id:
                mayor = db.get(EntidadVocabulario, e.actividad_mayor_id)
                if mayor is None or mayor.clase != "actividad" or mayor.fondo_id != recurso.fondo_id:
                    raise ErrorDescripcion(f"La actividad mayor elegida para «{e.valor}» no es una actividad del fondo.")
                while mayor.estado == "fusionada" and mayor.fusionada_en_id:
                    mayor = db.get(EntidadVocabulario, mayor.fusionada_en_id)
            if mayor is not None:
                _sub_actividad(db, mayor, nodo, e.valor, usuario_id, procedencia)
                enlaces["actividad_mayor"] = str(mayor.id)
            if e.edtf:
                periodo = _interpretar_fecha(e, "El periodo")
                f = _crear_fecha(db, periodo.legible, periodo, origen, confianza, motor_e)
                db.flush()
                _relacionar(db, ("fecha", f.id), nodo_ref, "is_date_associated_with", "temporal", usuario_id, procedencia)
            if e.clave:
                finales[e.clave] |= {"edtf": e.edtf, **{c: enlaces.get(c) for c in ("tipo_clave", "agente_clave",
                                                                                     "mandato_clave",
                                                                                     "actividad_mayor")}}
    return finales


def _sub_actividad(db: Session, mayor: EntidadVocabulario, sub: EntidadVocabulario, valor: str,
                   usuario_id: uuid.UUID, procedencia) -> None:
    """mayor → sub (rico:hasDirectSubevent), con las mismas reglas que en
    vocabularios: una sola actividad mayor y sin ciclos."""
    from app.servicios import autoridad

    if mayor.id == sub.id:
        raise ErrorDescripcion(f"«{valor}» no puede ser sub-actividad de sí misma.")
    v = autoridad.VINCULOS["actividad_mayor"]
    superiores = autoridad._superiores(db, v, sub.id)
    if superiores and mayor.id not in superiores:
        raise ErrorDescripcion(f"«{valor}» ya es sub-actividad de otra actividad; corríjalo en vocabularios.")
    if not superiores:
        if autoridad._crearia_ciclo(db, v, mayor.id, sub.id):
            raise ErrorDescripcion(f"Hacer de «{valor}» una sub-actividad formaría un ciclo.")
        _relacionar(db, ("entidad_vocabulario", mayor.id), ("entidad_vocabulario", sub.id), "has_direct_subevent",
                    "inclusion", usuario_id, procedencia)


# --- Evidencia del trabajo con IA: una decisión por propuesta ------------------------------------

CAMPOS_DECISION = {
    "agente": ("valor", "rol", "subtipo"), "lugar": ("valor",), "forma_documental": ("valor",),
    "tipo_actividad": ("valor",), "mandato": ("valor", "subtipo", "edtf"), "fecha": ("valor", "edtf", "fecha_subtipo"),
    "actividad": ("valor", "edtf", "tipo_clave", "agente_clave", "mandato_clave"),
}


def _comparable(campos: tuple, datos: dict) -> dict:
    return {c: (" ".join(str(datos.get(c)).split()) if datos.get(c) is not None else None) for c in campos}


def codigo_de_decision(tipo: str, datos: dict | None, propuesta: dict | None = None) -> str | None:
    """Qué relación (o atributo) del grafo afecta una decisión: la que creó
    la publicación o, si se rechazó, la que habría creado. Para la columna
    «propiedad RiC-O» del panel de decisiones."""
    datos = datos or {}
    if datos.get("codigo_ric"):
        return datos["codigo_ric"]
    if tipo == "forma_documental":
        return "forma_documental"
    if tipo == "tipo_actividad":
        return "has_activity_type"
    if tipo == "mandato":
        citado = any(x.get("tipo") == "actividad" and x.get("mandato_clave") == datos.get("clave")
                     for x in (propuesta or {}).get("entidades", []))
        return "regulates_or_regulated" if citado else "has_or_had_subject"
    par = RELACION_POR_ROL.get((tipo, datos.get("rol") if tipo == "agente" else None))
    return par[0] if par else None


def registrar_decisiones(db: Session, recurso: RecursoDocumental, propuesta: dict, finales: dict[str, dict],
                         manuales: list[EntidadConfirmada], titulo: str, alcance: str, usuario_id: uuid.UUID) -> int:
    """Compara cada propuesta del motor con lo que quedó publicado y deja un
    evento de auditoría por cada una. El valor propuesto es el que guardó el
    servidor al abrir el espacio de trabajo, no lo que diga el navegador."""
    if not propuesta.get("disponible"):
        return 0
    motor = mecanismos.preparar_motor(db, recurso.fondo_id or recurso.id, propuesta.get("motor"), usuario_id)
    comun = {"modelo": propuesta.get("motor"), "mecanismo_id": str(motor.id) if motor else None,
             "version_prompt": propuesta.get("version_prompt"), "propuesta_id": propuesta.get("propuesta_id"),
             "version_modelo": propuesta.get("version_modelo"),
             "fondo_id": str(recurso.fondo_id), "titulo_documento": recurso.titulo}
    n = 0

    def evento(**datos):
        nonlocal n
        registrar(db, modulo="descripcion", accion="decision_ia", usuario_id=usuario_id,
                  entidad_tipo="recurso_documental", entidad_id=recurso.id, nuevo=comun | datos)
        n += 1

    for p in propuesta.get("entidades", []):
        campos = CAMPOS_DECISION.get(p["tipo"], ("valor",))
        propuesto = _comparable(campos, p)
        final = finales.get(p["clave"])
        if final is None:
            decision, final_c = "rechazada", None
        else:
            final_c = _comparable(campos, final)
            decision = "aceptada" if final_c == propuesto else "corregida"
        evento(decision=decision, tipo=p["tipo"], clave=p["clave"], confianza=p.get("confianza"),
               propuesto=propuesto, final=final_c, subtipo=(final or p).get("subtipo"),
               codigo_ric=codigo_de_decision(p["tipo"], final if final is not None else p, propuesta))
    for e in manuales:  # lo que el motor no propuso (omisiones del motor)
        final_m = finales.get(e.clave or "", {"valor": e.valor})
        evento(decision="agregada", tipo=e.tipo, clave=e.clave, confianza=None, propuesto=None,
               final=_comparable(CAMPOS_DECISION.get(e.tipo, ("valor",)), final_m), subtipo=e.subtipo,
               codigo_ric=codigo_de_decision(e.tipo, final_m | {"rol": e.rol, "clave": e.clave}))
    if propuesta.get("idiomas"):
        p_c, f_c = ",".join(sorted(propuesta["idiomas"])), ",".join(sorted(recurso.idiomas or []))
        evento(decision="aceptada" if p_c == f_c else ("rechazada" if not f_c else "corregida"), tipo="idioma",
               clave="idioma", confianza=propuesta.get("confianza_idiomas"), propuesto={"valor": p_c},
               final={"valor": f_c} if f_c else None)
    for tipo, propuesto, final in (("titulo", propuesta.get("titulo"), titulo), ("alcance", propuesta.get("alcance"), alcance)):
        if propuesto:
            p_c, f_c = " ".join(propuesto.split()), " ".join((final or "").split())
            evento(decision="aceptada" if p_c == f_c else ("rechazada" if not f_c else "corregida"), tipo=tipo,
                   clave=tipo, confianza=propuesta.get("confianza_alcance") if tipo == "alcance" else None,
                   propuesto={"valor": p_c}, final={"valor": f_c} if f_c else None)
    return n


# --- Campos propios del Record Resource (versión 3) ---------------------------------------------------


def _idiomas(valores) -> list[str] | None:
    from app.servicios.motor import idiomas_validos

    if valores is None:
        return None
    _cardinalidad("idiomas", valores)
    limpios = idiomas_validos(valores)
    if len(limpios) != len([v for v in valores if str(v or "").strip()]):
        raise ErrorDescripcion("Cada idioma se indica con su código ISO 639-3 de tres letras (spa, lat, eng…).")
    return limpios or None


def _cardinalidad(clave: str, valores) -> None:
    """La cardinalidad del catálogo de atributos (RF-RIC-002)."""
    from app.servicios import atributos

    try:
        atributos.validar_cardinalidad(clave, valores)
    except atributos.ErrorAtributo as exc:
        raise ErrorDescripcion(str(exc)) from exc


def _texto_libre(valor: str | None) -> str | None:
    return (valor or "").strip()[:5000] or None


def _aplicar_campos(recurso: RecursoDocumental, propuesta: dict, idiomas, acceso: str | None, uso: str | None) -> None:
    """Idioma con su procedencia (el motor puede proponerlo); condiciones de
    acceso y de uso, siempre de una persona."""
    if idiomas is not None:
        codigos = _idiomas(idiomas)
        propuestos = propuesta.get("idiomas") or None
        if codigos is None:
            recurso.idiomas = recurso.origen_idiomas = recurso.confianza_idiomas = None
        else:
            recurso.idiomas = codigos
            if propuestos is None:
                recurso.origen_idiomas, recurso.confianza_idiomas = "persona", None
            else:
                igual = sorted(codigos) == sorted(propuestos)
                recurso.origen_idiomas = "motor" if igual else "motor_editado"
                recurso.confianza_idiomas = propuesta.get("confianza_idiomas")
    if acceso is not None:
        recurso.condiciones_acceso = _texto_libre(acceso)
    if uso is not None:
        recurso.condiciones_uso = _texto_libre(uso)


def _historia(recurso: RecursoDocumental, texto: str | None) -> None:
    """Historia archivística (ISAD-G 3.2.3, hallazgo DES-06): la escribe una
    persona; el motor no la propone."""
    if texto is not None:
        recurso.historia_archivistica = _texto_libre(texto)
        recurso.origen_historia_archivistica = "persona" if recurso.historia_archivistica else None


def _isadg(recurso: RecursoDocumental, textos: dict | None, escrituras: list[str] | None) -> None:
    """Resto de los elementos de ISAD-G (hallazgo DES-07), de una persona."""
    from app.servicios import isadg

    if escrituras is not None:
        _cardinalidad("escrituras", escrituras)
    try:
        isadg.aplicar(recurso, textos, escrituras)
    except isadg.ErrorIsadg as exc:
        raise ErrorDescripcion(str(exc)) from exc


def _serie_de(db: Session, recurso: RecursoDocumental) -> uuid.UUID | None:
    """La serie o subserie más cercana por encima del documento."""
    actual, vistos = recurso, set()
    while actual is not None and actual.id not in vistos:
        vistos.add(actual.id)
        if actual.nivel in ("serie", "subserie"):
            return actual.id
        actual = db.get(RecursoDocumental, actual.incluido_en_id) if actual.incluido_en_id else None
    return None


def _secuencia(db: Session, recurso: RecursoDocumental, otro_id: uuid.UUID, posicion: str,
               usuario_id: uuid.UUID) -> None:
    """Declara que este documento precede o sigue a otro de la misma serie
    (RiC-R008 precedes or preceded; la fila va del anterior al siguiente)."""
    otro = db.get(RecursoDocumental, otro_id)
    if otro is None or otro.publicado_en is None or otro.fondo_id != recurso.fondo_id or otro.id == recurso.id:
        raise ErrorDescripcion("El documento de la secuencia debe ser otra descripción publicada del mismo fondo.")
    if otro.nivel in ("fondo", "seccion", "subseccion", "serie", "subserie"):
        raise ErrorDescripcion("La secuencia une documentos o expedientes, no series ni fondos.")
    serie_a, serie_b = _serie_de(db, recurso), _serie_de(db, otro)
    misma = serie_a == serie_b if (serie_a or serie_b) else recurso.incluido_en_id == otro.incluido_en_id
    if not misma:
        raise ErrorDescripcion(f"«{otro.titulo}» no está en la misma serie: la secuencia es entre documentos de una "
                               "misma serie.")
    anterior, siguiente = (recurso, otro) if posicion == "precede" else (otro, recurso)
    if db.scalar(select(Relacion.id).where(Relacion.codigo_ric == "precedes_or_preceded", Relacion.estado == "vigente",
                                           Relacion.origen_id == siguiente.id, Relacion.destino_id == anterior.id)):
        raise ErrorDescripcion("Esa secuencia contradice otra ya registrada (al revés).")
    _relacionar(db, ("recurso_documental", anterior.id), ("recurso_documental", siguiente.id), "precedes_or_preceded",
                "temporal", usuario_id, ("persona", None, None))


@dataclass
class ParteConfirmada:
    titulo: str
    tipo_parte: EntidadConfirmada | None = None
    alcance: str | None = None
    recorte: dict | None = None  # {instanciacion_id, pagina, x, y, ancho, alto}


def _partes(db: Session, recurso: RecursoDocumental, partes: list[ParteConfirmada], usuario_id: uuid.UUID,
            instanciaciones_validas: set[str]) -> list[RecursoDocumental]:
    """Cada parte es un Record Resource de nivel parte documental (RiC-E05
    Record Part) dentro de la unidad documental, unido por RiC-R003 has or
    had constituent; puede llevar su propio recorte como instanciación."""
    from app.servicios import recorte as servicio_recorte

    if not partes:
        return []
    if recurso.nivel != "unidad_documental":
        raise ErrorDescripcion("Las partes documentales se registran dentro de una unidad documental.")
    creadas, recortes = [], db.info.setdefault("recortes_nuevos", [])
    for k, p in enumerate(partes):
        titulo = " ".join((p.titulo or "").split())
        if len(titulo) < 2:
            raise ErrorDescripcion("Cada parte documental lleva un título (por ejemplo «Sello de la Alcaldía»).")
        parte = RecursoDocumental(id=uuid.uuid4(), nivel="parte_documental", titulo=titulo[:300],
                                  alcance_contenido=_texto_libre(p.alcance), fondo_id=recurso.fondo_id,
                                  incluido_en_id=recurso.id, creado_por_id=usuario_id, origen_titulo="persona",
                                  origen_alcance="persona" if _texto_libre(p.alcance) else None,
                                  publicado_en=ahora(), publicado_por_id=usuario_id)
        db.add(parte)
        db.flush()
        if p.tipo_parte is not None and (p.tipo_parte.valor or "").strip():
            p.tipo_parte.tipo = "tipo_parte"
            p.tipo_parte.valor = " ".join(p.tipo_parte.valor.split())
            tipo = _nodo_vocabulario(db, recurso.fondo_id, p.tipo_parte, k, "persona", None, None, usuario_id)
            db.flush()
            parte.tipo_parte_id = tipo.id
        _relacionar(db, ("recurso_documental", recurso.id), ("recurso_documental", parte.id), "has_or_had_constituent",
                    "inclusion", usuario_id, ("persona", None, None))
        if p.recorte:
            origen_id = str(p.recorte.get("instanciacion_id") or "")
            if origen_id not in instanciaciones_validas:
                raise ErrorDescripcion("El recorte debe salir de uno de los documentos de esta descripción.")
            origen = db.get(Instanciacion, uuid.UUID(origen_id))
            try:
                inst = servicio_recorte.recortar(db, origen, p.recorte, titulo, usuario_id)
            except servicio_recorte.ErrorRecorte as exc:
                raise ErrorDescripcion(f"Recorte de «{titulo}»: {exc}") from exc
            recortes.append(inst)
            db.add(Relacion(origen_tipo="recurso_documental", origen_id=parte.id, destino_tipo="instanciacion",
                            destino_id=inst.id, tipo_relacion="asociacion", codigo_ric="has_or_had_instantiation",
                            origen="persona", confirmada_por_id=usuario_id))
        creadas.append(parte)
    db.flush()
    return creadas


def _superior(db: Session, fondo_id: uuid.UUID, nivel: str, incluido_en_id: uuid.UUID | None) -> RecursoDocumental:
    superior = db.get(RecursoDocumental, incluido_en_id) if incluido_en_id else db.get(RecursoDocumental, fondo_id)
    if superior is None or superior.fondo_id != fondo_id:
        raise ErrorDescripcion("El nivel superior elegido no pertenece a este fondo.")
    if rango(superior.nivel) >= rango(nivel):
        raise ErrorDescripcion(f"Un {nivel.replace('_', ' ')} no puede quedar dentro de un {superior.nivel.replace('_', ' ')}.")
    return superior


def publicar(db: Session, *, trabajo: TrabajoDescripcion, usuario_id: uuid.UUID, titulo: str, alcance: str,
             incluido_en_id: uuid.UUID | None, entidades: list[EntidadConfirmada], idiomas: list[str] | None = None,
             condiciones_acceso: str | None = None, condiciones_uso: str | None = None,
             precede_a_id: uuid.UUID | None = None, sigue_a_id: uuid.UUID | None = None,
             partes: list[ParteConfirmada] | None = None,
             historia_archivistica: str | None = None, isadg_textos: dict | None = None,
             escrituras: list[str] | None = None) -> RecursoDocumental:
    """Crea en una sola transacción el Record Resource, sus entidades y
    relaciones, la inclusión y el vínculo con las instanciaciones. Si algo
    falla, no queda nada a medias (quien llama hace rollback)."""
    titulo = " ".join((titulo or "").split())
    if len(titulo) < 3:
        raise ErrorDescripcion("Escriba el título de la descripción.")
    documentos = documentos_de(db, trabajo)
    ids_documentos = {str(d.id) for d in documentos}
    if db.scalar(select(Relacion.id).where(Relacion.destino_id.in_([d.id for d in documentos]),
                                           Relacion.codigo_ric == "has_or_had_instantiation",
                                           Relacion.estado == "vigente").limit(1)):
        raise ErrorDescripcion("Alguno de estos documentos ya fue descrito.", 409)
    propuesta = _propuesta(trabajo)
    # El motor que propuso es el agente mecanismo del vocabulario del fondo.
    mecanismos.preparar_motor(db, trabajo.fondo_id, propuesta.get("motor"), usuario_id)
    superior = _superior(db, trabajo.fondo_id, trabajo.nivel, incluido_en_id)
    origen_titulo, _ = _procedencia(titulo, propuesta.get("titulo") or None, None)
    origen_alcance, confianza_alcance = _procedencia(alcance, propuesta.get("alcance") or None,
                                                     propuesta.get("confianza_alcance"))
    momento = ahora()
    recurso = RecursoDocumental(
        id=uuid.uuid4(), nivel=trabajo.nivel, titulo=titulo[:300], alcance_contenido=(alcance or "").strip() or None,
        fondo_id=trabajo.fondo_id, incluido_en_id=superior.id, creado_por_id=usuario_id,
        origen_titulo=origen_titulo, origen_alcance=origen_alcance if (alcance or "").strip() else None,
        confianza_alcance=confianza_alcance if (alcance or "").strip() else None,
        motor=propuesta.get("motor") if origen_titulo != "persona" or origen_alcance != "persona" else None,
        publicado_en=momento, publicado_por_id=usuario_id,
    )
    _aplicar_campos(recurso, propuesta, idiomas if idiomas is not None else [], condiciones_acceso, condiciones_uso)
    _historia(recurso, historia_archivistica)
    _isadg(recurso, isadg_textos, escrituras)
    db.add(recurso)
    db.flush()
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=superior.id, destino_tipo="recurso_documental",
                    destino_id=recurso.id, tipo_relacion="inclusion", codigo_ric="includes_or_included",
                    origen="persona", confirmada_por_id=usuario_id))
    if precede_a_id:
        _secuencia(db, recurso, precede_a_id, "precede", usuario_id)
    if sigue_a_id:
        _secuencia(db, recurso, sigue_a_id, "sigue", usuario_id)
    for d in documentos + _derivadas(db, [d.id for d in documentos]):
        db.add(Relacion(origen_tipo="recurso_documental", origen_id=recurso.id, destino_tipo="instanciacion",
                        destino_id=d.id, tipo_relacion="asociacion", codigo_ric="has_or_had_instantiation",
                        origen="persona", confirmada_por_id=usuario_id))
    claves_propuestas = {p.get("clave") for p in propuesta.get("entidades", [])}
    for k, e in enumerate(entidades):  # toda entidad lleva clave, para enlazar la cadena de la actividad
        e.clave = e.clave or f"m{k + 1}"
    finales = _agregar_entidades(db, recurso, entidades, propuesta, usuario_id, ids_documentos)
    # Las partes van al final: un recorte escribe un archivo, que solo vale
    # la pena escribir cuando todo lo demás ya pasó la validación.
    _partes(db, recurso, partes or [], usuario_id, ids_documentos)
    _cerrar(db, trabajo, "publicado")
    trabajo.recurso_id = recurso.id
    if trabajo.propuesta_id:
        from app.models.evidencia_ia import PropuestaIA

        db.get(PropuestaIA, trabajo.propuesta_id).recurso_id = recurso.id
    db.flush()
    registrar(db, modulo="descripcion", accion="descripcion_publicada", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=recurso.id, nuevo=resumen(db, recurso))
    registrar_decisiones(db, recurso, propuesta, finales, [e for e in entidades if e.clave not in claves_propuestas],
                         titulo, alcance, usuario_id)
    return recurso


def versionar(db: Session, recurso: RecursoDocumental, motivo: str, usuario_id: uuid.UUID | None,
              hubo_cambio: bool = False) -> None:
    """La versión de la descripción tras publicar o corregir (RF-RIC-001)."""
    from app.servicios import versiones

    versiones.registrar(db, recurso, motivo, usuario_id, hubo_cambio=hubo_cambio)


# --- Lectura (interna) y corrección posterior -------------------------------------------------------


def _clasificacion_de(db: Session, recurso: RecursoDocumental) -> dict:
    """La clasificación propia (Ley 1712) y, si no tiene, la que hereda."""
    from app.servicios import derechos

    propia = derechos._vigente(db, recurso.id)
    rige = propia or derechos.declaracion_de_recurso(db, recurso)
    datos = lambda d: {"acceso": d.acceso, "fundamento": d.fundamento, "reproduccion": d.reproduccion,  # noqa: E731
                       "vigente_hasta": d.vigente_hasta.isoformat() if d.vigente_hasta else None}
    heredada = None
    if propia is None and rige is not None:
        origen = db.get(RecursoDocumental, rige.entidad_id)
        heredada = datos(rige) | {"de": origen.titulo if origen else None}
    return {"clasificacion": datos(propia) if propia else None, "clasificacion_heredada": heredada}


def detalle(db: Session, recurso: RecursoDocumental) -> dict:
    """Vista interna completa, con origen y confianza de cada dato. Solo
    para las pantallas de trabajo y la auditoría."""
    from app.servicios import propuestas_ia

    superior = db.get(RecursoDocumental, recurso.incluido_en_id) if recurso.incluido_en_id else None
    forma = db.get(EntidadVocabulario, recurso.forma_documental_id) if recurso.forma_documental_id else None
    entidades, instanciaciones = [], []
    relaciones = db.scalars(select(Relacion).where(
        Relacion.estado == "vigente",
        ((Relacion.origen_id == recurso.id) | (Relacion.destino_id == recurso.id)))
        .order_by(Relacion.creado_en)).all()
    partes, parte_de, secuencia = [], None, []
    for r in relaciones:
        if r.codigo_ric == "includes_or_included":
            continue
        if r.codigo_ric == "has_or_had_constituent":
            otro = db.get(RecursoDocumental, r.destino_id if r.origen_id == recurso.id else r.origen_id)
            if otro is None:
                continue
            breve = {"id": str(otro.id), "titulo": otro.titulo, "nivel": otro.nivel, "relacion_id": str(r.id)}
            if r.origen_id == recurso.id:
                tipo_parte = db.get(EntidadVocabulario, otro.tipo_parte_id) if otro.tipo_parte_id else None
                recortes = db.scalars(select(Instanciacion).join(Relacion, Relacion.destino_id == Instanciacion.id).where(
                    Relacion.origen_id == otro.id, Relacion.codigo_ric == "has_or_had_instantiation",
                    Relacion.estado == "vigente")).all()
                partes.append(breve | {"tipo_parte": tipo_parte.nombre if tipo_parte else None,
                                       "alcance_contenido": otro.alcance_contenido,
                                       "instanciaciones": [{"id": str(i.id), "nombre": i.nombre_original,
                                                            "recorte_zona": i.recorte_zona} for i in recortes]})
            else:
                parte_de = breve
            continue
        if r.codigo_ric == "precedes_or_preceded":
            otro = db.get(RecursoDocumental, r.destino_id if r.origen_id == recurso.id else r.origen_id)
            if otro is not None:
                secuencia.append({"relacion_id": str(r.id), "id": str(otro.id), "titulo": otro.titulo,
                                  "posicion": "precede_a" if r.origen_id == recurso.id else "sigue_a",
                                  "uri_rico": "rico:precedesOrPreceded" if r.origen_id == recurso.id
                                  else "rico:followsOrFollowed"})
            continue
        if r.codigo_ric == "has_or_had_instantiation":
            inst = db.get(Instanciacion, r.destino_id)
            if inst:
                instanciaciones.append({"id": str(inst.id), "nombre": inst.nombre_original,
                                        "custodios": custodios_de(db, inst.id),
                                        **({"fisica": True, "soporte": inst.soporte, "ubicacion": inst.ubicacion_fisica,
                                            "caracteristicas_fisicas": inst.caracteristicas_fisicas,
                                            **{c: getattr(inst, c) for c in CAMPOS_FISICO_AGN},
                                            "signatura": signatura_topografica(inst)}
                                           if inst.estado == "registro_fisico" else {})})
            continue
        nodo_tipo, nodo_id = (r.origen_tipo, r.origen_id) if r.destino_id == recurso.id else (r.destino_tipo, r.destino_id)
        if nodo_tipo == "entidad_vocabulario":
            n = db.get(EntidadVocabulario, nodo_id)
            tipo, valor, subtipo, extra = n.clase, n.nombre, n.subtipo, {}
            if r.destino_original_id and r.destino_original_id != n.id:
                # La relación se redirigió al fusionar: se conserva a qué
                # entidad citaba el documento originalmente (módulo 3).
                antes = db.get(EntidadVocabulario, r.destino_original_id)
                extra = {"antes_de_fusion": {"id": str(antes.id), "nombre": antes.nombre}} if antes else {}
            if n.clase == "actividad":
                extra |= {"contexto": contexto_actividad(db, n.id)}
            if n.clase == "mandato":
                extra |= {"expedicion": _fecha_de(db, n.id, "is_date_associated_with")}
        elif nodo_tipo == "fecha":
            n = db.get(Fecha, nodo_id)
            tipo, valor, subtipo = "fecha", n.expresion, None
            extra = {"fecha_normalizada": n.normalizada.isoformat() if n.normalizada else None,
                     **_fecha_publica(n)}
        else:
            continue
        entidades.append({
            "relacion_id": str(r.id), "entidad_id": str(nodo_id), "tipo": tipo, "valor": valor, "subtipo": subtipo,
            "rol": r.rol, "codigo_ric": r.codigo_ric, "uri_rico": ric_o.uri(r.codigo_ric),
            "fragmento": r.fragmento, "documento_id": str(r.fragmento_instanciacion_id) if r.fragmento_instanciacion_id else None,
            "pagina": r.fragmento_pagina, "zona": r.fragmento_zona,
            "propuesta_id": str(r.propuesta_id) if r.propuesta_id else None,
            "origen": r.origen, "confianza": r.confianza, "motor": r.motor, "estado_revision": r.estado_revision, **extra,
            **({"periodo": r.fecha_edtf, "periodo_legible": fechas.legible(r.fecha_edtf), "nota": r.nota}
               if r.codigo_ric == "has_or_had_holder" else {}),
        })
    return {
        "id": str(recurso.id), "nivel": recurso.nivel, "titulo": recurso.titulo,
        "alcance_contenido": recurso.alcance_contenido, "fondo_id": str(recurso.fondo_id),
        **_clasificacion_de(db, recurso),
        "incluido_en": {"id": str(superior.id), "titulo": superior.titulo, "nivel": superior.nivel} if superior else None,
        "forma_documental": {"id": str(forma.id), "nombre": forma.nombre, "origen": forma.origen} if forma else None,
        "entidades": entidades, "instanciaciones": instanciaciones, "control": control_de(recurso),
        "proteccion": {"datos_personales": recurso.datos_personales, "nota_accesibilidad": recurso.nota_accesibilidad},
        # Cada atributo con su fuente y su cardinalidad (RF-RIC-002).
        "atributos": atributos_con_fuente(recurso),
        # Las propuestas del motor que llevaron a esta descripción (RF-AI-002).
        "propuestas_ia": [propuestas_ia.out(p) for p in propuestas_ia.de_recurso(db, recurso.id)],
        "idiomas": recurso.idiomas or [], "origen_idiomas": recurso.origen_idiomas,
        "confianza_idiomas": recurso.confianza_idiomas,
        "condiciones_acceso": recurso.condiciones_acceso, "condiciones_uso": recurso.condiciones_uso,
        "historia_archivistica": recurso.historia_archivistica,
        "origen_historia_archivistica": recurso.origen_historia_archivistica,
        "isadg": _isadg_valores(recurso),
        "tipo_parte": _vocab_breve(db, recurso.tipo_parte_id) if recurso.tipo_parte_id else None,
        "partes": partes, "parte_de": parte_de, "secuencia": secuencia,
        "origen_titulo": recurso.origen_titulo, "origen_alcance": recurso.origen_alcance,
        "confianza_alcance": recurso.confianza_alcance, "motor": recurso.motor,
        "publicado_en": recurso.publicado_en.isoformat() if recurso.publicado_en else None,
        "actualizado_en": recurso.actualizado_en.isoformat() if recurso.actualizado_en else None,
    }


def _isadg_valores(recurso: RecursoDocumental) -> dict:
    from app.servicios import isadg

    return isadg.valores(recurso)


def _fecha_publica(f: Fecha) -> dict:
    return {"fecha_subtipo": f.subtipo, "edtf": f.edtf, "fecha_legible": fechas.legible(f.edtf, f.expresion),
            "calendario": f.calendario,
            "fecha_inicio": f.inicio.isoformat() if f.inicio else None, "fecha_fin": f.fin.isoformat() if f.fin else None}


def _fecha_de(db: Session, nodo_id: uuid.UUID, codigo: str) -> dict | None:
    f_id = db.scalar(select(Relacion.origen_id).where(Relacion.destino_id == nodo_id, Relacion.codigo_ric == codigo,
                                                      Relacion.estado == "vigente", Relacion.origen_tipo == "fecha"))
    f = db.get(Fecha, f_id) if f_id else None
    return _fecha_publica(f) if f else None


def _vocab_breve(db: Session, entidad_id: uuid.UUID) -> dict | None:
    v = db.get(EntidadVocabulario, entidad_id)
    return {"id": str(v.id), "nombre": v.nombre, "subtipo": v.subtipo} if v else None


def contexto_actividad(db: Session, actividad_id: uuid.UUID) -> dict:
    """La cadena documento → actividad → tipo de actividad → mandato, con el
    agente que la ejerce, tal como quedó en el grafo (relaciones vigentes)."""
    def destinos(codigo):
        return db.scalars(select(Relacion.destino_id).where(Relacion.origen_id == actividad_id,
                                                            Relacion.codigo_ric == codigo, Relacion.estado == "vigente")).all()

    def origenes(codigo):
        return db.scalars(select(Relacion.origen_id).where(Relacion.destino_id == actividad_id, Relacion.codigo_ric == codigo,
                                                           Relacion.estado == "vigente",
                                                           Relacion.origen_tipo == "entidad_vocabulario")).all()

    tipos = [t for t in (_vocab_breve(db, i) for i in destinos("has_activity_type")) if t]
    agentes = [a for a in (_vocab_breve(db, i) for i in origenes("performs_or_performed")) if a]
    mandatos = []
    for i in origenes("regulates_or_regulated"):
        m = _vocab_breve(db, i)
        if m:
            mandatos.append(m | {"expedicion": _fecha_de(db, i, "is_date_associated_with")})
    return {"tipo_actividad": tipos[0] if tipos else None, "tipos_actividad": tipos, "ejercida_por": agentes,
            "regulada_por": mandatos, "periodo": _fecha_de(db, actividad_id, "is_date_associated_with")}


# Datos de control del inventario (FUID), que escribe siempre una persona.
CAMPOS_CONTROL = ("codigo_referencia", "caja", "carpeta", "folios", "soporte", "tomo", "otra_unidad", "frecuencia_consulta")


def control_de(recurso: RecursoDocumental) -> dict:
    return {c: getattr(recurso, c) for c in CAMPOS_CONTROL}


def atributos_con_fuente(recurso: RecursoDocumental) -> list[dict]:
    from app.servicios import atributos

    return atributos.con_fuente(recurso)


def resumen(db: Session, recurso: RecursoDocumental) -> dict:
    """Lo que queda en auditoría: los datos descriptivos, con su procedencia."""
    d = detalle(db, recurso)
    return {
        "titulo": d["titulo"], "alcance_contenido": d["alcance_contenido"], "nivel": d["nivel"],
        "incluido_en": d["incluido_en"]["titulo"] if d["incluido_en"] else None,
        "forma_documental": d["forma_documental"]["nombre"] if d["forma_documental"] else None,
        "entidades": sorted(f"{e['tipo']}:{e['rol'] or ''}:{e['valor']} [{e['origen']}]" for e in d["entidades"]),
        "instanciaciones": sorted(i["nombre"] for i in d["instanciaciones"]),
        "idiomas": d["idiomas"], "condiciones_acceso": d["condiciones_acceso"], "condiciones_uso": d["condiciones_uso"],
        "partes": sorted(f"{p['titulo']} [{p['tipo_parte'] or ''}]" for p in d["partes"]),
        "secuencia": sorted(f"{x['posicion']}:{x['titulo']}" for x in d["secuencia"]),
        "historia_archivistica": d["historia_archivistica"], **d["isadg"],
        **control_de(recurso),
    }


def reabrir(db: Session, recurso: RecursoDocumental, usuario_id: uuid.UUID) -> TrabajoDescripcion:
    expirar(db)
    otro = db.scalar(select(TrabajoDescripcion).where(TrabajoDescripcion.recurso_id == recurso.id,
                                                      TrabajoDescripcion.estado == "abierto"))
    if otro is not None and otro.usuario_id != usuario_id:
        quien = db.get(Usuario, otro.usuario_id)
        raise ErrorDescripcion(f"Esta descripción está en edición por {quien.nombre if quien else 'otra persona'}.", 409)
    if otro is not None:
        otro.ultima_actividad = ahora()
        return otro
    trabajo = TrabajoDescripcion(id=uuid.uuid4(), usuario_id=usuario_id, fondo_id=recurso.fondo_id,
                                 nivel=recurso.nivel, recurso_id=recurso.id)
    db.add(trabajo)
    db.flush()
    return trabajo


def editar(db: Session, *, recurso: RecursoDocumental, trabajo: TrabajoDescripcion, usuario_id: uuid.UUID,
           titulo: str | None, alcance: str | None, incluido_en_id: uuid.UUID | None,
           anular: list[uuid.UUID], quitar_forma: bool, agregar: list[EntidadConfirmada],
           control: dict | None = None, idiomas: list[str] | None = None, condiciones_acceso: str | None = None,
           condiciones_uso: str | None = None, precede_a_id: uuid.UUID | None = None,
           sigue_a_id: uuid.UUID | None = None, agregar_partes: list[ParteConfirmada] | None = None,
           historia_archivistica: str | None = None, isadg_textos: dict | None = None,
           escrituras: list[str] | None = None) -> bool:
    """Aplica la corrección. Devuelve si algo cambió."""
    if trabajo.recurso_id != recurso.id:
        raise ErrorDescripcion("Este espacio de trabajo no corresponde a esta descripción.", 409)
    anterior = resumen(db, recurso)
    if titulo is not None:
        titulo = " ".join(titulo.split())
        if len(titulo) < 3:
            raise ErrorDescripcion("Escriba el título de la descripción.")
        if titulo != recurso.titulo:
            recurso.titulo, recurso.origen_titulo = titulo[:300], "persona"
    if alcance is not None and alcance.strip() != (recurso.alcance_contenido or ""):
        recurso.alcance_contenido = alcance.strip() or None
        recurso.origen_alcance = "persona" if alcance.strip() else None
        recurso.confianza_alcance = None
    if incluido_en_id is not None and incluido_en_id != recurso.incluido_en_id:
        superior = _superior(db, recurso.fondo_id, recurso.nivel, incluido_en_id)
        # Solo la inclusión orgánica; las adicionales (rol «adicional») siguen (CM-21).
        db.execute(update(Relacion).where(Relacion.destino_id == recurso.id, Relacion.codigo_ric == "includes_or_included",
                                          Relacion.estado == "vigente", Relacion.rol.is_(None))
                   .values(estado="anulada", anulada_en=ahora(), anulada_por_id=usuario_id))
        recurso.incluido_en_id = superior.id
        db.add(Relacion(origen_tipo="recurso_documental", origen_id=superior.id, destino_tipo="recurso_documental",
                        destino_id=recurso.id, tipo_relacion="inclusion", codigo_ric="includes_or_included",
                        origen="persona", confirmada_por_id=usuario_id))
    for relacion_id in anular:
        r = db.get(Relacion, relacion_id)
        if r is None or recurso.id not in (r.origen_id, r.destino_id) or r.codigo_ric in (
                "has_or_had_instantiation", "includes_or_included"):
            raise ErrorDescripcion("Una de las relaciones a quitar no pertenece a esta descripción.")
        r.estado, r.anulada_en, r.anulada_por_id = "anulada", ahora(), usuario_id
    if quitar_forma:
        recurso.forma_documental_id = None
    for campo, valor in (control or {}).items():
        if campo in CAMPOS_CONTROL:
            setattr(recurso, campo, (" ".join(valor.split()) or None) if isinstance(valor, str) else valor)
    if idiomas is not None and sorted(_idiomas(idiomas) or []) != sorted(recurso.idiomas or []):
        _aplicar_campos(recurso, {}, idiomas, None, None)
    _aplicar_campos(recurso, {}, None, condiciones_acceso, condiciones_uso)
    _historia(recurso, historia_archivistica)
    _isadg(recurso, isadg_textos, escrituras)
    if precede_a_id:
        _secuencia(db, recurso, precede_a_id, "precede", usuario_id)
    if sigue_a_id:
        _secuencia(db, recurso, sigue_a_id, "sigue", usuario_id)
    if any(e.tipo == "forma_documental" for e in agregar) and recurso.forma_documental_id and not quitar_forma:
        raise ErrorDescripcion("Ya tiene forma documental; quítela antes de poner otra.")
    documentos = {str(r.destino_id) for r in db.scalars(select(Relacion).where(
        Relacion.origen_id == recurso.id, Relacion.codigo_ric == "has_or_had_instantiation", Relacion.estado == "vigente"))}
    for k, e in enumerate(agregar):
        e.clave = e.clave or f"m{k + 1}"
    _agregar_entidades(db, recurso, agregar, {}, usuario_id, documentos)
    _partes(db, recurso, agregar_partes or [], usuario_id, documentos)
    db.flush()
    nuevo = resumen(db, recurso)
    if nuevo != anterior:
        recurso.actualizado_en = ahora()
        cambios_ant = {k: v for k, v in anterior.items() if nuevo.get(k) != v}
        cambios_nuevo = {k: nuevo[k] for k in cambios_ant}
        registrar(db, modulo="descripcion", accion="descripcion_editada", usuario_id=usuario_id,
                  entidad_tipo="recurso_documental", entidad_id=recurso.id, anterior=cambios_ant, nuevo=cambios_nuevo)
    _cerrar(db, trabajo, "publicado")
    return nuevo != anterior


# --- Agrupaciones sin archivos propios e inclusiones adicionales (CM-02, CM-21) ---------------------

NIVELES_AGRUPACION = ("seccion", "subseccion", "serie", "subserie", "expediente")


def crear_agrupacion(db: Session, *, fondo_id: uuid.UUID, nivel: str, titulo: str, incluido_en_id: uuid.UUID | None,
                     usuario_id: uuid.UUID, codigo_referencia: str | None = None, fechas_extremas: str | None = None,
                     alcance: str | None = None, productor_id: uuid.UUID | None = None) -> RecursoDocumental:
    """Un Record Set es una agregación intelectual: una serie existe porque
    agrupa expedientes, no porque tenga archivos propios (hallazgo CM-02).
    Se crea aquí sin ninguna instanciación, con su productor y sus fechas."""
    if nivel not in NIVELES_AGRUPACION:
        raise ErrorDescripcion("Solo se crean así secciones, subsecciones, series, subseries o expedientes.")
    titulo = " ".join((titulo or "").split())[:500]
    if not titulo:
        raise ErrorDescripcion("La agrupación necesita un título.")
    superior = _superior(db, fondo_id, nivel, incluido_en_id)
    codigo = (codigo_referencia or "").strip() or None
    if codigo and db.scalar(select(RecursoDocumental.id).where(RecursoDocumental.fondo_id == fondo_id,
                                                               RecursoDocumental.codigo_referencia == codigo)):
        raise ErrorDescripcion(f"El código de referencia «{codigo}» ya está en uso en este fondo.", 409)
    # Cuadro de clasificación (hallazgo DES-08): el código de una serie o
    # subserie se compone desde el de su superior (110 → 110.2 → 110.2.1).
    if codigo and nivel in ("serie", "subserie") and superior.codigo_referencia \
            and not codigo.startswith(superior.codigo_referencia):
        raise ErrorDescripcion(f"El código de una {nivel} empieza por el de su nivel superior "
                               f"(«{superior.codigo_referencia}»): por ejemplo «{superior.codigo_referencia}.1».")
    try:
        extremas = fechas.extremas(fechas_extremas)
    except fechas.FechaInvalida as exc:
        raise ErrorDescripcion(f"Fechas extremas: {exc}") from exc
    r = RecursoDocumental(id=uuid.uuid4(), nivel=nivel, titulo=titulo, fondo_id=fondo_id, incluido_en_id=superior.id,
                          codigo_referencia=codigo, fechas_extremas=(fechas_extremas or "").strip() or None,
                          fechas_extremas_edtf=extremas.edtf if extremas else None,
                          alcance_contenido=(alcance or "").strip() or None, origen_titulo="persona",
                          creado_por_id=usuario_id, publicado_en=ahora(), publicado_por_id=usuario_id)
    db.add(r)
    db.flush()
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=superior.id, destino_tipo="recurso_documental",
                    destino_id=r.id, tipo_relacion="inclusion", codigo_ric="includes_or_included", origen="persona",
                    confirmada_por_id=usuario_id))
    if productor_id:
        productor = db.get(EntidadVocabulario, productor_id)
        if productor is None or productor.clase != "agente" or productor.fondo_id != fondo_id:
            raise ErrorDescripcion("El productor debe ser un agente del vocabulario de este fondo.")
        db.add(Relacion(origen_tipo="recurso_documental", origen_id=r.id, destino_tipo="entidad_vocabulario",
                        destino_id=productor.id, tipo_relacion="procedencia", codigo_ric="has_creator",
                        rol="productor", origen="persona", confirmada_por_id=usuario_id))
    db.flush()
    registrar(db, modulo="descripcion", accion="agrupacion_creada", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=r.id, detalle=f"{nivel}: {titulo}",
              nuevo={"nivel": nivel, "titulo": titulo, "incluido_en": str(superior.id), "codigo_referencia": codigo,
                     "fechas_extremas": r.fechas_extremas_edtf, "productor": str(productor_id) if productor_id else None})
    return r


def _descendientes(db: Session, raiz_id: uuid.UUID) -> set[uuid.UUID]:
    vistos, pendientes = set(), [raiz_id]
    while pendientes:
        actual = pendientes.pop()
        for hijo in db.scalars(select(Relacion.destino_id).where(
                Relacion.origen_id == actual, Relacion.codigo_ric == "includes_or_included",
                Relacion.estado == "vigente")).all():
            if hijo not in vistos:
                vistos.add(hijo)
                pendientes.append(hijo)
    return vistos


def agregar_inclusion(db: Session, recurso: RecursoDocumental, conjunto: RecursoDocumental,
                      usuario_id: uuid.UUID) -> Relacion:
    """Inclusión adicional (rol «adicional»), por ejemplo en una colección
    facticia. La inclusión orgánica sigue siendo una sola: la de
    `incluido_en_id` (decisión CM-21, perfil de aplicación de RICORA)."""
    if conjunto.fondo_id != recurso.fondo_id:
        raise ErrorDescripcion("Solo se incluye en un conjunto del mismo fondo.")
    if conjunto.nivel in ("unidad_documental", "parte_documental") or conjunto.id == recurso.id:
        raise ErrorDescripcion("Solo una agrupación (sección, serie, expediente…) incluye a otra descripción.")
    if conjunto.id == recurso.incluido_en_id:
        raise ErrorDescripcion("Ese ya es su nivel superior orgánico.")
    if conjunto.id in _descendientes(db, recurso.id):
        raise ErrorDescripcion("Esa inclusión formaría un ciclo.")
    if db.scalar(select(Relacion.id).where(Relacion.origen_id == conjunto.id, Relacion.destino_id == recurso.id,
                                           Relacion.codigo_ric == "includes_or_included", Relacion.estado == "vigente")):
        raise ErrorDescripcion("Ya está incluido en ese conjunto.", 409)
    r = Relacion(origen_tipo="recurso_documental", origen_id=conjunto.id, destino_tipo="recurso_documental",
                 destino_id=recurso.id, tipo_relacion="inclusion", codigo_ric="includes_or_included", rol="adicional",
                 origen="persona", confirmada_por_id=usuario_id)
    db.add(r)
    db.flush()
    registrar(db, modulo="descripcion", accion="inclusion_adicional", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=recurso.id,
              detalle=f"«{recurso.titulo}» también incluido en «{conjunto.titulo}»",
              nuevo={"relacion_id": str(r.id), "conjunto": str(conjunto.id)})
    return r


# --- Un Record por documento dentro de un conjunto (CM-03) y original físico (CM-04) ----------------


def individualizar(db: Session, conjunto: RecursoDocumental, inst: Instanciacion, usuario_id: uuid.UUID,
                   titulo: str | None = None) -> RecursoDocumental:
    """Dos oficios distintos no son dos inscripciones de lo mismo: cada
    documento de un expediente puede tener su propio Record (con su propio
    productor, fecha y destinatario), incluido en el expediente, y su archivo
    pasa a ser instanciación de ese Record (hallazgo CM-03). La relación
    anterior no se borra: queda anulada."""
    if conjunto.nivel not in NIVELES_CONJUNTO:
        raise ErrorDescripcion("Solo se separa un documento de un expediente, una subserie o una serie.")
    fila = db.scalar(select(Relacion).where(Relacion.origen_id == conjunto.id, Relacion.destino_id == inst.id,
                                            Relacion.codigo_ric == "has_or_had_instantiation",
                                            Relacion.estado == "vigente"))
    if fila is None:
        raise ErrorDescripcion("Ese archivo no es una instanciación vigente de este conjunto.")
    titulo = " ".join((titulo or inst.nombre_original).split())[:500]
    r = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo=titulo, fondo_id=conjunto.fondo_id,
                          incluido_en_id=conjunto.id, origen_titulo="persona", creado_por_id=usuario_id,
                          publicado_en=ahora(), publicado_por_id=usuario_id)
    db.add(r)
    db.flush()
    fila.estado = "anulada"
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=conjunto.id, destino_tipo="recurso_documental",
                    destino_id=r.id, tipo_relacion="inclusion", codigo_ric="includes_or_included", origen="persona",
                    confirmada_por_id=usuario_id))
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=r.id, destino_tipo="instanciacion",
                    destino_id=inst.id, tipo_relacion="asociacion", codigo_ric="has_or_had_instantiation",
                    origen="persona", confirmada_por_id=usuario_id))
    db.flush()
    registrar(db, modulo="descripcion", accion="documento_individualizado", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=r.id,
              detalle=f"«{titulo}» pasa a ser su propio documento dentro de «{conjunto.titulo}»",
              anterior={"relacion_anulada": str(fila.id)}, nuevo={"record": str(r.id), "instanciacion": str(inst.id)})
    return r


# Estado de conservación y signatura topográfica del original físico
# (Esquema de Metadatos del AGN v1.4, tabla 4).
CAMPOS_FISICO_AGN = ("estado_conservacion", "deposito", "estante", "entrepano")


def signatura_topografica(inst: Instanciacion) -> str | None:
    partes = [f"{etiqueta} {valor}" for etiqueta, valor in (("Depósito", inst.deposito), ("estante", inst.estante),
                                                              ("entrepaño", inst.entrepano)) if valor]
    return ", ".join(partes) or None


def _datos_fisicos(inst: Instanciacion, datos: dict) -> None:
    from app.models.instanciacion import ESTADO_CONSERVACION

    for campo, valor in datos.items():
        if campo not in CAMPOS_FISICO_AGN:
            raise ErrorDescripcion(f"«{campo}» no es un dato del original físico.")
        valor = " ".join((valor or "").split())[:40] or None
        if campo == "estado_conservacion" and valor:
            valor = valor.lower()
            if valor not in ESTADO_CONSERVACION:
                raise ErrorDescripcion("Estado de conservación: " + ", ".join(ESTADO_CONSERVACION) + ".")
        setattr(inst, campo, valor)


def registrar_original_fisico(db: Session, recurso: RecursoDocumental, *, soporte: str, ubicacion: str | None,
                              usuario_id: uuid.UUID, caracteristicas: str | None = None,
                              datos_agn: dict | None = None) -> Instanciacion:
    """El original en papel (u otro soporte) como Instantiation sin archivo,
    con su tipo de soporte (rico:CarrierType). Cada archivo digital del
    documento queda como derivado de él (RiC-R014): la digitalización."""
    from app.models.instanciacion import TIPO_SOPORTE

    if soporte not in TIPO_SOPORTE:
        raise ErrorDescripcion("Elija el soporte del original: " + ", ".join(TIPO_SOPORTE) + ".")
    digitales = list(db.scalars(select(Instanciacion).join(Relacion, Relacion.destino_id == Instanciacion.id).where(
        Relacion.origen_id == recurso.id, Relacion.codigo_ric == "has_or_had_instantiation",
        Relacion.estado == "vigente", Instanciacion.estado == "listo_para_descripcion")))
    fisico = Instanciacion(id=uuid.uuid4(), fondo_id=recurso.fondo_id, nombre_original=f"Original en {soporte.replace('_', ' ')}",
                           estado="registro_fisico", paso="terminado", progreso=100, soporte=soporte,
                           ubicacion_fisica=(ubicacion or "").strip() or None, cargado_por_id=usuario_id,
                           caracteristicas_fisicas=(caracteristicas or "").strip()[:5000] or None)
    _datos_fisicos(fisico, datos_agn or {})
    db.add(fisico)
    db.flush()
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=recurso.id, destino_tipo="instanciacion",
                    destino_id=fisico.id, tipo_relacion="asociacion", codigo_ric="has_or_had_instantiation",
                    origen="persona", confirmada_por_id=usuario_id))
    for d in digitales:
        db.add(Relacion(origen_tipo="instanciacion", origen_id=fisico.id, destino_tipo="instanciacion",
                        destino_id=d.id, tipo_relacion="identidad", codigo_ric="has_or_had_derived_instantiation",
                        origen="persona", confirmada_por_id=usuario_id))
    db.flush()
    registrar(db, modulo="descripcion", accion="original_fisico_registrado", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=recurso.id, detalle=f"Original en {soporte} de «{recurso.titulo}»",
              nuevo={"instanciacion": str(fisico.id), "soporte": soporte, "ubicacion": fisico.ubicacion_fisica,
                     **{c: getattr(fisico, c) for c in CAMPOS_FISICO_AGN},
                     "digitalizaciones": [str(d.id) for d in digitales]})
    return fisico


def actualizar_original_fisico(db: Session, recurso: RecursoDocumental, inst: Instanciacion, *, usuario_id: uuid.UUID,
                               ubicacion: str | None = None, caracteristicas: str | None = None,
                               datos_agn: dict | None = None) -> Instanciacion:
    """El estado de conservación cambia con el tiempo (una restauración, un
    deterioro): se corrige aquí y la auditoría guarda el valor anterior."""
    vinculo = db.scalar(select(Relacion.id).where(Relacion.origen_id == recurso.id, Relacion.destino_id == inst.id,
                                                  Relacion.codigo_ric == "has_or_had_instantiation",
                                                  Relacion.estado == "vigente"))
    if vinculo is None or inst.estado != "registro_fisico":
        raise ErrorDescripcion("Ese original físico no pertenece a esta descripción.", 404)
    campos = ("ubicacion_fisica", "caracteristicas_fisicas", *CAMPOS_FISICO_AGN)
    anterior = {c: getattr(inst, c) for c in campos}
    if ubicacion is not None:
        inst.ubicacion_fisica = ubicacion.strip()[:300] or None
    if caracteristicas is not None:
        inst.caracteristicas_fisicas = caracteristicas.strip()[:5000] or None
    _datos_fisicos(inst, {k: v for k, v in (datos_agn or {}).items() if v is not None})
    nuevo = {c: getattr(inst, c) for c in campos}
    if nuevo != anterior:
        db.flush()
        registrar(db, modulo="descripcion", accion="original_fisico_actualizado", usuario_id=usuario_id,
                  entidad_tipo="instanciacion", entidad_id=inst.id, detalle=f"Original físico de «{recurso.titulo}»",
                  anterior={k: v for k, v in anterior.items() if nuevo[k] != v},
                  nuevo={k: v for k, v in nuevo.items() if anterior[k] != v})
    return inst



# --- Cadena de custodia sobre la instanciación (DES-05) -----------------------------------------------


def custodio_de_instanciacion(db: Session, inst: Instanciacion, agente_id: uuid.UUID, fecha_edtf: str | None,
                              nota: str | None, usuario_id: uuid.UUID) -> Relacion:
    """Quien tuvo o tiene la custodia del archivo o del original físico, con
    su tramo de fechas. El dominio de hasOrHadHolder admite Instantiation."""
    agente = db.get(EntidadVocabulario, agente_id)
    if agente is None or agente.clase != "agente" or agente.fondo_id != inst.fondo_id:
        raise ErrorDescripcion("El custodio debe ser un agente del vocabulario de este fondo.")
    tramo = None
    if fecha_edtf and fecha_edtf.strip():
        try:
            tramo = fechas.interpretar(fecha_edtf.strip()).edtf
        except fechas.FechaInvalida as exc:
            raise ErrorDescripcion(f"El periodo de la custodia: {exc}") from exc
    r = Relacion(origen_tipo="instanciacion", origen_id=inst.id, destino_tipo="entidad_vocabulario",
                 destino_id=agente.id, tipo_relacion="procedencia", codigo_ric="has_or_had_holder", rol="custodio",
                 origen="persona", confirmada_por_id=usuario_id, fecha_edtf=tramo,
                 nota=(nota or "").strip()[:500] or None)
    db.add(r)
    db.flush()
    registrar(db, modulo="descripcion", accion="custodio_registrado", usuario_id=usuario_id,
              entidad_tipo="instanciacion", entidad_id=inst.id,
              detalle=f"«{agente.nombre}» custodio de «{inst.nombre_original}»",
              nuevo={"agente": str(agente.id), "periodo": tramo, "nota": r.nota})
    return r


def custodios_de(db: Session, nodo_id: uuid.UUID) -> list[dict]:
    """La cadena de custodia de un documento o de un archivo, en orden de fechas."""
    filas = db.scalars(select(Relacion).where(Relacion.origen_id == nodo_id, Relacion.codigo_ric == "has_or_had_holder",
                                              Relacion.estado == "vigente")).all()
    salida = []
    for r in filas:
        a = db.get(EntidadVocabulario, r.destino_id)
        inicio = fechas.interpretar(r.fecha_edtf).inicio if r.fecha_edtf else None
        salida.append({"relacion_id": str(r.id), "agente": {"id": str(a.id), "nombre": a.nombre} if a else None,
                       "periodo": r.fecha_edtf, "periodo_legible": fechas.legible(r.fecha_edtf) if r.fecha_edtf else None,
                       "nota": r.nota, "_orden": inicio})
    salida.sort(key=lambda x: (x["_orden"] is None, x["_orden"] or 0))
    for x in salida:
        x.pop("_orden")
    return salida
