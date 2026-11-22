"""
Evaluación del rendimiento del motor con la medida F1 (objetivo 3 de la tesis).

Diseño (documentacion/modulo-evaluacion.md):
- La evaluación reúne los documentos del caso, aún sin describir, y los sortea con una semilla en
  un conjunto de desarrollo, con el que se ajusta la instrucción del motor, y uno de prueba, que se
  procesa una sola vez con la versión congelada.
- La referencia es la descripción que la archivista valida en Descripción. Al publicar, cada
  propuesta del motor queda en la auditoría como aceptada, corregida o rechazada, y lo que la
  archivista agregó sin que el motor lo propusiera, como agregada (servicios/descripcion.py,
  registrar_decisiones). De ahí sale la matriz de confusión.
      aceptada  verdadero positivo
      rechazada falso positivo
      agregada  falso negativo
      corregida falso positivo y falso negativo a la vez
- Se mide la precisión, la exhaustividad y la medida F1 por tipo y en el conjunto, la F1 micro y
  la macro, con intervalos de confianza del 95 % por remuestreo de documentos. El título, el
  alcance y contenido y el idioma son textos libres: se informan por tipo y no entran en la F1
  global, porque cualquier ajuste de redacción contaría como error.
- Un criterio se cumple cuando el límite inferior del intervalo alcanza el umbral, fijado antes de
  iniciar y congelado al iniciar.
- Solo cuenta la primera publicación de cada documento y solo las decisiones tomadas con la
  versión congelada del motor y de la instrucción.
- Validación de control: una segunda validadora decide por su cuenta sobre las propuestas
  originales de algunos documentos de prueba; el acuerdo es el porcentaje de decisiones iguales.
- La causa de cada error (lectura del texto, ambigüedad del documento, regla mal aplicada,
  invención del motor) se registra en ClasificacionError.
"""

import io
import random
import re
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import ahora
from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import Relacion
from app.models.evaluacion import ClasificacionError, Control, Evaluacion, EvaluacionDocumento
from app.models.instanciacion import Instanciacion
from app.servicios.auditoria import registrar

CONJUNTOS = ("desarrollo", "prueba")
TEXTO_LIBRE = ("titulo", "alcance", "idioma")
CAUSAS = {"lectura": "Lectura del texto", "ambiguedad": "Ambigüedad del documento",
          "regla": "Regla mal aplicada", "invencion": "Invención del motor"}
CRITERIO_POR_DEFECTO = {"f1": 0.80, "precision": 0.85, "exhaustividad": 0.80, "acuerdo": 0.80}
REMUESTREOS = 1000
SEMILLA_REMUESTREO = 20261031  # fija: los mismos datos dan siempre el mismo intervalo
VENTANA_PUBLICACION = 300  # segundos: las decisiones de una misma publicación
DECISIONES = ("aceptada", "corregida", "rechazada", "agregada")


class ErrorEvaluacion(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


# --- Métricas (funciones puras) --------------------------------------------------------------------


def conteo(decisiones: list[str]) -> dict:
    """Verdaderos positivos, falsos positivos y falsos negativos de una lista de decisiones."""
    c = {d: sum(1 for x in decisiones if x == d) for d in DECISIONES}
    return {"vp": c["aceptada"], "fp": c["rechazada"] + c["corregida"], "fn": c["agregada"] + c["corregida"], **c}


def prf(c: dict) -> dict:
    vp, fp, fn = c["vp"], c["fp"], c["fn"]
    p = vp / (vp + fp) if vp + fp else None
    r = vp / (vp + fn) if vp + fn else None
    f = 2 * vp / (2 * vp + fp + fn) if 2 * vp + fp + fn else None
    return {"precision": _r(p), "exhaustividad": _r(r), "f1": _r(f)}


def _r(x: float | None, d: int = 4) -> float | None:
    return None if x is None else round(x, d)


def intervalo(por_documento: list[dict], medida: str, remuestreos: int = REMUESTREOS,
              semilla: int = SEMILLA_REMUESTREO) -> dict:
    """Intervalo de confianza del 95 % de una medida, remuestreando documentos completos."""
    docs = [d for d in por_documento if d["vp"] + d["fp"] + d["fn"]]
    if len(docs) < 2:
        return {"inferior": None, "superior": None, "remuestreos": 0}
    azar = random.Random(semilla)
    valores = []
    for _ in range(remuestreos):
        muestra = [docs[azar.randrange(len(docs))] for _ in docs]
        v = prf({k: sum(x[k] for x in muestra) for k in ("vp", "fp", "fn")})[medida]
        if v is not None:
            valores.append(v)
    valores.sort()
    if not valores:
        return {"inferior": None, "superior": None, "remuestreos": 0}
    n = len(valores)
    return {"inferior": _r(valores[int(0.025 * (n - 1))]), "superior": _r(valores[int(round(0.975 * (n - 1)))]),
            "remuestreos": n}


def metricas(filas: list[dict]) -> dict:
    """Medidas globales (sin textos libres), por tipo y por documento, con sus intervalos."""
    de_entidades = [f for f in filas if f["tipo"] not in TEXTO_LIBRE]
    global_ = conteo([f["decision"] for f in de_entidades])
    por_doc: dict[str, list[str]] = defaultdict(list)
    for f in de_entidades:
        por_doc[f["documento_id"]].append(f["decision"])
    por_documento = [{"documento_id": k, **conteo(v)} for k, v in por_doc.items()]
    por_tipo = []
    tipos: dict[str, list[str]] = defaultdict(list)
    for f in filas:
        tipos[f["tipo"]].append(f["decision"])
    for t, ds in sorted(tipos.items()):
        c = conteo(ds)
        por_tipo.append({"tipo": t, "texto_libre": t in TEXTO_LIBRE, **c, **prf(c)})
    f1_tipos = [t["f1"] for t in por_tipo if not t["texto_libre"] and t["f1"] is not None]
    medidas = prf(global_)
    return {"conteo": global_, **medidas,
            "f1_macro": _r(sum(f1_tipos) / len(f1_tipos)) if f1_tipos else None,
            "intervalos": {m: intervalo(por_documento, m) for m in ("f1", "precision", "exhaustividad")},
            "por_tipo": por_tipo, "documentos": len(por_documento)}


def dictamen(m: dict, criterio: dict) -> dict:
    """Cumple si el límite inferior del intervalo alcanza el umbral (y, sin intervalo, el valor puntual)."""
    salida = {}
    for medida in ("f1", "precision", "exhaustividad"):
        umbral = criterio.get(medida)
        valor = m.get(medida)
        inferior = (m.get("intervalos", {}).get(medida) or {}).get("inferior")
        base = inferior if inferior is not None else valor
        salida[medida] = {"umbral": umbral, "valor": valor, "limite_inferior": inferior,
                          "cumple": None if base is None or umbral is None else base >= umbral}
    estados = [v["cumple"] for v in salida.values()]
    salida["hipotesis"] = (None if any(e is None for e in estados) else
                           "se sostiene" if all(estados) else "no se sostiene")
    return salida


def criterio_de(guardado: dict | None) -> dict:
    return CRITERIO_POR_DEFECTO | (guardado or {})


def validar_criterio(datos: dict) -> dict:
    nuevo = {}
    for k in CRITERIO_POR_DEFECTO:
        v = datos.get(k, CRITERIO_POR_DEFECTO[k])
        if not isinstance(v, (int, float)) or not 0 < v <= 1:
            raise ErrorEvaluacion(f"El umbral «{k}» va de 0 a 1.")
        nuevo[k] = round(float(v), 4)
    return nuevo


# --- Evaluación y documentos -----------------------------------------------------------------------


def _evaluacion(db: Session, evaluacion_id: uuid.UUID) -> Evaluacion:
    ev = db.get(Evaluacion, evaluacion_id)
    if ev is None:
        raise ErrorEvaluacion("La evaluación no existe.", 404)
    return ev


def _documentos(db: Session, ev: Evaluacion) -> list[EvaluacionDocumento]:
    return db.scalars(select(EvaluacionDocumento).where(EvaluacionDocumento.evaluacion_id == ev.id)).all()


def crear(db: Session, *, fondo_id: uuid.UUID, nombre: str, protocolo: str | None, usuario_id: uuid.UUID) -> Evaluacion:
    ev = Evaluacion(id=uuid.uuid4(), fondo_id=fondo_id, nombre=" ".join(nombre.split())[:200],
                    protocolo=(protocolo or "").strip() or None, umbral_similitud=1.0, creada_por_id=usuario_id,
                    criterio=dict(CRITERIO_POR_DEFECTO))
    db.add(ev)
    db.flush()
    registrar(db, modulo="evaluacion", accion="evaluacion_creada", usuario_id=usuario_id, entidad_tipo="evaluacion",
              entidad_id=ev.id, detalle=ev.nombre, nuevo={"fondo_id": str(fondo_id), "metodo": "medida F1"})
    return ev


def descrito(db: Session, inst_id: uuid.UUID) -> bool:
    return db.scalar(select(Relacion.id).where(Relacion.destino_id == inst_id, Relacion.estado == "vigente",
                                               Relacion.codigo_ric == "has_or_had_instantiation").limit(1)) is not None


def agregar_documentos(db: Session, ev: Evaluacion, ids: list[uuid.UUID], usuario_id: uuid.UUID) -> int:
    """Solo documentos del fondo, listos y aún sin describir: si ya estuvieran descritos, no habría
    una primera validación que medir."""
    if ev.estado != "preparacion":
        raise ErrorEvaluacion("Los documentos se agregan mientras la evaluación está en preparación.", 409)
    if ev.sorteada_en:
        raise ErrorEvaluacion("El sorteo ya se hizo: agregar documentos lo cambiaría.", 409)
    ya = {d.instanciacion_id for d in _documentos(db, ev)}
    nuevos = 0
    for inst_id in dict.fromkeys(ids):
        inst = db.get(Instanciacion, inst_id)
        if inst is None or inst.fondo_id != ev.fondo_id:
            raise ErrorEvaluacion("Uno de los documentos no es de este fondo.")
        if inst.estado != "listo_para_descripcion" or not (inst.texto_extraido or "").strip():
            raise ErrorEvaluacion(f"«{inst.nombre_original}» no está listo para describir o no tiene texto.")
        if descrito(db, inst.id):
            raise ErrorEvaluacion(f"«{inst.nombre_original}» ya está descrito: no tendría una primera validación que medir.")
        from app.servicios import derechos

        if derechos.instanciacion_restringida(db, inst):
            raise ErrorEvaluacion(f"«{inst.nombre_original}» tiene información clasificada o reservada (Ley 1712 de "
                                  "2014): se excluye de la evaluación.")
        if inst.id not in ya:
            db.add(EvaluacionDocumento(id=uuid.uuid4(), evaluacion_id=ev.id, instanciacion_id=inst.id))
            nuevos += 1
    db.flush()
    registrar(db, modulo="evaluacion", accion="documentos_agregados", usuario_id=usuario_id, entidad_tipo="evaluacion",
              entidad_id=ev.id, nuevo={"agregados": nuevos})
    return nuevos


def quitar_documento(db: Session, ev: Evaluacion, inst_id: uuid.UUID, usuario_id: uuid.UUID) -> None:
    if ev.estado != "preparacion" or ev.sorteada_en:
        raise ErrorEvaluacion("Solo se quita un documento en preparación y antes del sorteo.", 409)
    d = _documento(db, ev, inst_id)
    db.delete(d)
    db.flush()
    registrar(db, modulo="evaluacion", accion="documento_quitado", usuario_id=usuario_id, entidad_tipo="evaluacion",
              entidad_id=ev.id, anterior={"instanciacion_id": str(inst_id)})


def _documento(db: Session, ev: Evaluacion, inst_id: uuid.UUID) -> EvaluacionDocumento:
    d = db.scalar(select(EvaluacionDocumento).where(EvaluacionDocumento.evaluacion_id == ev.id,
                                                   EvaluacionDocumento.instanciacion_id == inst_id))
    if d is None:
        raise ErrorEvaluacion("Ese documento no está en la evaluación.", 404)
    return d


def anio_de(nombre: str) -> str:
    """El año que aparece en el nombre del archivo, para estratificar el sorteo."""
    m = re.search(r"(?<!\d)(1[5-9]\d{2}|20\d{2})(?!\d)", nombre or "")
    return m.group(1) if m else "sin año"


def sortear(db: Session, ev: Evaluacion, semilla: int, desarrollo: int, usuario_id: uuid.UUID) -> dict:
    """Sorteo estratificado por año: en cada año se reparte la misma proporción de desarrollo.
    Con la misma semilla y los mismos documentos, el resultado es siempre el mismo."""
    if ev.estado != "preparacion":
        raise ErrorEvaluacion("El sorteo se hace en preparación, antes de iniciar.", 409)
    documentos = sorted(_documentos(db, ev), key=lambda d: str(d.instanciacion_id))
    if len(documentos) < 3:
        raise ErrorEvaluacion("Se necesitan al menos tres documentos para sortear.")
    if not 1 <= desarrollo < len(documentos):
        raise ErrorEvaluacion("El conjunto de desarrollo debe tener al menos un documento y dejar documentos para la prueba.")
    nombres = {i.id: i.nombre_original for i in db.scalars(select(Instanciacion).where(
        Instanciacion.id.in_([d.instanciacion_id for d in documentos])))}
    estratos: dict[str, list[EvaluacionDocumento]] = defaultdict(list)
    for d in documentos:
        estratos[anio_de(nombres.get(d.instanciacion_id, ""))].append(d)
    azar = random.Random(semilla)
    proporcion = desarrollo / len(documentos)
    elegidos: list[EvaluacionDocumento] = []
    sobrantes: list[EvaluacionDocumento] = []
    for anio in sorted(estratos):
        grupo = estratos[anio][:]
        azar.shuffle(grupo)
        k = int(len(grupo) * proporcion)
        elegidos += grupo[:k]
        sobrantes += grupo[k:]
    azar.shuffle(sobrantes)
    elegidos += sobrantes[:desarrollo - len(elegidos)]
    ids = {d.id for d in elegidos}
    for d in documentos:
        d.conjunto = "desarrollo" if d.id in ids else "prueba"
    ev.semilla, ev.sorteada_en = semilla, ahora()
    db.flush()
    resultado = {"semilla": semilla, "desarrollo": len(ids), "prueba": len(documentos) - len(ids),
                 "estratos": {a: len(g) for a, g in sorted(estratos.items())}}
    registrar(db, modulo="evaluacion", accion="sorteo_realizado", usuario_id=usuario_id, entidad_tipo="evaluacion",
              entidad_id=ev.id, nuevo=resultado)
    return resultado


def fijar_criterio(db: Session, ev: Evaluacion, datos: dict, usuario_id: uuid.UUID) -> dict:
    """Los umbrales se fijan antes de iniciar: cambiarlos después de ver los datos invalidaría el dictamen."""
    if ev.estado != "preparacion":
        raise ErrorEvaluacion("Los umbrales se fijan antes de iniciar y no cambian después.", 409)
    nuevo = validar_criterio(datos)
    anterior, ev.criterio = criterio_de(ev.criterio), nuevo
    registrar(db, modulo="evaluacion", accion="criterio_fijado", usuario_id=usuario_id, entidad_tipo="evaluacion",
              entidad_id=ev.id, anterior=anterior, nuevo=nuevo)
    db.flush()
    return nuevo


def version_del_sistema(motor: str | None, version_prompt: str | None) -> dict:
    """Con qué se mide: el sistema, el motor, la instrucción y el perfil de aplicación SHACL.
    Se guarda al iniciar la evaluación y no cambia después."""
    import hashlib
    import os

    from app.servicios import ric_o

    perfil = getattr(ric_o, "RUTA_PERFIL_SHACL", None) or os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "recursos", "ric-o", "perfil-ricora.shacl.ttl")
    huella = None
    if os.path.exists(perfil):
        with open(perfil, "rb") as f:
            huella = hashlib.sha256(f.read()).hexdigest()
    return {"sistema": os.environ.get("RICORA_VERSION") or os.environ.get("GIT_COMMIT") or "sin etiqueta",
            "motor": motor, "version_instruccion": version_prompt, "perfil_shacl_sha256": huella,
            "fijada_en": ahora().isoformat()}


def cambiar_estado(db: Session, ev: Evaluacion, estado: str, usuario_id: uuid.UUID) -> None:
    documentos = _documentos(db, ev)
    if estado == "en_curso":
        if ev.estado != "preparacion":
            raise ErrorEvaluacion("Solo se inicia una evaluación en preparación.", 409)
        if not ev.sorteada_en or not any(d.conjunto == "prueba" for d in documentos):
            raise ErrorEvaluacion("Antes de iniciar, sortee los documentos en desarrollo y prueba.", 409)
        from app.servicios import motor

        activo = motor.motor_activo()
        ev.criterio = criterio_de(ev.criterio)  # queda congelado tal como estaba al iniciar
        ev.iniciada_en = ahora()
        ev.version_congelada = version_del_sistema(activo.nombre if activo else None, motor.VERSION_PROMPT)
    elif estado == "cerrada":
        if ev.estado != "en_curso":
            raise ErrorEvaluacion("Solo se cierra una evaluación en curso.", 409)
        ev.cerrada_en = ahora()
    else:
        raise ErrorEvaluacion("Estado desconocido.")
    anterior, ev.estado = ev.estado, estado
    registrar(db, modulo="evaluacion", accion="evaluacion_iniciada" if estado == "en_curso" else "evaluacion_cerrada",
              usuario_id=usuario_id, entidad_tipo="evaluacion", entidad_id=ev.id,
              anterior={"estado": anterior}, nuevo={"estado": estado, "documentos": len(documentos),
                                                    **({"criterio": ev.criterio, "version": ev.version_congelada}
                                                       if estado == "en_curso" else {})})


# --- Decisiones de validación ----------------------------------------------------------------------


def _recursos_por_instanciacion(db: Session, inst_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    filas = db.execute(select(Relacion.destino_id, Relacion.origen_id).where(
        Relacion.destino_id.in_(inst_ids), Relacion.origen_tipo == "recurso_documental",
        Relacion.codigo_ric == "has_or_had_instantiation")).all()
    salida: dict[uuid.UUID, list[str]] = defaultdict(list)
    for inst, recurso in filas:
        if str(recurso) not in salida[inst]:
            salida[inst].append(str(recurso))
    return salida


def _primera_publicacion(eventos: list[RegistroAuditoria]) -> list[RegistroAuditoria]:
    """Las decisiones de la primera publicación del documento: las que comparten propuesta con el
    primer evento y caen en la misma ventana de tiempo. Las ediciones posteriores no cuentan."""
    if not eventos:
        return []
    eventos = sorted(eventos, key=lambda e: (e.fecha, e.id))
    primero = eventos[0]
    propuesta = (primero.valor_nuevo or {}).get("propuesta_id")
    return [e for e in eventos if (e.valor_nuevo or {}).get("propuesta_id") == propuesta
            and (e.fecha - primero.fecha).total_seconds() <= VENTANA_PUBLICACION]


def decisiones(db: Session, ev: Evaluacion, conjunto: str = "prueba") -> dict:
    """Las decisiones de validación de los documentos del conjunto, con su estado frente a la
    versión congelada."""
    from app.servicios.decisiones_ia import TIPO_NOMBRE, _texto

    documentos = [d for d in _documentos(db, ev) if d.conjunto == conjunto]
    inst = {i.id: i for i in db.scalars(select(Instanciacion).where(
        Instanciacion.id.in_([d.instanciacion_id for d in documentos])))} if documentos else {}
    recursos = _recursos_por_instanciacion(db, list(inst)) if inst else {}
    todos = [r for rs in recursos.values() for r in rs]
    eventos = db.scalars(select(RegistroAuditoria).where(RegistroAuditoria.accion == "decision_ia",
                                                        RegistroAuditoria.entidad_id.in_(todos))).all() if todos else []
    por_recurso: dict[str, list[RegistroAuditoria]] = defaultdict(list)
    for e in eventos:
        por_recurso[e.entidad_id].append(e)
    version = ev.version_congelada or {}
    filas, estado_docs, fuera = [], [], 0
    for d in documentos:
        i = inst.get(d.instanciacion_id)
        rs = recursos.get(d.instanciacion_id, [])
        elegidos = _primera_publicacion([e for r in rs for e in por_recurso.get(r, [])])
        validas = 0
        for e in elegidos:
            n = e.valor_nuevo or {}
            en_version = (not version.get("version_instruccion")
                          or n.get("version_prompt") in (None, version.get("version_instruccion")))
            if not en_version:
                fuera += 1
                continue
            validas += 1
            filas.append({"evento_id": e.id, "documento_id": str(d.instanciacion_id), "recurso_id": e.entidad_id,
                          "documento": n.get("titulo_documento") or (i.nombre_original if i else None),
                          "nombre_archivo": i.nombre_original if i else None,
                          "tipo": n.get("tipo"), "tipo_nombre": TIPO_NOMBRE.get(n.get("tipo"), n.get("tipo")),
                          "decision": n.get("decision"), "propuesto": _texto(n.get("propuesto")),
                          "final": _texto(n.get("final")), "confianza": n.get("confianza"),
                          "fragmento_localizado": n.get("fragmento_localizado"), "modelo": n.get("modelo"),
                          "version_prompt": n.get("version_prompt"), "usuario_id": str(e.usuario_id) if e.usuario_id else None,
                          "fecha": e.fecha})
        estado_docs.append({"instanciacion_id": str(d.instanciacion_id), "nombre": i.nombre_original if i else None,
                            "conjunto": d.conjunto, "publicado": bool(rs), "decisiones": validas})
    return {"filas": filas, "documentos": estado_docs, "fuera_de_version": fuera}


# --- Validación de control y causas de error -------------------------------------------------------


def _evento_de_prueba(db: Session, ev: Evaluacion, evento_id: int) -> dict:
    fila = next((f for f in decisiones(db, ev)["filas"] if f["evento_id"] == evento_id), None)
    if fila is None:
        raise ErrorEvaluacion("Esa decisión no pertenece al conjunto de prueba de esta evaluación.", 404)
    return fila


def control_pendiente(db: Session, ev: Evaluacion, inst_id: uuid.UUID, usuario_id: uuid.UUID) -> dict:
    """Las propuestas originales del motor de un documento de prueba, sin la decisión de la primera
    validadora, para que la segunda decida por su cuenta."""
    d = _documento(db, ev, inst_id)
    if d.conjunto != "prueba":
        raise ErrorEvaluacion("La validación de control se hace sobre documentos de prueba.", 409)
    filas = [f for f in decisiones(db, ev)["filas"] if f["documento_id"] == str(inst_id) and f["decision"] != "agregada"]
    if not filas:
        raise ErrorEvaluacion("Ese documento todavía no se ha validado y publicado en Descripción.", 409)
    if any(f["usuario_id"] == str(usuario_id) for f in filas):
        raise ErrorEvaluacion("La validación de control la hace una persona distinta de la que validó el documento.", 403)
    hechas = {c.evento_id: c.decision for c in db.scalars(select(Control).where(
        Control.evaluacion_id == ev.id, Control.usuario_id == usuario_id))}
    inst = db.get(Instanciacion, inst_id)
    return {"documento": {"id": str(inst_id), "nombre": inst.nombre_original, "texto": inst.texto_extraido},
            "propuestas": [{"evento_id": f["evento_id"], "tipo": f["tipo"], "tipo_nombre": f["tipo_nombre"],
                            "propuesto": f["propuesto"], "confianza": f["confianza"],
                            "mi_decision": hechas.get(f["evento_id"])} for f in filas]}


def guardar_control(db: Session, ev: Evaluacion, evento_id: int, decision: str, usuario_id: uuid.UUID) -> None:
    if ev.estado != "en_curso":
        raise ErrorEvaluacion("La validación de control se registra con la evaluación en curso.", 409)
    if decision not in ("aceptada", "corregida", "rechazada"):
        raise ErrorEvaluacion("La decisión es aceptada, corregida o rechazada.")
    fila = _evento_de_prueba(db, ev, evento_id)
    if fila["decision"] == "agregada":
        raise ErrorEvaluacion("Lo agregado por la archivista no es una propuesta del motor.")
    if fila["usuario_id"] == str(usuario_id):
        raise ErrorEvaluacion("La validación de control la hace una persona distinta de la que validó el documento.", 403)
    c = db.scalar(select(Control).where(Control.evaluacion_id == ev.id, Control.evento_id == evento_id,
                                        Control.usuario_id == usuario_id))
    anterior = c.decision if c else None
    if c is None:
        c = Control(id=uuid.uuid4(), evaluacion_id=ev.id, evento_id=evento_id, usuario_id=usuario_id, decision=decision)
        db.add(c)
    else:
        c.decision = decision
    db.flush()
    registrar(db, modulo="evaluacion", accion="control_registrado", usuario_id=usuario_id, entidad_tipo="evaluacion",
              entidad_id=ev.id, anterior={"decision": anterior} if anterior else None,
              nuevo={"evento_id": evento_id, "decision": decision})


def acuerdo(db: Session, ev: Evaluacion, filas: list[dict] | None = None) -> dict:
    filas = filas if filas is not None else decisiones(db, ev)["filas"]
    original = {f["evento_id"]: f for f in filas}
    pares = [(original[c.evento_id]["decision"], c.decision) for c in db.scalars(
        select(Control).where(Control.evaluacion_id == ev.id)) if c.evento_id in original]
    iguales = sum(1 for a, b in pares if a == b)
    docs = {original[c.evento_id]["documento_id"] for c in db.scalars(select(Control).where(
        Control.evaluacion_id == ev.id)) if c.evento_id in original}
    return {"pares": len(pares), "iguales": iguales, "documentos": len(docs),
            "porcentaje": _r(iguales / len(pares)) if pares else None}


def errores(db: Session, ev: Evaluacion) -> list[dict]:
    """Las decisiones que no fueron aceptadas, con la causa registrada si la hay."""
    filas = [f for f in decisiones(db, ev)["filas"] if f["decision"] != "aceptada"]
    causas = {c.clave: c for c in db.scalars(select(ClasificacionError).where(ClasificacionError.evaluacion_id == ev.id))}
    salida = []
    for f in filas:
        c = causas.get(str(f["evento_id"]))
        salida.append({k: f[k] for k in ("evento_id", "documento", "tipo", "tipo_nombre", "decision", "propuesto", "final")}
                      | {"causa": c.tipo_error if c else None, "nota": c.nota if c else None})
    return salida


def clasificar(db: Session, ev: Evaluacion, evento_id: int, causa: str, nota: str | None, usuario_id: uuid.UUID) -> None:
    if causa not in CAUSAS:
        raise ErrorEvaluacion("Causa desconocida: " + ", ".join(CAUSAS.values()) + ".")
    fila = _evento_de_prueba(db, ev, evento_id)
    if fila["decision"] == "aceptada":
        raise ErrorEvaluacion("Una propuesta aceptada no es un error.")
    clave = str(evento_id)
    c = db.scalar(select(ClasificacionError).where(ClasificacionError.evaluacion_id == ev.id,
                                                   ClasificacionError.clave == clave))
    anterior = c.tipo_error if c else None
    if c is None:
        c = ClasificacionError(id=uuid.uuid4(), evaluacion_id=ev.id, clave=clave, ronda="individual",
                               clasificadora_id=usuario_id, tipo_error=causa, nota=(nota or "").strip() or None)
        db.add(c)
    else:
        c.tipo_error, c.nota, c.clasificadora_id = causa, (nota or "").strip() or None, usuario_id
    db.flush()
    registrar(db, modulo="evaluacion", accion="causa_registrada", usuario_id=usuario_id, entidad_tipo="evaluacion",
              entidad_id=ev.id, anterior={"causa": anterior} if anterior else None,
              nuevo={"evento_id": evento_id, "causa": causa})


# --- Resultados -----------------------------------------------------------------------------------


def resultados(db: Session, ev: Evaluacion) -> dict:
    datos = decisiones(db, ev)
    m = metricas(datos["filas"])
    criterio = criterio_de(ev.criterio)
    a = acuerdo(db, ev, datos["filas"])
    a["umbral"] = criterio["acuerdo"]
    a["cumple"] = None if a["porcentaje"] is None else a["porcentaje"] >= criterio["acuerdo"]
    causas = defaultdict(int)
    for e in errores(db, ev):
        causas[e["causa"] or "sin_clasificar"] += 1
    avisos = []
    sin_publicar = [d["nombre"] for d in datos["documentos"] if not d["publicado"]]
    if sin_publicar:
        avisos.append(f"{len(sin_publicar)} documento(s) de prueba todavía no se han validado y publicado.")
    if datos["fuera_de_version"]:
        avisos.append(f"{datos['fuera_de_version']} decisión(es) se tomaron con otra versión de la instrucción y no "
                      "entran en el cálculo.")
    if ev.estado == "preparacion":
        avisos.append("La evaluación está en preparación: los resultados son provisionales hasta iniciarla.")
    return {"metricas": m, "dictamen": dictamen(m, criterio), "criterio": criterio, "acuerdo": a,
            "causas": [{"causa": k, "nombre": CAUSAS.get(k, "Sin clasificar"), "cantidad": v} for k, v in causas.items()],
            "documentos": datos["documentos"], "decisiones": len(datos["filas"]), "avisos": avisos,
            "version_congelada": ev.version_congelada}


def evaluacion_out(db: Session, ev: Evaluacion) -> dict:
    documentos = _documentos(db, ev)
    return {"id": str(ev.id), "nombre": ev.nombre, "protocolo": ev.protocolo, "estado": ev.estado,
            "creada_en": ev.creada_en, "iniciada_en": ev.iniciada_en, "cerrada_en": ev.cerrada_en,
            "documentos": len(documentos),
            "desarrollo": sum(1 for d in documentos if d.conjunto == "desarrollo"),
            "prueba": sum(1 for d in documentos if d.conjunto == "prueba"),
            "semilla": ev.semilla, "sorteada_en": ev.sorteada_en, "criterio": criterio_de(ev.criterio),
            "version_congelada": ev.version_congelada}


def documentos_out(db: Session, ev: Evaluacion) -> list[dict]:
    docs = _documentos(db, ev)
    inst = {i.id: i for i in db.scalars(select(Instanciacion).where(
        Instanciacion.id.in_([d.instanciacion_id for d in docs])))} if docs else {}
    publicados = _recursos_por_instanciacion(db, list(inst)) if inst else {}
    return sorted([{"instanciacion_id": str(d.instanciacion_id), "nombre": inst[d.instanciacion_id].nombre_original,
                    "anio": anio_de(inst[d.instanciacion_id].nombre_original), "conjunto": d.conjunto,
                    "publicado": bool(publicados.get(d.instanciacion_id))} for d in docs if d.instanciacion_id in inst],
                  key=lambda x: (x["conjunto"] or "", x["nombre"]))


def hoja_de_calculo(db: Session, ev: Evaluacion) -> bytes:
    """Resultados y decisiones en Excel. La hoja «Decisiones» usa los mismos encabezados que la
    exportación de Auditoría, para que el Anexo D la importe tal cual."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    from app.servicios.decisiones_ia import DECISION_NOMBRE

    datos = decisiones(db, ev)
    r = resultados(db, ev)
    m, dic = r["metricas"], r["dictamen"]
    libro = Workbook()
    h = libro.active
    h.title = "Resumen"
    h.append(["Evaluación", ev.nombre])
    h.append(["Versión congelada", ", ".join(f"{k}: {v}" for k, v in (ev.version_congelada or {}).items() if k != "perfil_shacl_sha256")])
    h.append(["Semilla del sorteo", ev.semilla])
    h.append([])
    h.append(["Medida", "Valor", "Límite inferior IC 95 %", "Límite superior IC 95 %", "Umbral", "Cumple"])
    for medida, nombre in (("f1", "Medida F1"), ("precision", "Precisión"), ("exhaustividad", "Exhaustividad")):
        ic = m["intervalos"][medida]
        d = dic[medida]
        h.append([nombre, m[medida], ic["inferior"], ic["superior"], d["umbral"],
                  None if d["cumple"] is None else ("Sí" if d["cumple"] else "No")])
    h.append(["Medida F1 macro", m["f1_macro"]])
    h.append(["Hipótesis", dic["hipotesis"]])
    h.append(["Acuerdo entre validadoras", r["acuerdo"]["porcentaje"], None, None, r["acuerdo"]["umbral"],
              None if r["acuerdo"]["cumple"] is None else ("Sí" if r["acuerdo"]["cumple"] else "No")])
    h.append([])
    h.append(["Tipo", "Aceptadas", "Corregidas", "Rechazadas", "Agregadas", "Precisión", "Exhaustividad", "Medida F1",
              "Texto libre"])
    for t in m["por_tipo"]:
        h.append([t["tipo"], t["aceptada"], t["corregida"], t["rechazada"], t["agregada"], t["precision"],
                  t["exhaustividad"], t["f1"], "Sí" if t["texto_libre"] else "No"])
    det = libro.create_sheet("Decisiones")
    det.append(["Fecha", "Documento", "Tipo", "Clase RiC-O", "Propuesto por el motor", "Valor final", "Decisión",
                "Propiedad RiC-O", "Confianza", "Modelo", "Versión de la instrucción", "Etiqueta", "Archivista",
                "Archivo", "Fragmento hallado"])
    for f in datos["filas"]:
        det.append([f["fecha"].replace(tzinfo=None), f["documento"], f["tipo_nombre"], None, f["propuesto"], f["final"],
                    DECISION_NOMBRE.get(f["decision"], f["decision"]), None, f["confianza"], f["modelo"],
                    f["version_prompt"], None, None, f["nombre_archivo"],
                    None if f["fragmento_localizado"] is None else ("Sí" if f["fragmento_localizado"] else "No")])
    ca = libro.create_sheet("Causas")
    ca.append(["Documento", "Tipo", "Decisión", "Propuesto", "Valor final", "Causa", "Nota"])
    for e in errores(db, ev):
        ca.append([e["documento"], e["tipo_nombre"], e["decision"], e["propuesto"], e["final"],
                   CAUSAS.get(e["causa"], "Sin clasificar"), e["nota"]])
    for hoja in (h, det, ca):
        for celda in hoja[1]:
            celda.font = Font(bold=True)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()
