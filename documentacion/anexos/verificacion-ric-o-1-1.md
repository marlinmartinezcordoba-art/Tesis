# Verificación contra el archivo OWL de RiC-O 1.1: los trece puntos pendientes

Este anexo responde, uno por uno, los trece puntos que el «Anexo técnico, mapeo verificado entre el modelo de datos del Sistema RIC y la ontología RiC-O 1.1» dejó pendientes en su sección 4. También corrige tres afirmaciones de ese anexo que no resistieron la comparación con el archivo oficial.

## Fuentes y método

- **Ontología:** archivo OWL oficial de RiC-O 1.1 (versión del 22 de mayo de 2025), del Consejo Internacional de Archivos, con licencia CC BY 4.0. Se guarda en el proyecto en `app/recursos/ric-o/RiC-O_1-1.rdf`.
- **Modelo conceptual:** PDF de RiC-CM 1.0, noviembre de 2023.
- **Método:** cada propiedad se buscó por su nombre local y se leyeron su tipo (de objeto o de dato), su dominio, su rango, su inversa (`owl:inverseOf`), sus superpropiedades y su correspondencia con RiC-CM (`rico:RiCCMCorrespondingComponent`).
- **Comprobación permanente:** la verificación no queda solo en este texto. El mapeo vive en un único archivo de código, `app/servicios/ric_o.py`. La función `verificar_contra_owl()` vuelve a leer el OWL y la prueba `tests/test_ric_o.py` falla si alguno de estos casos se presenta:
  - un nombre no existe en el OWL;
  - el dominio o el rango no admiten las clases con que el sistema usa la propiedad;
  - la inversa declarada no es la del OWL;
  - el código RiC-CM no coincide.

## Respuesta a los trece puntos

| # | Punto pendiente | Lo que dice el OWL | Decisión en RICORA |
|---|---|---|---|
| 1 | Dominio y rango de `performsOrPerformed` | Dominio `Agent`, rango `Activity`. Inversa `isOrWasPerformedBy`. RiC-CM R060i. | Confirmado; sin cambios. |
| 2 | ¿Subclases de `Date` para simple, rango y conjunto? | No existen. RiC-O 1.1 tiene una sola clase `Date` (no hay `SingleDate` ni `DateRange`). Se describe con `expressedDate` (A19), `normalizedDateValue` (A29), `dateQualifier` (A13) y `hasDateType`. | Confirmado. El subtipo es un dato del sistema; en la exportación lo transmite la propia expresión EDTF. |
| 3 | Relación asociativa entre agentes | `isAgentAssociatedWithAgent`, RiC-CM R044, simétrica. Su nota de uso pide usarla solo si no cabe una más específica, por ejemplo `hasOrHadWorkRelationWith` (R046). | Confirmado. Se usa R044, que ya estaba en el catálogo. |
| 4 | ¿`Group` se puede instanciar directamente? | Sí. La nota de alcance de `Group` dice: «las entidades corporativas y las familias son clases de grupos, aunque son posibles otras clases de grupos», y pone el electorado como ejemplo. | El subtipo «grupo» se exporta como `rico:Group`. |
| 5 | Evento institucional y su agente | No hay propiedad dedicada a «hito de la historia de». Las más específicas son `affectsOrAffected` (R059: el evento tuvo un impacto significativo en la cosa) y `hasOrHadParticipant` (R058). | `affectsOrAffected` (R059), marcada como **general** en el mapeo. Cubre creación, reforma y traslado; el hito se exporta como `rico:Event`. |
| 6 | Versión de un `Mechanism` | Existe `technicalCharacteristics` (A41), propiedad de dato cuyo dominio es exactamente `Mechanism`. | La versión se guarda una sola vez en la ficha del mecanismo. Se exporta con `rico:technicalCharacteristics` para los mecanismos que actuaron sobre un archivo exportado (Siegfried al identificar el formato, Ghostscript al migrar), junto con esa acción como `rico:Activity` que el mecanismo ejerce (`performsOrPerformed`) y que afecta al archivo (`affectsOrAffected`). El motor de análisis no se exporta: es procedencia del dato. *Corregido el 3 de octubre de 2026 (hallazgos CM-11 y O-19 de la auditoría RiC): hasta entonces esta fila afirmaba una exportación que el código no hacía.* |
| 7 | Mandato que crea un agente o un tipo de actividad | No hay propiedad de «creación». Para un agente, `authorizes` (R067: el mandato da al agente «la autoridad o las competencias para actuar»). Para un tipo de actividad, `regulatesOrRegulated` (R063, Rule → Thing). | `authorizes` con rol «creacion» para el agente y `regulatesOrRegulated` con rol «creacion» para el tipo de actividad. El rol queda en la base y en la interfaz. |
| 8 | Vínculo entre función y serie (TRD) | No hay propiedad dedicada. | Se exporta con `isRelatedTo` (R001, la más general y simétrica), marcada como **general**. La relación sustantiva sigue siendo `documents` + `hasActivityType` en cada documento de la serie. |
| 9 | Jerarquía y tipo de lugar | Jerarquía: `containsOrContained` (R007, Place → Place). Su nota de uso: «para conectar dos regiones geográficas o administrativas». Tipo: `hasOrHadPlaceType` → `PlaceType`. | Ambas confirmadas. |
| 10 | Secuencia entre documentos | `precedesOrPreceded` (R008), con inversa `followsOrFollowed`, Thing → Thing. Su nota aclara que la relación no fija el criterio de orden y que puede haber entidades intermedias. | R008. La fila guarda «el origen precede al destino»; la inversa se lee de ella. |
| 11 | Custodia distinta de la producción | `hasOrHadHolder` (R039i), dominio `RecordResource` o `Instantiation`, rango `Agent`. Ejemplo de RiC-CM: el Archivo Nacional de España es o fue conservador de un fondo. | `hasOrHadHolder`. |
| 12 | Jerarquía normativa entre mandatos | No hay propiedad dedicada. `regulatesOrRegulated` (R063) admite una regla como origen y cualquier cosa como destino; la genérica es `isRuleAssociatedWith` (R062). | `regulatesOrRegulated` con rol «jerarquia_normativa»: la norma superior regula a la que la desarrolla. Interpretación declarada (ver riesgo abajo). |
| 13 | Idioma, condiciones de acceso y de uso | Acceso: `conditionsOfAccess` (A08). Uso: `conditionsOfUse` (A09); ambas de dato, sobre `RecordResource` o `Instantiation`. Idioma: `hasOrHadLanguage` → `Language`, **solo para Record, Record Part y Agent**; para un Record Set existe `hasOrHadAllMembersWithLanguage`. | Las tres confirmadas, respetando la diferencia entre documento y agrupación en el idioma. |

## Una propiedad que el anexo no mencionaba

El prompt de vocabularios pide registrar «la entidad que expidió» un mandato. RiC-O tiene para eso `issuedBy` (RiC-R065), de `Rule` a `Agent`, sin inversa declarada. Se agregó al catálogo con ese nombre.

## Tres correcciones al anexo anterior

1. **Parte documental.**
   - **El anexo decía:** usar `RecordResource` o `Record` con `hasOrHadPart`.
   - **El OWL dice:** RiC-O tiene la clase `RecordPart` (RiC-E05, «componente documental» en su etiqueta oficial en español) y la relación `hasOrHadConstituent` (R003), con dominio y rango `Record` o `RecordPart`. La nota de uso de `hasOrHadPart` pide usar la relación más específica cuando existe.
   - **Además:** la inclusión `includesOrIncluded` (R024) no admite `RecordPart` como destino.
   - **Decisión:** una parte documental es `rico:RecordPart` unida a su unidad documental por `hasOrHadConstituent`. Sigue siendo un recurso documental más en la base de datos, como pide el prompt; solo cambia la propiedad con que se exporta.
2. **Mandato y actividad.**
   - **El anexo decía:** «una Actividad está fundamentada en un Mandato mediante `authorizedBy`».
   - **El OWL dice:** el dominio de `authorizedBy` es `Agent`, no `Activity`.
   - **Decisión:** la regulación de una actividad por un mandato es `regulatesOrRegulated` (R063). El sistema ya lo hace así desde la versión 2 del módulo de descripción.
3. **Coordenadas.**
   - **El anexo decía:** las coordenadas se asocian a `Place` mediante la clase `Coordinates`.
   - **El OWL dice:** el dominio de `hasOrHadCoordinates` es `PhysicalLocation`, no `Place`. Para un lugar existe `geographicalCoordinates` (A11), de dato. Su nota la recomienda cuando no se usa `PhysicalLocation`.
   - **Decisión:** `rico:geographicalCoordinates`.

## Dos correcciones al propio mapeo, halladas al construir la exportación

Al exportar el fondo y validarlo dato a dato contra el OWL (no solo el mapeo), aparecieron dos errores del mapeo de la entrega anterior. Se corrigieron y la verificación automática ahora los habría detectado:

1. **Código RiC-CM de `rico:title`.**
   - **El mapeo decía:** RiC-A40.
   - **RiC-CM 1.0 dice:** RiC-A40 es **Structure**. El OWL anota `rico:title` como «especialización de RiC-A28 (Name)».
   - **Decisión:** `rico:title` ↔ RiC-A28. `verificar_contra_owl()` ahora compara también el código de cada atributo con el `RiCCMCorrespondingComponent` del OWL, como ya hacía con las relaciones. Con el código viejo, la prueba falla.
2. **Tipo de mandato.**
   - **El mapeo decía:** `hasOrHadRuleType` → `RuleType`.
   - **El OWL dice:** existe `hasOrHadMandateType` (dominio `Mandate`) → `MandateType`, subclase de `RuleType`. RiC-O pide usar la más específica.
   - **Decisión:** `hasOrHadMandateType`.

Y una omisión explícita nueva: la **estructura interna de un agente** (ISAAR 5.2.7). `rico:structure` solo admite Instantiation y RecordResource. RiC expresa esa estructura con relaciones entre agentes (`hasOrHadSubordinate`), que sí se exportan.

La exportación y su reporte de conformidad están en `documentacion/anexos/rico-ejemplo/`.

## Datos que RiC-O no tiene dónde poner

Estos datos se guardan en el sistema y no se exportan. La omisión es explícita y no un olvido:

- **Calendario de la fecha.** RiC-O no declara calendario. `normalizedDateValue` usa ISO 8601, que es gregoriano. La tesis lo declara como delimitación.
- **Nivel de detalle, fuentes y fechas de control del registro de autoridad.** Son control interno.
- **Origen, confianza y estado de revisión de cada dato.** Por regla del sistema nunca salen de él.
- **Estructura interna de un agente** (ISAAR 5.2.7): ver la sección anterior.

## Tipos de agrupación

El vocabulario oficial `recordSetTypes` de RiC-O tiene cuatro individuos: Fonds, Series, File y Collection. Fondo, serie y expediente se exportan con el individuo oficial.

Sección y subserie no tienen individuo oficial. Se declaran como conceptos propios del fondo, con `skos:broadMatch` hacia el oficial más cercano: sección hacia Fonds y subserie hacia Series. No se inventa un individuo dentro del espacio de nombres del Consejo Internacional de Archivos.

## Riesgos que quedan a juicio de la autora

| Decisión | Riesgo | Mitigación |
|---|---|---|
| Jerarquía normativa con R063 | Un lector puede entender «la ley regula el decreto» de forma más estrecha que «el decreto desarrolla la ley». | El rol «jerarquia_normativa» queda en la base y en la interfaz. La alternativa genérica (R062) pierde la dirección; se puede cambiar en un solo lugar del código. |
| Hito institucional con R059 | «Impacto significativo» es más fuerte que «hecho de su historia». | Marcada como general. Un hito menor que no afecte al agente no debería registrarse como hito. |
| Función y serie con R001 | R001 no dice nada del tipo de vínculo. | Marcada como general. La relación sustantiva se reconstruye por documents + hasActivityType. |


## Perfil de aplicación de RICORA: cardinalidades (decisión CM-21)

RiC-O 1.1 no declara ninguna propiedad funcional (`owl:FunctionalProperty`). Cada «a lo sumo uno» que impone RICORA es entonces una restricción propia del sistema. La autora la decidió el 3 de octubre de 2026 y aquí queda escrita con su razón. La misma tabla vive en el código (`ric_o.PERFIL_CARDINALIDAD`), y una prueba exige que ambas coincidan.

| Restricción | Razón |
|---|---|
| Un solo superior orgánico por descripción (incluido_en_id), más inclusiones adicionales con rol «adicional» | Principio de procedencia y orden original del cuadro de clasificación; una colección facticia se declara como inclusión adicional. |
| Una forma documental por documento | En diplomática un documento tiene un tipo documental; dos formas son dos documentos. |
| Una instanciación digital pertenece a un solo Record Resource | Un archivo inscribe un documento; si un conjunto mezcla documentos, cada uno se individualiza en su propio Record (CM-03). |
| Una regla de retención vigente por serie o subserie | La TRD asigna un solo tiempo de retención y una sola disposición final por serie o subserie. |
| Un tipo de actividad por actividad | La actividad es el ejercicio concreto de una competencia; dos competencias son dos actividades. |
| Un concepto superior por tipo de actividad | El árbol de funciones de la TRD es un árbol (función → subfunción), no un grafo. |
| Varios lugares superiores, cada uno con su vigencia y sin solaparse | Relajada: un municipio cambia de provincia o de estado en el tiempo. |
| Varios agentes o descripciones afectados por un hito | Relajada: una fusión o un traslado afecta a más de una entidad. |
| Una cadena de custodios con fechas | Relajada: la historia custodial tiene varios tramos. |
