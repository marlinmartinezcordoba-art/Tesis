# Módulo 2 · Descripción multinivel asistida por inteligencia artificial

**Versión:** 2 (actualizada según el prompt «Módulo 2, versión actualizada, profunda» y la maqueta «Sistema RIC · Auditoría», pestaña Decisiones de IA).
**Estado:** entregado, pendiente de validación.

**Qué cambió frente a la versión 1:**
- fechas con su precisión real, en formato extendido EDTF y con tres subtipos: simple, rango y conjunto;
- contexto institucional: **Actividad**, **Tipo de actividad** y **Mandato o norma**, con la cadena documento → actividad → tipo de actividad → mandato y el agente que la ejerce;
- seis tipos reutilizables en el vocabulario, todos con la misma verificación por similitud;
- relaciones entre agentes: subordinación, sucesión y asociación;
- el agente de subtipo «mecanismo», para actores de software;
- **un evento de auditoría por cada decisión de la archivista sobre cada propuesta del motor**, con el modelo y la versión de la instrucción, y el panel «Decisiones de IA» con su hoja de cálculo. Es la fuente del capítulo de evaluación (objetivo 3 de la tesis).

---

## 1. Propósito

El módulo toma uno o varios documentos ya listos desde la ingesta y le pide al motor de análisis una propuesta de descripción archivística completa según Records in Contexts. La propuesta incluye:
- agentes, lugares y fechas con su precisión real;
- el contexto institucional (actividad, tipo de actividad y mandato).

Luego la archivista valida cada propuesta, y el resultado se publica como un grafo de entidades y relaciones reales.

Cada decisión de validación queda registrada como evidencia de qué propuso la máquina y qué decidió la persona.

## 2. Auditoría (qué se revisó antes de construirlo)

**Documentos revisados:**
- el prompt actualizado del módulo 2 (secciones 1 a 12), que reemplaza las dos versiones anteriores;
- la maqueta «Sistema RIC · Auditoría», pestaña Decisiones de IA: cifras de aceptadas, corregidas y rechazadas; tabla con lo propuesto, el valor final, la decisión y la versión de la instrucción; filtros por tipo, decisión y periodo;
- el **archivo oficial de la ontología RiC-O 1.1** (`RiC-O_1-1.rdf`), consultado propiedad por propiedad;
- el PDF oficial de RiC-CM 1.0, para los códigos de entidad.

**Tres hallazgos en el archivo de la ontología:**

1. **«authorizes» no une el mandato con la actividad.** En RiC-O 1.1, `authorizes` (RiC-R067) va de **Mandate a Agent**; su inversa `authorizedBy` va de Agent a Mandate. Usarla sobre una Actividad viola el dominio de la propiedad. Así se decidió con la autora, que eligió la opción recomendada:
   - el mandato **regula** la actividad: `regulatesOrRegulated`, RiC-R063 (Rule → Thing, y Mandate es una Rule);
   - el mismo mandato **autoriza** al agente que la ejerce: R067, creada sola.
2. **La relación asociativa entre agentes**, que el prompt dejaba pendiente de confirmar, es `isAgentAssociatedWithAgent` (RiC-R044). Las otras dos están confirmadas:
   - `hasOrHadSubordinate` (R045), con inversa `isOrWasSubordinateTo`;
   - `hasSuccessor` (R016), con inversa `isSuccessorOf`.
3. **RiC-O 1.1 eliminó las clases SingleDate, DateRange y DateSet** (cambio del 22 de septiembre de 2023, registrado en el propio archivo). Ahora existe una sola `rico:Date`, con:
   - su tipo (`hasDateType`);
   - `expressedDate` (RiC-A19);
   - `normalizedDateValue` (RiC-A29), que admite EDTF;
   - `dateQualifier` (RiC-A13).

   Los tres subtipos del prompt se conservan en el sistema y se exportan de esa forma. Siguen siendo correctos frente a RiC-CM 1.0, donde son entidades.

**Confirmado:** `hasActivityType` (Activity → ActivityType) y `performsOrPerformed` (RiC-R060i) existen tal como dice el prompt. El tipo de actividad es una clase de tipos (`rico:ActivityType`), no una entidad «Función», que no existe en la ontología. Esto coincide con la corrección que hace el prompt.

**Error que corregí en el sistema durante este trabajo:** al fusionar dos entidades del vocabulario solo se redirigían las relaciones donde la entidad era el destino. Con la cadena de la actividad, el agente y el mandato también son origen de relaciones, y esas se habrían quedado apuntando a la entidad absorbida. Se agregó `origen_original_id` y la fusión ahora redirige los dos sentidos, con prueba.

## 3. Problema que resuelve

Un fondo histórico rara vez da fechas exactas. «Hacia 1948», «década de 1940» o «entre 1948 y 1952» son datos archivísticos, no errores que haya que forzar a un día.

Además, el contexto que da sentido a un documento no es solo quién lo produjo. Importa también:
- en ejercicio de qué competencia lo produjo;
- con qué norma la ejercía.

Y para evaluar la asistencia de la IA (objetivo 3) hace falta saber, propuesta por propuesta, qué aceptó, qué corrigió y qué descartó la archivista.

## 4. Usuarios

| Rol | Qué hace |
|---|---|
| Archivista, administrador | Describe, valida, publica, reabre y corrige |
| Revisor | Ve la cola y las descripciones publicadas, sin modificar |
| Consulta | Solo la ficha pública en el catálogo |
| Administrador | Además, ve el panel «Decisiones de IA» y descarga su hoja de cálculo |

## 5. Casos de uso

1. Describir un documento suelto o un conjunto (expediente, subserie o serie).
2. Aceptar, editar o descartar cada entidad propuesta, de siete tipos: agente, lugar, fecha, forma documental, actividad, tipo de actividad y mandato.
3. Ajustar una fecha directamente sobre la propuesta: subtipo, precisión y calificador, viendo en vivo cómo se lee.
4. Completar la cadena de una actividad: su tipo, el agente que la ejerce, el mandato que la regula y su periodo.
5. Resolver en el vocabulario, para los seis tipos reutilizables, si la entidad ya existe.
6. Publicar sin actividad ni mandato cuando el documento no permite inferirlos.
7. Relacionar dos agentes: subordinación, sucesión o asociación.
8. (Administrador) Revisar las decisiones de validación y exportarlas para la evaluación.

## 6. Entidades RiC involucradas

| Entidad | Dónde vive | Qué es aquí |
|---|---|---|
| Record Resource (RiC-E02): Record (E04) o Record Set (E03) | `recursos_documentales` | Nivel, título, alcance y contenido (RiC-A38), forma documental (RiC-A17) |
| Agent (E07), con los subtipos persona (E08), entidad corporativa (E11), cargo (E12), familia (E10) y **mecanismo (E13)** | vocabulario, clase `agente` | Registro único por fondo |
| Place (E22) | vocabulario, clase `lugar` | Registro único por fondo |
| Tipo de forma documental (A17) | vocabulario, clase `forma_documental` | Registro único por fondo |
| **Activity (E15)** | vocabulario, clase `actividad` | El ejercicio concreto y fechado de una competencia por un agente. Reutilizable entre los documentos de esa misma actuación |
| **Tipo de actividad** (`rico:ActivityType`) | vocabulario, clase `tipo_actividad` | La competencia estable (p. ej. «Policía local»). Valor controlado, nunca conectado directo a un documento |
| **Mandate (E17)** | vocabulario, clase `mandato`, con subtipo ley / decreto / ordenanza / acuerdo / resolución / otro (`rico:MandateType`) | La norma que regula la actividad |
| Date (E18), con los subtipos Single Date, Date Range y Date Set | `fechas` | Expresión tal como aparece (A19), EDTF (A29), subtipo y límites |
| Instantiation (E06) | `instanciaciones` | El archivo técnico (módulos 1 y 5) |

**Migración de lo anterior:** las actividades de la versión 1 pasaron al vocabulario con su mismo identificador, y sus relaciones se reapuntaron. La tabla `actividades` se conserva sin uso: nada se borra. Se probó con una actividad real de la versión anterior.

## 7. Relaciones RiC involucradas

El catálogo curado pasa de 35 a **40** códigos. Todos se verificaron en el archivo oficial de RiC-O 1.1.

| Qué | Código | URI RiC-O | Sentido |
|---|---|---|---|
| Productor / remitente / destinatario | R027 / R031 / R032 | rico:hasCreator / hasSender / hasAddressee | documento → agente |
| Agente, lugar o mandato mencionado | R019 | rico:hasOrHadSubject | documento → entidad |
| Fecha de creación | R080 | rico:isCreationDateOf | fecha → documento |
| Actividad documentada | R033 | rico:documents | documento → actividad |
| **Tipo de la actividad** | (propiedad de tipo, sin código R) | rico:hasActivityType | actividad → tipo |
| **Agente que la ejerce** | R060i | rico:performsOrPerformed | agente → actividad |
| **Mandato que la regula** | R063 | rico:regulatesOrRegulated | mandato → actividad |
| **Mandato que autoriza al agente** | R067 | rico:authorizes | mandato → agente |
| **Periodo de la actividad** | R068 | rico:isDateAssociatedWith | fecha → actividad |
| **Expedición del mandato** | R080 | rico:isCreationDateOf | fecha → mandato |
| **Subordinación entre agentes** | R045 | rico:hasOrHadSubordinate (inversa isOrWasSubordinateTo) | agente → agente |
| **Sucesión** | R016 | rico:hasSuccessor (inversa isSuccessorOf) | agente → agente |
| **Asociación** | R044 | rico:isAgentAssociatedWithAgent (simétrica) | agente ↔ agente |
| Inclusión / archivo técnico | R024 / R025 | rico:includesOrIncluded / hasOrHadInstantiation | — |

**Fuera de RiC, a propósito:** la jerarquía función → subfunción entre tipos de actividad se hará con SKOS (`skos:broader` / `skos:narrower`) desde el módulo de vocabularios, como dice el prompt (§2 y §9). No se construye aquí.

## 8. Funcionalidades

- **Fechas EDTF.** Una fecha nunca se escribe en código. Los controles de su tarjeta construyen la expresión según el subtipo:
  - **simple:** año, década, siglo o desconocido; mes y día opcionales; calificador exacta, aproximada, incierta o ambas;
  - **rango:** desde y hasta, cada uno con su calificador o «desconocido»;
  - **conjunto:** varias fechas sueltas.

  La forma legible en español se ve en vivo junto a la expresión. Por ejemplo, **«c. 1948» `1948~`**, **«década de 1940» `194X`**, **«de 1948 a 1952» `1948/1952`** o **«15 de enero de 1948 y 2 de marzo de 1948»** `{1948-01-15,1948-03-02}`. Una fecha sin completar no se puede aceptar.
- **Cadena de la actividad.** La tarjeta de actividad muestra una línea con su tipo, el agente, el mandato y el periodo, y tres selectores (Tipo de actividad, Ejercida por, Mandato o norma) con las entidades de la misma descripción, más un periodo opcional.

  La tarjeta del tipo de actividad dice a qué actividad está asignado. Si no está asignado a ninguna, impide publicar: un documento no se conecta a un tipo en abstracto.
- **Mandato.** Tiene el tipo de instrumento y la fecha de expedición. Si no regula ninguna actividad del documento, queda como mencionado (R019).
- **Reutilización sin duplicar la cadena.** Si otro documento de la misma actuación reutiliza la actividad, no se repiten las relaciones de tipo, agente y mandato. Solo se agrega su R033.
- **Propuesta del motor.** Siete tipos. La fecha llega con subtipo y EDTF. La actividad llega con tipo de actividad, agente y mandato:
  - un tipo o un mandato que el motor nombró dentro de la actividad se convierte en una propuesta propia, que la archivista decide aparte;
  - un agente que el motor no propuso no se inventa;
  - una EDTF inválida se descarta y la archivista la completa.
- **Decisiones de IA.** Al publicar se compara cada propuesta con lo publicado y se registra una decisión en auditoría (§16). En el panel del administrador:
  - cifras de aceptadas, corregidas, rechazadas y agregadas;
  - tabla por tipo de entidad, con la cobertura del motor;
  - detalle con lo propuesto, el valor final, la decisión y la versión de la instrucción;
  - filtros por tipo, decisión y periodo;
  - hoja de cálculo con resumen y detalle.
- **Relaciones entre agentes** (API del módulo de vocabularios). Se guarda una sola fila por relación y la inversa se lee de ella. La pantalla se hará con la actualización del módulo 3.
- **Ficha.** En el catálogo y en la vista interna la actividad muestra su cadena completa, y la fecha su forma legible. El catálogo ya no muestra «Sin fecha» para una fecha aproximada o incierta.

## 9. Flujos

**Validación con contexto**

1. La archivista abre el documento. La barra superior muestra el motor y la versión de la instrucción (por ejemplo `5a111bf3`).
2. En la tarjeta de fecha ajusta el calificador, de «Exacta» a «Incierta», y ve en vivo «1948 (incierta)», `1948?`.
3. En la tarjeta de actividad revisa la cadena propuesta: tipo «Policía local», ejercida por «Alcaldía Municipal», regulada por «Acuerdo 7 de 1946», periodo 1948.
4. Acepta cada tarjeta. Las de vocabulario, de los seis tipos, pasan por la pregunta «¿Es la misma entidad?».
5. Publica. En la misma transacción se crean el Record Resource, la cadena R033 + hasActivityType + R060 + R063 + R067 + R068 y las decisiones.

**Corrección posterior.** Reabrir y editar como en la versión 1. La auditoría guarda el antes y el después. Las correcciones posteriores no generan decisiones de IA: ahí el motor no propuso nada.

## 10. Pantallas

| Ruta | Pantalla |
|---|---|
| `/descripcion` | Por describir y Descritas |
| `/descripcion/trabajo/:id` | Espacio de trabajo con las tarjetas nuevas de fecha, actividad, tipo y mandato |
| `/descripcion/registro/:id` | Vista interna con la cadena y la fecha legible |
| `/auditoria?vista=decisiones` | **Decisiones de IA** (solo administrador) |

## 11. UX/UI

- **Contexto institucional en un solo tono.** Actividad, tipo de actividad y mandato comparten el color ciruela `--ctx` (#93437f en claro, #e8a2d3 en oscuro) y se distinguen por su insignia de subtipo, como pide el prompt.

  El violeta índigo ya lo usa el agente en el sistema, así que no se cambió (regla de conservar los colores actuales) y se eligió un tono distinto para que no se confundan. En el grafo, los tres nodos usan el mismo tono con opacidades distintas.
- **Las fechas no se escriben en código:** solo con controles. La expresión EDTF se muestra pequeña, como referencia.
- **Lo que bloquea la publicación** se cuenta como «pendiente» en la barra: una fecha sin completar o un tipo de actividad suelto.
- **El panel de decisiones dice sus límites:** estas cifras miden la aceptación de una archivista que ve la propuesta antes de decidir. No reemplazan la evaluación frente a descripciones hechas sin ver la IA (§22).
- Verificado en navegador real a 1360 px y 390 px, sin errores de JavaScript ni desplazamiento horizontal.

## 12. Modelo de datos

**Migración 0009** (reversible; se probó subirla, bajarla y volverla a subir, y con datos reales de la versión 1):

- `clase_vocabulario` gana `actividad`, `tipo_actividad` y `mandato`.
- `codigo_relacion_ric` gana `has_activity_type`, `performs_or_performed`, `has_successor`, `is_agent_associated_with_agent` e `is_date_associated_with`.
- `fechas` gana:
  - `subtipo` (simple / rango / conjunto);
  - `edtf`;
  - `inicio` y `fin`: los límites del intervalo, para ordenar y buscar. Las fechas exactas antiguas se convirtieron solas a EDTF nivel 0.
- `relaciones` gana `origen_original_id` (trazabilidad de la fusión por el lado del origen).
- Las actividades pasan a `entidades_vocabulario`. La tabla vieja queda.

**Decisiones de IA:** no hay tabla nueva. Viven en el registro de auditoría, que es de solo anexar, como evento `decision_ia`, según el principio 3 del prompt.

## 13. API

| Método y ruta | Qué cambia |
|---|---|
| `POST /api/descripcion/iniciar` | La propuesta trae actividad, tipo de actividad, mandato, fechas con subtipo y EDTF, y `version_prompt` |
| `POST /api/descripcion/verificar-vocabulario` | Admite los seis tipos reutilizables |
| `POST /api/descripcion/publicar` | Cada entidad lleva `clave`, `edtf`, `fecha_subtipo` y, si es actividad, `tipo_clave`, `agente_clave` y `mandato_clave`. Crea la cadena y registra las decisiones |
| `PATCH /api/descripcion/{id}` | Igual que antes, con los campos nuevos |
| `GET /api/auditoria/decisiones-ia` | **Nuevo, solo administrador.** Filtros `tipo`, `decision`, `desde`, `hasta`, `fondo_id`. Devuelve resumen, por tipo, modelos, versiones y filas |
| `GET /api/auditoria/decisiones-ia/hoja-de-calculo` | **Nuevo, solo administrador.** Hoja de cálculo «Resumen» + «Decisiones» |
| `POST /api/vocabulario/{id}/relaciones-agente` | **Nuevo.** `{destino_id, tipo: subordinado | sucesor | asociado}`. El detalle del agente devuelve sus relaciones en los dos sentidos |

## 14. Uso de IA

- **El motor propone el contexto institucional** cuando el texto lo menciona: la actividad, la competencia (tipo de actividad), quién la ejerce y la norma. La instrucción le pide no proponer nada de eso si no hay confianza razonable. Ninguna de esas entidades es obligatoria para publicar.
- **Fechas con precisión honesta:** se le dan al motor las formas EDTF permitidas y se le prohíbe inventar precisión. El servidor valida lo que devuelve.
- **Versión de la instrucción.** Es un resumen SHA-256 de la instrucción y del esquema de respuesta, en sus primeros 8 caracteres. Hoy es `5a111bf3`. Cambia solo si cambia lo que se le pide al motor.

  Queda en la propuesta de cada sesión y en cada decisión, para saber con qué instrucción salió cada resultado de la evaluación.
- **El valor propuesto lo guarda el servidor** al abrir el espacio de trabajo y no se modifica. La decisión se calcula contra ese valor, no contra lo que diga el navegador.

## 15. Seguridad

- **Los campos de procedencia no salen en la consulta pública.** Origen, confianza, motor y fragmentos siguen fuera de la lista cerrada de la ficha. La cadena de la actividad y las fechas legibles entran a esa lista sin campos internos. Lo comprueba una prueba que recorre toda la respuesta.
- **El panel de decisiones es solo del administrador** (403 para archivista y revisor, probado). Muestra quién validó cada propuesta, y eso es información del equipo.
- **El administrador no escribe rutas ni EDTF a mano:** todo se valida en el servidor contra el subconjunto.

## 16. Auditoría (qué queda registrado)

| Acción | Qué guarda |
|---|---|
| `decision_ia` (una por propuesta, más una por cada agregada) | `decision` (aceptada / corregida / rechazada / agregada), `tipo`, `clave`, `propuesto` y `final` (valor, rol, subtipo, EDTF y enlaces de la actividad, según el tipo), `confianza`, `modelo`, `version_prompt`, fondo y título del documento |
| `decision_ia` para el título y el alcance | Lo mismo, sobre esos dos campos |
| `agentes_relacionados` | Tipo, código RiC y con quién |
| `descripcion_publicada`, `descripcion_editada`, etc. | Como en la versión 1 |

**Cuándo una propuesta es «corregida»:** cuando cambia cualquiera de sus campos significativos. Por ejemplo:
- agente: valor, rol o subtipo;
- fecha: expresión, EDTF o subtipo;
- mandato: valor, instrumento o expedición;
- actividad: valor, periodo o enlaces.

Reutilizar una autoridad con otro nombre («Alcaldía» → «Alcaldía Municipal») también cuenta como corrección, porque cambió el valor final.

## 17. Interoperabilidad

- **Fechas en EDTF** (ISO 8601-2), el formato que piden RiC-O (`normalizedDateValue`), la Library of Congress y los portales de archivos.
- **Cada relación nueva lleva su URI RiC-O 1.1.** Las relaciones entre agentes llevan además su inversa declarada (`INVERSA_RICO`), lista para la exportación RDF (módulo 4).
- **La hoja de cálculo de decisiones** se abre en cualquier programa estadístico para el capítulo de resultados.

## 18. Normativa aplicable

- **RiC-CM 1.0 y RiC-O 1.1:** Activity, ActivityType, Mandate, Date y sus relaciones, verificadas contra el archivo oficial.
- **ISO 8601-2:2019 (EDTF), niveles 0 y 1**, más el conjunto del nivel 2.
- **ISAD(G):** 3.1.3 (fechas), 3.2.1 a 3.2.2 (productor e historia institucional) y 3.3.1 (alcance y contenido).
- **ISDF:** el tipo de actividad corresponde a la función, sin crear una entidad Función que RiC-O no tiene.
- **Metodología colombiana de TRD** (Acuerdo 004 de 2019 del AGN): la jerarquía función → subfunción se resolverá con SKOS en el módulo 3.

## 19. Arquitectura

- `servicios/fechas.py`: subconjunto EDTF, forma legible y límites.
- `servicios/motor.py`: instrucción, esquema, enlace de la cadena y `VERSION_PROMPT`.
- `servicios/descripcion.py`: publicación de los siete tipos, la cadena, `contexto_actividad()` y `registrar_decisiones()`.
- `servicios/decisiones_ia.py`: lectura del registro, cifras y hoja de cálculo.
- `servicios/vocabulario.py`:
  - conteo de documentos, que ahora atraviesa la actividad;
  - fusión en los dos sentidos;
  - relaciones entre agentes.

### Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| **Librería o mecanismo de validación EDTF** (prompt §5) | **Librería `edtf` 5.0.2** (Python, implementa los niveles 0, 1 y 2, con dependencias pyparsing y dateutil); **validación propia con expresiones regulares** sobre el subconjunto; edtf-validate (solo valida, sin interpretar) | **Las dos capas:** expresiones regulares propias que acotan el subconjunto, y la librería `edtf` que confirma que la expresión es válida | La librería sola acepta lo que el subconjunto excluye (estaciones como `1948-21`, años con exponente) e **inventa un margen de diez años** para un extremo desconocido (`/1952` lo toma como desde 1942), algo inadmisible en un archivo. Las expresiones regulares solas no detectan días imposibles. Juntas: el subconjunto exacto, la validez garantizada por una implementación madura y los límites calculados sin inventar | La dependencia suma unos 2 MB. Si la librería cambia su análisis, las pruebas lo detectan: hay casos válidos e inválidos fijados |
| **Mandato y actividad** | `authorizes` sobre la actividad (lo que decía el prompt); **R063 regula**; R063 + R067 | **R063 + R067**, elegida por la autora | `authorizes` en RiC-O 1.1 tiene dominio Mandate y rango Agent: aplicada a una Actividad, la validación contra la ontología la rechazaría, y el objetivo 2 exige conformidad con RiC-O. R063 conserva el sentido de «fundamentada en» y R067 conserva el de «autoriza», ahora sobre el agente correcto | Si el agente que ejerce cambia en la corrección, la R067 anterior queda. Se anula a mano desde la vista interna |
| **Dónde viven actividad, tipo y mandato** | Tablas propias por entidad; **vocabulario único con clases nuevas** | **Vocabulario** (`entidades_vocabulario`) | El prompt exige la misma verificación por similitud y el mismo servicio que agente y lugar. Así la fusión, la detección de duplicados, el índice de términos y el grafo funcionan sin código paralelo | El vocabulario mezcla entidades de naturaleza distinta. Se separan por `clase`, que todas las consultas filtran |
| **Inversa de las relaciones entre agentes** | Dos filas, una por sentido (lo que sugiere el prompt); **una fila con la inversa leída** | **Una fila** | RiC-O declara la inversa (`owl:inverseOf`): es la misma relación leída al revés. Con dos filas, anular una dejaría la otra viva y el grafo diría dos cosas distintas. El detalle del agente y la exportación muestran los dos sentidos | Ninguno práctico. Una consulta SQL que busque solo en un sentido debe mirar ambos; el servicio ya lo hace |
| **Dónde se guardan las decisiones de IA** | Tabla propia; **registro de auditoría** | **Auditoría**, como exige el principio 3 del prompt | Es de solo anexar (protegida por disparador): ni la administración puede retocar la evidencia de la evaluación | Las consultas leen JSON. Es rápido para el tamaño de un fondo; con cientos de miles de decisiones convendría un índice por acción |
| **Categoría «agregada»** | Solo aceptada / corregida / rechazada; **agregar «agregada»** | **Agregada**, mostrada aparte | Sin ella no se sabe qué no vio el motor, y la exhaustividad no se puede estimar. No altera las tres del prompt, que siguen contándose solas | Ninguno |
| **Color del contexto institucional** | Violeta del prompt, igual al del agente; **un tono distinto de la misma familia** | **Ciruela `--ctx`** | El agente ya es violeta índigo en el sistema y la autora pidió conservar los colores actuales. Con el mismo violeta, agente y actividad se confundirían en el grafo y en las tarjetas | Ninguno |
| Dónde se guarda el grafo (Apache AGE) | Ver versión anterior | Tablas relacionales | Sin cambios | Sin cambios |
| Algoritmo de similitud | pg_trgm | Sin cambios | Ahora sirve a seis clases | Sin cambios |
| Marca «en edición», índice único, motor Gemini, propuesta en el trabajo | — | Sin cambios | — | — |

## 20. Código (dónde vive, cómo se organiza)

```
alembic/versions/0009_descripcion_contexto.py   EDTF, clases y códigos nuevos, actividades al vocabulario
app/models/enums.py                             40 códigos RiC, URI e inversas
app/models/descripcion.py                       clases, subtipos, fechas con EDTF, origen_original_id
app/servicios/fechas.py                         subconjunto EDTF (nuevo)
app/servicios/motor.py                          instrucción v2, cadena, VERSION_PROMPT
app/servicios/descripcion.py                    publicación con cadena, decisiones, contexto
app/servicios/decisiones_ia.py                  panel y hoja de cálculo (nuevo)
app/servicios/vocabulario.py                    conteos, fusión en dos sentidos, relaciones entre agentes
app/routers/auditoria.py, vocabulario.py        rutas nuevas
frontend/src/lib/fechas.ts                      EDTF desde controles y forma legible (nuevo)
frontend/src/components/SelectorFecha.tsx       captura por subtipo (nuevo)
frontend/src/components/ContextoActividad.tsx   la cadena en fichas (nuevo)
frontend/src/pages/EspacioTrabajo.tsx           tarjetas de fecha, actividad, tipo y mandato
frontend/src/pages/Auditoria.tsx                pestaña Decisiones de IA
tests/test_descripcion_contexto.py              29 pruebas nuevas
```

## 21. Pruebas

**187 pruebas en el proyecto, todas pasan**, 29 de ellas nuevas en `tests/test_descripcion_contexto.py`. Las 20 de la versión 1 siguen pasando, con dos ajustes que son el comportamiento nuevo:
- una fecha sin EDTF ya no se publica;
- la actividad ahora también pasa por el vocabulario.

| Prueba (prompt §11–12) | Qué comprueba |
|---|---|
| Fechas interpretadas (6 casos) y rechazadas (7 casos) | Forma legible y límites de exacta, aproximada, década, rango con calificador, inicio desconocido y conjunto. Se rechazan: estación, 30 de febrero, rango invertido, extremo abierto `..`, «una de», exponente y año negativo |
| Fecha aproximada, rango y conjunto quedan en EDTF | Se guardan normalizadas, con subtipo, límites y forma legible. Un subtipo que no corresponde, o una fecha sin completar, da 422 |
| **La cadena completa** | R033, hasActivityType, R060, R063 y **R067 del mandato al agente**. El documento nunca toca el tipo. Desde el catálogo se recupera como una sola cadena (tipo, agente, mandato con instrumento y expedición, periodo), sin campos internos. Un segundo documento que reutiliza la actividad no duplica la cadena. Los conteos son de documentos, no de actividades. La fecha se ve como «c. 1948» |
| Tipo de actividad suelto | 422: «no está asignado a ninguna actividad» |
| Publicar sin actividad ni mandato | Válido |
| Vocabulario, seis tipos (6 casos) | Para cada uno, la verificación encuentra el existente y no lo confunde con otra clase |
| Reutilizar y crear tipo de actividad y mandato | Sin decidir, 409 con las coincidencias; reutilizando, no se duplica |
| **Un evento por decisión** (definición de terminado) | Con una aceptada, dos corregidas (agente que cambia de nombre y de subtipo; fecha que cambia de precisión con la misma expresión), dos rechazadas y una agregada: **exactamente un evento por propuesta** más uno por la agregada, con el valor propuesto, el final y el tipo correctos, y con modelo y versión de la instrucción. Título y alcance, con su propia decisión |
| Sin motor no hay decisiones | Describir a mano no genera evidencia falsa |
| Panel de decisiones | Solo administrador (403 para archivista y revisor). Cifras exactas, filtro por tipo, hoja de cálculo con sus dos hojas y el número de filas correcto |
| Relaciones entre agentes | Subordinación y asociación; repetida, consigo misma o con un lugar dan 422; la inversa se lee con su URI de RiC-O; una sola fila por relación |
| Fusión en los dos sentidos | El agente que ejerce y el autorizado pasan a la definitiva, con el original guardado |

**Pruebas de mutación** (se rompe el código a propósito y se comprueba que alguna prueba falle):

| Mutación | Resultado |
|---|---|
| No registrar las decisiones | Detectada |
| No crear la R067 | Detectada |
| Admitir estaciones en el subconjunto | Detectada |
| Contar las corregidas como aceptadas | Detectada |
| Fusión sin redirigir el origen | Detectada |
| Permitir un tipo de actividad suelto | Detectada |

**Verificación visual** en navegador real, con un motor de prueba que responde como Gemini:
- tarjetas de actividad (cadena y selectores), fecha (selector en vivo) y mandato;
- publicación;
- ficha del catálogo con la cadena;
- panel de decisiones;
- grafo;
- móvil a 390 px.

## 22. Criterios de aceptación

| Criterio (prompt §11–12) | Cumple |
|---|---|
| Documento individual de principio a fin | ✓ |
| Conjunto como expediente que sintetiza entre documentos | ✓ |
| Confianza baja que no bloquea | ✓ |
| Reutilizar y crear nueva, para cada uno de los seis tipos | ✓ |
| Bloqueo con dos usuarios, por expiración y por cancelación | ✓ (versión 1, sigue pasando) |
| Reapertura y edición con auditoría | ✓ |
| Fecha aproximada, rango y conjunto normalizadas en EDTF | ✓ |
| Actividad conectada a su tipo y a su mandato, recuperable como una sola cadena desde el catálogo | ✓ |
| La cola nunca devuelve lo ya descrito | ✓ |
| Ningún endpoint público expone origen, confianza ni estado de revisión | ✓ |
| Decisión EDTF con tabla completa | ✓ (§19) |
| Ejemplo documentado de la cadena en el fondo de prueba | ✓ (§23) |
| Exactamente un evento de decisión por aceptada, corregida y rechazada, con valores correctos | ✓ |

**Pendiente honesto:**

- **Lo que mide el panel no es todavía la evaluación del objetivo 3.** Mide la aceptación de una archivista que ve la propuesta, y eso tiene sesgo de anclaje. La evaluación frente a descripciones hechas por archivistas **sin ver la IA** necesita:
  - un modo de descripción ciega;
  - un comparador;
  - el acuerdo entre dos archivistas.

  Esta evidencia es la base de esa comparación, pero no la reemplaza.
- **La pantalla de relaciones entre agentes y la jerarquía SKOS de los tipos de actividad** quedan para la actualización del módulo 3, como indica el prompt. Aquí están el modelo, el servicio y la API.
- **La calidad real de Gemini proponiendo actividades y mandatos** no se pudo medir en este entorno, que no tiene clave. El despliegue prueba que el motor responde.

## 23. Evidencia concreta de aplicación de RiC

Ejemplo construido en el fondo de prueba durante la verificación visual: **«Oficio_210_1948.pdf»**, publicado como unidad documental.

```
Record «Oficio de la Alcaldía sobre la vigilancia de los mercados» (RiC-E04)
  ─ rico:hasCreator (R027) ─────────→ Agent/CorporateBody «Alcaldía Municipal»
  ─ rico:hasAddressee (R032) ───────→ Agent/Position «Gobernador del Departamento»
  ─ rico:hasOrHadSubject (R019) ────→ Place «Tunja»
  ← rico:isCreationDateOf (R080) ── Date «hacia 1948» · EDTF 1948? · 1948 (incierta)   ← corregida de 1948~
  ─ rico:documents (R033) ──────────→ Activity «Vigilancia de mercados por la Alcaldía, 1948» (RiC-E15)
        ─ rico:hasActivityType ─────→ ActivityType «Policía local»
        ← rico:performsOrPerformed (R060i) ─ Agent «Alcaldía Municipal»
        ← rico:regulatesOrRegulated (R063) ─ Mandate «Acuerdo 7 de 1946» (acuerdo; expedido 1946) (RiC-E17)
                                             ─ rico:authorizes (R067) ──→ Agent «Alcaldía Municipal»
        ← rico:isDateAssociatedWith (R068) ─ Date 1948
```

Decisiones registradas en auditoría para ese documento, con el motor `gemini-de-prueba` y la instrucción `5a111bf3`:
- 8 aceptadas, entre ellas la actividad, el tipo, el mandato, los dos agentes y el lugar;
- 1 corregida: la fecha, de aproximada a incierta;
- 1 rechazada: la forma documental «Oficio».

En la ficha del catálogo la actividad se lee así: *tipo: Policía local · ejercida por Alcaldía Municipal · regulada por Acuerdo 7 de 1946 (acuerdo, 1946) · 1948*.

Ese es el contexto institucional que RiC agrega a ISAD(G). La consulta pública lo muestra sin ningún dato de procedencia.
