"""Laboratorio de evaluación (T070): M01-M14 tal como se definieron en
07_Metricas de la matriz maestra, calculadas de datos reales del sistema
— nunca simuladas.

Donde el sistema todavía no tiene lo que una métrica necesita (una verdad
fundamental curada a mano para M01/M02, un estudio de tiempos con personas
para M07-M09, texto de referencia para el OCR en M13, una encuesta de
usabilidad para M14), el valor es `None` con una nota que dice exactamente
qué falta, en vez de inventar un número. M03 sí se puede calcular con
datos reales: `ric.auditoria` (T071) audita por muestreo las relaciones ya
aceptadas, igual que CLA-04/VAL-03 en MAZUCA — mientras no haya muestras
revisadas todavía, M03 también queda en None.
"""

from . import auditoria
from .models import PropuestaRiC

_NOTA_SIN_DATASET = (
    "Requiere un dataset con verdad fundamental curada a mano (T003, entidades/relaciones "
    "esperadas por documento); no implementado en este ciclo."
)
_NOTA_SIN_MUESTRAS = (
    'Requiere muestras ya revisadas de auditoría RiC (comando "auditoria_muestra_ric"); '
    "todavía no hay ninguna."
)
_NOTA_SIN_TIEMPOS = (
    "Requiere instrumentar el tiempo real de revisión, con y sin asistencia de IA; "
    "no implementado en este ciclo."
)
_NOTA_SIN_REFERENCIA_OCR = "Requiere texto de referencia verificado por una persona para comparar contra el OCR; no implementado en este ciclo."
_NOTA_SIN_ENCUESTA = "Requiere un estudio de usabilidad con personas archivistas; no implementado en este ciclo."
_NOTA_SIN_ITERACIONES = 'Requiere marcar a qué "iteración" del aprendizaje asistido (T061) pertenece cada lote de propuestas; no implementado en este ciclo.'


def _tasa(numerador, denominador):
    return round(numerador / denominador, 4) if denominador else None


def _metrica(codigo, nombre, formula, valor, nota=None):
    if valor is None and nota is None:
        nota = "Sin datos suficientes todavía (denominador en cero)."
    return {"codigo": codigo, "nombre": nombre, "formula": formula, "valor": valor, "nota": nota}


def calcular_metricas():
    decididas = PropuestaRiC.objects.exclude(estado=PropuestaRiC.Estado.PENDIENTE)
    total_decididas = decididas.count()
    aceptadas = decididas.filter(estado=PropuestaRiC.Estado.ACEPTADA).count()
    modificadas = decididas.filter(estado=PropuestaRiC.Estado.MODIFICADA).count()
    rechazadas_total = decididas.filter(estado=PropuestaRiC.Estado.RECHAZADA).count()

    total_propuestas = PropuestaRiC.objects.count()
    con_evidencia = PropuestaRiC.objects.filter(evidencia__isnull=False).count()

    # M11: de las propuestas que de verdad pasaron por el motor de reglas
    # estructural (auto-rechazadas al generarse, o materializadas en una
    # RelacionRiC que superó la segunda validación al guardarse), cuántas
    # terminaron siendo una relación estructuralmente válida.
    rechazadas_por_regla = PropuestaRiC.objects.filter(
        estado=PropuestaRiC.Estado.RECHAZADA, validado_por__isnull=True
    ).count()
    materializadas = aceptadas + modificadas
    evaluadas_por_el_motor = materializadas + rechazadas_por_regla

    m03_auditoria = auditoria.reporte_exactitud()
    m03_valor = m03_auditoria["exactitud"] / 100 if m03_auditoria["exactitud"] is not None else None
    m03_nota = None if m03_valor is not None else _NOTA_SIN_MUESTRAS

    return [
        _metrica("M01", "Precisión de entidades", "TP/(TP+FP)", None, _NOTA_SIN_DATASET),
        _metrica("M02", "Recall de entidades", "TP/(TP+FN)", None, _NOTA_SIN_DATASET),
        _metrica("M03", "Precisión de relaciones", "TP/(TP+FP), por auditoría de muestreo (T071)", m03_valor, m03_nota),
        _metrica("M04", "Tasa de aprobación", "Aprobadas/Propuestas decididas", _tasa(aceptadas, total_decididas)),
        _metrica("M05", "Tasa de corrección", "Corregidas/Propuestas decididas", _tasa(modificadas, total_decididas)),
        _metrica("M06", "Tasa de rechazo", "Rechazadas/Propuestas decididas", _tasa(rechazadas_total, total_decididas)),
        _metrica("M07", "Tiempo manual", "Minutos/documento", None, _NOTA_SIN_TIEMPOS),
        _metrica("M08", "Tiempo asistido", "Minutos/documento", None, _NOTA_SIN_TIEMPOS),
        _metrica("M09", "Reducción de tiempo", "1 - asistido/manual", None, _NOTA_SIN_TIEMPOS),
        _metrica("M10", "Trazabilidad", "Propuestas con evidencia/total", _tasa(con_evidencia, total_propuestas)),
        _metrica(
            "M11", "Consistencia RiC", "Relaciones válidas/evaluadas por el motor de reglas",
            _tasa(materializadas, evaluadas_por_el_motor),
        ),
        _metrica("M12", "Mejora por iteración", "Métrica_n - Métrica_0", None, _NOTA_SIN_ITERACIONES),
        _metrica("M13", "Calidad de OCR", "Texto correcto/texto evaluado", None, _NOTA_SIN_REFERENCIA_OCR),
        _metrica("M14", "Usabilidad", "Escala definida en estudio", None, _NOTA_SIN_ENCUESTA),
    ]
