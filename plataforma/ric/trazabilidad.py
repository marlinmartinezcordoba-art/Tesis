"""M7 · Trazabilidad de la descripción de un documento (RF-M7-01 a 03).

Une las dos fuentes que ya registran todo sin excepción:
- la bitácora encadenada por hash (EventoRiC, estilo PREMIS): qué propuso
  el motor, qué decidió cada persona, cada carga, extracción y publicación;
- la auditoría de cambios (RegistroAuditoria, módulo 0): el valor anterior
  y el nuevo de cada campo del documento, sus archivos y sus relaciones.

Cada punto de la línea de tiempo es un evento de la bitácora con los
cambios de campo que ocurrieron en ese mismo instante por la misma persona;
un cambio auditado sin evento propio aparece como punto aparte. Nada se
deduce ni se inventa: todo sale de registros que ya existen.

La reconstrucción de un instante (`descripcion_en`) usa VersionRiC, que
guarda cómo estaba cada entidad y cada relación ANTES de cada cambio.
"""

import csv
import io
import json
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from . import flujo, reglas
from .models import EventoRiC, Instantiation, Record, RegistroAuditoria, RelacionRiC, VersionRiC

# Una decisión genera a la vez su evento y sus cambios auditados; se agrupan
# si ocurren dentro de esta ventana y por la misma persona.
_VENTANA = timedelta(seconds=3)

_ETIQUETAS_DETALLE = {
    "antes": "Valor anterior", "despues": "Valor nuevo", "de": "Tipo anterior", "a": "Tipo nuevo",
    "motivo": "Motivo", "nota": "Nota", "decision": "Decisión", "revision": "Revisión", "entidad": "Entidad",
    "relacion": "Relación n.º", "pagina": "Página", "confianza_ocr": "Confianza OCR", "paginas": "Páginas",
    "caracteres": "Caracteres", "sha256": "Huella SHA-256", "archivo": "Archivo", "expediente": "Expediente",
    "serie": "Serie", "formato": "Formato", "tipo_mime": "Tipo MIME", "tamano_bytes": "Tamaño (bytes)",
    "propuestas": "Propuestas", "proveedor": "Proveedor", "modelo": "Modelo", "error": "Error",
    "forma_documental": "Forma documental", "retirado_del_catalogo": "Retirado del catálogo",
    "rechazada_en_revision": "Rechazada en revisión", "intento": "Intento", "record": "Documento n.º",
    "relaciones": "Relaciones", "entidad_nombre": "Entidad", "relacion_id": "Relación RiC", "estado": "Estado",
    "confianza": "Confianza", "propuesta": "Propuesta n.º", "mecanismo_id": "Motor (Mechanism E13) n.º",
    "evidencia_verificada": "Evidencia encontrada en el texto", "rechazada_automaticamente": "Descartada por las reglas RiC",
    "motivo_rechazo": "Motivo del descarte", "idioma": "Idioma", "cola": "Cola", "mensaje": "Mensaje",
    "exportacion_historial": "Exportación del historial",
}
_TIPO_ACTOR = {
    EventoRiC.Tipo.PROPUESTA_IA: "ia",
    EventoRiC.Tipo.EXTRACCION: "sistema",
    EventoRiC.Tipo.INGESTA: "humano",
}


def _legible(valor):
    if valor is True:
        return "sí"
    if valor is False:
        return "no"
    if valor in (None, ""):
        return "—"
    if isinstance(valor, (list, dict)):
        return json.dumps(valor, ensure_ascii=False)[:300]
    return str(valor)[:300]


def _objetos_del_documento(record):
    """(content_type, ids) de todo lo que forma la descripción del documento."""
    ct_rel = ContentType.objects.get_for_model(RelacionRiC)
    ct_inst = ContentType.objects.get_for_model(Instantiation)
    relaciones = list(flujo.relaciones_de(record, solo_validadas=False).values_list("pk", flat=True))
    relaciones += list(RelacionRiC.todos.filter(
        Q(origen_object_id=record.pk, origen_content_type__model="record")
        | Q(destino_object_id=record.pk, destino_content_type__model="record"),
        eliminado=True,
    ).values_list("pk", flat=True))
    return [
        (ContentType.objects.get_for_model(Record), [record.pk]),
        (ct_inst, list(Instantiation.todos.filter(record_resource=record).values_list("pk", flat=True))),
        (ct_rel, relaciones),
    ]


def _cambios_auditados(registro):
    """[{campo, antes, despues}] a partir de antes/después de la auditoría."""
    antes, despues = registro.antes or {}, registro.despues or {}
    modelo = registro.content_type.model_class() if registro.content_type_id else None
    cambios = []
    for campo in sorted(set(antes) | set(despues)):
        if antes.get(campo) == despues.get(campo):
            continue
        etiqueta = campo
        if modelo is not None:
            try:
                etiqueta = str(modelo._meta.get_field(campo).verbose_name)
            except Exception:
                pass
        cambios.append({"campo": etiqueta, "antes": _legible(antes.get(campo)), "despues": _legible(despues.get(campo))})
    return cambios


def _cambios_del_evento(evento):
    detalle = evento.detalle or {}
    if "antes" in detalle or "despues" in detalle:
        filas = [{"campo": "Valor", "antes": _legible(detalle.get("antes")), "despues": _legible(detalle.get("despues"))}]
    elif "de" in detalle and "a" in detalle:
        filas = [{"campo": "Tipo de relación", "antes": _legible(detalle.get("de")), "despues": _legible(detalle.get("a"))}]
    else:
        filas = []
    datos = [{"campo": _ETIQUETAS_DETALLE.get(k, k.replace("_", " ")), "valor": _legible(v)}
             for k, v in detalle.items() if k not in ("antes", "despues", "de", "a")]
    return filas, datos


def linea_de_tiempo(record):
    """Todos los puntos del historial del documento, del más antiguo al más
    reciente: [{fecha, usuario, tipo, titulo, actor, cambios, datos, evento}]."""
    eventos = list(
        EventoRiC.objects.filter(instanciacion__record_resource=record).select_related("instanciacion").order_by("fecha", "id")
    )
    filtro = Q()
    for ct, ids in _objetos_del_documento(record):
        if ids:
            filtro |= Q(content_type=ct, object_id__in=ids)
    registros = list(
        RegistroAuditoria.objects.filter(filtro).exclude(accion=RegistroAuditoria.Accion.CONSULTAR).order_by("fecha", "id")
    ) if filtro else []

    puntos = []
    for e in eventos:
        cambios, datos = _cambios_del_evento(e)
        puntos.append({
            "fecha": e.fecha, "usuario": e.agente, "tipo": e.tipo, "titulo": e.get_tipo_display(),
            "actor": _TIPO_ACTOR.get(e.tipo, "humano") if e.exitoso else "error", "exitoso": e.exitoso,
            "archivo": e.instanciacion.nombre if e.instanciacion else "", "cambios": cambios, "datos": datos,
            "evento": e, "id": f"e{e.pk}",
        })
    usados = set()
    for r in registros:
        cambios = _cambios_auditados(r)
        if not cambios and r.accion == RegistroAuditoria.Accion.MODIFICAR:
            continue
        destino = next((p for p in puntos if p["evento"] is not None and p["usuario"] == r.usuario_nombre
                        and abs(p["fecha"] - r.fecha) <= _VENTANA), None)
        if destino is not None and r.accion == RegistroAuditoria.Accion.MODIFICAR:
            for c in cambios:
                c["campo"] = f"{r.objeto_texto[:60]} · {c['campo']}" if r.content_type.model != "record" else c["campo"]
            destino["cambios"].extend(cambios)
            usados.add(r.pk)
            continue
        puntos.append({
            "fecha": r.fecha, "usuario": r.usuario_nombre or "sistema", "tipo": f"auditoria_{r.accion}",
            "titulo": f"{r.get_accion_display()} · {r.objeto_texto[:80]}", "actor": "humano" if r.usuario_id else "sistema",
            "exitoso": r.exitoso, "archivo": "", "cambios": cambios if r.accion == RegistroAuditoria.Accion.MODIFICAR else [],
            "datos": [{"campo": "Detalle", "valor": _legible(r.detalle)}] if r.detalle else [], "evento": None, "id": f"a{r.pk}",
        })
    puntos.sort(key=lambda p: (p["fecha"], p["id"]))
    return puntos


def _version_en(modelo, pk, momento):
    """Cómo estaba una entidad o relación en `momento`: la primera
    fotografía tomada DESPUÉS (guarda el estado anterior al cambio), o None
    si no cambió desde entonces (vale el estado actual)."""
    version = (
        VersionRiC.objects.filter(content_type=ContentType.objects.get_for_model(modelo), object_id=pk, fecha__gt=momento)
        .order_by("fecha", "id").first()
    )
    return version.datos_anteriores if version else None


def descripcion_en(record, momento):
    """RF-M7-03: la descripción completa del documento en `momento`, en
    solo lectura: sus datos propios y sus relaciones (incluidas las que
    después se retiraron o rechazaron), con el nombre que cada entidad
    tenía entonces."""
    datos_record = _version_en(Record, record.pk, momento) or {}
    ficha = {
        "nombre": datos_record.get("nombre", record.nombre),
        "forma_documental": datos_record.get("tipo_forma_documental", record.tipo_forma_documental) or "—",
        "idioma": datos_record.get("idioma", record.idioma) or "—",
        "publicado": datos_record.get("publicado", record.publicado),
        "existia": record.fecha_registro <= momento,
    }
    matriz = reglas.cargar_matriz()["relaciones"]
    filas = []
    relaciones = RelacionRiC.todos.filter(
        Q(origen_object_id=record.pk, origen_content_type__model="record")
        | Q(destino_object_id=record.pk, destino_content_type__model="record"),
        fecha_creacion__lte=momento,
    ).order_by("fecha_creacion", "id")
    for rel in relaciones:
        datos = _version_en(RelacionRiC, rel.pk, momento) or {}
        if datos.get("eliminado", rel.eliminado):  # ya estaba borrada lógicamente en ese momento
            continue
        entidad = flujo.otro_lado(rel, record)
        nombre_entidad = str(entidad) if entidad is not None else "(entidad retirada)"
        if entidad is not None:
            version_entidad = _version_en(type(entidad), entidad.pk, momento)
            if version_entidad and version_entidad.get("nombre"):
                nombre_entidad = version_entidad["nombre"]
        relacion_id = datos.get("relacion_id", rel.relacion_id)
        filas.append({
            "relacion_id": relacion_id,
            "nombre_relacion": matriz.get(relacion_id, {}).get("nombre", relacion_id),
            "estado": datos.get("estado", rel.estado),
            "revision": datos.get("revision", rel.revision),
            "entidad": nombre_entidad,
            "tipo_entidad": entidad._meta.verbose_name if entidad is not None else "",
            "reconstruida": bool(datos),
        })
    ficha["relaciones"] = filas
    return ficha


def exportar(record, formato="csv"):
    """El historial completo como evidencia fuera del sistema (CSV o JSON),
    con el resultado de la verificación de la cadena de eventos."""
    from .models import verificar_cadena

    puntos = linea_de_tiempo(record)
    intacta = all(verificar_cadena(i)[0] for i in record.instanciaciones.all())
    if formato == "json":
        datos = {
            "documento": {"id": record.pk, "nombre": record.nombre, "identificador": record.identificador},
            "cadena_de_eventos_integra": intacta,
            "eventos": [{
                "fecha": p["fecha"].isoformat(), "usuario": p["usuario"], "tipo": p["tipo"], "accion": p["titulo"],
                "exitoso": p["exitoso"], "archivo": p["archivo"],
                "hash_evento": p["evento"].hash_evento if p["evento"] else None,
                "hash_anterior": p["evento"].hash_anterior if p["evento"] else None,
                "cambios": p["cambios"], "datos": p["datos"],
            } for p in puntos],
        }
        return json.dumps(datos, ensure_ascii=False, indent=2), "application/json"
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(["documento", record.pk, record.nombre, "cadena íntegra" if intacta else "CADENA ALTERADA"])
    escritor.writerow(["fecha", "usuario", "acción", "archivo", "campo", "valor anterior", "valor nuevo", "otros datos", "hash del evento"])
    for p in puntos:
        otros = "; ".join(f"{d['campo']}: {d['valor']}" for d in p["datos"])
        hash_evento = p["evento"].hash_evento if p["evento"] else ""
        filas = p["cambios"] or [{"campo": "", "antes": "", "despues": ""}]
        for c in filas:
            escritor.writerow([p["fecha"].isoformat(), p["usuario"], p["titulo"], p["archivo"], c["campo"], c["antes"], c["despues"], otros, hash_evento])
    return "﻿" + salida.getvalue(), "text/csv; charset=utf-8"
