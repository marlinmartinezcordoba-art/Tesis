"""Lineamientos técnicos de la tesis convertidos en reglas verificables.

Cada criterio pertenece a un proceso archivístico y protege un atributo del
patrimonio documental (autenticidad, integridad o accesibilidad). Siempre
declara su fuente normativa para que el informe pueda citarla.
"""

from django.db import models


class Proceso(models.TextChoices):
    CLASIFICACION = "clasificacion", "Clasificación"
    DESCRIPCION = "descripcion", "Descripción"
    VALORACION = "valoracion", "Valoración"
    METADATOS = "metadatos", "Gestión de metadatos"
    ACCESO = "acceso", "Acceso"


class Atributo(models.TextChoices):
    AUTENTICIDAD = "autenticidad", "Autenticidad"
    INTEGRIDAD = "integridad", "Integridad"
    ACCESIBILIDAD = "accesibilidad", "Accesibilidad"


class Criterio(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador (pendiente de Fase 4)"
        VALIDADO = "validado", "Validado en la tesis"

    codigo = models.CharField(max_length=20, unique=True)
    proceso = models.CharField(max_length=20, choices=Proceso.choices)
    atributo = models.CharField(max_length=20, choices=Atributo.choices)
    enunciado = models.TextField(help_text="Lo que debe cumplir la solución de IA.")
    verificacion = models.TextField(
        help_text="Cómo comprueba la entidad que el criterio se cumple."
    )
    fuente_normativa = models.CharField(max_length=255)
    obligatorio = models.BooleanField(default=True)
    riesgo_asociado = models.CharField(
        max_length=255, blank=True, help_text="Sesgo, pérdida de contexto, trazabilidad…"
    )
    estado = models.CharField(
        max_length=10, choices=Estado.choices, default=Estado.BORRADOR
    )

    class Meta:
        ordering = ["proceso", "codigo"]

    def __str__(self):
        return f"{self.codigo} · {self.enunciado[:60]}"
