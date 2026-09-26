"""Aplica los criterios de los lineamientos a un documento del acervo.

Algunos criterios se comprueban automáticamente con la evidencia que guarda
la plataforma (bitácora, hashes, sugerencias validadas). Los demás quedan
como "revisión manual" para que la persona archivista los evalúe.
"""

from dataclasses import dataclass

from acervo.models import EventoPreservacion, verificar_cadena

from .models import Criterio

CUMPLE = "cumple"
NO_CUMPLE = "no_cumple"
MANUAL = "revision_manual"


@dataclass
class Resultado:
    criterio: Criterio
    estado: str
    evidencia: str


def _met_01(doc):
    ingreso = doc.eventos.filter(tipo=EventoPreservacion.Tipo.INGRESO).exists()
    fallidas = doc.eventos.filter(tipo=EventoPreservacion.Tipo.FIJEZA, exitoso=False)
    if not ingreso:
        return NO_CUMPLE, "No hay evento de ingreso con hash."
    if fallidas.exists():
        return NO_CUMPLE, f"{fallidas.count()} verificación(es) de fijeza fallida(s)."
    return CUMPLE, f"SHA-256 {doc.sha256[:16]}… registrado al ingresar."


def _met_02(doc):
    ok, roto = verificar_cadena(doc)
    if ok:
        return CUMPLE, f"Bitácora íntegra ({doc.eventos.count()} eventos)."
    return NO_CUMPLE, f"La cadena se rompe en el evento {roto.pk}."


UMBRAL_OCR = 75


def _met_03(doc):
    extraccion = doc.eventos.filter(tipo=EventoPreservacion.Tipo.EXTRACCION).last()
    if not extraccion:
        return MANUAL, "Aún no se ha extraído el texto del documento."
    confianza = extraccion.detalle.get("confianza_ocr")
    if confianza is None:
        return CUMPLE, "Texto leído directamente del archivo, sin OCR."
    herramienta = extraccion.detalle.get("herramienta", "OCR")
    if confianza >= UMBRAL_OCR:
        return CUMPLE, f"{herramienta}: confianza media {confianza} %."
    return NO_CUMPLE, (
        f"{herramienta}: confianza media {confianza} %, por debajo de {UMBRAL_OCR} %. "
        "El texto requiere revisión humana."
    )


def _des_01(doc):
    campos = {
        "código de referencia": doc.codigo_referencia,
        "título": doc.titulo,
        "productor": doc.productor,
        "fechas": doc.fechas,
        "volumen y soporte": doc.volumen_soporte,
        "nivel de descripción": doc.nivel_descripcion,
    }
    faltan = [nombre for nombre, valor in campos.items() if not valor]
    if faltan:
        return NO_CUMPLE, "Faltan: " + ", ".join(faltan) + "."
    return CUMPLE, "Los seis elementos esenciales están diligenciados."


def _decision_humana(doc):
    pendientes = doc.sugerencias.filter(estado="pendiente").count()
    total = doc.sugerencias.count()
    if total == 0:
        return MANUAL, "Aún no hay sugerencias de IA para este documento."
    if pendientes:
        return NO_CUMPLE, f"{pendientes} de {total} sugerencias sin validación humana."
    return CUMPLE, f"Las {total} sugerencias tienen decisión humana registrada."


def _des_03(doc):
    aceptadas = doc.sugerencias.filter(estado="aceptada")
    if not doc.sugerencias.exists():
        return MANUAL, "Aún no hay sugerencias de IA para este documento."
    sin_evidencia = aceptadas.filter(evidencia_verificada=False).count()
    if sin_evidencia:
        return NO_CUMPLE, f"{sin_evidencia} dato(s) de IA aceptado(s) sin cambios y sin evidencia verificada."
    verificadas = doc.sugerencias.filter(evidencia_verificada=True).count()
    return CUMPLE, (
        f"{verificadas} de {doc.sugerencias.count()} sugerencias con evidencia verificada; "
        "ninguna sin evidencia se aceptó sin corrección."
    )


def _normalizar(texto):
    return " ".join(texto.strip().lower().split())


def _cla_02(doc):
    """Verifica el principio de procedencia comparando, en el grafo RiC, el
    productor del documento (Record) contra el productor declarado para la
    serie donde quedó clasificado (Record Set). Es la parte de CLA-02 que
    MAZUCA puede comprobar de forma automática; el resto (que la propuesta
    no mezcle niveles de un fondo distinto) sigue siendo revisión manual."""
    if not doc.unidad_clasificacion:
        return MANUAL, "El documento aún no está clasificado."

    relacion_unidad = doc.unidad_clasificacion.relaciones_entidad.filter(
        tipo_relacion="productor"
    ).first()
    if relacion_unidad is None:
        return MANUAL, (
            f"«{doc.unidad_clasificacion}» no tiene un productor declarado; "
            "no se puede verificar la procedencia automáticamente."
        )
    productor_unidad = relacion_unidad.entidad.nombre

    relacion_doc = doc.relacionentidaddocumento_set.filter(tipo_relacion="productor").first()
    productor_doc = relacion_doc.entidad.nombre if relacion_doc else doc.productor
    if not productor_doc:
        return MANUAL, (
            f"El documento no tiene productor identificado (ni en el grafo ni en la ficha); "
            f"la serie declara como productor a «{productor_unidad}»."
        )

    if _normalizar(productor_doc) == _normalizar(productor_unidad):
        return CUMPLE, f"El productor del documento coincide con el de la serie: «{productor_unidad}»."
    return NO_CUMPLE, (
        f"El productor del documento («{productor_doc}») no coincide con el productor "
        f"declarado para «{doc.unidad_clasificacion}» («{productor_unidad}»): posible mezcla "
        "de procedencias."
    )


def _cla_04(doc):
    from asistencia.auditoria import reporte_exactitud

    reporte = reporte_exactitud("clasificacion")
    if reporte["total_revisadas"] == 0:
        return MANUAL, (
            "Aún no hay muestras de auditoría de clasificación revisadas. "
            "Genérelas con el comando `auditoria_muestra`."
        )
    return CUMPLE, (
        f"{reporte['total_revisadas']} muestra(s) de auditoría de clasificación revisada(s), "
        f"exactitud {reporte['exactitud']} %."
    )


def _cla_03(doc):
    if doc.sugerencias.filter(proceso="clasificacion", estado="pendiente").exists():
        return NO_CUMPLE, "Hay una propuesta de clasificación de IA sin validar."
    if not doc.unidad_clasificacion:
        return MANUAL, "El documento aún no está clasificado."
    sugerencia = (
        doc.sugerencias.filter(proceso="clasificacion")
        .exclude(estado="pendiente")
        .order_by("-fecha_validacion")
        .first()
    )
    if sugerencia is None:
        return MANUAL, f"Clasificado en «{doc.unidad_clasificacion}», sin pasar por una sugerencia de IA."
    if sugerencia.estado != "rechazada" and sugerencia.evidencia_verificada is False:
        return NO_CUMPLE, "La clasificación vigente vino de una sugerencia sin evidencia verificada."
    return CUMPLE, (
        f"Clasificado en «{doc.unidad_clasificacion.ruta()}», "
        f"validado por {sugerencia.validado_por}."
    )


def _val_02(doc):
    sugerencias = doc.sugerencias.filter(proceso="valoracion")
    if not sugerencias.exists():
        return MANUAL, "Aún no se han generado indicios de valoración para este documento."
    if sugerencias.filter(estado="pendiente").exists():
        return MANUAL, "Hay indicios de valor propuestos por IA pendientes de validación."
    aceptados = sugerencias.filter(estado__in=["aceptada", "modificada"])
    if not aceptados.exists():
        return CUMPLE, "Los indicios propuestos fueron rechazados; no hay ningún indicio vigente."
    sin_evidencia = aceptados.filter(evidencia_verificada=False).count()
    if sin_evidencia:
        return NO_CUMPLE, f"{sin_evidencia} indicio(s) de valor aceptado(s) sin evidencia verificada."
    return CUMPLE, (
        f"{aceptados.count()} indicio(s) de valor secundario validado(s) por una persona archivista, "
        "todos con evidencia verificada; ninguno se usó para justificar una eliminación "
        "(la plataforma no ofrece esa función)."
    )


def _val_03(doc):
    from asistencia.auditoria import reporte_sesgo_valoracion

    reporte = reporte_sesgo_valoracion()
    revisados = {campo: r for campo, r in reporte.items() if r["total_revisadas"] > 0}
    if not revisados:
        return MANUAL, (
            "Aún no hay muestras de auditoría de valoración revisadas por tipo de indicio. "
            "Genérelas con el comando `auditoria_muestra`."
        )
    resumen = ", ".join(f"{campo}: {r['exactitud']} %" for campo, r in revisados.items())
    return CUMPLE, f"Exactitud desglosada por tipo de indicio ({resumen})."


def _des_04(doc):
    relaciones = doc.relacionentidaddocumento_set.select_related("entidad")
    if not relaciones.exists():
        return MANUAL, "El documento no tiene entidades vinculadas todavía."
    resumen = ", ".join(f"{r.entidad} ({r.get_tipo_relacion_display()})" for r in relaciones[:5])
    return CUMPLE, f"{relaciones.count()} relación(es) tipada(s): {resumen}."


def _met_04(doc):
    exportaciones = doc.eventos.filter(tipo=EventoPreservacion.Tipo.EXPORTACION)
    if not exportaciones.exists():
        return MANUAL, (
            "El documento aún no se ha exportado. Use los enlaces «Dublin Core» o «PREMIS» "
            "en la lista de documentos."
        )
    ultima = exportaciones.last()
    return CUMPLE, f"Exportado por última vez a {ultima.detalle.get('esquema', '—')} el {ultima.fecha:%Y-%m-%d}."


def _acc_01(doc):
    revision = doc.revisiones_datos.first()
    if revision is None:
        return MANUAL, "Aún no se han revisado los datos personales."
    if not revision.vigente:
        return NO_CUMPLE, "El texto cambió después de la última revisión de datos personales."
    if revision.decision == "pendiente":
        return NO_CUMPLE, f"{len(revision.hallazgos)} posible(s) dato(s) personal(es) sin decisión humana."
    return CUMPLE, (
        f"{revision.get_decision_display()} (decidido por {revision.decidido_por}); "
        f"{len(revision.hallazgos)} hallazgo(s) revisado(s)."
    )


def _acc_03(doc):
    from acceso.servicios import requisitos_publicacion

    faltantes = requisitos_publicacion(doc)
    if doc.publicado and not faltantes:
        return CUMPLE, "Publicado con todos los requisitos cumplidos."
    if doc.publicado:
        return NO_CUMPLE, "Publicado, pero ya no cumple: " + " ".join(faltantes)
    if faltantes:
        return MANUAL, "No publicado. Falta: " + " ".join(faltantes)
    return MANUAL, "No publicado; cumple los requisitos para aprobar su publicación."


def _acc_04(doc):
    """Las sugerencias que salieron de un proveedor en la nube (Claude, que
    envía el texto a un servicio externo) solo deben existir sobre documentos
    con la revisión de datos personales ya decidida y sin restricción de
    acceso; los proveedores locales (spaCy, palabras clave) no importan aquí
    porque no salen del equipo de la entidad."""
    nube = doc.sugerencias.filter(modelo="claude")
    if not nube.exists():
        return MANUAL, "El documento no tiene sugerencias generadas por un proveedor en la nube."

    revision = doc.revisiones_datos.first()
    if revision is None or not revision.vigente:
        return NO_CUMPLE, (
            f"{nube.count()} sugerencia(s) de un proveedor en la nube, pero el documento no "
            "tiene una revisión de datos personales vigente."
        )
    if revision.decision == "pendiente":
        return NO_CUMPLE, (
            f"{nube.count()} sugerencia(s) de un proveedor en la nube, pero la revisión de "
            "datos personales sigue sin decisión."
        )
    if revision.decision == "restringido":
        return NO_CUMPLE, (
            f"{nube.count()} sugerencia(s) de un proveedor en la nube sobre un documento de "
            "acceso restringido: el texto no debió salir de la entidad."
        )
    return CUMPLE, (
        f"{nube.count()} sugerencia(s) de un proveedor en la nube; revisión de datos "
        f"personales decidida ({revision.get_decision_display()}), documento no restringido."
    )


VERIFICADORES = {
    "MET-01": _met_01,
    "MET-02": _met_02,
    "MET-03": _met_03,
    "DES-01": _des_01,
    "DES-02": _decision_humana,
    "DES-03": _des_03,
    "DES-04": _des_04,
    "CLA-01": _decision_humana,
    "CLA-02": _cla_02,
    "CLA-03": _cla_03,
    "CLA-04": _cla_04,
    "VAL-01": lambda doc: (
        CUMPLE,
        "La plataforma no ofrece ninguna acción de eliminación ni de disposición documental; "
        "la IA solo puede señalar indicios de valor secundario.",
    ),
    "VAL-02": _val_02,
    "VAL-03": _val_03,
    "MET-04": _met_04,
    "ACC-01": _acc_01,
    "ACC-03": _acc_03,
    "ACC-04": _acc_04,
}


def evaluar_documento(documento):
    resultados = []
    for criterio in Criterio.objects.all():
        verificador = VERIFICADORES.get(criterio.codigo)
        if verificador:
            estado, evidencia = verificador(documento)
        else:
            estado, evidencia = MANUAL, criterio.verificacion
        resultados.append(Resultado(criterio, estado, evidencia))
    return resultados
