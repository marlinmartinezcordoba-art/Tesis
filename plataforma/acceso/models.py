"""Proceso de acceso: revisión de datos personales y aprobación para publicar.

Un documento solo se aprueba para el portal de consulta cuando una persona
archivista revisó sus datos personales y decidió cómo darlo a conocer.
"""

import hashlib

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from acervo.models import Documento, EventoPreservacion, registrar_evento

from . import detector


def hash_texto(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class RevisionDatosPersonales(models.Model):
    class Decision(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de decisión"
        PUBLICABLE = "publicable", "Publicable sin cambios"
        ANONIMIZAR = "anonimizar", "Publicable con datos ocultos"
        RESTRINGIDO = "restringido", "Acceso restringido"

    documento = models.ForeignKey(
        Documento, on_delete=models.CASCADE, related_name="revisiones_datos"
    )
    fecha = models.DateTimeField(auto_now_add=True)
    detector_version = models.CharField(max_length=20)
    hash_texto = models.CharField(
        max_length=64, help_text="Huella del texto revisado; si el texto cambia, hay que revisar de nuevo."
    )
    hallazgos = models.JSONField(default=list)

    decision = models.CharField(
        max_length=12, choices=Decision.choices, default=Decision.PENDIENTE
    )
    motivo = models.TextField(blank=True)
    decidido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    fecha_decision = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "revisión de datos personales"
        verbose_name_plural = "revisiones de datos personales"

    def __str__(self):
        return f"{self.documento} · {self.get_decision_display()}"

    @property
    def total_sensibles(self):
        return sum(h["sensible"] for h in self.hallazgos)

    @property
    def vigente(self):
        return self.hash_texto == hash_texto(self.documento.texto_extraido)

    def validar_decision(self, decision, motivo):
        """Reglas de la decisión humana; lanza ValueError si no se cumplen."""
        if self.decision != self.Decision.PENDIENTE:
            raise ValueError("Esta revisión ya tiene una decisión.")
        if decision == self.Decision.PENDIENTE or decision not in self.Decision.values:
            raise ValueError("Decisión no válida.")
        if not self.vigente:
            raise ValueError("El texto cambió después de la revisión. Revise de nuevo.")
        if decision != self.Decision.PUBLICABLE and not motivo:
            raise ValueError("Indique el motivo de la decisión.")
        if decision == self.Decision.PUBLICABLE and self.hallazgos and not motivo:
            raise ValueError("Hay posibles datos personales: justifique por qué se publica sin cambios.")

    def decidir(self, usuario, decision, motivo=""):
        if not usuario or not usuario.is_authenticated:
            raise PermissionError("Solo una persona autenticada puede decidir.")
        self.validar_decision(decision, motivo)

        doc = self.documento
        with transaction.atomic():
            self.decision = decision
            self.motivo = motivo
            self.decidido_por = usuario
            self.fecha_decision = timezone.now()
            self.save()
            if decision == self.Decision.PUBLICABLE:
                doc.texto_publico = doc.texto_extraido
            elif decision == self.Decision.ANONIMIZAR:
                doc.texto_publico = detector.anonimizar(doc.texto_extraido, self.hallazgos)
            else:
                doc.texto_publico = ""
                doc.publicado = False
            doc.save(update_fields=["texto_publico", "publicado"])
            registrar_evento(
                doc,
                EventoPreservacion.Tipo.REVISION_DATOS,
                agente=usuario,
                detalle={"revision": self.pk, "decision": decision, "motivo": motivo},
            )
