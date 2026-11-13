# Correspondencia entre la tesis y RICORA

Tesis: *Descripción archivística asistida por inteligencia artificial para archivos históricos: prototipo basado en
el modelo Records in Contexts (RiC-CM)*. Maestría en Gestión de la Información Documental, Universidad de La Salle.

Este documento es el lado del software del Anexo A de la tesis: dice, para cada parte de la tesis, qué parte de
RICORA la cumple y qué prueba automática lo demuestra. Si se cambia algo de lo que aquí aparece, hay que revisar
también la sección de la tesis que se cita.

## Objetivos

| Objetivo de la tesis | Lo cumple en RICORA | Prueba automática |
|---|---|---|
| 1. Analizar los fundamentos de RiC-CM y RiC-O | `app/servicios/ric_o.py` (clases y propiedades de RiC-O 1.1 con su código RiC-R), `app/recursos/ric-o/perfil-ricora.shacl.ttl`, `app/servicios/exportacion_rico.py` | `tests/test_exportacion_rico.py` |
| 2. Diseñar la arquitectura con validación del archivista | Ingesta, Descripción, Autoridades y términos, Datos enlazados, Auditoría | Una por requisito (abajo) |
| 3. Comparar las descripciones del prototipo con las de archivistas | `app/servicios/evaluacion.py`, `evaluacion_analisis.py`, `evaluacion_ric.py`, `evaluacion_participantes.py`; pantalla Evaluación | `tests/test_evaluacion_objetivo3.py`, `tests/test_evaluacion.py` |

## Capítulo III, Tabla 3 (dimensiones de la comparación)

| Dimensión | Indicador | Dónde lo calcula RICORA |
|---|---|---|
| 1. Identificación de entidades | P, R y F1 por tipo, estricto y flexible | `evaluacion.resultados` → `estricto`, `flexible` |
| 2. Relaciones en red | P, R y F1 por propiedad RiC-O; confusiones | `resultados` → `relaciones` |
| 3. Normalización y autoridades | Fechas en EDTF, duplicidad de agentes y lugares | `evaluacion_analisis.indicadores` → hoja «Normalización y cobertura» |
| 4. Trazabilidad y evidencia | Entidades del motor con fragmento | `indicadores` → `evidencia_motor` |
| 5. Conformidad y eficiencia | Conformidad RiC-O 1.1, clases y propiedades usadas, tiempos (Wilcoxon) | `resultados` → `conformidad`, `indicadores.cobertura`, `tiempos`, `prueba_tiempos` |

## Hipótesis y criterio de comparabilidad (capítulo III, 3.3)

El criterio se fija antes de iniciar y no cambia después (`evaluacion.fijar_criterio`). Valores iniciales en
`evaluacion_analisis.CRITERIO_POR_DEFECTO`: margen de F1 de 0,10 frente al acuerdo entre archivistas, mínimo de 10
casos por tipo, rúbrica media de 3 o más y 100 % de descripciones asistidas conformes. El veredicto por tipo lo da
`evaluacion_analisis.veredicto`.

Análisis estadístico: acuerdo entre archivistas con F1 (Hripcsak y Rothschild, 2005); kappa ponderado cuadrático
para la rúbrica (`evaluacion.kappa_ponderado`); kappa de Cohen para la clasificación de desacuerdos; intervalos por
remuestreo de documentos, 1000 réplicas (`evaluacion_analisis.intervalo_f`); Wilcoxon para los tiempos pareados
(`evaluacion_analisis.wilcoxon`).

## Instrumentos

| Instrumento | Lo alimenta RICORA |
|---|---|
| 1. Matriz de evaluación ciega | Hoja de cálculo de resultados de Evaluación (`evaluacion.hoja_de_calculo`) |
| 2. Mapeo semántico RiC-O | `ric_o.py` y la exportación RiC-O validada |
| 3. Trazabilidad y gobernanza | Autoría en el grafo (`exportacion_rico`, rico:Activity del motor y de la archivista), umbral de revisión 0,70 (`config.umbral_confianza`), auditoría encadenada |
| 4. Análisis de contenido | No depende del software |
| 5. Matriz de requisitos | Cada requisito con su prueba automática (columna J del instrumento) |

## Consideraciones éticas (capítulo III, 3.7)

| Salvaguarda | En RICORA |
|---|---|
| Integridad del documento | Huella SHA-256 al ingresar y verificación; el original no se modifica; nada se borra, se anula |
| Supervisión humana | El motor propone con certeza y fragmento; la archivista acepta, corrige, rechaza o agrega; cada decisión queda registrada |
| Explicabilidad | El motor es un rico:Mechanism con su versión; cada relación se asocia a la actividad que la produjo |
| Datos personales (Ley 1581) | `datos_personales.anonimizar_para_motor` antes de todo envío al motor |
| Reserva (Ley 1712) | `derechos.py`: lo reservado no se publica, no se exporta, no se busca ni lo consulta el asistente |

## Límites que la tesis debe declarar

- OCR (Tesseract) con limpieza previa de la imagen; no reconoce manuscritos (HTR).
- El motor es externo (Gemini): su versión y la de la instrucción quedan en cada propuesta, y su cuota diaria limita
  el volumen.
- El asistente recupera pasajes por palabras (índice en español de PostgreSQL), no por significado.

## Versión evaluada

Los resultados del capítulo IV corresponden a la versión de RICORA congelada para la evaluación (etiqueta del
repositorio). Durante la evaluación no se publican cambios.
