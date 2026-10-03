# Auditoría de conformidad RiC — Rama RiC-O, propiedad por propiedad

Alcance: secciones 4, 7 y 8 del prompt de auditoría. Revisa las relaciones de la sección 3 del anexo de mapeo, los 13 puntos pendientes de su sección 4 (con la decisión de `documentacion/anexos/verificacion-ric-o-1-1.md`), una comprobación mecánica anti-invención contra el OWL oficial (`app/recursos/ric-o/RiC-O_1-1.rdf`) y la validación SHACL.

Método:
- Lectura con número de línea de `app/servicios/ric_o.py` (el mapeo único), `app/servicios/exportacion_rico.py`, `app/servicios/conformidad_rico.py`, `app/servicios/grafo.py`, `app/recursos/ric-o/perfil-ricora.shacl.ttl`, los servicios que escriben filas en `relaciones` y las pruebas.
- Dos scripts propios en el anexo A:
  - `estatico.py`: extrae todo término `rico:`/`RICO.`/`RICO[...]`/`skos:` del backend, del frontend y del perfil SHACL, más los 111 términos de los diccionarios del mapeo, y los coteja con el OWL mediante rdflib.
  - `test_auditoria_dinamica.py`: arma un fondo con **todas** las relaciones del mapeo. Las crea con los servicios reales (`autoridad.vincular` para los 13 vínculos de `VINCULOS`) y con filas directas para las que crea el flujo de descripción. Lo exporta con `exportacion_rico.exportar` y verifica cada tripleta contra el OWL con un verificador **independiente** de `conformidad_rico`. Se ejecutó sobre una base de datos PostgreSQL aparte (`ricora_auditoria_rico`), sin tocar el repositorio.
- Las pruebas del repositorio se ejecutaron como se pidió (resultado en O-31).

Convención de citas: «IRI» = `https://www.ica.org/standards/RiC/ontology#` + nombre local. Toda relación guardada en `relaciones` se exporta por un único punto genérico:
- `app/servicios/exportacion_rico.py:244` toma `ric_o.propiedad(rel.codigo_ric)`;
- `:249` filtra por dominio y rango (`ric_o.uso_valido`);
- `:252` escribe `(uri(origen), RICO[p.rico], uri(destino))`.

En adelante, «exportación genérica» remite a esas tres líneas.

---

## A. Relaciones de la sección 3 del anexo

### O-01 · documents / documentedBy (Record Resource → Activity)
- Rama: RiC-O
- Módulo(s): descripcion, vocabularios, instrumentos
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/models/descripcion.py:170-203` — tabla `relaciones` (`codigo_ric` enum, `origen_*`/`destino_*`), creada en `alembic/versions/0003_descripcion.py:92`.
  - `app/servicios/descripcion.py:77` — `("actividad", None): ("documents", …)`; `:419-421` — la publicación inserta la fila documento → actividad.
  - `app/servicios/ric_o.py:157` — `"documents": Propiedad("documents", "RiC-R033", RECURSOS + ("Instantiation",), ("Activity",), "documentedBy")`.
  - Exportación genérica `app/servicios/exportacion_rico.py:244-252`; IRI `rico:documents`. La inversa `documentedBy` no se emite; se infiere por `owl:inverseOf`, que `ric_o.py:424-428` comprueba contra el OWL.
  - Script dinámico: 1 tripleta `rico:documents`, 0 problemas de dominio y rango.
- Prueba automatizada: `tests/test_exportacion_rico.py::test_contexto_agentes_lugar_funciones_actividad_mandato` (aserción `(o114, RICO.documents, actividad)`); `tests/test_descripcion_contexto.py::test_la_actividad_queda_conectada_a_su_tipo_agente_y_mandato_y_se_ve_en_el_catalogo`; `tests/test_ric_o.py::test_todo_el_mapeo_es_conforme_al_owl_oficial`.
- Razonamiento: la actividad es un registro del vocabulario (`entidades_vocabulario`, clase «actividad»), no un texto libre en el documento. Dos archivistas que nombren la misma actividad terminan en el mismo nodo gracias a la verificación de duplicados del vocabulario. El nombre interno `documents` coincide con la propiedad RiC-O; el código R033 coincide con `RiCCMCorrespondingComponent`.

### O-02 · hasOrHadPart / isOrWasPartOf e includesOrIncluded (jerarquía documental)
- Rama: RiC-O
- Módulo(s): descripcion, instrumentos
- Clasificación: Implementado y conforme
- Evidencia:
  - La jerarquía vive en `recursos_documentales.incluido_en_id` (una sola FK, de modo que el padre es único). Además se escribe una fila `includes_or_included` (`tests/test_instrumentos.py:38-39` refleja el patrón del servicio) y `has_or_had_constituent` para las partes (`app/servicios/descripcion.py:682-683`).
  - `app/servicios/ric_o.py:147-150`:
    - `includesOrIncluded` (R024): RecordSet → RecordSet | Record;
    - `hasOrHadConstituent` (R003): Record | RecordPart → Record | RecordPart.
  - `app/servicios/exportacion_rico.py:350-355`: la jerarquía se exporta desde `incluido_en_id`; `:353` usa `rico:hasOrHadConstituent` para la parte documental y `:355` usa `rico:includesOrIncluded` en los demás casos.
  - En el OWL, `includesOrIncluded` y `hasOrHadConstituent` son `rdfs:subPropertyOf rico:hasOrHadPart` (comprobado con rdflib), así que `hasOrHadPart` queda implicado sin emitirse.
  - `hasOrHadPart` e `isOrWasPartOf` no se emiten nunca. Términos buscados: `hasOrHadPart`, `isOrWasPartOf` en app/ y frontend/src, sin resultado fuera del OWL. Es la decisión de la corrección 1 del anexo de verificación.
- Prueba automatizada: `tests/test_exportacion_rico.py::test_cada_nivel_con_su_clase_y_su_tipo_de_agrupacion`; `tests/test_ric_o.py::test_parte_documental_es_record_part_y_se_une_por_constituyente`; `tests/test_descripcion_v3.py::test_parte_documental_con_recorte_queda_unida_a_su_unidad_documental`.
- Razonamiento: se usan las subpropiedades más específicas que exige la nota de uso de `hasOrHadPart`. La cardinalidad (un solo padre) la garantizan la FK y la forma SHACL `pr:RecordPart` (`perfil-ricora.shacl.ttl:45-49`, `sh:maxCount 1`). El script dinámico encontró 7 `includesOrIncluded` y 1 `hasOrHadConstituent`, sin problemas.

### O-03 · hasOrHadInstantiation / isOrWasInstantiationOf
- Rama: RiC-O
- Módulo(s): ingesta, descripcion, preservacion, instrumentos
- Clasificación: Implementado y conforme
- Evidencia:
  - Fila `has_or_had_instantiation` recurso → instanciación: `app/routers/descripcion.py:326,346`; `app/servicios/preservacion.py:525-527` la replica tras migrar.
  - `app/servicios/ric_o.py:153-154` (R025, RECURSOS → Instantiation, inversa `isOrWasInstantiationOf`).
  - Exportación genérica; nodo `rico:Instantiation` en `app/servicios/exportacion_rico.py:453-465`.
- Prueba automatizada: `tests/test_instrumentos.py::test_grafo_de_un_documento_con_sus_relaciones_ric_y_sin_datos_internos`. La exportación RDF la cubre de forma indirecta `tests/test_exportacion_rico.py::test_la_exportacion_es_conforme_al_owl_y_al_perfil_shacl` (la forma `pr:Instantiation`, `perfil-ricora.shacl.ttl:53-58`, exige `inversePath hasOrHadInstantiation` o `migratedInto`).
- Razonamiento: la relación es una fila tipada con el nombre exacto, en la dirección del dominio, y la valida SHACL.

### O-04 · hasCreator / isCreatorOf
- Rama: RiC-O
- Módulo(s): descripcion, instrumentos
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/descripcion.py:69` (`("agente","productor"): ("has_creator", …)`) y `:386-398` (fila documento → agente con rol).
  - `app/servicios/ric_o.py:140` (R027, RECURSOS + Instantiation → los seis subtipos de agente).
  - Exportación genérica; 3 tripletas en el script dinámico.
- Prueba automatizada: `tests/test_exportacion_rico.py::test_contexto_agentes_lugar_funciones_actividad_mandato` (`(o114, RICO.hasCreator, alcaldia)`); `tests/test_exportacion_rico.py::test_shacl_detecta_lo_que_no_cumple[relacion_a_clase_ajena-relacion-has_creator]`.
- Razonamiento: el productor es un agente controlado del vocabulario, no un texto. No se usan las clases reificadas `OrganicProvenanceRelation` (el anexo las deja como opcionales «cuando se necesite mayor precisión»). El rol y la procedencia quedan en la fila y no se exportan, por la regla de procedencia del sistema.

### O-05 · performsOrPerformed / isOrWasPerformedBy
- Rama: RiC-O
- Módulo(s): descripcion, vocabularios
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/descripcion.py:436-438` (agente → actividad en la publicación).
  - `app/servicios/autoridad.py:344-345` (vínculo `ejercida_por`, que se declara desde la actividad pero guarda la fila agente → actividad).
  - `app/servicios/ric_o.py:160-161` (R060i, AGENTES → Activity).
  - Exportación genérica; 2 tripletas en el script dinámico, sin problemas.
- Prueba automatizada: `tests/test_exportacion_rico.py::test_contexto_agentes_lugar_funciones_actividad_mandato`; `tests/test_ric_o.py::test_la_verificacion_detecta_un_rango_que_no_corresponde`.
- Razonamiento: el OWL declara dominio `Agent` y rango `Activity`, idénticos a lo que el código admite.

### O-06 · authorizedBy / authorizes (Mandate → Agent)
- Rama: RiC-O
- Módulo(s): descripcion, vocabularios
- Clasificación: Implementado y conforme (con la corrección del anexo)
- Evidencia:
  - `app/servicios/descripcion.py:442-445`: cuando una actividad cita mandato y agente, se crea la fila mandato → agente `authorizes`.
  - `app/servicios/autoridad.py:354-355` (vínculo `creado_por`, rol «creacion»).
  - `app/servicios/ric_o.py:172-173` (`authorizes` R067, Mandate → AGENTES, inversa `authorizedBy`).
  - OWL: `authorizedBy` tiene dominio `Agent` y rango `Mandate` (comprobado). Por eso la relación «actividad fundamentada en mandato» que pedía el anexo se resuelve con `regulatesOrRegulated` (`ric_o.py:164-169`), como dice la corrección 2 de `verificacion-ric-o-1-1.md`.
  - Exportación genérica; 1 tripleta `rico:authorizes` en el script dinámico.
- Prueba automatizada: `tests/test_autoridad.py::test_mandato_que_crea_un_agente_y_entidad_que_lo_expidio` y `tests/test_descripcion_contexto.py::test_la_actividad_queda_conectada_a_su_tipo_agente_y_mandato_y_se_ve_en_el_catalogo`, ambas de base de datos y API. Ninguna prueba del repositorio afirma la tripleta RDF `rico:authorizes`; solo la cubre el mapeo, en `tests/test_ric_o.py::test_todo_el_mapeo_es_conforme_al_owl_oficial`.
- Razonamiento: el código no usó `authorizedBy` con Activity, que habría violado el dominio. Usa la dirección y el dominio reales del OWL. El campo `authorizingMandate` del anexo no existe en RiC-O 1.1 como propiedad; búsqueda en el OWL: sin resultado, y el código no lo inventa.

### O-07 · hasSuccessor / isSuccessorOf
- Rama: RiC-O
- Módulo(s): vocabularios
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/autoridad.py:330-331` (vínculo `sucesor`, jerárquico, sin ciclos).
  - `app/servicios/ric_o.py:176` (R016, AGENTES → AGENTES).
  - `app/models/enums.py:159-163`: la inversa se lee de la misma fila.
  - API `app/routers/vocabulario.py:322` (`POST /{entidad_id}/vinculos`).
  - Exportación genérica; 1 tripleta en el script dinámico.
- Prueba automatizada: `tests/test_autoridad.py::test_relacion_entre_agentes_es_una_fila_con_su_inversa_fecha_y_nota`. Ninguna prueba ejercita la exportación RDF de esta relación.
- Razonamiento: una sola fila con fecha y nota, sin ciclos, y el nombre exacto de RiC-O. La vigencia (`relaciones.fecha_edtf`) no se exporta. RiC-O solo podría expresarla reificando la relación (`AgentTemporalRelation`), y eso no se hace. Es una pérdida menor, no una invención.

### O-08 · hasOrHadSubordinate / isOrWasSubordinateTo
- Rama: RiC-O
- Módulo(s): vocabularios
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/autoridad.py:328-329` (vínculo `subordinado`).
  - `app/servicios/ric_o.py:175` (R045).
  - Exportación genérica; 1 tripleta en el script dinámico.
- Prueba automatizada: `tests/test_autoridad.py::test_jerarquia_entre_cargos_usa_la_misma_relacion`; `tests/test_descripcion_contexto.py::test_relaciones_entre_agentes_con_su_inversa`. Ninguna prueba de la exportación RDF.
- Razonamiento: es la relación que el anexo de verificación usa para sustituir el texto «estructura interna» (ISAAR 5.2.7). Ese texto se omite explícitamente (`ric_o.py:251-253`, `exportacion_rico.py:384-385`), sin inventar nada.

### O-09 · migratedInto / migratedFrom
- Rama: RiC-O
- Módulo(s): preservacion
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/preservacion.py:522-524` (fila original → nueva al migrar).
  - `app/servicios/ric_o.py:155` (R015, Instantiation → Instantiation).
  - Exportación genérica; 1 tripleta en el script dinámico.
  - `perfil-ricora.shacl.ttl:57-58` admite la instanciación derivada por `inversePath migratedInto`.
- Prueba automatizada: `tests/test_preservacion.py::test_migracion_soportada_crea_nueva_instanciacion_sin_tocar_la_original` y `::test_migracion_no_soportada_espera_el_archivo_y_luego_lo_enlaza` (base de datos). Ninguna prueba del RDF.
- Razonamiento: es una fila tipada y dirigida. `migratedInto` es subpropiedad de `hasOrHadDerivedInstantiation` en el OWL, así que la semántica es correcta.

### O-10 · hasOrHadIdentifier / isOrWasIdentifierOf
- Rama: RiC-O
- Módulo(s): vocabularios, instrumentos
- Clasificación: Implementado y conforme (la parte `owl:sameAs` se trata en O-30)
- Evidencia:
  - Tabla `identificadores_entidad` (`app/models/descripcion.py:296-311`; migración `alembic/versions/0011_autoridad_isaar.py:69-104`), con un esquema controlado `ESQUEMA_IDENTIFICADOR` (`app/models/descripcion.py:42`).
  - Servicio `app/servicios/autoridad.py:201-226`; API `app/routers/vocabulario.py:275`.
  - `app/servicios/ric_o.py:237-238` (`hasOrHadIdentifier` → `Identifier`; `hasIdentifierType` → `IdentifierType`).
  - `app/servicios/exportacion_rico.py:415-422`: nodo `rico:Identifier` con `rico:textualValue`, `rico:hasIdentifierType` hacia un concepto `rico:IdentifierType` por esquema y `rico:hasOrHadIdentifier` desde la entidad.
  - Para el código de referencia de los documentos se usa la propiedad de dato `rico:identifier` (`ric_o.py:219`, `exportacion_rico.py:332-335`).
- Prueba automatizada: `tests/test_autoridad.py` (alta de wikidata/VIAF, línea 174 y siguientes); `tests/test_exportacion_rico.py::test_contexto_agentes_lugar_funciones_actividad_mandato` solo afirma el `owl:sameAs`, no el nodo `rico:Identifier`. El script dinámico confirma 1 `hasOrHadIdentifier` y 1 `hasIdentifierType` sin problemas.
- Razonamiento: se cumple exactamente lo que el anexo pide (valor y esquema juntos, la misma propiedad para el identificador interno y el externo). El esquema es un valor controlado, no texto libre: dos personas que registren «VIAF» terminan en el mismo concepto `tipo-de-identificador/viaf`.

### O-11 · hasActivityType (Activity → ActivityType)
- Rama: RiC-O
- Módulo(s): descripcion, vocabularios
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/descripcion.py:434-436` (actividad → tipo).
  - `app/servicios/ric_o.py:158-159` (sin código RiC-CM: RiC-O no le asigna `RiCCMCorrespondingComponent`, comprobado).
  - Exportación genérica.
  - `exportacion_rico.py:368-379`: el tipo también es `skos:Concept` en un `skos:ConceptScheme` del fondo, con `skos:broader` y `skos:hasTopConcept`.
  - SHACL `perfil-ricora.shacl.ttl:85-98` (como máximo un tipo por actividad; `skos:broader` hacia otro `ActivityType`).
- Prueba automatizada: `tests/test_exportacion_rico.py::test_contexto_agentes_lugar_funciones_actividad_mandato` (aserciones de `hasActivityType` y `skos:broader`).
- Razonamiento: es la implementación profunda que describe el prompt (sección 5): un vocabulario controlado y reutilizable con jerarquía SKOS. En el OWL, `rico:Type` es subclase de `rico:Concept`, no de `skos:Concept`; la doble tipificación `skos:Concept` es un añadido válido.

### O-12 · expressedDate / normalizedDateValue / dateQualifier (clase Date)
- Rama: RiC-O
- Módulo(s): descripcion, vocabularios, instrumentos
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - Tabla `fechas` (`app/models/descripcion.py:129-148`: `expresion`, `subtipo`, `edtf`, `calendario`; calendario añadido en `alembic/versions/0012_descripcion_v3.py:39`).
  - `app/servicios/ric_o.py:222-224` (A19, A29, A13, verificados contra `RiCCMCorrespondingComponent` en `:434-441`).
  - `app/servicios/exportacion_rico.py:438-450` (nodo `rico:Date`), `:258-269` (fechas libres) y `:266`, `:445` (el calificador «aproximada» o «incierta» se deriva de `~`, `%` o `?`).
  - Las relaciones de fecha usan IRIs sacados del mapeo:
    - `rico:isCreationDateOf` (`ric_o.py:194`, R080);
    - `rico:isDateAssociatedWith` (`ric_o.py:196`, R068);
    - `rico:hasBeginningDate` y `rico:hasEndDate` (`ric_o.py:244-245`).
  - Términos escritos directamente, fuera de los diccionarios del mapeo: `RICO.Date`, `RICO.hasCreationDate` (`exportacion_rico.py:348`) y `RICO.isAssociatedWithDate` (`:284`). Los tres existen en el OWL; la diferencia es de disciplina, porque el docstring de `ric_o.py:4-7` dice «Nadie escribe un nombre de RiC-O suelto en otro módulo».
  - SHACL: `perfil-ricora.shacl.ttl:107-112` y el patrón EDTF generado en `conformidad_rico.py:43-52`.
- Prueba automatizada: `tests/test_exportacion_rico.py::test_contexto_agentes_lugar_funciones_actividad_mandato` (`normalizedDateValue "1948~"` y `dateQualifier "aproximada"`); `::test_shacl_detecta_lo_que_no_cumple[edtf_invalido-rico:normalizedDateValue]`.
- Razonamiento: la parte central es conforme. El OWL documenta EDTF dentro de `normalizedDateValue` y el sistema lo usa. Quedan tres brechas:
  1. La fecha de expedición de un mandato se pierde en RDF (ver O-29).
  2. Las «fechas extremas» de una agrupación (texto libre `recursos_documentales.fechas_extremas`) se exportan como `rico:hasCreationDate` del Record Set (`exportacion_rico.py:345-348`). RiC-O ofrece la propiedad más precisa `hasOrHadAllMembersWithCreationDate` para las fechas de los miembros. Además, el EDTF solo se deriva cuando el texto es «AAAA» o «AAAA–AAAA» (`:322`, `:346-347`); en otro caso solo sale `expressedDate`.
  3. El subconjunto EDTF del sistema rechaza el inicio abierto `../1539` (`app/servicios/fechas.py:154`, comprobado al ejecutar), aunque RiC-O lo admite en sus ejemplos (`1948/..`).
- Acción recomendada:
  - Mover `Date`, `hasCreationDate` e `isAssociatedWithDate` a los diccionarios de `ric_o.py`.
  - Evaluar `hasOrHadAllMembersWithCreationDate` para las fechas extremas de las agrupaciones.
  - Documentar o ampliar el soporte de rangos abiertos al inicio.

### O-13 · hasDirectSubevent / isDirectSubeventOf
- Rama: RiC-O
- Módulo(s): descripcion, vocabularios
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/descripcion.py:473-487` (`_sub_actividad`: una sola actividad mayor, sin ciclos).
  - `app/servicios/autoridad.py:340-341` (vínculo `actividad_mayor`).
  - `app/servicios/ric_o.py:162-163`. El OWL declara dominio y rango `Event` y la propiedad es subpropiedad de `hasDirectPart` y `hasSubeventTransitive`, comprobado.
  - Exportación genérica; 1 tripleta en el script dinámico.
- Prueba automatizada: `tests/test_descripcion_v3.py::test_actividad_publicada_como_sub_actividad_de_otra_existente` (base de datos). Ninguna prueba del RDF.
- Razonamiento: el nombre es exacto y está separado correctamente de la jerarquía SKOS entre tipos de actividad. El frontend lo rotula bien (`frontend/src/components/FichaAutoridad.tsx:863`).

---

## B. Los 13 puntos pendientes del anexo (sección 4) frente a la decisión documentada

### O-14 · Punto 1 — dominio y rango de performsOrPerformed
- Rama: RiC-O · Módulo(s): descripcion, vocabularios · Clasificación: Implementado y conforme
- Evidencia: decisión «confirmado» en `documentacion/anexos/verificacion-ric-o-1-1.md` (tabla, fila 1); `app/servicios/ric_o.py:160-161`; comprobación automática en `ric_o.py:413-423`.
- Prueba automatizada: `tests/test_ric_o.py::test_la_verificacion_detecta_un_rango_que_no_corresponde`.
- Razonamiento: ver O-05. La prueba fuerza un rango erróneo (`Mandate`) y verifica que la comprobación contra el OWL lo detecta, así que la protección es real y no solo declarativa.

### O-15 · Punto 2 — sin subclases de Date
- Rama: RiC-O · Módulo(s): descripcion · Clasificación: Implementado y conforme
- Evidencia:
  - `app/models/descripcion.py:139` (`subtipo` simple, rango o conjunto en la base de datos).
  - `app/servicios/exportacion_rico.py:441` (siempre `rico:Date`).
  - Búsqueda de `SingleDate|DateRange|DateSet` en app/ y frontend/src: sin resultado.
- Prueba automatizada: `tests/test_exportacion_rico.py::test_contexto_agentes_lugar_funciones_actividad_mandato`.
- Razonamiento: el subtipo vive en la base de datos y se transmite en RDF por la forma EDTF de `normalizedDateValue`, como decidió el equipo. No se inventa ninguna subclase.

### O-16 · Punto 3 — relación asociativa entre agentes
- Rama: RiC-O · Módulo(s): vocabularios · Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/autoridad.py:332-333` (vínculo `asociado`, simétrico, que impide el duplicado inverso en `:441-443`).
  - `app/servicios/ric_o.py:177-178` (R044, inversa la propia propiedad).
  - Exportación genérica; 1 tripleta en el script dinámico.
- Prueba automatizada: `tests/test_descripcion_contexto.py::test_relaciones_entre_agentes_con_su_inversa`. Ninguna prueba del RDF.
- Razonamiento: es la propiedad genérica que el OWL ofrece. La nota de uso pide preferir la específica cuando exista, y `hasOrHadWorkRelationWith` no se ofrece como vínculo. Es aceptable mientras la interfaz no distinga relaciones laborales.

### O-17 · Punto 4 — Group instanciable
- Rama: RiC-O · Módulo(s): vocabularios · Clasificación: Implementado y conforme
- Evidencia: `app/servicios/ric_o.py:74` (`"grupo": "Group"`); `app/servicios/exportacion_rico.py:362-363`; el script dinámico emite 1 `rico:Group`.
- Prueba automatizada: `tests/test_ric_o.py::test_grupo_se_instancia_directamente`.
- Razonamiento: es coherente con la nota de alcance de `rico:Group`.

### O-18 · Punto 5 — evento institucional (hito) y su agente
- Rama: RiC-O · Módulo(s): vocabularios · Clasificación: Implementado y conforme
- Evidencia:
  - Tabla `hitos` (`app/models/descripcion.py:313-326`); servicio `app/servicios/autoridad.py:245-278`; API `app/routers/vocabulario.py:292`.
  - `app/servicios/ric_o.py:91` (`"hito": "Event"`) y `:182-186` (`affectsOrAffected`, R059, estado «general»).
  - `app/servicios/exportacion_rico.py:427-434`: `rico:Event`, `rico:name` y `rico:affectsOrAffected` hacia el agente, con la fecha por `_periodo`.
- Prueba automatizada: `tests/test_exportacion_rico.py::test_contexto_agentes_lugar_funciones_actividad_mandato` (`[hito] = list(g.subjects(RICO.affectsOrAffected, alcaldia))`).
- Razonamiento: la propiedad está marcada «general» y documentada como interpretación. El tipo del hito (`creacion`, `reforma`…) no se exporta; queda solo en la base de datos.

### O-19 · Punto 6 — versión de un Mechanism (technicalCharacteristics)
- Rama: RiC-O
- Módulo(s): vocabularios, preservacion, instrumentos
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - La versión vive una sola vez en la ficha del mecanismo: `app/models/descripcion.py:99` (`version`), escrita por `app/servicios/vocabulario.py:375-398` (migración 0013).
  - `app/servicios/ric_o.py:220` mapea `version_mecanismo → technicalCharacteristics` (A41). Dominio OWL: `Mechanism`, comprobado.
  - Pero `app/servicios/exportacion_rico.py:18-19` y `:214` excluyen **todos** los agentes mecanismo de la exportación. `technicalCharacteristics` no aparece en ningún `g.add` (búsqueda de `version_mecanismo` y `technicalCharacteristics` en `exportacion_rico.py`: sin resultado), y el script dinámico confirma 0 tripletas.
  - Contradicciones con lo que se afirma:
    - `documentacion/anexos/verificacion-ric-o-1-1.md` (fila 6) dice «se exporta con `rico:technicalCharacteristics`»;
    - `frontend/src/components/FichaAutoridad.tsx:645` dice al usuario «se exporta como rico:technicalCharacteristics»;
    - la forma SHACL `pr:Mechanism` (`perfil-ricora.shacl.ttl:70-74`, `minCount 1`) nunca tiene focos.
- Prueba automatizada: `tests/test_exportacion_rico.py::test_no_sale_nada_interno_ni_borradores_ni_mecanismos` prueba lo contrario (que el mecanismo NO sale).
- Razonamiento: el modelo de datos es profundo, con un registro reutilizable y la versión declarada una vez. Pero la decisión documentada y el texto de la interfaz prometen una exportación que el código suprime a propósito. No es un nombre inventado, sino una afirmación falsa sobre el comportamiento.
- Acción recomendada: decidir una de dos opciones y alinear documento, interfaz y SHACL:
  - exportar los mecanismos con `rico:technicalCharacteristics`;
  - o corregir la fila 6 del anexo y la pista de `FichaAutoridad.tsx:645`, y retirar la forma `pr:Mechanism`.

### O-20 · Punto 7 — mandato que crea un agente o un tipo de actividad
- Rama: RiC-O · Módulo(s): vocabularios · Clasificación: Implementado y conforme (con pérdida declarada del matiz en RDF)
- Evidencia:
  - `app/servicios/autoridad.py:353-358`: los vínculos `creado_por` (`authorizes`, rol «creacion») y `competencia_creada_por` (`regulates_or_regulated`, rol «creacion», hacia `tipo_actividad`).
  - `app/servicios/ric_o.py:164-173`: el destino de `regulatesOrRegulated` incluye `ActivityType`; el rango OWL es `Thing`.
  - El rol se guarda en `relaciones.rol` y la exportación genérica (`exportacion_rico.py:252`) no lo transmite.
- Prueba automatizada: `tests/test_autoridad.py::test_mandato_que_crea_un_agente_y_entidad_que_lo_expidio`; `::test_mandato_que_crea_una_competencia` (base de datos y API).
- Razonamiento: no se inventó ninguna propiedad «creates». En RDF, sin embargo, «crea al agente» no se distingue de «autoriza al agente», ni «crea la competencia» de «regula». La decisión lo acepta («el rol queda en la base y en la interfaz»).

### O-21 · Punto 8 — vínculo función ↔ serie (TRD)
- Rama: RiC-O · Módulo(s): vocabularios · Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/autoridad.py:364-365` (vínculo `serie_producida`, destino `recurso:serie,subserie`).
  - `app/servicios/ric_o.py:199-203` (`isRelatedTo`, R001, «general»).
  - Exportación genérica; 1 tripleta en el script dinámico.
- Prueba automatizada: `tests/test_autoridad.py::test_tipo_de_actividad_con_su_serie_documental` (base de datos). Ninguna prueba del RDF.
- Razonamiento: se usa la propiedad más general que existe, marcada así. La relación sustantiva sigue reconstruible por `documents` + `hasActivityType`.

### O-22 · Punto 9 — jerarquía y tipo de lugar
- Rama: RiC-O · Módulo(s): vocabularios · Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/autoridad.py:338-339` (vínculo `lugar_superior`, con superior único).
  - `app/servicios/ric_o.py:188-189` (`containsOrContained`, R007) y `:234` (`hasOrHadPlaceType` → `PlaceType`).
  - `app/servicios/exportacion_rico.py:395-397` (tipo de lugar como concepto `rico:PlaceType`).
  - `entidades_vocabulario.tipo_lugar` (`app/models/descripcion.py:118`).
- Prueba automatizada: `tests/test_autoridad.py::test_lugar_con_coordenadas_tipo_superior_y_nombres_historicos`; el tipo de lugar en RDF lo cubre `tests/test_exportacion_rico.py::test_contexto_agentes_lugar_funciones_actividad_mandato`. `containsOrContained` en RDF no tiene prueba; el script dinámico encontró 1 tripleta correcta.
- Razonamiento: es conforme. Prueba de profundidad del tipo de lugar: `tipo_lugar` es `String(30)` y el concepto exportado se arma por slug del texto (`exportacion_rico.py:288`, `_slug`). «Municipio» y «municipio» convergen, pero «municipio» y «ciudad» para el mismo concepto no. Es un vocabulario semicontrolado; conviene revisar si la interfaz restringe los valores.

### O-23 · Punto 10 — secuencia entre documentos
- Rama: RiC-O · Módulo(s): descripcion · Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/descripcion.py:630-641` (misma serie, sin contradicción).
  - `app/servicios/ric_o.py:152` (R008, inversa `followsOrFollowed`).
  - `app/servicios/descripcion.py:814-815` rotula la inversa correctamente.
  - Exportación genérica; 1 tripleta en el script dinámico.
- Prueba automatizada: `tests/test_descripcion_v3.py::test_secuencia_y_custodio_se_guardan_y_se_ven_en_el_catalogo`. Ninguna prueba del RDF.
- Razonamiento: una fila dirigida con validaciones de coherencia y el nombre exacto.

### O-24 · Punto 11 — custodia distinta de la producción
- Rama: RiC-O · Módulo(s): descripcion · Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/descripcion.py:74` (rol «custodio» → `has_or_had_holder`) y `:388-394` (rechaza que el custodio sea el productor).
  - `app/servicios/ric_o.py:144-145` (R039i).
  - Exportación genérica; 1 tripleta en el script dinámico.
- Prueba automatizada: `tests/test_descripcion_v3.py::test_secuencia_y_custodio_se_guardan_y_se_ven_en_el_catalogo`; `::test_custodio_igual_al_productor_se_rechaza`; `tests/test_ric_o.py::test_etiquetas_oficiales_en_espanol`.
- Razonamiento: es conforme. Hay una observación lateral: el catálogo `CODIGO_RELACION_RIC` conserva también `is_or_was_holder_of` (R039, la dirección contraria, `app/models/enums.py:82`), sin mapeo ni escritor (ver O-33).

### O-25 · Punto 12 — jerarquía normativa entre mandatos
- Rama: RiC-O · Módulo(s): vocabularios · Clasificación: Implementado y conforme (interpretación declarada)
- Evidencia:
  - `app/servicios/autoridad.py:350-352` (vínculo `mandato_superior`, rol «jerarquia_normativa», sin ciclos).
  - `app/servicios/ric_o.py:164-169`.
  - Exportación genérica; 4 tripletas `regulatesOrRegulated` en el script dinámico, entre ellas la de mandato a mandato.
- Prueba automatizada: `tests/test_autoridad.py::test_mandato_derivado_se_navega_en_ambos_sentidos_sin_ciclos` (base de datos).
- Razonamiento: igual que en O-20, el rol no viaja en RDF. El riesgo está documentado en la tabla de riesgos de la verificación.

### O-26 · Punto 13 — idioma, condiciones de acceso y de uso
- Rama: RiC-O
- Módulo(s): descripcion, instrumentos
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - Columnas `recursos_documentales.idiomas` (ARRAY ISO 639-3), `condiciones_acceso` y `condiciones_uso` (`app/models/recurso_documental.py:50-58`; migración `alembic/versions/0012_descripcion_v3.py:30-34`).
  - `app/servicios/ric_o.py:215-216` (A08, A09) y `:232-233` (`hasOrHadLanguage` para Record, RecordPart y Agent; `hasOrHadAllMembersWithLanguage` para RecordSet).
  - `app/servicios/exportacion_rico.py:332-335` (condiciones) y `:342-344` (idioma por clase), más `:296-308` (nodo `rico:Language` con `skos:exactMatch` a Lexvo ISO 639-3).
  - El OWL define `hasOrHadAllMembersWithLanguage` como «a Language used by **all** the Records or Record Parts…» y ofrece además `hasOrHadSomeMembersWithLanguage` (comprobado).
- Prueba automatizada: `tests/test_exportacion_rico.py::test_idioma_iso_639_3_con_la_propiedad_de_cada_clase` (solo un Record); `::test_cada_nivel_con_su_clase_y_su_tipo_de_agrupacion` (`conditionsOfAccess`); `tests/test_descripcion_v3.py::test_idioma_y_condiciones_se_guardan_y_sin_ellas_publica`. Ninguna prueba de idioma en un RecordSet ni de `conditionsOfUse` en RDF.
- Razonamiento: acceso, uso e idioma de un Record son conformes. Para una agrupación con varios idiomas (por ejemplo `["spa","lat"]`), el exportador emite una tripleta `hasOrHadAllMembersWithLanguage` por cada idioma. En RiC-O eso afirma que **todos** los miembros están en español **y** todos en latín, lo que casi nunca es cierto. La decisión del anexo de verificación no consideró `hasOrHadSomeMembersWithLanguage`.
- Acción recomendada: usar `hasOrHadSomeMembersWithLanguage` cuando la agrupación declara más de un idioma, o cuando no consta que todos los miembros lo compartan. Añadirlo al mapeo (lo verifica `verificar_contra_owl`) y probarlo.

---

## C. Comprobación mecánica anti-invención

### O-27 · Términos RiC-O emitidos en la exportación RDF: todos existen y se usan con su tipo, dominio y rango
- Rama: RiC-O
- Módulo(s): instrumentos (exportación), descripcion, vocabularios
- Clasificación: Implementado y conforme
- Evidencia:
  - Script estático (anexo A.1): los 111 términos de los diccionarios del mapeo (`ric_o.py:58-246`, clases, propiedades de objeto e inversas, propiedades de dato y de apoyo) existen en el OWL con el tipo esperado (Clase, ObjectProperty o DatatypeProperty): **0 problemas**. Los individuos `rst:Fonds`, `rst:Series` y `rst:File` existen en el OWL como `RecordSetType`.
  - Script dinámico (anexo A.2), con 258 tripletas que cubren las 27 propiedades del mapeo:
    - 27 clases RiC-O y 61 predicados `rico:` distintos;
    - **0 términos inexistentes**;
    - **0 usos de una propiedad de objeto con un literal, o de una de dato con un nodo**;
    - **0 incompatibilidades de dominio o rango** (con cierre de `rdfs:subClassOf` y `owl:unionOf`).
  - Otros espacios emitidos, todos bien formados y existentes:
    - SKOS: `Concept`, `ConceptScheme`, `inScheme`, `hasTopConcept`, `prefLabel`, `broader`, `broadMatch`, `exactMatch`;
    - RDFS: `label`, `seeAlso`;
    - OWL: `sameAs`.
  - Objetos externos: Lexvo `http://lexvo.org/id/iso639-3/{spa,lat}`, PRONOM `https://www.nationalarchives.gov.uk/PRONOM/fmt/…` y Wikidata (ver O-30).
  - **No** se emiten términos `dcterms:`, `premis:` ni `prov:` en el RDF. El PREMIS de `app/servicios/paquete.py:56-58` es XML, no RDF. Las cadenas «rico:…» de `paquete.py:398,406,410,413,626` son etiquetas JSON del paquete y nombran términos existentes.
  - `conformidad_rico.reporte` sobre ese mismo grafo: `owl.conforme=True`, `mapeo.problemas=[]`, `shacl.conforme=True` (41 formas).
- Prueba automatizada:
  - `tests/test_ric_o.py::test_todo_el_mapeo_es_conforme_al_owl_oficial`;
  - `::test_la_verificacion_detecta_un_nombre_inventado`;
  - `tests/test_exportacion_rico.py::test_la_exportacion_es_conforme_al_owl_y_al_perfil_shacl`;
  - `::test_la_verificacion_owl_es_independiente_del_mapeo`.
- Razonamiento: la disciplina del anexo («nunca inventar un nombre de propiedad») se cumple en todo lo que sale como RDF. Además lo protege una prueba que reconstruye el dominio y el rango desde el OWL, de modo que un nombre inventado haría fallar la prueba. Hay dos matices:
  - `verificar_contra_owl` no comprueba el dominio de las propiedades de dato (`ric_o.py:434-441` solo verifica la existencia y el código RiC-CM). Lo compensa `conformidad_rico.verificar_owl` (`:172-174`), que sí lo hace sobre el grafo real.
  - Tres términos se escriben fuera del mapeo único (O-12), aunque existen.

### O-28 · Nombres RiC-O inexistentes u obsoletos en la capa de presentación (API, hoja de cálculo, interfaz)
- Rama: RiC-O
- Módulo(s): instrumentos, descripcion, vocabularios
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/grafo.py:285-286`: `uri_rico("forma_documental")` devuelve **`"rico:hasOrHadDocumentaryFormType"`, que no existe en RiC-O 1.1**. Script estático: «NO EXISTE EN OWL». La propiedad real, que usa la exportación, es `rico:hasDocumentaryFormType` (`ric_o.py:241`). El valor viaja:
    - en la API del grafo (`grafo.py:293` → `uri_rico` de cada arista);
    - en el título emergente de la arista en la interfaz (`frontend/src/components/Grafo.tsx:407`);
    - en la columna «Propiedad RiC-O» de la hoja Excel descargable (`grafo.py:530-532`).
  - `frontend/src/components/FichaAutoridad.tsx:878`: muestra `rico:hasOrHadRuleType` como propiedad del tipo de instrumento. Existe en el OWL, pero la exportación usa `hasOrHadMandateType` (`ric_o.py:243`). La corrección 2 del anexo de verificación quedó sin aplicar en la interfaz.
  - `frontend/src/components/FichaAutoridad.tsx:645`: promete `rico:technicalCharacteristics` (ver O-19).
  - `app/models/enums.py:137-155` (`URI_RICO`): un diccionario paralelo y desactualizado que `app/servicios/descripcion.py:847` todavía usa para `uri_rico`. No tiene `has_or_had_holder`, `has_or_had_constituent`, `precedes_or_preceded`, `has_direct_subevent`, etc., y para esos códigos devuelve `None`. Contradice la regla de `ric_o.py:4-7` de una única fuente.
  - Ninguna de estas cadenas entra en el RDF exportado (O-27).
- Prueba automatizada: ninguna encontrada que compare las etiquetas `uri_rico` de la API o de la interfaz con el OWL. `tests/test_auditoria_v7.py::test_cada_decision_muestra_su_clase_y_su_propiedad_de_ric_o` cubre solo el panel de decisiones.
- Razonamiento: la sección 7 del prompt prohíbe inventar nombres en la exportación RDF, y allí no ocurre. Pero la API y la hoja Excel se presentan como «Propiedad RiC-O» y muestran un nombre inexistente. Un evaluador que copie ese IRI obtendría un término falso. Es una inconsistencia nueva en el sentido de la sección 8.
- Acción recomendada:
  - Hacer que `grafo.uri_rico("forma_documental")` lea `ric_o.APOYO["forma_documental"][0]`.
  - Cambiar `FichaAutoridad.tsx:878` a `rico:hasOrHadMandateType`.
  - Eliminar `URI_RICO` y `INVERSA_RICO` de `enums.py` y derivarlos de `ric_o.PROPIEDADES`.
  - Ampliar `estatico.py` (o una prueba equivalente) para escanear las cadenas «rico:» de app/ y frontend/ contra el OWL.

### O-29 · La fecha de expedición de un mandato se descarta en la exportación
- Rama: RiC-O
- Módulo(s): descripcion, instrumentos
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/descripcion.py:402-406`: la publicación crea la fila fecha → mandato `is_creation_date_of`.
  - `app/servicios/autoridad.py:650` la lee para la ficha.
  - `app/servicios/ric_o.py:194-195` limita el destino de `isCreationDateOf` a RECURSOS + Instantiation, que es lo que dice el OWL: `hasCreationDate` tiene dominio Instantiation o RecordResource.
  - `exportacion_rico.py:249-250` la omite y la cuenta. En el script dinámico: `omitidas: {'rico:isCreationDateOf entre clases que su dominio o rango no admiten': 1}`.
- Prueba automatizada: ninguna encontrada.
- Razonamiento: el sistema no inventa nada, porque el filtro de dominio funciona. Pero un dato descriptivo central de un mandato (la fecha de expedición) nunca llega al RDF, aunque RiC-O tiene propiedades válidas para una Rule: `isAssociatedWithDate` y `hasBeginningDate`, ambas con dominio `Thing`. Además, la fila de la base de datos guarda un código cuyo rango RiC-O no admite el destino, así que el código interno no es fiel a la propiedad que nombra.
- Acción recomendada: guardar la expedición con un código cuyo dominio admita `Mandate` (`is_date_associated_with`, o `is_beginning_date_of`, ya en el catálogo y existente en el OWL) y mapearlo; añadir una prueba.

### O-30 · owl:sameAs hacia autoridades externas con IRIs no canónicos; etiqueta de idioma no canónica
- Rama: RiC-O (con ISAAR-CPF)
- Módulo(s): vocabularios, instrumentos
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/autoridad.py:228-233` (`URI_EXTERNA`: `https://www.wikidata.org/entity/{}`, `https://viaf.org/viaf/{}`, `https://id.loc.gov/authorities/names/{}`, `https://isni.org/isni/{}`).
  - `app/servicios/exportacion_rico.py:423-425` emite `owl:sameAs` hacia esas URI.
  - `tests/test_exportacion_rico.py:140` fija la forma `https://www.wikidata.org/entity/Q1000000`.
  - Las URI de entidad que publican Wikidata (`http://www.wikidata.org/entity/Q…`), VIAF (`http://viaf.org/viaf/…`) e id.loc.gov (`http://id.loc.gov/authorities/names/…`) usan `http`. Para ISNI no se verificó la forma canónica actual.
  - `NombreEntidad.idioma` (`app/models/descripcion.py:285`, `String(12)`, texto libre) se emite como etiqueta de idioma del literal (`exportacion_rico.py:408`). Con «spa» (ISO 639-3) produce `@spa`, que BCP 47 considera no canónico frente a `@es`.
- Prueba automatizada: `tests/test_exportacion_rico.py::test_contexto_agentes_lugar_funciones_actividad_mandato`, que fija la forma con https.
- Razonamiento: en RDF, `http://…/Q42` y `https://…/Q42` son nodos distintos. El `owl:sameAs` no enlaza con el grafo de Wikidata ni con VIAF, así que el propósito de interoperabilidad queda neutralizado aunque la tripleta sea sintácticamente válida. Esto es conocimiento externo al repositorio y conviene confirmarlo con cada autoridad.
- Acción recomendada: usar las URI de entidad canónicas de cada autoridad. Restringir `NombreEntidad.idioma` a una lista controlada y convertirla a BCP 47 al serializar.

---

## D. Pruebas, SHACL y catálogo

### O-31 · Ejecución de las pruebas existentes y alcance real
- Rama: RiC-O
- Módulo(s): instrumentos
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - Comando pedido: `cd /home/user/Tesis && source /home/user/venv-ricora/bin/activate && unset DATABASE_URL && python -m pytest -q -p no:cacheprovider tests/test_ric_o.py tests/test_exportacion_rico.py`.
    - 1.ª ejecución: **25 errors**, `psycopg2.OperationalError: connection … port 5432 failed: Connection refused`. El servidor PostgreSQL local estaba detenido y `tests/conftest.py:11` exige PostgreSQL, incluso para las 7 pruebas de `test_ric_o.py` que no usan la base de datos, por la fixture `autouse` de `tests/conftest.py:52-60`.
    - Tras `service postgresql start`: **25 passed, 4 warnings in 13.07s**.
  - Cobertura: la fixture `fondo_rico` (`tests/test_exportacion_rico.py:31-89`) solo ejercita en RDF 11 de las 27 propiedades del mapeo:
    - `documents`, `hasActivityType`, `performsOrPerformed`, `regulatesOrRegulated`, `isOrWasLocationOf`;
    - `includesOrIncluded`, `hasOrHadConstituent`, `hasCreator`, `hasAddressee`, `hasOrHadSubject`, `hasOrHadInstantiation`;
    - más `isCreationDateOf` y el hito.
  - No se exportan en ninguna prueba: `hasSuccessor`, `hasOrHadSubordinate`, `isAgentAssociatedWithAgent`, `authorizes`, `issuedBy`, `migratedInto`, `hasDirectSubevent`, `containsOrContained`, `precedesOrPreceded`, `hasOrHadHolder`, `isRelatedTo`, `occupiesOrOccupied`, `hasSender`, `isDateAssociatedWith` ni `affectsOrAffected` más allá del hito. Solo las cubre la verificación del mapeo. El script dinámico de esta auditoría demuestra que hoy salen bien.
  - `occupies_or_occupied` está mapeado (`ric_o.py:179`), pero ningún servicio crea esa fila (búsqueda en app/: solo `ric_o.py:179` e `instrumentos.py:571`). Es una capacidad que existe en el mapeo y no en la operación.
- Prueba automatizada: las 25 citadas.
- Razonamiento: las pruebas pasan y son de buena calidad (detectan un nombre inventado y un rango erróneo). Pero dependen de un servicio externo que no estaba en marcha, y la exportación de más de la mitad de las relaciones no tiene aserción propia.
- Acción recomendada:
  - Ampliar `fondo_rico` con un vínculo de cada tipo de `autoridad.VINCULOS` y con las filas de secuencia, custodio y migración. El anexo A.2 sirve de plantilla.
  - Separar `test_ric_o.py` de la fixture de base de datos.
  - Documentar el requisito de PostgreSQL en la ejecución de pruebas.

### O-32 · Validación SHACL de la exportación: existe, qué cubre y cuándo corre
- Rama: RiC-O
- Módulo(s): instrumentos
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - Perfil escrito a mano: `app/recursos/ric-o/perfil-ricora.shacl.ttl:18-120`. Cubre RecordResource, RecordSet, Record, RecordPart, Instantiation, Agent, Mechanism, Place, Activity, ActivityType, Mandate, Date y Language.
  - Formas generadas desde el mapeo, una por propiedad: `app/servicios/conformidad_rico.py:53-65`, con `targetSubjectsOf` y `sh:or` de `sh:class` en origen y destino.
  - Patrón EDTF generado desde `fechas.py`: `conformidad_rico.py:43-52`.
  - Motor: `pyshacl.validate(..., ont_graph=jerarquia(), inference="none")` en `conformidad_rico.py:96-114`. `jerarquia()` (`:81-93`) aporta `subClassOf` y los individuos `rst:`.
  - Total: 41 formas. Resultado sobre el grafo completo del script dinámico: conforme.
  - Ejecución: solo bajo demanda en `GET /api/exportacion/conformidad` (`app/routers/exportacion.py:61-73`) y en pruebas. La descarga `GET /api/exportacion/rdf` (`:46-58`), la resolución de URI (`:141-169`) y la exportación de fragmento del grafo (`app/routers/grafo.py:100-122`) **no validan** antes de servir.
  - Huecos:
    - la forma `pr:Mechanism` nunca tiene focos (O-19);
    - no hay formas para `rico:Event` (hitos), `rico:Identifier`, `AgentName`/`PlaceName` (`textualValue` obligatorio), ni para el título de `Instantiation`;
    - las formas generadas no comprueban cardinalidades de las relaciones, salvo las del perfil manual;
    - la validación usa `inference="none"`, así que una clase que solo se pudiera inferir no se reconoce. Esto es correcto para un perfil cerrado.
- Prueba automatizada:
  - `tests/test_exportacion_rico.py::test_la_exportacion_es_conforme_al_owl_y_al_perfil_shacl`;
  - `::test_shacl_detecta_lo_que_no_cumple`, con 5 casos negativos (sin título, relación a clase ajena, EDTF inválido, idioma no ISO, parte suelta);
  - `::test_la_verificacion_owl_es_independiente_del_mapeo`.
- Razonamiento: la validación SHACL es real, se ejecutó y detecta errores (comprobado por las pruebas negativas). Pero es una herramienta de diagnóstico a demanda, no una barrera: un RDF no conforme se serviría igual. Su cobertura deja fuera varias clases que sí se emiten.
- Acción recomendada: añadir formas para Event, Identifier, AgentName y PlaceName. Retirar o activar `pr:Mechanism`. Considerar validar (o al menos registrar el resultado de `reporte`) en cada descarga completa.

### O-33 · Códigos del catálogo de relaciones sin mapeo RiC-O ni escritor
- Rama: RiC-O
- Módulo(s): descripcion, vocabularios
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia: `app/models/enums.py:72-…` (`CODIGO_RELACION_RIC`). Veinte códigos no están en `ric_o.PROPIEDADES`:
  - `has_author`, `has_accumulator`, `has_receiver`, `has_collector`;
  - `is_or_was_holder_of`, `is_or_was_manager_of`, `is_or_was_owner_of`, `is_or_was_controller_of`;
  - `has_or_had_subdivision`, `exists_or_existed_in`, `has_or_had_member`, `is_or_was_leader_of`;
  - `is_original_of`, `has_copy`, `has_or_had_derived_instantiation`, `is_or_was_expressed_by`;
  - `is_beginning_date_of`, `is_end_date_of`, `is_modification_date_of`, `is_or_was_jurisdiction_of`.

  Los 20 existen en el OWL al pasarlos a camelCase (comprobado con rdflib). Ningún servicio los escribe: búsqueda de cada código entre comillas en app/, excluido `enums.py`. Solo `app/servicios/resumen_fondo.py:20` lee `has_author` y `has_accumulator`. Si se usaran, `exportacion_rico.py:246-248` los omitiría como «sin propiedad en RiC-O», lo cual sería falso.
- Prueba automatizada: `tests/test_ric_o.py::test_cada_codigo_mapeado_existe_en_el_catalogo_del_sistema` (solo cubre la dirección mapeo → catálogo).
- Razonamiento: no hay invención. Hay un catálogo más amplio que el mapeo, con una dirección duplicada (`is_or_was_holder_of` frente a `has_or_had_holder`). El contador de omisiones daría un motivo erróneo.
- Acción recomendada: mapear los códigos que se vayan a usar (`hasOrHadMember` y `isOrWasLeaderOf` sostendrían las relaciones de membresía de ISAAR) o retirarlos del enum. Distinguir en `omitidas` entre «sin mapeo en el sistema» y «sin propiedad en RiC-O».

---

## Tabla resumen

| ID | Título | Clasificación |
|---|---|---|
| O-01 | documents / documentedBy | Implementado y conforme |
| O-02 | hasOrHadPart / includesOrIncluded / hasOrHadConstituent | Implementado y conforme |
| O-03 | hasOrHadInstantiation | Implementado y conforme |
| O-04 | hasCreator | Implementado y conforme |
| O-05 | performsOrPerformed | Implementado y conforme |
| O-06 | authorizes / authorizedBy (Mandate → Agent) | Implementado y conforme |
| O-07 | hasSuccessor | Implementado y conforme |
| O-08 | hasOrHadSubordinate | Implementado y conforme |
| O-09 | migratedInto | Implementado y conforme |
| O-10 | hasOrHadIdentifier | Implementado y conforme |
| O-11 | hasActivityType (+ SKOS) | Implementado y conforme |
| O-12 | expressedDate / normalizedDateValue / dateQualifier | Implementado pero incompleto o no conforme |
| O-13 | hasDirectSubevent | Implementado y conforme |
| O-14 | P1 performsOrPerformed dominio/rango | Implementado y conforme |
| O-15 | P2 sin subclases de Date | Implementado y conforme |
| O-16 | P3 isAgentAssociatedWithAgent | Implementado y conforme |
| O-17 | P4 Group instanciable | Implementado y conforme |
| O-18 | P5 hito → affectsOrAffected | Implementado y conforme |
| O-19 | P6 technicalCharacteristics del mecanismo (prometido, no exportado) | Implementado pero incompleto o no conforme |
| O-20 | P7 mandato que crea agente o competencia | Implementado y conforme |
| O-21 | P8 función ↔ serie con isRelatedTo | Implementado y conforme |
| O-22 | P9 containsOrContained / hasOrHadPlaceType | Implementado y conforme |
| O-23 | P10 precedesOrPreceded | Implementado y conforme |
| O-24 | P11 hasOrHadHolder | Implementado y conforme |
| O-25 | P12 jerarquía normativa con regulatesOrRegulated | Implementado y conforme |
| O-26 | P13 idioma y condiciones (AllMembersWithLanguage sobreafirma) | Implementado pero incompleto o no conforme |
| O-27 | Anti-invención en el RDF emitido (0 términos inexistentes) | Implementado y conforme |
| O-28 | Nombres RiC-O inexistentes u obsoletos en API, Excel e interfaz | Implementado pero incompleto o no conforme |
| O-29 | Fecha de expedición del mandato descartada en RDF | Implementado pero incompleto o no conforme |
| O-30 | owl:sameAs con IRIs no canónicos; etiqueta de idioma | Implementado pero incompleto o no conforme |
| O-31 | Pruebas: pasan (25), dependen de PostgreSQL, cobertura RDF parcial | Implementado pero incompleto o no conforme |
| O-32 | SHACL: real, a demanda, con huecos | Implementado pero incompleto o no conforme |
| O-33 | Códigos del catálogo sin mapeo ni escritor | Implementado pero incompleto o no conforme |

---

## Anexo A — Scripts usados y su salida

### A.1 Script estático `rico/estatico.py`

```python
"""Comprobación estática anti-invención: todo término rico:/skos: que el código
puede emitir o mostrar, contra el OWL oficial RiC-O 1.1 (rdflib)."""
import re, sys, pathlib
sys.path.insert(0, "/home/user/Tesis")
from rdflib import Graph, RDF, RDFS, OWL, URIRef
from rdflib.collection import Collection
from app.servicios import ric_o

RAIZ = pathlib.Path("/home/user/Tesis")
R = ric_o.RICO
g = Graph(); g.parse(ric_o.OWL_ARCHIVO)

def tipo(n):
    u = URIRef(R + n)
    t = set(g.objects(u, RDF.type))
    if OWL.Class in t: return "Clase"
    if OWL.ObjectProperty in t: return "Objeto"
    if OWL.DatatypeProperty in t: return "Dato"
    if OWL.NamedIndividual in t: return "Individuo"
    return None

# 1. Términos del mapeo único, con el papel que el código les da.
uso = {}  # nombre -> set(papel esperado)
def add(n, papel, donde): uso.setdefault(n, set()).add((papel, donde))
for d in (ric_o.CLASE_NIVEL, ric_o.CLASE_AGENTE, ric_o.CLASE_VOCABULARIO, ric_o.CLASE_NODO):
    for v in d.values(): add(v, "Clase", "ric_o.CLASE_*")
for k, v in ric_o.SUPERCLASES.items():
    add(k, "Clase", "ric_o.SUPERCLASES")
    for s in v:
        if s not in ("Thing", "Concept"): add(s, "Clase", "ric_o.SUPERCLASES")
for c, p in ric_o.PROPIEDADES.items():
    add(p.rico, "Objeto", f"PROPIEDADES[{c}]")
    if p.inversa: add(p.inversa, "Objeto", f"PROPIEDADES[{c}].inversa")
    for cl in p.origen + p.destino:
        if cl != "Thing": add(cl, "Clase", f"PROPIEDADES[{c}] origen/destino")
for k, (n, _) in ric_o.ATRIBUTOS.items(): add(n, "Dato", f"ATRIBUTOS[{k}]")
for k, (n, dom, rango) in ric_o.APOYO.items():
    add(n, "Objeto", f"APOYO[{k}]"); add(rango, "Clase", f"APOYO[{k}] rango")
    for cl in dom:
        if cl != "Thing": add(cl, "Clase", f"APOYO[{k}] dominio")

# 2. Términos escritos fuera del mapeo (regex sobre el código y el perfil SHACL).
patrones = [r"RICO\.([A-Za-z]+)", r"RICO\[\s*[\"']([A-Za-z]+)[\"']\s*\]", r"rico:([A-Za-z]+)"]
literales = {}
archivos = [*RAIZ.glob("app/**/*.py"), *RAIZ.glob("frontend/src/**/*.ts"), *RAIZ.glob("frontend/src/**/*.tsx"),
            *RAIZ.glob("app/recursos/ric-o/*.ttl")]
for f in archivos:
    for i, linea in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        for pat in patrones:
            for m in re.finditer(pat, linea):
                literales.setdefault(m.group(1), []).append(f"{f.relative_to(RAIZ)}:{i}")

print("== 1. Mapeo único (ric_o.py) ==")
malos = 0
for n in sorted(uso):
    real = tipo(n)
    esperados = {p for p, _ in uso[n]}
    estado = "OK" if real in esperados and len(esperados) == 1 else "PROBLEMA"
    if estado != "OK":
        malos += 1
        print(f"  {estado}: {n}: usado como {sorted(esperados)}, OWL={real}  ({sorted(d for _, d in uso[n])[:3]})")
print(f"  {len(uso)} términos del mapeo; {malos} problemas")

print("== 2. Términos rico: escritos en el código, la interfaz y el perfil SHACL ==")
malos = 0
for n in sorted(literales):
    real = tipo(n)
    if real is None:
        malos += 1
        print(f"  NO EXISTE EN OWL: rico:{n}  en {literales[n]}")
print(f"  {len(literales)} términos distintos; {malos} inexistentes")
for n in sorted(literales):
    print(f"    rico:{n} [{tipo(n)}] {literales[n][:4]}{' …' if len(literales[n])>4 else ''}")

print("== 3. Individuos de recordSetTypes ==")
for k in sorted(set(ric_o.TIPO_AGRUPACION_OFICIAL.values()) | set(ric_o.TIPO_AGRUPACION_PROPIO.values())):
    u = URIRef(ric_o.RST + k)
    print(f"  rst:{k}: tipos={sorted(str(t).split('#')[-1] for t in g.objects(u, RDF.type))}")

print("== 4. Términos SKOS usados ==")
SKOS_CORE = {"Concept","ConceptScheme","Collection","OrderedCollection","inScheme","hasTopConcept","topConceptOf",
 "altLabel","hiddenLabel","prefLabel","notation","changeNote","definition","editorialNote","example","historyNote",
 "note","scopeNote","broader","broaderTransitive","narrower","narrowerTransitive","related","semanticRelation",
 "member","memberList","mappingRelation","broadMatch","narrowMatch","relatedMatch","exactMatch","closeMatch"}
sk = {}
for f in archivos:
    for i, linea in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        for m in re.finditer(r"SKOS(?:\.([A-Za-z]+)|\[\s*ric_o\.(SKOS_[A-Z]+)\s*\])|skos:([A-Za-z]+)", linea):
            n = m.group(1) or (getattr(ric_o, m.group(2)) if m.group(2) else m.group(3))
            sk.setdefault(n, []).append(f"{f.relative_to(RAIZ)}:{i}")
for n in sorted(sk):
    print(f"  skos:{n}: {'OK' if n in SKOS_CORE else 'NO EXISTE EN SKOS'} {sk[n][:3]}")
```

Ejecución: `cd /home/user/Tesis && source /home/user/venv-ricora/bin/activate && python <scratchpad>/auditoria/rico/estatico.py`. Salida (la entrada `rico:get` es un falso positivo del regex: es `URI_RICO.get(` en `grafo.py:288` y `descripcion.py:847`):

```text
== 1. Mapeo único (ric_o.py) ==
  111 términos del mapeo; 0 problemas
== 2. Términos rico: escritos en el código, la interfaz y el perfil SHACL ==
  NO EXISTE EN OWL: rico:get  en ['app/servicios/grafo.py:288', 'app/servicios/descripcion.py:847']
  NO EXISTE EN OWL: rico:hasOrHadDocumentaryFormType  en ['app/servicios/grafo.py:286']
  77 términos distintos; 2 inexistentes
    rico:Activity [Clase] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:86']
    rico:ActivityType [Clase] ['app/models/descripcion.py:28', 'frontend/src/lib/vocabulario.ts:55', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:89', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:93'] …
    rico:Agent [Clase] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:63']
    rico:AgentName [Clase] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:67']
    rico:CorporateBody [Clase] ['frontend/src/lib/vocabulario.ts:61']
    rico:Date [Clase] ['app/servicios/ric_o.py:316', 'app/servicios/exportacion_rico.py:261', 'app/servicios/exportacion_rico.py:441', 'app/servicios/conformidad_rico.py:45'] …
    rico:DocumentaryFormType [Clase] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:41']
    rico:Event [Clase] ['app/routers/vocabulario.py:293', 'app/servicios/autoridad.py:242', 'app/servicios/autoridad.py:277', 'app/servicios/exportacion_rico.py:426'] …
    rico:Family [Clase] ['frontend/src/lib/vocabulario.ts:61']
    rico:Group [Clase] ['app/servicios/ric_o.py:74', 'app/models/descripcion.py:33', 'frontend/src/lib/vocabulario.ts:61']
    rico:Identifier [Clase] ['app/servicios/exportacion_rico.py:418']
    rico:IdentifierType [Clase] ['app/models/descripcion.py:41']
    rico:Instantiation [Clase] ['app/servicios/exportacion_rico.py:456', 'app/servicios/paquete.py:398', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:54']
    rico:Language [Clase] ['app/servicios/ric_o.py:318', 'app/servicios/exportacion_rico.py:301', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:33', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:43'] …
    rico:LegalStatus [Clase] ['app/models/descripcion.py:35', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:68']
    rico:Mandate [Clase] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:101']
    rico:MandateType [Clase] ['app/models/descripcion.py:48', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:103']
    rico:Mechanism [Clase] ['frontend/src/lib/vocabulario.ts:62', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:71']
    rico:Person [Clase] ['frontend/src/lib/vocabulario.ts:61']
    rico:Place [Clase] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:77']
    rico:PlaceName [Clase] ['app/models/descripcion.py:276', 'frontend/src/components/FichaAutoridad.tsx:777']
    rico:PlaceType [Clase] ['app/models/descripcion.py:37', 'app/models/descripcion.py:115', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:83']
    rico:Position [Clase] ['frontend/src/lib/vocabulario.ts:62']
    rico:Record [Clase] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:36']
    rico:RecordPart [Clase] ['frontend/src/components/DescripcionV3.tsx:253', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:46']
    rico:RecordResource [Clase] ['app/servicios/ric_o.py:320', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:19']
    rico:RecordSet [Clase] ['app/servicios/paquete.py:626', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:28']
    rico:RecordSetType [Clase] ['app/servicios/exportacion_rico.py:317', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:30']
    rico:affectsOrAffected [Objeto] ['frontend/src/components/FichaAutoridad.tsx:597']
    rico:authorizes [Objeto] ['app/models/enums.py:149']
    rico:documents [Objeto] ['app/models/enums.py:144']
    rico:expressedDate [Dato] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:109']
    rico:followsOrFollowed [Objeto] ['app/servicios/descripcion.py:815']
    rico:geographicalCoordinates [Dato] ['frontend/src/components/FichaAutoridad.tsx:755', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:80']
    rico:get [None] ['app/servicios/grafo.py:288', 'app/servicios/descripcion.py:847']
    rico:hasActivityType [Objeto] ['app/servicios/descripcion.py:15', 'app/models/enums.py:119', 'app/models/enums.py:146', 'frontend/src/components/FichaAutoridad.tsx:850'] …
    rico:hasAddressee [Objeto] ['app/models/enums.py:140']
    rico:hasBeginningDate [Objeto] ['app/servicios/exportacion_rico.py:274']
    rico:hasCreationDate [Objeto] ['app/servicios/exportacion_rico.py:348']
    rico:hasCreator [Objeto] ['app/servicios/ric_o.py:333', 'app/models/enums.py:138']
    rico:hasDirectSubevent [Objeto] ['app/servicios/autoridad.py:340', 'app/servicios/descripcion.py:473', 'app/models/enums.py:129', 'frontend/src/components/FichaAutoridad.tsx:863']
    rico:hasDocumentaryFormType [Objeto] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:41']
    rico:hasOrHadAgentName [Objeto] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:67']
    rico:hasOrHadAllMembersWithLanguage [Objeto] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:33']
    rico:hasOrHadConstituent [Objeto] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:48']
    rico:hasOrHadDocumentaryFormType [None] ['app/servicios/grafo.py:286']
    rico:hasOrHadIdentifier [Objeto] ['app/models/descripcion.py:41']
    rico:hasOrHadInstantiation [Objeto] ['app/servicios/paquete.py:406', 'app/models/enums.py:143', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:57']
    rico:hasOrHadLanguage [Objeto] ['app/models/recurso_documental.py:50', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:43']
    rico:hasOrHadLegalStatus [Objeto] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:68']
    rico:hasOrHadMandateType [Objeto] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:103']
    rico:hasOrHadPlaceType [Objeto] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:83']
    rico:hasOrHadRuleType [Objeto] ['frontend/src/components/FichaAutoridad.tsx:878']
    rico:hasOrHadSubject [Objeto] ['app/models/enums.py:145']
    rico:hasOrHadSubordinate [Objeto] ['app/models/enums.py:150']
    rico:hasRecordSetType [Objeto] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:30']
    rico:hasSender [Objeto] ['app/models/enums.py:139']
    rico:hasSuccessor [Objeto] ['app/models/enums.py:151']
    rico:identifier [Dato] ['app/recursos/ric-o/perfil-ricora.shacl.ttl:24', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:55', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:119']
    rico:includesOrIncluded [Objeto] ['app/models/enums.py:141', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:38']
    rico:isAgentAssociatedWithAgent [Objeto] ['app/models/enums.py:152', 'app/models/enums.py:162']
    rico:isAssociatedWithDate [Objeto] ['app/servicios/exportacion_rico.py:284']
    rico:isCreationDateOf [Objeto] ['app/models/enums.py:142']
    rico:isDateAssociatedWith [Objeto] ['app/models/enums.py:153']
    rico:isDirectSubeventOf [Objeto] ['frontend/src/components/DescripcionV3.tsx:142']
    rico:isOrWasConstituentOf [Objeto] ['frontend/src/pages/Registro.tsx:251']
    rico:isOrWasSubordinateTo [Objeto] ['app/models/enums.py:160']
    rico:isSuccessorOf [Objeto] ['app/models/enums.py:161']
    rico:migratedInto [Objeto] ['app/servicios/paquete.py:410', 'app/servicios/paquete.py:413', 'app/models/enums.py:154', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:58']
    rico:name [Dato] ['app/servicios/exportacion_rico.py:365', 'app/servicios/exportacion_rico.py:366', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:65', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:78'] …
    rico:normalizedDateValue [Dato] ['app/servicios/conformidad_rico.py:48', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:109', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:112']
    rico:performsOrPerformed [Objeto] ['app/models/enums.py:147']
    rico:precedesOrPreceded [Objeto] ['app/servicios/descripcion.py:814', 'frontend/src/components/DescripcionV3.tsx:101']
    rico:regulatesOrRegulated [Objeto] ['app/models/enums.py:148']
    rico:structure [Dato] ['app/servicios/ric_o.py:251']
    rico:technicalCharacteristics [Dato] ['frontend/src/components/FichaAutoridad.tsx:645', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:73']
    rico:title [Dato] ['app/servicios/ric_o.py:208', 'app/servicios/exportacion_rico.py:365', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:21', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:102']
== 3. Individuos de recordSetTypes ==
  rst:File: tipos=['Concept', 'NamedIndividual', 'RecordSetType']
  rst:Fonds: tipos=['Concept', 'NamedIndividual', 'RecordSetType']
  rst:Series: tipos=['Concept', 'NamedIndividual', 'RecordSetType']
== 4. Términos SKOS usados ==
  skos:Concept: OK ['app/servicios/ric_o.py:83', 'app/servicios/exportacion_rico.py:369', 'frontend/src/components/FichaAutoridad.tsx:820']
  skos:ConceptScheme: OK ['app/servicios/exportacion_rico.py:373', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:95']
  skos:broadMatch: OK ['app/servicios/ric_o.py:57', 'app/servicios/ric_o.py:68', 'app/servicios/exportacion_rico.py:318']
  skos:broader: OK ['app/routers/vocabulario.py:353', 'app/servicios/autoridad.py:553', 'app/servicios/autoridad.py:554']
  skos:exactMatch: OK ['app/servicios/exportacion_rico.py:307']
  skos:hasTopConcept: OK ['app/servicios/exportacion_rico.py:379']
  skos:inScheme: OK ['app/servicios/exportacion_rico.py:375', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:95']
  skos:narrower: OK ['app/servicios/autoridad.py:561', 'frontend/src/components/FichaAutoridad.tsx:806', 'frontend/src/pages/Vocabularios.tsx:25']
  skos:prefLabel: OK ['app/servicios/exportacion_rico.py:370', 'app/servicios/exportacion_rico.py:374', 'app/recursos/ric-o/perfil-ricora.shacl.ttl:94']
```

### A.2 Script dinámico `rico/test_auditoria_dinamica.py`

```python
"""Auditoría dinámica (solo lectura del repo): se arma un fondo con TODAS las
relaciones del mapeo, a través de los servicios reales (autoridad.vincular,
agregar_nombre, agregar_hito, preservación no), se exporta con
exportacion_rico.exportar y se comprueba cada tripleta contra el OWL con un
verificador propio (independiente de conformidad_rico)."""
import uuid
from collections import Counter

from rdflib import OWL, RDF, RDFS, Literal, URIRef, BNode
from rdflib.collection import Collection

from tests.conftest import *  # noqa: F401,F403  (fixtures db, admin, base_de_pruebas…)
from tests.test_exportacion_rico import fondo_rico, exportar  # noqa: F401
from tests.test_instrumentos import fondo_descrito, _recurso  # noqa: F401
from app.models.descripcion import Relacion, Fecha
from app.models.instanciacion import Instanciacion
from app.servicios import autoridad, conformidad_rico, ric_o, vocabulario, exportacion_rico

R = ric_o.RICO
SKOS_CORE = {"Concept", "ConceptScheme", "inScheme", "hasTopConcept", "prefLabel", "broader", "narrower",
             "broadMatch", "exactMatch", "closeMatch", "altLabel", "notation", "topConceptOf", "related"}


def _crear(db, fondo, clase, nombre, subtipo=None):
    return vocabulario.crear(db, fondo_id=fondo.id, clase=clase, nombre=nombre, subtipo=subtipo, origen="persona",
                             confianza=None, motor=None, usuario_id=None)


def _owl_decl(g, nombre):
    u = URIRef(R + nombre)
    t = set(g.objects(u, RDF.type))
    kind = "objeto" if OWL.ObjectProperty in t else "dato" if OWL.DatatypeProperty in t else None

    def cl(n):
        if isinstance(n, URIRef):
            return {str(n).split("#")[-1]}
        s = set()
        for lst in g.objects(n, OWL.unionOf):
            s |= {str(x).split("#")[-1] for x in Collection(g, lst)}
        return s
    dom = set().union(*[cl(d) for d in g.objects(u, RDFS.domain)]) if list(g.objects(u, RDFS.domain)) else set()
    ran = set().union(*[cl(d) for d in g.objects(u, RDFS.range)]) if list(g.objects(u, RDFS.range)) else set()
    return kind, dom, ran


def _ancestros(g, c):
    vistos, pend = {c}, [URIRef(R + c)]
    while pend:
        a = pend.pop()
        for s in g.objects(a, RDFS.subClassOf):
            if isinstance(s, URIRef):
                n = str(s).split("#")[-1]
                if n not in vistos:
                    vistos.add(n); pend.append(s)
    return vistos | {"Thing"}


def test_auditoria(db, fondo_rico, admin):
    f = fondo_rico
    fondo = f["fondo"]
    g_owl = ric_o._owl()
    # --- contexto adicional por los servicios reales -----------------------------------
    persona = _crear(db, fondo, "agente", "Pedro Pérez", "persona")
    grupo = _crear(db, fondo, "agente", "Junta de vecinos", "grupo")
    concejo = _crear(db, fondo, "agente", "Concejo Municipal", "entidad_corporativa")
    familia = _crear(db, fondo, "agente", "Familia Suárez", "familia")
    ley = _crear(db, fondo, "mandato", "Ley 4 de 1913", "ley")
    sub = _crear(db, fondo, "actividad", "Revisión de permisos")
    boyaca = db.scalar(__import__("sqlalchemy").select(vocabulario.EntidadVocabulario).where(
        vocabulario.EntidadVocabulario.nombre == "Boyacá", vocabulario.EntidadVocabulario.fondo_id == fondo.id))
    db.flush()
    alc, gob = f["alcaldia"], db.get(vocabulario.EntidadVocabulario,
                                     next(r.destino_id for r in db.query(Relacion).filter_by(codigo_ric="has_addressee")))
    hechos = []
    for tipo, desde, con_tipo, con in (
            ("subordinado", alc, "entidad_vocabulario", grupo),
            ("sucesor", concejo, "entidad_vocabulario", alc),
            ("asociado", persona, "entidad_vocabulario", familia),
            ("lugar_agente", alc, "entidad_vocabulario", f["tunja"]),     # declarado desde el agente (destino)
            ("lugar_superior", f["tunja"], "entidad_vocabulario", boyaca),
            ("actividad_mayor", sub, "entidad_vocabulario", f["actividad"]),
            ("ejercida_por", sub, "entidad_vocabulario", concejo),
            ("mandato_actividad", sub, "entidad_vocabulario", ley),
            ("mandato_superior", f["acuerdo"], "entidad_vocabulario", ley),
            ("creado_por", alc, "entidad_vocabulario", ley),
            ("competencia_creada_por", f["funcion"], "entidad_vocabulario", ley),
            ("expedido_por", ley, "entidad_vocabulario", concejo),
            ("serie_producida", f["funcion"], "recurso_documental", f["serie"].id)):
        try:
            autoridad.vincular(db, tipo=tipo, desde=desde, con_tipo=con_tipo,
                               con_id=con if isinstance(con, uuid.UUID) else con.id, usuario_id=admin.id)
            hechos.append(tipo)
        except autoridad.ErrorAutoridad as exc:
            hechos.append(f"{tipo}: ERROR {exc}")
    # Filas de descripción que no pasan por vincular (mismo patrón que descripcion.py)
    inst2 = Instanciacion(id=uuid.uuid4(), fondo_id=fondo.id, nombre_original="Oficio_114_1948.pdfa.pdf", ruta="x/z.pdf",
                          tamano_bytes=11, estado="listo_para_descripcion", huella="b" * 64, formato_puid="fmt/354")
    db.add(inst2); db.flush()
    inst1 = db.query(Relacion).filter_by(codigo_ric="has_or_had_instantiation").first().destino_id
    fexp = Fecha(id=uuid.uuid4(), expresion="12 de marzo de 1946", edtf="1946-03-12", origen="persona")
    fact = Fecha(id=uuid.uuid4(), expresion="1948", edtf="1948", origen="persona")
    db.add_all([fexp, fact]); db.flush()
    for o_t, o, d_t, d, cod, rol in (
            ("recurso_documental", f["o114"].id, "entidad_vocabulario", persona.id, "has_sender", "remitente"),
            ("recurso_documental", f["exp49"].id, "entidad_vocabulario", grupo.id, "has_or_had_holder", "custodio"),
            ("recurso_documental", f["o114"].id, "recurso_documental", f["o115"].id, "precedes_or_preceded", None),
            ("recurso_documental", f["o114"].id, "recurso_documental", f["parte"].id, "has_or_had_constituent", None),
            ("instanciacion", inst1, "instanciacion", inst2.id, "migrated_into", None),
            ("entidad_vocabulario", persona.id, "entidad_vocabulario", gob.id, "occupies_or_occupied", None),
            ("fecha", fexp.id, "entidad_vocabulario", f["acuerdo"].id, "is_creation_date_of", None),  # expedición
            ("fecha", fact.id, "entidad_vocabulario", f["actividad"].id, "is_date_associated_with", None),
            ("recurso_documental", f["o115"].id, "entidad_vocabulario", f["acuerdo"].id, "has_or_had_subject", "mandato")):
        db.add(Relacion(origen_tipo=o_t, origen_id=o, destino_tipo=d_t, destino_id=d, tipo_relacion="asociacion",
                        codigo_ric=cod, rol=rol, origen="persona"))
    autoridad.agregar_nombre(db, f["tunja"], tipo="historica", nombre="Hunza", idioma="spa", regla=None,
                             vigencia_edtf="1500/1539", usuario_id=admin.id)
    db.commit()
    print("\nVínculos declarados por autoridad.vincular:", hechos)

    ex = exportar(db, f)
    g = ex.grafo
    print("Tripletas:", len(g), "| omitidas:", dict(ex.omitidas))

    # --- 1. inventario de términos emitidos ---------------------------------------------
    preds = Counter(str(p) for p in g.predicates())
    clases = Counter(str(o) for o in g.objects(None, RDF.type))
    print("\n== Predicados emitidos ==")
    for p, n in sorted(preds.items()):
        print(f"  {n:4} {p}")
    print("== Clases emitidas (rdf:type) ==")
    for c, n in sorted(clases.items()):
        print(f"  {n:4} {c}")

    # --- 2. verificación independiente contra el OWL ------------------------------------
    problemas = set()
    def clases_de(n):
        s = {str(t)[len(R):] for t in g.objects(n, RDF.type) if str(t).startswith(R)}
        if not s and isinstance(n, URIRef):
            s = {str(t)[len(R):] for t in g_owl.objects(n, RDF.type) if str(t).startswith(R)}
        return s
    for c in clases:
        if c.startswith(R) and (URIRef(c), RDF.type, OWL.Class) not in g_owl:
            problemas.add(f"CLASE INEXISTENTE {c}")
        if c.startswith(ric_o.SKOS) and c[len(ric_o.SKOS):] not in SKOS_CORE:
            problemas.add(f"CLASE SKOS INEXISTENTE {c}")
    for s, p, o in g:
        ps = str(p)
        if ps.startswith(ric_o.SKOS):
            if ps[len(ric_o.SKOS):] not in SKOS_CORE:
                problemas.add(f"SKOS INEXISTENTE {ps}")
            continue
        if not ps.startswith(R):
            continue
        n = ps[len(R):]
        kind, dom, ran = _owl_decl(g_owl, n)
        if kind is None:
            problemas.add(f"PROPIEDAD INEXISTENTE rico:{n}"); continue
        if kind == "objeto" and isinstance(o, Literal):
            problemas.add(f"rico:{n} es de objeto y lleva literal")
        if kind == "dato" and not isinstance(o, Literal):
            problemas.add(f"rico:{n} es de dato y apunta a un nodo")
        cs = clases_de(s)
        if dom and not any(_ancestros(g_owl, c) & dom for c in cs):
            problemas.add(f"DOMINIO rico:{n}: sujeto {sorted(cs)} ∉ {sorted(dom)}")
        if kind == "objeto" and ran:
            co = clases_de(o)
            if not any(_ancestros(g_owl, c) & ran for c in co):
                problemas.add(f"RANGO rico:{n}: objeto {sorted(co)} ∉ {sorted(ran)}")
        if kind == "dato" and isinstance(o, Literal) and o.datatype and ran and "Literal" not in ran:
            problemas.add(f"TIPO DE DATO rico:{n}: {o.datatype} vs {ran}")
    print("\n== Problemas frente al OWL (verificador propio) ==")
    for x in sorted(problemas):
        print("  ", x)
    print("  total:", len(problemas))

    # --- 3. cobertura: cada código del mapeo, ¿sale en RDF? -----------------------------
    print("\n== Cobertura de PROPIEDADES en la exportación ==")
    for cod, p in sorted(ric_o.PROPIEDADES.items()):
        print(f"  {cod:32} rico:{p.rico:28} tripletas={preds.get(R + p.rico, 0)}")
    for clave, (nombre, _) in sorted(ric_o.ATRIBUTOS.items()):
        print(f"  ATRIBUTO {clave:23} rico:{nombre:28} tripletas={preds.get(R + nombre, 0)}")
    for clave, (nombre, _, _) in sorted(ric_o.APOYO.items()):
        print(f"  APOYO {clave:26} rico:{nombre:28} tripletas={preds.get(R + nombre, 0)}")

    # --- 4. otros espacios -----------------------------------------------------------------
    print("\n== IRIs de objeto fuera de la base del sistema y de rico/rst ==")
    externos = sorted({str(o) for o in g.objects() if isinstance(o, URIRef)
                       and not str(o).startswith((exportacion_rico.base(), R, ric_o.RST))})
    for e in externos:
        print("  ", e)
    print("== Literales con etiqueta de idioma ==", sorted({o.language for o in g.objects() if isinstance(o, Literal) and o.language}))

    # --- 5. conformidad del propio sistema (OWL + SHACL) --------------------------------
    rep = conformidad_rico.reporte(ex)
    print("\n== conformidad_rico.reporte ==")
    print("  conforme:", rep["conforme"], "| owl:", rep["owl"], "| mapeo:", rep["mapeo"])
    print("  shacl conforme:", rep["shacl"]["conforme"], "| formas:", rep["shacl"]["formas"])
    for r in rep["shacl"]["resultados"]:
        print("   ", r)
```

Ejecución (base de datos aparte para no interferir con `ricora_pruebas`): `cd /home/user/Tesis && source /home/user/venv-ricora/bin/activate && export DATABASE_URL=postgresql+psycopg2://ricora:ricora@localhost:5432/ricora_auditoria_rico && python -m pytest -q -s -p no:cacheprovider --rootdir=/home/user/Tesis <scratchpad>/auditoria/rico/test_auditoria_dinamica.py` → `1 passed`. Nota: la primera versión del script usó la vigencia `../1539`, que el sistema rechaza (`FechaInvalida: «../1539» no es un rango que este sistema admita`); se cambió a `1500/1539`. Salida (sin los mensajes de alembic):

```text
Vínculos declarados por autoridad.vincular: ['subordinado', 'sucesor', 'asociado', 'lugar_agente', 'lugar_superior', 'actividad_mayor', 'ejercida_por', 'mandato_actividad', 'mandato_superior', 'creado_por', 'competencia_creada_por', 'expedido_por', 'serie_producida']
Tripletas: 258 | omitidas: {'borradores sin publicar': 1, 'descripciones con acceso clasificado o reservado': 0, 'rico:isCreationDateOf entre clases que su dominio o rango no admiten': 1, 'estructura interna de un agente (sin propiedad en RiC-O)': 1, 'calendario distinto del gregoriano (sin propiedad en RiC-O)': 1}

== Predicados emitidos ==
    58 http://www.w3.org/1999/02/22-rdf-syntax-ns#type
    37 http://www.w3.org/2000/01/rdf-schema#label
     2 http://www.w3.org/2000/01/rdf-schema#seeAlso
     1 http://www.w3.org/2002/07/owl#sameAs
     2 http://www.w3.org/2004/02/skos/core#broadMatch
     1 http://www.w3.org/2004/02/skos/core#broader
     2 http://www.w3.org/2004/02/skos/core#exactMatch
     1 http://www.w3.org/2004/02/skos/core#hasTopConcept
     2 http://www.w3.org/2004/02/skos/core#inScheme
     5 http://www.w3.org/2004/02/skos/core#prefLabel
     1 https://www.ica.org/standards/RiC/ontology#affectsOrAffected
     1 https://www.ica.org/standards/RiC/ontology#authorizes
     1 https://www.ica.org/standards/RiC/ontology#conditionsOfAccess
     1 https://www.ica.org/standards/RiC/ontology#containsOrContained
     1 https://www.ica.org/standards/RiC/ontology#dateQualifier
     1 https://www.ica.org/standards/RiC/ontology#documents
    13 https://www.ica.org/standards/RiC/ontology#expressedDate
     1 https://www.ica.org/standards/RiC/ontology#geographicalCoordinates
     1 https://www.ica.org/standards/RiC/ontology#hasActivityType
     1 https://www.ica.org/standards/RiC/ontology#hasAddressee
     3 https://www.ica.org/standards/RiC/ontology#hasBeginningDate
     3 https://www.ica.org/standards/RiC/ontology#hasCreator
     1 https://www.ica.org/standards/RiC/ontology#hasDirectSubevent
     2 https://www.ica.org/standards/RiC/ontology#hasDocumentaryFormType
     2 https://www.ica.org/standards/RiC/ontology#hasEndDate
     1 https://www.ica.org/standards/RiC/ontology#hasIdentifierType
     1 https://www.ica.org/standards/RiC/ontology#hasOrHadAgentName
     1 https://www.ica.org/standards/RiC/ontology#hasOrHadConstituent
     1 https://www.ica.org/standards/RiC/ontology#hasOrHadHolder
     1 https://www.ica.org/standards/RiC/ontology#hasOrHadIdentifier
     1 https://www.ica.org/standards/RiC/ontology#hasOrHadInstantiation
     2 https://www.ica.org/standards/RiC/ontology#hasOrHadLanguage
     1 https://www.ica.org/standards/RiC/ontology#hasOrHadLegalStatus
     2 https://www.ica.org/standards/RiC/ontology#hasOrHadMandateType
     1 https://www.ica.org/standards/RiC/ontology#hasOrHadPlaceName
     1 https://www.ica.org/standards/RiC/ontology#hasOrHadPlaceType
     2 https://www.ica.org/standards/RiC/ontology#hasOrHadSubject
     1 https://www.ica.org/standards/RiC/ontology#hasOrHadSubordinate
     6 https://www.ica.org/standards/RiC/ontology#hasRecordSetType
     1 https://www.ica.org/standards/RiC/ontology#hasSender
     1 https://www.ica.org/standards/RiC/ontology#hasSuccessor
     1 https://www.ica.org/standards/RiC/ontology#history
     9 https://www.ica.org/standards/RiC/ontology#identifier
     7 https://www.ica.org/standards/RiC/ontology#includesOrIncluded
     2 https://www.ica.org/standards/RiC/ontology#instantiationExtent
     1 https://www.ica.org/standards/RiC/ontology#isAgentAssociatedWithAgent
     1 https://www.ica.org/standards/RiC/ontology#isAssociatedWithDate
     5 https://www.ica.org/standards/RiC/ontology#isCreationDateOf
     1 https://www.ica.org/standards/RiC/ontology#isDateAssociatedWith
     1 https://www.ica.org/standards/RiC/ontology#isOrWasLocationOf
     1 https://www.ica.org/standards/RiC/ontology#isRelatedTo
     1 https://www.ica.org/standards/RiC/ontology#issuedBy
     1 https://www.ica.org/standards/RiC/ontology#migratedInto
    24 https://www.ica.org/standards/RiC/ontology#name
     9 https://www.ica.org/standards/RiC/ontology#normalizedDateValue
     1 https://www.ica.org/standards/RiC/ontology#occupiesOrOccupied
     2 https://www.ica.org/standards/RiC/ontology#performsOrPerformed
     1 https://www.ica.org/standards/RiC/ontology#precedesOrPreceded
     4 https://www.ica.org/standards/RiC/ontology#regulatesOrRegulated
     2 https://www.ica.org/standards/RiC/ontology#scopeAndContent
     3 https://www.ica.org/standards/RiC/ontology#textualValue
    13 https://www.ica.org/standards/RiC/ontology#title
== Clases emitidas (rdf:type) ==
     4 http://www.w3.org/2004/02/skos/core#Concept
     1 http://www.w3.org/2004/02/skos/core#ConceptScheme
     2 https://www.ica.org/standards/RiC/ontology#Activity
     2 https://www.ica.org/standards/RiC/ontology#ActivityType
     1 https://www.ica.org/standards/RiC/ontology#AgentName
     2 https://www.ica.org/standards/RiC/ontology#CorporateBody
    13 https://www.ica.org/standards/RiC/ontology#Date
     2 https://www.ica.org/standards/RiC/ontology#DocumentaryFormType
     1 https://www.ica.org/standards/RiC/ontology#Event
     1 https://www.ica.org/standards/RiC/ontology#Family
     1 https://www.ica.org/standards/RiC/ontology#Group
     1 https://www.ica.org/standards/RiC/ontology#Identifier
     1 https://www.ica.org/standards/RiC/ontology#IdentifierType
     2 https://www.ica.org/standards/RiC/ontology#Instantiation
     2 https://www.ica.org/standards/RiC/ontology#Language
     1 https://www.ica.org/standards/RiC/ontology#LegalStatus
     2 https://www.ica.org/standards/RiC/ontology#Mandate
     2 https://www.ica.org/standards/RiC/ontology#MandateType
     1 https://www.ica.org/standards/RiC/ontology#Person
     2 https://www.ica.org/standards/RiC/ontology#Place
     1 https://www.ica.org/standards/RiC/ontology#PlaceName
     1 https://www.ica.org/standards/RiC/ontology#PlaceType
     1 https://www.ica.org/standards/RiC/ontology#Position
     2 https://www.ica.org/standards/RiC/ontology#Record
     1 https://www.ica.org/standards/RiC/ontology#RecordPart
     6 https://www.ica.org/standards/RiC/ontology#RecordSet
     2 https://www.ica.org/standards/RiC/ontology#RecordSetType

== Problemas frente al OWL (verificador propio) ==
  total: 0

== Cobertura de PROPIEDADES en la exportación ==
  affects_or_affected              rico:affectsOrAffected            tripletas=1
  authorizes                       rico:authorizes                   tripletas=1
  contains_or_contained            rico:containsOrContained          tripletas=1
  documents                        rico:documents                    tripletas=1
  has_activity_type                rico:hasActivityType              tripletas=1
  has_addressee                    rico:hasAddressee                 tripletas=1
  has_creator                      rico:hasCreator                   tripletas=3
  has_direct_subevent              rico:hasDirectSubevent            tripletas=1
  has_or_had_constituent           rico:hasOrHadConstituent          tripletas=1
  has_or_had_holder                rico:hasOrHadHolder               tripletas=1
  has_or_had_instantiation         rico:hasOrHadInstantiation        tripletas=1
  has_or_had_subject               rico:hasOrHadSubject              tripletas=2
  has_or_had_subordinate           rico:hasOrHadSubordinate          tripletas=1
  has_sender                       rico:hasSender                    tripletas=1
  has_successor                    rico:hasSuccessor                 tripletas=1
  includes_or_included             rico:includesOrIncluded           tripletas=7
  is_agent_associated_with_agent   rico:isAgentAssociatedWithAgent   tripletas=1
  is_creation_date_of              rico:isCreationDateOf             tripletas=5
  is_date_associated_with          rico:isDateAssociatedWith         tripletas=1
  is_or_was_location_of            rico:isOrWasLocationOf            tripletas=1
  is_related_to                    rico:isRelatedTo                  tripletas=1
  issued_by                        rico:issuedBy                     tripletas=1
  migrated_into                    rico:migratedInto                 tripletas=1
  occupies_or_occupied             rico:occupiesOrOccupied           tripletas=1
  performs_or_performed            rico:performsOrPerformed          tripletas=2
  precedes_or_preceded             rico:precedesOrPreceded           tripletas=1
  regulates_or_regulated           rico:regulatesOrRegulated         tripletas=4
  ATRIBUTO alcance_contenido       rico:scopeAndContent              tripletas=2
  ATRIBUTO calificador_fecha       rico:dateQualifier                tripletas=1
  ATRIBUTO condiciones_acceso      rico:conditionsOfAccess           tripletas=1
  ATRIBUTO condiciones_uso         rico:conditionsOfUse              tripletas=0
  ATRIBUTO coordenadas             rico:geographicalCoordinates      tripletas=1
  ATRIBUTO descripcion_general     rico:generalDescription           tripletas=0
  ATRIBUTO extension               rico:recordResourceExtent         tripletas=0
  ATRIBUTO extension_instanciacion rico:instantiationExtent          tripletas=2
  ATRIBUTO fecha_expresada         rico:expressedDate                tripletas=13
  ATRIBUTO fecha_normalizada       rico:normalizedDateValue          tripletas=9
  ATRIBUTO historia                rico:history                      tripletas=1
  ATRIBUTO identificador           rico:identifier                   tripletas=9
  ATRIBUTO nombre                  rico:name                         tripletas=24
  ATRIBUTO reglas                  rico:ruleFollowed                 tripletas=0
  ATRIBUTO titulo                  rico:title                        tripletas=13
  ATRIBUTO valor_textual           rico:textualValue                 tripletas=3
  ATRIBUTO version_mecanismo       rico:technicalCharacteristics     tripletas=0
  APOYO estatuto_juridico          rico:hasOrHadLegalStatus          tripletas=1
  APOYO fin                        rico:hasEndDate                   tripletas=2
  APOYO forma_documental           rico:hasDocumentaryFormType       tripletas=2
  APOYO identificador_externo      rico:hasOrHadIdentifier           tripletas=1
  APOYO idioma_agrupacion          rico:hasOrHadAllMembersWithLanguage tripletas=0
  APOYO idioma_registro            rico:hasOrHadLanguage             tripletas=2
  APOYO inicio                     rico:hasBeginningDate             tripletas=3
  APOYO nombre_agente              rico:hasOrHadAgentName            tripletas=1
  APOYO nombre_lugar               rico:hasOrHadPlaceName            tripletas=1
  APOYO tipo_agrupacion            rico:hasRecordSetType             tripletas=6
  APOYO tipo_identificador         rico:hasIdentifierType            tripletas=1
  APOYO tipo_lugar                 rico:hasOrHadPlaceType            tripletas=1
  APOYO tipo_mandato               rico:hasOrHadMandateType          tripletas=2

== IRIs de objeto fuera de la base del sistema y de rico/rst ==
   http://lexvo.org/id/iso639-3/lat
   http://lexvo.org/id/iso639-3/spa
   http://www.w3.org/2004/02/skos/core#Concept
   http://www.w3.org/2004/02/skos/core#ConceptScheme
   https://www.nationalarchives.gov.uk/PRONOM/fmt/18
   https://www.nationalarchives.gov.uk/PRONOM/fmt/354
   https://www.wikidata.org/entity/Q1000000
== Literales con etiqueta de idioma == ['spa']

== conformidad_rico.reporte ==
  conforme: True | owl: {'conforme': True, 'problemas': []} | mapeo: {'problemas': []}
  shacl conforme: True | formas: 41
```

### A.3 Pruebas del repositorio

```text
$ cd /home/user/Tesis && source /home/user/venv-ricora/bin/activate && unset DATABASE_URL && python -m pytest -q -p no:cacheprovider tests/test_ric_o.py tests/test_exportacion_rico.py
# 1.ª ejecución (PostgreSQL detenido):
E   psycopg2.OperationalError: connection to server at "localhost" (127.0.0.1), port 5432 failed: Connection refused
2 warnings, 25 errors in 11.14s
# tras `service postgresql start`:
25 passed, 4 warnings in 13.07s
```
