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

import datetime
import hashlib
import json

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction


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
    creado_por = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="RF-M5-04: quién creó esta entrada (vacío si la creó el sistema).",
    )
    modificado_por = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="RF-M5-04: quién hizo la última modificación.",
    )
    serie_trd = models.CharField(
        max_length=255, blank=True,
        help_text="RF-M5-03: serie o subserie de la Tabla de Retención Documental vigente con la que se vincula esta entrada de autoridad.",
    )

    class Meta:
        abstract = True

    def __str__(self):
        return self.nombre or self.identificador or f"{self.__class__.__name__} #{self.pk}"

    def save(self, *args, **kwargs):
        # F07 (versionado, RF-016): antes de sobrescribir una entidad que
        # ya existía, guarda cómo estaba — nunca en la creación, ahí no
        # hay nada previo que versionar. Todo en una transacción: si el
        # guardado falla después, no debe quedar una versión huérfana de
        # un cambio que en realidad nunca se aplicó.
        with transaction.atomic():
            if self.pk:
                anterior = type(self).objects.filter(pk=self.pk).first()
                if anterior is not None:
                    _registrar_version(anterior)
            super().save(*args, **kwargs)


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
    # M6 (RF-M6-04) / M8: un documento solo queda visible en el catálogo
    # para consulta cuando la revisión archivística lo aprobó y publicó.
    publicado = models.BooleanField(default=False)
    fecha_publicacion = models.DateTimeField(null=True, blank=True)
    publicado_por = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

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


class FormaDocumental(models.Model):
    """M5 (vocabularios): forma documental controlada — oficio, acta,
    resolución, contrato... En RiC-O 1.1 es la clase
    `rico:DocumentaryFormType`, a la que un Record apunta mediante
    `rico:hasDocumentaryFormType` (RiC-A17, verificado en ric_matrix.json).
    Cada entrada se vincula con la serie/subserie de la TRD (RF-M5-03).

    Es un catálogo de tipos reutilizable: "Oficio" o "Acta de reunión"
    aparecen en decenas de series distintas, cada una con su propio plazo
    de retención y su propia disposición final. Por eso esos datos NO
    viven aquí sino en el Mandato de cada serie (corrección de la
    especificación v3); las series en las que aparece una forma se llegan
    por `actividades` (Activity.formas_documentales)."""

    nombre = models.CharField(max_length=255, unique=True)
    definicion = models.TextField(blank=True)
    serie_trd = models.CharField(
        max_length=255, blank=True,
        help_text="Serie o subserie de la Tabla de Retención Documental a la que corresponde este tipo.",
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    modificado_por = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["nombre"]
        verbose_name = "forma documental"
        verbose_name_plural = "formas documentales"

    def __str__(self):
        return self.nombre

    def series(self):
        """Las series/subseries de la TRD (Actividad + su Mandato) en las que
        esta forma documental aparece como tipo documental."""
        return self.actividades.select_related("mandato").order_by("nombre")


class Record(RecordResource):
    """RiC-E04 Record: contenido informacional discreto, formado al menos una vez."""

    tipo_forma_documental = models.CharField(max_length=255, blank=True, help_text="RiC-A17 Documentary Form Type.")
    forma_documental = models.ForeignKey(
        FormaDocumental, null=True, blank=True, on_delete=models.SET_NULL, related_name="records",
        help_text="RiC-A17 como entrada controlada del vocabulario de formas documentales (M5).",
    )
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
    class CondicionAcceso(models.TextChoices):
        ABIERTO = "abierto", "Abierto"
        RESTRINGIDO = "restringido", "Restringido"
        RESERVADO = "reservado", "Reservado"

    class TipoCopia(models.TextChoices):
        MASTER = "master_preservacion", "Máster de preservación"
        ACCESO = "copia_acceso", "Copia de acceso"

    condicion_acceso = models.CharField(
        max_length=12, choices=CondicionAcceso.choices, default=CondicionAcceso.ABIERTO,
        help_text="Clasificación de acceso a la información (Ley 1712 de 2014); la decide el equipo archivístico. "
        "RF-M8-04: el rol consulta solo ve documentos con todas sus instanciaciones abiertas.",
    )
    tipo_copia = models.CharField(max_length=20, choices=TipoCopia.choices, default=TipoCopia.ACCESO)
    nota_autenticidad = models.TextField(
        blank=True,
        help_text="Mecanismos de verificación además de la huella SHA-256: firma digital, sello de tiempo, cadena de custodia.",
    )
    instanciacion_origen = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="derivadas",
        help_text="La instanciación de la que esta se deriva por migración o conversión de formato (RiC-R015: una "
        "copia de preservación PDF/A generada desde el TIFF original), nunca una sustitución silenciosa del original.",
    )
    formato = models.CharField(max_length=20, blank=True, help_text="RF-M1-03: extensión detectada al cargar (pdf, docx, png...).")
    tamano_bytes = models.BigIntegerField(null=True, blank=True, help_text="RF-M1-03: tamaño del archivo al cargar.")
    idioma_detectado = models.CharField(max_length=8, blank=True, help_text="RF-M2-03: código del idioma detectado en el texto extraído.")

    class Meta:
        verbose_name = "ingesta de un documento (M1/M2) — Instantiation"
        verbose_name_plural = "ingesta de documentos (M1/M2) — Instantiation"

    def calcular_y_guardar_hash(self):
        import hashlib

        h = hashlib.sha256()
        self.archivo.seek(0)
        for bloque in iter(lambda: self.archivo.read(65536), b""):
            h.update(bloque)
        self.archivo.seek(0)
        self.sha256 = h.hexdigest()

    def save(self, *args, **kwargs):
        # F01: el hash se calcula una sola vez, sobre el archivo tal como
        # se ingirió — nunca se recalcula después, para que sea el hash del
        # original inmutable y no de una posible edición posterior del campo.
        if self.archivo and not self.sha256:
            self.calcular_y_guardar_hash()
        if self.archivo and not self.formato:
            self.formato = self.archivo.name.rsplit(".", 1)[-1].lower() if "." in self.archivo.name else ""
        if self.archivo and self.tamano_bytes is None:
            try:
                self.tamano_bytes = self.archivo.size
            except (OSError, ValueError):
                self.tamano_bytes = None
        super().save(*args, **kwargs)

    def paginas_calidad_baja(self):
        """RF-M2-04: páginas con OCR por debajo del umbral configurado y sin
        decisión de la persona todavía ("aceptar igual" o "reescanear")."""
        umbral = ConfiguracionSistema.actual().umbral_calidad_ocr
        return self.paginas.filter(uso_ocr=True, confianza_ocr__lt=umbral, calidad_aceptada__isnull=True)

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
    cajas_ocr = models.JSONField(
        null=True, blank=True,
        help_text="F02: caja delimitadora de cada palabra reconocida por OCR "
        "(izquierda/arriba/ancho/alto en píxeles, más su confianza). Vacío "
        "cuando la página no tuvo OCR (texto plano o capa de texto de PDF).",
    )
    calidad_aceptada = models.BooleanField(
        null=True, blank=True,
        help_text="RF-M2-04: decisión sobre una página de calidad baja — True 'aceptar igual', False 'reescanear', vacío sin decidir.",
    )

    class Meta:
        ordering = ["numero"]
        unique_together = ["instanciacion", "numero"]
        verbose_name = "página de texto"
        verbose_name_plural = "páginas de texto"

    def __str__(self):
        return f"{self.instanciacion} · p.{self.numero}"


class ComponenteEstructural(models.Model):
    """F03 (Comprensión documental): un componente de la estructura del
    documento (encabezado, título, campo tipo PARA/DE/ASUNTO, fecha,
    sección, artículo, párrafo, firma o tabla) detectado automáticamente
    sobre el texto ya extraído (F02).

    No es una entidad de RiC-CM: es una señal de comprensión documental que
    alimenta la segmentación (F04) y las propuestas de entidades/relaciones
    (F05) — es heurística basada en reglas, no un modelo de IA, por eso
    cada componente guarda qué regla lo detectó (trazabilidad, sección 7
    de los lineamientos del sistema)."""

    class Tipo(models.TextChoices):
        ENCABEZADO = "encabezado", "Encabezado institucional"
        TITULO = "titulo", "Título / identificador del documento"
        CAMPO = "campo", "Campo (PARA/DE/ASUNTO/FECHA/LUGAR...)"
        FECHA = "fecha", "Fecha"
        SECCION = "seccion", "Encabezado de sección"
        ARTICULO = "articulo", "Artículo"
        PARRAFO = "parrafo", "Párrafo"
        FIRMA = "firma", "Firma"
        TABLA = "tabla", "Tabla"

    instanciacion = models.ForeignKey(Instantiation, on_delete=models.CASCADE, related_name="componentes")
    pagina = models.PositiveIntegerField()
    orden = models.PositiveIntegerField(help_text="Posición del componente dentro de la página, en orden de lectura.")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    etiqueta = models.CharField(max_length=50, blank=True, help_text="Para tipo=campo: PARA, DE, ASUNTO...; para tipo=articulo: 'ARTÍCULO 1'.")
    texto = models.TextField(blank=True)
    datos = models.JSONField(null=True, blank=True, help_text="Para tipo=tabla: filas/columnas; para tipo=fecha: el texto de la fecha reconocida.")
    confianza = models.FloatField(help_text="Heurística basada en reglas: más alta cuanto más específica la regla, más baja si es por descarte.")
    regla = models.CharField(max_length=50, help_text="Nombre de la regla que detectó este componente.")

    class Meta:
        ordering = ["pagina", "orden"]
        verbose_name = "componente estructural (F03)"
        verbose_name_plural = "componentes estructurales (F03)"

    def __str__(self):
        return f"{self.instanciacion} p.{self.pagina} · {self.get_tipo_display()}: {self.texto[:40]}"


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
    """RiC-E15 Activity: evento diseñado y realizado por un agente con un
    propósito. Cada serie o subserie de la TRD se registra como una
    Actividad (función) vinculada a su Mandato (especificación v3)."""

    tipo_actividad = models.CharField(max_length=255, blank=True, help_text="RiC-A02 Activity Type.")
    mandato = models.ForeignKey(
        "Mandate", null=True, blank=True, on_delete=models.SET_NULL, related_name="actividades",
        help_text="La serie/subserie de la TRD que regula esta función (caso común de RiC-R063 'regulates or regulated').",
    )
    formas_documentales = models.ManyToManyField(
        FormaDocumental, blank=True, related_name="actividades",
        help_text="Tipos documentales que produce esta serie según la TRD (RF-M5-03).",
    )

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
    """RiC-E17 Mandate: delegación explícita de responsabilidad o autoridad.

    Es también la entidad que representa cada serie o subserie de la Tabla
    de Retención Documental (especificación v3): aquí, y no en la forma
    documental, van los tiempos de retención y la disposición final, porque
    varían serie por serie. Las cuatro casillas de disposición son las de la
    TRD colombiana (CT, E, MT, S) y pueden combinarse (p. ej. CT + MT)."""

    tipo_mandato = models.CharField(max_length=255, blank=True, help_text="RiC-A44 Mandate Type.")
    codigo_serie = models.CharField(max_length=20, blank=True, help_text="Código de la serie en la TRD.")
    codigo_subserie = models.CharField(max_length=20, blank=True, help_text="Código de la subserie en la TRD, si aplica.")
    tiempo_retencion_archivo_gestion = models.PositiveIntegerField(null=True, blank=True, help_text="Años en archivo de gestión, según la TRD.")
    tiempo_retencion_archivo_central = models.PositiveIntegerField(null=True, blank=True, help_text="Años en archivo central, según la TRD.")
    conservacion_total = models.BooleanField(default=False, help_text="Disposición final CT.")
    eliminacion = models.BooleanField(default=False, help_text="Disposición final E.")
    medio_tecnologico = models.BooleanField(default=False, help_text="Disposición final MT (medio tecnológico / digitalización).")
    seleccion = models.BooleanField(default=False, help_text="Disposición final S.")
    soporte = models.CharField(max_length=100, blank=True, help_text="Soporte según la TRD: papel, electrónico...")
    procedimiento = models.TextField(blank=True, help_text="Columna 'Procedimiento' de la TRD: qué se hace al vencer la retención.")
    vigencia = models.DateField(null=True, blank=True, help_text="Fecha de vigencia/aprobación de la TRD de la que sale esta serie.")

    DISPOSICIONES = (
        ("conservacion_total", "CT", "Conservación total"),
        ("eliminacion", "E", "Eliminación"),
        ("medio_tecnologico", "MT", "Medio tecnológico"),
        ("seleccion", "S", "Selección"),
    )

    class Meta:
        verbose_name = "mandato"
        verbose_name_plural = "mandatos"

    def disposicion_final_codigos(self):
        return [codigo for campo, codigo, _ in self.DISPOSICIONES if getattr(self, campo)]

    def disposicion_final_texto(self):
        return " + ".join(nombre for campo, _, nombre in self.DISPOSICIONES if getattr(self, campo))

    @property
    def es_serie_trd(self):
        return bool(self.codigo_serie or self.tiempo_retencion_archivo_gestion is not None or self.disposicion_final_codigos())

    def retencion_texto(self):
        """Resumen legible para fichas y revisión: 'gestión 3 años · central 7 años · Selección'."""
        if not self.es_serie_trd:
            return ""
        partes = []
        if self.tiempo_retencion_archivo_gestion is not None:
            partes.append(f"gestión {self.tiempo_retencion_archivo_gestion} años")
        if self.tiempo_retencion_archivo_central is not None:
            partes.append(f"central {self.tiempo_retencion_archivo_central} años")
        partes.append(self.disposicion_final_texto() or "sin disposición")
        return " · ".join(partes)


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
# mecanismo propio de RICORA que hace cumplir "la IA propone, la persona
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
        null=True, blank=True,
        help_text="F02: caja delimitadora (bbox) del fragmento sobre la página OCR, "
        "calculada automáticamente cuando la página tiene coordenadas de OCR "
        "(ver ric.evidencia.localizar_posicion); vacía si la página no tuvo OCR.",
    )
    verificada = models.BooleanField(
        null=True, help_text="Si el fragmento se encontró literalmente en el texto extraído de la instanciación."
    )

    class Meta:
        verbose_name = "evidencia"
        verbose_name_plural = "evidencias"

    def __str__(self):
        return f"Evidencia p.{self.pagina or '?'}: {self.fragmento[:60]}"


class VersionRiC(models.Model):
    """F07 (versionado, RF-016): fotografía de cómo estaba una entidad o
    relación justo antes de sobrescribirla. Nunca se crea al crear la
    entidad — solo cuando una ya existente se guarda con cambios — así que
    el historial completo de una entidad son sus N versiones más el estado
    actual del propio registro.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="+")
    object_id = models.PositiveBigIntegerField()
    objeto = GenericForeignKey("content_type", "object_id")

    datos_anteriores = models.JSONField(help_text="Campos propios (sin relaciones) tal como estaban antes de este cambio.")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "versión (historial RiC)"
        verbose_name_plural = "versiones (historial RiC)"

    def __str__(self):
        return f"{self.content_type.model} #{self.object_id} · {self.fecha:%Y-%m-%d %H:%M}"


def _valor_serializable(valor):
    if isinstance(valor, (datetime.date, datetime.datetime)):
        return valor.isoformat()
    if isinstance(valor, (str, int, float, bool, type(None))):
        return valor
    return str(valor)


def _registrar_version(instancia):
    """Guarda en `VersionRiC` una fotografía JSON de los campos propios
    (concretos, sin relaciones) de `instancia` — sirve igual para una
    entidad `Thing` con herencia multitabla (sus campos heredados están en
    `_meta.fields`) que para una `RelacionRiC`, que no hereda de `Thing`."""
    datos = {
        campo.name: _valor_serializable(getattr(instancia, campo.name))
        for campo in instancia._meta.fields
        if not campo.is_relation
    }
    VersionRiC.objects.create(
        content_type=ContentType.objects.get_for_model(type(instancia)),
        object_id=instancia.pk,
        datos_anteriores=datos,
    )


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
    motivo_decision = models.TextField(
        blank=True, help_text="M4/M6: por qué se retiró o rechazó esta relación (queda en el historial).",
    )
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

    @property
    def origen_decision(self):
        """CC-08: de dónde salió la relación — de una propuesta del motor
        (tiene evidencia) o de una corrección manual del archivista."""
        return "propuesta_ia" if self.evidencia_id else "correccion_manual"

    def clean(self):
        from django.core.exceptions import ValidationError

        from . import reglas

        try:
            reglas.validar_relacion(self.relacion_id, self.origen, self.destino)
        except reglas.RelacionInvalida as e:
            raise ValidationError(str(e)) from e

    def save(self, *args, **kwargs):
        anterior = RelacionRiC.objects.filter(pk=self.pk).first() if self.pk else None
        self.full_clean()
        with transaction.atomic():
            if anterior is not None:
                _registrar_version(anterior)
            super().save(*args, **kwargs)


class PropuestaRiC(models.Model):
    """Una propuesta de IA sobre el grafo RiC: 'este Record se relaciona con
    esta entidad (nueva o existente) mediante esta relación'.

    La IA nunca escribe RelacionRiC ni entidades directamente — solo crea
    filas aquí. `validar()` es el único camino para que una propuesta se
    convierta en grafo real, y solo lo hace una persona autenticada.
    """

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de validación"
        ACEPTADA = "aceptada", "Aceptada"
        MODIFICADA = "modificada", "Aceptada con cambios"
        RECHAZADA = "rechazada", "Rechazada"

    origen_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="+")
    origen_object_id = models.PositiveBigIntegerField()
    origen = GenericForeignKey("origen_content_type", "origen_object_id")

    relacion_id = models.CharField(max_length=10, help_text="Ej. 'R027'.")
    entidad_tipo = models.CharField(max_length=10, help_text="Ej. 'E11'. Tipo de la entidad destino propuesta.")
    entidad_nombre = models.CharField(max_length=500)

    proveedor = models.CharField(max_length=50, help_text="Nombre del ProveedorIA que la generó.")
    version_modelo = models.CharField(max_length=100, blank=True)
    confianza = models.FloatField(help_text="Entre 0 y 1.")
    justificacion = models.TextField(blank=True)
    evidencia = models.ForeignKey(Evidencia, null=True, blank=True, on_delete=models.SET_NULL, related_name="propuestas")
    datos_extra = models.JSONField(
        default=dict, blank=True,
        help_text="Lo que el motor propuso además del nombre: rol del agente en el documento, fecha "
        "normalizada y precisión, tipo de norma, tipo de lugar y código DANE, entrada de vocabulario sugerida.",
    )

    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    motivo_decision = models.TextField(
        blank=True,
        help_text="Por qué se rechazó: del motor de reglas (automático) o de la persona archivista.",
    )
    validado_por = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.PROTECT, related_name="propuestas_ric_validadas"
    )
    fecha_validacion = models.DateTimeField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "propuesta de IA (RiC)"
        verbose_name_plural = "propuestas de IA (RiC)"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"{self.relacion_id} · {self.entidad_tipo} {self.entidad_nombre} ({self.estado})"

    def _aplicar_datos_extra(self, entidad):
        """Lo que el motor propuso por clase (sección 12 de la especificación)
        llevado a los atributos RiC-CM reales de la entidad nueva: fecha
        expresada/normalizada/calificador (CC-07), tipo de lugar y DANE,
        tipo de mandato o regla, tipo de actividad."""
        extra = self.datos_extra or {}
        campos = entidad._meta.fields
        nombres = {c.name for c in campos}
        if "expresion" in nombres:  # Date (E18)
            entidad.expresion = extra.get("fecha_texto_original", "") or entidad.expresion
            entidad.valor_normalizado = extra.get("fecha_normalizada", "") or entidad.valor_normalizado
            entidad.calificador = extra.get("precision_fecha", "") or entidad.calificador
            entidad.tipo_fecha = extra.get("tipo_fecha", "") or entidad.tipo_fecha
        if "tipo_lugar" in nombres:  # Place (E22)
            entidad.tipo_lugar = extra.get("tipo_lugar", "") or entidad.tipo_lugar
            if extra.get("codigo_dane") and not entidad.identificador:
                entidad.identificador = f"DANE:{extra['codigo_dane']}"
        if "tipo_mandato" in nombres and extra.get("tipo_norma"):  # Mandate (E17)
            entidad.tipo_mandato = extra["tipo_norma"]
        elif "tipo_regla" in nombres and extra.get("tipo_norma"):  # Rule (E16)
            entidad.tipo_regla = extra["tipo_norma"]
        if "tipo_actividad" in nombres and extra.get("tipo_funcion"):  # Activity (E15)
            entidad.tipo_actividad = extra["tipo_funcion"].replace("_", " ")

    def validar(self, usuario, aceptar, entidad_nombre_final=None, entidad_existente=None, motivo=""):
        """`entidad_existente`: una instancia ya guardada del modelo que
        corresponde a `self.entidad_tipo`, para VINCULAR la propuesta a una
        entidad que el archivista sabe que ya existe (evita duplicados que
        una simple coincidencia de nombre no detectaría). Si no se da, se
        usa `entidad_nombre_final` (o el nombre propuesto) con
        `get_or_create` por nombre, como antes."""
        from django.utils import timezone

        from . import tipos

        if self.estado != self.Estado.PENDIENTE:
            raise ValueError("Esta propuesta ya fue validada.")
        if not usuario or not usuario.is_authenticated:
            raise PermissionError("Solo una persona autenticada puede validar.")
        if not aceptar and not motivo:
            raise ValueError("Indique el motivo del rechazo.")

        with transaction.atomic():
            if aceptar:
                modelo = tipos.ric_id_a_modelo(self.entidad_tipo)
                if modelo is None:
                    raise ValueError(f"Tipo de entidad desconocido: {self.entidad_tipo!r}")

                if entidad_existente is not None:
                    if not isinstance(entidad_existente, modelo):
                        raise ValueError(
                            f"La entidad elegida no es de tipo {modelo.__name__} "
                            f"({self.entidad_tipo}: {type(entidad_existente).__name__})."
                        )
                    entidad = entidad_existente
                    nombre_final = entidad.nombre
                else:
                    nombre_final = entidad_nombre_final or self.entidad_nombre
                    entidad, creada = modelo.objects.get_or_create(nombre=nombre_final)
                    if creada:
                        entidad.creado_por = usuario
                        self._aplicar_datos_extra(entidad)
                        entidad.save()

                rol = (self.datos_extra or {}).get("rol_en_el_documento")
                # Sentido inverso (p. ej. R080 "is creation date of"): en RiC-CM
                # la entidad es el dominio y el documento el rango.
                origen, destino = (entidad, self.origen) if (self.datos_extra or {}).get("inversa") else (self.origen, entidad)
                relacion = RelacionRiC(
                    relacion_id=self.relacion_id, origen=origen, destino=destino,
                    evidencia=self.evidencia, validado_por=usuario, fecha_validacion=timezone.now(),
                    descripcion_relacion=f"Rol en el documento: {rol}." if rol else "",
                )
                relacion.save()  # revalida dominio/rango (segunda pasada, defensa en profundidad)
                relacion.estado = (
                    RelacionRiC.Estado.ACEPTADA if nombre_final == self.entidad_nombre and entidad_existente is None
                    else RelacionRiC.Estado.MODIFICADA
                )
                relacion.save()
                self.estado = relacion.estado
            else:
                self.estado = self.Estado.RECHAZADA

            self.motivo_decision = motivo
            self.validado_por = usuario
            self.fecha_validacion = timezone.now()
            self.save()

            instanciacion = self.evidencia.instanciacion if self.evidencia else None
            registrar_evento(
                instanciacion, EventoRiC.Tipo.VALIDACION,
                agente=usuario,
                detalle={"propuesta": self.pk, "estado": self.estado, "motivo": motivo},
            )


class PropuestaSegmentacion(models.Model):
    """F04 (Segmentación): propuesta de que `instanciacion` contiene, además
    de su documento principal, otro documento distinto a partir de cierta
    página — detectada por repetición de un título (F03) dentro del mismo
    archivo (por ejemplo, varios oficios escaneados juntos en un solo PDF).

    Es heurística basada en reglas, igual que F03, no un modelo de IA —
    pero el principio es el mismo que en `PropuestaRiC`: 'la IA propone, la
    persona decide'. Nunca se separa el archivo solo: `validar()` es el
    único camino para crear el Record/Instantiation del segmento."""

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de validación"
        ACEPTADA = "aceptada", "Aceptada"
        RECHAZADA = "rechazada", "Rechazada"

    instanciacion = models.ForeignKey(
        Instantiation, on_delete=models.CASCADE, related_name="propuestas_segmentacion"
    )
    pagina_inicio = models.PositiveIntegerField()
    pagina_fin = models.PositiveIntegerField()
    titulo_detectado = models.CharField(max_length=500, blank=True)
    confianza = models.FloatField()
    regla = models.CharField(max_length=50)

    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    motivo_decision = models.TextField(blank=True)
    validado_por = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.PROTECT, related_name="segmentaciones_validadas"
    )
    fecha_validacion = models.DateTimeField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    record_creado = models.ForeignKey(
        "Record", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="El Record creado al aceptar esta propuesta (vacío si está pendiente o fue rechazada).",
    )
    instanciacion_creada = models.ForeignKey(
        Instantiation, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["instanciacion", "pagina_inicio"]
        verbose_name = "propuesta de segmentación (F04)"
        verbose_name_plural = "propuestas de segmentación (F04)"

    def __str__(self):
        return f"{self.instanciacion} p.{self.pagina_inicio}-{self.pagina_fin}: {self.titulo_detectado} ({self.estado})"

    def validar(self, usuario, aceptar, motivo=""):
        from django.utils import timezone

        if self.estado != self.Estado.PENDIENTE:
            raise ValueError("Esta propuesta ya fue validada.")
        if not usuario or not usuario.is_authenticated:
            raise PermissionError("Solo una persona autenticada puede validar.")
        if not aceptar and not motivo:
            raise ValueError("Indique el motivo del rechazo.")

        with transaction.atomic():
            if aceptar:
                from .segmentacion import materializar_segmento

                self.record_creado, self.instanciacion_creada = materializar_segmento(self)
                self.estado = self.Estado.ACEPTADA
            else:
                self.estado = self.Estado.RECHAZADA

            self.motivo_decision = motivo
            self.validado_por = usuario
            self.fecha_validacion = timezone.now()
            self.save()

            registrar_evento(
                self.instanciacion, EventoRiC.Tipo.SEGMENTACION, agente=usuario,
                detalle={
                    "propuesta": self.pk, "pagina_inicio": self.pagina_inicio, "pagina_fin": self.pagina_fin,
                    "titulo": self.titulo_detectado, "aceptada": aceptar, "motivo": motivo,
                },
            )
        return self


class EventoRiC(models.Model):
    """Bitácora de preservación del núcleo `ric`, mismo patrón que
    `acervo.EventoPreservacion` (estilo PREMIS: cada evento se encadena con
    el anterior mediante un hash, así que alterar o borrar uno rompe la
    cadena) pero encadenada por `Instantiation` en vez de por `Documento`.

    Limitación conocida y aceptada: un evento sobre una relación entre dos
    entidades sin ninguna Instantiation de por medio (por ejemplo, una
    relación de parentesco entre dos Person) no tiene una cadena continua
    que integrar — `instanciacion` queda vacío y el evento no se encadena
    con nada. Para el ciclo experimental P0 (procedencia, tema, fechas de
    un Record) esto no aplica: esas relaciones siempre nacen de evidencia
    en una Instantiation.
    """

    class Tipo(models.TextChoices):
        EXTRACCION = "extraccion_texto", "Extracción de texto (OCR)"
        PROPUESTA_IA = "propuesta_ia", "Propuesta generada por IA"
        VALIDACION = "validacion_humana", "Validación humana"
        SEGMENTACION = "segmentacion", "Segmentación en documento nuevo (F04)"
        FUSION = "fusion_entidades", "Fusión de dos entidades duplicadas (F08)"
        INGESTA = "ingesta", "Carga de un archivo (M1)"
        RELACION_EDITADA = "relacion_editada", "Relación corregida o retirada (M4)"
        PUBLICACION = "publicacion", "Aprobación y publicación en el catálogo (M6)"
        EXPORTACION = "exportacion", "Exportación (M9)"

    instanciacion = models.ForeignKey(
        Instantiation, null=True, blank=True, on_delete=models.PROTECT, related_name="eventos"
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
        verbose_name = "evento (bitácora RiC)"
        verbose_name_plural = "eventos (bitácora RiC)"

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.instanciacion or 'sin instanciación'}"

    def calcular_hash(self):
        contenido = json.dumps(
            {
                "instanciacion": self.instanciacion_id,
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


def registrar_evento(instanciacion, tipo, agente, detalle=None, exitoso=True):
    agente_str = getattr(agente, "get_username", lambda: str(agente))()
    with transaction.atomic():
        ultimo = None
        if instanciacion is not None:
            ultimo = (
                EventoRiC.objects.select_for_update()
                .filter(instanciacion=instanciacion)
                .order_by("-id")
                .first()
            )
        evento = EventoRiC(
            instanciacion=instanciacion,
            tipo=tipo,
            agente=agente_str,
            detalle=detalle or {},
            exitoso=exitoso,
            hash_anterior=ultimo.hash_evento if ultimo else GENESIS,
        )
        evento.hash_evento = evento.calcular_hash()
        evento.save()
    return evento


class Exportacion(models.Model):
    """M9 (RF-M9-03): registro de cada exportación — quién, cuándo, qué
    formato, qué documentos — con el archivo generado para descargarlo."""

    class Formato(models.TextChoices):
        RDF = "rdf", "RDF/RiC-O (Turtle)"
        JSON_LD = "json-ld", "JSON-LD"
        CSV = "csv", "CSV (tabular)"

    usuario = models.ForeignKey("auth.User", null=True, on_delete=models.SET_NULL, related_name="exportaciones")
    fecha = models.DateTimeField(auto_now_add=True)
    formato = models.CharField(max_length=10, choices=Formato.choices)
    documentos = models.JSONField(default=list, help_text="IDs de los Record exportados.")
    total_registros = models.PositiveIntegerField(default=0)
    archivo = models.FileField(upload_to="ric/exportaciones/%Y/%m/")

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "exportación (M9)"
        verbose_name_plural = "exportaciones (M9)"

    def __str__(self):
        return f"{self.get_formato_display()} · {self.total_registros} registro(s) · {self.fecha:%Y-%m-%d %H:%M}"


class ProveedorIAConfig(models.Model):
    """M11 (RF-M11-02): proveedores de IA configurados desde la propia
    aplicación, con prueba de conexión antes de activarlos. Solo uno está
    activo a la vez como fuente del motor de análisis."""

    class Proveedor(models.TextChoices):
        GEMINI = "gemini", "Gemini (Google, en la nube)"
        CLAUDE = "claude", "Claude (Anthropic, en la nube)"
        LOCAL = "local-spacy", "IA local (spaCy, sin salir del servidor)"

    proveedor = models.CharField(max_length=20, choices=Proveedor.choices)
    modelo = models.CharField(max_length=100, blank=True, help_text="Vacío = el modelo por defecto del proveedor.")
    clave_api = models.CharField(max_length=500, blank=True, help_text="Vacío = usar la variable de entorno del servidor.")
    activo = models.BooleanField(default=False)
    ultima_prueba = models.DateTimeField(null=True, blank=True)
    prueba_exitosa = models.BooleanField(null=True, blank=True)
    mensaje_prueba = models.TextField(blank=True)
    actualizado_por = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "proveedor"]
        verbose_name = "proveedor de IA (M11)"
        verbose_name_plural = "proveedores de IA (M11)"

    def __str__(self):
        return f"{self.get_proveedor_display()}{' · ' + self.modelo if self.modelo else ''}"

    @property
    def clave_enmascarada(self):
        if not self.clave_api:
            return "(variable de entorno)"
        return "•••• " + self.clave_api[-4:]


class ConfiguracionSistema(models.Model):
    """Parámetros configurables desde M11: el tiempo límite de revisión
    (RF-M10-04) y el umbral de calidad del OCR (RF-M2-04). Una sola fila."""

    dias_limite_revision = models.PositiveIntegerField(
        default=7, help_text="RF-M10-04: días tras los cuales un documento pendiente de revisión genera alerta.",
    )
    umbral_calidad_ocr = models.FloatField(
        default=60.0, help_text="RF-M2-04: confianza media de OCR (0-100) por debajo de la cual una página se marca 'calidad baja'.",
    )
    umbral_confianza_revision = models.FloatField(
        default=0.70, help_text="CC-04: confianza (0-1) por debajo de la cual una ficha se marca de baja confianza en análisis y revisión.",
    )
    umbral_similitud_vocabulario = models.FloatField(
        default=0.80, help_text="CC-05: similitud (0-1) a partir de la cual se propone reutilizar una entrada del vocabulario en vez de crear una nueva.",
    )
    actualizado_por = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuración del sistema"
        verbose_name_plural = "configuración del sistema"

    def __str__(self):
        return "Configuración del sistema"

    @classmethod
    def actual(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config


def verificar_cadena(instanciacion):
    """Devuelve (True, None) si la bitácora de `instanciacion` está intacta,
    o (False, evento_roto) si algo se alteró o se borró de la cadena."""
    anterior = GENESIS
    for evento in instanciacion.eventos.order_by("id"):
        if evento.hash_anterior != anterior or evento.calcular_hash() != evento.hash_evento:
            return False, evento
        anterior = evento.hash_evento
    return True, None
