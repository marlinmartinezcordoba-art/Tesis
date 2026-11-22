# Módulo de evaluación del rendimiento con la medida F1 (objetivo 3 de la tesis)

**Versión:** 3 (reemplaza la evaluación ciega; la versión 2 queda en `modulo-evaluacion-ciega-retirado.md`).
**Estado:** entregado; los umbrales los aprueba la tutoría con juicio de expertos.

## 1. Propósito

Medir el rendimiento del motor de análisis en la extracción de entidades y relaciones de RiC-CM con la medida F1 y sus componentes, precisión y exhaustividad, frente a la descripción que la archivista valida en el propio sistema. Es la evidencia del objetivo 3: «Evaluar con la medida F1 el rendimiento del prototipo en la extracción de entidades y relaciones de RiC-CM, frente a la descripción validada por la archivista en el propio sistema».

## 2. Por qué se retiró la evaluación ciega

La metodología de la tesis pasó a ser descriptiva evaluativa y no exige describir a ciegas: no hay archivistas externas disponibles para una referencia independiente. La referencia es la validación que la archivista ya hace en Descripción. Las tablas del protocolo ciego (anotaciones, exposiciones, calificaciones, participantes) se conservan con sus datos, pero ningún servicio las usa.

## 3. Cómo se cuenta

Al publicar una descripción, `servicios/descripcion.registrar_decisiones` deja en la auditoría un evento `decision_ia` por cada propuesta del motor y por cada dato que la archivista agregó.

| Decisión | Cuenta como |
|---|---|
| aceptada | verdadero positivo (VP) |
| rechazada | falso positivo (FP), dato inventado |
| agregada | falso negativo (FN), dato omitido |
| corregida | FP y FN a la vez |

Precisión = VP / (VP + FP). Exhaustividad = VP / (VP + FN). F1 = 2VP / (2VP + FP + FN).

- El título, el alcance y contenido y el idioma son textos libres: se informan por tipo y no entran en la F1 global ni en la macro.
- Solo cuenta la primera publicación de cada documento (las ediciones posteriores no cambian la medida).
- Solo cuentan las decisiones tomadas con la versión de la instrucción congelada al iniciar.
- Intervalos de confianza del 95 % por remuestreo de documentos, 1 000 repeticiones, semilla fija.
- Un criterio se cumple cuando el límite inferior del intervalo alcanza el umbral. La hipótesis se sostiene si se cumplen los tres.

## 4. Flujo

1. **Crear** la evaluación (administración).
2. **Agregar** los documentos del caso, listos y aún sin describir. Se excluyen los reservados (Ley 1712 de 2014).
3. **Sortear** con una semilla los conjuntos de desarrollo y prueba, estratificado por el año del nombre del archivo. Con la misma semilla, el mismo resultado.
4. **Fijar los umbrales**: F1 0,80, precisión 0,85, exhaustividad 0,80 y acuerdo 0,80 por defecto.
5. **Ajustar** la instrucción del motor con los documentos de desarrollo (en Descripción).
6. **Iniciar**: se congelan los umbrales y la versión del sistema (`RICORA_VERSION`), del motor, de la instrucción y del perfil SHACL.
7. **Validar** los documentos de prueba en Descripción, una sola vez.
8. **Validación de control**: una persona distinta de la que validó decide sobre las propuestas originales de algunos documentos de prueba, sin ver la primera decisión. El acuerdo es el porcentaje de decisiones iguales.
9. **Causas de error**: lectura del texto, ambigüedad del documento, regla mal aplicada o invención del motor.
10. **Resultados** y descarga en Excel. La hoja «Decisiones» tiene los encabezados de la exportación de Auditoría, de modo que `evaluar_ricora.py --importar` la pasa al Anexo D.
11. **Cerrar**.

## 5. Rutas

| Método | Ruta | Quién |
|---|---|---|
| GET, POST | `/api/evaluacion` | listar (validadoras: en curso) · crear (administración) |
| GET | `/api/evaluacion/{id}` | ver |
| GET, POST | `/api/evaluacion/{id}/documentos` | listar · agregar |
| DELETE | `/api/evaluacion/{id}/documentos/{inst}` | quitar antes del sorteo |
| POST | `/api/evaluacion/{id}/sorteo` | sortear |
| PUT | `/api/evaluacion/{id}/criterio` | umbrales |
| POST | `/api/evaluacion/{id}/estado` | iniciar o cerrar |
| GET | `/api/evaluacion/{id}/resultados` y `/resultados/hoja-de-calculo` | administración |
| GET, PUT | `/api/evaluacion/{id}/control/{inst}` y `/control/decisiones/{evento}` | segunda validadora |
| GET, PUT | `/api/evaluacion/{id}/errores` y `/errores/{evento}` | validadoras |

## 6. Datos

- `evaluaciones`: se agregan `semilla` y `sorteada_en` (migración 0065).
- `evaluacion_documentos`: se agrega `conjunto` (desarrollo o prueba).
- `evaluacion_control`: decisiones de la segunda validadora.
- `evaluacion_errores` (ClasificacionError): la causa de cada error, con clave = identificador del evento de auditoría.

## 7. Pruebas

`tests/test_evaluacion.py`: conteo y medidas calculadas a mano, exclusión de textos libres, intervalo reproducible, dictamen por límite inferior, sorteo reproducible, reglas de preparación y congelamiento, flujo completo con F1 esperada, causas de error, validación de control con acuerdo, exclusión de otra versión y de reediciones.

## 8. Pendiente

- Los documentos citados que propone el motor todavía no se publican como relación ni generan decisión; cuando se publiquen, entrarán solos en la medida.
- La versión del sistema depende de que el despliegue fije `RICORA_VERSION` (por ejemplo, con la etiqueta `v1.0.0`).
