"""
Listas de valores controlados usadas por más de un modelo. Cada una tiene
como comentario la sección de la especificación funcional de la que sale,
para no tener que volver al documento a verificar de dónde salió un valor.
"""

# Documento — nivel de descripción (sección 09, bloque Documento)
NIVEL_DOCUMENTO = ("documento_simple", "componente", "conjunto")

# Documento — soporte (sección 09, bloque Documento)
SOPORTE_DOCUMENTO = ("fisico", "digital_nativo", "digitalizado")

# Instanciación — tipo de copia (sección 09, bloque Instanciación)
TIPO_COPIA = ("master_preservacion", "copia_acceso")

# Instanciación — condición de acceso (sección 09, bloque Instanciación;
# conecta con Ley 1712 de 2014 sobre transparencia y acceso a la información
# pública — la clasificación real de cada documento es una decisión
# archivística, este campo solo la registra)
CONDICION_ACCESO = ("abierto", "restringido", "reservado")

# Agente — tipo de agente (sección 09, bloque Agente; subtipos de la clase
# Agent en RiC-CM 1.0: Person (RiC-E08) y Group (RiC-E09) con CorporateBody
# (RiC-E11) y Family (RiC-E10) como subtipos de Group, más Position
# (RiC-E12) y Mechanism (RiC-E13) — agregados tras la revisión del estándar
# oficial de noviembre de 2023 (ver artefacto "Alineación con RiC-CM 1.0"):
# "cargo" es el rol funcional de una persona dentro de un grupo,
# independiente de quién lo ocupe en cada momento (p. ej. "Secretario
# General" como entidad propia, distinta de la persona que lo ejerce hoy);
# "mecanismo" es un proceso o sistema — típicamente de software — que
# realiza actividades según reglas dadas por quien lo creó, útil para
# trazar como agente al propio motor de análisis (módulo 3) cuando importa
# registrar qué propuso, con qué versión, y no solo guardarlo como texto
# suelto en origen_motor.
TIPO_AGENTE = ("persona", "entidad_corporativa", "familia", "grupo", "cargo", "mecanismo")

# Agente — rol que cumple en un documento específico (usado por el prompt
# de la clase Agente y por el criterio CC-03: solo productor o firmante
# sustentan una relación de procedencia)
ROL_AGENTE_EN_DOCUMENTO = ("productor", "firmante", "destinatario", "mencionado")

# Actividad — tipo de función (sección 09, bloque Actividad y Función)
TIPO_FUNCION = ("sustantiva", "de_apoyo")

# Mandato — tipo de norma (sección 09, bloque Mandato y Regla)
TIPO_NORMA = ("externa", "interna")

# Fecha — tipo de fecha (sección 09, bloque Fecha)
TIPO_FECHA = ("creacion", "tramite", "vigencia", "plazo")

# Fecha — precisión (sección 09, bloque Fecha; CC-07 exige no forzar una
# fecha exacta cuando el documento no la da)
PRECISION_FECHA = ("exacta", "aproximada", "rango")

# Lugar — tipo de lugar (sección 09, bloque Lugar)
TIPO_LUGAR = ("pais", "departamento", "municipio", "direccion")

# Relación — categorías amplias de la ontología RiC-O (sección 09, bloque
# Relación, y sección 10 sobre el motor de grafo). Cada una agrupa varios
# códigos específicos de CODIGO_RELACION_RIC más abajo.
TIPO_RELACION = ("procedencia", "asociacion", "temporal", "inclusion", "espacial", "identidad")

# Relación — código específico tomado del catálogo oficial de relaciones de
# RiC-CM 1.0 (sección 5.4/5.6, códigos RiC-Rxxx), en snake_case siguiendo la
# convención de nombres de propiedad de RiC-O (prefijo rico:). Nullable a
# nivel de columna: no reemplaza a tipo_relacion (que sigue siendo
# obligatorio como categoría amplia), lo precisa cuando corresponde a uno
# de estos ~30 códigos más relevantes para un archivo público colombiano.
# El estándar define 86 en total (ver artefacto "Alineación con RiC-CM
# 1.0"); esta lista se amplía según haga falta, nunca hay que agotarla de
# una vez. Comentario entre paréntesis: código RiC-R oficial y categoría.
CODIGO_RELACION_RIC = (
    # -- procedencia (RiC-R026 has provenance y sus especializaciones) --
    "has_creator",  # RiC-R027 — autoría/creación intelectual
    "has_author",  # RiC-R079 — autoría formal de un Record (persona/grupo/cargo)
    "has_accumulator",  # RiC-R028 — acumulación intencional o no
    "has_receiver",  # RiC-R029
    "has_collector",  # RiC-R030
    "has_sender",  # RiC-R031
    "has_addressee",  # RiC-R032
    # -- gestión / custodia (RiC-R036 has or had authority over y narrower) --
    "is_or_was_holder_of",  # RiC-R039 — custodia; no existe "transfer of custody" como código propio
    "is_or_was_manager_of",  # RiC-R038
    "is_or_was_owner_of",  # RiC-R037
    "is_or_was_controller_of",  # RiC-R041
    # -- agente a agente (RiC-R044 y narrower) --
    "has_or_had_subordinate",  # RiC-R045 — jerarquía institucional
    "has_or_had_subdivision",  # RiC-R005 — subdivisión de un Group
    "occupies_or_occupied",  # RiC-R054 — persona que ocupa un cargo (Position)
    "exists_or_existed_in",  # RiC-R056 — el cargo (Position) existe dentro de un Group
    "has_or_had_member",  # RiC-R055
    "is_or_was_leader_of",  # RiC-R042
    # -- recurso documental a recurso documental / instanciación --
    "includes_or_included",  # RiC-R024 — pertenencia a un conjunto documental
    "has_or_had_constituent",  # RiC-R003
    "is_original_of",  # RiC-R010
    "has_copy",  # RiC-R012
    "has_or_had_derived_instantiation",  # RiC-R014
    "migrated_into",  # RiC-R015 — migración/conversión de formato entre instanciaciones
    # -- regla / mandato --
    "regulates_or_regulated",  # RiC-R063 — una Rule regula un Record Resource (p. ej. retención)
    "is_or_was_expressed_by",  # RiC-R064 — la Rule vive textualmente en un Record
    "authorizes",  # RiC-R067 — Mandate autoriza a un Agente
    # -- fecha --
    "is_creation_date_of",  # RiC-R080
    "is_beginning_date_of",  # RiC-R069
    "is_end_date_of",  # RiC-R071
    "is_modification_date_of",  # RiC-R073
    # -- espacial --
    "is_or_was_location_of",  # RiC-R075
    "is_or_was_jurisdiction_of",  # RiC-R076
)

# Relación — de dónde salió la propuesta (CC-05, CC-08)
ORIGEN_DECISION = ("propuesta_ia", "correccion_manual")

# Usuario — roles del sistema (sección 07, módulo 11, RF-M11-01)
ROL_USUARIO = ("archivista", "revisor", "consulta", "administrador")
