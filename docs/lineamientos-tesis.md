# Capítulo IV. Lineamientos técnicos para la incorporación de inteligencia
artificial en la automatización asistida de procesos archivísticos en
archivos históricos del orden nacional

> **Nota de trazabilidad metodológica.** Este documento es un **borrador
> experto de trabajo**, elaborado para adelantar la estructura y el
> contenido técnico del capítulo IV antes de cerrar las Fases 2 y 3. Cada
> lineamiento debe contrastarse con los hallazgos del análisis de contenido
> (Fase 2, hasta el 13/10/2026) y con el diagnóstico normativo (Fase 3,
> 16/10–16/11/2026), y validarse con la dirección de la tesis y con Zully y
> Catalina antes de considerarse definitivo. Donde la redacción de una norma
> específica (Acuerdo 001 de 2024 del AGN; CONPES 4144 de 2025) requiere el
> número exacto de artículo, se deja señalado "**verificar en Fase 3**" en
> vez de inventar una cita que el equipo no ha confirmado todavía.
>
> **Una precisión normativa para el equipo:** la Recomendación sobre la
> Ética de la Inteligencia Artificial fue adoptada por la Conferencia
> General de la UNESCO en **noviembre de 2021**, no en 2023. Si el
> anteproyecto ya cita "2023", conviene corregirlo antes de la sustentación;
> es el tipo de detalle que un jurado revisa.

## 4.1 Presentación y alcance

Los lineamientos que siguen responden a la pregunta de investigación de la
tesis: **cómo incide la incorporación de IA en la automatización de los
procesos archivísticos de los archivos históricos del orden nacional, en
relación con la autenticidad, la integridad y la accesibilidad del
patrimonio documental**. No son una norma técnica ni tienen fuerza
obligatoria fuera de este trabajo: son una **propuesta técnica** dirigida a
las entidades del orden nacional que custodian archivos históricos, para
que evalúen la pertinencia de una solución de IA antes de incorporarla a
sus procesos.

Cada lineamiento se redactó con la misma estructura, para que sea
verificable y no solo declarativo:

| Campo | Qué contiene |
|---|---|
| **Código** | Proceso (CLA, DES, VAL, MET, ACC) y consecutivo. |
| **Enunciado** | Lo que debe cumplir una solución de IA, en lenguaje claro. |
| **Atributo protegido** | Autenticidad, integridad o accesibilidad (la tríada de la pregunta de investigación). |
| **Fundamento normativo** | La norma o estándar que lo respalda. |
| **Criterio de verificación** | Cómo se comprueba, en términos observables, no solo declarados. |
| **Riesgo que mitiga** | Qué pasa si el lineamiento no se cumple. |
| **Obligatorio / recomendado** | Si es una condición mínima o una buena práctica deseable. |
| **Estado en MAZUCA** | Si el prototipo ya lo aplica, lo aplica parcialmente, o queda como trabajo futuro. Esta columna es honesta a propósito: no todos los lineamientos tienen que estar implementados para que la tesis sea válida — el prototipo es una instanciación parcial, no el lineamiento mismo. |

## 4.2 Principios rectores transversales

Antes de los lineamientos por proceso, cinco principios que atraviesan los
cinco procesos y que se derivan directamente de la pregunta de
investigación:

1. **Supervisión humana significativa.** La IA propone; una persona con
   competencia archivística decide. No basta con que exista un botón de
   "aceptar": la decisión debe poder revisarse, tener un motivo cuando se
   rechaza, y la persona debe tener información suficiente (evidencia,
   confianza, modelo usado) para decidir con criterio, no por inercia.
   *(UNESCO, 2021, principio de supervisión y decisión humanas; ISO
   15489-1:2016)*.
2. **Trazabilidad de la intervención de la IA.** Todo dato que se origina
   en un sistema de IA debe poder distinguirse del dato producido
   directamente por una persona, con el modelo, la versión y la fecha.
   *(ISO 14721 —OAIS—, información de procedencia; ISO 15489-1:2016)*.
3. **No sustitución del principio de procedencia ni del orden original.**
   La IA puede acelerar tareas, pero no puede reorganizar el archivo según
   una lógica distinta a la que la propia documentación revela.
   *(Ley 594 de 2000; ISAD(G) 2.ª ed.)*.
4. **Verificabilidad de la evidencia, no solo de la salida.** No basta con
   que la IA entregue un dato plausible: el dato debe poder rastrearse
   hasta el fragmento del documento que lo sustenta. Esto es lo que separa
   una automatización asistida de una automatización opaca.
   *(Principio general de explicabilidad, UNESCO, 2021; aplicado aquí como
   control técnico, no solo como declaración de buenas intenciones)*.
5. **Proporcionalidad frente a los datos personales y sensibles.** Ninguna
   automatización puede ampliar el acceso a datos personales más allá de lo
   que ya permite la ley, y toda transferencia de datos a un tercero
   (incluida una nube de IA) exige que la entidad haya decidido
   previamente qué tan sensible es la información.
   *(Ley 1581 de 2012; Ley 1712 de 2014)*.

## 4.3 Lineamientos por proceso

### 4.3.1 Clasificación

| Código | Enunciado | Atributo | Fundamento normativo | Obligatorio | Estado en MAZUCA |
|---|---|---|---|---|---|
| **CLA-01** | La IA propone la ubicación del documento dentro del cuadro de clasificación vigente de la entidad; la asignación definitiva la hace una persona con competencia archivística. | Autenticidad | Ley 594 de 2000, art. 24 (obligación de clasificar según cuadro); Acuerdo 001 de 2024 del AGN (verificar artículo en Fase 3) | Sí | Implementado |
| **CLA-02** | La propuesta de clasificación respeta el principio de procedencia y el orden original: no agrupa documentos de productores distintos en una misma unidad, ni reinterpreta la estructura del fondo. | Integridad | Ley 594 de 2000, art. 4 (principio de procedencia); ISAD(G) 2.ª ed., área de contexto | Sí | Implementado (control de diseño; no hay una prueba automática que detecte mezcla de productores) |
| **CLA-03** | La IA solo propone entre las unidades del cuadro de clasificación que la entidad ya cargó; nunca crea fondos, secciones, series ni subseries nuevas. Toda propuesta cita evidencia textual verificable contra el documento. | Autenticidad | Ley 594 de 2000; ISO 15489-1:2016 | Sí | Implementado |
| **CLA-04** | La entidad audita periódicamente, por muestreo, la exactitud de las propuestas de clasificación aceptadas sin corrección, y ajusta el cuadro de palabras clave o los ejemplos dados a la IA cuando el error supera un umbral definido por la entidad. | Integridad | ISO 15489-1:2016 (mejora continua de procesos); UNESCO, 2021 (evaluación de impacto y monitoreo continuo) | Recomendado | **Implementado**: comando `auditoria_muestra clasificacion`, con reporte de exactitud. |

### 4.3.2 Descripción

| Código | Enunciado | Atributo | Fundamento normativo | Obligatorio | Estado en MAZUCA |
|---|---|---|---|---|---|
| **DES-01** | Los borradores de descripción generados por IA cubren, como mínimo, los seis elementos esenciales de ISAD(G): código de referencia, título, productor, fecha(s), volumen y soporte, y nivel de descripción. | Accesibilidad | ISAD(G) 2.ª ed., elementos 3.1.1–3.1.5 y 3.2.1 | Sí | Implementado |
| **DES-02** | Cada dato generado por IA identifica el modelo, la versión y el nivel de confianza declarado por el proveedor, y se distingue del dato ingresado directamente por una persona. | Autenticidad | ISO 15489-1:2016; UNESCO, 2021 | Sí | Implementado |
| **DES-03** | Todo dato descriptivo propuesto por IA cita un fragmento literal del documento que lo respalda; la plataforma verifica automáticamente que ese fragmento exista en el texto fuente antes de mostrar la sugerencia. Un dato sin evidencia verificable solo se incorpora si una persona lo corrige o lo redacta de nuevo. | Autenticidad | ISAD(G) 2.ª ed.; ISO 15489-1:2016; UNESCO, 2021 (fiabilidad y explicabilidad) | Sí | Implementado |
| **DES-04** | Las personas, lugares e instituciones identificadas por IA se registran como entidades vinculables, con la relación que tienen con el documento (productor, mencionado, destinatario), siguiendo el modelo de Records in Context en lugar de tratarlas como texto libre. | Accesibilidad | Records in Contexts – Conceptual Model (ICA) | Recomendado | **Implementado** en el proveedor en la nube. El proveedor local (spaCy) solo reconoce entidades, no su papel: propone siempre "mencionado" por defecto, limitación documentada. |

### 4.3.3 Valoración

| Código | Enunciado | Atributo | Fundamento normativo | Obligatorio | Estado en MAZUCA |
|---|---|---|---|---|---|
| **VAL-01** | La IA puede señalar indicios de valor secundario (histórico, cultural o científico), pero en ningún caso recomienda, prioriza ni ejecuta una acción de eliminación o disposición documental. En un archivo histórico de conservación permanente, esta restricción es absoluta. | Integridad | Decreto 1080 de 2015; Acuerdo 001 de 2024 del AGN (verificar artículo en Fase 3) | Sí | Implementado — y reforzado estructuralmente: la plataforma no ofrece ninguna función de eliminar un documento, ni para la IA ni para una persona usuaria. |
| **VAL-02** | Todo indicio de valor secundario señalado por IA cita un fragmento literal del documento que lo respalda, y la plataforma verifica esa evidencia antes de considerarlo válido. | Autenticidad | ISO 15489-1:2016; UNESCO, 2021 | Sí | Implementado |
| **VAL-03** | La entidad revisa periódicamente, por muestreo, si los indicios de valor secundario señalados por IA concentran sesgos temáticos o geográficos (por ejemplo, favorecer sistemáticamente documentos de ciertas regiones o actores sobre otros), y documenta el hallazgo. | Integridad | UNESCO, 2021, principio de equidad y no discriminación | Recomendado | **Implementado**: comando `auditoria_muestra valoracion --reporte`, desglosado por tipo de indicio. Sigue dependiendo de que se acumule volumen suficiente para que el muestreo tenga sentido estadístico. |

### 4.3.4 Gestión de metadatos

| Código | Enunciado | Atributo | Fundamento normativo | Obligatorio | Estado en MAZUCA |
|---|---|---|---|---|---|
| **MET-01** | Todo objeto digital recibe un valor de fijeza (hash criptográfico) desde el momento de su ingreso, y ese valor se puede volver a verificar en cualquier momento posterior. | Integridad | ISO 14721 (OAIS), información de fijeza (*fixity information*) | Sí | Implementado (SHA-256) |
| **MET-02** | Todas las acciones sobre un documento —humanas o generadas por IA— quedan registradas en una bitácora que permite detectar si algún registro fue alterado o eliminado después de creado. | Autenticidad | ISO 15489-1:2016; ISO 14721 (OAIS), información de procedencia | Sí | Implementado (bitácora encadenada por hash, al estilo PREMIS) |
| **MET-03** | El texto obtenido por reconocimiento óptico de caracteres declara la herramienta, la versión y el nivel de confianza; por debajo de un umbral definido por la entidad, el texto debe marcarse para revisión humana antes de usarse en descripción o en acceso. | Autenticidad | ISO 15489-1:2016; ISO 14721 (OAIS) | Sí | Implementado (umbral de referencia: 75 %, a validar por la entidad) |
| **MET-04** | Los metadatos técnicos y descriptivos del documento se pueden exportar en un esquema estándar interoperable (por ejemplo, Dublin Core o PREMIS), para que la entidad no quede atada a un formato propietario. | Accesibilidad | ISO 15489-1:2016 (interoperabilidad); buenas prácticas de preservación digital | Recomendado | **Implementado**: exportación a Dublin Core (oai_dc) y PREMIS 3, con evento en la bitácora. |

### 4.3.5 Acceso

| Código | Enunciado | Atributo | Fundamento normativo | Obligatorio | Estado en MAZUCA |
|---|---|---|---|---|---|
| **ACC-01** | Antes de publicar un documento, la IA señala posibles datos personales o sensibles, para que una persona decida si el documento se publica sin cambios, se anonimiza o se restringe. | Accesibilidad | Ley 1581 de 2012; Ley 1712 de 2014 | Sí | Implementado |
| **ACC-02** | La búsqueda asistida por IA muestra el resultado dentro de su contexto archivístico (nivel de descripción, productor, fondo), nunca como un fragmento aislado sin procedencia. | Accesibilidad | ISAD(G) 2.ª ed.; Records in Contexts (ICA) | Recomendado | Parcial: los datos ya existen, pero todavía no hay un buscador propio en el portal (queda pendiente el portal público). |
| **ACC-03** | Solo se publica en el portal de consulta el documento que tiene descripción completa, integridad verificada, revisión de datos personales decidida y ninguna sugerencia de IA pendiente de validación. | Accesibilidad | Ley 1712 de 2014; Ley 1581 de 2012; Ley 594 de 2000 | Sí | Implementado |
| **ACC-04** | Solo se envía a un servicio de IA en la nube el texto de un documento cuya revisión de datos personales ya fue decidida; si se decidió anonimizar, se envía la versión anonimizada, y un documento restringido no se envía a ningún servicio externo. | Integridad | Ley 1581 de 2012, art. 26 (transferencia internacional de datos) | Sí | Implementado |
| **ACC-05** | Los documentos publicados incluyen una alternativa textual o una transcripción para las personas que usan lectores de pantalla, siguiendo como referencia las Pautas de Accesibilidad para el Contenido Web (WCAG). | Accesibilidad | Ley 1712 de 2014 (acceso en condiciones de igualdad); WCAG 2.2 como referencia técnica | Recomendado | **Trabajo futuro, deliberadamente**: depende del portal público de consulta, que el equipo decidió dejar fuera del alcance de la tesis. No tiene sentido construirlo antes de tener dónde mostrarlo. |

## 4.4 Matriz resumen: cobertura por atributo y por proceso

| | Clasificación | Descripción | Valoración | Metadatos | Acceso | Total |
|---|---|---|---|---|---|---|
| Autenticidad | CLA-01, CLA-03 | DES-02, DES-03 | VAL-02 | MET-02, MET-03 | ACC-04 | 8 |
| Integridad | CLA-02, CLA-04 | — | VAL-01, VAL-03 | MET-01 | — | 5 |
| Accesibilidad | — | DES-01, DES-04 | — | MET-04 | ACC-01, ACC-02, ACC-03, ACC-05 | 7 |
| **Total** | **4** | **4** | **3** | **4** | **5** | **20** |

La tabla muestra un desbalance real que conviene discutir en la Fase 3: hoy
hay más lineamientos de **autenticidad** que de **integridad** en
clasificación y descripción, y ninguno de integridad en descripción ni en
acceso. No es necesariamente un error —hay procesos donde la integridad se
protege sobre todo desde metadatos—, pero es un punto que el diagnóstico
normativo debería confirmar o corregir con literatura y con los hallazgos
del análisis de contenido, no solo con este borrador.

## 4.4bis Actualización: cuatro lineamientos nuevos ya construidos

Después de la primera versión de este capítulo, se implementaron cuatro de
los cinco lineamientos que estaban marcados como "trabajo futuro":
CLA-04, DES-04, VAL-03 y MET-04 (columna "Estado en MAZUCA" arriba, ya
actualizada). El único que sigue pendiente es **ACC-05**, y de forma
deliberada: depende del portal público de consulta, que el equipo decidió
mantener fuera del alcance de esta tesis.

## 4.5 Lo que falta antes de que estos lineamientos sean definitivos

1. **Contrastar cada enunciado con los hallazgos de la Fase 2** (análisis de
   contenido): ¿qué problemas reales reportan los estudios sobre IA en
   archivos históricos? ¿Los lineamientos de arriba responden a ellos o
   faltan categorías?
2. **Confirmar los artículos exactos** del Acuerdo 001 de 2024 del AGN y
   del CONPES 4144 de 2025 (Fase 3); en este borrador se citan por su
   materia, no por artículo, para no inventar una referencia que nadie ha
   verificado.
3. **Decidir con la dirección de la tesis** si los lineamientos "nuevos,
   propuestos" (CLA-04, DES-04, VAL-03, MET-04, ACC-05) se quedan como
   recomendados y quedan para trabajo futuro, o si alguno debe volverse
   obligatorio y construirse en el prototipo antes de abril de 2027.
4. **Corregir la fecha de la Recomendación de la UNESCO** (2021, no 2023)
   en el resto de la tesis si aparece citada con el año equivocado.
