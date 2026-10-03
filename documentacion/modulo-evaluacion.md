# Módulo de evaluación ciega (objetivo 3 de la tesis)

**Versión:** 1.
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

Ninguna se crea ni se modifica. Lo que se anota y lo que el motor propone usa los tipos de la descripción:
- agente con rol, que es la base de RiC-R027/R031/R032/R039i;
- lugar, fecha (EDTF), actividad, tipo de actividad, mandato y forma documental.

Las anotaciones son datos de investigación, no descripción del fondo: **no entran al vocabulario ni al grafo.**

## 7. Relaciones RiC involucradas

Solo indirectamente: el rol del agente define con qué se empareja (un productor no se compara con un destinatario), igual que define `hasCreator` y `hasAddressee` al publicar.

## 8. Funcionalidades

- Evaluaciones por fondo, con estado (preparación, en curso, cerrada), protocolo y umbral.
- Documentos: solo los listos y sin describir. Si un documento se describe en el sistema durante la evaluación, el resultado lo marca.
- Propuestas generadas como en Descripción (mismo motor, misma instrucción, con su versión), congeladas y ocultas.
- Anotación ciega, con borrador y envío. Al enviarla se mide el tiempo desde que se abrió.
- Anotación asistida: empieza con la propuesta puesta.
- Rúbrica de tres criterios, de 1 a 5.
- **Reglas de ceguera, exigidas por el servidor:**
  - quien vio la propuesta de un documento (asistida, rúbrica o resultados) no puede describirlo a ciegas;
  - tampoco quien lo abrió en Descripción;
  - con una descripción ciega abierta, no se puede ver la propuesta.
- Resultados:
  - precisión, exhaustividad y F1 por tipo, estricta y flexible, micro y macro;
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
| `POST` | administrador | Crear |
| `POST /{id}/documentos` | administrador | Agregar documentos sin describir (422 si alguno ya está descrito) |
| `POST /{id}/propuestas` | administrador | Generar las propuestas; solo devuelve cuántas |
| `POST /{id}/estado` | administrador | Iniciar (exige todas las propuestas) o cerrar |
| `GET /{id}/tareas` | anota | Sus documentos y lo que ya hizo |
| `POST /{id}/documentos/{doc}/anotar` | anota | Empezar o retomar, ciega o asistida (409 si la ceguera ya no es posible) |
| `PUT /anotaciones/{a}` | la autora de la anotación | Guardar o enviar |
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

Hoja de cálculo (.xlsx) con tres hojas: entidades (estricta y flexible), acuerdo, tiempos y rúbrica, y una hoja por documento. Sirve para el análisis estadístico en otra herramienta.

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
| Emparejamiento | Por conjunto (sin unicidad); **uno a uno, del más parecido al menos, por tipo y rol** | **Uno a uno** | Evita contar dos veces la misma entidad. Comparar por rol respeta que «productor» y «destinatario» son relaciones RiC distintas | El orden voraz no es el óptimo global (algoritmo húngaro). Con pocas entidades por tipo, la diferencia es despreciable |
| Igualdad de valores | Solo exacta; solo por similitud; **las dos** | **Estricta** (normalizada: tildes, mayúsculas, signos; fechas por EDTF) **y flexible** (SequenceMatcher ≥ umbral de la evaluación, 0,85 por defecto) | La estricta es reproducible e indiscutible; la flexible reconoce variantes («Concejo Municipal» y «Concejo Municipal de Tunja»). Se reportan las dos para que el jurado vea la diferencia | El umbral es una elección: se fija por evaluación, antes de empezar, y se informa. Lo ideal es que la autora lo justifique con una muestra |
| Acuerdo entre archivistas | Kappa de Cohen; **F1 entre pares** | **F1** | En extracción de entidades no hay «negativos» (todo lo no anotado), así que el kappa no está definido; F1 converge al kappa cuando los negativos son muchos (Hripcsak y Rothschild, 2005) | Menos conocido para un jurado de archivística: se explica en la pantalla y en la tesis |
| Rúbrica | Sin rúbrica; escala 1–3; **1–5 en tres criterios, kappa ponderado cuadrático** | Así | Mide lo que las métricas no ven (pertinencia del contexto). El kappa ponderado respeta que 4 frente a 5 es menos desacuerdo que 1 frente a 5 | Los criterios son una propuesta: la autora debe validarlos o cambiarlos |
| Tiempos | Cronómetro manual; **servidor, de abrir a enviar** | **Servidor** | Sin intervención y comparable entre condiciones | Incluye pausas. Se reporta la mediana, robusta a una pausa larga |

## 20. Código

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
