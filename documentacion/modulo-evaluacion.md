# Módulo de evaluación ciega (objetivo 3 de la tesis)

**Versión:** 2 (descripción y evaluación en RiC: entidades, relaciones RiC-O y conformidad; cambios en §24).
**Estado:** entregado, pendiente de validación metodológica por la autora.

**Origen:** ningún prompt de la autora define este módulo. Nace de la auditoría de brechas del sistema: el objetivo 3 de la tesis («evaluación frente a archivistas») no tenía cómo medirse dentro del sistema. El panel de decisiones de IA mide la **aceptación** de la archivista, que ve la propuesta antes de decidir. Eso no es una evaluación ciega. Las decisiones metodológicas de §19 son propuestas y la autora debe validarlas.

---

## 1. Propósito

Medir la calidad del motor de análisis frente a archivistas, con un procedimiento que se pueda repetir y defender:
- **a ciegas:** el documento se describe sin ver nunca la propuesta; es el patrón de referencia;
- **asistida:** con la propuesta delante; mide el tiempo y la corrección;
- **rúbrica:** se califica la propuesta de 1 a 5 en exactitud, completitud y pertinencia.

## 2. Auditoría (qué se revisó antes de construirlo)

- El panel de decisiones de IA (auditoría v7) **no sirve como evaluación**: la archivista ve la propuesta antes de decidir (sesgo de anclaje), y lo que el motor no propuso solo aparece si ella lo agrega.
- El motor recibe el vocabulario del fondo como contexto (descripción v3). **Si se evalúa sobre documentos ya descritos, sus entidades ya están en el vocabulario** y el motor «acierta» por contexto. Ese riesgo de contaminación no estaba controlado en ninguna parte.
- Los registros de auditoría permiten saber si una persona abrió un documento en Descripción (donde vio la propuesta).

## 3. Problema que resuelve

Sin una referencia independiente, afirmar que «el motor acierta» es circular. El módulo produce esa referencia, la protege del sesgo y calcula las métricas estándar de extracción de información.

## 4. Usuarios

- **Administración:**
  - crea la evaluación y elige los documentos;
  - genera las propuestas, la inicia y la cierra;
  - ve los resultados;
  - anula una anotación.
- **Archivistas** (permiso de escribir en Descripción): describen a ciegas y asistidas, y califican.
- **Revisor y consulta:** no entran (403).

## 5. Casos de uso

1. La administradora crea «Piloto», con su protocolo y su umbral de similitud.
2. Agrega documentos **aún no descritos** del fondo.
3. Genera las propuestas del motor, que **no se muestran a nadie**.
4. Inicia la evaluación.
5. Cada archivista hace cada documento en orden: a ciegas, luego asistida, luego calificar.
6. Al cerrar, la administradora ve precisión, exhaustividad y F1 por tipo, acuerdo entre archivistas, tiempos y rúbrica, y descarga la hoja de cálculo.

## 6. Entidades RiC involucradas

Ninguna se crea ni se modifica en el fondo. Desde la versión 2, lo que se anota y lo que el motor propone son **entidades con su clase de RiC-O**:
- el documento que se describe (rico:Record);
- agente con su clase (Person, CorporateBody, Position, Group, Family, Mechanism; o Agent si no se precisa);
- lugar (Place), fecha (Date, con EDTF), actividad (Activity), tipo de actividad (ActivityType), mandato (Mandate) y forma documental (DocumentaryFormType).

Las anotaciones son datos de investigación, no descripción del fondo: **no entran al vocabulario ni al grafo.**

## 7. Relaciones RiC involucradas

Desde la versión 2, **directamente**. La archivista une el documento y las entidades (o las entidades entre sí) con una de 28 propiedades de RiC-O del mapeo verificado (`evaluacion_ric.PROPIEDADES`). Entre ellas:
- hasCreator R027, hasAuthor R079, hasSender R031, hasAddressee R032, hasOrHadHolder R039i;
- hasOrHadSubject R019, isCreationDateOf R080, isOrWasLocationOf R075, documents R033;
- hasActivityType, performsOrPerformed R060i, regulatesOrRegulated R063, authorizes R067;
- relaciones entre agentes (R045, R054, R055…) y hasDocumentaryFormType.

Cada una se muestra con su nombre archivístico, su etiqueta oficial en español y su código RiC-CM (por ejemplo: «Destinatario — se dirige a (rico:hasAddressee · RiC-R032)»). La propuesta del motor se convierte a las mismas relaciones que crearía la publicación (`descripcion.RELACION_POR_ROL` y la cadena de la actividad).

## 8. Funcionalidades

- Evaluaciones por fondo, con estado (preparación, en curso, cerrada), protocolo y umbral.
- Documentos: solo los listos y sin describir. Si un documento se describe en el sistema durante la evaluación, el resultado lo marca.
- Propuestas generadas como en Descripción (mismo motor, misma instrucción, con su versión), congeladas y ocultas.
- Anotación ciega, con borrador y envío. Al enviarla se mide el tiempo desde que se abrió.
- Anotación asistida: empieza con la propuesta puesta.
- Rúbrica de tres criterios, de 1 a 5.
- **Descripción en RiC (v2):**
  - entidades y relaciones RiC-O, como se describe arriba;
  - la pantalla solo ofrece las relaciones que RiC-O admite entre los dos extremos elegidos;
  - el borrador se guarda y muestra su conformidad;
  - una descripción que no es RiC válida no se envía.
- **Conformidad RiC-O 1.1 (v2):** de cada descripción, la del motor, la ciega y la asistida. Se revisa contra:
  - el mapeo verificado: clase del origen y del destino;
  - el perfil: un título, a lo sumo una forma documental, a lo sumo un tipo por actividad, ninguna entidad suelta;
  - el OWL oficial: dominio y rango.
- **Reglas de ceguera, exigidas por el servidor:**
  - quien vio la propuesta de un documento (asistida, rúbrica o resultados) no puede describirlo a ciegas;
  - tampoco quien lo abrió en Descripción;
  - con una descripción ciega abierta, no se puede ver la propuesta.
- Resultados:
  - precisión, exhaustividad y F1 por tipo, estricta y flexible, micro y macro;
  - lo mismo para las **relaciones**, por propiedad de RiC-O, con el acuerdo entre archivistas en relaciones;
  - **confusión de propiedades**: los mismos extremos con otra relación (el motor dijo destinatario y la archivista, productor);
  - **conformidad RiC-O** por origen (motor, ciega, asistida) y los problemas más frecuentes;
  - acuerdo entre archivistas (F1);
  - tiempos (mediana y media);
  - rúbrica (media y kappa ponderado);
  - resultados por documento;
  - hoja de cálculo.

## 9. Flujos

```
preparación ── agregar documentos (sin describir) ── generar propuestas (ocultas) ── iniciar
en curso ───── por documento y persona: a ciegas ─▶ asistida ─▶ ver propuesta y calificar
                (no se puede volver a ciegas después de ver la propuesta)
cerrada ────── resultados (quien los ve queda expuesto: ya no describe a ciegas)
```

## 10. Pantallas

**Evaluación** (barra lateral, grupo Sistema):
- lista de evaluaciones y formulario «Nueva evaluación» (administración);
- detalle: tarjeta de administración (documentos, generar, iniciar, cerrar, resultados) y «Mis tareas» con los tres botones por documento;
- formulario de anotación: documento y descripción lado a lado; en pantalla angosta, uno debajo del otro;
- rúbrica, con confirmación previa: «después, ya no podrá describirlo a ciegas»;
- resultados.

## 11. UX/UI

- El botón «A ciegas» se apaga, con su razón, cuando ya no es posible.
- La rúbrica pide confirmar antes de mostrar la propuesta.
- Las cifras usan el formato colombiano (coma decimal).
- La nota de método está al pie de los resultados.
- Verificado a 390 px sin desplazamiento horizontal.

## 12. Modelo de datos (migración 0015)

- `evaluaciones`: fondo, nombre, protocolo, umbral (0,5 a 1, con restricción), estado y fechas.
- `evaluacion_documentos`: la propuesta congelada (JSONB), con el motor y la versión de la instrucción.
- `evaluacion_anotaciones`: única por evaluación, documento, persona y condición. Tiene estado (en curso, enviada, **anulada**: nada se borra), datos (JSONB), inicio y envío.
- `evaluacion_exposiciones`: cada vez que alguien vio una propuesta y por qué. Es la base de la regla de ceguera.
- `evaluacion_calificaciones`: puntaje de 1 a 5 (con restricción). Si se cambia, el anterior queda en la auditoría.

## 13. API (`/api/evaluacion`)

| Método y ruta | Permiso | Qué hace |
|---|---|---|
| `GET ?fondo_id` | anota o administra | Lista (quien anota ve solo las en curso) |
| `GET /propiedades` | anota o administra | Las 28 relaciones de RiC-O disponibles, con los extremos que admite cada una (v2) |
| `POST` | administrador | Crear |
| `POST /{id}/documentos` | administrador | Agregar documentos sin describir (422 si alguno ya está descrito) |
| `POST /{id}/propuestas` | administrador | Generar las propuestas; solo devuelve cuántas |
| `POST /{id}/estado` | administrador | Iniciar (exige todas las propuestas) o cerrar |
| `GET /{id}/tareas` | anota | Sus documentos y lo que ya hizo |
| `POST /{id}/documentos/{doc}/anotar` | anota | Empezar o retomar, ciega o asistida (409 si la ceguera ya no es posible) |
| `PUT /anotaciones/{a}` | la autora de la anotación | Guardar o enviar. v2: `relaciones` con `{origen, propiedad, destino}`; responde con la conformidad; enviar exige conformidad (422 con los problemas). Sin `relaciones`, acepta el formato anterior con roles y lo convierte |
| `POST /{id}/documentos/{doc}/propuesta` | anota | Ver la propuesta para calificar (queda la exposición) |
| `PUT /{id}/documentos/{doc}/calificacion` | anota | Rúbrica (exige haberla visto) |
| `POST /anotaciones/{a}/anular` | administrador | Anular, sin borrar |
| `GET /{id}/resultados[/hoja-de-calculo]` | administrador | Métricas |

## 14. Uso de IA

Se usa el mismo motor y la misma instrucción de Descripción, con el contexto de vocabulario, para evaluar el sistema tal como funciona. La versión de la instrucción y el motor quedan en cada documento y en los resultados.

## 15. Seguridad

- Permisos por rol: el revisor y la consulta no entran; solo la administración ve propuestas agregadas y resultados.
- Una anotación solo la edita quien la hizo.
- Las propuestas nunca salen en la creación ni en la generación.
- **Las reglas de ceguera están en el servidor, no en la pantalla.**
- Las anotaciones no entran al catálogo, ni a la exportación RDF, ni al vocabulario.

## 16. Auditoría (qué queda registrado)

Todo, en el módulo `evaluacion`, con nombre legible:
- creación, documentos agregados, propuestas generadas, inicio y cierre;
- anotación iniciada, enviada (con entidades y segundos) y anulada;
- propuesta vista (con su motivo), calificación y resultados consultados.

## 17. Interoperabilidad

Hoja de cálculo (.xlsx) con cinco hojas:
- entidades (estricta y flexible);
- relaciones RiC, por propiedad, con la confusión de propiedades (v2);
- conformidad RiC-O, por origen y por problema (v2);
- acuerdo, tiempos y rúbrica;
- documentos. Sirve para el análisis estadístico en otra herramienta.

## 18. Normativa y referencias de método

- Precisión, exhaustividad y F1: medidas estándar de extracción de información (conferencias MUC).
- Acuerdo entre anotadores con F1 cuando no hay negativos: Hripcsak y Rothschild (2005), *Agreement, the F-measure, and reliability in information retrieval*, JAMIA 12(3).
- Kappa de Cohen ponderado (Cohen, 1968) para la rúbrica ordinal.
- Diseño ciego frente a asistido para medir el sesgo de anclaje en la validación humana de propuestas automáticas.

## 19. Arquitectura y decisiones

`app/servicios/evaluacion.py` (las métricas son funciones puras, probadas con valores calculados a mano), `app/routers/evaluacion.py`, `app/models/evaluacion.py` y `frontend/src/pages/Evaluacion.tsx`.

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Patrón de referencia | Lo publicado en Descripción; una descripción experta única adjudicada; **cada descripción ciega como referencia** | **Cada ciega es una referencia** (las métricas suman sobre todas) | Lo publicado está sesgado por la propuesta. Una adjudicación exige una tercera persona y un procedimiento que la autora debe definir. Cada referencia ciega es independiente y el acuerdo entre ellas dice cuánto «techo» hay | Si dos archivistas difieren mucho, el motor se mide contra referencias inconsistentes. Por eso se reporta el acuerdo junto a las métricas. Si la autora prefiere una referencia adjudicada, se agrega sin cambiar lo demás |
| Cómo se garantiza la ceguera | Confiar en la instrucción a la persona; ocultarlo en la pantalla; **registrar cada exposición y negarlo en el servidor** | **Servidor** (exposiciones + trabajos en Descripción) | Una regla que solo vive en la pantalla no es evidencia. Con el registro, la tesis puede afirmar que ninguna referencia ciega vio la propuesta | No detecta que alguien vea la propuesta en la pantalla de otra persona. Eso queda en el protocolo |
| Documentos admitidos | Cualquiera; **solo sin describir** | **Solo sin describir** | El motor recibe el vocabulario del fondo como contexto: con un documento ya descrito, sus entidades estarían en el contexto (fuga de la respuesta) | Exige reservar documentos para la evaluación. Si alguien los describe durante la evaluación, el resultado lo marca |
| Emparejamiento | Por conjunto (sin unicidad); **uno a uno, del más parecido al menos** | **Uno a uno**. v1 comparaba por tipo y rol; **v2 compara las entidades solo por tipo**, y el rol se mide como relación (§24) | Evita contar dos veces la misma entidad. En RiC el papel de un agente no es de la entidad sino de su relación con el documento | El orden voraz no es el óptimo global (algoritmo húngaro). Con pocas entidades por tipo, la diferencia es despreciable |
| Igualdad de valores | Solo exacta; solo por similitud; **las dos** | **Estricta** (normalizada: tildes, mayúsculas, signos; fechas por EDTF) **y flexible** (SequenceMatcher ≥ umbral de la evaluación, 0,85 por defecto) | La estricta es reproducible e indiscutible; la flexible reconoce variantes («Concejo Municipal» y «Concejo Municipal de Tunja»). Se reportan las dos para que el jurado vea la diferencia | El umbral es una elección: se fija por evaluación, antes de empezar, y se informa. Lo ideal es que la autora lo justifique con una muestra |
| Acuerdo entre archivistas | Kappa de Cohen; **F1 entre pares** | **F1** | En extracción de entidades no hay «negativos» (todo lo no anotado), así que el kappa no está definido; F1 converge al kappa cuando los negativos son muchos (Hripcsak y Rothschild, 2005) | Menos conocido para un jurado de archivística: se explica en la pantalla y en la tesis |
| Rúbrica | Sin rúbrica; escala 1–3; **1–5 en tres criterios, kappa ponderado cuadrático** | Así | Mide lo que las métricas no ven (pertinencia del contexto). El kappa ponderado respeta que 4 frente a 5 es menos desacuerdo que 1 frente a 5 | Los criterios son una propuesta: la autora debe validarlos o cambiarlos |
| Tiempos | Cronómetro manual; **servidor, de abrir a enviar** | **Servidor** | Sin intervención y comparable entre condiciones | Incluye pausas. Se reporta la mediana, robusta a una pausa larga |

## 20. Código

v2 agrega `app/servicios/evaluacion_ric.py` (conversión, conformidad y comparación de relaciones) y `tests/test_evaluacion_ric.py` (10 pruebas). No hay migración: las anotaciones ya se guardaban en JSONB.

```
alembic/versions/0015_evaluacion_ciega.py
app/models/evaluacion.py
app/servicios/evaluacion.py          métricas (puras) y flujo con las reglas de ceguera
app/routers/evaluacion.py
frontend/src/pages/Evaluacion.tsx
tests/test_evaluacion.py             7 pruebas
```

## 21. Pruebas (7; el proyecto llega a 282)

| Prueba | Qué comprueba |
|---|---|
| Emparejamiento uno a uno | Ni una referencia ni una entidad del sistema cuentan dos veces; el rol separa; la fecha se compara por EDTF |
| Precisión, exhaustividad y F1 a mano | Estricta: 3 VP, 2 FP, 2 FN → 0,6 / 0,6 / 0,6. Flexible (0,75): 4/1/1 → F1 0,8 |
| Kappa ponderado a mano | Acuerdo perfecto: 1. Igual al azar: 0. Desacuerdos de un punto: 0,8 exacto (cálculo en el comentario) |
| Ciclo completo | Dos archivistas a ciegas y una asistida, rúbrica, tiempos. Estricto acumulado 6/4/2 → P 0,6, E 0,75; acuerdo F1 0,75; medias de rúbrica; motor y versión; hoja de cálculo; los eventos de auditoría |
| Ceguera | Tras la asistida, después de abrirlo en Descripción y después de ver los resultados, a ciegas da 409 con su razón |
| Documentos y permisos | Un documento ya descrito se rechaza (contaminaría); la archivista no crea; el revisor no entra; la archivista solo ve las en curso |
| Anotaciones | Una ajena no se edita; un agente sin rol se rechaza; anular es solo de la administración y no borra |

**Mutaciones** detectadas:
- quitar la regla de ceguera;
- admitir documentos descritos;
- romper el emparejamiento uno a uno (no se detectaba; se agregó el caso que faltaba).

**Recorrido real en navegador:** crear, agregar, generar, iniciar, ciega, asistida, calificar y resultados, con las cifras correctas, en escritorio y a 390 px, sin errores.

## 22. Criterios de aceptación

| Criterio | Cumple |
|---|---|
| La referencia ciega no puede haber visto la propuesta (exigido por el servidor y probado) | ✓ |
| No se evalúa sobre documentos ya descritos | ✓ |
| P, E y F1 por tipo, estrictas y flexibles, verificadas a mano | ✓ |
| Acuerdo entre archivistas y kappa de la rúbrica | ✓ |
| Tiempos por condición | ✓ |
| Todo en la auditoría; nada se borra | ✓ |
| **Validación del método por la autora** (umbral, criterios de la rúbrica, referencia por persona o adjudicada) | Pendiente |
| **Aplicación real con archivistas sobre el fondo de prueba** | Pendiente: es trabajo de campo de la tesis, no de software |

## 23. Evidencia

En desarrollo, sobre el oficio 301 de 1949, con un motor de prueba:
- **El motor propuso:** productor «Alcaldía Municipal de Tunja», destinatario «Concejo Municipal» y lugar «Tunja».
- **A ciegas se registró:** solo el productor.
- **Resultado:** P = 0,33, E = 1, F1 = 0,5, en estricta y en flexible. Rúbrica 4/4/4. Kappa no calculable, porque hay una sola calificadora (la pantalla lo muestra como «—», sin inventarlo).

La evidencia de la tesis será la misma pantalla con el motor real y las archivistas reales. Los números de este ejemplo **no** son resultados de la investigación.

## 24. Versión 2: la descripción y la evaluación en RiC

**Por qué.** El título y la pregunta de la tesis piden comparar descripciones basadas en RiC-CM. El resumen promete medir F «por tipo de entidad y de relación». La versión 1 no lo cumplía:
- la archivista anotaba una ficha con entidades sueltas;
- solo se medían entidades;
- nadie revisaba si lo descrito era RiC válido.

**Qué cambió:**
1. La descripción se hace en RiC: entidades con clase y relaciones con propiedad de RiC-O.
2. Se miden las relaciones y la confusión de propiedades.
3. Se revisa la conformidad de cada descripción con RiC-O 1.1.

**Qué no cambió:**
- las reglas de ceguera;
- la rúbrica (sus criterios siguen siendo exactitud, completitud y pertinencia);
- los tiempos;
- la regla de solo documentos sin describir.

Una anotación con el formato anterior se sigue leyendo: se convierte con la regla de la publicación.

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo anota la archivista | Ficha con roles (v1); grafo libre con cualquier propiedad de RiC-O; **entidades + relaciones de una lista cerrada del mapeo verificado** | **Lista cerrada** (28 propiedades) | Son las que el sistema sabe exportar y verificar. Quedan fuera las estructurales (jerarquía, instanciación, secuencia), que no se deducen leyendo un documento. Una propiedad libre no se podría comparar con el motor ni validar | Si una archivista necesita una relación que no está, no puede anotarla. Se agrega al mapeo (con su verificación contra el OWL), no en la evaluación |
| Cómo se convierte la propuesta del motor | Pedirle al motor tripletas; **convertir sus roles con la misma regla de la publicación** | **Misma regla** | Se evalúa el sistema tal como publica, no una salida distinta. Sin cambiar la instrucción del motor, sigue valiendo la versión registrada | El motor no propone relaciones entre agentes (subordinación, cargo). Las que anote la archivista cuentan como no encontradas: es una limitación real del motor y queda medida |
| Cuándo una relación es acierto | Solo la propiedad; **propiedad y los dos extremos** | **Propiedad y extremos** (cada extremo, con la misma igualdad estricta o flexible que las entidades) | «Productor = Alcaldía» es un hecho. «Hay un productor» no lo es | Un extremo con una variante de nombre baja el acierto estricto. Para eso está la flexible |
| Mismos extremos con otra propiedad | Contarlo solo como error; **contarlo además como confusión** | **Confusión aparte** | Dice qué se equivoca el motor (destinatario frente a productor), que es lo que la tesis necesita discutir | Ninguno: no altera P, E ni F1 |
| Conformidad: contra qué | Solo el perfil SHACL de la exportación; **mapeo + perfil + OWL oficial** | **Las tres** | El perfil SHACL exige cosas propias de una exportación (pertenencia a un fondo, identificadores), que una anotación no tiene. El OWL oficial es independiente del mapeo del sistema | Un agente sin clase solo es válido donde cualquier agente lo es (por ejemplo, el autor exige la clase). Se informa con esa razón |
| ¿Se puede enviar una descripción no conforme? | Sí, y se mide; **no: el borrador sí, el envío no** | **No se envía** | La referencia tiene que ser RiC válida; si no, se compararía el motor con algo que RiC-O no admite. La conformidad de las archivistas queda en 100 % por protocolo, y así se reporta | Una archivista podría «forzar» una relación válida pero no pensada. La pantalla muestra el nombre archivístico y la etiqueta oficial para evitarlo |
| Agente sin papel en el formato anterior | Tema (como el motor); **sin relación** | **Sin relación**, en una anotación de una persona | No se le inventa un dato a la referencia humana. El motor sí usa «mencionado» porque así publica | Ninguno |

**Pruebas nuevas (tests/test_evaluacion_ric.py):**
- la conversión del motor;
- un nodo con dos papeles;
- la cadena de la actividad;
- la conformidad: mapeo, OWL, agente sin clase y perfil;
- el catálogo;
- relaciones y confusión calculadas a mano;
- el flujo por la API: 422 por propiedad inexistente, por entidad inexistente y por envío no conforme; formato anterior; resultados y hoja;
- la asistida anulada que se reabre con la propuesta.

**Falla anterior corregida en el camino.** Una anotación asistida anulada se reabría vacía, sin la propuesta del motor. Ahora vuelve con ella.

**Recorrido en navegador** (motor simulado, base de prueba):
- se describió un acta en RiC;
- la entidad suelta «Tunja» impidió el envío, con su razón;
- al relacionarla, quedó conforme;
- la asistida trajo las cuatro relaciones del motor;
- los resultados mostraron entidades, relaciones por propiedad, confusiones y conformidad;
- a 390 px, sin desplazamiento horizontal ni errores.

**Pendiente de la autora:**
- validar que la lista de 28 propiedades es la adecuada para el conjunto documental del caso;
- decidir si la rúbrica agrega un criterio relacional (punto 3, que no se tocó).

## 25. Versión 3: el objetivo 3 convertido en lógica

**Por qué.** La tesis (capítulo III) describe un procedimiento que el sistema no ejecutaba completo: el criterio de comparabilidad se aplicaba a mano, los errores se clasificaban fuera del sistema, no había intervalos ni prueba de los tiempos, y los documentos reservados podían entrar a la evaluación. Ahora el sistema hace lo que la tesis dice.

**Qué se agregó (migración 0054, `app/servicios/evaluacion_analisis.py`):**

1. **Criterio de comparabilidad** por evaluación (`evaluaciones.criterio`): margen de F frente al acuerdo entre archivistas (0,10), mínimo de entidades de referencia por tipo (10), media mínima de la rúbrica (3) y conformidad mínima de las asistidas (100 %). Se fija en preparación (`PUT /api/evaluacion/{id}/criterio`) y se congela al iniciar; el inicio lo registra en la auditoría. Los resultados traen `comparabilidad`: cada tipo de entidad queda **comparable**, **no comparable** (con sus motivos), **datos insuficientes** o **sin techo**.
2. **Acuerdo entre archivistas por tipo**, que es el techo de cada tipo.
3. **Supervisión en la condición asistida:** cada propuesta del motor quedó aceptada (igual), corregida (parecida desde el umbral) o rechazada; lo que añadió la archivista es «agregada».
4. **Desacuerdos:** cada diferencia entre el motor y una referencia ciega (variante, sobrante, faltante, otra relación, relación sobrante o faltante), con una clave estable. Se clasifican con la taxonomía de la tesis (`GET /desacuerdos`, `PUT /desacuerdos/{clave}`), solo con la evaluación cerrada. Cada investigadora clasifica por su cuenta y ve la clasificación de la otra solo después de dar la suya; si difieren, se registra el consenso. Kappa de Cohen entre clasificadoras y distribución final por tipo de error.
5. **Estadística:** intervalo de confianza del 95 % de la F micro (flexible) por remuestreo de documentos, 1000 repeticiones y semilla fija (Efron y Tibshirani, 1993); prueba de rangos con signo de Wilcoxon de los tiempos pareados (misma archivista, mismo documento), con corrección por empates y de continuidad (Wilcoxon, 1945).
6. **Documentos reservados fuera:** un archivo clasificado o reservado no se agrega a la evaluación.
7. **Tiempos por documento** con las evaluadoras anonimizadas («Evaluadora 1, 2…»).
8. **Rúbrica con descriptores** de los cinco niveles en la pantalla de calificación.
9. **Indicador de fragmento no hallado** en el panel de decisiones de IA (capítulo V): cada decisión guarda si el fragmento citado por el motor apareció en el texto.

La hoja de cálculo suma cuatro pestañas: Comparabilidad, Supervisión (asistida), Tiempos por documento y Desacuerdos.

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cuándo se fija el criterio | Al analizar los datos; antes de iniciar | Antes de iniciar, congelado | Un criterio elegido después de ver los datos invalida la respuesta a la pregunta | Un criterio mal pensado no se corrige; se valida con el juicio de expertos antes de iniciar |
| Techo de comparación | Un valor fijo de F; el acuerdo entre archivistas | Acuerdo entre archivistas por tipo | No se le exige al motor más coincidencia que la que tienen dos profesionales | Con una sola archivista no hay techo: el tipo queda «sin techo» y no se decide |
| Unidad del remuestreo | Entidades; documentos | Documentos | Las entidades de un documento no son independientes | Con pocos documentos el intervalo es ancho; así se informa |
| Prueba de los tiempos | t pareada; Wilcoxon | Wilcoxon, aproximación normal | Los tiempos no siguen una distribución normal; con menos de 6 pares no se informa p | La aproximación normal es conservadora con muestras pequeñas |
| Clasificación de errores | Fuera del sistema; en el sistema, independiente y con consenso | En el sistema | La independencia se garantiza en el servidor y el kappa se calcula sobre lo registrado | Las investigadoras ven las propuestas; por eso solo se clasifica con la evaluación cerrada |
| Documentos reservados | Admitirlos; excluirlos | Excluirlos | Su texto iría al motor y lo verían las evaluadoras | Puede reducir la muestra en fondos con mucha reserva |

**Pruebas:** `tests/test_evaluacion_objetivo3.py` (Wilcoxon y kappa calculados a mano, remuestreo reproducible, supervisión, el criterio tipo por tipo, documento reservado rechazado, el flujo completo con clasificación independiente y consenso, el indicador de fragmento no hallado).
