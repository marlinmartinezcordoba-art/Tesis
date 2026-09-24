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


VERIFICADORES = {
    "MET-01": _met_01,
    "MET-02": _met_02,
    "DES-01": _des_01,
    "DES-02": _decision_humana,
    "CLA-01": _decision_humana,
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
