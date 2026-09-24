"""Operaciones del proceso de acceso."""

from acervo.models import EventoPreservacion, registrar_evento
from lineamientos.verificacion import CUMPLE, VERIFICADORES

from . import detector
from .models import RevisionDatosPersonales, hash_texto


def revisar_datos_personales(documento, agente="sistema"):
    """Ejecuta el detector y deja la revisión pendiente de decisión humana."""
    if not documento.texto_extraido:
        raise ValueError("Primero extraiga el texto del documento.")
    hallazgos = [h.como_dict() for h in detector.detectar(documento.texto_extraido)]
    revision = RevisionDatosPersonales.objects.create(
        documento=documento,
        detector_version=detector.VERSION,
        hash_texto=hash_texto(documento.texto_extraido),
        hallazgos=hallazgos,
    )
    registrar_evento(
        documento,
        EventoPreservacion.Tipo.REVISION_DATOS,
        agente=f"detector de datos personales {detector.VERSION}",
        detalle={
            "revision": revision.pk,
            "hallazgos": len(hallazgos),
            "sensibles": revision.total_sensibles,
        },
    )
    return revision


def requisitos_publicacion(documento):
    """Lista lo que le falta al documento para poder publicarse (vacía = listo)."""
    faltantes = []
    for codigo, nombre in [
        ("MET-01", "Integridad del archivo"),
        ("MET-02", "Bitácora íntegra"),
        ("DES-01", "Descripción ISAD(G) completa"),
    ]:
        estado, evidencia = VERIFICADORES[codigo](documento)
        if estado != CUMPLE:
            faltantes.append(f"{nombre}: {evidencia}")

    if documento.sugerencias.filter(estado="pendiente").exists():
        faltantes.append("Hay sugerencias de IA sin validación humana.")

    revision = documento.revisiones_datos.first()
    if revision is None:
        faltantes.append("Falta la revisión de datos personales.")
    elif not revision.vigente:
        faltantes.append("El texto cambió después de la revisión de datos personales.")
    elif revision.decision == RevisionDatosPersonales.Decision.PENDIENTE:
        faltantes.append("La revisión de datos personales no tiene decisión.")
    elif revision.decision == RevisionDatosPersonales.Decision.RESTRINGIDO:
        faltantes.append("El documento tiene acceso restringido.")
    return faltantes


def aprobar_publicacion(documento, usuario):
    if not usuario or not usuario.is_authenticated:
        raise PermissionError("Solo una persona autenticada puede aprobar la publicación.")
    faltantes = requisitos_publicacion(documento)
    if faltantes:
        return False, faltantes
    documento.publicado = True
    documento.save(update_fields=["publicado"])
    registrar_evento(
        documento,
        EventoPreservacion.Tipo.PUBLICACION,
        agente=usuario,
        detalle={"revision_datos": documento.revisiones_datos.first().pk},
    )
    return True, []
