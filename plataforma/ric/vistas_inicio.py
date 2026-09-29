"""Inicio de RICORA: la pantalla de trabajo de cada persona. Qué tiene
pendiente (con el botón que lleva a hacerlo), los últimos documentos con su
estado y el paso que sigue, y accesos directos según su rol."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from . import acceso_documentos, flujo, indicadores, roles, valoracion
from .models import Agent, ConfiguracionSistema, Instantiation, PropuestaRiC, SolicitudRestablecimiento

RECIENTES = 8

# Paso que sigue según el estado del documento: (texto del botón, cómo llegar).
_SIGUIENTE = {
    flujo.SIN_TEXTO: ("Preprocesar", lambda r: reverse("preproceso")),
    flujo.SIN_ANALIZAR: ("Analizar", lambda r: reverse("analisis", args=[r.pk])),
    flujo.EN_ANALISIS: ("Decidir", lambda r: reverse("analisis", args=[r.pk])),
    flujo.EN_REVISION: ("Revisar", lambda r: reverse("revision", args=[r.pk])),
    flujo.PUBLICADO: ("Ver ficha", lambda r: reverse("catalogo_ficha", args=["record", r.pk])),
}
_ESTADO_CORTO = {
    flujo.SIN_TEXTO: "Sin texto",
    flujo.SIN_ANALIZAR: "Por analizar",
    flujo.EN_ANALISIS: "En análisis",
    flujo.EN_REVISION: "En revisión",
    flujo.PUBLICADO: "Publicado",
}


def _saludo():
    hora = timezone.localtime().hour
    return "Buenos días" if hora < 12 else "Buenas tardes" if hora < 19 else "Buenas noches"


def _atencion(atrasados, listas, administra=False):
    """Alertas abiertas, las críticas primero: revisiones atrasadas, errores
    del OCR y expedientes con la retención cumplida."""
    alertas = []
    for f in atrasados:
        alertas.append({"nivel": "critica", "titulo": f"Revisión atrasada: {f['dias']} días esperando",
                        "sujeto": f["record"].nombre, "url": reverse("revision", args=[f["record"].pk])})
    for inst in Instantiation.objects.filter(estado_proceso=Instantiation.EstadoProceso.ERROR).order_by("-pk")[:5]:
        alertas.append({"nivel": "critica", "titulo": "El OCR falló en este archivo", "sujeto": inst.nombre, "url": reverse("preproceso")})
    for r in listas["disposicion"]:
        alertas.append({"nivel": "critica" if r["fase"] == valoracion.DISPOSICION else "alta",
                        "titulo": "Disposición final: retención en central cumplida" if r["fase"] == valoracion.DISPOSICION else f"Disposición final en {r['dias']} días",
                        "sujeto": r["expediente"].nombre, "url": reverse("valoracion_transferencias")})
    for r in listas["primaria"]:
        alertas.append({"nivel": "alta",
                        "titulo": "Transferencia primaria vencida" if r["fase"] == valoracion.CENTRAL else f"Transferencia primaria en {r['dias']} días",
                        "sujeto": r["expediente"].nombre, "url": reverse("valoracion_transferencias")})
    for s in SolicitudRestablecimiento.objects.filter(atendida=False, usuario__is_active=True).select_related("usuario")[:5] if administra else ():
        alertas.append({"nivel": "alta", "titulo": "Pidió restablecer su contraseña",
                        "sujeto": s.usuario.get_full_name() or s.usuario.username, "url": reverse("admin_usuarios")})
    for inst in Instantiation.objects.filter(estado_proceso=Instantiation.EstadoProceso.CALIDAD_BAJA).order_by("-pk")[:5]:
        alertas.append({"nivel": "alta", "titulo": "Texto del OCR de calidad baja", "sujeto": inst.nombre, "url": reverse("preproceso")})
    return alertas


@login_required
def inicio(request):
    usuario = request.user
    trabaja = roles.puede(usuario, roles.ARCHIVISTA, roles.REVISOR)
    ingesta = roles.puede(usuario, roles.ARCHIVISTA)
    visibles = acceso_documentos.documentos_visibles(usuario)

    tareas, alertas, cifras = [], [], []
    if trabaja:
        limite = ConfiguracionSistema.actual().dias_limite_revision
        atrasados = indicadores.atrasados(limite)
        listas = valoracion.transferencias()
        por_revisar = len(indicadores.esperando_revision())
        if ingesta:
            tareas.append({"n": Instantiation.objects.filter(estado_proceso=Instantiation.EstadoProceso.SIN_ENVIAR).count(),
                           "texto": "archivos sin enviar al OCR", "detalle": "Cargados, esperando el preprocesamiento",
                           "url": reverse("preproceso"), "icono": "ocr"})
            tareas.append({"n": PropuestaRiC.objects.filter(estado=PropuestaRiC.Estado.PENDIENTE).values("origen_object_id").distinct().count(),
                           "texto": "documentos con propuestas de la IA por decidir", "detalle": "Aceptar, corregir o rechazar cada propuesta",
                           "url": reverse("analisis_lista"), "icono": "ia"})
        tareas.append({"n": por_revisar, "texto": "documentos esperando revisión",
                       "detalle": f"{len(atrasados)} con más de {limite} días" if atrasados else "Ninguno atrasado",
                       "url": reverse("revision_lista") + "?filtro=pendientes", "icono": "revision"})
        tareas.append({"n": len(listas["primaria"]) + len(listas["disposicion"]), "texto": "expedientes con retención vencida o por vencer",
                       "detalle": f"{len(listas['primaria'])} a transferir · {len(listas['disposicion'])} a disposición final",
                       "url": reverse("valoracion_transferencias"), "icono": "retencion", "alerta": True})
        alertas = _atencion(atrasados, listas, administra=usuario.is_superuser)

    estados = {e: 0 for e in _ESTADO_CORTO}
    if trabaja:
        for record in visibles:
            estados[flujo.estado_documento(record)] += 1
    cifras.append({"n": visibles.count(), "texto": "documentos"})
    cifras.append({"n": visibles.filter(publicado=True).count(), "texto": "publicados", "clase": "ok"})
    if trabaja:
        cifras += [
            {"n": estados[flujo.SIN_TEXTO], "texto": "sin texto"},
            {"n": estados[flujo.SIN_ANALIZAR], "texto": "por analizar"},
            {"n": estados[flujo.EN_ANALISIS], "texto": "en análisis"},
            {"n": estados[flujo.EN_REVISION], "texto": "en revisión"},
            {"n": len(atrasados), "texto": "revisiones atrasadas", "clase": "peligro" if atrasados else ""},
            {"n": Agent.objects.count(), "texto": "personas e instituciones"},
        ]

    recientes = []
    base = visibles.order_by("-fecha_publicacion", "-fecha_registro") if not trabaja else visibles.order_by("-fecha_registro")
    for record in base[:RECIENTES]:
        estado = flujo.estado_documento(record)
        accion, url = _SIGUIENTE[estado]
        recientes.append({"record": record, "estado": estado, "estado_texto": _ESTADO_CORTO[estado],
                          "accion": accion, "url": url(record)})

    return render(request, "ric/inicio.html", {
        "saludo": _saludo(),
        "tareas": tareas,
        "alertas": alertas[:6],
        "alertas_total": len(alertas),
        "cifras": cifras,
        "recientes": recientes,
        "trabaja": trabaja,
        "ingesta": ingesta,
        "rol": roles.ETIQUETAS[roles.rol_de(usuario)],
    })
