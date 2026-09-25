"""Auditoría periódica por muestreo de las sugerencias de IA (CLA-04, VAL-03).

No es un control por documento, sino organizacional: cada cierto tiempo, la
entidad toma una muestra de las sugerencias de clasificación o valoración
que ya fueron aceptadas, y una persona confirma si la IA acertó. Con eso se
puede medir la exactitud real y detectar sesgos (por ejemplo, si la IA
señala valor histórico casi siempre en documentos de una sola región).

Se corre con el comando de gestión `auditoria_muestra`, porque es una tarea
periódica de la entidad, no una acción sobre un documento puntual.
"""

import random

from django.db import models, transaction
from django.utils import timezone

from asistencia.models import SugerenciaIA


class MuestraAuditoria(models.Model):
    class Resultado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de revisión"
        CORRECTA = "correcta", "La IA acertó"
        INCORRECTA = "incorrecta", "La IA se equivocó"

    sugerencia = models.OneToOneField(SugerenciaIA, on_delete=models.CASCADE)
    fecha_seleccion = models.DateTimeField(auto_now_add=True)
    resultado = models.CharField(
        max_length=12, choices=Resultado.choices, default=Resultado.PENDIENTE
    )
    observacion = models.TextField(blank=True)
    revisado_por = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.PROTECT
    )
    fecha_revision = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "muestra de auditoría"
        verbose_name_plural = "muestras de auditoría"
        ordering = ["-fecha_seleccion"]

    def __str__(self):
        return f"Auditoría · {self.sugerencia} · {self.get_resultado_display()}"

    def validar_resultado(self, resultado, observacion):
        """Reglas de la revisión; lanza ValueError si no se cumplen. No depende
        del usuario, para poder validarse desde un formulario antes de guardar."""
        if self.resultado != self.Resultado.PENDIENTE:
            raise ValueError("Esta muestra ya fue revisada.")
        if resultado == self.Resultado.PENDIENTE or resultado not in self.Resultado.values:
            raise ValueError("Resultado no válido.")
        if resultado == self.Resultado.INCORRECTA and not observacion:
            raise ValueError("Explique en qué se equivocó la IA.")

    def revisar(self, usuario, resultado, observacion=""):
        if not usuario or not usuario.is_authenticated:
            raise PermissionError("Solo una persona autenticada puede revisar una muestra.")
        self.validar_resultado(resultado, observacion)
        self.resultado = resultado
        self.observacion = observacion
        self.revisado_por = usuario
        self.fecha_revision = timezone.now()
        self.save()


def seleccionar_muestra(proceso, tamano):
    """Elige al azar `tamano` sugerencias aceptadas de `proceso` sin auditar."""
    candidatas = list(
        SugerenciaIA.objects.filter(
            proceso=proceso, estado__in=["aceptada", "modificada"]
        ).exclude(muestraauditoria__isnull=False)
    )
    elegidas = random.sample(candidatas, k=min(tamano, len(candidatas)))
    with transaction.atomic():
        creadas = [MuestraAuditoria.objects.create(sugerencia=s) for s in elegidas]
    return creadas


def reporte_exactitud(proceso):
    """Porcentaje de aciertos entre las muestras ya revisadas de un proceso."""
    revisadas = MuestraAuditoria.objects.filter(
        sugerencia__proceso=proceso
    ).exclude(resultado=MuestraAuditoria.Resultado.PENDIENTE)
    total = revisadas.count()
    if total == 0:
        return {"total_revisadas": 0, "correctas": 0, "exactitud": None}
    correctas = revisadas.filter(resultado=MuestraAuditoria.Resultado.CORRECTA).count()
    return {
        "total_revisadas": total,
        "correctas": correctas,
        "exactitud": round(100 * correctas / total, 1),
    }


def reporte_sesgo_valoracion():
    """Para VAL-03: exactitud desglosada por tipo de valor (histórico, cultural,
    científico), para detectar si la IA acierta mucho más en un tipo que en otro."""
    reporte = {}
    for campo in ("valor_historico", "valor_cultural", "valor_cientifico"):
        revisadas = MuestraAuditoria.objects.filter(
            sugerencia__proceso="valoracion", sugerencia__campo=campo
        ).exclude(resultado=MuestraAuditoria.Resultado.PENDIENTE)
        total = revisadas.count()
        correctas = revisadas.filter(resultado=MuestraAuditoria.Resultado.CORRECTA).count()
        reporte[campo] = {
            "total_revisadas": total,
            "correctas": correctas,
            "exactitud": round(100 * correctas / total, 1) if total else None,
        }
    return reporte
