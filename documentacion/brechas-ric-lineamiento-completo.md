# Qué le falta a RICORA para aplicar RiC completo

Diagnóstico para la tesis. Compara RICORA, código por código, con las cuatro
partes de Records in Contexts y dice qué falta, qué debería tener y en qué
orden aplicarlo. Las cifras salen de una medición reproducible (al final), no
de una opinión.

## 1. Qué es «el lineamiento completo»

RiC tiene cuatro partes. RICORA debe responder a todas, pero no de la misma forma.

| Parte | Versión vigente | Qué exige a un sistema | Cómo se mide |
|---|---|---|---|
| RiC-FAD (fundamentos) | 1.0 (2023) | Los principios: descripción como red de entidades y relaciones, contexto múltiple, procedencia. | Revisión cualitativa. |
| RiC-CM (modelo conceptual) | 1.0 (2023) | 19 entidades, 42 atributos (RiC-A01 a A45, con huecos) y 85 relaciones (RiC-R001 a R086). | Código por código (anexo A). |
| RiC-O (ontología) | 1.1 (mayo 2025) | La forma técnica de escribir RiC-CM: 107 clases, 480 propiedades de objeto y 75 de dato. Es «totalmente conforme» con RiC-CM 1.0. | Contra el OWL oficial que el sistema ya trae (`app/recursos/ric-o/RiC-O_1-1.rdf`). |
| RiC-AG (guías de aplicación) | 0.1, **borrador** (oct. 2025) | Recomendaciones prácticas: implantación evolutiva, vocabularios en SKOS, cómo modelar digitalización, valoración y eliminación, secuencias, instanciaciones y extensiones. | Recomendación por recomendación (sección 4). |

> **Lo que conviene tener claro (y defender en la tesis).** RiC no define niveles
> de conformidad ni un mínimo obligatorio. Aplicarlo completo no significa usar
> las 480 propiedades: muchas son inversas, transitivas o propias de archivos
> personales (maestro-alumno, conocidos). Significa poder expresar todo lo del
> modelo que tiene sentido para un archivo colombiano, y dejar escrita y
> justificada la decisión sobre lo que no aplica. Una cobertura del 100 % no es
> una meta razonable; una cobertura justificada sí lo es.

## 2. Dónde está RICORA hoy (medido)

| Qué se mide | Cubierto | Total | % |
|---|---|---|---|
| Entidades de RiC-CM | 19 | 19 | 100 % |
| Atributos de RiC-CM | 29 | 42 | 69 % |
| Relaciones de RiC-CM | 53 | 85 | 62 % |
| Clases de RiC-O 1.1 | 69 | 107 | 64 % |
| Pares de relación de RiC-O (contando una propiedad y su inversa como una; sin roles, transitivas ni proxies) | 67 | 190 | 35 % |
| Propiedades de dato de RiC-O | 35 | 75 | 47 % |

Notas de método:

- «Cubierto» significa que el código del sistema puede escribir ese término en
  el grafo publicado, validado por el OWL y el SHACL. No significa que cada
  fondo lo tenga diligenciado.
- Dos códigos aparecían en el código pero solo en el catálogo del perfil AGN,
  sin que el sistema los escriba: RiC-A33 (técnica de producción) y R070 (fecha
  de nacimiento). Se cuentan como **no cubiertos**.
- El 35 % de RiC-O engaña si se lee solo: la mayoría de lo que falta son
  variantes («algunos miembros», «la mayoría de los miembros», «directamente»,
  «tuvo» en pasado) de relaciones que RICORA ya usa en su forma general. La
  cifra que importa es la de RiC-CM.

## 3. Lo que falta, por prioridad

### Prioridad A: núcleo archivístico colombiano. Debe hacerse.

Son brechas que tocan datos que RICORA **ya tiene** en sus tablas y no dice en
RiC, o procesos que la gestión documental colombiana exige.

| # | Brecha | RiC-CM / RiC-O | Qué hay hoy | Qué debería tener |
|---|---|---|---|---|
| A1 | **Los tipos documentales de la serie (TRD)** no salen en RiC. | RiC-A17 en un Record Set: `rico:hasOrHadSomeMembersWithDocumentaryFormType` / `hasOrHadAllMembersWithDocumentaryFormType` | La TRD guarda los tipos de cada serie; el grafo solo pone `hasDocumentaryFormType` en documentos sueltos (su dominio es Record y RecordPart). RiC-AG lo dice expresamente para los Record Sets. | Cada serie y subserie, con sus tipos documentales de la TRD como `SomeMembersWith…`; si la TRD dice que todos los documentos son de un tipo, `AllMembersWith…`. |
| A2 | **Procedencia orgánica** del fondo. | RiC-R026 `rico:hasOrganicProvenance` (y su nodo `OrganicProvenanceRelation`) | El productor sale como creador (`hasCreator`) o acumulador. | El fondo y cada sección, con su procedencia orgánica hacia la entidad o dependencia. Es el principio de procedencia dicho en RiC; un archivista lo buscará primero. |
| A3 | **La eliminación sin fecha de destrucción ni resultado.** | `rico:hasDestructionDate`; RiC-R061 `resultsOrResultedIn` | La disposición es una Activity con fecha general (`isAssociatedWithDate`). | En la eliminación, el expediente con `hasDestructionDate`. En la digitalización, la migración y la selección, la Activity con `resultsOrResultedIn` hacia lo que produjo. Es el patrón exacto de RiC-AG para valoración y digitalización. |
| A4 | **El original físico y la copia digital no se distinguen.** | `rico:hasOrHadAnalogueInstantiation` / `hasOrHadDigitalInstantiation`; RiC-A04 `CarrierExtent`; RiC-A37 `RepresentationType` | La signatura topográfica y el estado de conservación existen en las tablas, pero salen como nota. Todas las instanciaciones se enlazan igual. | El original en papel como instanciación analógica, con su extensión de soporte (folios, cajas, metros lineales) y su ubicación. El archivo escaneado como instanciación digital derivada del original, con su tipo de representación. |
| A5 | **Estado del documento** (borrador, definitivo, copia). | RiC-A39 `RecordState`; RiC-R011 `isDraftOf` | No existe. | El estado de cada documento con un vocabulario controlado, y el borrador enlazado a su versión final. Es el ciclo de un SGDEA. |
| A6 | **Respuesta de una comunicación.** | RiC-R013 `rico:hasReply` / `isReplyTo` | No existe; solo hay secuencia (precede, sigue). | El oficio de respuesta enlazado al recibido. Es el corazón de las comunicaciones oficiales (radicados de entrada y salida) y RiC-AG lo pone como ejemplo de secuencia precisa. |
| A7 | **Completitud del expediente.** | RiC-A24 `rico:integrityNote` | No existe. Ojo: la huella SHA-256 ya va bien en `authenticityNote`; `integrityNote` es la **completitud intelectual**, no la fijeza. | En el expediente: si está completo, qué falta y la referencia a la hoja de control. |
| A8 | **El código de clasificación como atributo de RiC.** | RiC-A07 `rico:classification` | El código del CCD sale como `skos:notation`. | Además, `rico:classification` en cada recurso, con el código del cuadro. |
| A9 | **La descripción como documento que describe.** | RiC-R021 `rico:describesOrDescribed` | El FUID, la guía y el índice se generan, pero no existen en el grafo. | Cada instrumento generado y aprobado como un `rico:Record` (forma documental «inventario», «guía») que `describesOrDescribed` el fondo, con su autor y su fecha. Así el sistema describe también su propia descripción. |

### Prioridad B: contexto y agentes. Conviene hacerla con el fondo real.

| # | Brecha | RiC-CM / RiC-O | Para qué sirve en un archivo colombiano |
|---|---|---|---|
| B1 | Tipo de entidad | RiC-A12 `CorporateBodyType` | Entidad del orden nacional, departamental o municipal; sector central o descentralizado. |
| B2 | Autoridad y vigilancia | RiC-R036 `hasOrHadAuthorityOver`; RiC-R066 `isOrWasEnforcedBy` | La adscripción o vinculación (el ministerio sobre la entidad) y quién vigila la regla (el AGN o el consejo departamental sobre la TRD). |
| B3 | Participantes y fecha de los hechos | RiC-R058 `hasOrHadParticipant`; RiC-R084 `occurredAtDate`; RiC-R006 `hasOrHadSubevent` | Quién intervino en un hito o en un comité, y cuándo ocurrió, sin confundirlo con quien lo ejecutó. |
| B4 | Fechas de existencia de personas | RiC-R070 `hasBirthDate`; RiC-R072 `hasDeathDate` | ISAAR(CPF) 5.2.1 con las fechas propias de RiC, no solo inicio y fin. |
| B5 | Materia principal | RiC-R020 `hasOrHadMainSubject` | Distinguir la materia principal de las secundarias del tesauro. |
| B6 | Derechos de autor | RiC-R040 `hasOrHadIntellectualPropertyRightsHolder` | El titular de los derechos patrimoniales (Ley 23 de 1982), distinto del productor. |
| B7 | Relaciones entre documentos e instanciaciones | RiC-R004 componentes; R022 asociado; R023 vínculo genético; R034 instanciaciones asociadas | Un correo con sus adjuntos; los antecedentes de un acto; un expediente híbrido. |
| B8 | Tipo de contenido | RiC-A10 `ContentType`; RiC-A33 técnica de producción | Texto, imagen, plano, audio; manuscrito, mecanografiado, impreso. |
| B9 | Fechas predominantes | RiC-R082 y R083 (creación de algunos o de la mayoría de los miembros) | Las fechas predominantes que ya pide el FUID, dichas en RiC. |
| B10 | Tipo de familia y de ocupación | RiC-A20 `FamilyType`; RiC-A30 `OccupationType` | Archivos familiares y personales; profesión de los productores. |
| B11 | Tipo de evento | RiC-A18 `EventType` | Clasificar los hitos (creación, fusión, liquidación de una entidad) con vocabulario controlado. |
| B12 | Localización textual de un lugar | RiC-A27 `rico:location`, `PhysicalLocation` | La dirección o el predio de una sede o de un depósito de archivo. |
| B13 | Relación temporal y descendencia | RiC-R009 `precedesInTime`; RiC-R017 `hasDescendant` | Orden en el tiempo entre hechos o documentos sin secuencia archivística; genealogías en archivos familiares. |

### Prioridad C: no aplica o vale poco. Se documenta y no se implementa por ahora.

| Brecha | Código | Por qué no ahora |
|---|---|---|
| Maestro-alumno, estudios | RiC-R053, `StudyAtRelation` | Propio de archivos personales y biografías. |
| Conoce, conoce de | RiC-R050, R051 | Igual: archivos personales. |
| Correspondiente, relación laboral | RiC-R052, R046 | En archivos institucionales lo cubren el remitente, el destinatario y el cargo. Se reconsidera si entra un archivo personal. |
| Lugares adyacentes y superpuestos | RiC-R077, R078 | Sin uso en la descripción institucional. |
| Fechas dentro de otra y que se cruzan | RiC-R085, R086 | La fecha en EDTF ya expresa intervalos e incertidumbre. |
| Equivalencia funcional | RiC-R035 | Útil para comparar funciones entre entidades; no lo pide la TRD. |
| Grupo demográfico | RiC-A15 | Solo con consentimiento y finalidad clara (Ley 1581, datos sensibles). RiC-AG tiene un caso sobre comunidades indígenas: se aborda si el proyecto lo requiere. |
| `rico:Proxy` y rango en secuencia | RiC-O 1.1 | RiC-AG recomienda expresar el orden con relaciones (precede, sigue), que RICORA ya usa. |

## 4. Las recomendaciones de RiC-AG frente a RICORA

| Recomendación de RiC-AG 0.1 | Estado en RICORA | Qué hacer |
|---|---|---|
| Implantar por etapas, con un piloto sobre un conjunto pequeño y real. | Etapas sí; **piloto real, no**: todo se ha probado con fondos de prueba. | Cargar un fondo real (CCD, TRD y un lote) y medir. Es lo que más credibilidad le da a la tesis. |
| Mapear primero uno a uno desde la norma anterior y enriquecer después. | Hecho: ISAD(G) e ISAAR(CPF) mapeados, y el motor de IA extrae entidades del texto. | Nada. |
| Ocultar los tecnicismos de RiC al archivista y sugerir relaciones. | Hecho: términos en español, propuestas de la IA, vocabulario controlado. | Nada. |
| Vocabularios controlados en SKOS, con identificador, y el término más preciso. | Hecho para funciones, formas documentales, materias y tipos de agrupación. | Agregar los vocabularios nuevos: estado del documento (A5), tipo de entidad (B1), tipo de contenido y de representación (A4, B8). |
| En un Record Set, los tipos documentales con `…SomeMembers…` / `…AllMembers…`. | **No.** | Brecha A1. |
| La digitalización es una Activity que afecta el documento y **resulta en** una instanciación. | Parcial: la derivación existe, sin la Activity ni `resultsOrResultedIn`. | Brecha A3, y A4 para la instanciación analógica y la digital. |
| La eliminación, con `hasDestructionDate` y el acta como mandato. | Parcial: Activity, acta y regla sí; fecha de destrucción no. | Brecha A3. |
| Secuencias con relaciones y, en correspondencia, `hasReply`. | Secuencia sí; respuesta no. | Brecha A6. |
| Extender RiC solo si hace falta, en un espacio de nombres propio, como subclase o subpropiedad, documentado. | RICORA no inventa propiedades: lo que RiC-O no expresa va a un grafo de control que no se publica. | Mantenerlo. Si se necesita una extensión (por ejemplo, la disposición final de la TRD como tipo), declararla `ricora:` como subpropiedad de RiC-O y publicarla. |
| Registrar el trabajo en la lista de recursos de RiC y en la lista de correo. | No. | Hacerlo cuando el piloto real esté listo. Da visibilidad internacional a la tesis. |

## 5. Cómo aplicar el lineamiento completo: plan

| Fase | Contenido | Resultado verificable |
|---|---|---|
| 1 | Prioridad A completa (A1 a A9). Casi todo son datos que ya existen; se agrega la propiedad en `ric_o.py`, la forma en el SHACL, el campo donde falte y la prueba de tripleta. | Atributos de RiC-CM: de 29 a 34 de 42. Relaciones: de 53 a 58 de 85. |
| 2 | Piloto con un fondo real: CCD, TRD aprobada, un lote de transferencia y unas decenas de documentos descritos. | Informe de conformidad SHACL del fondo real y medición de la IA con el módulo Evaluación. |
| 3 | Prioridad B, en el orden que pida el fondo real (no todas aplican a todos los fondos). | Cobertura justificada: cada código con «cubierto» o «no aplica, porque…». |
| 4 | Interoperabilidad comprobada: exportar el fondo real e importarlo de vuelta; importar un conjunto RiC-O de un tercero (por ejemplo, datos publicados de FranceArchives o Memobase, que RiC-AG cita como usuarios de RiC-O). | Ida y vuelta sin pérdida, e informe de lo que se omite al importar. |
| 5 | Prueba automática de cobertura: falla si una propiedad cubierta deja de escribirse, y lista lo marcado «no aplica». | La cobertura deja de ser una afirmación y queda en la integración continua. |

### Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Meta de cobertura | 100 % de RiC-O; 100 % de RiC-CM; cobertura justificada | Cobertura justificada de RiC-CM | RiC no define niveles de conformidad. RiC-AG pide implantar por etapas y según la necesidad. Forzar relaciones de archivos personales en un archivo institucional agrega campos vacíos. | Un jurado puede preguntar «¿por qué no todo?». Se responde con la tabla de prioridad C. |
| Orden | Primero agentes (B); primero núcleo TRD (A); todo junto | Primero A | A usa datos que ya existen, toca lo que hace distinto a RICORA (la TRD y la gestión documental colombiana) y sigue patrones que RiC-AG da literalmente. | Ninguno relevante; son cambios acotados. |
| Piloto real | Antes de A; después de A; no hacerlo | Después de A | Con A hecho, el piloto mide el sistema completo en lo esencial. | Conseguir un fondo real con permiso de uso; anonimizar datos personales. |
| Extensiones propias | Ninguna; subpropiedades `ricora:`; propiedades sueltas | Ninguna por ahora; `ricora:` solo si aparece una necesidad real | RiC-AG: «verifique que la extensión es realmente necesaria». Hasta hoy, todo lo necesario tiene término en RiC-O 1.1. | Si se necesita, hay que mantenerla cuando RiC cambie. |

## 6. Sobre la innovación (para el capítulo de estado del arte)

RICORA no es el único software que usa RiC: RiC-AG cita a FranceArchives y a
Memobase como implementaciones de RiC-O, y existen conversores públicos
(Archives nationales de Francia). Lo que la tesis puede defender como
innovación es la combinación, que no se encontró documentada en otro sistema:

1. **Un sistema de descripción nativo de RiC**: lo publicado vive en un grafo RiC-O 1.1 validado, no se convierte después.
2. **La TRD y el CCD colombianos como instrumentos RiC**: la TRD como `rico:Rule` versionada, regulada por su acto (`rico:Mandate`), con cada expediente regido por la regla vigente en su fecha, y la disposición final como `rico:Activity`.
3. **Asistencia de IA medida**: la propuesta del motor como registro aparte, la decisión humana auditada y la evaluación ciega con métricas por relación RiC.

Conviene sostenerlo con una revisión sistemática del estado del arte (bases
académicas y la lista de recursos de RiC), no con la afirmación de que no hay
otro.

## Anexo A. Cobertura de RiC-CM 1.0, código por código

Generado desde el OWL de RiC-O 1.1 (que cita el código de RiC-CM de cada
término) y el código de `app/`. «Cubierto» = el sistema escribe al menos uno
de los términos de RiC-O que implementan ese código. Prioridad: A, B o C
según la sección 3.

| Código | Nombre en RiC-CM | Términos de RiC-O | Estado | Prioridad |
|---|---|---|---|---|
| RiC-A01 | Accruals | `accruals` | Cubierto |  |
| RiC-A02 | Activity Type | `ActivityType` | Cubierto |  |
| RiC-A03 | Authenticity Note | `authenticityNote` | Cubierto |  |
| RiC-A04 | Carrier Extent | `CarrierExtent`, `carrierExtent` | Falta | A |
| RiC-A05 | Carrier Type | `CarrierType` | Cubierto |  |
| RiC-A07 | Classification | `classification` | Falta | A |
| RiC-A08 | Conditions of Access | `conditionsOfAccess` | Cubierto |  |
| RiC-A09 | Conditions of Use | `conditionsOfUse` | Cubierto |  |
| RiC-A10 | Content Type | `ContentType` | Falta | B |
| RiC-A11 | Coordinates | `geographicalCoordinates` | Cubierto |  |
| RiC-A12 | Corporate Body Type | `CorporateBodyType` | Falta | B |
| RiC-A13 | Date Qualifier | `dateQualifier` | Cubierto |  |
| RiC-A15 | Demographic Group | `DemographicGroup` | Falta | C |
| RiC-A17 | Documentary Form Type | `DocumentaryFormType` | Cubierto |  |
| RiC-A18 | Event Type | `EventType` | Falta | B |
| RiC-A19 | Expressed Date | `expressedDate` | Cubierto |  |
| RiC-A20 | Family Type | `FamilyType` | Falta | B |
| RiC-A21 | History | `history` | Cubierto |  |
| RiC-A22 | Identifier | `Identifier`, `identifier` | Cubierto |  |
| RiC-A23 | Instantiation Extent | `InstantiationExtent`, `instantiationExtent` | Cubierto |  |
| RiC-A24 | Integrity Note | `integrityNote` | Falta | A |
| RiC-A25 | Language | `Language` | Cubierto |  |
| RiC-A26 | Legal Status | `LegalStatus` | Cubierto |  |
| RiC-A27 | Location | `PhysicalLocation`, `location` | Falta | B |
| RiC-A28 | Name | `AgentName`, `Name`, `PlaceName` | Cubierto |  |
| RiC-A29 | Normalized Date | `normalizedDateValue` | Cubierto |  |
| RiC-A30 | Occupation Type | `OccupationType` | Falta | B |
| RiC-A31 | Physical Characteristics Note | `physicalCharacteristicsNote` | Cubierto |  |
| RiC-A32 | Place Type | `PlaceType` | Cubierto |  |
| RiC-A33 | Production Technique | `ProductionTechniqueType`, `productionTechnique` | Falta | B |
| RiC-A34 | Quality of Representation Note | `qualityOfRepresentationNote` | Cubierto |  |
| RiC-A35 | Record Resource extent | `RecordResourceExtent`, `recordResourceExtent` | Cubierto |  |
| RiC-A36 | Record Set Type | `RecordSetType` | Cubierto |  |
| RiC-A37 | Representation Type | `RepresentationType` | Falta | A |
| RiC-A38 | Scope and Content | `scopeAndContent` | Cubierto |  |
| RiC-A39 | State | `RecordState` | Falta | A |
| RiC-A40 | Structure | `structure` | Cubierto |  |
| RiC-A41 | Technical Characteristics | `technicalCharacteristics` | Cubierto |  |
| RiC-A42 | Date Type | `DateType` | Cubierto |  |
| RiC-A43 | General Description | `generalDescription` | Cubierto |  |
| RiC-A44 | Mandate Type | `MandateType` | Cubierto |  |
| RiC-A45 | Rule Type | `RuleType` | Cubierto |  |
| RiC-R001 | is related to | `isRelatedTo` | Cubierto |  |
| RiC-R002 | has or had part | `WholePartRelation`, `hasOrHadPart` | Cubierto |  |
| RiC-R003 | has or had constituent | `hasOrHadConstituent`, `isOrWasConstituentOf` | Cubierto |  |
| RiC-R004 | has or had component | `hasOrHadComponent`, `isOrWasComponentOf` | Falta | B |
| RiC-R005 | has or had subdivision | `GroupSubdivisionRelation`, `hasOrHadSubdivision`, `isOrWasSubdivisionOf` | Cubierto |  |
| RiC-R006 | has or had subevent | `hasOrHadSubevent`, `isOrWasSubeventOf` | Falta | B |
| RiC-R007 | contains or contained | `containsOrContained`, `isOrWasContainedBy` | Cubierto |  |
| RiC-R008 | precedes or preceded | `SequentialRelation`, `followsOrFollowed`, `precedesOrPreceded` | Cubierto |  |
| RiC-R009 | precedes in time | `TemporalRelation`, `followsInTime`, `precedesInTime` | Falta | B |
| RiC-R010 | is original of | `isOriginalOf` | Cubierto |  |
| RiC-R011 | is draft of | `isDraftOf` | Falta | A |
| RiC-R012 | has copy | `hasCopy` | Cubierto |  |
| RiC-R013 | has reply | `hasReply`, `isReplyTo` | Falta | A |
| RiC-R014 | has or had derived instantiation | `DerivationRelation`, `hasOrHadDerivedInstantiation`, `isOrWasDerivedFromInstantiation` | Cubierto |  |
| RiC-R015 | migrated into | `MigrationRelation`, `migratedFrom`, `migratedInto` | Cubierto |  |
| RiC-R016 |  | `AgentTemporalRelation`, `hasSuccessor`, `isSuccessorOf` | Cubierto |  |
| RiC-R017 | has descendant | `DescendanceRelation`, `hasAncestor`, `hasDescendant` | Falta | B |
| RiC-R018 | has child | `ChildRelation` | Cubierto |  |
| RiC-R019 | has or had subject | `hasOrHadSubject`, `isOrWasSubjectOf` | Cubierto |  |
| RiC-R020 | has or had main subject | `hasOrHadMainSubject`, `isOrWasMainSubjectOf` | Falta | B |
| RiC-R021 | describes or described | `describesOrDescribed`, `isOrWasDescribedBy` | Falta | A |
| RiC-R022 | is record resource associated with record resource | `RecordResourceToRecordResourceRelation`, `isRecordResourceAssociatedWithRecordResource` | Falta | B |
| RiC-R023 | has genetic link to record resource | `RecordResourceGeneticRelation`, `hasGeneticLinkToRecordResource` | Falta | B |
| RiC-R024 | includes or included | `includesOrIncluded`, `isOrWasIncludedIn` | Cubierto |  |
| RiC-R025 | has or had instantiation | `RecordResourceToInstantiationRelation`, `hasOrHadInstantiation`, `isOrWasInstantiationOf` | Cubierto |  |
| RiC-R026 | has provenance | `OrganicProvenanceRelation`, `hasOrganicProvenance`, `isOrganicProvenanceOf` | Falta | A |
| RiC-R027 | has creator | `CreationRelation`, `hasCreator`, `isCreatorOf` | Cubierto |  |
| RiC-R028 | has accumulator | `AccumulationRelation`, `hasAccumulator`, `isAccumulatorOf` | Cubierto |  |
| RiC-R029 | has receiver | `hasReceiver` | Cubierto |  |
| RiC-R030 | has collector | `hasCollector` | Cubierto |  |
| RiC-R031 | has sender | `hasSender`, `isSenderOf` | Cubierto |  |
| RiC-R032 | has addressee | `hasAddressee`, `isAddresseeOf` | Cubierto |  |
| RiC-R033 | documents | `ActivityDocumentationRelation`, `documentedBy`, `documents` | Cubierto |  |
| RiC-R034 | is instantiation associated with instantiation | `isInstantiationAssociatedWithInstantiation` | Falta | B |
| RiC-R035 | is functionally equivalent to | `FunctionalEquivalenceRelation`, `isFunctionallyEquivalentTo` | Falta | C |
| RiC-R036 | has or had authority over | `AuthorityRelation`, `hasOrHadAuthorityOver`, `isOrWasUnderAuthorityOf` | Falta | B |
| RiC-R037 | is or was owner of | `isOrWasOwnerOf` | Cubierto |  |
| RiC-R038 | is or was manager of | `isOrWasManagerOf` | Cubierto |  |
| RiC-R039 | is or was holder of | `RecordResourceHoldingRelation`, `hasOrHadHolder`, `isOrWasHolderOf` | Cubierto |  |
| RiC-R040 | is or was holder of intellectual property rights of | `IntellectualPropertyRightsRelation`, `hasOrHadIntellectualPropertyRightsHolder`, `isOrWasHolderOfIntellectualPropertyRightsOf` | Falta | B |
| RiC-R041 | is or was controller of | `isOrWasControllerOf` | Cubierto |  |
| RiC-R042 | is or was leader of | `LeadershipRelation`, `hasOrHadLeader`, `isOrWasLeaderOf` | Cubierto |  |
| RiC-R044 | is agent associated with agent | `AgentToAgentRelation`, `isAgentAssociatedWithAgent` | Cubierto |  |
| RiC-R045 | has or had subordinate  | `AgentHierarchicalRelation`, `hasOrHadSubordinate`, `isOrWasSubordinateTo` | Cubierto |  |
| RiC-R046 | has or had work relation with | `WorkRelation`, `hasOrHadWorkRelationWith` | Falta | C |
| RiC-R047 | has family association with | `FamilyRelation`, `hasFamilyAssociationWith` | Cubierto |  |
| RiC-R048 | has sibling | `SiblingRelation` | Cubierto |  |
| RiC-R049 | has or had spouse | `SpouseRelation` | Cubierto |  |
| RiC-R050 | knows of | `KnowingOfRelation`, `knownBy`, `knowsOf` | Falta | C |
| RiC-R051 | knows | `KnowingRelation`, `knows` | Falta | C |
| RiC-R052 | has or had correspondent | `CorrespondenceRelation`, `hasOrHadCorrespondent` | Falta | C |
| RiC-R053 | has or had teacher | `TeachingRelation`, `hasOrHadStudent`, `hasOrHadTeacher` | Falta | C |
| RiC-R054 | occupies or occupied | `PositionHoldingRelation`, `isOrWasOccupiedBy`, `occupiesOrOccupied` | Cubierto |  |
| RiC-R055 | has or had member | `MembershipRelation`, `hasOrHadMember`, `isOrWasMemberOf` | Cubierto |  |
| RiC-R056 | exists or existed in | `PositionToGroupRelation`, `existsOrExistedIn`, `hasOrHadPosition` | Cubierto |  |
| RiC-R057 | is event associated with | `EventRelation` | Cubierto |  |
| RiC-R058 | has or had participant | `hasOrHadParticipant`, `isOrWasParticipantIn` | Falta | B |
| RiC-R059 | affects or affected | `affectsOrAffected`, `isOrWasAffectedBy` | Cubierto |  |
| RiC-R060 | is or was performed by | `PerformanceRelation`, `isOrWasPerformedBy`, `performsOrPerformed` | Cubierto |  |
| RiC-R061 | results or resulted in | `resultsOrResultedFrom`, `resultsOrResultedIn` | Falta | A |
| RiC-R062 | is rule associated with | `RuleRelation` | Cubierto |  |
| RiC-R063 | regulates or regulated | `isOrWasRegulatedBy`, `regulatesOrRegulated` | Cubierto |  |
| RiC-R064 | is or was expressed by | `isOrWasExpressedBy` | Cubierto |  |
| RiC-R065 | issued by | `issuedBy` | Cubierto |  |
| RiC-R066 | is or was enforced by | `isOrWasEnforcedBy`, `isOrWasResponsibleForEnforcing` | Falta | B |
| RiC-R067 | authorizes | `MandateRelation`, `authorizedBy`, `authorizes` | Cubierto |  |
| RiC-R068 | is date associated with | `isAssociatedWithDate`, `isDateAssociatedWith` | Cubierto |  |
| RiC-R069 | is beginning date of | `DateType`, `hasBeginningDate`, `isBeginningDateOf` | Cubierto |  |
| RiC-R070 | is birth date of | `hasBirthDate`, `isBirthDateOf` | Falta | B |
| RiC-R071 | is end date of | `hasEndDate`, `isEndDateOf` | Cubierto |  |
| RiC-R072 | is death date of | `hasDeathDate`, `isDeathDateOf` | Falta | B |
| RiC-R073 | is modification date of | `isModificationDateOf` | Cubierto |  |
| RiC-R074 | is place associated with | `PlaceRelation` | Cubierto |  |
| RiC-R075 | is or was location of | `hasOrHadLocation`, `isOrWasLocationOf` | Cubierto |  |
| RiC-R076 | is or was jurisdiction of | `isOrWasJurisdictionOf` | Cubierto |  |
| RiC-R077 | is or was adjacent to | `isOrWasAdjacentTo` | Falta | C |
| RiC-R078 | overlaps or overlapped | `overlapsOrOverlapped` | Falta | C |
| RiC-R079 | has author | `AuthorshipRelation`, `hasAuthor`, `isAuthorOf` | Cubierto |  |
| RiC-R080 | is creation date of | `hasCreationDate`, `isCreationDateOf` | Cubierto |  |
| RiC-R081 | is or was creation date of all members of | `hasOrHadAllMembersWithCreationDate` | Cubierto |  |
| RiC-R082 | is or was creation date of some members of | `hasOrHadSomeMembersWithCreationDate`, `isOrWasCreationDateOfSomeMembersOf`, `someMembersWithCreationDate` | Falta | B |
| RiC-R083 | is or was creation date of most members of | `hasOrHadMostMembersWithCreationDate`, `isOrWasCreationDateOfMostMembersOf`, `mostMembersWithCreationDate` | Falta | B |
| RiC-R084 | is date of occurrence of | `isDateOfOccurrenceOf`, `occurredAtDate` | Falta | B |
| RiC-R085 | is within | `hasWithin`, `isWithin` | Falta | C |
| RiC-R086 | intersects | `intersects` | Falta | C |

## Anexo B. Cómo repetir la medición

```bash
source /home/user/venv-ricora/bin/activate
python - <<'PY'
# 1. Lee app/recursos/ric-o/RiC-O_1-1.rdf con rdflib.
# 2. Para cada término de RiC-O, toma los códigos RiC-A.. y RiC-R.. que cita.
# 3. Busca cada término (y su inversa, en camelCase o snake_case) en app/**/*.py.
# 4. Un código está cubierto si al menos uno de sus términos lo está y no aparece
#    solo en catálogos (perfil_agn.py, importacion_rico.py, terminos.py).
PY
```

La fase 5 del plan convierte este procedimiento en una prueba automática.

## Fuentes

- ICA, RiC-CM 1.0 (2023): https://www.ica.org/app/uploads/2024/01/ric-cm-1.0_0.pdf
- ICA, RiC-O 1.1 (2025): https://www.ica.org/ica-network/expert-groups/egad/records-in-contexts-ontology/
- ICA-EGAD, RiC-AG 0.1 (borrador, 2025): https://github.com/ICA-EGAD/RiC-AG (estrategias de implantación; preguntas sobre actividades, extensiones, instanciación, secuencias y vocabularios)
- Anuncio de RiC-AG 0.1: https://www.ica.org/egad-publishes-ric-application-guidelines-ric-ag-version-0-1/
