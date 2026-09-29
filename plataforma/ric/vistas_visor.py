"""Módulo 1 · Visor documental (auditoría de arquitectura, pregunta 17): el
documento a la izquierda — PDF con pdf.js, imagen, TIFF convertido página a
página, o su texto — y a la derecha su contexto RiC navegable: expediente y
ruta de clasificación, serie de la TRD con la retención heredada, forma
documental, entidades relacionadas validadas por categoría, sus
instanciaciones con huella e integridad, y la evidencia de cada relación en
la página que se está viendo (pregunta 18: navegación contextual integrada).

Cada apertura queda en la auditoría (acción «consultar»)."""

import io
import json
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from . import clasificacion, flujo, grafo, reglas, valoracion
from .acceso_documentos import documentos_visibles, puede_ver_instanciacion, solo_publicados
from .auditoria_acciones import registrar_accion
from .models import Instantiation, Record

_PDF = {".pdf"}
_IMAGEN_NATIVA = {".jpg", ".jpeg", ".png"}
_IMAGEN_CONVERTIDA = {".tif", ".tiff", ".bmp"}
LADO_MAXIMO_VISTA = 2400  # píxeles: suficiente para leer, liviano para el navegador


def _tipo_vista(instanciacion):
    extension = Path(instanciacion.archivo.name).suffix.lower()
    if extension in _PDF:
        return "pdf"
    if extension in _IMAGEN_NATIVA:
        return "imagen"
    if extension in _IMAGEN_CONVERTIDA:
        return "imagen_convertida"
    return "texto"


def _contexto_rico(record):
    matriz = reglas.cargar_matriz()["relaciones"]
    grupos = {}
    evidencias = []
    for rel in flujo.relaciones_de(record):
        otro = flujo.otro_lado(rel, record)
        if otro is None:
            continue
        categoria = grafo.categoria_relacion(rel.relacion_id)
        grupos.setdefault(categoria, []).append({
            "relacion": rel, "nombre": matriz.get(rel.relacion_id, {}).get("nombre", rel.relacion_id),
            "otro": otro, "slug": type(otro).__name__.lower(), "tipo": type(otro)._meta.verbose_name,
        })
        if rel.evidencia and rel.evidencia.pagina:
            evidencias.append({
                "pagina": rel.evidencia.pagina, "fragmento": rel.evidencia.fragmento[:300],
                "relacion": f"{rel.relacion_id} {matriz.get(rel.relacion_id, {}).get('nombre', '')}", "entidad": str(otro),
            })
    orden = [c for c in grafo.CATEGORIAS if c in grupos]
    return [{"categoria": grafo.CATEGORIAS[c][0], "color": grafo.CATEGORIAS[c][1], "filas": grupos[c]} for c in orden], evidencias


def _marcos(instanciacion):
    from PIL import Image

    try:
        with instanciacion.archivo.open("rb") as f, Image.open(f) as imagen:
            return getattr(imagen, "n_frames", 1)
    except (OSError, ValueError):
        return 1


@login_required
def visor_documento(request, pk):
    record = get_object_or_404(Record, pk=pk)
    if solo_publicados(request.user) and not documentos_visibles(request.user).filter(pk=pk).exists():
        messages.error(request, "Este documento no está disponible para consulta (no publicado o de acceso restringido).")
        return redirect("catalogo")
    instanciaciones = list(record.instanciaciones.all())
    if not instanciaciones:
        messages.error(request, "El documento no tiene archivos cargados.")
        return redirect("catalogo_ficha", tipo="record", pk=pk)
    elegida = request.GET.get("inst", "")
    instanciacion = next((i for i in instanciaciones if str(i.pk) == elegida), None) or flujo.instanciacion_principal(record)
    if not puede_ver_instanciacion(request.user, instanciacion):
        return HttpResponseForbidden("Archivo de acceso restringido.")
    paginas = list(instanciacion.paginas.order_by("numero").values("numero", "texto", "confianza_ocr", "uso_ocr"))
    try:
        pagina = max(1, int(request.GET.get("pagina", "1")))
    except ValueError:
        pagina = 1
    tipo_vista = _tipo_vista(instanciacion)
    # Las páginas se cuentan en el propio archivo, no en el texto extraído:
    # un escaneo sin preprocesar también se hojea completo.
    total = len(paginas) or 1
    if tipo_vista == "imagen_convertida":
        total = max(total, _marcos(instanciacion))
    pagina = min(pagina, total) if paginas else pagina
    relaciones, evidencias = _contexto_rico(record)
    expediente = clasificacion.expediente_de(record)
    registrar_accion("consultar", objeto=record, detalle={"instanciacion": instanciacion.pk, "archivo": instanciacion.nombre, "pagina": pagina})
    return render(request, "ric/visor.html", {
        "record": record, "instanciacion": instanciacion, "instanciaciones": instanciaciones,
        "tipo_vista": tipo_vista, "pagina": pagina, "total_paginas": total,
        "paginas_json": json.dumps({p["numero"]: {"texto": p["texto"], "ocr": p["uso_ocr"], "confianza": p["confianza_ocr"]} for p in paginas}),
        "evidencias_json": json.dumps(evidencias),
        "texto_pagina": next((p["texto"] for p in paginas if p["numero"] == pagina), ""),
        "relaciones": relaciones, "evidencias": evidencias,
        "expediente": expediente, "ruta": expediente.ruta() if expediente is not None else [],
        "valoracion": valoracion.resumen(expediente) if expediente is not None and expediente.es_expediente else None,
        "estado": flujo.ETIQUETAS[flujo.estado_documento(record)],
        "puede_trabajar": not solo_publicados(request.user),
    })


@login_required
def archivo_original(request, pk):
    """El archivo original, solo con sesión y solo si el rol puede verlo
    (antes cualquier sesión podía descargar cualquier archivo por su id)."""
    instanciacion = get_object_or_404(Instantiation, pk=pk)
    if not puede_ver_instanciacion(request.user, instanciacion):
        registrar_accion("acceso_denegado", exitoso=False, detalle={"ruta": request.path, "instanciacion": pk})
        return HttpResponseForbidden("Archivo no disponible para su rol: el documento no está publicado o su acceso es restringido.")
    nombre = instanciacion.archivo.name.rsplit("/", 1)[-1]
    respuesta = FileResponse(instanciacion.archivo.open("rb"), filename=nombre, content_type=instanciacion.tipo_mime or None)
    respuesta["X-Content-Type-Options"] = "nosniff"
    respuesta["Cache-Control"] = "private, max-age=300"
    return respuesta


@login_required
def archivo_pagina_png(request, pk, numero):
    """TIFF y BMP no se ven en el navegador: se convierten a PNG página a
    página al vuelo, sin tocar el original ni guardar copias."""
    from PIL import Image, ImageSequence

    instanciacion = get_object_or_404(Instantiation, pk=pk)
    if not puede_ver_instanciacion(request.user, instanciacion):
        return HttpResponseForbidden("Archivo no disponible para su rol.")
    if _tipo_vista(instanciacion) not in ("imagen", "imagen_convertida"):
        raise Http404("Este archivo no es una imagen.")
    with instanciacion.archivo.open("rb") as f, Image.open(f) as imagen:
        marcos = list(ImageSequence.Iterator(imagen))
        if numero < 1 or numero > len(marcos):
            raise Http404("La imagen no tiene esa página.")
        marco = marcos[numero - 1].convert("RGB")
        marco.thumbnail((LADO_MAXIMO_VISTA, LADO_MAXIMO_VISTA))
        salida = io.BytesIO()
        marco.save(salida, format="PNG", optimize=True)
    respuesta = HttpResponse(salida.getvalue(), content_type="image/png")
    respuesta["Cache-Control"] = "private, max-age=300"
    return respuesta
