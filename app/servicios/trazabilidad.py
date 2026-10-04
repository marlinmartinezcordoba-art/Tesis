"""
Módulo transversal de auditoría: las consultas.

El registro lo hace servicios/auditoria.registrar(), que llaman todos los
módulos. Aquí se lee ese registro para las tres vistas del prompt:
trazabilidad de una entidad, trazabilidad propia y panel consolidado
semanal por persona (calculado al vuelo; decisión en la documentación).

Nada de este archivo escribe en la auditoría: es de solo lectura, y la
base de datos rechaza cualquier UPDATE o DELETE sobre el registro.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.auditoria import RegistroAuditoria
from app.models.sesion import Sesion
from app.models.usuario import Usuario
from app.servicios.auditoria import Accion

# --- Catálogo de acciones: nombre legible y grupo del panel consolidado ---------------------------

# (texto, grupo). Grupo None = no cuenta como acción de trabajo en el panel
# (sesiones, intentos fallidos, eventos del propio sistema).
ACCIONES: dict[str, tuple[str, str | None]] = {
    Accion.INICIO_SESION: ("Inició sesión", None),
    Accion.CIERRE_SESION: ("Cerró sesión", None),
    Accion.INGRESO_FALLIDO: ("Intento de ingreso fallido", None),
    Accion.INGRESO_BLOQUEADO: ("Ingreso bloqueado por intentos", None),
    Accion.SOLICITUD_RECUPERACION: ("Pidió recuperar la contraseña", None),
    Accion.CONTRASENA_DEFINIDA: ("Definió su contraseña", None),
    Accion.CONTRASENA_CAMBIADA: ("Cambió su contraseña", None),
    Accion.USUARIO_CREADO: ("Creó un usuario", "Administración"),
    Accion.USUARIO_EDITADO: ("Editó un usuario", "Administración"),
    Accion.USUARIO_DESACTIVADO: ("Desactivó un usuario", "Administración"),
    Accion.USUARIO_REACTIVADO: ("Reactivó un usuario", "Administración"),
    Accion.ENLACE_ENVIADO: ("Envió un enlace de acceso", "Administración"),
    Accion.SESIONES_REVOCADAS: ("Cerró las sesiones de un usuario", "Administración"),
    Accion.CUENTA_ADMINISTRADORA_RESTABLECIDA: ("Cuenta administradora restablecida", None),
    Accion.SEGUNDO_FACTOR_ACTIVADO: ("Activó el segundo factor de su cuenta", None),
    Accion.SEGUNDO_FACTOR_DESACTIVADO: ("Quitó el segundo factor de su cuenta", None),
    Accion.SEGUNDO_FACTOR_RESTABLECIDO: ("Quitó el segundo factor de una cuenta (teléfono perdido)", "Administración"),
    Accion.CODIGO_RESPALDO_USADO: ("Entró con un código de respaldo", None),
    "rol_creado": ("Creó un rol", "Administración"),
    "rol_editado": ("Editó un rol", "Administración"),
    "parametro_cambiado": ("Cambió un parámetro", "Administración"),
    "fondo_registrado": ("Registró un fondo", "Administración"),
    "alerta_atendida": ("Atendió una alerta", "Alertas atendidas"),
    "consolidado_revisado": ("Revisó el registro de auditoría de la semana", None),
    # Ingesta
    "documento_cargado": ("Cargó un documento", "Documentos cargados"),
    "lote_creado": ("Abrió un lote de transferencia", "Lotes abiertos"),
    "rdf_publico_descargado": ("Descargó el RDF público del fondo", None),
    "ead3_exportado": ("Exportó el fondo en EAD3", None),
    "dip_entregado": ("Descargó el paquete de difusión (DIP) de una descripción", None),
    "lote_acta_fijada": ("Indicó el acta escaneada de un lote", None),
    "lote_confirmado": ("Confirmó un lote: paquete de envío y acuse de recibo", "Lotes recibidos"),
    "lote_anulado": ("Anuló un lote de transferencia", None),
    "carga_rechazada": ("Carga rechazada", None),
    "duplicado_confirmado": ("Confirmó que no era duplicado", "Documentos cargados"),
    "carga_cancelada": ("Canceló un duplicado", "Documentos cargados"),
    "carga_descartada": ("Descartó un documento con error", "Documentos cargados"),
    "reintento": ("Reintentó el procesamiento", "Documentos cargados"),
    # Descripción
    "descripcion_iniciada": ("Abrió una descripción", None),
    "descripcion_cancelada": ("Salió sin publicar", None),
    "edicion_liberada": ("Liberó una edición", None),
    "descripcion_publicada": ("Publicó una descripción", "Descripciones validadas"),
    "descripcion_editada": ("Corrigió una descripción", "Descripciones validadas"),
    "decision_ia": ("Decidió sobre una propuesta de la IA", None),
    "recorte_creado": ("Recortó una parte documental como instanciación propia", "Descripciones validadas"),
    # Vocabularios
    "fusion_vocabulario": ("Fusionó entidades del vocabulario", "Entidades del vocabulario"),
    "sugerencia_fusion_descartada": ("Descartó una sugerencia de fusión", "Entidades del vocabulario"),
    "agentes_relacionados": ("Relacionó dos agentes", "Entidades del vocabulario"),
    "entidad_enriquecida": ("Enriqueció una ficha de autoridad", "Entidades del vocabulario"),
    "nombre_agregado": ("Agregó una forma del nombre", "Entidades del vocabulario"),
    "nombre_anulado": ("Anuló una forma del nombre", "Entidades del vocabulario"),
    "identificador_agregado": ("Agregó un identificador", "Entidades del vocabulario"),
    "identificador_anulado": ("Anuló un identificador", "Entidades del vocabulario"),
    "hito_agregado": ("Agregó un hito institucional", "Entidades del vocabulario"),
    "hito_anulado": ("Anuló un hito institucional", "Entidades del vocabulario"),
    "vinculo_declarado": ("Declaró un vínculo entre entidades", "Entidades del vocabulario"),
    "vinculo_anulado": ("Anuló un vínculo entre entidades", "Entidades del vocabulario"),
    "concepto_superior_cambiado": ("Ubicó un tipo de actividad en el árbol de funciones", "Entidades del vocabulario"),
    "mecanismo_registrado": ("Registró un mecanismo (software) con su versión", None),
    # Instrumentos
    "inventario_exportado": ("Exportó un inventario", "Instrumentos generados"),
    "guia_exportada": ("Exportó una guía", "Instrumentos generados"),
    "rdf_exportado": ("Exportó el fondo en RiC-O (RDF)", "Instrumentos generados"),
    "grafo_exportado": ("Exportó un fragmento del grafo del fondo en RiC-O (RDF)", "Instrumentos generados"),
    "hallazgo_creado": ("Registró un hallazgo de conformidad", "Hallazgos de conformidad"),
    "evaluacion_creada": ("Creó una evaluación ciega", "Evaluación"),
    "documentos_agregados": ("Agregó documentos a una evaluación", "Evaluación"),
    "propuestas_generadas": ("Generó las propuestas del motor para una evaluación", "Evaluación"),
    "evaluacion_iniciada": ("Inició una evaluación", "Evaluación"),
    "evaluacion_cerrada": ("Cerró una evaluación", "Evaluación"),
    "anotacion_iniciada": ("Empezó a describir un documento de una evaluación", "Evaluación"),
    "anotacion_enviada": ("Envió la descripción de un documento de una evaluación", "Evaluación"),
    "anotacion_anulada": ("Anuló una anotación de una evaluación", "Evaluación"),
    "propuesta_vista": ("Vio la propuesta del motor en una evaluación", "Evaluación"),
    "calificacion_registrada": ("Calificó una propuesta del motor con la rúbrica", "Evaluación"),
    "resultados_consultados": ("Consultó los resultados de una evaluación", "Evaluación"),
    "hallazgo_actualizado": ("Cambió el estado o la acción de un hallazgo", "Hallazgos de conformidad"),
    "version_prompt_etiquetada": ("Puso nombre a una versión de la instrucción del motor", "Administración"),
    "conformidad_rico_validada": ("Validó la conformidad con RiC-O (OWL y SHACL)", "Instrumentos generados"),
    # Preservación
    "integridad_verificada": ("Verificó la integridad", "Verificaciones de integridad"),
    "migracion_aprobada": ("Aprobó una migración", "Migraciones"),
    "migracion_completada": ("Migración completada", None),
    "migracion_fallida": ("Migración fallida", None),
    "segunda_copia_creada": ("Creó una segunda copia", None),
    "copia_primaria_restaurada": ("Restauró la copia primaria desde la segunda copia", "Restauraciones"),
    "derechos_declarados": ("Declaró derechos", "Declaraciones de derechos"),
    "paquete_exportado": ("Exportó un paquete de preservación (AIP)", "Paquetes de preservación"),
    "custodio_registrado": ("Registró un tramo de la custodia de un archivo", None),
    "regla_creada": ("Creó una regla de retención (TRD)", "Reglas de retención"),
    "agrupacion_creada": ("Creó una agrupación del cuadro de clasificación", "Agrupaciones"),
    "inclusion_adicional": ("Incluyó una descripción en otro conjunto", None),
    "documento_individualizado": ("Separó un documento de su conjunto", None),
    "original_fisico_registrado": ("Registró el original físico de un documento", None),
    "original_fisico_actualizado": ("Corrigió la ubicación, la signatura o el estado de conservación del original físico", None),
    "proteccion_datos_declarada": ("Declaró los datos personales (Ley 1581) o la versión accesible de una descripción", None),
    "segunda_copia_reposicion_encargada": ("Encargó rehacer una segunda copia", None),
    "respaldo_bd": ("Respaldó la base de datos", "Respaldos de la base de datos"),
    "simulacro_restauracion": ("Probó restaurar un respaldo de la base", None),
    "respaldo_descargado": ("Descargó un respaldo fuera del servidor", None),
    "paquete_recuperacion": ("Armó el paquete de recuperación ante desastres", None),
    "simulacro_recuperacion": ("Probó restaurar el sistema completo desde el paquete de recuperación", None),
    "paquete_recuperacion_descargado": ("Descargó el paquete de recuperación fuera del servidor", None),
}


def etiqueta(accion: str) -> str:
    return ACCIONES.get(accion, (accion.replace("_", " ").capitalize(), None))[0]


def grupo(accion: str) -> str | None:
    return ACCIONES.get(accion, (None, None))[1]


# --- Serialización con valores antes y después ------------------------------------------------------


def _cambios(anterior, nuevo) -> list[dict]:
    """Pares campo / antes / después para mostrarlos lado a lado. Solo
    cuando la acción cambió un valor existente (hay «antes»): en una
    creación no hay nada que comparar y los datos van en el detalle."""
    if not isinstance(anterior, dict):
        return []
    anterior, nuevo = anterior or {}, nuevo or {}
    return [{"campo": k, "antes": anterior.get(k), "despues": nuevo.get(k)}
            for k in list(dict.fromkeys([*anterior, *nuevo])) if anterior.get(k) != nuevo.get(k)]


# Entidades cuyos cambios son descripción archivística: solo en ellas tiene
# sentido la columna «propiedad RiC-O» (un cambio de rol de usuario, no).
ENTIDADES_ARCHIVISTICAS = {"recurso_documental", "entidad_vocabulario", "instanciacion"}


def _propiedad_del_evento(e: RegistroAuditoria) -> dict | None:
    """Si el evento es sobre una relación del grafo (vínculo declarado o
    anulado, decisión del motor), la propiedad de RiC-O que representa."""
    from app.servicios import ric_o

    for valores in (e.valor_nuevo, e.valor_anterior):
        if isinstance(valores, dict):
            if valores.get("codigo_ric"):
                return ric_o.propiedad_de_codigo(valores["codigo_ric"])
            if "skos:broader" in valores:
                return {"nombre": "skos:broader", "estado": "verificada", "codigo_cm": None}
    return None


def evento_out(e: RegistroAuditoria, nombres: dict) -> dict:
    from app.servicios import ric_o

    cambios = _cambios(e.valor_anterior, e.valor_nuevo)
    if e.entidad_tipo in ENTIDADES_ARCHIVISTICAS:
        for c in cambios:
            c["propiedad_rico"] = ric_o.propiedad_de_campo(c["campo"])
    return {"id": e.id, "fecha": e.fecha, "usuario_id": str(e.usuario_id) if e.usuario_id else None,
            "usuario": nombres.get(e.usuario_id) if e.usuario_id else "El sistema",
            "modulo": e.modulo, "accion": e.accion, "etiqueta": etiqueta(e.accion),
            "entidad_tipo": e.entidad_tipo, "entidad_id": e.entidad_id, "detalle": e.detalle,
            "propiedad_rico": _propiedad_del_evento(e), "cambios": cambios}


def _nombres(db: Session) -> dict:
    return dict(db.execute(select(Usuario.id, Usuario.nombre)).all())


# --- Trazabilidad por entidad y propia ------------------------------------------------------------

# Qué permiso de módulo hace falta para ver la historia de cada tipo de entidad.
MODULO_DE_ENTIDAD = {
    "recurso_documental": "descripcion", "instanciacion": "ingesta", "entidad_vocabulario": "vocabularios",
    "hallazgo": "usuarios", "version_prompt": "usuarios", "evaluacion": "usuarios",
    "sugerencia_fusion": "vocabularios", "trabajo_descripcion": "descripcion",
    "usuario": "usuarios", "rol": "usuarios", "sesion": "usuarios", "parametro": "usuarios", "alerta": None,
}


def entidad(db: Session, entidad_tipo: str, entidad_id: str, *, solo_de: uuid.UUID | None) -> list[dict]:
    consulta = select(RegistroAuditoria).where(RegistroAuditoria.entidad_id == entidad_id)
    if entidad_tipo:
        consulta = consulta.where(RegistroAuditoria.entidad_tipo == entidad_tipo)
    if solo_de is not None:
        consulta = consulta.where(RegistroAuditoria.usuario_id == solo_de)
    filas = db.scalars(consulta.order_by(RegistroAuditoria.fecha.desc(), RegistroAuditoria.id.desc()).limit(500)).all()
    nombres = _nombres(db)
    return [evento_out(e, nombres) for e in filas]


def _consulta_propia(usuario_id: uuid.UUID, accion: str | None, modulo: str | None, desde: date | None,
                     hasta: date | None):
    consulta = select(RegistroAuditoria).where(RegistroAuditoria.usuario_id == usuario_id)
    if accion:
        consulta = consulta.where(RegistroAuditoria.accion == accion)
    if modulo:
        consulta = consulta.where(RegistroAuditoria.modulo == modulo)
    if desde:
        consulta = consulta.where(RegistroAuditoria.fecha >= _inicio_local(desde))
    if hasta:
        consulta = consulta.where(RegistroAuditoria.fecha < _inicio_local(hasta + timedelta(days=1)))
    return consulta


def propia(db: Session, usuario_id: uuid.UUID, *, accion: str | None = None, modulo: str | None = None,
           desde: date | None = None, hasta: date | None = None, limite: int = 200, antes_de: int | None = None) -> dict:
    from sqlalchemy import func

    total = db.scalar(select(func.count()).select_from(
        _consulta_propia(usuario_id, accion, modulo, desde, hasta).subquery()))
    consulta = _consulta_propia(usuario_id, accion, modulo, desde, hasta)
    if antes_de:
        consulta = consulta.where(RegistroAuditoria.id < antes_de)
    filas = db.scalars(consulta.order_by(RegistroAuditoria.id.desc()).limit(limite + 1)).all()
    nombres = _nombres(db)
    return {"eventos": [evento_out(e, nombres) for e in filas[:limite]], "total": total,
            "siguiente": filas[limite - 1].id if len(filas) > limite else None}


# --- Exportación completa a Excel (patrón «historial reciente») -------------------------------------


def _mecanismo(e: RegistroAuditoria) -> str | None:
    """El agente mecanismo (el motor y su versión) cuando el evento lo cita."""
    for v in (e.valor_nuevo, e.valor_anterior):
        if isinstance(v, dict) and (v.get("modelo") or v.get("motor")):
            return " · ".join(str(x) for x in (v.get("modelo") or v.get("motor"), v.get("version_prompt")) if x)
    return None


def _texto_cambios(cambios: list[dict]) -> str:
    return "; ".join(f"{c['campo']}: {c['antes']} → {c['despues']}" for c in cambios)


def hoja_propia(db: Session, usuario_id: uuid.UUID, *, accion: str | None = None, modulo: str | None = None,
                desde: date | None = None, hasta: date | None = None) -> bytes:
    """Toda la trazabilidad propia que cumple los filtros, no solo la visible."""
    from app.servicios.hoja import libro

    filas = db.scalars(_consulta_propia(usuario_id, accion, modulo, desde, hasta)
                       .order_by(RegistroAuditoria.id.desc())).all()
    nombres = _nombres(db)
    datos = []
    for e in filas:
        o = evento_out(e, nombres)
        prop = o["propiedad_rico"] or {}
        datos.append([e.id, e.fecha, o["usuario"], e.modulo, o["etiqueta"], e.accion, e.entidad_tipo, e.entidad_id,
                      e.detalle, prop.get("nombre"), _texto_cambios(o["cambios"]), _mecanismo(e)])
    return libro([("Trazabilidad", ["Identificador del evento", "Fecha (hora de Bogotá)", "Persona", "Módulo", "Acción",
                                    "Código de la acción", "Tipo de entidad", "Identificador de la entidad", "Detalle",
                                    "Propiedad RiC-O", "Cambios (antes → después)", "Agente mecanismo (motor)"], datos)])


def hoja_consolidado(db: Session, dia: date) -> bytes:
    """La semana completa: una fila por persona y, en otra hoja, cada sesión."""
    from app.servicios.hoja import libro

    datos = consolidado(db, dia)
    grupos = sorted({g for f in datos["filas"] for g in f["acciones"]})
    personas = [[f["nombre"], f["rol_nombre"], "sí" if f["activo"] else "no", f["dias_habiles_trabajados"], f["dias_habiles"],
                 f["dias_fin_de_semana"], round(f["segundos_conectado"] / 3600, 2), f["sesiones"],
                 *[f["acciones"].get(g, 0) for g in grupos], f["usuario_id"]] for f in datos["filas"]]
    sesiones = []
    for f in datos["filas"]:
        usuario = db.get(Usuario, uuid.UUID(f["usuario_id"]))
        for s in desglose(db, usuario, dia)["sesiones"]:
            sesiones.append([f["nombre"], s["inicio"], s["fin"], round(s["segundos"] / 60, 1), s["motivo"],
                             "sí" if s["en_curso"] else "no", "; ".join(f"{k}: {v}" for k, v in sorted(s["acciones"].items())),
                             s["sesion_id"]])
    return libro([
        (f"Semana {datos['semana']['lunes']}", ["Persona", "Rol", "Activa", "Días hábiles trabajados", "Días hábiles de la semana",
                                                "Días de fin de semana", "Horas conectada", "Sesiones",
                                                *[f"Acciones · {g}" for g in grupos], "Identificador de la persona"], personas),
        ("Sesiones", ["Persona", "Inicio", "Fin", "Minutos", "Cómo terminó", "En curso", "Acciones durante la sesión",
                      "Identificador de la sesión"], sesiones)])


def acciones_de(db: Session, usuario_id: uuid.UUID | None) -> list[dict]:
    """Tipos de acción presentes (para los filtros), con su nombre legible."""
    consulta = select(RegistroAuditoria.accion, RegistroAuditoria.modulo).distinct()
    if usuario_id is not None:
        consulta = consulta.where(RegistroAuditoria.usuario_id == usuario_id)
    return sorted(({"accion": a, "modulo": m, "etiqueta": etiqueta(a)} for a, m in db.execute(consulta).all()),
                  key=lambda x: (x["modulo"], x["etiqueta"]))


# --- Panel consolidado semanal (al vuelo) -----------------------------------------------------------


def _zona() -> ZoneInfo:
    return ZoneInfo(settings.zona_horaria)


def _inicio_local(dia: date) -> datetime:
    return datetime.combine(dia, time.min, tzinfo=_zona())


def lunes_de(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


@dataclass
class TramoSesion:
    sesion_id: str
    inicio: datetime
    fin: datetime
    en_curso: bool
    motivo: str | None


def _sesiones(db: Session, usuario_ids: list[uuid.UUID], desde: datetime, hasta: datetime) -> dict:
    """Sesiones de cada persona que tocan el intervalo, reconstruidas desde
    los eventos de inicio y cierre de la auditoría (la fuente que no se
    puede alterar). Una sesión aún abierta termina en su última actividad."""
    margen = timedelta(hours=settings.horas_maximas_sesion + 1)
    inicios = db.scalars(select(RegistroAuditoria).where(
        RegistroAuditoria.accion == Accion.INICIO_SESION, RegistroAuditoria.usuario_id.in_(usuario_ids),
        RegistroAuditoria.fecha >= desde - margen, RegistroAuditoria.fecha < hasta)).all()
    ids = [e.entidad_id for e in inicios]
    cierres = {e.entidad_id: e for e in db.scalars(select(RegistroAuditoria).where(
        RegistroAuditoria.accion == Accion.CIERRE_SESION, RegistroAuditoria.entidad_id.in_(ids)))} if ids else {}
    abiertas = {str(s.id): s for s in db.scalars(select(Sesion).where(
        Sesion.id.in_([uuid.UUID(i) for i in ids if i]), Sesion.cerrada_en.is_(None)))} if ids else {}
    por_usuario = defaultdict(list)
    for e in inicios:
        inicio = datetime.fromisoformat((e.valor_nuevo or {}).get("inicio") or e.fecha.isoformat())
        cierre = cierres.get(e.entidad_id)
        if cierre is not None:
            fin, en_curso, motivo = datetime.fromisoformat(cierre.valor_nuevo["fin"]), False, cierre.valor_nuevo.get("motivo")
        elif e.entidad_id in abiertas:
            fin, en_curso, motivo = max(abiertas[e.entidad_id].ultima_actividad, inicio), True, None
        else:
            continue  # sin cierre ni sesión abierta: datos incompletos, no se inventa una duración
        # Solo la parte que cae dentro del intervalo consultado.
        tramo_inicio, tramo_fin = max(inicio, desde), min(fin, hasta)
        if tramo_fin > tramo_inicio or (tramo_fin == tramo_inicio and desde <= inicio < hasta):
            por_usuario[e.usuario_id].append(TramoSesion(e.entidad_id, tramo_inicio, tramo_fin, en_curso, motivo))
    for tramos in por_usuario.values():
        tramos.sort(key=lambda t: t.inicio)
    return por_usuario


def _dias_locales(inicio: datetime, fin: datetime) -> set[date]:
    zona = _zona()
    a, b = inicio.astimezone(zona).date(), fin.astimezone(zona).date()
    return {a + timedelta(days=i) for i in range((b - a).days + 1)}


def _dias_habiles(lunes: date) -> int:
    """Días hábiles (lunes a viernes) de la semana; en la semana en curso,
    solo los que ya empezaron."""
    hoy = ahora().astimezone(_zona()).date()
    return sum(1 for i in range(5) if lunes + timedelta(days=i) <= hoy)


def consolidado(db: Session, dia: date) -> dict:
    lunes = lunes_de(dia)
    desde, hasta = _inicio_local(lunes), _inicio_local(lunes + timedelta(days=7))
    # Todas las personas activas, más las inactivas que trabajaron esa semana.
    usuarios = db.scalars(select(Usuario).order_by(Usuario.nombre)).all()
    sesiones = _sesiones(db, [u.id for u in usuarios], desde, hasta)
    acciones = defaultdict(lambda: defaultdict(int))
    for usuario_id, accion in db.execute(select(RegistroAuditoria.usuario_id, RegistroAuditoria.accion).where(
            RegistroAuditoria.fecha >= desde, RegistroAuditoria.fecha < hasta,
            RegistroAuditoria.usuario_id.is_not(None))).all():
        if grupo(accion):
            acciones[usuario_id][grupo(accion)] += 1
    habiles = _dias_habiles(lunes)
    filas = []
    for u in usuarios:
        tramos = sesiones.get(u.id, [])
        if not u.activo and not tramos and not acciones.get(u.id):
            continue
        dias = set().union(*(_dias_locales(t.inicio, t.fin) for t in tramos)) if tramos else set()
        segundos = sum((t.fin - t.inicio).total_seconds() for t in tramos)
        filas.append({
            "usuario_id": str(u.id), "nombre": u.nombre, "rol": u.rol, "rol_nombre": u.rol_info.nombre if u.rol_info else u.rol,
            "activo": u.activo,
            "dias_trabajados": len(dias), "dias_habiles_trabajados": sum(1 for d in dias if d.weekday() < 5),
            "dias_fin_de_semana": sum(1 for d in dias if d.weekday() >= 5), "dias_habiles": habiles,
            "segundos_conectado": int(segundos), "sesiones": len(tramos),
            "en_curso": any(t.en_curso for t in tramos),
            "acciones": dict(sorted(acciones.get(u.id, {}).items())),
        })
    return {"semana": {"lunes": lunes.isoformat(), "domingo": (lunes + timedelta(days=6)).isoformat(),
                       "anterior": (lunes - timedelta(days=7)).isoformat(),
                       "siguiente": (lunes + timedelta(days=7)).isoformat() if lunes + timedelta(days=7) <= ahora().date() else None,
                       "zona_horaria": settings.zona_horaria},
            "filas": filas}


def desglose(db: Session, usuario: Usuario, dia: date) -> dict:
    lunes = lunes_de(dia)
    desde, hasta = _inicio_local(lunes), _inicio_local(lunes + timedelta(days=7))
    tramos = _sesiones(db, [usuario.id], desde, hasta).get(usuario.id, [])
    eventos = db.scalars(select(RegistroAuditoria).where(
        RegistroAuditoria.usuario_id == usuario.id, RegistroAuditoria.fecha >= desde, RegistroAuditoria.fecha < hasta)
        .order_by(RegistroAuditoria.fecha)).all()
    salida = []
    for t in tramos:
        durante = defaultdict(int)
        for e in eventos:
            if grupo(e.accion) and t.inicio <= e.fecha <= t.fin + timedelta(seconds=1):
                durante[grupo(e.accion)] += 1
        salida.append({"sesion_id": t.sesion_id, "inicio": t.inicio, "fin": t.fin, "en_curso": t.en_curso,
                       "motivo": t.motivo, "segundos": int((t.fin - t.inicio).total_seconds()),
                       "acciones": dict(durante)})
    return {"usuario": {"id": str(usuario.id), "nombre": usuario.nombre}, "semana": lunes.isoformat(),
            "sesiones": salida, "segundos_conectado": sum(s["segundos"] for s in salida)}


def revisiones_de(db: Session, lunes: date) -> list[dict]:
    """Constancias de revisión del registro de esa semana (NDSA, Control, nivel 4)."""
    filas = db.execute(select(RegistroAuditoria, Usuario.nombre).outerjoin(Usuario, Usuario.id == RegistroAuditoria.usuario_id)
                       .where(RegistroAuditoria.accion == "consolidado_revisado",
                              RegistroAuditoria.entidad_id == lunes.isoformat())
                       .order_by(RegistroAuditoria.fecha)).all()
    return [{"fecha": r.fecha, "por": nombre, "nota": (r.valor_nuevo or {}).get("nota")} for r, nombre in filas]
