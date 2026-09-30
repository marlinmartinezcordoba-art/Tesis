# Módulo 3 · Vocabularios y control de autoridad

**Estado:** entregado, pendiente de validación.

---

## 1. Propósito

Mantener un registro único y reutilizable, por fondo, de los agentes, lugares y formas documentales. Así, la misma entidad no se convierte en varios nodos desconectados cada vez que aparece en un documento nuevo. El módulo:

- evita duplicados antes de que existan (servicio de verificación, que usa descripción);
- detecta los que ya se colaron (sugerencias de fusión);
- permite fusionarlos con aprobación humana, sin borrar nada y con rastro completo.

## 2. Auditoría (qué se revisó antes de construirlo)

**Documentos revisados:**

- el prompt del módulo 3 (secciones 1 a 10);
- el diseño consolidado, Parte 4;
- el mockup «Sistema RIC · Vocabularios»;
- lo ya construido en el módulo 2: `app/servicios/vocabulario.py` con `verificar()` y `crear()`, y la tabla `entidades_vocabulario`.

**Hallazgos:**

- **El servicio de verificación ya existía** (se construyó en el módulo 2 como servicio de este módulo). No se duplicó. Este módulo lo **amplía** con la navegación, la detección y la fusión en el mismo archivo. La decisión de similitud (§19) ya estaba documentada en el módulo 2 y aquí se completa con su uso para la detección.
- **El prompt pide evaluar Celery y Redis «ya previstos en las dependencias aunque comentados».** En este proyecto reescrito no están. Sí existe un trabajador en segundo plano (el de la ingesta). Se evaluó en la tabla de decisión (§19).
- **La tabla ya tenía `estado` y `fusionada_en_id`** desde la migración 0003. Faltaba poder saber, en cada relación redirigida, a qué entidad apuntaba antes. Se agregó `relaciones.destino_original_id`.
- **El diseño pide «enlace directo a su descripción en el catálogo».** El catálogo navegable es del módulo 4. Mientras tanto, el enlace lleva a la descripción publicada (vista interna del módulo 2). Cuando exista el catálogo, se cambia el destino del enlace.
- **Colores:** el sistema de diseño del prompt repite el acento terracota. Se mantiene la paleta de tonos medios de RICORA, por decisión de la autora.

## 3. Problema que resuelve

Un mismo productor aparece escrito de muchas formas a lo largo de décadas: «Alcaldía Municipal de Tunja», «Alcaldia Mpal. de Tunja», «Alcaldía de Tunja». Si cada forma es un nodo distinto:

- el grafo se fragmenta;
- la búsqueda por productor devuelve resultados parciales;
- el índice del fondo (módulo 4) sale con entradas repetidas.

El control de autoridad es lo que hace confiable el punto de acceso.

## 4. Usuarios

| Rol | Qué hace |
|---|---|
| Archivista, coordinador de archivo, descriptor | Navega, revisa sugerencias, aprueba o descarta, fusiona a mano |
| Revisor, auditor (lectura) | Ve el vocabulario, las sugerencias y el historial, sin modificar |
| Administrador | Todo lo anterior, y además cambia los criterios de detección |
| Consulta | Sin acceso al módulo |

Los permisos salen de la tabla de roles del módulo de autenticación: módulo «vocabularios», nivel leer o escribir. Cualquier petición que modifica algo exige escritura.

## 5. Casos de uso

1. Ver el vocabulario del fondo, filtrar por tipo, buscar por nombre y ordenar por número de documentos.
2. Revisar una sugerencia de fusión y aprobarla, eligiendo cuál queda como definitiva.
3. Descartar una sugerencia («son distintas»): no cambia nada y el par no se vuelve a sugerir.
4. Abrir una entidad y ver sus documentos, las formas que absorbió y su historial de fusiones.
5. Fusionar a mano desde el detalle: buscar otra entidad del mismo tipo, elegir la definitiva y confirmar.
6. Consultar una entidad fusionada: con el filtro «Ver fusionadas», o desde un documento antiguo que la citaba.
7. Pedir una búsqueda de candidatos en el momento, sin esperar la periódica.
8. (Administrador) Ajustar los criterios: similitud mínima, conexiones máximas y frecuencia.
9. (Descripción) Verificar si una entidad ya existe antes de crearla. Es el servicio que consume el módulo 2.

## 6. Entidades RiC involucradas

| Entidad del vocabulario | RiC-CM 1.0 | Subtipos |
|---|---|---|
| Agente | RiC-E07 Agent | Persona (E08), Entidad corporativa (E11), Cargo (E12), Familia (E10) |
| Lugar | RiC-E22 Place | — |
| Forma documental | RiC-A17 Documentary form type (atributo del Record, gestionado como vocabulario controlado) | — |

La sugerencia de fusión no es una entidad RiC: es un registro de trabajo interno del sistema.

## 7. Relaciones RiC involucradas

Este módulo **no crea relaciones nuevas**. Redirige las que ya existen. Al fusionar, cambia el destino de toda relación **vigente** que apuntaba a la entidad absorbida, conservando su código RiC. Las relaciones ya anuladas se dejan como estaban, porque son historia de correcciones pasadas:

- *has creator* (RiC-R027);
- *has sender* (R031); *has addressee* (R032);
- *has or had subject* (R019);
- las demás del catálogo curado que apunten a un agente o lugar.

Además, el campo `forma_documental_id` de cada Record que usaba la forma absorbida pasa a la definitiva.

**La equivalencia entre la absorbida y la definitiva** queda en `fusionada_en_id`. Es una relación explícita, del tipo «es la misma que». RiC-CM no define una relación oficial de equivalencia de autoridades. Por eso se guarda como enlace de control interno y no se inventa un código RiC-R. En RiC-O, al exportar, el equivalente natural es `owl:sameAs`. Esa decisión se toma en el módulo 4.

## 8. Funcionalidades

- **Navegación:**
  - vocabulario del fondo con chips de filtro por tipo (Todos, Agentes, Lugares, Formas documentales);
  - búsqueda por nombre, que tolera tildes y errores menores (trigramas);
  - orden por documentos conectados, ascendente o descendente, o por nombre;
  - cada fila muestra la insignia de tipo, el nombre, el subtipo, la referencia RiC y el número de documentos a la derecha.
- **Sugerencias:** una tarjeta por par, con las dos entidades lado a lado, el porcentaje de similitud al centro y los botones «Son distintas» y «Aprobar fusión». El sistema propone como definitiva la de más conexiones; la persona puede cambiarla.
- **Detalle:** documentos conectados con enlace a su descripción, formas absorbidas, historial de fusiones y «Fusionar con otra entidad».
- **Fusión:**
  - es una sola transacción;
  - redirige las relaciones y las formas documentales;
  - marca la absorbida como fusionada;
  - si la absorbida ya había absorbido otras, esas pasan a apuntar a la nueva definitiva (no quedan cadenas);
  - las demás sugerencias pendientes que involucran a la absorbida quedan como «obsoleta»;
  - todo queda en la auditoría.
- **Detección periódica:** compara entre sí las entidades activas del mismo tipo y fondo. Sugiere solo pares con similitud alta en los que **ambas** tengan pocas conexiones. Nunca repite un par ya decidido.
- **Criterios configurables** (solo el administrador):
  - similitud mínima, 60 % por defecto;
  - conexiones máximas, 10 por defecto;
  - frecuencia, cada 24 h por defecto.
- **Rastro desde el documento:** en la descripción publicada de un documento cuya entidad se fusionó, aparece «Antes citaba a «X», fusionada en esta entidad», con enlace.

## 9. Flujos

**Aprobar una sugerencia:**

1. El trabajador en segundo plano, cuando le toca, busca pares y deja sugerencias pendientes.
2. La pestaña «Sugerencias de fusión» muestra el contador.
3. El archivista compara las dos entidades y abre «ver documentos» si duda.
4. Elige cuál queda como definitiva y pulsa «Aprobar fusión».
5. El servidor bloquea la sugerencia (`SELECT … FOR UPDATE`), fusiona en una transacción y registra la auditoría.
6. Aviso: «X se fusionó en Y».

**Fusión manual:**

1. En el detalle, «Fusionar con otra entidad».
2. Se busca por nombre; solo aparecen entidades del mismo tipo y fondo.
3. Se elige una; se muestran las dos lado a lado con el selector «Queda como definitiva».
4. «Confirmar fusión».
5. Si la definitiva es la otra, la pantalla se mueve a su detalle.

**Descartar:** «Son distintas». La sugerencia queda descartada, con auditoría. El par no se vuelve a proponer.

## 10. Pantallas

| Pantalla | Ruta |
|---|---|
| Vocabulario (pestaña) | `/vocabularios` |
| Sugerencias de fusión (pestaña, con contador) | `/vocabularios` |
| Detalle de entidad, con fusión manual | `/vocabularios/:id` |

Entrada «Vocabularios» en la barra lateral, dentro de «Trabajo archivístico», visible solo para roles con acceso de lectura.

## 11. UX/UI

- **Nada se fusiona con un solo clic accidental:** en la sugerencia hay que pulsar «Aprobar fusión». En la manual hay dos pasos (elegir y confirmar), con el selector de definitiva siempre visible.
- **Consecuencia antes de decidir:** la tarjeta dice qué va a pasar, por ejemplo «Si aprueba, el documento de «X» pasa a «Y»».
- **Lenguaje archivístico:** «queda como definitiva», «son distintas», «formas absorbidas».
- Las referencias RiC (E07, E22, A17) aparecen discretas, para quien las quiera ver.
- En móvil las dos columnas se apilan y la similitud queda entre ellas. Se verificó que no hay desplazamiento horizontal a 390 px.

## 12. Modelo de datos

**Tabla nueva `sugerencias_fusion` (migración 0005):**

- `fondo_id`, `clase`;
- el par ordenado `entidad_a_id < entidad_b_id`;
- `similitud`;
- `estado`: pendiente / aprobada / descartada / obsoleta;
- `resuelta_en`, `resuelta_por_id`, `definitiva_id`.

El índice único `ux_sugerencia_par` impide repetir un par.

**Columna nueva `relaciones.destino_original_id`:** a qué entidad apuntaba la relación antes de la primera fusión que la movió. Si hay fusiones sucesivas, se conserva la original (`coalesce`).

**Ya existentes** (migración 0003): en `entidades_vocabulario`, `estado` (activa/fusionada), `fusionada_en_id` y `nombre_normalizado` con índice GIN de trigramas.

**Parámetros nuevos** en la tabla `parametros`:

- `fusion_similitud_pct`;
- `fusion_max_conexiones`;
- `fusion_horas_deteccion`;
- `fusion_ultima_deteccion` (interno).

## 13. API

Todas bajo `/api/vocabulario`. Exigen sesión y permiso del módulo: leer para GET, escribir para lo demás.

| Método y ruta | Qué hace |
|---|---|
| `GET /api/vocabulario?fondo_id&clase&q&estado&orden` | Lista con búsqueda, filtro por tipo, activas o fusionadas, y orden |
| `GET /api/vocabulario/{id}` | Detalle: documentos, documentos históricos, absorbidas, historial |
| `POST /api/vocabulario/verificar` | Servicio de similitud |
| `GET /api/vocabulario/sugerencias-fusion?fondo_id` | Cola de candidatos pendientes |
| `POST /api/vocabulario/sugerencias-fusion/{id}/aprobar` | Ejecuta la fusión; `definitiva_id` opcional |
| `POST /api/vocabulario/sugerencias-fusion/{id}/descartar` | Marca el par como distinto |
| `POST /api/vocabulario/fusionar` | Fusión manual: `definitiva_id`, `absorbida_id` |
| `POST /api/vocabulario/detectar?fondo_id` | Busca candidatos en el momento |
| `GET/PUT /api/vocabulario/parametros` | Criterios de detección (PUT solo administrador) |

**Sobre `verificar`:** el prompt permite que sea de uso interno. El módulo de descripción **no** lo llama por HTTP: importa el mismo servicio de Python (`vocabulario.verificar`). La ruta HTTP existe para la pantalla y exige permiso de escritura del módulo. Así no queda ninguna puerta abierta sin sesión.

**Ampliación del módulo 2:** `GET /api/descripcion/registros/{id}` ahora incluye, por cada agente o lugar redirigido, `antes_de_fusion` con la entidad que citaba originalmente.

## 14. Uso de IA

**Ninguno.** La detección es comparación de texto por trigramas, determinista y explicable: se puede decir exactamente por qué se sugirió un par. Es deliberado. Una decisión de autoridad no debe depender de un modelo que no se puede auditar. Y la regla del prompt, «nunca fusionar sin aprobación humana, ni con 100 % de similitud», se cumple sin excepciones.

## 15. Seguridad

- Permisos por rol en el backend. La interfaz solo oculta botones; quien decide es el servidor.
- Aprobar bloquea la fila de la sugerencia (`FOR UPDATE`): dos personas que aprueban a la vez no fusionan dos veces. La segunda recibe 409 «ya no está pendiente».
- **No se fusionan entidades de distinto tipo o fondo, ni una entidad consigo misma, ni una ya fusionada** (409).
- Todo parámetro se valida con rango.
- Solo el administrador cambia los criterios.
- **No destructivo:** no hay ninguna ruta que borre entidades, sugerencias ni relaciones.

## 16. Auditoría (qué queda registrado)

| Acción | Cuándo | Qué guarda |
|---|---|---|
| `fusion_vocabulario` | Toda fusión, sugerida o manual | Quién, cuándo, entidad definitiva y absorbida (id, nombre, conexiones antes), relaciones movidas, formas documentales movidas, origen (sugerencia o manual) |
| `sugerencia_fusion_descartada` | Al descartar | Quién, cuándo, el par |
| `parametro_cambiado` | Al cambiar un criterio | Valor anterior y nuevo |

La tabla de auditoría es de solo anexar (disparador del módulo de autenticación). Una prueba explícita confirma que **cada** fusión deja exactamente un evento.

## 17. Interoperabilidad

- El vocabulario consolidado será la fuente directa del **índice** del fondo (módulo 4), según el diseño consolidado.
- `fusionada_en_id` permite exportar la equivalencia (`owl:sameAs` en RiC-O) y mantener vivas las URI antiguas, que redirigen a la definitiva.
- **Pendiente para más adelante:** alinear las autoridades con vocabularios externos (VIAF, Wikidata, tesauros de lugares del DANE/IGAC). No lo pide este prompt; queda anotado.

## 18. Normativa aplicable

- **ISAAR(CPF)** (ICA): registro de autoridad único para instituciones, personas y familias. Este módulo es su aplicación práctica.
- **RiC-CM 1.0:** Agent (E07) y subtipos, Place (E22), Documentary form type (A17).
- **ISAD(G), elemento 3.2.1:** el nombre del productor debe ser coherente en toda la descripción.
- **NTC 4095** y el **Acuerdo 027 de 2006 (AGN)**, sobre puntos de acceso normalizados.
- **Principio de no destructividad** del sistema: la absorbida nunca se borra.

## 19. Arquitectura

- **Servicio:** `app/servicios/vocabulario.py` concentra la normalización, la verificación, la creación, las conexiones, la detección y la fusión. Descripción y este módulo usan el mismo código.
- **Detección:** corre dentro del trabajador en segundo plano que ya existía (`app/trabajador.py`), en su propio ciclo, solo cuando pasa el intervalo configurado.
- **Rutas:** `app/routers/vocabulario.py`.

### Decisiones

Las dos que el prompt exige (§4) están primero.

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| **Algoritmo de similitud** | Distancia de edición clásica (Levenshtein, en Python o con `fuzzystrmatch`); **trigramas con `pg_trgm`**; librería externa (rapidfuzz) | **pg_trgm** sobre el nombre en minúsculas y sin tildes. Umbral 0,45 para verificar (preguntar de más no hace daño) y 60 % para sugerir fusión (configurable) | Ya viene con PostgreSQL: cero dependencias nuevas. El índice GIN hace la comparación en la base de datos, sin traer el vocabulario entero a Python. La autocomparación para detectar se resuelve con una sola consulta. Tolera el orden de palabras, las abreviaturas y los nombres parciales, donde Levenshtein penaliza de más | Nombres cortos o casi iguales de entidades distintas («Juan Pérez» / «Juana Pérez») pueden sugerirse. No es grave: nunca se fusiona sin una persona, y descartar el par lo retira para siempre |
| **Mecanismo de ejecución periódica** | Celery + Redis (beat); cron del sistema; APScheduler dentro del servidor web; **el trabajador en segundo plano que ya existe** | **El trabajador existente**, con la hora de la última búsqueda guardada en `parametros` | En este proyecto Celery y Redis no están instalados. Traerlos suma dos servicios y ~150 MB de memoria a un servidor de 2 GB solo para una tarea diaria de segundos. El cron del sistema vive fuera de Docker y se pierde al reinstalar. APScheduler en el servidor web se duplicaría con varios procesos. El trabajador ya corre siempre, es uno solo y ya maneja la base de datos | Si el trabajador está detenido, no se buscan candidatos. Se mitiga con el botón «Buscar candidatos ahora», y con que la ingesta tampoco funciona en ese caso, así que se nota enseguida. Si algún día hay varias tareas periódicas, conviene reevaluar Celery |
| Cómo se representa la fusión | Borrar la absorbida; copiar sus datos en la definitiva; **marcarla y enlazarla** | **`estado = fusionada` + `fusionada_en_id`** en la absorbida, y **`destino_original_id`** en cada relación movida | Cumple la no destructividad y deja rastro en los dos sentidos: desde la entidad (qué absorbió) y desde el documento (a quién citaba) | Las consultas deben filtrar por `estado = activa`. Se hace en un solo lugar (el servicio) y hay prueba |
| Cuál queda como definitiva por defecto | La más antigua; la de nombre más largo; **la de más conexiones** | **La de más conexiones**, siempre modificable antes de aprobar | Es la forma más usada, y mover menos relaciones es menos riesgo | Puede no ser la forma normalizada correcta. Por eso el selector es explícito |
| Criterio de «pocas conexiones» | Umbral fijo; relativo al fondo; **configurable, 10 por defecto** | **Configurable por el administrador** | Una entidad con muchos documentos ya fue validada muchas veces; si está duplicada, lo mejor es la fusión manual consciente. Así la cola de sugerencias se centra en lo dudoso | Un duplicado entre dos entidades muy conectadas no se sugiere solo. Queda la fusión manual |
| Deshacer una fusión | Botón «deshacer»; **no ofrecerlo en esta versión** | **No se ofrece** | `destino_original_id` guarda lo necesario para revertir, pero reversar con fusiones encadenadas o descripciones corregidas después necesita reglas que el prompt no define | Una fusión equivocada se corrige hoy editando las descripciones afectadas. Queda como mejora, con los datos ya preservados |

## 20. Código (dónde vive, cómo se organiza)

```
alembic/versions/0005_vocabularios.py   sugerencias_fusion y relaciones.destino_original_id
app/models/descripcion.py               SugerenciaFusion; Relacion.destino_original_id
app/servicios/vocabulario.py            verificar, crear, conexiones_de, documentos_conectados,
                                        fusionar, detectar_candidatos, deteccion_periodica
app/servicios/parametros.py             criterios de detección con su validación
app/servicios/descripcion.py            detalle(): antes_de_fusion
app/trabajador.py                       llama a deteccion_periodica en cada ciclo
app/routers/vocabulario.py              /api/vocabulario
frontend/src/pages/Vocabularios.tsx     pestañas Vocabulario y Sugerencias; criterios
frontend/src/pages/EntidadVocabulario.tsx   detalle y fusión manual
frontend/src/lib/vocabulario.ts         tipos y nombres
tests/test_vocabularios.py
```

## 21. Pruebas

10 pruebas en `tests/test_vocabularios.py`, contra PostgreSQL real con `pg_trgm` (111 en total en el proyecto, todas pasan).

- **Verificación:** encuentra «Alcaldía de Tunja» ↔ «Alcaldía Municipal de Tunja». No confunde «Concejo Municipal de Sogamoso» ni «Ministerio de Hacienda». No mezcla tipos.
- **Detección:**
  - sugiere solo el par parecido y poco conectado;
  - no sugiere un par parecido si una de las dos tiene muchos documentos, ni dos entidades distintas;
  - no repite el par en una segunda pasada.
- **Periodicidad:** no vuelve a buscar antes del intervalo configurado; sí después.
- **Aprobar:**
  - redirige todas las relaciones;
  - marca la absorbida como fusionada con enlace a la definitiva;
  - guarda `destino_original_id`;
  - la auditoría tiene quién, las dos entidades y cuántas relaciones se movieron;
  - una segunda aprobación de la misma sugerencia responde 409 y no deja un segundo evento.
- **Descartar:** no cambia ninguna entidad ni relación, y el par no se vuelve a sugerir.
- **Fusión manual:**
  - mismo resultado que la sugerida;
  - la forma documental se redirige;
  - fusionar un agente con un lugar responde 409.
- **Fusionada:**
  - fuera del listado por defecto;
  - visible con el filtro;
  - accesible por su id, con los documentos que la citaban;
  - desde la descripción del documento antiguo se llega a ella (`antes_de_fusion`);
  - no se borra;
  - verificar ya no la ofrece.
- **Listado:** filtro por tipo, búsqueda sin tildes, orden por conexiones y por nombre.
- **Permisos y auditoría:**
  - sin sesión 401; roles consulta y revisor 403 en aprobar, descartar y fusionar;
  - **cada fusión deja exactamente un evento de auditoría** (Definición de Terminado §10).
- **Criterios:** solo el administrador los cambia; valores fuera de rango, 422.

**Verificación visual** en navegador real:

- vocabulario con chips;
- búsqueda;
- sugerencias con similitud al centro;
- aprobar y descartar;
- detalle con historial;
- fusión manual con selector;
- entidad fusionada;
- rastro desde el documento;
- móvil a 390 px sin desplazamiento horizontal;
- sin errores de JavaScript.

## 22. Criterios de aceptación

| Criterio (prompt §9–10) | Cumple |
|---|---|
| Verificación detecta coincidencias razonables sin falsos positivos claros | ✓ |
| La detección sugiere solo con similitud alta y baja conexión de ambas | ✓ |
| Aprobar redirige todo, marca fusionada y audita con detalle completo | ✓ |
| Descartar no modifica nada | ✓ |
| La fusión manual da el mismo resultado que la sugerida | ✓ |
| La fusionada no sale por defecto, pero es accesible por id y desde el documento que la citó | ✓ |
| Ningún endpoint fusiona sin el rol requerido | ✓ |
| Ninguna fusión sin su registro de auditoría (prueba explícita) | ✓ |
| Las dos decisiones técnicas documentadas con tabla completa | ✓ (§19) |
| Nunca fusiona sola, ni con 100 % de similitud | ✓ (no existe código que fusione fuera de aprobar/fusionar) |
| No borra físicamente ninguna entidad | ✓ |

**Pendiente honesto:**

- El umbral de 60 % se eligió con ejemplos de prueba, no con el fondo real. Conviene revisarlo después de describir un lote real: si llegan demasiadas sugerencias falsas, subirlo; si se escapan duplicados, bajarlo.
- ~~El enlace «a su descripción en el catálogo» lleva hoy a la descripción interna.~~ Resuelto en el módulo 4: ahora abre la ficha del catálogo.

## 23. Evidencia concreta de aplicación de RiC

**Antes de la fusión**, dos nodos Agent para el mismo productor:

```
Record «Oficio 114 de 1948» ─ rico:hasCreator → Agent/CorporateBody «Alcaldía Municipal de Tunja»
Record «Oficio 115 de 1948» ─ rico:hasCreator → Agent/CorporateBody «Alcaldía Municipal de Tunja»
Record «Acta del concejo…»  ─ rico:hasCreator → Agent/CorporateBody «Alcaldía Municipal de Tunja»
Record «Oficio 201 de 1949» ─ rico:hasCreator → Agent/CorporateBody «Alcaldia Mpal. de Tunja»
```

Sugerencia detectada: similitud 70 %, 3 y 1 conexiones. La archivista aprueba con «Alcaldía Municipal de Tunja» como definitiva.

**Después:**

```
Record «Oficio 201 de 1949» ─ rico:hasCreator → Agent «Alcaldía Municipal de Tunja»
                              (destino_original_id → «Alcaldia Mpal. de Tunja»)
Agent «Alcaldia Mpal. de Tunja»  estado = fusionada, fusionada_en → «Alcaldía Municipal de Tunja»
Auditoría: fusion_vocabulario · Marlín Martínez · 1 relación redirigida · desde una sugerencia
```

El productor queda como **un solo punto de acceso con 4 documentos**, que es lo que exige ISAAR(CPF). La forma variante no se pierde: sigue consultable y trazable desde el documento que la usaba.
