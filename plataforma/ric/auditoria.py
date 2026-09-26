"""Auditoría periódica por muestreo de las relaciones RiC ya aceptadas
(T071): mismo patrón que `asistencia.auditoria` (CLA-04/VAL-03) — cada
cierto tiempo se toma una muestra al azar de relaciones ya aceptadas o
modificadas, y una persona confirma si la propuesta de IA era correcta.

No es solo control de calidad: es también la única fuente real (sin
inventar un dataset) de M03 "Precisión de relaciones" en el laboratorio de
evaluación (`ric.metricas`) — se corre con el comando de gestión
`auditoria_muestra_ric`, porque es una tarea periódica de la entidad, no
una acción sobre un documento puntual.
"""

import random

from django.db import models, transaction
from django.utils import timezone

from .models import RelacionRiC


class MuestraRiC(models.Model):
    class Resultado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de revisión"
        CORRECTA = "correcta", "La IA acertó"
        INCORRECTA = "incorrecta", "La IA se equivocó"

    relacion = models.OneToOneField(RelacionRiC, on_delete=models.CASCADE, related_name="muestra_auditoria")
    fecha_seleccion = models.DateTimeField(auto_now_add=True)
    resultado = models.CharField(max_length=12, choices=Resultado.choices, default=Resultado.PENDIENTE)
    observacion = models.TextField(blank=True)
    revisado_por = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.PROTECT)
    fecha_revision = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "muestra de auditoría RiC"
        verbose_name_plural = "muestras de auditoría RiC"
        ordering = ["-fecha_seleccion"]

    def __str__(self):
        return f"Auditoría RiC · {self.relacion} · {self.get_resultado_display()}"

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


def seleccionar_muestra(tamano, relacion_id=None):
    """Elige al azar `tamano` relaciones RiC ya aceptadas/modificadas y sin
    auditar todavía; opcionalmente solo de un `relacion_id` (p. ej. "R027")."""
    candidatas = RelacionRiC.objects.filter(
        estado__in=(RelacionRiC.Estado.ACEPTADA, RelacionRiC.Estado.MODIFICADA)
    ).exclude(muestra_auditoria__isnull=False)
    if relacion_id:
        candidatas = candidatas.filter(relacion_id=relacion_id)
    candidatas = list(candidatas)
    elegidas = random.sample(candidatas, k=min(tamano, len(candidatas)))
    with transaction.atomic():
        creadas = [MuestraRiC.objects.create(relacion=r) for r in elegidas]
    return creadas


def reporte_exactitud():
    """M03 "Precisión de relaciones": porcentaje de aciertos entre las
    muestras ya revisadas."""
    revisadas = MuestraRiC.objects.exclude(resultado=MuestraRiC.Resultado.PENDIENTE)
    total = revisadas.count()
    if total == 0:
        return {"total_revisadas": 0, "correctas": 0, "exactitud": None}
    correctas = revisadas.filter(resultado=MuestraRiC.Resultado.CORRECTA).count()
    return {
        "total_revisadas": total,
        "correctas": correctas,
        "exactitud": round(100 * correctas / total, 1),
    }
