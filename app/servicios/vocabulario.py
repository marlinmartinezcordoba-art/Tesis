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
    forma: str | None = None  # la otra forma del nombre que coincidió, si no fue la autorizada


def _formas():
    """Nombre autorizado y otras formas vigentes (paralelas, históricas,
    siglas) de cada entidad, normalizados: la búsqueda los mira todos
    (hallazgo DES-10). Así «Cabildo de Tunja» encuentra a la Alcaldía."""
    from sqlalchemy import literal, union_all

    from app.models.descripcion import NombreEntidad

    return union_all(
        select(EntidadVocabulario.id.label("entidad_id"), EntidadVocabulario.nombre_normalizado.label("n"),
               literal(None).label("forma")),
        select(NombreEntidad.entidad_id, NombreEntidad.nombre_normalizado, NombreEntidad.nombre)
        .where(NombreEntidad.estado == "vigente", NombreEntidad.nombre_normalizado.is_not(None)),
    ).subquery("formas")


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
    formas = _formas()
    similitud = func.similarity(formas.c.n, buscado)
    filas = db.execute(
        select(EntidadVocabulario, similitud.label("s"), formas.c.forma)
        .join(formas, formas.c.entidad_id == EntidadVocabulario.id)
        .where(EntidadVocabulario.fondo_id == fondo_id,
               EntidadVocabulario.clase == clase,
               EntidadVocabulario.estado == "activa",
               or_(similitud >= settings.umbral_similitud, formas.c.n == buscado))
        .order_by(similitud.desc(), EntidadVocabulario.nombre)
    ).all()
    mejores: dict[uuid.UUID, tuple] = {}
    for e, s, forma in filas:  # la mejor forma de cada entidad
        if e.id not in mejores:
            mejores[e.id] = (e, s, forma)
    return [Coincidencia(id=e.id, nombre=e.nombre, subtipo=e.subtipo, similitud=round(float(s), 2),
                         conexiones=conexiones(db, e.id), forma=forma)
            for e, s, forma in list(mejores.values())[:limite]]


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
    ficha_movida = _fusionar_ficha(db, definitiva, absorbida, usuario_id)
    # Un mecanismo: las acciones técnicas que ejecutó pasan a la definitiva.
    if absorbida.clase == "agente" and absorbida.subtipo == "mecanismo":
        ficha_movida += _mover_usos_mecanismo(db, absorbida.id, definitiva.id)
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
                     "registros_ficha_movidos": ficha_movida,
                     "origen": "sugerencia" if sugerencia is not None else "manual"},
              detalle=f"«{absorbida.nombre}» se fusionó en «{definitiva.nombre}».")
    return movidas + formas


def _fusionar_ficha(db: Session, definitiva: EntidadVocabulario, absorbida: EntidadVocabulario,
                    usuario_id: uuid.UUID) -> int:
    """Lo que cuelga de la ficha de autoridad pasa a la definitiva: hitos,
    formas del nombre (y el nombre de la absorbida, como «otra forma»),
    identificadores y la jerarquía de funciones. Una relación que quedó de
    la entidad consigo misma (A subordinada a B, y B se fusiona en A) se
    anula. Devuelve cuántos registros se movieron."""
    from sqlalchemy import update

    from app.db.base import ahora
    from app.models.descripcion import Hito, IdentificadorEntidad, NombreEntidad

    movidos = db.execute(update(Hito).where(Hito.agente_id == absorbida.id, Hito.estado == "vigente")
                         .values(agente_id=definitiva.id,
                                 agente_original_id=func.coalesce(Hito.agente_original_id, absorbida.id))).rowcount
    movidos += db.execute(update(NombreEntidad).where(NombreEntidad.entidad_id == absorbida.id,
                                                      NombreEntidad.estado == "vigente")
                          .values(entidad_id=definitiva.id)).rowcount
    ya = {normalizar(n) for n in db.scalars(select(NombreEntidad.nombre).where(
        NombreEntidad.entidad_id == definitiva.id, NombreEntidad.estado == "vigente"))}
    if absorbida.nombre_normalizado != definitiva.nombre_normalizado and absorbida.nombre_normalizado not in ya:
        db.add(NombreEntidad(entidad_id=definitiva.id, tipo="historica" if definitiva.clase == "lugar" else "otra",
                             nombre=absorbida.nombre, nombre_normalizado=absorbida.nombre_normalizado,
                             creado_por_id=usuario_id))
        movidos += 1
    existentes = set(db.execute(select(IdentificadorEntidad.esquema, IdentificadorEntidad.valor).where(
        IdentificadorEntidad.entidad_id == definitiva.id, IdentificadorEntidad.estado == "vigente")).all())
    for i in db.scalars(select(IdentificadorEntidad).where(IdentificadorEntidad.entidad_id == absorbida.id,
                                                           IdentificadorEntidad.estado == "vigente")).all():
        if (i.esquema, i.valor) in existentes:
            i.estado = "anulado"  # el mismo identificador ya está en la definitiva
        else:
            i.entidad_id = definitiva.id
            movidos += 1
    # Árbol de funciones (SKOS): los específicos de la absorbida cuelgan de
    # la definitiva; la definitiva hereda el superior si no tenía.
    movidos += db.execute(update(EntidadVocabulario).where(EntidadVocabulario.concepto_superior_id == absorbida.id,
                                                           EntidadVocabulario.id != definitiva.id)
                          .values(concepto_superior_id=definitiva.id)).rowcount
    if definitiva.concepto_superior_id == absorbida.id:
        definitiva.concepto_superior_id = None
    if definitiva.concepto_superior_id is None and absorbida.concepto_superior_id not in (None, definitiva.id):
        definitiva.concepto_superior_id = absorbida.concepto_superior_id
    db.execute(update(Relacion).where(Relacion.origen_id == definitiva.id, Relacion.destino_id == definitiva.id,
                                      Relacion.estado == "vigente")
               .values(estado="anulada", anulada_en=ahora(), anulada_por_id=usuario_id))
    db.flush()
    from app.servicios import autoridad

    autoridad.recalcular_nivel(db, definitiva)
    return movidos


def detectar_candidatos(db: Session, fondo_id: uuid.UUID | None = None) -> int:
    """Compara entre sí las entidades activas del mismo tipo y fondo con el
    mismo criterio de similitud que verificar(), y registra una sugerencia
    por cada par muy parecido en el que ambas tienen pocas conexiones. No
    fusiona nada. Un par ya sugerido (en cualquier estado) no se repite."""
    from sqlalchemy.orm import aliased

    from app.models.descripcion import SugerenciaFusion
    from app.servicios import parametros

    from app.models.descripcion import ESQUEMA_EXTERNO, IdentificadorEntidad

    umbral = int(parametros.leer(db, "fusion_similitud_pct")) / 100
    maximo = int(parametros.leer(db, "fusion_max_conexiones"))
    a, b = aliased(EntidadVocabulario), aliased(EntidadVocabulario)
    # Nombre autorizado y otras formas del nombre de cada lado (VOC-05).
    fa, fb = _formas().alias("fa"), _formas().alias("fb")
    similitud = func.max(func.similarity(fa.c.n, fb.c.n))
    otra_forma = func.bool_or(fa.c.forma.is_not(None) | fb.c.forma.is_not(None))
    consulta = (select(a, b, similitud.label("s"), otra_forma.label("otra"))
                .join(b, (a.fondo_id == b.fondo_id) & (a.clase == b.clase) & (a.id < b.id))
                .join(fa, fa.c.entidad_id == a.id).join(fb, fb.c.entidad_id == b.id)
                .where(a.estado == "activa", b.estado == "activa", func.similarity(fa.c.n, fb.c.n) >= umbral)
                .group_by(a.id, b.id))
    # El mismo identificador externo (Wikidata, VIAF, ISNI, LCNAF) es la
    # señal más fuerte de duplicado: se sugiere siempre, sin mirar el nombre
    # ni las conexiones.
    ia, ib = aliased(IdentificadorEntidad), aliased(IdentificadorEntidad)
    por_identificador = (select(a, b)
                         .join(ia, ia.entidad_id == a.id).join(ib, (ib.esquema == ia.esquema) & (ib.valor == ia.valor))
                         .join(b, (b.id == ib.entidad_id) & (a.fondo_id == b.fondo_id) & (a.clase == b.clase)
                               & (a.id < b.id))
                         .where(a.estado == "activa", b.estado == "activa", ia.estado == "vigente",
                                ib.estado == "vigente", ia.esquema.in_(ESQUEMA_EXTERNO)).distinct())
    if fondo_id is not None:
        consulta = consulta.where(a.fondo_id == fondo_id)
        por_identificador = por_identificador.where(a.fondo_id == fondo_id)
    pares = [(x, y, float(s_), "otra_forma" if otra else "nombre") for x, y, s_, otra in db.execute(consulta).all()]
    mismos = {(x.id, y.id) for x, y in db.execute(por_identificador).all()}
    pares = [p for p in pares if (p[0].id, p[1].id) not in mismos] + [
        (x, y, 1.0, "identificador") for x, y in db.execute(por_identificador).all()]
    if not pares:
        return 0
    conexiones = conexiones_de(db, list({x.id for p in pares for x in p[:2]}))
    existentes = set(db.execute(select(SugerenciaFusion.entidad_a_id, SugerenciaFusion.entidad_b_id)).all())
    nuevas = 0
    for x, y, s, motivo in pares:
        if (x.id, y.id) in existentes:
            continue
        if motivo != "identificador" and (conexiones[x.id] > maximo or conexiones[y.id] > maximo):
            continue
        # Dos versiones de un mismo programa son mecanismos distintos: el
        # resultado de cada una debe poder atribuirse a la suya.
        if x.subtipo == y.subtipo == "mecanismo" and (x.version or "") != (y.version or ""):
            continue
        db.add(SugerenciaFusion(fondo_id=x.fondo_id, clase=x.clase, entidad_a_id=x.id, entidad_b_id=y.id,
                                similitud=round(float(s), 2), motivo=motivo))
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
                       usuario_id: uuid.UUID, fecha_edtf: str | None = None, nota: str | None = None,
                       ip: str | None = None) -> Relacion:
    """Relación declarada entre dos agentes del mismo fondo. Se guarda una
    sola fila; su inversa (owl:inverseOf en RiC-O) se lee de ella, nunca se
    duplica, para que anular una anule las dos lecturas a la vez. La
    validación (mismo fondo, sin ciclos en la jerarquía, sin repetir) y la
    auditoría son las de autoridad.vincular()."""
    from app.servicios import autoridad

    if tipo not in RELACION_AGENTES:
        raise ErrorRelacionAgentes("Tipo de relación entre agentes desconocido.")
    if origen.clase != "agente" or destino.clase != "agente" or origen.fondo_id != destino.fondo_id:
        raise ErrorRelacionAgentes("Solo se relacionan agentes del mismo fondo.")
    try:
        return autoridad.vincular(db, tipo=tipo, desde=origen, con_tipo="entidad_vocabulario", con_id=destino.id,
                                  usuario_id=usuario_id, fecha_edtf=fecha_edtf, nota=nota, ip=ip)
    except autoridad.ErrorAutoridad as exc:
        raise ErrorRelacionAgentes(str(exc)) from exc


def relaciones_de_agente(db: Session, agente_id: uuid.UUID) -> list[dict]:
    """Las relaciones del agente leídas en los dos sentidos, con la inversa
    cuando el agente es el destino."""
    from app.servicios import ric_o

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
                       "uri_rico": ric_o.uri(r.codigo_ric) if es_origen else ric_o.uri_inversa(r.codigo_ric),
                       "con": {"id": str(otro.id), "nombre": otro.nombre, "subtipo": otro.subtipo} if otro else None})
    return salida


# --- Mecanismos: un solo registro por programa y versión ------------------------------------------


def mecanismo(db: Session, *, fondo_id: uuid.UUID, nombre: str, version: str | None,
              usuario_id: uuid.UUID | None = None) -> EntidadVocabulario:
    """Agente de subtipo mecanismo (RiC-E13) para un programa con su versión
    exacta: el motor de análisis, Ghostscript. Si ya existe en el
    vocabulario del fondo (mismo nombre y misma versión), se reutiliza; si
    no, se crea aquí, con el servicio único de creación. Nadie guarda el
    nombre de un programa como texto suelto en otro módulo."""
    from app.servicios.auditoria import registrar

    nombre = " ".join(nombre.split())
    version = (version or "").strip() or None
    etiqueta = nombre if not version or version in nombre else f"{nombre} {version}"
    existente = db.scalar(select(EntidadVocabulario).where(
        EntidadVocabulario.fondo_id == fondo_id, EntidadVocabulario.clase == "agente",
        EntidadVocabulario.subtipo == "mecanismo",
        EntidadVocabulario.version == version if version else EntidadVocabulario.version.is_(None),
        EntidadVocabulario.nombre_normalizado == normalizar(etiqueta)))
    if existente is not None:
        # Si se fusionó, vale la definitiva.
        while existente.estado == "fusionada" and existente.fusionada_en_id:
            existente = db.get(EntidadVocabulario, existente.fusionada_en_id)
        return existente
    e = crear(db, fondo_id=fondo_id, clase="agente", nombre=etiqueta, subtipo="mecanismo", origen="persona",
              confianza=None, motor=None, usuario_id=usuario_id)
    e.version = version
    db.flush()
    if version is None:
        from app.servicios import alertas

        alertas.crear(db, tipo="mecanismo_sin_version", severidad="media", modulo="vocabularios",
                      entidad_tipo="entidad_vocabulario", entidad_id=e.id, fondo_id=fondo_id,
                      mensaje=f"«{etiqueta}» actuó sin declarar su versión. Complete la versión exacta en su ficha: "
                              "sin ella no se puede reproducir ni atribuir lo que hizo.")
    registrar(db, modulo="vocabularios", accion="mecanismo_registrado", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=e.id, nuevo={"nombre": etiqueta, "version": version},
              detalle=f"Mecanismo «{etiqueta}» registrado en el vocabulario del fondo")
    return e


def usos_mecanismo():
    """(modelo, columna) de cada acción técnica que apunta a un mecanismo."""
    from app.models.descripcion import Actividad, Fecha
    from app.models.instanciacion import Instanciacion
    from app.models.preservacion import Migracion, Restauracion, SegundaCopia, VerificacionIntegridad

    return [(Instanciacion, Instanciacion.mecanismo_identificacion_id), (Migracion, Migracion.mecanismo_id),
            (VerificacionIntegridad, VerificacionIntegridad.mecanismo_id), (SegundaCopia, SegundaCopia.mecanismo_id),
            (Restauracion, Restauracion.mecanismo_id), (EntidadVocabulario, EntidadVocabulario.motor_id),
            (Relacion, Relacion.motor_id), (Fecha, Fecha.motor_id), (Actividad, Actividad.motor_id),
            (RecursoDocumental, RecursoDocumental.motor_id)]


def _mover_usos_mecanismo(db: Session, de: uuid.UUID, a: uuid.UUID) -> int:
    from sqlalchemy import update

    return sum(db.execute(update(modelo).where(columna == de).values({columna.key: a})).rowcount
               for modelo, columna in usos_mecanismo())


def conteo_usos_mecanismo(db: Session, mecanismo_id: uuid.UUID) -> dict[str, int]:
    """Cuántas acciones técnicas ejecutó el mecanismo, por tabla."""
    salida = {}
    for modelo, columna in usos_mecanismo():
        n = db.scalar(select(func.count()).select_from(modelo).where(columna == mecanismo_id)) or 0
        if n:
            salida[modelo.__tablename__ + ("." + columna.key if columna.key != "mecanismo_id" else "")] = n
    return salida


# --- Contexto de vocabulario para el motor de análisis (módulo 2, versión 3) ---------------------

# Cuántas entidades existentes recibe el motor por tipo, y desde qué
# parecido con el texto (decisión en documentacion/modulo-2-descripcion.md).
CONTEXTO_POR_TIPO = 10
CONTEXTO_UMBRAL = 0.5
CLASES_CONTEXTO = ("agente", "lugar", "forma_documental", "actividad", "tipo_actividad", "mandato")


def contexto_para_motor(db: Session, fondo_id: uuid.UUID, texto: str, por_tipo: int = CONTEXTO_POR_TIPO,
                        umbral: float = CONTEXTO_UMBRAL) -> list:
    """Entidades activas del fondo cuyo nombre aparece (o casi) en el texto
    de los documentos, por tipo, de la más a la menos parecida. Se mide con
    word_similarity de pg_trgm: el parecido entre el nombre y el tramo del
    texto que más se le parece, así que tolera tildes, mayúsculas y erratas
    del OCR. Los mecanismos no se ofrecen: no aparecen en los documentos."""
    from app.servicios.motor import EntradaContexto

    buscado = normalizar(texto or "")[:60_000]
    if not buscado:
        return []
    formas = _formas()
    parecido = func.max(func.word_similarity(formas.c.n, buscado))
    salida, n = [], 0
    for clase in CLASES_CONTEXTO:
        # También por sus otras formas del nombre (hallazgo DES-10): el texto
        # puede decir «Cabildo» aunque la autoridad se llame «Alcaldía».
        filas = db.execute(
            select(EntidadVocabulario, parecido.label("s"))
            .join(formas, formas.c.entidad_id == EntidadVocabulario.id)
            .where(EntidadVocabulario.fondo_id == fondo_id, EntidadVocabulario.clase == clase,
                   EntidadVocabulario.estado == "activa",
                   or_(EntidadVocabulario.subtipo.is_(None), EntidadVocabulario.subtipo != "mecanismo"))
            .group_by(EntidadVocabulario.id)
            .having(parecido >= umbral)
            .order_by(parecido.desc(), EntidadVocabulario.nombre)
            .limit(por_tipo)).all()
        for e, s in filas:
            n += 1
            salida.append(EntradaContexto(codigo=f"V{n}", id=str(e.id), tipo=clase, nombre=e.nombre, subtipo=e.subtipo,
                                          similitud=round(float(s), 2)))
    return salida
