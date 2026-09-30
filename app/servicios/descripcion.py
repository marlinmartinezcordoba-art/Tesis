"""
Descripción multinivel: marca «en edición», publicación transaccional del
Record Resource con sus relaciones, y corrección posterior.

Relaciones que crea (catálogo curado, códigos oficiales RiC-CM 1.0):

| Qué                          | Código RiC-R                           | Sentido               |
|------------------------------|----------------------------------------|-----------------------|
| Productor                    | has_creator (R027)                     | documento → agente    |
| Remitente                    | has_sender (R031)                      | documento → agente    |
| Destinatario                 | has_addressee (R032)                   | documento → agente    |
| Agente o lugar mencionado    | has_or_had_subject (R019)              | documento → entidad   |
| Fecha de creación            | is_creation_date_of (R080)             | fecha → documento     |
| Actividad documentada        | documents (R033)                       | documento → actividad |
| Inclusión en nivel superior  | includes_or_included (R024)            | superior → documento  |
| Archivo técnico              | has_or_had_instantiation (R025)        | documento → archivo   |

La forma documental no es una relación sino un atributo (RiC-A17), que
apunta a una entrada del vocabulario.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.descripcion import (
    Actividad, EntidadVocabulario, Fecha, Relacion, TrabajoDescripcion, TrabajoInstanciacion,
)
from app.models.enums import URI_RICO
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import NIVEL_DESCRIPCION, RecursoDocumental
from app.models.usuario import Usuario
from app.servicios import vocabulario
from app.servicios.auditoria import registrar

NIVELES_CONJUNTO = ("expediente", "subserie", "serie")
CLASES_VOCABULARIO = ("agente", "lugar", "forma_documental")

# (tipo, rol) → (código RiC, categoría amplia, sentido)
RELACION_POR_ROL = {
    ("agente", "productor"): ("has_creator", "procedencia"),
    ("agente", "remitente"): ("has_sender", "procedencia"),
    ("agente", "destinatario"): ("has_addressee", "procedencia"),
    ("agente", "mencionado"): ("has_or_had_subject", "asociacion"),
    ("lugar", None): ("has_or_had_subject", "espacial"),
    ("fecha", None): ("is_creation_date_of", "temporal"),
    ("actividad", None): ("documents", "asociacion"),
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
    trabajo.estado = estado
    trabajo.cerrado_en = ahora()
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


def documentos_de(db: Session, trabajo: TrabajoDescripcion) -> list[Instanciacion]:
    filas = db.execute(select(Instanciacion).join(
        TrabajoInstanciacion, TrabajoInstanciacion.instanciacion_id == Instanciacion.id)
        .where(TrabajoInstanciacion.trabajo_id == trabajo.id).order_by(TrabajoInstanciacion.orden)).scalars().all()
    return list(filas)


def _sin_descripcion():
    return ~exists().where(Relacion.destino_id == Instanciacion.id, Relacion.estado == "vigente",
                           Relacion.codigo_ric == "has_or_had_instantiation")


def cola(db: Session, fondo_id: uuid.UUID) -> list[tuple[Instanciacion, str | None]]:
    """Instanciaciones listas para describir y sin Record Resource, con el
    nombre de quien las tiene en edición (si alguien)."""
    expirar(db)
    filas = db.scalars(select(Instanciacion).where(
        Instanciacion.fondo_id == fondo_id, Instanciacion.estado == "listo_para_descripcion", _sin_descripcion())
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
    if len(documentos) != len(ids) or any(d.estado != "listo_para_descripcion" for d in documentos):
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
    fragmento: str | None = None
    documento_id: str | None = None
    inicio: int | None = None
    clave: str | None = None  # clave de la propuesta del motor, si viene de ahí
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


def _fecha_iso(valor: str | None) -> date | None:
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _agregar_entidades(db: Session, recurso: RecursoDocumental, entidades: list[EntidadConfirmada],
                       propuesta: dict, usuario_id: uuid.UUID, documentos: set[str]) -> None:
    propuestas = {p["clave"]: p for p in propuesta.get("entidades", []) if p.get("clave")}
    motor = propuesta.get("motor")
    formas = [e for e in entidades if e.tipo == "forma_documental"]
    if len(formas) > 1:
        raise ErrorDescripcion("Un documento o conjunto tiene una sola forma documental; deje solo una.")
    for i, e in enumerate(entidades):
        e.valor = " ".join((e.valor or "").split())
        if not e.valor:
            raise ErrorDescripcion("Hay una entidad sin valor; escríbalo o descártela.")
        if e.tipo not in ("agente", "lugar", "fecha", "actividad", "forma_documental"):
            raise ErrorDescripcion(f"Tipo de entidad desconocido: {e.tipo}.")
        base = propuestas.get(e.clave) if e.clave else None
        origen, confianza = _procedencia(e.valor, base.get("valor") if base else None, base.get("confianza") if base else None)
        motor_e = motor if base else None
        fragmento = e.fragmento if e.documento_id in documentos else None
        instanciacion_fragmento = uuid.UUID(e.documento_id) if fragmento else None

        if e.tipo == "forma_documental":
            recurso.forma_documental_id = _nodo_vocabulario(db, recurso.fondo_id, e, i, origen, confianza, motor_e, usuario_id).id
            continue
        rol = e.rol if e.tipo == "agente" else None
        if e.tipo == "agente" and rol not in ("productor", "remitente", "destinatario", "mencionado"):
            raise ErrorDescripcion(f"Indique el rol de «{e.valor}»: productor, remitente, destinatario o mencionado.")
        codigo, categoria = RELACION_POR_ROL[(e.tipo, rol)]
        if e.tipo in CLASES_VOCABULARIO:
            nodo = _nodo_vocabulario(db, recurso.fondo_id, e, i, origen, confianza, motor_e, usuario_id)
            nodo_tipo = "entidad_vocabulario"
        elif e.tipo == "fecha":
            nodo = Fecha(id=uuid.uuid4(), expresion=e.valor[:200], normalizada=_fecha_iso(e.fecha_normalizada),
                         origen=origen, confianza=confianza, motor=motor_e)
            nodo_tipo = "fecha"
        else:
            nodo = Actividad(id=uuid.uuid4(), fondo_id=recurso.fondo_id, nombre=e.valor[:300],
                             origen=origen, confianza=confianza, motor=motor_e)
            nodo_tipo = "actividad"
        db.add(nodo)
        db.flush()
        origen_nodo, destino_nodo = (("fecha", nodo.id), ("recurso_documental", recurso.id)) if e.tipo == "fecha" \
            else (("recurso_documental", recurso.id), (nodo_tipo, nodo.id))
        db.add(Relacion(
            origen_tipo=origen_nodo[0], origen_id=origen_nodo[1], destino_tipo=destino_nodo[0], destino_id=destino_nodo[1],
            tipo_relacion=categoria, codigo_ric=codigo, rol=rol or (e.tipo if e.tipo == "lugar" else None),
            fragmento=fragmento, fragmento_instanciacion_id=instanciacion_fragmento,
            fragmento_inicio=e.inicio if fragmento else None,
            origen=origen, confianza=confianza, motor=motor_e, confirmada_por_id=usuario_id,
        ))


def _superior(db: Session, fondo_id: uuid.UUID, nivel: str, incluido_en_id: uuid.UUID | None) -> RecursoDocumental:
    superior = db.get(RecursoDocumental, incluido_en_id) if incluido_en_id else db.get(RecursoDocumental, fondo_id)
    if superior is None or superior.fondo_id != fondo_id:
        raise ErrorDescripcion("El nivel superior elegido no pertenece a este fondo.")
    if rango(superior.nivel) >= rango(nivel):
        raise ErrorDescripcion(f"Un {nivel.replace('_', ' ')} no puede quedar dentro de un {superior.nivel.replace('_', ' ')}.")
    return superior


def publicar(db: Session, *, trabajo: TrabajoDescripcion, usuario_id: uuid.UUID, titulo: str, alcance: str,
             incluido_en_id: uuid.UUID | None, entidades: list[EntidadConfirmada]) -> RecursoDocumental:
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
    db.add(recurso)
    db.flush()
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=superior.id, destino_tipo="recurso_documental",
                    destino_id=recurso.id, tipo_relacion="inclusion", codigo_ric="includes_or_included",
                    origen="persona", confirmada_por_id=usuario_id))
    for d in documentos:
        db.add(Relacion(origen_tipo="recurso_documental", origen_id=recurso.id, destino_tipo="instanciacion",
                        destino_id=d.id, tipo_relacion="asociacion", codigo_ric="has_or_had_instantiation",
                        origen="persona", confirmada_por_id=usuario_id))
    _agregar_entidades(db, recurso, entidades, propuesta, usuario_id, ids_documentos)
    _cerrar(db, trabajo, "publicado")
    trabajo.recurso_id = recurso.id
    db.flush()
    registrar(db, modulo="descripcion", accion="descripcion_publicada", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=recurso.id, nuevo=resumen(db, recurso))
    return recurso


# --- Lectura (interna) y corrección posterior -------------------------------------------------------


def detalle(db: Session, recurso: RecursoDocumental) -> dict:
    """Vista interna completa, con origen y confianza de cada dato. Solo
    para las pantallas de trabajo y la auditoría."""
    superior = db.get(RecursoDocumental, recurso.incluido_en_id) if recurso.incluido_en_id else None
    forma = db.get(EntidadVocabulario, recurso.forma_documental_id) if recurso.forma_documental_id else None
    entidades, instanciaciones = [], []
    relaciones = db.scalars(select(Relacion).where(
        Relacion.estado == "vigente",
        ((Relacion.origen_id == recurso.id) | (Relacion.destino_id == recurso.id)))
        .order_by(Relacion.creado_en)).all()
    for r in relaciones:
        if r.codigo_ric == "includes_or_included":
            continue
        if r.codigo_ric == "has_or_had_instantiation":
            inst = db.get(Instanciacion, r.destino_id)
            if inst:
                instanciaciones.append({"id": str(inst.id), "nombre": inst.nombre_original})
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
        elif nodo_tipo == "fecha":
            n = db.get(Fecha, nodo_id)
            tipo, valor, subtipo = "fecha", n.expresion, None
            extra = {"fecha_normalizada": n.normalizada.isoformat() if n.normalizada else None}
        elif nodo_tipo == "actividad":
            n = db.get(Actividad, nodo_id)
            tipo, valor, subtipo, extra = "actividad", n.nombre, None, {}
        else:
            continue
        entidades.append({
            "relacion_id": str(r.id), "entidad_id": str(nodo_id), "tipo": tipo, "valor": valor, "subtipo": subtipo,
            "rol": r.rol, "codigo_ric": r.codigo_ric, "uri_rico": URI_RICO.get(r.codigo_ric),
            "fragmento": r.fragmento, "documento_id": str(r.fragmento_instanciacion_id) if r.fragmento_instanciacion_id else None,
            "origen": r.origen, "confianza": r.confianza, "motor": r.motor, "estado_revision": r.estado_revision, **extra,
        })
    return {
        "id": str(recurso.id), "nivel": recurso.nivel, "titulo": recurso.titulo,
        "alcance_contenido": recurso.alcance_contenido, "fondo_id": str(recurso.fondo_id),
        "incluido_en": {"id": str(superior.id), "titulo": superior.titulo, "nivel": superior.nivel} if superior else None,
        "forma_documental": {"id": str(forma.id), "nombre": forma.nombre, "origen": forma.origen} if forma else None,
        "entidades": entidades, "instanciaciones": instanciaciones, "control": control_de(recurso),
        "origen_titulo": recurso.origen_titulo, "origen_alcance": recurso.origen_alcance,
        "confianza_alcance": recurso.confianza_alcance, "motor": recurso.motor,
        "publicado_en": recurso.publicado_en.isoformat() if recurso.publicado_en else None,
        "actualizado_en": recurso.actualizado_en.isoformat() if recurso.actualizado_en else None,
    }


# Datos de control del inventario (FUID), que escribe siempre una persona.
CAMPOS_CONTROL = ("codigo_referencia", "caja", "carpeta", "folios", "soporte")


def control_de(recurso: RecursoDocumental) -> dict:
    return {c: getattr(recurso, c) for c in CAMPOS_CONTROL}


def resumen(db: Session, recurso: RecursoDocumental) -> dict:
    """Lo que queda en auditoría: los datos descriptivos, con su procedencia."""
    d = detalle(db, recurso)
    return {
        "titulo": d["titulo"], "alcance_contenido": d["alcance_contenido"], "nivel": d["nivel"],
        "incluido_en": d["incluido_en"]["titulo"] if d["incluido_en"] else None,
        "forma_documental": d["forma_documental"]["nombre"] if d["forma_documental"] else None,
        "entidades": sorted(f"{e['tipo']}:{e['rol'] or ''}:{e['valor']} [{e['origen']}]" for e in d["entidades"]),
        "instanciaciones": sorted(i["nombre"] for i in d["instanciaciones"]),
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
           control: dict | None = None) -> None:
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
        db.execute(update(Relacion).where(Relacion.destino_id == recurso.id, Relacion.codigo_ric == "includes_or_included",
                                          Relacion.estado == "vigente")
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
    if any(e.tipo == "forma_documental" for e in agregar) and recurso.forma_documental_id and not quitar_forma:
        raise ErrorDescripcion("Ya tiene forma documental; quítela antes de poner otra.")
    documentos = {str(r.destino_id) for r in db.scalars(select(Relacion).where(
        Relacion.origen_id == recurso.id, Relacion.codigo_ric == "has_or_had_instantiation", Relacion.estado == "vigente"))}
    _agregar_entidades(db, recurso, agregar, {}, usuario_id, documentos)
    db.flush()
    nuevo = resumen(db, recurso)
    if nuevo != anterior:
        recurso.actualizado_en = ahora()
        cambios_ant = {k: v for k, v in anterior.items() if nuevo.get(k) != v}
        cambios_nuevo = {k: nuevo[k] for k in cambios_ant}
        registrar(db, modulo="descripcion", accion="descripcion_editada", usuario_id=usuario_id,
                  entidad_tipo="recurso_documental", entidad_id=recurso.id, anterior=cambios_ant, nuevo=cambios_nuevo)
    _cerrar(db, trabajo, "publicado")
