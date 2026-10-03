# Auditoría de conformidad con Records in Contexts (RiC-CM y RiC-O)

**Fecha:** 3 de octubre de 2026 · **Estado del cierre:** ver `documentacion/cierre-auditoria-ric.md` y el panel de hallazgos (cada hallazgo con su identificador) · **Alcance:** el código del repositorio, en la rama `claude/plataforma-base` · **Naturaleza:** solo examen. No se modificó ningún código para hacerla.

Esta auditoría responde con evidencia una pregunta: ¿RICORA modela Records in Contexts en profundidad, o solo toma prestados sus nombres? Cada hallazgo hace una de dos cosas:

- cita el archivo y la línea donde vive lo evaluado;
- o deja constancia de que se buscó (en qué lugares y con qué términos) y no se encontró.

Los prompts de especificación y los documentos del propio equipo se usaron como **vara de medir**, nunca como evidencia. Cuando un documento del equipo afirma algo que el código no hace, eso es un hallazgo (ver CM-11 / O-19).

## 1. Resultado en una tabla

| Bloque | Hallazgos | Conformes | Incompletos o no conformes | No implementados |
|---|---|---|---|---|
| Rama RiC-CM (modelo conceptual) | 22 | 3 | 18 | 1 |
| Rama RiC-O (ontología) | 33 | 24 | 9 | 0 |
| Normas complementarias · Ingesta y Descripción | 20 | 5 | 11 | 4 |
| Normas complementarias · Vocabularios e Instrumentos | 17 | 2 | 12 | 3 |
| Normas complementarias · Preservación | 14 | 3 | 8 | 3 |
| **Total** | **106** | **37** | **58** | **11** |

Ningún bloque queda en «conforme» de forma global. La conclusión honesta tiene dos caras.

- **Lo que sí es RiC de verdad, y es lo más difícil:**
  - el sistema no es un gestor documental con nombres prestados;
  - las entidades viven en tablas propias;
  - las relaciones son filas tipadas con su código RiC-CM;
  - el tipo de actividad es un vocabulario controlado con jerarquía SKOS;
  - el mecanismo es un registro reutilizable con versión;
  - las fechas se normalizan en EDTF;
  - el RDF que se exporta no inventa ningún término. Se comprobó de forma mecánica: los 111 términos del mapeo y las 258 tripletas de un fondo de prueba con las 27 relaciones, contrastados con el OWL oficial de RiC-O 1.1 (O-27).
- **Lo que falta:**
  - una parte del modelo conceptual quedó a medio camino: cargo sin ocupante, Record Set que solo nace de archivos, Rule inexistente, cardinalidades más estrictas que el estándar;
  - varias normas complementarias están más prometidas que construidas: SPARQL, EAD3/EAC-CPF/IIIF, veraPDF/JHOVE, respaldo de la base de datos, TRD;
  - hay **fugas de lo reservado**, que es lo más urgente.

## 2. Lo que no puede esperar

Estas son las prioridades, ordenadas por el daño posible, no por el número de hallazgo.

| # | Hallazgo | Por qué es urgente | Evidencia verificada por el auditor |
|---|---|---|---|
| 1 | **INS-02 · Fugas de información clasificada o reservada (Ley 1712)** | El rol consulta ve el título de partes y de documentos hermanos reservados en la ficha. Un archivo declarado reservado se exporta en el RDF y en `/id/`. Un agente que solo aparece en un documento reservado se publica si está vinculado a otro agente público. | `app/servicios/exportacion_rico.py:98-113` solo mira declaraciones sobre descripciones, no sobre instanciaciones. `app/servicios/consulta.py:35-47` copia `partes`, `secuencia` e `instanciaciones` sin filtrar. Una prueba reproducible pasó 4/4, es decir, **confirmó** las cuatro fugas. *Cerrado el mismo día: esa prueba se invirtió y quedó como regresión en `tests/test_cierre_ins02.py` (ver `cierre-auditoria-ric.md`).* |
| 2 | **PRE-10 · Base de datos sin respaldo ni simulacro de restauración** | Las descripciones, las relaciones, la auditoría y las huellas de referencia de la fijeza viven solo en PostgreSQL. Sin respaldo, perder el disco es perder el fondo descrito. | `app/routers/preservacion.py:118-119` lo reconoce: `"simulacro_base_de_datos": None`. Se buscó `pg_dump` y `pg_restore` en todo el repositorio, sin resultado. |
| 3 | **O-28 · Nombre de propiedad inventado a la vista del usuario** | `rico:hasOrHadDocumentaryFormType` **no existe** en RiC-O 1.1 (la real es `hasDocumentaryFormType`). Aparece en el grafo, en su API y en la columna «Propiedad RiC-O» del Excel. No llega al RDF, pero es justo la falta de disciplina que el anexo prohíbe. | `app/servicios/grafo.py:286`; el término aparece 0 veces en `app/recursos/ric-o/RiC-O_1-1.rdf`. |
| 4 | **CM-11 / O-19 · Un documento del equipo afirma algo falso** | La verificación de los 13 puntos dice que la versión del mecanismo se exporta con `rico:technicalCharacteristics`, pero el exportador descarta todos los mecanismos. | `app/servicios/exportacion_rico.py:214` (`e.subtipo == "mecanismo"` → `None`) frente a `documentacion/anexos/verificacion-ric-o-1-1.md`, fila 6. |
| 5 | **PRE-07 · La segunda copia comparte disco, servidor y usuario** | Es automática y se verifica, pero ante la falla del disco o un error humano no protege nada. | Ver el anexo 5. |
| 6 | **PRE-08 · La fijeza periódica puede saltarse un ciclo entero** | La pasada se marca como hecha **antes** de recorrer. Si un despliegue reinicia el trabajador a mitad de camino, lo que faltaba no se verifica hasta 30 días después. | `app/servicios/preservacion.py:292-298`. |

## 3. Cuestionamientos a la propia especificación

La auditoría encontró tres casos en los que no es justo cargarle la brecha al código.

- **ING-01 e ING-02 (SIP BagIt y procedencia del lote):** los exige la sección 6 del prompt de auditoría, pero **el prompt de ingesta actualizado no los pide**. Son brechas de especificación. Se reportan como «no implementado» porque la regla es reportar lo que el código hace, pero la acción correcta es decidir si se quieren, no darlas por incumplidas.
- **CM-21 (cardinalidades):** RiC-O 1.1 no declara ninguna propiedad funcional. Cada «a lo sumo uno» del sistema (un superior por recurso, un custodio, un tipo de actividad por actividad) es más estricto que el estándar. A veces es una decisión de negocio defendible, por ejemplo el árbol orgánico de un fondo colombiano. Tiene que estar escrita como decisión, no quedar implícita.
- **INS-01 (RDF sin autenticación):** el prompt pide que la exportación responda sin sesión. Hoy responde 401, salvo `/id/` si el administrador lo enciende. Con las fugas del hallazgo INS-02 abiertas, **abrirla sería un error**. El orden correcto es primero cerrar las fugas y después publicar.

## 4. Cómo se hizo

- **Cinco frentes**, cada uno con un anexo propio en `documentacion/anexos/auditoria-conformidad-ric/`:
  1. RiC-CM, entidad por entidad;
  2. RiC-O, propiedad por propiedad, con comprobación mecánica contra el OWL;
  3. Ingesta y Descripción (OAIS, BagIt, EDTF, ISAD-G, cuadro de clasificación y TRD);
  4. Vocabularios e Instrumentos (ISAAR-CPF, ISDF, SKOS, Ley 1712, SPARQL, EAD3, EAC-CPF, IIIF);
  5. Preservación (PREMIS, segunda copia, veraPDF y JHOVE, respaldo, fijeza, NDSA, OAIS).
- **Regla de evidencia:** sin cita `ruta:línea` no hay «implementado». Sin búsqueda explícita, con sus términos, no hay «no implementado». Código presente no es capacidad operando: se revisó si algo lo ejecuta de verdad (trabajador, despliegue, configuración).
- **Prueba de profundidad**, aplicada en cada caso dudoso: si dos personas describen el mismo concepto con palabras distintas, ¿terminan en dos textos libres o en el mismo registro controlado?
- **Verificación cruzada:** el auditor comprobó por su cuenta las afirmaciones de más peso. Ejecutó la prueba de fugas y leyó las líneas citadas en INS-02, PRE-08, PRE-10, CM-11, O-28 y VOC-02. Al hacerlo corrigió una conclusión: `rico:hasOrHadRuleType`, que muestra la ficha de autoridad, **sí existe** en el OWL. Ahí hay una incoherencia con el exportador, no una invención.
- **Pruebas del repositorio:** pasan las de RiC-O, exportación, autoridad y descripción. Dos observaciones:
  - `tests/test_ingesta.py::test_ocr_guarda_su_confianza_como_promedio_por_palabra` falló 1 de 3 veces: es intermitente y hay que estabilizarla, no ignorarla;
  - 14 de las 27 relaciones del mapeo no tienen ninguna prueba que afirme su tripleta RDF (O-31).

## 5. Qué no hace esta auditoría

- No corrige código.
- No sustituye la verificación del OWL de los 13 puntos pendientes. Esa ya se hizo aparte (`anexos/verificacion-ric-o-1-1.md`), y aquí solo se comprobó que el código respeta lo decidido allí.
- No evalúa el motor de inteligencia artificial.
- No emite un juicio sobre la tesis.

## 6. Cómo pasarla al panel de hallazgos

`anexos/auditoria-conformidad-ric/hallazgos-para-panel.json` contiene los **69 hallazgos no conformes**, con los campos del panel de hallazgos de conformidad del módulo de auditoría:

- `titulo`, con su identificador, por ejemplo «INS-02 · …»;
- `descripcion`, con la rama, la clasificación, la evidencia y el razonamiento;
- `componentes`, con los módulos afectados;
- `accion`, la acción recomendada.

Los 37 conformes no se cargan, porque el panel registra brechas. Se cargan como «abiertos»; el título y la descripción quedan fijos, como exige el panel, y solo cambian el estado y la acción a medida que se corrigen.

## 7. Índice completo de hallazgos

El detalle de cada uno (evidencia, prueba, razonamiento y acción) está en el anexo de su bloque.

### Rama RiC-CM (modelo conceptual)

| ID | Hallazgo | Rama o norma | Clasificación |
|---|---|---|---|
| CM-01 | Record Resource: una tabla, y el subtipo se deduce del nivel | RiC-CM | Incompleto o no conforme |
| CM-02 | Record Set (fondo, sección, serie, subserie, expediente): los niveles intermedios solo nacen de archivos, y la sección no se puede crear | RiC-CM | Incompleto o no conforme |
| CM-03 | Record y parte documental: los documentos de un expediente nunca llegan a ser Records | RiC-CM | Incompleto o no conforme |
| CM-04 | Instantiation: tabla propia y rica en datos técnicos, pero solo digital, de un único recurso y sin las relaciones entre instanciaciones que declara el catálogo | RiC-CM | Incompleto o no conforme |
| CM-05 | Agent (supertipo) y su enumerado de subtipos: declarado en Python, sin restricción en la base de datos, y duplicado | RiC-CM | Incompleto o no conforme |
| CM-06 | Persona | RiC-CM | Incompleto o no conforme |
| CM-07 | Grupo (Group usado directamente) | RiC-CM | Incompleto o no conforme |
| CM-08 | Entidad corporativa | RiC-CM (con ISAAR-CPF) | Conforme |
| CM-09 | Familia | RiC-CM | Incompleto o no conforme |
| CM-10 | Cargo (Position): solo admite jerarquía entre cargos, nunca se une a quien lo ocupa ni al grupo donde existe | RiC-CM | Incompleto o no conforme |
| CM-11 | Mecanismo (Mechanism): registro propio y reutilizable con versión (profundo), pero excluido de la exportación y unido a las acciones técnicas solo por clave foránea | RiC-CM | Incompleto o no conforme |
| CM-12 | Lugar (Place): nombres históricos, coordenadas, tipo y jerarquía presentes; jerarquía de un solo superior sin tiempo y lugar del documento siempre como «tema» | RiC-CM | Incompleto o no conforme |
| CM-13 | Event (no Activity): tabla «hitos» atada a un solo agente | RiC-CM | Incompleto o no conforme |
| CM-14 | Activity: registro del vocabulario con su cadena tipo–agente–mandato–subactividad; sin vínculo con Event ni con las acciones técnicas | RiC-CM | Incompleto o no conforme |
| CM-15 | ActivityType (tipo de actividad / función) como vocabulario controlado con jerarquía SKOS | RiC-CM (con SKOS) | Conforme |
| CM-16 | Date: entidad propia con subtipo y EDTF, pero dispersa en cadenas para agentes, hitos, relaciones y conjuntos | RiC-CM (con EDTF) | Incompleto o no conforme |
| CM-17 | Mandate | RiC-CM | Conforme |
| CM-18 | Rule (distinta de Mandate): no existe | RiC-CM | No implementado |
| CM-19 | Transversal: la tabla polimórfica de relaciones no restringe dominio ni rango al escribir | RiC-CM | Incompleto o no conforme |
| CM-20 | Transversal: catálogo de relaciones y enumerados declarados que no se implementan | RiC-CM | Incompleto o no conforme |
| CM-21 | Transversal: cardinalidades más estrictas que RiC-O | RiC-CM | Incompleto o no conforme |
| CM-22 | Transversal: las acciones técnicas no se modelan como Activity ejercida por un Mechanism | RiC-CM (con PREMIS) | Incompleto o no conforme |

### Rama RiC-O (ontología)

| ID | Hallazgo | Rama o norma | Clasificación |
|---|---|---|---|
| O-01 | documents / documentedBy (Record Resource → Activity) | RiC-O | Conforme |
| O-02 | hasOrHadPart / isOrWasPartOf e includesOrIncluded (jerarquía documental) | RiC-O | Conforme |
| O-03 | hasOrHadInstantiation / isOrWasInstantiationOf | RiC-O | Conforme |
| O-04 | hasCreator / isCreatorOf | RiC-O | Conforme |
| O-05 | performsOrPerformed / isOrWasPerformedBy | RiC-O | Conforme |
| O-06 | authorizedBy / authorizes (Mandate → Agent) | RiC-O | Conforme |
| O-07 | hasSuccessor / isSuccessorOf | RiC-O | Conforme |
| O-08 | hasOrHadSubordinate / isOrWasSubordinateTo | RiC-O | Conforme |
| O-09 | migratedInto / migratedFrom | RiC-O | Conforme |
| O-10 | hasOrHadIdentifier / isOrWasIdentifierOf | RiC-O | Conforme |
| O-11 | hasActivityType (Activity → ActivityType) | RiC-O | Conforme |
| O-12 | expressedDate / normalizedDateValue / dateQualifier (clase Date) | RiC-O | Incompleto o no conforme |
| O-13 | hasDirectSubevent / isDirectSubeventOf | RiC-O | Conforme |
| O-14 | Punto 1 — dominio y rango de performsOrPerformed | RiC-O | Conforme |
| O-15 | Punto 2 — sin subclases de Date | RiC-O | Conforme |
| O-16 | Punto 3 — relación asociativa entre agentes | RiC-O | Conforme |
| O-17 | Punto 4 — Group instanciable | RiC-O | Conforme |
| O-18 | Punto 5 — evento institucional (hito) y su agente | RiC-O | Conforme |
| O-19 | Punto 6 — versión de un Mechanism (technicalCharacteristics) | RiC-O | Incompleto o no conforme |
| O-20 | Punto 7 — mandato que crea un agente o un tipo de actividad | RiC-O | Conforme |
| O-21 | Punto 8 — vínculo función ↔ serie (TRD) | RiC-O | Conforme |
| O-22 | Punto 9 — jerarquía y tipo de lugar | RiC-O | Conforme |
| O-23 | Punto 10 — secuencia entre documentos | RiC-O | Conforme |
| O-24 | Punto 11 — custodia distinta de la producción | RiC-O | Conforme |
| O-25 | Punto 12 — jerarquía normativa entre mandatos | RiC-O | Conforme |
| O-26 | Punto 13 — idioma, condiciones de acceso y de uso | RiC-O | Incompleto o no conforme |
| O-27 | Términos RiC-O emitidos en la exportación RDF: todos existen y se usan con su tipo, dominio y rango | RiC-O | Conforme |
| O-28 | Nombres RiC-O inexistentes u obsoletos en la capa de presentación (API, hoja de cálculo, interfaz) | RiC-O | Incompleto o no conforme |
| O-29 | La fecha de expedición de un mandato se descarta en la exportación | RiC-O | Incompleto o no conforme |
| O-30 | owl:sameAs hacia autoridades externas con IRIs no canónicos; etiqueta de idioma no canónica | RiC-O (con ISAAR-CPF) | Incompleto o no conforme |
| O-31 | Ejecución de las pruebas existentes y alcance real | RiC-O | Incompleto o no conforme |
| O-32 | Validación SHACL de la exportación: existe, qué cubre y cuándo corre | RiC-O | Incompleto o no conforme |
| O-33 | Códigos del catálogo de relaciones sin mapeo RiC-O ni escritor | RiC-O | Incompleto o no conforme |

### Normas complementarias · Ingesta y Descripción

| ID | Hallazgo | Rama o norma | Clasificación |
|---|---|---|---|
| ING-01 | SIP conforme a BagIt al confirmar un lote | BagIt (RFC 8493) / OAIS (SIP) | No implementado |
| ING-02 | Metadatos de procedencia del lote (remitente, dependencia de origen, acta de transferencia) | OAIS (Producer/SIP), ISAD-G 3.2.4 (Forma de ingreso), Ley 594/AGN (transferencias documentales) | No implementado |
| ING-03 | OAIS: recepción con huella SHA-256 y detección de duplicados | OAIS (Receive Submission / Quality Assurance), PREMIS (fixity) | Conforme |
| ING-04 | Identificación de formato contra PRONOM con Siegfried | OAIS (Quality Assurance) / PREMIS (format) / PRONOM | Conforme |
| ING-05 | OCR con confianza por palabra y marca de baja confianza | OAIS (Quality Assurance) / requisito propio del prompt de ingesta §3bis | Conforme |
| ING-06 | OAIS aplicado a la ingesta: funciones de la entidad Ingest | OAIS (ISO 14721: Receive Submission, Quality Assurance, Generate AIP, Generate Descriptive Info, Coordinate Updates) | Incompleto o no conforme |
| ING-07 | Enlace del panel de alertas al espacio de descripción para «formato no identificado» | requisito del prompt de ingesta §9 | Incompleto o no conforme |
| ING-08 | Roles con acceso a los endpoints de ingesta | requisito del prompt de ingesta §5 | Incompleto o no conforme |
| ING-09 | Recorrido de los compromisos de verificación del prompt de ingesta | prompt del módulo 1 (§3, §3bis, §4-§7, §10, §11) | Incompleto o no conforme |
| DES-01 | Fechas EDTF en tres subtipos con calificador de incertidumbre y aproximación | EDTF (ISO 8601-2, niveles 0-1 y conjunto del nivel 2) | Conforme |
| DES-02 | Fechas extremas de fondo y expedientes guardadas como texto libre, fuera de EDTF | EDTF / ISAD-G 3.1.3 | Incompleto o no conforme |
| DES-03 | Desvíos menores del subconjunto EDTF declarado | EDTF | Incompleto o no conforme |
| DES-04 | Las relaciones nuevas entre documentos (parte, precede, sigue, documenta) como relaciones tipadas | RiC-CM (relaciones) aplicado por el prompt de descripción; complemento a la norma de §6 | Conforme |
| DES-05 | Relación de custodia: existe, pero sin fechas, sin cadena y solo sobre el Record Resource | RiC-CM (custodia, RiC-R039i) / ISAD-G 3.2.3 | Incompleto o no conforme |
| DES-06 | Historia de custodia narrativa (historia archivística) | ISAD-G 3.2.3 (Historia archivística) / RiC-CM (atributo History de Record Resource) | No implementado |
| DES-07 | Cobertura de ISAD-G: 7 áreas, 26 elementos | ISAD-G | Incompleto o no conforme |
| DES-08 | Cuadro de clasificación documental (fondo-sección-subsección-serie-subserie con códigos) | CCD/TRD (metodología AGN Colombia) | Incompleto o no conforme |
| DES-09 | TRD: tiempos de retención y disposición final heredados | CCD/TRD (Acuerdo AGN 004/2019) / ISAD-G 3.3.2 | No implementado |
| DES-10 | Contexto de vocabulario para el motor: léxico (trigramas) en lugar de búsqueda semántica | requisito del prompt de descripción §4 (cuarto principio) | Incompleto o no conforme |
| DES-11 | Recorrido de los compromisos del prompt de descripción | prompt del módulo 2 (§2-§12) | Incompleto o no conforme |

### Normas complementarias · Vocabularios e Instrumentos

| ID | Hallazgo | Rama o norma | Clasificación |
|---|---|---|---|
| VOC-01 | Ficha de agente ISAAR-CPF: cuatro áreas, pero control e identificación incompletos | ISAAR-CPF | Incompleto o no conforme |
| VOC-02 | Relaciones de parentesco, cargo y membresía: no se pueden declarar como relaciones tipadas | ISAAR-CPF (5.3.2) / RiC-O | No implementado |
| VOC-03 | Tipo de actividad (ISDF): poco más que nombre y jerarquía SKOS | ISDF | Incompleto o no conforme |
| VOC-04 | SKOS: broader/narrower y prefLabel sí; altLabel y notation no | SKOS | Incompleto o no conforme |
| VOC-05 | Detección de duplicados y fusión | ISAAR-CPF / RiC-CM (registro único y reutilizable) | Incompleto o no conforme |
| VOC-06 | Relaciones entre agentes: tipadas en la base, pero sin fechas ni nota en RDF | RiC-O / ISAAR-CPF 5.3.3–5.3.4 | Incompleto o no conforme |
| VOC-07 | Mecanismo con versión como registro reutilizable | RiC-CM (Mechanism RiC-E13) / PREMIS Agent | Incompleto o no conforme |
| VOC-08 | Lugar ampliado, actividad y mandato (compromisos 5bis y 6 del prompt) | RiC-CM / RiC-O | Conforme |
| VOC-09 | Compromisos del prompt de vocabularios sin implementar o parciales (lista) | ISAAR-CPF / ISDF / SKOS | Incompleto o no conforme |
| INS-01 | La exportación RDF (Turtle/JSON-LD) NO responde sin autenticación; las URI solo si el administrador lo enciende | RiC-O / Datos abiertos (Ley 1712, art. 11) | Incompleto o no conforme |
| INS-02 | Filtro por nivel de acceso Ley 1712: funciona por descripción, pero hay fugas en la ficha del catálogo y en el RDF | Ley 1712 de 2014 (arts. 18–19) | Incompleto o no conforme |
| INS-03 | La guía del fondo incluye lo reservado y lo envía al motor externo | Ley 1712 de 2014 | Incompleto o no conforme |
| INS-04 | No hay punto SPARQL | SPARQL | No implementado |
| INS-05 | EAD3, EAC-CPF e IIIF: no existen | EAD3, EAC-CPF, IIIF | No implementado |
| INS-06 | Inventario FUID: generado y con pendientes marcados, pero con columnas incompletas frente al Acuerdo 042 de 2002 | CCD/TRD (AGN, FUID) | Incompleto o no conforme |
| INS-07 | Catálogo, guía e índice (compromisos del prompt de instrumentos) | ISAD-G / instrumentos de descripción | Conforme |
| INS-08 | Compromisos de instrumentos sin implementar o parciales (lista) | Ley 1712 / SPARQL / EAD3 / EAC-CPF / IIIF / CCD-TRD | Incompleto o no conforme |

### Normas complementarias · Preservación

| ID | Hallazgo | Rama o norma | Clasificación |
|---|---|---|---|
| PRE-01 | Las cuatro entidades PREMIS por instanciación: estructura, alcance y validación | PREMIS | Incompleto o no conforme |
| PRE-02 | Eventos PREMIS: fechas aproximadas, resultado sin vocabulario y eventos ausentes | PREMIS | Incompleto o no conforme |
| PRE-03 | Agente PREMIS de software = Mechanism del vocabulario con su versión | PREMIS | Conforme |
| PRE-04 | Agente PREMIS de tipo persona: sale de la tabla de usuarios, no del vocabulario del fondo | PREMIS | Incompleto o no conforme |
| PRE-05 | Entidad Derechos de PREMIS (versión mínima, heredable) | PREMIS | Conforme |
| PRE-06 | Los recortes (partes documentales) reciben un PREMIS falso: evento de «ingreso» y ninguna relación con su origen | PREMIS | Incompleto o no conforme |
| PRE-07 | Segunda copia: automática y verificada, pero no independiente del equipo | OAIS (Almacenamiento de Archivo) | Incompleto o no conforme |
| PRE-08 | Verificación de fijeza periódica | NDSA (Integridad) | Incompleto o no conforme |
| PRE-09 | Validación formal de PDF/A (veraPDF) y TIFF (JHOVE) | OAIS (Planificación de la Preservación) | No implementado |
| PRE-10 | Respaldo de la base de datos y simulacro de restauración | OAIS (Gestión de Datos, Almacenamiento) | No implementado |
| PRE-11 | OAIS: AIP en BagIt (instanciación y expediente) con PREMIS y PDI de cinco categorías | OAIS | Conforme |
| PRE-12 | OAIS: paquete de difusión (DIP) | OAIS | No implementado |
| PRE-13 | NDSA Levels of Digital Preservation 2.0: nivel alcanzado por área | NDSA | Incompleto o no conforme |
| PRE-14 | Compromisos del prompt de preservación: estado de cumplimiento | OAIS | Incompleto o no conforme |
