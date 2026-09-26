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


class UnidadClasificacion(models.Model):
    """Entrada del cuadro de clasificación de la entidad (fondo, sección, serie o subserie).

    La entidad carga su propio cuadro; RICORA no impone uno. La IA solo
    propone entre las unidades ya existentes: nunca crea niveles nuevos.

    Corresponde a RiC-E03 Record Set: una agrupación jerárquica de
    documentos, con relaciones de inclusión entre sí (`padre`/`hijos`) y de
    procedencia hacia el Agente que la produjo (ver
    `RelacionEntidadUnidad` más abajo). Que un fondo tenga un productor no
    es una idea nueva de RiC-CM: es la propia definición legal de "fondo"
    en la Ley 594 de 2000, art. 3 — "totalidad de las series documentales
    de la misma procedencia".
    """

    class Tipo(models.TextChoices):
        FONDO = "fondo", "Fondo"
        SECCION = "seccion", "Sección"
        SERIE = "serie", "Serie"
        SUBSERIE = "subserie", "Subserie"

    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    padre = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="hijos"
    )
    descripcion = models.TextField(
        blank=True, help_text="Qué tipo de documentos agrupa; es lo que la IA compara contra el texto."
    )
    palabras_clave = models.CharField(
        max_length=500, blank=True,
        help_text="Términos separados por comas, usados por el proveedor de IA local para proponer coincidencias.",
    )

    class Meta:
        ordering = ["codigo"]
        verbose_name = "unidad del cuadro de clasificación"
        verbose_name_plural = "cuadro de clasificación"

    def __str__(self):
        return f"{self.codigo} · {self.nombre}"

    def ruta(self):
        """Fondo > sección > serie, para mostrar el contexto completo."""
        unidades, actual = [self], self.padre
        while actual:
            unidades.append(actual)
            actual = actual.padre
        return " > ".join(u.nombre for u in reversed(unidades))


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
    unidad_clasificacion = models.ForeignKey(
        UnidadClasificacion, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="documentos", help_text="Serie o subserie del cuadro de clasificación.",
    )

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
    """Agente, lugar o actividad, al estilo Records in Contexts (RiC-CM 1.0, ICA-EGAD, 2023).

    Corresponde a los tipos de entidad RiC-E07 Agent (con sus subtipos
    Person y Group/Corporate Body → persona, institucion), RiC-E22 Place
    (→ lugar) y RiC-E15 Activity (→ actividad).

    RiC-CM NO tiene un tipo de entidad "Concepto" o "Tema" separado: el
    "de qué trata" un documento se modela como una relación asociativa
    hacia una entidad que ya existe (ver TipoRelacion.TRATA_SOBRE más
    abajo), no como un tipo de entidad nuevo. Por eso este modelo no tiene
    un tipo "concepto".
    """

    class Tipo(models.TextChoices):
        PERSONA = "persona", "Persona"
        LUGAR = "lugar", "Lugar"
        INSTITUCION = "institucion", "Institución"
        ACTIVIDAD = "actividad", "Actividad"

    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    nombre = models.CharField(max_length=255)
    documentos = models.ManyToManyField(
        Documento, related_name="entidades", blank=True, through="RelacionEntidadDocumento"
    )

    class Meta:
        ordering = ["tipo", "nombre"]
        unique_together = ["tipo", "nombre"]
        verbose_name_plural = "entidades"

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"


class RelacionEntidadDocumento(models.Model):
    """El tipo de vínculo entre una entidad y un documento (DES-04).

    Sigue las categorías de relación de RiC-CM: PRODUCTOR es una relación
    de procedencia (≈ CreationRelation); MENCIONADO, DESTINATARIO,
    TRATA_SOBRE y LUGAR_PRODUCCION son relaciones asociativas (≈
    isOrWasSubjectOf); DOCUMENTA conecta el documento con la actividad que
    testimonia (≈ hasOrHadParticipant, de Activity a Agent, aplicada aquí
    en la dirección documento→actividad).

    Nota de alcance: estos nombres en español son una implementación
    práctica inspirada en las categorías de RiC-O, no una importación
    literal de las URIs de la ontología OWL. Para publicar datos en
    RDF/RiC-O habría que mapear cada uno al nombre exacto de propiedad de
    la ontología oficial (ica.org/standards/RiC), verificándolo contra el
    archivo fuente — no se hizo aquí porque ese sitio no fue accesible al
    construir este módulo.
    """

    class TipoRelacion(models.TextChoices):
        PRODUCTOR = "productor", "Productor"
        MENCIONADO = "mencionado", "Mencionado"
        DESTINATARIO = "destinatario", "Destinatario"
        DOCUMENTA = "documenta", "Documenta (actividad testimoniada)"
        TRATA_SOBRE = "trata_sobre", "Trata sobre"
        LUGAR_PRODUCCION = "lugar_produccion", "Lugar de producción"

    documento = models.ForeignKey(Documento, on_delete=models.CASCADE)
    entidad = models.ForeignKey(Entidad, on_delete=models.CASCADE)
    tipo_relacion = models.CharField(
        max_length=20, choices=TipoRelacion.choices, default=TipoRelacion.MENCIONADO
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["documento", "entidad", "tipo_relacion"]
        verbose_name = "relación entidad–documento"
        verbose_name_plural = "relaciones entidad–documento"

    def __str__(self):
        return f"{self.entidad} · {self.get_tipo_relacion_display()} de {self.documento}"


# Qué tipo de relación tiene sentido para cada tipo de entidad. Se usa para
# validar las propuestas de la IA antes de guardarlas (defensa en
# profundidad: no basta con que el modelo de lenguaje elija una combinación
# válida, RICORA la vuelve a comprobar).
RELACIONES_VALIDAS_POR_TIPO = {
    "persona": {"productor", "mencionado", "destinatario", "trata_sobre"},
    "institucion": {"productor", "mencionado", "destinatario", "trata_sobre"},
    "lugar": {"mencionado", "lugar_produccion", "trata_sobre"},
    "actividad": {"documenta", "trata_sobre"},
}


class RelacionEntidadUnidad(models.Model):
    """Relación de procedencia entre una unidad del cuadro (Record Set,
    RiC-E03) y el Agente que la produjo (CLA-02, principio de procedencia).

    Solo personas e instituciones pueden ser productoras de un fondo o una
    serie — un lugar o una actividad no "produce" documentos en el sentido
    archivístico, así que RELACIONES_VALIDAS_UNIDAD_POR_TIPO no los admite.
    """

    class TipoRelacion(models.TextChoices):
        PRODUCTOR = "productor", "Productor"

    unidad = models.ForeignKey(
        UnidadClasificacion, on_delete=models.CASCADE, related_name="relaciones_entidad"
    )
    entidad = models.ForeignKey(Entidad, on_delete=models.CASCADE)
    tipo_relacion = models.CharField(
        max_length=20, choices=TipoRelacion.choices, default=TipoRelacion.PRODUCTOR
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["unidad", "entidad", "tipo_relacion"]
        verbose_name = "relación entidad–unidad de clasificación"
        verbose_name_plural = "relaciones entidad–unidad de clasificación"

    def __str__(self):
        return f"{self.entidad} · {self.get_tipo_relacion_display()} de {self.unidad}"


RELACIONES_VALIDAS_UNIDAD_POR_TIPO = {
    "persona": {"productor"},
    "institucion": {"productor"},
}


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
        EXPORTACION = "exportacion_metadatos", "Exportación de metadatos"

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

