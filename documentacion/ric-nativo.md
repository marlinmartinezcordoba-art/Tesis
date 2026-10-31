# RICORA nativo en RiC

Este documento cierra el paso de **descripción conforme con RiC** (nivel 2) a **sistema nativo en RiC** (nivel 3).
RiC no define niveles de conformidad. La escala y sus siete criterios son la propuesta de la investigación para que
la afirmación «el sistema es nativo en RiC» se pueda verificar con datos y con pruebas automáticas, no solo
declarar.

## 1. Escala de adopción

| Nivel | Nombre | Qué significa |
|---|---|---|
| 0 | Descripción multinivel | Se describe con ISAD(G) y la NTC 4095; RiC no interviene. |
| 1 | Migración a RiC | Se describe con ISAD(G) y al final un programa convierte las fichas a RiC-O. |
| 2 | Descripción conforme con RiC | Lo publicado nace en RiC y se valida contra la ontología oficial antes de publicarse. |
| 3 | Sistema nativo en RiC | Las entidades son de la institución, el acervo se consulta como un solo grafo y la historia de la descripción también es RiC. |

## 2. Los siete criterios y dónde se cumplen

| # | Criterio | Cómo lo cumple RICORA | Prueba automática |
|---|---|---|---|
| 1 | Las entidades existen por sí mismas, no subordinadas a un fondo | Agentes, lugares, materias y mandatos son autoridades de la institución (`vocabulario.CLASES_INSTITUCIONALES`): una sola URI aunque las citen documentos de varios fondos. Los lugares se enlazan con GeoNames y Wikidata (`owl:sameAs`). | `test_ric_nativo.py::test_un_lugar_es_uno_para_toda_la_institucion_y_se_enlaza_con_geonames_y_wikidata` |
| 2 | Las relaciones son datos de primer nivel | Cada relación se exporta también como nodo `rico:Relation` (su clase específica), con fuente, destino, vigencia, rol y `rico:relationCertainty`. | `test_especializacion_ric.py::test_relacion_propuesta_por_el_motor_lleva_su_certeza_y_su_fuente` |
| 3 | Admite procedencia múltiple | Un documento puede tener varios productores, y un agente puede producir en varios fondos. | `test_autoridades_compartidas.py::test_una_autoridad_para_toda_la_institucion` |
| 4 | Intercambia RiC en las dos direcciones | Entrada: RiC-O, EAD 2002/EAD3 y EAC-CPF. Salida: RiC-O (Turtle, JSON-LD), EAD3 y EAC-CPF, todo validado. | `test_importacion_rico.py` |
| 5 | Permite consultar el grafo de todo el acervo | `GET /api/publico/sparql` sin `fondo_id` consulta la unión de los grafos públicos de todos los fondos; con `fondo_id`, solo ese. | `test_ric_nativo.py::test_sparql_sobre_todo_el_acervo` |
| 6 | Cubre el modelo conceptual | 42 de 42 atributos de RiC-CM 1.0 y 85 de 85 relaciones que cita el OWL de RiC-O 1.1. | `test_cobertura_ric.py` |
| 7 | La historia de la descripción también es RiC | Cada relación se asocia (`rico:isAssociatedWithEvent`) a la actividad que la produjo: la propuesta, ejercida por el motor como `rico:Mechanism` con su versión (`rico:technicalCharacteristics`), y la validación, la corrección o la descripción manual, ejercidas por la archivista. | `test_ric_nativo.py::test_la_autoria_de_cada_relacion_esta_en_el_grafo` |

## 3. Cómo se demuestra en el sistema

- **Panel «Adopción de RiC»** (Consulta y difusión → Datos enlazados (RiC-O) → Adopción de RiC;
  `GET /api/exportacion/adopcion-ric`, `app/servicios/adopcion_ric.py`). Mide los siete criterios con los datos
  reales de la base y del almacén del grafo. Para cada criterio muestra la evidencia, cómo se verifica y la prueba
  automática que lo demuestra.
- **Cumplido no es lo mismo que en uso.** Un criterio está *cumplido* cuando el sistema tiene la capacidad y una
  prueba automática la demuestra. Está *en uso* cuando el acervo ya tiene casos que la ejercen; por ejemplo, un
  documento con dos productores. El panel muestra las dos cosas por separado, para no presentar como evidencia de
  uso lo que solo es capacidad.
- **Consultas que cualquiera puede ejecutar.** El panel trae cuatro consultas SPARQL sobre todo el acervo: quién
  afirmó cada relación, documentos de todos los fondos y su productor, lugares enlazados con GeoNames o Wikidata,
  y mecanismos con su versión.
- **La URI de cada entidad es legible para una persona.** `/id/{uuid}` entrega RiC-O (Turtle o JSON-LD) a una
  máquina y, a un navegador que pide `text/html`, una ficha legible (`app/servicios/pagina_entidad.py`). La ficha
  muestra la clase de RiC-O con su etiqueta oficial en español, los datos, las entidades relacionadas y la tabla
  «Quién afirmó cada relación»: el documento, la relación en palabras («tiene como creador a») y la entidad, con
  la actividad y quién la ejerció. Se arma con las mismas tripletas que la versión para máquinas, así que nunca
  dice algo distinto.

## 4. Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo registrar quién afirmó cada relación | (a) Solo el atributo `origen` en la base; (b) `rico:relationSource` con texto libre; (c) actividades RiC (`rico:Activity`) asociadas a cada relación | (c) | Es el patrón de RiC-O para eventos: la historia de la descripción queda en el mismo modelo que la descripción, y se consulta con SPARQL. | Más tripletas por relación (dos actividades si la propuso el motor). Se acepta: la consulta y la validación SHACL lo soportan. |
| Cómo aparece el motor de análisis | (a) Ocultarlo; (b) un `rico:Mechanism` con su versión | (b) | Transparencia: la evaluación (objetivo 3) depende de saber qué versión del motor propuso cada relación. RiC-A41 (características técnicas) existe para esto. | Un motor sin versión registrada no puede exportarse como mecanismo válido. Esas relaciones salen sin el agente de la propuesta, se cuentan como omitidas y el criterio 7 queda parcial (nivel 2). Así no se bloquea la publicación. |
| Cómo aparece la archivista | (a) Su nombre en todos los grafos; (b) solo su cargo; (c) cargo en el público y nombre en el completo | (c) | Ley 1581 de 2012: el grafo público no expone datos personales de quien trabaja en el archivo. La responsabilidad institucional queda trazada por el cargo (`rico:Position`), y el nombre (`rico:Person`) queda en el grafo completo, de acceso restringido. | Si un fondo tiene varias archivistas, el grafo público no las distingue. El grafo completo y la auditoría sí. |
| Qué entidades son de la institución | (a) Todas; (b) agentes, lugares, materias y mandatos; (c) solo agentes | (b) | Las formas documentales, los tipos de actividad y las funciones nacen de la TRD de cada fondo; compartirlas mezclaría instrumentos distintos. Un lugar o un agente, en cambio, es el mismo para toda la institución. | Duplicados creados antes del cambio: se resuelven con «Posibles duplicados» en Autoridades y términos. |
| Enlace de lugares con fuentes externas | (a) Ninguno; (b) GeoNames; (c) GeoNames y Wikidata | (c) | Fuentes abiertas y gratuitas. GeoNames es la referencia para topónimos; Wikidata ya se usaba para agentes. Se valida el formato (GeoNames: número; acepta la URL completa). | Un identificador mal escrito enlaza otro lugar. La archivista lo verifica al registrarlo. |
| Consulta SPARQL del acervo | (a) Un grafo por fondo; (b) la unión de los grafos públicos | (b), con (a) disponible con `fondo_id` | Un sistema nativo responde preguntas de todo el acervo con una sola consulta. Solo entran grafos públicos ya sincronizados, nunca lo clasificado o reservado. | Más costo por consulta. Se limita con el máximo de resultados y el tiempo de espera ya existentes. |
| Página HTML en la URI | (a) Solo RDF; (b) negociación de contenido: HTML para personas, RDF para máquinas | (b) | Es la práctica de datos enlazados: la misma URI sirve a ambos. La ficha usa las mismas tripletas que la versión RDF y escapa todo el texto. | Ninguno nuevo: respeta la misma regla de acceso que la versión RDF. |
| Cómo se informa el nivel | (a) Declararlo en la tesis; (b) que el sistema se mida a sí mismo | (b) | La afirmación es verificable por un jurado o un evaluador, con los datos del momento y las pruebas automáticas citadas. Distingue capacidad de uso. | Si cambian los datos, cambia el resultado. Eso es lo esperado. |

## 5. Requisito 6: el título y el alcance también citan su evidencia

Antes, cada entidad propuesta por el motor traía su fragmento literal del texto, pero el título y el alcance y
contenido no traían ninguno. La afirmación «toda propuesta cita su evidencia» no era cierta para esos dos campos.

Ahora el motor devuelve `evidencia_titulo` (1 a 3 fragmentos) y `evidencia_alcance` (1 a 6), cada uno copiado
literalmente con su documento. El esquema de respuesta los exige. RICORA los localiza en el texto igual que los
fragmentos de las entidades (`motor._evidencias`). En el espacio de trabajo, debajo de cada campo, aparecen los
fragmentos como enlaces que resaltan el pasaje en el documento. Si ninguno se halla en el texto, dice «Evidencia:
no identificada en el texto». La decisión de la archivista sobre el título y el alcance queda en la auditoría con
`fragmento_localizado`, y así entra en el indicador «propuestas sin fragmento localizado».

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Evidencia de los campos de texto libre | (a) Sin evidencia; (b) un fragmento; (c) varios fragmentos localizados | (c) | El alcance sintetiza varios documentos: un solo fragmento no lo sustenta. | El motor puede citar fragmentos que no están en el texto; se marcan como no localizados y no se resaltan. |
| Alcance sin ningún fragmento hallado | (a) Mantener la confianza del motor; (b) bajarla como la de una entidad sin fragmento | (b) | Misma regla para todo lo que propone el motor: sin evidencia verificable, confianza baja (`CONFIANZA_SIN_FRAGMENTO`). | Ninguno: la archivista revisa igual. |
| Propuestas guardadas antes del cambio | (a) Tratarlas como «no identificada»; (b) como «no registrada» | (b) | No se puede afirmar que no había evidencia si no se pidió. La pantalla no muestra la línea y la auditoría registra `null`. | Ninguno. |

El cambio de instrucciones cambia `VERSION_PROMPT`. Cada documento de una evaluación guarda la propuesta que se
generó para él, con su versión de instrucciones, y los resultados listan las versiones usadas («motores»). Si una
evaluación mezcla versiones, sus cifras no son comparables entre sí: la evaluación del objetivo 3 debe generarse
completa después de este cambio.

## 6. Migraciones

- `0055_autoria_en_el_grafo`: incrementa `version_datos` de todos los grafos para que el trabajador los
  regenere con la autoría de cada relación. No borra ni modifica datos descriptivos.
