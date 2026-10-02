# Módulo 2 · Descripción multinivel asistida por inteligencia artificial

**Estado:** entregado, pendiente de validación.

---

## 1. Propósito

Toma uno o varios documentos ya listos desde ingesta, les aplica el motor de análisis para proponer una descripción según Records in Contexts, deja que el archivista valide cada propuesta, y publica el resultado como un grafo de entidades y relaciones reales en la base de datos.

## 2. Auditoría (qué se revisó antes de construirlo)

**Documentos revisados:**

- el prompt del módulo 2;
- el diseño consolidado (Parte 3);
- el mockup «Sistema RIC · Descripción»: Por describir con selección múltiple; espacio de trabajo en dos columnas, con fragmentos resaltados, tarjetas de propuesta, bloque de vocabulario y barra de publicación;
- el catálogo curado del andamiaje.

**Hallazgo que exigió detenerse:** al catálogo curado de 32 relaciones le faltaban tres que este módulo necesita. Se preguntó a la autora, que indicó usar las oficiales de RiC. Se agregaron con su código oficial de RiC-CM 1.0 (ver §7):

- RiC-R025 *has or had instantiation*;
- RiC-R033 *documents*;
- RiC-R019 *has or had subject*.

**Dependencia nueva:** el servicio de verificación de vocabulario pertenece al módulo 3, que todavía no existía. Se construyó aquí como servicio de ese módulo (`app/servicios/vocabulario.py`) con su decisión técnica documentada (§19). Descripción lo consume, como exige el prompt. El módulo 3 lo reutilizará tal cual.

## 3. Problema que resuelve

Describir un fondo histórico documento por documento, a mano, no es viable. Con el principio de proporcionalidad de ISAD(G) y un motor que propone —citando de dónde sale cada dato—, el archivista:

- valida en lugar de transcribir;
- puede describir a nivel de expediente, subserie o serie.

## 4. Usuarios

| Rol | Qué hace |
|---|---|
| Archivista, administrador | Describe, valida, publica, reabre y corrige |
| Revisor (provisional) | Ve la cola y las descripciones publicadas, sin modificar |
| Consulta | Solo la ficha pública en el catálogo |

## 5. Casos de uso

1. Describir un documento suelto (nivel unidad documental).
2. Describir varios como conjunto, eligiendo expediente, subserie o serie.
3. Aceptar, editar o descartar cada entidad que propone el motor.
4. Resolver si una entidad ya existe en el vocabulario: reutilizarla o crear una nueva.
5. Agregar a mano lo que el motor no vio.
6. Publicar.
7. Reabrir una descripción publicada y corregirla.
8. Salir sin publicar, lo que libera el documento para otra persona.

## 6. Entidades RiC involucradas

| Entidad RiC-CM | Dónde vive | Qué es aquí |
|---|---|---|
| Record Resource (E02): Record en la unidad documental, Record Set en expediente, subserie y serie | `recursos_documentales` | Título, alcance y contenido (RiC-A38 / ISAD 3.3.1), nivel, forma documental (A17) |
| Agent (E07): Person, Corporate Body, Position (cargo), Family | `entidades_vocabulario`, clase agente | Registro único por fondo |
| Place (E22) | `entidades_vocabulario`, clase lugar | Registro único por fondo |
| Tipo de forma documental (A17) | `entidades_vocabulario`, clase forma_documental | Registro único por fondo |
| Date (E18) | `fechas` | Expresión literal y fecha normalizada (solo si es exacta) |
| Activity (E15) | `actividades` | Lo que el documento documenta |
| Instantiation (E06) | `instanciaciones` (módulo 1) | El archivo técnico, ya existente |
| Mechanism (E13) | Columna `motor` | Queda registrado qué motor propuso cada dato |

## 7. Relaciones RiC involucradas

| Qué | Código oficial | URI RiC-O | Sentido |
|---|---|---|---|
| Productor | RiC-R027 has creator | rico:hasCreator | documento → agente |
| Remitente | RiC-R031 has sender | rico:hasSender | documento → agente |
| Destinatario | RiC-R032 has addressee | rico:hasAddressee | documento → agente |
| Agente o lugar mencionado | **RiC-R019 has or had subject** (agregada) | rico:hasOrHadSubject | documento → entidad |
| Fecha de creación | RiC-R080 is creation date of | rico:isCreationDateOf | fecha → documento |
| Actividad | **RiC-R033 documents** (agregada) | rico:documents | documento → actividad |
| Inclusión en el nivel superior | RiC-R024 includes or included | rico:includesOrIncluded | superior → documento |
| Archivo técnico | **RiC-R025 has or had instantiation** (agregada) | rico:hasOrHadInstantiation | documento → instanciación |

El catálogo curado pasa de 32 a 35 códigos. Cada relación lleva además su categoría amplia (procedencia, temporal, espacial, inclusión, asociación).

## 8. Funcionalidades

- **Cola «Por describir».** Instanciaciones en `listo_para_descripcion` sin relación RiC-R025 vigente. No hay campo de estado nuevo: en cuanto se publica, el documento sale de la cola solo. Muestra quién tiene cada documento en edición.
- **Marca «en edición».**
  - Queda registrado quién y desde cuándo.
  - La base de datos impide que dos personas tomen el mismo documento, incluso si pulsan al mismo tiempo (índice único parcial).
  - Se libera sola tras **30 minutos sin actividad** (la pantalla envía una señal cada 2 minutos) o de inmediato con «Salir sin publicar».
  - También aplica a la reapertura de una descripción publicada.
- **Propuesta del motor:**
  - título y alcance y contenido (sintetizando todos los documentos del conjunto);
  - entidades con tipo, subtipo, rol, valor y confianza;
  - el **fragmento exacto** citado y el documento del que sale.
- **Control de fragmentos.** El sistema busca cada fragmento en el texto real. Si no aparece, la confianza baja a 0,3 como máximo y la tarjeta dice «no se encontró en el texto: verifíquelo». Es la defensa contra lo que un motor pueda inventar.
- **Validación por entidad:**
  - aceptar, editar (valor, clase de agente, rol, fecha exacta) o descartar (con deshacer);
  - las de confianza baja se marcan, sin bloquear nada;
  - agentes, lugares y formas documentales pasan por la **verificación de vocabulario** antes de confirmarse, con las dos rutas: reutilizar o crear nueva.
- **Publicar:**
  - se habilita cuando no queda nada pendiente de resolver;
  - es una sola transacción: si algo falla no queda nada a medias, y la marca sigue tomada para corregir y volver a publicar.
- **Corrección posterior:**
  - reabrir, cambiar título, alcance y nivel superior, quitar relaciones, agregar entidades;
  - lo que se quita **no se borra**: queda «anulado» con fecha y autor;
  - la auditoría guarda el valor anterior y el nuevo.
- **Ficha pública** (`/api/catalogo/registros/{id}`): base del catálogo del módulo 4. Nunca incluye origen, confianza, motor, estado de revisión ni fragmentos.

## 9. Flujos

**Un documento**

1. Descripción → «Por describir» → «Describir».
2. El espacio de trabajo muestra el texto a la izquierda, con los fragmentos resaltados. Al pulsar una tarjeta, su fragmento se resalta con más fuerza y la vista se desplaza hasta él.
3. A la derecha están el título y el alcance (editables), «Queda incluido en» y las tarjetas de cada entidad.
4. Se acepta cada tarjeta. En un agente puede aparecer: «Ya existe algo parecido… ¿Es la misma entidad?», con «Reutilizar esta» o «Es distinta: crear nueva».
5. La barra muestra «nada pendiente» → «Publicar descripción».
6. Vuelve a la cola con «Se publicó…».

**Conjunto**

1. Se marcan las casillas de varios documentos.
2. Aparece la barra «N documentos seleccionados · Son un [Expediente/Subserie/Serie] · Describir como conjunto».
3. El motor recibe todos los textos, cada uno con su nombre, y sintetiza entre ellos. Cada fragmento indica de qué documento sale.

**Corrección**

1. «Descritas» → «Ver y corregir».
2. La vista interna muestra cada relación con su URI RiC-O, su procedencia y su confianza.
3. «Corregir» → editar → «Guardar cambios».

**Sin motor** (sin clave, sin conexión o con error del motor)

1. El espacio se abre con un aviso: «Puede describir a mano».
2. Se escribe el título y se agregan las entidades con «+ Agregar una entidad».

## 10. Pantallas

| Ruta | Pantalla |
|---|---|
| `/descripcion` pestaña «Por describir» | Cola con casillas, botón «Describir» por fila y barra de conjunto |
| `/descripcion` pestaña «Descritas» | Descripciones publicadas, con quién las tiene en edición |
| `/descripcion/trabajo/:id` | Espacio de trabajo en dos columnas (se puede recargar sin perder la propuesta) |
| `/descripcion/registro/:id` | Vista interna de una descripción publicada y su corrección |

## 11. UX/UI

- **Mockup** «Sistema RIC · Descripción», con la paleta de tono medio. Colores por tipo:
  - agente: morado (el tono reservado a agentes);
  - fecha: azul grisáceo;
  - lugar: naranja;
  - actividad: azul;
  - forma documental: verde.
- **Confianza baja:** insignia naranja. **Aceptada o corregida:** insignia verde.
- **La procedencia no se mezcla con el texto:** se ve en insignias y en líneas aparte, nunca dentro del título ni de un valor. Es el error que el prompt recuerda de un sistema anterior.
- **Barra de publicación fija** abajo, con el conteo: «6 entidades · 5 aceptadas · 1 con confianza baja · nada pendiente».
- **Móvil:** las columnas se apilan (texto arriba, propuestas abajo).

## 12. Modelo de datos

Migración `0003_descripcion.py`, que activa además `pg_trgm`.

| Tabla | Clave |
|---|---|
| `recursos_documentales` (ampliada) | alcance_contenido, forma_documental_id, **origen_titulo, origen_alcance, confianza_alcance, motor**, publicado_en/por, actualizado_en |
| `entidades_vocabulario` | fondo_id, clase, subtipo, nombre, nombre_normalizado (índice GIN de trigramas), estado (activa/fusionada), fusionada_en_id, **origen, confianza, motor, estado_revision** |
| `fechas` / `actividades` | Expresión o nombre, más las mismas columnas de procedencia |
| `relaciones` | origen/destino (tipo e id), tipo_relacion, **codigo_ric**, rol, fragmento, fragmento_instanciacion_id, fragmento_inicio, estado (vigente/anulada), anulada_en/por, confirmada_por, más las columnas de procedencia |
| `trabajos_descripcion` | usuario, fondo, nivel, recurso_id (en reaperturas), propuesta (JSON), estado (abierto/publicado/cancelado/expirado), ultima_actividad |
| `trabajo_instanciaciones` | trabajo, instanciación, abierto. **Índice único parcial `WHERE abierto`**: el candado |

## 13. API

Todas bajo `/api/descripcion`.

| Método y ruta | Qué hace |
|---|---|
| `GET /cola?fondo_id=` | Por describir, según la regla de la §8 |
| `POST /iniciar` | `instanciacion_ids` y `nivel` si son varios. Toma la marca y devuelve documentos con su texto y la propuesta. **409** si otra persona los tiene |
| `POST /verificar-vocabulario` | Tipo y valor → coincidencias del vocabulario del fondo (delega en el servicio de vocabularios) |
| `POST /publicar` | Creación transaccional. **409** con las coincidencias si hay parecidos que el archivista no resolvió |
| `POST /{trabajo_id}/cancelar` | Libera la marca sin publicar |
| `PATCH /{recurso_id}` | Corrige una descripción publicada, con auditoría de antes y después |
| `GET /trabajos/{id}`, `POST /trabajos/{id}/latido` | Recargar el espacio y mantener la marca |
| `GET /niveles-superiores`, `GET /publicadas`, `GET /registros/{id}`, `POST /registros/{id}/reabrir` | Apoyo de las pantallas |
| `GET /api/catalogo/registros/{id}` | Ficha pública (cualquier rol con sesión) |

- Escritura: archivista y administrador. Lectura: además el revisor.
- La ficha pública la ve también el rol consulta.

## 14. Uso de IA

- **Motor:** Gemini (`gemini-3.5-flash`), por su API REST, con salida JSON estructurada (esquema fijo) y temperatura 0,1. Usa la clave `GEMINI_API_KEY` que ya tenía el servidor.
- **Instrucción:** usar solo el texto, citar un fragmento literal, dar la confianza, no inventar, marcar lo dudoso con confianza baja, y sintetizar todos los documentos en el alcance.
- **Lo que recibe:** hasta 20.000 caracteres por documento y 60.000 en total.
- **La IA propone y nunca decide:** nada se publica sin que una persona lo acepte, ni siquiera con confianza alta.
- **Cada dato conserva su procedencia:** motor, motor corregido o persona. La calcula **el servidor**, comparando con la propuesta guardada; no se le cree al navegador.
- **Registro del motor:** queda el nombre del motor en cada dato (RiC-E13 Mechanism).
- **Verificación en cada despliegue:** el despliegue ejecuta `python -m app.cli probar-motor` y deja en el registro si el motor responde.

## 15. Seguridad

- Escritura solo para archivista y administrador. El revisor lee y recibe 403 en toda acción (probado).
- Un trabajo solo lo puede publicar, cancelar o mantener su dueño: con otra persona responde 404 («no existe o es de otra persona»).
- La procedencia no se puede falsificar desde el navegador (§14).
- La ficha pública se arma con una **lista cerrada** de campos permitidos, no quitando campos de la vista interna, así que un campo interno nuevo no puede colarse por descuido. Una prueba recorre la respuesta completa buscando cualquier clave prohibida.
- El texto de los documentos solo sale del servidor hacia el motor configurado.

## 16. Auditoría (qué queda registrado)

- `descripcion_iniciada`: documentos y nivel.
- `descripcion_publicada`: resumen completo; cada entidad con su procedencia.
- `descripcion_cancelada`.
- `edicion_liberada`: expiración por inactividad.
- `descripcion_editada`: valores anteriores y nuevos, solo de lo que cambió.

## 17. Interoperabilidad

- Cada relación guarda su código RiC-R oficial y su URI RiC-O 1.1 (`URI_RICO`), listos para la exportación.
- Las fechas se normalizan a ISO 8601 solo cuando son exactas; la expresión original se conserva siempre.

## 18. Normativa aplicable

- **ISAD(G):** descripción multinivel (3.1.4), alcance y contenido (3.3.1), principio de proporcionalidad.
- **RiC-CM 1.0 / RiC-O 1.1:** entidades, atributos y relaciones con códigos oficiales.
- **Acuerdo 027 de 2006 y Acuerdo 004 de 2019 del AGN:** descripción y control de autoridad mediante el vocabulario único por fondo.
- **Ley 1712 de 2014:** trazabilidad de quién describió y quién corrigió.

## 19. Arquitectura

- **Módulos del código:**
  - `servicios/motor.py`: motor y control de la propuesta;
  - `servicios/vocabulario.py`: servicio único de similitud, del módulo 3;
  - `servicios/descripcion.py`: candado, publicación y corrección;
  - `servicios/consulta.py`: ficha pública.
- **Publicación:** es una transacción de PostgreSQL.
- **Candado:** índice único parcial en la base de datos.

### Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| **Dónde se guarda el grafo** (Apache AGE estaba en el prompt maestro; esta decisión había quedado pendiente y se documenta después, a pedido de la autora) | **Apache AGE** (extensión de PostgreSQL para grafos, consultas en Cypher); **tablas relacionales de PostgreSQL** (`relaciones` con códigos RiC-R e índices); Neo4j (base de grafos aparte); almacén RDF con SPARQL (p. ej. Fuseki) | **Tablas relacionales de PostgreSQL**. AGE queda como opción de evolución | Lo que el sistema consulta son vecindarios de 1 a 3 saltos y la jerarquía del fondo. SQL con índices lo resuelve en milisegundos para el tamaño de un fondo. AGE exige otra imagen de base de datos, aprender Cypher y respaldos más delicados, y guarda el grafo en un esquema propio que habría que mantener sincronizado con el resto. Neo4j suma un segundo motor que sincronizar (el prompt maestro lo descarta). El grafo interoperable es RiC-O en RDF, que se genera como exportación | Consultas de caminos largos («todo lo conectado a 6 saltos») serían más naturales en Cypher. Si hacen falta: cada fila de `relaciones` corresponde a una arista de AGE, y la migración es un guion, no un rediseño |
| **Algoritmo de similitud** del vocabulario (el prompt 3 exige documentarlo; se necesitaba ya aquí) | Distancia de edición clásica (Levenshtein, en Python o con `fuzzystrmatch`); **trigramas con `pg_trgm`**; librería externa (rapidfuzz) | **pg_trgm** sobre el nombre en minúsculas y sin tildes, umbral **0,45** (configurable con `UMBRAL_SIMILITUD_VOCABULARIO`) | Ya viene con PostgreSQL: no suma dependencias. Un índice GIN resuelve la búsqueda en la base de datos, sin traer el vocabulario entero a Python. Tolera el orden de palabras y los nombres parciales («Alcaldía Municipal» ↔ «Alcaldía Municipal de Tunja»), donde Levenshtein falla | Nombres muy cortos o casi iguales de personas distintas («Juan Pérez» / «Juana Pérez») aparecen como posibles coincidencias. No es grave: el archivista decide, nunca se fusiona solo |
| Tiempo de la marca «en edición» | 15 min; **30 min**; 60 min | **30 min sin actividad**, con señal cada 2 minutos mientras la pantalla está abierta | Leer y validar un documento largo toma tiempo; con la señal, la marca no vence mientras se trabaja. Si alguien cierra el navegador, en 30 minutos el documento vuelve a estar disponible | Quien deja la pantalla abierta sin usarla retiene el documento. Se ve en la cola («En edición por…») |
| Cómo se impide la edición doble | Comprobar en el código; bloqueo de filas; **índice único parcial** | **Índice único parcial** en `trabajo_instanciaciones` | Lo garantiza la base de datos aunque dos personas pulsen en el mismo milisegundo | Ninguno relevante |
| Motor | Anthropic, OpenAI (de pago); modelo local (Ollama, pesado para 2 GB); **Gemini** | **Gemini** por REST, sin SDK | Ya había clave gratuita en el servidor; la salida JSON con esquema reduce respuestas malformadas; no carga memoria en el servidor | Depende de un servicio externo: sin él se describe a mano, con aviso. El texto viaja a Google: no cargar documentos con reserva legal sin evaluarlo |
| Dónde se guarda la propuesta | Solo en el navegador; **en el trabajo** | **En `trabajos_descripcion`** | Recargar la página no hace perder la propuesta; el servidor puede comprobar la procedencia contra ella | Ninguno |
| Relaciones que faltaban en el catálogo | Detenerse; usar solo la categoría amplia; **agregar las oficiales** | **Agregar RiC-R025, R033 y R019**, por indicación de la autora | Son oficiales de RiC-CM 1.0. Sin ellas no se puede vincular el archivo, la actividad ni lo mencionado | Ninguno |

## 20. Código (dónde vive, cómo se organiza)

```
app/models/descripcion.py         entidades, relaciones, trabajos y candado
app/models/recurso_documental.py  ampliado con los campos descriptivos
app/servicios/motor.py            Gemini + control de fragmentos
app/servicios/vocabulario.py      verificar() y crear() (módulo 3)
app/servicios/descripcion.py      cola, candado, publicar, detalle, editar
app/servicios/consulta.py         ficha pública (lista cerrada)
app/routers/descripcion.py        /api/descripcion y /api/catalogo
frontend/src/pages/Descripcion.tsx, EspacioTrabajo.tsx, Registro.tsx
frontend/src/components/Vocabulario.tsx; lib/descripcion.ts
```

## 21. Pruebas

20 pruebas en `tests/test_descripcion.py` (95 en total en el proyecto). El motor se reemplaza por uno de prueba; el resto es el código real contra PostgreSQL.

- **De principio a fin (un documento):**
  - fragmentos ubicados en el texto;
  - publicación con los códigos RiC correctos;
  - procedencia motor / motor corregido;
  - título limpio, sin marcas mezcladas;
  - sale de la cola y la marca se libera;
  - evento de auditoría.
- **Conjunto como expediente:**
  - el motor recibe los dos documentos con sus nombres;
  - cada fragmento apunta al documento correcto;
  - un conjunto sin nivel se rechaza.
- **Control del motor:**
  - un fragmento inventado rebaja la confianza a 0,3 como máximo;
  - una confianza baja no bloquea la publicación;
  - sin motor se describe a mano;
  - con el motor fallando se describe igual.
- **Vocabulario:**
  - detecta parecidos y no confunde entidades distintas («Gobernación de Boyacá», «Juan Pérez»);
  - reutilizar no crea duplicados; crear nueva sí crea;
  - sin decidir, la publicación responde 409 y no crea nada;
  - un espía confirma que descripción **llama de verdad** al servicio de vocabularios, por cada agente, lugar y forma documental.
- **Concurrencia (dos usuarios simulados):**
  - el segundo recibe 409 con el nombre del primero y no puede cancelar un trabajo ajeno;
  - la marca se libera por cancelación y por expiración, y el trabajo vencido ya no publica;
  - el latido mantiene la marca;
  - la base de datos rechaza dos marcas sobre el mismo documento;
  - la reapertura también se bloquea entre personas.
- **Corrección:** reabrir y editar; la relación quitada queda anulada, no borrada; la auditoría tiene el antes y el después.
- **Reglas de la cola y la publicación:**
  - la cola nunca devuelve un documento ya descrito, ni uno en proceso;
  - la publicación es todo o nada: con un error no queda ni una fila, y luego se puede publicar.
- **Consulta pública:** la ficha no tiene ninguna clave de procedencia, mientras la vista interna sí las tiene.
- **Permisos:** 401 sin sesión, 403 para el rol consulta, y el revisor solo lee.

Además se **comprobó que las pruebas detectan fallas**: al meter a propósito «confianza» en la ficha pública, o al saltarse la pregunta de vocabulario, las pruebas correspondientes fallan.

**Verificación visual** en navegador real, con la ingesta de verdad:

- cola con selección;
- espacio de trabajo con fragmentos resaltados;
- pregunta de vocabulario;
- barra de publicación;
- corrección;
- móvil.

## 22. Criterios de aceptación

| Criterio (prompt §9–10) | Cumple |
|---|---|
| Documento individual de la cola a la publicación | ✓ |
| Conjunto como expediente que sintetiza y cita el documento correcto | ✓ |
| Confianza baja que no bloquea | ✓ |
| Vocabulario: reutilizar (sin duplicar) y crear nueva | ✓ |
| Bloqueo con dos usuarios simulados; se libera por expiración y por cancelación | ✓ |
| Reabrir y editar con auditoría de antes y después | ✓ |
| La cola nunca devuelve una instanciación con Record Resource | ✓ |
| Ningún endpoint público expone origen, confianza ni estado de revisión | ✓ |
| La llamada al vocabulario es una dependencia real, no una reimplementación | ✓ (prueba con espía) |

**Pendiente honesto:** la calidad real de las propuestas de Gemini no se pudo medir aquí (sin clave en este entorno). El registro del despliegue dirá si el motor responde en el servidor. La evaluación de calidad —precisión de las entidades frente a una descripción hecha por una archivista— es un trabajo de la tesis que conviene hacer con documentos reales del fondo.

## 23. Evidencia concreta de aplicación de RiC

Después de publicar el oficio de prueba, el grafo guardado es:

```
Record «Oficio de la Alcaldía Municipal sobre el estado del archivo» (unidad documental)
  ← rico:includesOrIncluded ─ Record Set «Correspondencia municipal» (fondo)
  ─ rico:hasCreator ────────→ Agent/CorporateBody «Alcaldía Municipal»      [motor, 93 %]
  ─ rico:hasAddressee ──────→ Agent/Position «Gobernador del Departamento»  [motor corregido]
  ← rico:isCreationDateOf ── Date «15 de marzo de 1948» (1948-03-15)        [motor, 97 %]
  ─ rico:hasOrHadSubject ───→ Place «Boyacá»                                 [motor, 40 %: confianza baja]
  ─ rico:documents ─────────→ Activity «Conservación del archivo municipal»
  ─ rico:hasOrHadInstantiation → Instantiation «Oficio_114_1948.pdf» (fmt/18, SHA-256 …)
  forma documental (RiC-A17): «Oficio»
```

- Las procedencias entre corchetes solo se ven en la vista interna. La ficha pública muestra el mismo grafo sin ellas.
- La Alcaldía Municipal es **un solo nodo** del vocabulario del fondo: el siguiente documento que la mencione se conecta a ella («Reutilizar esta») en lugar de crear otra.
