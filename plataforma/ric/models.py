"""Motor RiC: entidades y relaciones alineadas con RiC-CM 1.0 / RiC-O 1.1.

Este es el núcleo RiC-native que reemplaza gradualmente al modelo plano de
`acervo` (Documento/UnidadClasificacion/Entidad). Cada entidad y cada
relación aquí se verificó campo por campo contra las fuentes primarias
(RiC-CM-1.0.pdf y RiC-O_1-1.rdf); el resultado de esa verificación vive en
`ric/fixtures/ric_matrix.json` y es lo que usa `ric.reglas` para validar
que una `RelacionRiC` respete el dominio/rango oficial.

Jerarquías de tipos reales (herencia multitabla de Django), no un solo
campo `tipo`: así una FK a `RecordResource` acepta indistintamente un
Record Set, un Record o un Record Part, igual que en RiC-CM.
"""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Thing(models.Model):
    """RiC-E01 Thing. Mixin abstracto: atributos comunes a toda entidad RiC.

    No se instancia sola (RiC-CM tampoco la instancia directamente salvo
    para representar cosas fuera del alcance del modelo).
    """

    identificador = models.CharField(
        max_length=255, blank=True,
        help_text="RiC-A22 Identifier: identifica la entidad dentro de un dominio dado.",
    )
    nombre = models.CharField(max_length=500, help_text="RiC-A28 Name.")
    descripcion_general = models.TextField(blank=True, help_text="RiC-A43 General Description.")
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.nombre or self.identificador or f"{self.__class__.__name__} #{self.pk}"


# ---------------------------------------------------------------------------
# Record Resource: RiC-E02, con Record Set / Record / Record Part (RiC-E03-05)
# ---------------------------------------------------------------------------

class RecordResource(Thing):
    """RiC-E02 Record Resource. Concreta (herencia multitabla): así una
    Instantiation o una RelacionRiC pueden apuntar a "un Record Resource"
    sin importar si es Record Set, Record o Record Part."""

    autenticidad = models.TextField(blank=True, help_text="RiC-A03 Authenticity Note.")
    clasificacion = models.CharField(max_length=255, blank=True, help_text="RiC-A07 Classification.")
    condiciones_acceso = models.TextField(blank=True, help_text="RiC-A08 Conditions of Access.")
    condiciones_uso = models.TextField(blank=True, help_text="RiC-A09 Conditions of Use.")
    tipo_contenido = models.CharField(
        max_length=255, blank=True,
        help_text="RiC-A10 Content Type (simplificado a texto libre; RiC-O lo trata como clase controlada).",
    )
    historia = models.TextField(blank=True, help_text="RiC-A21 History.")
    nota_integridad = models.TextField(blank=True, help_text="RiC-A24 Integrity Note.")
    idioma = models.CharField(max_length=255, blank=True, help_text="RiC-A25 Language.")
    estatus_legal = models.CharField(max_length=255, blank=True, help_text="RiC-A26 Legal Status.")
    extension = models.CharField(max_length=255, blank=True, help_text="RiC-A35 Record Resource Extent.")
    alcance_y_contenido = models.TextField(blank=True, help_text="RiC-A38 Scope and content.")
    estado_produccion = models.CharField(
        max_length=50, blank=True,
        help_text="RiC-A39 State (RiC-O: 'Record State'). Solo aplica a Record/Record Part.",
    )
    estructura = models.TextField(blank=True, help_text="RiC-A40 Structure.")

    class Meta:
        verbose_name = "recurso documental"
        verbose_name_plural = "recursos documentales"


class RecordSet(RecordResource):
    """RiC-E03 Record Set: agrupación de uno o más Records (fondo, sección, serie, subserie)."""

    accruals = models.CharField(max_length=255, blank=True, help_text="RiC-A01 Accruals.")
    tipo_conjunto = models.CharField(
        max_length=50, blank=True,
        help_text="RiC-A36 Record Set Type: fondo, sección, serie, subserie, colección...",
    )
    padre = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="hijos",
        help_text="Caso común de RiC-R024 'includes or included' entre Record Sets; el caso general se "
                   "modela con RelacionRiC.",
    )

    class Meta:
        verbose_name = "conjunto de registros (Record Set)"
        verbose_name_plural = "conjuntos de registros (Record Set)"

    def productor(self):
        """Agente ligado por RiC-R026/R027 (procedencia). Ver ric.reglas."""
        return (
            RelacionRiC.objects.filter(
                relacion_id__in=("R026", "R027"),
                origen_content_type=ContentType.objects.get_for_model(self),
                origen_object_id=self.pk,
            )
            .select_related()
            .first()
        )


class Record(RecordResource):
    """RiC-E04 Record: contenido informacional discreto, formado al menos una vez."""

    tipo_forma_documental = models.CharField(max_length=255, blank=True, help_text="RiC-A17 Documentary Form Type.")
    record_set = models.ForeignKey(
        RecordSet, null=True, blank=True, on_delete=models.SET_NULL, related_name="records",
        help_text="Caso común de RiC-R024 'includes or included'; el caso general se modela con RelacionRiC.",
    )

    class Meta:
        verbose_name = "registro (Record)"
        verbose_name_plural = "registros (Record)"


class RecordPart(RecordResource):
    """RiC-E05 Record Part: componente de un Record con contenido informacional propio."""

    tipo_forma_documental = models.CharField(max_length=255, blank=True, help_text="RiC-A17 Documentary Form Type.")
    record_padre = models.ForeignKey(
        Record, on_delete=models.CASCADE, related_name="partes",
        help_text="RiC-R003 'has or had constituent' (caso Record -> Record Part).",
    )

    class Meta:
        verbose_name = "parte de registro (Record Part)"
        verbose_name_plural = "partes de registro (Record Part)"


class Instantiation(Thing):
    """RiC-E06 Instantiation: la inscripción física/digital de un Record Resource."""

    record_resource = models.ForeignKey(
        RecordResource, on_delete=models.CASCADE, related_name="instanciaciones",
        help_text="RiC-R025 'has or had instantiation'.",
    )
    archivo = models.FileField(upload_to="ric/instanciaciones/%Y/%m/")
    sha256 = models.CharField(
        max_length=64, editable=False,
        help_text="No es un atributo de RiC-CM: extensión de preservación digital (RiC-CM 1.0, sección 1.9).",
    )
    tipo_soporte = models.CharField(max_length=255, blank=True, help_text="RiC-A05 Carrier Type.")
    extension_soporte = models.CharField(max_length=255, blank=True, help_text="RiC-A04 Carrier Extent.")
    tipo_representacion = models.CharField(max_length=255, blank=True, help_text="RiC-A37 Representation Type.")
    caracteristicas_fisicas = models.TextField(blank=True, help_text="RiC-A31 Physical Characteristics Note.")

    class Meta:
        verbose_name = "instanciación (Instantiation)"
        verbose_name_plural = "instanciaciones (Instantiation)"

    def calcular_y_guardar_hash(self):
        import hashlib

        h = hashlib.sha256()
        self.archivo.seek(0)
        for bloque in iter(lambda: self.archivo.read(65536), b""):
            h.update(bloque)
        self.archivo.seek(0)
        self.sha256 = h.hexdigest()

    @property
    def texto_extraido(self):
        """Todas las páginas unidas; para buscar evidencia con su página exacta,
        recorrer `self.paginas` en vez de esto."""
        return "\n\n".join(p.texto for p in self.paginas.all())


class PaginaTexto(models.Model):
    """Texto extraído de una página de una Instantiation, con su confianza de
    OCR si aplica. Permite que la Evidencia de una propuesta señale la
    página exacta, no solo "en algún lugar del documento"."""

    instanciacion = models.ForeignKey(Instantiation, on_delete=models.CASCADE, related_name="paginas")
    numero = models.PositiveIntegerField()
    texto = models.TextField(blank=True)
    uso_ocr = models.BooleanField(default=False)
    confianza_ocr = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["numero"]
        unique_together = ["instanciacion", "numero"]
        verbose_name = "página de texto"
        verbose_name_plural = "páginas de texto"

    def __str__(self):
        return f"{self.instanciacion} · p.{self.numero}"


# ---------------------------------------------------------------------------
# Agent: RiC-E07, con Person/Group/Family/CorporateBody/Position/Mechanism
# ---------------------------------------------------------------------------

class Agent(Thing):
    """RiC-E07 Agent: entidad que actúa en el mundo."""

    historia = models.TextField(blank=True, help_text="RiC-A21 History.")
    idioma = models.CharField(max_length=255, blank=True, help_text="RiC-A25 Language.")
    estatus_legal = models.CharField(max_length=255, blank=True, help_text="RiC-A26 Legal Status.")

    class Meta:
        verbose_name = "agente"
        verbose_name_plural = "agentes"


class Person(Agent):
    """RiC-E08 Person: un ser humano individual."""

    tipo_ocupacion = models.CharField(max_length=255, blank=True, help_text="RiC-A30 Occupation Type.")

    class Meta:
        verbose_name = "persona"
        verbose_name_plural = "personas"


class Group(Agent):
    """RiC-E09 Group: dos o más agentes que actúan juntos como un agente."""

    grupo_demografico = models.CharField(max_length=255, blank=True, help_text="RiC-A15 Demographic Group.")

    class Meta:
        verbose_name = "grupo"
        verbose_name_plural = "grupos"


class Family(Group):
    """RiC-E10 Family: personas relacionadas por parentesco, matrimonio u otra convención social."""

    tipo_familia = models.CharField(max_length=255, blank=True, help_text="RiC-A20 Family Type.")

    class Meta:
        verbose_name = "familia"
        verbose_name_plural = "familias"


class CorporateBody(Group):
    """RiC-E11 Corporate Body: grupo organizado con estatus legal o social reconocido."""

    tipo_entidad_corporativa = models.CharField(max_length=255, blank=True, help_text="RiC-A12 Corporate Body Type.")

    class Meta:
        verbose_name = "entidad corporativa"
        verbose_name_plural = "entidades corporativas"


class Position(Agent):
    """RiC-E12 Position: el rol funcional de una Person dentro de un Group."""

    class Meta:
        verbose_name = "posición (cargo)"
        verbose_name_plural = "posiciones (cargos)"


class Mechanism(Agent):
    """RiC-E13 Mechanism: proceso o sistema (software, robot) que realiza una actividad."""

    caracteristicas_tecnicas = models.TextField(blank=True, help_text="RiC-A41 Technical Characteristics.")

    class Meta:
        verbose_name = "mecanismo"
        verbose_name_plural = "mecanismos"


# ---------------------------------------------------------------------------
# Event: RiC-E14, con Activity (RiC-E15)
# ---------------------------------------------------------------------------

class Event(Thing):
    """RiC-E14 Event: algo que sucede u ocurre en el tiempo y el espacio."""

    tipo_evento = models.CharField(max_length=255, blank=True, help_text="RiC-A18 Event Type.")
    historia = models.TextField(blank=True, help_text="RiC-A21 History.")

    class Meta:
        verbose_name = "evento"
        verbose_name_plural = "eventos"


class Activity(Event):
    """RiC-E15 Activity: evento diseñado y realizado por un agente con un propósito."""

    tipo_actividad = models.CharField(max_length=255, blank=True, help_text="RiC-A02 Activity Type.")

    class Meta:
        verbose_name = "actividad"
        verbose_name_plural = "actividades"


# ---------------------------------------------------------------------------
# Rule: RiC-E16, con Mandate (RiC-E17)
# ---------------------------------------------------------------------------

class Rule(Thing):
    """RiC-E16 Rule: condiciones que gobiernan la existencia/autoridad de un agente o actividad."""

    tipo_regla = models.CharField(max_length=255, blank=True, help_text="RiC-A45 Rule Type.")
    historia = models.TextField(blank=True, help_text="RiC-A21 History.")

    class Meta:
        verbose_name = "regla"
        verbose_name_plural = "reglas"


class Mandate(Rule):
    """RiC-E17 Mandate: delegación explícita de responsabilidad o autoridad."""

    tipo_mandato = models.CharField(max_length=255, blank=True, help_text="RiC-A44 Mandate Type.")

    class Meta:
        verbose_name = "mandato"
        verbose_name_plural = "mandatos"


# ---------------------------------------------------------------------------
# Date (RiC-E18) y Place (RiC-E22): sin subtipos
# ---------------------------------------------------------------------------

class Date(Thing):
    """RiC-E18 Date: información cronológica asociada a una entidad."""

    expresion = models.CharField(max_length=255, blank=True, help_text="RiC-A19 Expressed Date.")
    valor_normalizado = models.CharField(
        max_length=100, blank=True, help_text="RiC-A29 Normalized Date (ISO 8601 / EDTF)."
    )
    calificador = models.CharField(
        max_length=50, blank=True,
        help_text="RiC-A13 Date Qualifier. La certeza de la fecha frente a OTRA entidad va en la "
                   "RelacionRiC que las conecta (RiC-RA01), no aquí.",
    )
    tipo_fecha = models.CharField(max_length=100, blank=True, help_text="RiC-A42 Date Type.")

    class Meta:
        verbose_name = "fecha"
        verbose_name_plural = "fechas"


class Place(Thing):
    """RiC-E22 Place: área geográfica delimitada y nombrada."""

    coordenadas = models.CharField(max_length=255, blank=True, help_text="RiC-A11 Coordinates (ISO 6709).")
    ubicacion = models.CharField(max_length=500, blank=True, help_text="RiC-A27 Location.")
    tipo_lugar = models.CharField(max_length=255, blank=True, help_text="RiC-A32 Place Type.")
    historia = models.TextField(blank=True, help_text="RiC-A21 History.")

    class Meta:
        verbose_name = "lugar"
        verbose_name_plural = "lugares"


# ---------------------------------------------------------------------------
# Evidencia, propuesta de IA y relaciones (no son entidades RiC; son el
# mecanismo propio de MAZUCA que hace cumplir "la IA propone, la persona
# decide" sobre el grafo RiC de arriba)
# ---------------------------------------------------------------------------

class Evidencia(models.Model):
    """Fragmento verificable de una Instantiation que respalda una propuesta de IA.

    No es un concepto de RiC-CM: es el mecanismo de trazabilidad propio de
    la plataforma (sección 7 de los lineamientos del sistema).
    """

    instanciacion = models.ForeignKey(Instantiation, on_delete=models.CASCADE, related_name="evidencias")
    pagina = models.PositiveIntegerField(null=True, blank=True)
    fragmento = models.TextField(help_text="Texto literal citado como evidencia.")
    posicion = models.JSONField(
        null=True, blank=True, help_text="Coordenadas (bbox) cuando el proveedor de IA las entrega."
    )
    verificada = models.BooleanField(
        null=True, help_text="Si el fragmento se encontró literalmente en el texto extraído de la instanciación."
    )

    class Meta:
        verbose_name = "evidencia"
        verbose_name_plural = "evidencias"

    def __str__(self):
        return f"Evidencia p.{self.pagina or '?'}: {self.fragmento[:60]}"


class RelacionRiC(models.Model):
    """Una afirmación de relación entre dos entidades del grafo RiC.

    `relacion_id` es uno de los 85 identificadores verificados de
    `ric/fixtures/ric_matrix.json` (R001-R086, salvo R043, que no existe
    en RiC-CM 1.0). El dominio/rango se valida contra esa misma fuente en
    `ric.reglas.validar_relacion` antes de guardar — ver también
    `RelacionRiC.clean()`.
    """

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de validación"
        ACEPTADA = "aceptada", "Aceptada"
        MODIFICADA = "modificada", "Aceptada con cambios"
        RECHAZADA = "rechazada", "Rechazada"

    class Certeza(models.TextChoices):
        CIERTA = "certain", "Cierta"
        INCIERTA = "uncertain", "Incierta"
        DESCONOCIDA = "unknown", "Desconocida"

    relacion_id = models.CharField(max_length=10, help_text="Ej. 'R026'. Ver ric/fixtures/ric_matrix.json.")

    origen_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="+")
    origen_object_id = models.PositiveBigIntegerField()
    origen = GenericForeignKey("origen_content_type", "origen_object_id")

    destino_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="+")
    destino_object_id = models.PositiveBigIntegerField()
    destino = GenericForeignKey("destino_content_type", "destino_object_id")

    certeza = models.CharField(max_length=12, choices=Certeza.choices, blank=True, help_text="RiC-RA01.")
    descripcion_relacion = models.TextField(blank=True, help_text="RiC-RA03 Description of Relation.")
    fuente_relacion = models.TextField(blank=True, help_text="RiC-RA05 Source of Relation.")

    evidencia = models.ForeignKey(
        Evidencia, null=True, blank=True, on_delete=models.SET_NULL, related_name="relaciones",
        help_text="Nula si la relación se creó a mano por el archivista, sin propuesta de IA de por medio.",
    )
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    validado_por = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.PROTECT, related_name="relaciones_validadas"
    )
    fecha_validacion = models.DateTimeField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "relación RiC"
        verbose_name_plural = "relaciones RiC"

    def __str__(self):
        return f"{self.origen} --{self.relacion_id}--> {self.destino}"

    def clean(self):
        from django.core.exceptions import ValidationError

        from . import reglas

        try:
            reglas.validar_relacion(self.relacion_id, self.origen, self.destino)
        except reglas.RelacionInvalida as e:
            raise ValidationError(str(e)) from e

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
