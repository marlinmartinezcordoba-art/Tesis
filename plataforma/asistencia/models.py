"""Sugerencias de IA sujetas a validación humana.

Principio rector: la IA propone y la persona archivista decide. Ninguna
sugerencia modifica el documento hasta que alguien la acepta o la corrige,
y ambas acciones quedan en la bitácora de preservación.
"""

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from acervo.models import (
    Documento,
    Entidad,
    EventoPreservacion,
    UnidadClasificacion,
    registrar_evento,
)
from lineamientos.models import Criterio, Proceso

# Campos del documento que una sugerencia puede completar.
CAMPOS_EDITABLES = {
    "codigo_referencia",
    "titulo",
    "fechas",
    "nivel_descripcion",
    "productor",
    "alcance_contenido",
}

# Sugerencias que, al aceptarse, vinculan una entidad al documento.
CAMPOS_ENTIDAD = {"persona", "lugar", "institucion"}

# Sugerencia cuyo valor es el código de una unidad ya existente del cuadro
# de clasificación. La IA nunca crea unidades nuevas, solo elige entre las
# que la entidad ya cargó.
CAMPO_CLASIFICACION = "clasificacion"


class SugerenciaIA(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de validación"
        ACEPTADA = "aceptada", "Aceptada"
        MODIFICADA = "modificada", "Aceptada con cambios"
        RECHAZADA = "rechazada", "Rechazada"

    documento = models.ForeignKey(
        Documento, on_delete=models.CASCADE, related_name="sugerencias"
    )
    proceso = models.CharField(max_length=20, choices=Proceso.choices)
    campo = models.CharField(max_length=50)
    valor_propuesto = models.TextField()
    justificacion = models.TextField(blank=True)
    evidencia = models.TextField(
        blank=True, help_text="Fragmento literal del documento que respalda la propuesta."
    )
    evidencia_verificada = models.BooleanField(
        null=True, help_text="Si MAZUCA encontró la evidencia en el texto del documento."
    )
    confianza = models.FloatField(help_text="Entre 0 y 1, según el proveedor de IA.")
    modelo = models.CharField(max_length=100)
    version_modelo = models.CharField(max_length=50)
    criterios = models.ManyToManyField(Criterio, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.PENDIENTE
    )
    valor_final = models.TextField(blank=True)
    motivo_decision = models.TextField(blank=True)
    validado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    fecha_validacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "sugerencia de IA"
        verbose_name_plural = "sugerencias de IA"

    def __str__(self):
        return f"{self.get_proceso_display()} · {self.campo} · {self.documento}"

    def validar(self, usuario, aceptar, valor_final=None, motivo=""):
        if self.estado != self.Estado.PENDIENTE:
            raise ValueError("La sugerencia ya fue validada.")
        if not usuario or not usuario.is_authenticated:
            raise PermissionError("Solo una persona autenticada puede validar.")
        if not aceptar and not motivo:
            raise ValueError("Indique el motivo del rechazo.")

        with transaction.atomic():
            if aceptar:
                valor = self.valor_propuesto if valor_final is None else valor_final
                self.estado = (
                    self.Estado.ACEPTADA
                    if valor == self.valor_propuesto
                    else self.Estado.MODIFICADA
                )
                self.valor_final = valor
                if self.campo in CAMPOS_EDITABLES:
                    anterior = getattr(self.documento, self.campo)
                    setattr(self.documento, self.campo, valor)
                    self.documento.save(update_fields=[self.campo])
                    registrar_evento(
                        self.documento,
                        EventoPreservacion.Tipo.MODIFICACION,
                        agente=usuario,
                        detalle={"campo": self.campo, "antes": anterior, "despues": valor},
                    )
                elif self.campo in CAMPOS_ENTIDAD:
                    entidad, _ = Entidad.objects.get_or_create(tipo=self.campo, nombre=valor)
                    entidad.documentos.add(self.documento)
                    registrar_evento(
                        self.documento,
                        EventoPreservacion.Tipo.MODIFICACION,
                        agente=usuario,
                        detalle={"entidad_vinculada": str(entidad)},
                    )
                elif self.campo == CAMPO_CLASIFICACION:
                    try:
                        unidad = UnidadClasificacion.objects.get(codigo=valor)
                    except UnidadClasificacion.DoesNotExist:
                        raise ValueError(
                            f"No existe la unidad «{valor}» en el cuadro de clasificación."
                        )
                    anterior = self.documento.unidad_clasificacion
                    self.documento.unidad_clasificacion = unidad
                    self.documento.save(update_fields=["unidad_clasificacion"])
                    registrar_evento(
                        self.documento,
                        EventoPreservacion.Tipo.MODIFICACION,
                        agente=usuario,
                        detalle={
                            "campo": self.campo,
                            "antes": str(anterior) if anterior else "",
                            "despues": str(unidad),
                        },
                    )
            else:
                self.estado = self.Estado.RECHAZADA

            self.motivo_decision = motivo
            self.validado_por = usuario
            self.fecha_validacion = timezone.now()
            self.save()
            registrar_evento(
                self.documento,
                EventoPreservacion.Tipo.VALIDACION,
                agente=usuario,
                detalle={
                    "sugerencia": self.pk,
                    "decision": self.estado,
                    "modelo": f"{self.modelo} {self.version_modelo}",
                    "motivo": motivo,
                },
            )
