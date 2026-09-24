"""Acervo documental: documentos y su historia de preservación.

La integridad se protege en dos niveles:
- cada documento guarda el SHA-256 calculado al ingresar;
- cada evento de preservación (al estilo PREMIS) se encadena con el anterior
  mediante un hash, de modo que alterar o borrar un evento rompe la cadena.
"""

import hashlib
import json

from django.db import models, transaction


def calcular_sha256(archivo):
    h = hashlib.sha256()
    archivo.seek(0)
    for bloque in iter(lambda: archivo.read(65536), b""):
        h.update(bloque)
    archivo.seek(0)
    return h.hexdigest()


class Documento(models.Model):
    class Nivel(models.TextChoices):
        FONDO = "fondo", "Fondo"
        SECCION = "seccion", "Sección"
        SERIE = "serie", "Serie"
        UNIDAD = "unidad", "Unidad documental"

    # Elementos obligatorios de ISAD(G) 3.1.1–3.1.5 y 3.2.1
    codigo_referencia = models.CharField(max_length=100, blank=True)
    titulo = models.CharField(max_length=500)
    fechas = models.CharField(max_length=100, blank=True)
    nivel_descripcion = models.CharField(
        max_length=10, choices=Nivel.choices, default=Nivel.UNIDAD
    )
    volumen_soporte = models.CharField(max_length=255, blank=True)
    productor = models.CharField(max_length=255, blank=True)
    alcance_contenido = models.TextField(blank=True)

    archivo = models.FileField(upload_to="acervo/%Y/%m/")
    sha256 = models.CharField(max_length=64, editable=False)
    formato = models.CharField(max_length=100, blank=True, editable=False)
    tamano_bytes = models.BigIntegerField(default=0, editable=False)
    texto_extraido = models.TextField(blank=True)
    texto_publico = models.TextField(
        blank=True, editable=False,
        help_text="Texto que se muestra al público, con los datos personales ocultos si se decidió anonimizar.",
    )
    publicado = models.BooleanField(default=False, editable=False)
    fecha_ingreso = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        nuevo = self._state.adding
        if nuevo:
            self.sha256 = calcular_sha256(self.archivo)
            self.tamano_bytes = self.archivo.size
            self.formato = getattr(self.archivo.file, "content_type", "") or ""
        super().save(*args, **kwargs)
        if nuevo:
            registrar_evento(
                self,
                EventoPreservacion.Tipo.INGRESO,
                agente="sistema",
                detalle={"sha256": self.sha256, "tamano_bytes": self.tamano_bytes},
            )

    def verificar_fijeza(self, agente="sistema"):
        """Recalcula el hash y registra el resultado como evento PREMIS."""
        with self.archivo.open("rb") as f:
            actual = calcular_sha256(f)
        ok = actual == self.sha256
        registrar_evento(
            self,
            EventoPreservacion.Tipo.FIJEZA,
            agente=agente,
            detalle={"esperado": self.sha256, "obtenido": actual},
            exitoso=ok,
        )
        return ok


class Entidad(models.Model):
    """Persona, lugar o institución validada; base de los índices y de Records in Contexts."""

    class Tipo(models.TextChoices):
        PERSONA = "persona", "Persona"
        LUGAR = "lugar", "Lugar"
        INSTITUCION = "institucion", "Institución"

    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    nombre = models.CharField(max_length=255)
    documentos = models.ManyToManyField(Documento, related_name="entidades", blank=True)

    class Meta:
        ordering = ["tipo", "nombre"]
        unique_together = ["tipo", "nombre"]
        verbose_name_plural = "entidades"

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"


class EventoPreservacion(models.Model):
    class Tipo(models.TextChoices):
        INGRESO = "ingreso", "Ingreso"
        FIJEZA = "verificacion_fijeza", "Verificación de fijeza"
        EXTRACCION = "extraccion_texto", "Extracción de texto (OCR)"
        SUGERENCIA_IA = "sugerencia_ia", "Sugerencia generada por IA"
        VALIDACION = "validacion_humana", "Validación humana"
        MODIFICACION = "modificacion_metadatos", "Modificación de metadatos"
        REVISION_DATOS = "revision_datos_personales", "Revisión de datos personales"
        PUBLICACION = "aprobacion_publicacion", "Aprobación de publicación"

    documento = models.ForeignKey(
        Documento, on_delete=models.PROTECT, related_name="eventos"
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    fecha = models.DateTimeField(auto_now_add=True)
    agente = models.CharField(max_length=255)
    detalle = models.JSONField(default=dict)
    exitoso = models.BooleanField(default=True)
    hash_anterior = models.CharField(max_length=64, editable=False)
    hash_evento = models.CharField(max_length=64, editable=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.documento}"

    def calcular_hash(self):
        contenido = json.dumps(
            {
                "documento": self.documento_id,
                "tipo": self.tipo,
                "agente": self.agente,
                "detalle": self.detalle,
                "exitoso": self.exitoso,
                "hash_anterior": self.hash_anterior,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


GENESIS = "0" * 64


def registrar_evento(documento, tipo, agente, detalle=None, exitoso=True):
    agente = getattr(agente, "get_username", lambda: str(agente))()
    with transaction.atomic():
        ultimo = (
            EventoPreservacion.objects.select_for_update()
            .filter(documento=documento)
            .order_by("-id")
            .first()
        )
        evento = EventoPreservacion(
            documento=documento,
            tipo=tipo,
            agente=agente,
            detalle=detalle or {},
            exitoso=exitoso,
            hash_anterior=ultimo.hash_evento if ultimo else GENESIS,
        )
        evento.hash_evento = evento.calcular_hash()
        evento.save()
    return evento


def verificar_cadena(documento):
    """Devuelve (True, None) si la bitácora está intacta o (False, evento_roto)."""
    anterior = GENESIS
    for evento in documento.eventos.order_by("id"):
        if evento.hash_anterior != anterior or evento.calcular_hash() != evento.hash_evento:
            return False, evento
        anterior = evento.hash_evento
    return True, None

