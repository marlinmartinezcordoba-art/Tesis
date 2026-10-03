"""
Listas de valores controlados usadas por más de un modelo. Cada una tiene
como comentario la sección de la especificación funcional de la que sale,
para no tener que volver al documento a verificar de dónde salió un valor.
"""

# Hallazgos CM-01, CM-05, CM-16 y CM-20 de la auditoría RiC: aquí había
# enumerados de una versión anterior de la especificación (nivel y soporte
# del documento, tipo de copia, tipo de agente, rol del agente, tipo de
# función, de norma, de fecha, precisión y tipo de lugar) que ningún código
# usaba y que divergían de los vigentes. Se retiraron: cada lista controlada
# vive una sola vez, junto a su modelo (models/descripcion.py,
# models/recurso_documental.py) y, cuando corresponde, como restricción de
# la base de datos.

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
    # -- agregadas por la autora del proyecto al construir el módulo de
    #    descripción (códigos oficiales de RiC-CM 1.0 / RiC-O 1.1) --
    "has_or_had_instantiation",  # RiC-R025 — Record Resource → Instantiation
    "documents",  # RiC-R033 — Record Resource → Activity que documenta
    "has_or_had_subject",  # RiC-R019 — Record Resource → lo que se menciona o trata
    # -- contexto institucional y relaciones entre agentes (Módulo 2,
    #    versión actualizada; verificadas contra RiC-O 1.1, archivo oficial) --
    "has_activity_type",  # rico:hasActivityType — Activity → ActivityType (sin código R: es una propiedad de tipo)
    "performs_or_performed",  # RiC-R060i — Agent → Activity que ejerce
    "has_successor",  # RiC-R016 — Agent → Agent que lo sucede
    "is_agent_associated_with_agent",  # RiC-R044 — vínculo entre agentes sin jerarquía ni sucesión
    "is_date_associated_with",  # RiC-R068 — Date → la Activity (u otra cosa) que fecha
    # -- verificación contra el OWL de RiC-O 1.1 de los trece puntos que el
    #    anexo de mapeo dejó pendientes (documentacion/anexos/
    #    verificacion-ric-o-1-1.md); propiedad exacta en servicios/ric_o.py --
    "has_or_had_holder",  # RiC-R039i — Record Resource o Instantiation → agente custodio
    "precedes_or_preceded",  # RiC-R008 — un documento precede a otro de la misma serie
    "has_direct_subevent",  # rico:hasDirectSubevent — actividad mayor → sub-actividad
    "contains_or_contained",  # RiC-R007 — lugar que contiene a otro
    "affects_or_affected",  # RiC-R059 — hito institucional (Event) → agente cuya historia marca
    "is_related_to",  # RiC-R001 — tipo de actividad (función) ↔ serie que produce (sin propiedad dedicada)
    "issued_by",  # RiC-R065 — mandato → entidad que lo expidió
)

# Los nombres de RiC-O de cada código (y su inversa) viven solo en
# app/servicios/ric_o.py: ric_o.uri() y ric_o.uri_inversa().


