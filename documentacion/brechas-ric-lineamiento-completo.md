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

## 2. Dónde está RICORA (medido)

| Qué se mide | Antes de la fase 1 | Después de la fase 1 | Cobertura total (sección 8) | Total |
|---|---|---|---|---|
| Entidades de RiC-CM | 19 | 19 | 19 | 19 |
| Atributos de RiC-CM | 29 (69 %) | 35 (83 %) | **42 (100 %)** | 42 |
| Relaciones de RiC-CM | 43 (51 %) | 50 (59 %), más 1 cubierta por su especialización | **84, más 1 cubierta por su especialización (100 %)** | 85 |

> **Corrección.** La primera versión de este informe decía 53 relaciones. Eran
> 43: la búsqueda de texto contó como cubiertos nueve códigos que el sistema
> tiene en su catálogo como «reservados» y no exporta (receptor, coleccionista,
> propietario, gestor, control, original, copia, fecha de modificación y
> jurisdicción). La medición ahora sale del mapeo que usa la exportación
> (`app/servicios/cobertura_ric.py`) y una prueba impide que baje.

Medición de RiC-O 1.1 antes de la fase 1, por término (sigue siendo útil como contexto):

| Qué se mide | Cubierto | Total | % |
|---|---|---|---|
| Clases de RiC-O 1.1 | 69 | 107 | 64 % |
| Pares de relación de RiC-O (contando una propiedad y su inversa como una; sin roles, transitivas ni proxies) | 67 | 190 | 35 % |
| Propiedades de dato de RiC-O | 35 | 75 | 47 % |

Notas de método:

- «Cubierto» significa que el código del sistema puede escribir ese término en
  el grafo publicado, validado por el OWL y el SHACL. No significa que cada
  fondo lo tenga diligenciado.
- Dos códigos aparecían en el código pero solo en el catálogo del perfil AGN,
  sin que el sistema los escriba: RiC-A33 (técnica de producción) y R070 (fecha
  de nacimiento). Se cuentan como **no cubiertos**. Lo mismo los nueve códigos
  reservados de la corrección de arriba.
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
| A2 | ~~Procedencia orgánica del fondo.~~ **No era una brecha** (ver sección 7). | RiC-R026 `rico:hasOrganicProvenance` | El productor sale como creador (`hasCreator`) o acumulador (`hasAccumulator`), que en RiC-O 1.1 son subpropiedades de `hasOrganicProvenance`. | Nada más. La nota de uso oficial dice usar la general «solo si no es posible usar una relación más específica, por ejemplo *has creator*». Escribirla además iría contra RiC-O. |
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

> Esta tabla fue la recomendación inicial. La cobertura total (sección 8) las
> implementó todas por decisión de la usuaria; quedan como capacidad disponible,
> no como campo obligatorio, y el grupo demográfico con su protección.

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
| 1 | Prioridad A completa (A1 a A9). Casi todo son datos que ya existen; se agrega la propiedad en `ric_o.py`, la forma en el SHACL, el campo donde falte y la prueba de tripleta. | Hecho: atributos de 29 a 35 de 42; relaciones de 43 a 50 de 85 (sección 7). |
| 2 | Piloto con un fondo real: CCD, TRD aprobada, un lote de transferencia y unas decenas de documentos descritos. | Informe de conformidad SHACL del fondo real y medición de la IA con el módulo Evaluación. |
| 3 | Prioridad B, en el orden que pida el fondo real (no todas aplican a todos los fondos). | Hecho, junto con la prioridad C, antes del piloto (sección 8): 42 de 42 atributos y 85 de 85 relaciones. |
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

## 7. Fase 1 ejecutada (22 de octubre de 2026)

| # | Qué hace ahora el sistema | En RiC-O 1.1 | Dónde se ve |
|---|---|---|---|
| A1 | Al aplicar la TRD, cada serie o subserie queda unida a sus tipos documentales. Las ya creadas se completaron desde su alcance («Tipos documentales: …»). Una versión nueva los reemplaza. | `hasOrHadSomeMembersWithDocumentaryFormType` | Grafo RiC-O y descargas. |
| A2 | Nada: ya estaba cubierta por `hasCreator` y `hasAccumulator` (ver la corrección de la tabla A). | — | — |
| A3 | El expediente eliminado lleva su fecha de destrucción (la del acta). La digitalización del original en papel es una actividad que lo afecta y resulta en la copia digital; la migración de formato resulta en su archivo nuevo. | `hasDestructionDate`, `resultsOrResultedIn` | Grafo. |
| A4 | El original en papel y la copia digital se distinguen; el original lleva la extensión de su soporte (folios) y su signatura topográfica como un lugar con localización; cada archivo declara su tipo de representación (analógica, imagen, texto, audio, video). | `hasOrHadAnalogueInstantiation`, `hasOrHadDigitalInstantiation`, `carrierExtent`, `CarrierExtent`, `hasOrHadLocation`, `location`, `hasRepresentationType` | Grafo. |
| A5 | Estado del documento (borrador, definitivo, original, copia, copia auténtica) y «Es borrador de…». | `hasRecordState`, `isDraftOf` (nodo `RecordResourceGeneticRelation`) | Descripción: «Respuesta y borrador», «Estado del documento»; ficha de consulta. |
| A6 | «Responde a…»: la comunicación recibida tiene su respuesta, aunque estén en series distintas. | `hasReply` (nodo `RecordResourceToRecordResourceRelation`) | Igual que A5. |
| A7 | Completitud del expediente o del documento. | `integrityNote` | Descripción: «Completitud»; ficha de consulta. |
| A8 | El código del cuadro: el propio en secciones, series y subseries; el de su serie en expedientes y documentos. | `classification` | Grafo. |
| A9 | El cuadro de clasificación y el documento de cada versión de la TRD describen el fondo; cada versión aplicada (la regla) se expresa en su documento. | `describesOrDescribed`, `isOrWasExpressedBy` | Grafo. |

Pruebas: `tests/test_ric_fase1.py` (cada brecha, conformidad OWL y SHACL, ida y
vuelta exacta tablas → grafo → tablas) y `tests/test_cobertura_ric.py` (la
cobertura no baja y todo faltante tiene prioridad y motivo).

### Decisiones de la fase 1

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| A2, procedencia orgánica | Escribir `hasOrganicProvenance` además de `hasCreator`; no escribirla | No escribirla | La nota de uso de RiC-O 1.1 lo pide así; un consumidor con razonador la infiere de `hasCreator`. | Un consumidor sin razonador que busque solo la general no la encuentra. Se acepta: es lo que dice la norma. |
| Respuesta y borrador | Campos en la tabla; filas de relación | Filas de relación (con su nodo, fuente y auditoría), como la secuencia | En RiC son relaciones de primera clase; así salen con su procedencia y se pueden anular sin borrar. | Ninguno relevante. |
| Estado del documento | Texto libre; vocabulario cerrado | Vocabulario de cinco valores | RiC-AG pide valores controlados. Solo en documentos: es el dominio de `hasRecordState`. | Puede faltar un valor; se amplía en `ESTADO_DOCUMENTO`. |
| Signatura topográfica | Nota física; un lugar | Un lugar (`rico:Place`) con su localización textual | RiC-A27 es de un lugar y `hasOrHadLocation` admite cualquier cosa; la nota física ya tenía el estado de conservación. | Cada original crea su propio lugar; agruparlos por depósito queda para cuando haya un registro de depósitos. |
| Instrumentos como documentos | Incluirlos en el fondo; describirlo | Describirlo (`describesOrDescribed`) | El cuadro y la TRD no son parte del fondo sino su descripción. El perfil SHACL admite un documento que no está incluido si describe el fondo. | El FUID y la guía no salen todavía: el sistema los genera al vuelo y no los guarda; deben registrarse cuando se aprueben (siguiente paso). |
| Medición | Búsqueda de texto; desde el mapeo | Desde el mapeo, con prueba | La búsqueda de texto infló el resultado (corrección de la sección 2). | Ninguno: la prueba lo mantiene. |

## 8. Cobertura total ejecutada (22 de octubre de 2026)

Con la fase 1 hecha, la usuaria pidió completar el total: 42 de 42 atributos y
85 de 85 relaciones. Se hizo antes del piloto con un fondo real, que sigue siendo
la recomendación de RiC-AG (sección 4) y el siguiente paso. La regla fue que
cada código fuera una capacidad real: un dato que el archivista registra o que
el sistema deduce de lo que ya tiene, nunca una tripleta de relleno.

| Grupo | Qué hace ahora el sistema | En RiC-O 1.1 | Dónde se registra |
|---|---|---|---|
| Roles del documento | Receptor, coleccionista, propietario, gestor, titular de derechos de autor y materia principal, además de los que ya había. | `hasReceiver` (R029), `hasCollector` (R030), `hasOrHadOwner` (R037), `hasOrHadManager` (R038), `hasOrHadIntellectualPropertyRightsHolder` (R040), `hasOrHadMainSubject` (R020) | Descripción, «Agentes del documento». |
| Copia y original | «Es copia de…»: la copia queda unida a su original. | `hasCopy` (R012), `isOriginalOf` (R010) | Descripción, «Respuesta, borrador y copia». |
| Fecha de modificación | Rol «modificación» en las fechas del documento. | `isModificationDateOf` (R073) | Descripción, fechas. |
| Contenido y técnica | Tipo de contenido del documento (texto, imagen, plano, audio…); técnica de producción del original (manuscrito, mecanografiado, impreso…). | `hasContentOfType` (A10), `productionTechnique` y `hasProductionTechniqueType` (A33) | Descripción; perfil AGN del original físico. |
| Fechas entre niveles | Fechas predominantes de la agrupación; el sistema deduce si la fecha de cada documento está dentro de las del conjunto o se cruza con ellas. | `hasOrHadMostMembersWithCreationDate` (R083), `hasOrHadSomeMembersWithCreationDate` (R082), `isWithin` (R085), `intersects` (R086) | Descripción de la agrupación; lo demás se deduce. |
| Archivos | Componentes de un archivo (el correo y sus adjuntos); el recorte y su fuente; la migración como equivalente funcional del original. | `hasOrHadComponent` (R004), `isInstantiationAssociatedWithInstantiation` (R034), `isFunctionallyEquivalentTo` (R035) | Registro, «Componentes»; recorte y migración (automáticos). |
| Agentes | Tipo de entidad (ocho tipos del Estado colombiano), tipo de familia, ocupación, grupo demográfico; nacimiento y muerte de personas. | `hasOrHadCorporateBodyType` (A12), `hasFamilyType` (A20), `hasOrHadOccupationOfType` (A30), `hasOrHadDemographicGroup` (A15), `hasBirthDate` (R070), `hasDeathDate` (R072) | Ficha de autoridad. |
| Vínculos de autoridad | Ascendiente de, autoridad sobre, control, relación laboral, sabe de, conoce a, correspondencia, maestro de, participante en una actividad, jurisdicción de un lugar, lugares adyacentes y superpuestos. | R017, R036, R041, R046, R050, R051, R052, R053, R058, R076, R077, R078 | Ficha de autoridad, «Vínculos». |
| Hitos | Cada hito con su tipo, su fecha de ocurrencia y el orden entre hitos sucesivos. | `hasEventType` (A18), `occurredAtDate` (R084), `precedesInTime` (R009), `hasOrHadSubevent` (R006) | Línea de tiempo de la ficha. |
| TRD | El ente que vigila la TRD (el AGN o el consejo departamental). | `isOrWasEnforcedBy` (R066) | Parametrización de la TRD; se puede corregir también en una versión vigente. |

Pruebas:

- `tests/test_cobertura_ric.py`: 42 de 42 y 84 más 1 de 85, medidos desde el mapeo.
- `tests/test_ric_total.py`: arma un fondo con TRD, disposición, documentos,
  archivos, original en papel, agentes, vínculos e hitos; lo exporta completo y
  exige que **cada uno de los 127 códigos** aparezca en el grafo como propiedad
  o clase, que el grafo sea conforme al OWL y al perfil SHACL, que el grupo
  demográfico no salga en la exportación pública y que la ida y vuelta tablas →
  grafo → tablas sea exacta.

Esa prueba encontró un defecto que la medida del mapeo no veía: en RiC-O 1.1
`OccupationType` es subclase de `ActivityType`, y el perfil exige a todo tipo de
actividad su etiqueta SKOS y su esquema. Las ocupaciones salían sin esquema. Se
corrigió: los tipos de entidad, de familia, las ocupaciones y los grupos
demográficos van ahora cada uno en su esquema SKOS del fondo, como recomienda
RiC-AG.

### Decisiones de la cobertura total

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Alcance | Solo prioridad B; B y C | B y C (pedido de la usuaria) | Con todo cubierto, el piloto mide qué se usa en vez de qué falta. | Campos que un fondo institucional no usa. Se mitiga: todos son opcionales y ninguno bloquea la publicación. |
| R026, procedencia orgánica | Escribirla también; dejarla a su especialización | Dejarla a su especialización | Igual que en la fase 1: la nota de uso de RiC-O lo pide. | El mismo de la fase 1. |
| Grupo demográfico (A15) | No implementarlo; implementarlo abierto; implementarlo protegido | Protegido | Es dato sensible (Ley 1581, art. 5). Solo sale en el grafo completo, nunca en el público ni en la consulta; la ficha advierte que requiere consentimiento y finalidad. | Que se registre sin consentimiento. La advertencia no lo impide; la responsabilidad es de la entidad. |
| Fechas dentro y que se cruzan (R085, R086) | Pedirlas al archivista; deducirlas | Deducirlas de las fechas EDTF | Es un cálculo, no un juicio; pedirlo sería trabajo doble. La que solo se cruza sirve de alerta de revisión. | Solo se deducen con fechas EDTF normalizadas en el documento y en el conjunto. |
| Equivalencia funcional (R035) | Entre funciones de entidades; entre archivos | Entre el archivo migrado y su original | Es el uso que RiC-O documenta para instanciaciones y el sistema ya registra las migraciones. | No compara funciones entre entidades; si se necesita, se agrega como vínculo de autoridad. |
| Copia (R012) e isOriginalOf (R010) | Dos campos; uno | Uno («Es copia de…») y el otro se deduce | Son la misma relación vista desde cada lado. | Ninguno relevante. |
| Ocupación y tipos de agente | Texto suelto; concepto SKOS | Concepto en un esquema SKOS del fondo | RiC-AG y el perfil SHACL (ver el defecto encontrado arriba). | Las ocupaciones escritas distinto crean conceptos distintos; normalizarlas con un tesauro queda como mejora. |
| Medición | Solo el mapeo; mapeo y grafo exportado | Ambas | El mapeo dice qué puede escribir el sistema; el grafo prueba que lo escribe y que es conforme. | La prueba usa un fondo armado para ella, no un fondo real: el piloto sigue siendo necesario. |

## Anexo A. Cobertura de RiC-CM 1.0, código por código

Generado con `app/servicios/cobertura_ric.py` desde el mapeo que usa la exportación (no desde una búsqueda de texto). «Cubierto» = el sistema escribe al menos uno de los términos de RiC-O que implementan ese código, o su inversa. Desde la cobertura total (sección 8) no falta ningún código; R026 se cubre por su especialización, como pide RiC-O. La prueba `tests/test_ric_total.py` comprueba además que cada término aparece de verdad en un grafo exportado.

| Código | Estado | Términos de RiC-O que escribe el sistema, o motivo |
|---|---|---|
| RiC-A01 | Cubierto | `accruals` |
| RiC-A02 | Cubierto | `ActivityType` |
| RiC-A03 | Cubierto | `authenticityNote` |
| RiC-A04 | Cubierto | `CarrierExtent`, `carrierExtent` |
| RiC-A05 | Cubierto | `CarrierType` |
| RiC-A07 | Cubierto | `classification` |
| RiC-A08 | Cubierto | `conditionsOfAccess` |
| RiC-A09 | Cubierto | `conditionsOfUse` |
| RiC-A10 | Cubierto | `ContentType` |
| RiC-A11 | Cubierto | `geographicalCoordinates` |
| RiC-A12 | Cubierto | `CorporateBodyType` |
| RiC-A13 | Cubierto | `dateQualifier` |
| RiC-A15 | Cubierto | `DemographicGroup` |
| RiC-A17 | Cubierto | `DocumentaryFormType` |
| RiC-A18 | Cubierto | `EventType` |
| RiC-A19 | Cubierto | `expressedDate` |
| RiC-A20 | Cubierto | `FamilyType` |
| RiC-A21 | Cubierto | `history` |
| RiC-A22 | Cubierto | `Identifier`, `identifier` |
| RiC-A23 | Cubierto | `InstantiationExtent`, `instantiationExtent` |
| RiC-A24 | Cubierto | `integrityNote` |
| RiC-A25 | Cubierto | `Language` |
| RiC-A26 | Cubierto | `LegalStatus` |
| RiC-A27 | Cubierto | `location` |
| RiC-A28 | Cubierto | `AgentName`, `PlaceName`, `name`, `title` |
| RiC-A29 | Cubierto | `normalizedDateValue` |
| RiC-A30 | Cubierto | `OccupationType` |
| RiC-A31 | Cubierto | `physicalCharacteristicsNote` |
| RiC-A32 | Cubierto | `PlaceType` |
| RiC-A33 | Cubierto | `ProductionTechniqueType`, `productionTechnique` |
| RiC-A34 | Cubierto | `qualityOfRepresentationNote` |
| RiC-A35 | Cubierto | `RecordResourceExtent`, `recordResourceExtent` |
| RiC-A36 | Cubierto | `RecordSetType` |
| RiC-A37 | Cubierto | `RepresentationType` |
| RiC-A38 | Cubierto | `scopeAndContent` |
| RiC-A39 | Cubierto | `RecordState` |
| RiC-A40 | Cubierto | `structure` |
| RiC-A41 | Cubierto | `technicalCharacteristics` |
| RiC-A42 | Cubierto | `DateType` |
| RiC-A43 | Cubierto | `generalDescription` |
| RiC-A44 | Cubierto | `MandateType` |
| RiC-A45 | Cubierto | `RuleType` |
| RiC-R001 | Cubierto | `isRelatedTo` |
| RiC-R002 | Cubierto | `WholePartRelation`, `hasOrHadPart` |
| RiC-R003 | Cubierto | `hasOrHadConstituent`, `isOrWasConstituentOf` |
| RiC-R004 | Cubierto | `hasOrHadComponent`, `isOrWasComponentOf` |
| RiC-R005 | Cubierto | `GroupSubdivisionRelation`, `hasOrHadSubdivision`, `isOrWasSubdivisionOf` |
| RiC-R006 | Cubierto | `hasOrHadSubevent` |
| RiC-R007 | Cubierto | `containsOrContained`, `isOrWasContainedBy` |
| RiC-R008 | Cubierto | `SequentialRelation`, `followsOrFollowed`, `precedesOrPreceded` |
| RiC-R009 | Cubierto | `precedesInTime` |
| RiC-R010 | Cubierto | `isOriginalOf` |
| RiC-R011 | Cubierto | `hasDraft`, `isDraftOf` |
| RiC-R012 | Cubierto | `hasCopy`, `isCopyOf` |
| RiC-R013 | Cubierto | `hasReply`, `isReplyTo` |
| RiC-R014 | Cubierto | `DerivationRelation`, `hasOrHadDerivedInstantiation`, `isOrWasDerivedFromInstantiation` |
| RiC-R015 | Cubierto | `MigrationRelation`, `migratedFrom`, `migratedInto` |
| RiC-R016 | Cubierto | `AgentTemporalRelation`, `hasSuccessor`, `isSuccessorOf` |
| RiC-R017 | Cubierto | `DescendanceRelation`, `hasAncestor`, `hasDescendant` |
| RiC-R018 | Cubierto | `ChildRelation` |
| RiC-R019 | Cubierto | `hasOrHadSubject`, `isOrWasSubjectOf` |
| RiC-R020 | Cubierto | `hasOrHadMainSubject`, `isOrWasMainSubjectOf` |
| RiC-R021 | Cubierto | `describesOrDescribed` |
| RiC-R022 | Cubierto | `RecordResourceToRecordResourceRelation` |
| RiC-R023 | Cubierto | `RecordResourceGeneticRelation` |
| RiC-R024 | Cubierto | `includesOrIncluded`, `isOrWasIncludedIn` |
| RiC-R025 | Cubierto | `RecordResourceToInstantiationRelation`, `hasOrHadInstantiation`, `isOrWasInstantiationOf` |
| RiC-R026 | Cubierto por su especialización | Procedencia orgánica: el sistema escribe hasCreator (R027) y hasAccumulator (R028), subpropiedades de hasOrganicProvenance; RiC-O pide usar la general solo si no cabe una más específica. |
| RiC-R027 | Cubierto | `CreationRelation`, `hasCreator`, `isCreatorOf` |
| RiC-R028 | Cubierto | `AccumulationRelation`, `hasAccumulator`, `isAccumulatorOf` |
| RiC-R029 | Cubierto | `hasReceiver`, `isReceiverOf` |
| RiC-R030 | Cubierto | `hasCollector`, `isCollectorOf` |
| RiC-R031 | Cubierto | `hasSender`, `isSenderOf` |
| RiC-R032 | Cubierto | `hasAddressee`, `isAddresseeOf` |
| RiC-R033 | Cubierto | `ActivityDocumentationRelation`, `documentedBy`, `documents` |
| RiC-R034 | Cubierto | `isInstantiationAssociatedWithInstantiation` |
| RiC-R035 | Cubierto | `isFunctionallyEquivalentTo` |
| RiC-R036 | Cubierto | `AuthorityRelation`, `hasOrHadAuthorityOver`, `isOrWasUnderAuthorityOf` |
| RiC-R037 | Cubierto | `OwnershipRelation`, `hasOrHadOwner`, `isOrWasOwnerOf` |
| RiC-R038 | Cubierto | `ManagementRelation`, `hasOrHadManager`, `isOrWasManagerOf` |
| RiC-R039 | Cubierto | `RecordResourceHoldingRelation`, `hasOrHadHolder`, `isOrWasHolderOf` |
| RiC-R040 | Cubierto | `IntellectualPropertyRightsRelation`, `hasOrHadIntellectualPropertyRightsHolder`, `isOrWasHolderOfIntellectualPropertyRightsOf` |
| RiC-R041 | Cubierto | `AgentControlRelation`, `hasOrHadController`, `isOrWasControllerOf` |
| RiC-R042 | Cubierto | `LeadershipRelation`, `hasOrHadLeader`, `isOrWasLeaderOf` |
| RiC-R044 | Cubierto | `AgentToAgentRelation`, `isAgentAssociatedWithAgent` |
| RiC-R045 | Cubierto | `AgentHierarchicalRelation`, `hasOrHadSubordinate`, `isOrWasSubordinateTo` |
| RiC-R046 | Cubierto | `WorkRelation`, `hasOrHadWorkRelationWith` |
| RiC-R047 | Cubierto | `FamilyRelation`, `hasFamilyAssociationWith` |
| RiC-R048 | Cubierto | `SiblingRelation` |
| RiC-R049 | Cubierto | `SpouseRelation` |
| RiC-R050 | Cubierto | `KnowingOfRelation`, `knownBy`, `knowsOf` |
| RiC-R051 | Cubierto | `KnowingRelation`, `knows` |
| RiC-R052 | Cubierto | `CorrespondenceRelation`, `hasOrHadCorrespondent` |
| RiC-R053 | Cubierto | `TeachingRelation`, `hasOrHadStudent`, `hasOrHadTeacher` |
| RiC-R054 | Cubierto | `PositionHoldingRelation`, `isOrWasOccupiedBy`, `occupiesOrOccupied` |
| RiC-R055 | Cubierto | `MembershipRelation`, `hasOrHadMember`, `isOrWasMemberOf` |
| RiC-R056 | Cubierto | `PositionToGroupRelation`, `existsOrExistedIn`, `hasOrHadPosition` |
| RiC-R057 | Cubierto | `EventRelation` |
| RiC-R058 | Cubierto | `hasOrHadParticipant`, `isOrWasParticipantIn` |
| RiC-R059 | Cubierto | `affectsOrAffected`, `isOrWasAffectedBy` |
| RiC-R060 | Cubierto | `PerformanceRelation`, `isOrWasPerformedBy`, `performsOrPerformed` |
| RiC-R061 | Cubierto | `resultsOrResultedIn` |
| RiC-R062 | Cubierto | `RuleRelation` |
| RiC-R063 | Cubierto | `isOrWasRegulatedBy`, `regulatesOrRegulated` |
| RiC-R064 | Cubierto | `isOrWasExpressedBy` |
| RiC-R065 | Cubierto | `issuedBy` |
| RiC-R066 | Cubierto | `isOrWasEnforcedBy` |
| RiC-R067 | Cubierto | `MandateRelation`, `authorizedBy`, `authorizes` |
| RiC-R068 | Cubierto | `isAssociatedWithDate`, `isDateAssociatedWith` |
| RiC-R069 | Cubierto | `DateType`, `hasBeginningDate` |
| RiC-R070 | Cubierto | `hasBirthDate` |
| RiC-R071 | Cubierto | `hasEndDate` |
| RiC-R072 | Cubierto | `hasDeathDate` |
| RiC-R073 | Cubierto | `hasModificationDate`, `isModificationDateOf` |
| RiC-R074 | Cubierto | `PlaceRelation` |
| RiC-R075 | Cubierto | `hasOrHadLocation`, `isOrWasLocationOf` |
| RiC-R076 | Cubierto | `hasOrHadJurisdiction`, `isOrWasJurisdictionOf` |
| RiC-R077 | Cubierto | `isOrWasAdjacentTo` |
| RiC-R078 | Cubierto | `overlapsOrOverlapped` |
| RiC-R079 | Cubierto | `AuthorshipRelation`, `hasAuthor`, `isAuthorOf` |
| RiC-R080 | Cubierto | `hasCreationDate`, `isCreationDateOf` |
| RiC-R081 | Cubierto | `hasOrHadAllMembersWithCreationDate` |
| RiC-R082 | Cubierto | `hasOrHadSomeMembersWithCreationDate` |
| RiC-R083 | Cubierto | `hasOrHadMostMembersWithCreationDate` |
| RiC-R084 | Cubierto | `occurredAtDate` |
| RiC-R085 | Cubierto | `isWithin` |
| RiC-R086 | Cubierto | `intersects` |

## Anexo B. Cómo repetir la medición

```bash
source /home/user/venv-ricora/bin/activate
python -c "from app.servicios import cobertura_ric as c; m = c.medir(); print(m['atributos'], m['relaciones'])"
```

La prueba `tests/test_cobertura_ric.py` falla si la cobertura baja o si aparece un código sin prioridad ni motivo.

## Fuentes

- ICA, RiC-CM 1.0 (2023): https://www.ica.org/app/uploads/2024/01/ric-cm-1.0_0.pdf
- ICA, RiC-O 1.1 (2025): https://www.ica.org/ica-network/expert-groups/egad/records-in-contexts-ontology/
- ICA-EGAD, RiC-AG 0.1 (borrador, 2025): https://github.com/ICA-EGAD/RiC-AG (estrategias de implantación; preguntas sobre actividades, extensiones, instanciación, secuencias y vocabularios)
- Anuncio de RiC-AG 0.1: https://www.ica.org/egad-publishes-ric-application-guidelines-ric-ag-version-0-1/
