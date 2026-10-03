# Módulo 3 · Vocabularios y control de autoridad

**Estado:** versión 2 (ficha de autoridad ISAAR-CPF, lugar ampliado, árbol de funciones, jerarquía de mandatos). Pendiente de validación.

**Qué cambió en la versión 2.** La versión 1 guardaba de cada entidad solo su nombre, su tipo y sus fusiones. La versión 2 completa cuatro cosas:

- **Agente:** ficha de autoridad en las cuatro áreas de ISAAR-CPF.
- **Lugar:** coordenadas, tipo, jerarquía y nombres históricos.
- **Tipo de actividad:** árbol función → subfunción → trámite, con SKOS, y su serie documental.
- **Actividad y mandato:** sub-actividades, norma superior, mandato que crea una entidad o una competencia y entidad que expidió el mandato.

Todos los nombres de RiC-O que usa el módulo salen de un único mapeo (`app/servicios/ric_o.py`). Una prueba lo compara contra el archivo OWL oficial de RiC-O 1.1: ver `documentacion/anexos/verificacion-ric-o-1-1.md`.

---

## 1. Propósito

Mantener, por fondo, un registro único y reutilizable de sus entidades de contexto:

- agentes, incluido el mecanismo (un programa con su versión);
- lugares;
- formas documentales;
- actividades;
- tipos de actividad;
- mandatos o normas.

Cada entidad tiene el nivel de detalle que pide su norma de descripción. El módulo:

- evita duplicados antes de que existan, con el servicio de verificación que usa descripción;
- detecta los que ya se colaron, con las sugerencias de fusión;
- los fusiona con aprobación humana, sin borrar nada;
- permite enriquecer cada entidad después de creada, sin bloquear ningún trabajo de descripción.

## 2. Auditoría (qué se revisó antes de construirlo)

**Documentos revisados:**

- el prompt actualizado del módulo 3 (versión 2, secciones 1 a 12);
- el prompt del módulo 2 versión 3, en las partes que remite a vocabularios;
- el anexo de mapeo RiC-O 1.1 entregado con los prompts;
- el archivo OWL oficial de RiC-O 1.1;
- el PDF de RiC-CM 1.0;
- el código de la versión 1.

**Hallazgos:**

1. **El anexo de mapeo dejaba trece puntos sin verificar.** Se verificaron todos contra el OWL antes de escribir código, y tres afirmaciones del anexo resultaron incorrectas. Las que tocan a este módulo:
   - las coordenadas de un lugar se exportan con `rico:geographicalCoordinates`, no con la clase `Coordinates`, que es de `PhysicalLocation`;
   - el grupo se puede instanciar directamente (`rico:Group`);
   - la relación asociativa entre agentes es `isAgentAssociatedWithAgent` (R044);
   - la versión del mecanismo tiene propiedad propia: `technicalCharacteristics` (A41).
2. **El prompt pide «la entidad que expidió» un mandato.** Ninguna relación del catálogo lo cubría. RiC-O tiene `issuedBy` (RiC-R065, de Rule a Agent). Se agregó al catálogo: es la propiedad verificada para un dato que el prompt exige. No es una relación inventada.
3. **El prompt pide relaciones entre agentes «fechadas» y con «una breve descripción».** La tabla `relaciones` no tenía dónde guardarlas. Se agregaron `fecha_edtf` y `nota`.
4. **Había tres copias de la lista de subtipos de agente** (modelo, motor y descripción). Quedó una sola, en el modelo; las otras dos la importan. El subtipo «grupo» se agregó una sola vez y llega a los tres.
5. **El prompt habla de «Celery y Redis ya previstos».** En este proyecto no están instalados. Se mantiene la decisión de la versión 1: el trabajador en segundo plano que ya existe.
6. **Colores:** se mantiene la paleta de RICORA (no el terracota del prompt), por decisión de la autora. Actividad, tipo de actividad y mandato comparten el tono de contexto.

## 3. Problema que resuelve

Sin control de autoridad, un mismo productor escrito de cinco formas son cinco nodos sueltos. Además, sin ficha de autoridad, el archivista no puede responder las preguntas que un usuario de archivo histórico trae primero:

- **quién era** el productor;
- **cuándo existió**;
- **de quién dependía**;
- **a quién sucedió**;
- **qué norma lo creó**;
- **dónde actuó**.

La versión 2 hace que el vocabulario responda esas preguntas con datos estructurados que se pueden exportar a RiC-O, no con texto suelto.

## 4. Usuarios

| Rol | Qué hace |
|---|---|
| Archivista, coordinador de archivo, descriptor | Navega, enriquece fichas, declara vínculos, revisa sugerencias, fusiona |
| Revisor, auditor (lectura) | Ve todo, sin modificar (403 en cualquier escritura) |
| Administrador | Todo lo anterior y los criterios de detección |
| Consulta | Sin acceso al módulo |

Los permisos salen de la matriz única de roles: módulo «vocabularios», con nivel de lectura o de escritura.

## 5. Casos de uso

1. Ver el vocabulario, filtrar por los seis tipos y buscar por nombre.
2. Filtrar los agentes por nivel de detalle para encontrar los que siguen en ficha mínima.
3. Ver los tipos de actividad como árbol de funciones.
4. Completar la ficha ISAAR de un agente:
   - formas del nombre;
   - identificadores (internos y de autoridad externa);
   - versión, si es un mecanismo;
   - fechas de existencia;
   - historia;
   - estatuto jurídico;
   - estructura;
   - contexto;
   - fuentes;
   - reglas.
5. Registrar hitos de la línea de tiempo institucional: creación, reforma, traslado, supresión.
6. Relacionar dos agentes: jerárquica, temporal o asociativa, con vigencia y nota.
7. Declarar el lugar de actuación de un agente y el mandato que lo creó.
8. Completar un lugar: tipo, coordenadas con mapa, lugar superior y nombres históricos con su periodo.
9. Ubicar un tipo de actividad bajo otro (función → subfunción) y enlazarlo con la serie que produce.
10. Declarar la estructura de una actividad (sub-actividades), quién la ejerce y qué mandato la regula.
11. Declarar la norma superior de un mandato, la entidad que lo expidió y qué agente o competencia creó.
12. Anular cualquiera de esos datos sin borrarlo.
13. Revisar sugerencias de fusión y fusionar a mano. La ficha de la absorbida pasa a la definitiva.

## 6. Entidades RiC involucradas

| Entidad | RiC-CM 1.0 | Clase RiC-O 1.1 | Detalle en la versión 2 |
|---|---|---|---|
| Agente persona | E08 | `rico:Person` | Ficha ISAAR de cuatro áreas |
| Agente familia | E10 | `rico:Family` | Ídem |
| Agente entidad corporativa | E11 | `rico:CorporateBody` | Ídem, más estatuto jurídico |
| **Agente grupo (nuevo)** | E09 | `rico:Group` | Comité o junta sin personería. La nota de alcance de `rico:Group` admite «otras clases de grupos» |
| Agente cargo | E12 | `rico:Position` | Jerarquía entre cargos con la misma relación R045 |
| Agente mecanismo | E13 | `rico:Mechanism` | Versión obligatoria, exportada como `rico:technicalCharacteristics` (A41) |
| Lugar | E22 | `rico:Place` | Coordenadas (A11), tipo (`rico:PlaceType`), nombres (`rico:PlaceName`) |
| Forma documental | A17 | `rico:DocumentaryFormType` | — |
| Actividad | E15 | `rico:Activity` | Sub-actividades |
| Tipo de actividad | — | `rico:ActivityType` y `skos:Concept` | Árbol SKOS, serie que produce |
| Mandato o norma | E17 | `rico:Mandate` | Tipo de instrumento (`rico:RuleType`), jerarquía, emisor |
| **Hito institucional (nuevo)** | E14 | `rico:Event` | Usado directamente, no como Activity |

## 7. Relaciones RiC involucradas

Cada relación se guarda en una sola fila: la inversa se lee de ella y nunca se duplica. Los códigos y las propiedades salen de `ric_o.py`.

| Vínculo (lo declara la persona en…) | Fila guardada | RiC-O 1.1 | RiC-CM |
|---|---|---|---|
| Tiene o tuvo como subordinado a (agente) | agente → agente | `hasOrHadSubordinate` / `isOrWasSubordinateTo` | R045 |
| Tiene como sucesor a (agente) | agente → agente | `hasSuccessor` / `isSuccessorOf` | R016 |
| Está asociado con (agente) | agente ↔ agente | `isAgentAssociatedWithAgent` (simétrica) | R044 |
| Actúa o actuó en (agente) | lugar → agente | `isOrWasLocationOf` / `hasOrHadLocation` | R075 |
| Fue creado o establecido por (agente) | mandato → agente, rol creación | `authorizes` / `authorizedBy` | R067 |
| Está dentro de (lugar) | lugar superior → lugar | `containsOrContained` / `isOrWasContainedBy` | R007 |
| Es sub-actividad de (actividad) | actividad mayor → sub | `hasDirectSubevent` / `isDirectSubeventOf` | atajo de R006 |
| Es o fue ejercida por (actividad) | agente → actividad | `performsOrPerformed` / `isOrWasPerformedBy` | R060i |
| Está regulada por (actividad) | mandato → actividad | `regulatesOrRegulated` / `isOrWasRegulatedBy` | R063 |
| Desarrolla o deriva de (mandato) | norma superior → derivada, rol jerarquía normativa | `regulatesOrRegulated` | R063 |
| Fue expedido por (mandato) | mandato → agente | `issuedBy` | R065 |
| Es una competencia creada por (tipo de actividad) | mandato → tipo, rol creación | `regulatesOrRegulated` | R063 |
| Produce la serie (tipo de actividad) | tipo → serie o subserie | `isRelatedTo` (**general**) | R001 |
| Hito de su historia (agente) | tabla `hitos` | `affectsOrAffected` (**general**) | R059 |
| Función → subfunción | `concepto_superior_id` | `skos:broader` / `skos:narrower` | no es RiC |

Las relaciones **generales** son las que no tienen propiedad dedicada en RiC-O. El sistema usa la más específica que existe, como pide la propia ontología, y la interfaz lo dice con una marca «general».

## 8. Funcionalidades

**Navegación**

- Chips por los seis tipos y búsqueda que tolera tildes.
- En agentes, filtro por nivel de detalle (mínimo o completo) e insignia de nivel en cada fila.
- En tipos de actividad, interruptor entre lista y árbol.
- Cada fila muestra la clase exacta de RiC-O según el subtipo, por ejemplo `rico:Group`, y la versión si es un mecanismo.

**Ficha de agente.** Cuatro áreas plegables:

1. **Identificación:**
   - tipo;
   - forma autorizada (no editable aquí);
   - otras formas del nombre (paralela con su lengua, normalizada con su regla, otra con su periodo);
   - identificadores con su esquema: interno, VIAF, Wikidata, ISNI o LCNAF. Los externos llevan una insignia distinta y un enlace a la autoridad;
   - versión obligatoria si es un mecanismo.
2. **Descripción:**
   - fechas de existencia en EDTF, con inicio sin fin admitido;
   - historia;
   - estatuto jurídico (en entidad corporativa y grupo);
   - estructura interna;
   - contexto general;
   - línea de tiempo institucional;
   - lugares de actuación;
   - funciones (las actividades que ejerce);
   - mandato que lo creó.
3. **Relaciones:** con otros agentes. Se declaran en los dos sentidos («tiene como subordinado» o «está subordinado a»), con vigencia EDTF opcional y nota.
4. **Control:**
   - identificador del registro;
   - reglas (por defecto, ISAAR-CPF 2.ª edición);
   - nivel de detalle calculado;
   - fechas de creación y de última revisión, leídas de la auditoría;
   - fuentes.

**Ficha de lugar**

- Tipo de lugar.
- Coordenadas, validadas en rango y siempre juntas, con un mapa de OpenStreetMap.
- Lugar superior, uno solo, sin ciclos.
- Lugares que contiene.
- Nombres históricos con su periodo.

**Ficha de tipo de actividad**

- Superior (`skos:broader`) y específicos (`skos:narrower`), sin ciclos y con niveles ilimitados.
- Serie o subserie que produce. Solo se admite una serie o una subserie, nunca un expediente.
- Mandato que creó la competencia.
- Actividades que llevan este tipo.

**Ficha de actividad**

- Tipo y periodo, tomados de la descripción.
- Agente que la ejerce.
- Mandato que la regula.
- Actividad mayor (una sola, sin ciclos) y sub-actividades.

**Ficha de mandato**

- Tipo de instrumento y fecha de expedición.
- Entidad que lo expidió.
- Actividades que regula.
- Agentes y competencias que creó.
- Jerarquía normativa en los dos sentidos, sin ciclos.

**Nada se borra.** Una forma del nombre, un identificador, un hito o un vínculo que sobra queda «anulado», con quién y cuándo en la auditoría.

**Fusión.** Sigue igual que en la versión 1. Además, la ficha de la absorbida pasa a la definitiva:

- hitos;
- formas del nombre, y el nombre de la absorbida como «otra forma» (como «nombre histórico» si es un lugar);
- identificadores;
- los específicos del árbol de funciones;
- se anula la relación que quedó de la entidad consigo misma.

Dos versiones del mismo programa nunca se sugieren para fusión.

**Mecanismos.** `vocabulario.mecanismo()` es el único punto de registro. Busca por nombre y versión exactos; si existe lo reutiliza, y si no, lo crea con el servicio único de creación. Preservación lo usa para Ghostscript y descripción para el motor de análisis.

## 9. Flujos

**Enriquecer un agente creado desde descripción**

1. En Vocabularios, chip Agentes y filtro «Ficha mínima».
2. Abrir el agente. Las áreas están desplegadas y se edita en el lugar.
3. Al guardar el primer dato del área de descripción (un campo o un hito), la insignia pasa a «Ficha completa». Queda en auditoría con el valor anterior y el nuevo.

**Declarar una relación jerárquica desde el subordinado**

1. «+ Está o estuvo subordinado a».
2. Buscar el superior y elegirlo.
3. Vigencia y nota, opcionales.
4. «Declarar vínculo».

La fila se guarda superior → subordinado, como pide RiC-O. Si el vínculo formaría un ciclo, el servidor lo rechaza con 422.

**Armar el árbol de funciones**

1. En la ficha de un tipo de actividad, «Cambiar» el superior.
2. Elegir otro tipo de actividad.
3. El árbol se ve en Vocabularios → Tipos de actividad → Árbol de funciones, con la serie que produce cada función.

## 10. Pantallas

| Pantalla | Ruta |
|---|---|
| Vocabulario (lista o árbol de funciones), con filtros | `/vocabularios` |
| Sugerencias de fusión | `/vocabularios` (pestaña) |
| Ficha de la entidad (según su clase), fusión manual, documentos | `/vocabularios/:id` |

## 11. UX/UI

- Las áreas de ISAAR son secciones plegables numeradas como en la norma. El área de control empieza plegada porque casi todo en ella se calcula.
- Cada vínculo muestra su propiedad de RiC-O y su código RiC-CM en tipografía monoespaciada y discreta. En la lectura inversa se muestra la propiedad inversa y el código con «i», por ejemplo `rico:isOrWasContainedBy · RiC-R007i`.
- Lo «general» se marca y se explica al pasar el cursor.
- Las fechas nunca se escriben en EDTF: se usa el mismo selector del módulo de descripción, con su forma legible en español.
- El mapa sale solo si hay coordenadas.
- El enlace «Abrir en OpenStreetMap» queda como respaldo si el mapa no carga.
- En móvil, las parejas etiqueta–valor pasan a una columna. Se verificó a 390 px sin desplazamiento horizontal.

## 12. Modelo de datos

**Migración 0010:** códigos nuevos del catálogo. Este módulo usa `contains_or_contained`, `has_direct_subevent`, `affects_or_affected`, `is_related_to` e `issued_by`.

**Migración 0011:**

- **`entidades_vocabulario`** gana estas columnas:
  - `version`;
  - `existencia_edtf`, `existencia_inicio` y `existencia_fin`;
  - `historia`, `estatuto_juridico`, `estructura` y `contexto_general`;
  - `reglas`, `nivel_detalle` (con índice) y `fuentes`;
  - `latitud` y `longitud` (con restricción de rango);
  - `tipo_lugar`;
  - `concepto_superior_id`: SKOS broader, con una restricción que impide que un concepto sea su propio superior.
- **`relaciones`** gana `fecha_edtf` y `nota`.
- **Tablas nuevas:**
  - `nombres_entidad`: tipo, nombre, idioma, regla, vigencia EDTF con inicio y fin, y estado vigente o anulado;
  - `identificadores_entidad`: esquema, valor y estado, con índice único vigente por entidad, esquema y valor;
  - `hitos`: agente, tipo, descripción, EDTF con inicio y fin, estado y agente original si hubo fusión.

La migración se probó de ida y de vuelta (0011 → 0009 → 0011).

## 13. API

Todas bajo `/api/vocabulario`, con sesión y permiso del módulo: leer para GET y escribir para lo demás.

| Método y ruta | Qué hace |
|---|---|
| `GET ?fondo_id&clase&q&estado&orden&nivel_detalle` | Lista. `nivel_detalle` filtra agentes por mínimo o completo |
| `GET /funciones/arbol?fondo_id` | Árbol completo de funciones (SKOS), con las series que produce cada una |
| `GET /series?fondo_id&q` | Series y subseries, para enlazarlas con su función |
| `GET /{id}` | Detalle con `ficha` según la clase |
| `PATCH /{id}` | Campos de enriquecimiento de la clase. El nombre autorizado no (422). La versión de un mecanismo no puede quedar vacía. Recalcula el nivel de detalle |
| `POST /{id}/nombres` | Otra forma del nombre, o nombre histórico de un lugar |
| `POST /{id}/identificadores` | Identificador con esquema; valida la forma de Wikidata, VIAF e ISNI |
| `POST /{id}/hitos` | Hito de la línea de tiempo (EDTF) |
| `POST /{id}/registros/{nombre\|identificador\|hito}/{rid}/anular` | Anula sin borrar |
| `POST /{id}/vinculos` | Declara un vínculo del catálogo de §7. Valida clases, fondo, repetición, superior único y ciclos |
| `POST /{id}/vinculos/{relacion_id}/anular` | Anula sin borrar |
| `PUT /{id}/concepto-superior` | Ubica un tipo de actividad en el árbol, sin ciclos |
| `POST /{id}/relaciones-agente` | (versión 1, se mantiene) Relación entre agentes, ahora con vigencia y nota; usa el mismo servicio |
| Sugerencias, fusión, detección, parámetros, verificar | Sin cambios de contrato |

## 14. Uso de IA

Ninguno en este módulo. La ficha de autoridad la escribe una persona.

La comparación de nombres sigue siendo por trigramas, determinista y explicable. El motor de análisis es un `rico:Mechanism` más del vocabulario, con su versión, y no decide nada aquí.

## 15. Seguridad

- Permisos en el backend: el revisor y el rol de consulta reciben 403 en cualquier escritura (hay prueba).
- Validación de cada campo:
  - rangos de coordenadas;
  - listas cerradas de estatuto jurídico, tipo de lugar, esquema de identificador, tipo de hito y tipo de forma;
  - forma de los identificadores externos;
  - EDTF del subconjunto del sistema;
  - textos con longitud máxima.
- No se vincula entre fondos, ni con una entidad fusionada, ni una entidad consigo misma. Una entidad fusionada no se edita (409).
- No hay ninguna ruta que borre.

## 16. Auditoría (qué queda registrado)

| Acción | Qué guarda |
|---|---|
| `entidad_enriquecida` | Solo los campos que cambiaron, con el valor anterior y el nuevo, incluido el cambio de nivel de detalle |
| `nombre_agregado`, `identificador_agregado`, `hito_agregado` | El registro nuevo (si el identificador es externo, también) |
| `nombre_anulado`, `identificador_anulado`, `hito_anulado` | Estado vigente → anulado |
| `vinculo_declarado` | Código, rol, propiedad de RiC-O, origen, destino, vigencia y nota |
| `vinculo_anulado` | Estado vigente → anulada |
| `concepto_superior_cambiado` | `skos:broader` anterior y nuevo |
| `mecanismo_registrado` | Nombre y versión |
| `fusion_vocabulario` | Como en la versión 1, más los registros de la ficha que se movieron |

Las fechas de creación y de última revisión de la ficha **se leen** de estos eventos; no se capturan a mano.

## 17. Interoperabilidad

- **Identificadores externos:** cada uno lleva su esquema, y el sistema arma la URI de la autoridad (VIAF, Wikidata, ISNI, LCNAF). Es lo que permitirá exportar `rico:hasOrHadIdentifier` y `owl:sameAs` en el módulo de instrumentos.
- **Árbol de funciones:** sale de SKOS, el estándar del W3C. Un tesauro de funciones de otra institución podría alinearse con `skos:exactMatch`.
- **Coordenadas:** en grados decimales (WGS84), el formato que usan OpenStreetMap y los geoportales del país.

## 18. Normativa aplicable

- **ISAAR (CPF), 2.ª edición:** las cuatro áreas de la ficha y el nivel de detalle (5.4.6).
- **RiC-CM 1.0 y RiC-O 1.1:** clases y relaciones de §6 y §7, verificadas contra el OWL oficial.
- **SKOS** (W3C, 2009), para el árbol de funciones.
- **Metodología colombiana de TRD** (Acuerdo 004 de 2019 del AGN): vínculo entre función y serie.
- **EDTF** (ISO 8601-2), el mismo subconjunto del módulo de descripción.
- La autora debe confirmar la versión vigente de los acuerdos del AGN.

## 19. Arquitectura

- **`app/servicios/vocabulario.py`:** verificación, creación, conexiones, detección, fusión (ahora con la ficha), relaciones entre agentes (delegan en autoridad) y `mecanismo()`.
- **`app/servicios/autoridad.py` (nuevo):** ficha por clase, enriquecimiento y nivel de detalle, nombres, identificadores, hitos, catálogo de vínculos (`VINCULOS`) con su validación, y árbol SKOS.
- **`app/servicios/ric_o.py`:** el mapeo único a RiC-O, que usan la ficha y la futura exportación.

### Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| **Algoritmo de similitud** (exigida, §4) | Levenshtein; **trigramas `pg_trgm`**; rapidfuzz | **pg_trgm** (sin cambios desde la versión 1) | Viene con PostgreSQL, tiene índice GIN, tolera abreviaturas y cambios de orden | Falsos parecidos en nombres cortos; nunca se fusiona sin una persona |
| **Ejecución periódica** (exigida, §4) | Celery y Redis; cron; APScheduler; **trabajador existente** | **Trabajador existente** (sin cambios) | Celery y Redis no están instalados, y sumarían unos 150 MB a un servidor de 2 GB por una tarea diaria | Si el trabajador se detiene no hay detección; existe el botón «Buscar ahora» |
| **Librería de mapas** (exigida, §4) | (a) Mapa estático propio (SVG) sin servicio externo; (b) **Leaflet** con teselas de OpenStreetMap; (c) **mapa incrustado de OpenStreetMap** (`export/embed`), sin librería; (d) Google Maps u otro servicio con clave | **(c) mapa incrustado de OpenStreetMap** | Solo hay que ubicar un punto, sin rutas ni distancias. No suma ninguna dependencia a la interfaz (Leaflet son 150 kB y su hoja de estilos). Es libre, no pide clave ni cobra. (a) exigiría datos cartográficos propios de Colombia. (d) es de pago a partir de cierto uso | Depende de que openstreetmap.org esté disponible. Si no carga, la ficha muestra igual las coordenadas y el enlace. Si algún día se necesitan varios puntos en un mismo mapa, se pasa a Leaflet |
| Dónde guardar la ficha | JSON libre en una columna; tabla aparte por clase; **columnas tipadas más tablas para lo que se repite** | **Columnas tipadas** (lo que se valida o filtra) y **tablas** para nombres, identificadores e hitos | El nivel de detalle se filtra con un índice y las coordenadas se validan en la base (restricciones `CHECK`). Las listas repetibles necesitan estado y auditoría por elemento. Un JSON libre no se puede validar ni consultar con rigor | Más columnas en una tabla que comparten seis clases; el servicio decide cuáles aplican a cada una (`campos_de`) |
| Un solo catálogo de vínculos | Una ruta y una tabla por cada relación; **un catálogo declarativo (`VINCULOS`) sobre la tabla `relaciones`** | **Catálogo declarativo** | Una sola validación (clases, fondo, repetición, superior único, ciclos) y una sola auditoría para las trece relaciones. Agregar una relación es una línea, no una ruta | Un error en el catálogo afecta a todas; por eso cada vínculo tiene su prueba |
| Jerarquía de funciones | Relación RiC-O entre tipos; tabla aparte; **`skos:broader` como columna `concepto_superior_id`** | **Columna SKOS, un solo superior** | RiC-O no tiene jerarquía entre tipos (anexo, §2). Una función con un solo superior es lo que pide la TRD y hace que el árbol no sea ambiguo | SKOS admite varios superiores; si el fondo los necesitara, se pasaría a una tabla |
| Tipo de lugar | Clase del vocabulario editable por fondo; **lista controlada en el código** | **Lista controlada**: país, departamento, provincia, municipio, corregimiento, vereda, barrio, edificio, otro | Cubre la división político-administrativa colombiana y el caso del edificio. Con un vocabulario por fondo, la misma categoría podría escribirse de varias formas | Un fondo con otra división territorial necesita ampliar la lista: es un cambio de una línea |
| Un mecanismo por versión | Un mecanismo con un historial de versiones; **un registro por versión** | **Un registro por versión**, con nombre «Programa versión» | Cada resultado debe atribuirse a la versión exacta que lo produjo, y las fusiones las excluyen | Hay más registros de mecanismo; son pocos |
| El nombre autorizado | Editable aquí; **solo desde descripción** | **Solo desde descripción** | Cambiarlo debe pasar por la verificación de duplicados, como pide el prompt | Para corregir una errata hay que reabrir una descripción |
| Nivel de detalle | Campo que elige la persona; **calculado** | **Calculado** al guardar | El prompt lo define por el área de descripción; si lo eligiera la persona, el filtro mentiría | Un solo dato de historia ya cuenta como completo; es la regla del prompt |
| Deshacer una fusión | Botón; **no ofrecerlo** | **No se ofrece** (sin cambios) | Los datos para revertir se conservan, pero las reglas no están definidas | Se corrige editando |

## 20. Código (dónde vive, cómo se organiza)

```
alembic/versions/0010_ocr_y_codigos_ric_o.py   códigos verificados (R007, R059, R001, R065…)
alembic/versions/0011_autoridad_isaar.py       ficha, nombres, identificadores, hitos, SKOS
app/models/descripcion.py                     columnas y tablas nuevas; listas controladas
app/servicios/autoridad.py                    ficha, vínculos, árbol de funciones (nuevo)
app/servicios/vocabulario.py                  fusión con ficha; mecanismo(); relaciones de agentes
app/servicios/ric_o.py                        mapeo único a RiC-O 1.1
app/routers/vocabulario.py                    rutas nuevas (§13)
frontend/src/components/FichaAutoridad.tsx    las fichas por clase (nuevo)
frontend/src/pages/EntidadVocabulario.tsx     integra la ficha
frontend/src/pages/Vocabularios.tsx           filtro de nivel de detalle; árbol de funciones
tests/test_autoridad.py                       22 pruebas de la versión 2
tests/test_vocabularios.py                    pruebas de la versión 1, todas siguen pasando
```

## 21. Pruebas

**22 pruebas nuevas** en `tests/test_autoridad.py`, contra PostgreSQL real. Las de la versión 1 se mantienen sin cambios y pasan. Cada exigencia del prompt (§11) tiene la suya:

- **Las cuatro áreas** se guardan, incluida una existencia abierta («1948/» → «desde 1948 (fin desconocido)», inicio 1948-01-01, sin fin). Las fechas de control salen de la auditoría y no se pueden escribir.
- **El nombre autorizado** no se cambia por PATCH (422).
- **Nivel de detalle:**
  - un dato que no es del área de descripción no lo cambia;
  - la historia lo pasa a completo, con un evento que guarda el valor anterior y el nuevo;
  - vaciarla lo devuelve a mínimo;
  - el filtro devuelve exactamente cada grupo.
- **Relación entre agentes:**
  - una sola fila leída en los dos sentidos, con propiedad inversa y código RiC-CM con «i»;
  - vigencia y nota se guardan;
  - la sucesión al revés se rechaza (ciclo);
  - la asociativa no se repite al revés.
- **Jerarquía entre cargos** con la misma relación R045.
- **Anular** vínculos, formas e hitos: no se borran, quedan en auditoría, y la ficha vuelve a mínima si queda vacía.
- **Grupo:** se guarda, se lista con su subtipo y se exporta como `rico:Group`.
- **Identificador externo:** conserva su esquema, se distingue del interno, arma su URI, valida su forma y no se repite.
- **Mecanismo:**
  - la misma versión reutiliza el mismo registro y otra versión crea otro;
  - la versión no puede vaciarse;
  - dos versiones no se sugieren para fusión;
  - sin versión, la ficha queda marcada.
- **Hitos:** se listan en orden cronológico aunque se carguen desordenados (1948, década de 1960, c. 1975), con `rico:Event` y R059. Cuentan para el nivel de detalle. Una fecha imposible se rechaza.
- **Lugar:**
  - coordenadas, tipo y superior se guardan y se muestran;
  - el superior ve lo que contiene;
  - los nombres históricos salen en orden con su periodo («hasta 1539 (inicio desconocido)», «de 1541 a 1819»);
  - se rechazan un segundo superior, un ciclo, una latitud de 95, una coordenada sin su par y un tipo inexistente.
- **Árbol de funciones:**
  - tres niveles;
  - ciclo directo e indirecto rechazados;
  - broader y narrower en la ficha;
  - no deja filas en `relaciones` (no es RiC-O);
  - un agente no entra al árbol.
- **Función → serie:** se muestra en la ficha y en el árbol, marcada como general (R001). Un expediente se rechaza.
- **Sub-actividades:** la mayor ve sus menores y la menor ve su mayor, con `rico:hasDirectSubevent`. No se confunde con SKOS. Una sola mayor, sin ciclos, solo entre actividades.
- **Mandato derivado:** se navega en los dos sentidos, sin ciclos, guardado como R063 con rol de jerarquía normativa.
- **Mandato que crea un agente** (R067, rol creación) y **entidad que lo expidió** (R065).
- **Mandato que crea una competencia** (R063, rol creación).
- **Entre fondos, o con una entidad fusionada:** no se vincula; una entidad fusionada no se edita (409).
- **Fusión con ficha:**
  - hitos, identificadores y formas pasan a la definitiva;
  - el nombre absorbido queda como otra forma;
  - la relación consigo misma queda anulada;
  - la auditoría cuenta los registros movidos.
- **Permisos:** el revisor y el rol de consulta reciben 403 en PATCH y en hitos; el revisor puede leer.

**Prueba del mapeo** (`tests/test_ric_o.py`): todas las propiedades de §7 existen en el OWL y se usan con clases que su dominio y su rango admiten.

**Verificación visual** en navegador real sobre el fondo de prueba:

- ficha de agente con las cuatro áreas;
- persona con Wikidata y VIAF;
- mecanismo con versión;
- lugar con mapa, superior y nombres históricos;
- tipo de actividad con broader y narrower;
- actividad con sub-actividad;
- mandato con emisor, jerarquía y creación;
- lista filtrada por ficha mínima;
- árbol de funciones con su serie;
- declarar un vínculo desde la pantalla;
- móvil a 390 px;
- sin errores de JavaScript.

El mapa no cargó en el entorno de construcción porque su red bloquea openstreetmap.org. La ficha mostró igual las coordenadas y el enlace.

## 22. Criterios de aceptación

| Criterio (prompt §11–12) | Cumple |
|---|---|
| Verificación y detección para los seis tipos, sin falsos positivos claros | ✓ (versión 1, sin cambios) |
| Aprobar redirige todo, marca fusionada y audita; descartar no cambia nada; la fusión manual da lo mismo | ✓ |
| Ninguna fusión sin auditoría (prueba explícita) | ✓ |
| Ficha de agente con sus cuatro áreas, incluida la existencia abierta | ✓ |
| El nivel de detalle cambia solo y el filtro es correcto | ✓ |
| Relación entre agentes con inversa automática (una fila, dos lecturas) | ✓ |
| Árbol de funciones desde SKOS, sin ciclos (prueba explícita) | ✓ |
| Sub-actividades en los dos sentidos, sin confundirse con SKOS | ✓ |
| Agente grupo se guarda, lista y filtra | ✓ |
| Identificador externo con esquema, distinto del interno | ✓ |
| Mecanismo con versión, registro único reutilizable | ✓ (lo reutiliza preservación desde la fase siguiente) |
| Hitos con fecha, en orden cronológico | ✓ |
| Lugar con coordenadas, tipo, superior y nombres históricos con periodo | ✓ |
| Tipo de actividad con su serie | ✓ |
| Mandato derivado navegable en los dos sentidos, sin ciclos | ✓ |
| Tres decisiones del §4 con tabla completa (similitud, periodicidad, mapas) | ✓ (§19) |
| Confirmación contra el OWL de la relación asociativa | ✓ R044, propiedad dedicada y simétrica (anexo de verificación, punto 3) |
| Ejemplos documentados sobre el fondo de prueba | ✓ (§23) |

**Pendientes honestos:**

- El fondo de prueba es sintético. Los ejemplos de §23 muestran que el modelo funciona, no que la información histórica sea cierta. Para la sustentación conviene repetirlos con entidades reales del fondo.
- La jerarquía normativa con R063 es una interpretación declarada (ver el riesgo en el anexo de verificación).

## 23. Evidencia concreta de aplicación de RiC

**Ficha ISAAR completa** sobre el fondo de prueba: «Secretaría de Gobierno de Tunja».

```
rico:CorporateBody  «Secretaría de Gobierno de Tunja»          nivel de detalle: completo
  1. Identificación
     otra forma del nombre: «Secretaría de Gobierno»
     identificador interno: AMT-SG-01
  2. Descripción
     existencia: 1948/  → «desde 1948 (fin desconocido)»
     historia: «Creada por el Acuerdo 12 de 1948 para atender el orden público y los permisos.»
     estatuto jurídico: pública · estructura: «Despacho del secretario y dos inspecciones de policía.»
     línea de tiempo (rico:Event, rico:affectsOrAffected R059):
       12 de marzo de 1948 · Creación por el Acuerdo 12 del Concejo
       década de 1950       · Asume la inspección de espectáculos
     actúa o actuó en Tunja                         rico:hasOrHadLocation       RiC-R075i
     ejerce o ejerció «Ejercicio de la policía local en 1948»  rico:performsOrPerformed RiC-R060i
     fue creado o establecido por «Acuerdo 12 de 1948»          rico:authorizedBy   RiC-R067i
  3. Relaciones
     jerárquica:  está o estuvo subordinado a «Alcaldía Municipal de Tunja»
                  vigencia desde 1948 (fin desconocido)      rico:isOrWasSubordinateTo   RiC-R045i
     temporal:    tiene como sucesor a «Secretaría de Gobierno y Convivencia de Tunja»
                  vigencia 1998 · «Reforma administrativa municipal.»   rico:hasSuccessor  RiC-R016
     asociativa:  está asociado con «Junta de Ornato y Mejoras» (rico:Group)
                  «Colaboraron en el trámite de las fiestas de 1948.»  rico:isAgentAssociatedWithAgent RiC-R044
  4. Control
     reglas: ISAAR (CPF), 2.ª edición · creación y última revisión: tomadas de la auditoría
     fuentes: «Gaceta municipal de Tunja, 1948.»
```

**Otros ejemplos del mismo fondo:**

- **Grupo:** «Junta de Ornato y Mejoras», un `rico:Group` usado directamente. Tiene como sucesor a la Secretaría de Obras Públicas (1952).
- **Identificador externo:** «Gustavo Rojas Pinilla», `rico:Person`, con Wikidata Q318229 → `https://www.wikidata.org/entity/Q318229` y VIAF 35360567, junto con su insignia de autoridad externa.
- **Mecanismo:** «Ghostscript 10.05.1», `rico:Mechanism`, con versión 10.05.1 (`rico:technicalCharacteristics`). Registrado una sola vez con `vocabulario.mecanismo()`.
- **Lugar:** «Tunja», municipio.
  - Coordenadas 5.5353, -73.3678 (`rico:geographicalCoordinates`).
  - Está dentro de Boyacá (R007i), que está dentro de Colombia.
  - Nombres históricos (`rico:PlaceName`): Hunza, hasta 1539; Muy Noble y Muy Leal Ciudad de Tunja, de 1541 a 1819.
- **Función y serie:** el árbol es Gobierno municipal → Policía local → Permisos de espectáculos públicos (`skos:broader`). Esta última produce la serie «Permisos» (R001, general).
- **Actividad compuesta:** «Ejercicio de la policía local en 1948» tiene como sub-actividad la «Expedición de permisos para las fiestas de 1948» (`rico:hasDirectSubevent`).
- **Mandato:** «Acuerdo 12 de 1948».
  - Fue expedido por el Concejo Municipal de Tunja (`rico:issuedBy`, R065).
  - Desarrolla la Ley 4 de 1913 (R063, jerarquía normativa).
  - Crea la Secretaría de Gobierno (R067, creación).
  - Regula la actividad de policía local (R063).
