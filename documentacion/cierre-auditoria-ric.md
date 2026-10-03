# Cierre de brechas de la auditoría de conformidad RiC

Este documento lleva el cierre, hallazgo por hallazgo, de los 69 hallazgos no conformes de la auditoría del 3 de octubre de 2026 (`auditoria-conformidad-ric.md`). La fuente de verdad del estado de cada hallazgo es el **panel de hallazgos de conformidad** del módulo de Auditoría:

- cada hallazgo entra con su identificador («INS-02», «PRE-10»…);
- al desplegar, el registro de cierres en código (`app/servicios/cierre_auditoria.py`) lo pasa a «cerrado», o a «en corrección» si algo depende de infraestructura o de una decisión;
- el cambio de estado queda con su fecha, su evidencia y las pruebas que lo cubren;
- una prueba (`tests/test_cierre_auditoria.py`) exige que cada prueba citada exista de verdad.

Reglas que se siguieron:

- ningún hallazgo se da por cerrado sin una prueba automatizada en verde;
- las pruebas nuevas se escribieron primero contra el código anterior y fallaban (reproducían el hallazgo);
- ningún nombre de RiC-O nuevo entra sin verificarlo contra el OWL oficial. Hay una prueba que escanea todo el código y la interfaz.

## 1. Las cuatro decisiones de especificación (sección 2 del prompt de cierre)

La autora las resolvió el 3 de octubre de 2026, antes de escribir código para ellas.

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| ING-01 e ING-02 · Lote de transferencia y paquete de envío | Las dos cosas · solo la procedencia · ninguna | **Las dos cosas** | La procedencia de una transferencia (remitente, dependencia, acta; Ley 594 de 2000) debe quedar en una tabla propia, no en notas. El paquete de envío en BagIt da al lote la misma verificabilidad que ya tiene el paquete de preservación. | Más pasos al ingresar. Se mitiga con valores por defecto y un solo formulario por lote. |
| CM-21 · Cardinalidades | Mantener todo único · un superior orgánico más otros · abrir todo como RiC-O | **Un superior orgánico más otros** | El principio de procedencia y el orden original del cuadro de clasificación exigen una inclusión orgánica única. Otras inclusiones (una colección facticia) se admiten como filas adicionales. La custodia pasa a ser una cadena con fechas. | Dos caminos para «estar incluido en». Se mitiga marcando cuál es el orgánico. |
| INS-01 · RDF sin sesión | Solo lo público · mantener con sesión | **Solo lo público**, tras cerrar INS-02 | Datos enlazados abiertos para lo que la ley permite publicar. Lo sigue gobernando el interruptor del administrador, que está apagado. | Publicar algo mal clasificado. Se mitiga con el filtro de INS-02, ya cerrado y probado, y porque el interruptor sigue apagado hasta que la autora lo encienda. |

## 2. Prioridad crítica (sección 3 del prompt de cierre)

| Hallazgo | Estado | Qué se hizo | Pruebas |
|---|---|---|---|
| INS-02 · Fugas de lo reservado | Cerrado | La reserva se aplica en todos los caminos laterales. RDF y `/id/` excluyen los archivos reservados (por declaración propia o heredada) y las entidades que solo citan documentos no exportados. La ficha de consulta solo nombra las partes, la secuencia y los archivos visibles. El grafo oculta el archivo reservado. La reserva vencida se levanta sola (Ley 1712, art. 22). | `tests/test_cierre_ins02.py` (6) |
| PRE-10 · Respaldo de la base y simulacro | Cerrado | Ver la sección 3. | `tests/test_cierre_pre10.py` (7) |
| O-28 · Nombre de RiC-O inventado en la presentación | Cerrado | Una sola fuente, `ric_o.uri()`. Se corrigieron `hasDocumentaryFormType` y `hasOrHadMandateType`, y se retiraron los diccionarios paralelos de `enums.py`. | `tests/test_ric_o.py` (escaneo de app/ y frontend/ contra el OWL) |
| CM-11 y O-19 · El mecanismo no se exportaba | Cerrado | Ver la sección 4. | `tests/test_cierre_cm11.py` (3) |
| PRE-07 · Segunda copia no independiente | **En corrección** | Hecho: manifiesto de huellas fuera de la base, alerta «huella de referencia alterada» y la web en solo lectura sobre la segunda copia. Falta la independencia física: otro disco u otro equipo. | `tests/test_cierre_pre07.py` (3) |
| PRE-08 · La fijeza podía saltarse un ciclo | Cerrado | La verificación va por antigüedad y en lotes, y hay alerta de atraso. | `tests/test_cierre_pre08.py` (3) y la prueba de frecuencia reescrita |

## 3. Respaldo de la base de datos (PRE-10)

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo se vuelca | `pg_dump` simple · `pg_basebackup` · `pg_dump -Fc` sobre una instantánea exportada | **`pg_dump -Fc --snapshot`** | Los conteos y la huella de control se toman **en la misma instantánea** que el volcado. Así el simulacro compara exactamente lo mismo y no se confunde con escrituras ocurridas entre medio. | Un volcado lógico, no un respaldo continuo: se puede perder lo escrito desde el último volcado (24 h por defecto, configurable a 1 h). |
| Cómo se prueba | Confiar en que `pg_dump` no falló · restaurar a mano de vez en cuando · simulacro automático | **Simulacro automático en cada respaldo** | Un respaldo nunca restaurado no es un respaldo. El volcado se restaura en una base efímera y se comparan los conteos de 11 tablas clave y la huella de las huellas de fijeza. La base efímera se elimina al terminar. | Doble carga breve sobre el mismo PostgreSQL. Es aceptable en un fondo de este tamaño. |
| Dónde queda | Mismo volumen · otro volumen · almacenamiento de pago | **Otro volumen, más la descarga obligatoria a otro equipo** | Las reglas del proyecto excluyen recursos de pago. La copia fuera del servidor la hace la administración al descargar el respaldo desde Preservación › Configuración. Si pasan 7 días sin hacerlo, salta una alerta. | Depende de una persona. Se mitiga con la alerta y con el registro de cada descarga. |
| Retención | Guardar todo · retirar los viejos | **Conservar los 30 últimos volcados** (configurable) | El disco del servidor es pequeño. El archivo retirado deja su registro, con la fecha en que salió. | Un volcado viejo ya no está en el servidor. Si se descargó, sigue existiendo fuera. |
| Contraseña | En la línea de órdenes · en una variable de entorno | **`PGPASSWORD`** en el entorno del proceso | No aparece en la lista de procesos ni en los registros. | Ninguno relevante. |

## 4. Mecanismo en la exportación (CM-11, O-19 y parte de CM-22)

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| ¿Se exporta el mecanismo? | Nunca, y se corrige el anexo · siempre · solo el que actuó sobre un archivo exportado | **Solo el que actuó sobre un archivo exportado** | Siegfried identificó el formato y Ghostscript migró el archivo: esa es historia del objeto (contexto de RiC). El motor de análisis es procedencia del dato, que el sistema nunca exporta. | Ninguno: no sale nada interno. |
| Cómo se modela la acción técnica | Nota de texto · PREMIS dentro del RDF · `rico:Activity` | **`rico:Activity`** que el mecanismo ejerce (`performsOrPerformed`) y que afecta al archivo (`affectsOrAffected`, R059) | Usa clases y propiedades verificadas contra el OWL. R059 es la más cercana: «el evento tuvo un impacto significativo en la cosa». Su rango es `Thing`. | R059 es general. Queda marcada como tal en el mapeo (`ric_o.ACCION_TECNICA`). |
| La versión | Texto en la acción · atributo del mecanismo | **`rico:technicalCharacteristics` del mecanismo** (A41, dominio `Mechanism`) | Se declara una sola vez y la referencian todas las acciones. | Ninguno. |

## 5. Bloque 1 · RiC-CM

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Integridad de la tabla de relaciones (CM-19) | Validar en cada servicio · restricción de la base · guardián de sesión | **Guardián `before_flush`** sobre toda sesión de SQLAlchemy | Ninguna ruta, actual o futura, puede escribir una fila que RiC-O no admita. Al activarse encontró dos errores reales que se corrigieron: la expedición del mandato con R080 y el remitente o destinatario de un conjunto, que el mapeo restringía sin necesidad. | Un error de programación aparece como fallo al guardar. Es preferible a un dato que la exportación descarta en silencio. |
| Documentos de un expediente (CM-03) | Cambiar la publicación de conjuntos · individualizar después | **Individualizar después** (`…/individualizar`) | No rompe el flujo de descripción. Cada oficio gana su Record cuando el archivista lo necesita, y se describe al reabrirlo. | Requiere un paso más por documento. |
| Original físico (CM-04) | Texto `soporte` en el documento · Instantiation sin archivo | **Instantiation sin archivo** (estado `registro_fisico`) | Es lo que dice RiC-CM: el papel y el PDF son dos inscripciones del mismo documento; la digitalización deriva del original (R014). | Columnas de archivo ahora opcionales. Los servicios que esperan un archivo filtran por estado. |
| Regla de retención (CM-18, DES-09) | Tabla aparte · clase del vocabulario | **Clase `regla` (rico:Rule)** | Reutiliza la ficha, los vínculos, la fusión y la exportación del vocabulario. RiC-O ya ofrece `regulatesOrRegulated` entre una regla y lo que regula. | La regla se crea en Vocabularios y se une a la serie desde su ficha: son dos pasos. |
| Fechas como entidad o atributo (CM-16) | Todo como nodo Fecha · todo como texto · mixto documentado | **Mixto documentado** | Son entidad Date (nodo propio): la fecha del documento, el periodo de la actividad y la expedición del mandato. Son atributos EDTF validados: las fechas extremas, la existencia del agente, el periodo de un hito y la vigencia de una relación o de un tramo de custodia. Todas usan el mismo subconjunto EDTF. | Un atributo no tiene su propia URI. Se exporta como nodo Date anónimo cuando RiC-O lo pide. |
| Acciones técnicas (CM-22) | Solo PREMIS · Activity en la base · Activity proyectada al exportar | **Activity proyectada al exportar** | En la base la acción es un evento PREMIS que apunta a su mecanismo, que es lo correcto para preservación. RiC la ve como Activity con tipo, ejercida por el Mechanism y documentada por su resultado. | Ninguno: es la misma información en dos vocabularios. |

## 6. Bloque 2 · RiC-O

| Hallazgo | Estado | Qué se hizo | Pruebas |
|---|---|---|---|
| O-12 · Nombres de RiC-O escritos a mano | Cerrado | La exportación toma toda clase y propiedad del mapeo único. Una prueba impide volver a escribir `RICO.X` en la exportación. | `tests/test_ric_o.py`, `tests/test_cierre_bloque2.py` |
| O-26 · Idiomas de una agrupación | Cerrado | Un idioma: «todos sus miembros». Varios: «algunos miembros» en cada uno. | `tests/test_cierre_bloque2.py` (2) |
| O-30 · URI externas e idioma | Cerrado | URI canónicas de cada autoridad e idioma ISO 639-3 validado y serializado en BCP 47. | `tests/test_cierre_bloque2.py` (11) |
| O-31 · Relaciones sin tripleta propia | Cerrado | Quince relaciones con tripleta comprobada. Las pruebas del mapeo corren sin PostgreSQL. | `tests/test_cierre_o31.py` (4) |
| O-32 · Validación SHACL solo a demanda | Cerrado | Formas nuevas y validación en cada descarga, con auditoría, cabecera y alerta. | `tests/test_cierre_o32.py` (11) |

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Fechas extremas de una agrupación (O-12) | `hasCreationDate` · `hasOrHadAllMembersWithCreationDate` | **`hasOrHadAllMembersWithCreationDate`** para el conjunto; `hasCreationDate` para el documento | Las fechas extremas (ISAD(G) 3.1.3) son las de producción de lo que contiene la agrupación, no la «creación» del conjunto. RiC-O tiene la propiedad exacta (dominio `RecordSet`), verificada contra el OWL. | Un consumidor que buscaba `hasCreationDate` en una serie ya no lo encuentra. Es lo correcto según la norma. |
| Varios idiomas en una agrupación (O-26) | Siempre «todos» · siempre «algunos» · según la cantidad | **Según la cantidad** | Si el expediente declara un solo idioma, todos sus documentos están en él. Si declara dos, decir «todos en español y todos en latín» es falso. | Un expediente con todos sus documentos bilingües saldría como «algunos». Es una afirmación más débil, pero no falsa. |
| URI de autoridad (O-30) | https en todas · la que publica cada autoridad | **La canónica de cada una**: http para Wikidata, VIAF y LC; https para ISNI | En RDF, `http://…/Q42` y `https://…/Q42` son nodos distintos. Un `owl:sameAs` hacia la forma no canónica no enlaza con nada. | Si una autoridad cambia su forma canónica, hay que actualizar `URI_EXTERNA`. Está en un solo lugar. |
| Idioma de una forma del nombre (O-30) | Texto libre · ISO 639-3 validado | **ISO 639-3 validado**, convertido a BCP 47 (dos letras cuando existen) al serializar | Es el mismo código que ya usan las descripciones. BCP 47 exige la forma corta («es», no «spa»). | Un idioma de tres letras sin forma de dos letras sale con las tres, lo que es válido en BCP 47. |
| Base de pruebas (O-31) | `autouse` · solo bajo demanda | **Solo bajo demanda** (`db` la pide) | Las pruebas del mapeo RiC-O no tocan la base y deben correr aunque PostgreSQL esté detenido. Así un fallo de infraestructura no oculta un error de conformidad. | Una prueba nueva que use la base sin pedir `db` fallaría. Todas lo piden hoy. |
| Entidades sin documentos en la exportación | Exportar todo el vocabulario · solo el contexto alcanzable desde los documentos | **Solo el contexto alcanzable** (se mantiene) | Lo encontró la prueba de O-31: un cargo sin ningún vínculo a documentos no sale en el RDF. La exportación describe el fondo, no el vocabulario completo. Así se evita publicar autoridades sueltas sin relación con lo publicado. | Una autoridad recién creada no aparece hasta que se vincula. Es coherente con el filtro de lo reservado (INS-02). |
| ¿Bloquear una descarga no conforme? (O-32) | Bloquear · servir sin mirar · servir marcada | **Servir marcada**: cabecera, auditoría y alerta | Los datos son de la entidad: negarle la descarga por un defecto del software es peor que entregarla avisando. La alerta hace que el defecto se corrija y la auditoría deja constancia de qué se entregó. | Alguien podría publicar un archivo marcado como no conforme. Se mitiga con el aviso visible en la interfaz. |

## 7. Bloque 3 · Ingesta y descripción

| Hallazgo | Estado | Qué se hizo | Pruebas |
|---|---|---|---|
| ING-01 · Sin paquete de envío (SIP) | Cerrado | Paquete BagIt al confirmar el lote, validado con bagit-python | `tests/test_cierre_ing01_ing02.py` |
| ING-02 · Sin procedencia del lote | Cerrado | Tabla `lotes_ingesta` con remitente, dependencia, acta y forma de ingreso | `tests/test_cierre_ing01_ing02.py`, `tests/test_cierre_bloque3.py` |
| ING-06 · OAIS en la ingesta | Cerrado | Recepción, validación, acuse y procedencia (tabla abajo) | `tests/test_cierre_ing01_ing02.py` |
| ING-07 · Enlace de la alerta de formato | Cerrado | Las dos alertas de la ingesta enlazan a describir | `frontend/src/pruebas/alertas.test.ts`, `tests/test_cierre_ing01_ing02.py` |
| ING-08 · Revisor en la ingesta | Cerrado (desviación documentada) | Lectura sí, escritura no, también en los lotes | `tests/test_cierre_ing01_ing02.py`, `tests/test_ingesta.py` |
| ING-09 · Compromisos del prompt y OCR intermitente | Cerrado | Causa raíz del OCR intermitente corregida | `tests/test_cierre_ocr_estable.py` |
| DES-03 · EDTF fuera del subconjunto | Cerrado | `1948-XX-12` y `194X-03` se rechazan | `tests/test_cierre_bloque3.py` |
| DES-07 · ISAD(G) incompleta | Cerrado | Los 26 elementos con fuente, ficha y RDF | `tests/test_cierre_bloque3.py` |
| DES-10 · Contexto léxico del motor | Cerrado (decisión mantenida y ampliada) | También las otras formas del nombre | `tests/test_cierre_bloque3.py` |
| DES-11 · Compromisos del prompt de descripción | Cerrado | Prueba de `%` y `194X` por la API | `tests/test_cierre_bloque3.py` |

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Paquete de envío (ING-01) | Copiar los archivos al paquete · comprimir · enlaces duros | **Enlaces duros** al archivo de la ingesta (copia si el disco no los admite) | El paquete existe completo y validable sin ocupar el doble de espacio en un servidor pequeño. Los archivos de la ingesta no se modifican nunca, así que el enlace no cambia por debajo. | Si un día se borrara el archivo de la ingesta, el enlace del paquete lo conserva (es el mismo archivo, con dos nombres). |
| Integridad del envío (ING-01) | Confiar en la ingesta · recalcular la huella al empaquetar | **Recalcular y comparar** | Si el archivo cambió entre la carga y la confirmación, el lote no se confirma y se sabe por qué. | Un lote grande tarda en confirmarse lo que tarda leer sus archivos. |
| Bolsa entrante del productor | Aceptar una bolsa BagIt de la dependencia · solo armarla aquí | **Solo armarla aquí** (delimitación) | Las dependencias de una entidad pequeña entregan papel o carpetas, no bolsas BagIt. Validar una bolsa entrante queda como trabajo futuro. | Un productor que sí entregue BagIt no tiene la verificación de origen a origen. |
| Lote obligatorio | Obligatorio · opcional | **Opcional** | La carga suelta (un archivo que aparece en el fondo) sigue existiendo. Una transferencia formal exige dependencia y acta. | Una transferencia cargada sin lote pierde su procedencia. La interfaz ofrece el lote en el mismo formulario. |
| Custodia anterior (ING-02 con DES-05) | Solo texto · relación de custodia | **Relación `hasOrHadHolder`** de la dependencia hasta la fecha del acta | Así la procedencia llega al RDF y a la ficha. No queda solo en una nota. | Si el acta no tiene fecha simple, el tramo queda sin fecha. |
| Revisor en la ingesta (ING-08) | Solo archivista y administrador · revisor con lectura | **Revisor con lectura** (se mantiene) | Quien revisa una descripción necesita ver de dónde vino el documento y en qué estado llegó, sin poder cambiarlo. Lo gobierna la tabla de roles, que el administrador puede ajustar. | Se aparta de la letra del prompt del módulo 1. Queda escrito aquí. |
| OCR intermitente (ING-09) | Reintentar la prueba · subir el límite de tiempo · un hilo por proceso | **Un hilo por proceso** (`OMP_THREAD_LIMIT=1`) | Se reprodujo la causa: con varios reconocimientos a la vez, los hilos de OpenMP compiten. Ocho reconocimientos tardaban 195 s; con un hilo tardan 0,8 s y dan el mismo resultado. Afecta igual al trabajador en producción. | Una sola página grande en un servidor ocioso puede tardar algo más que con varios hilos. Es aceptable frente a lo impredecible. |
| Dígitos sin precisar (DES-03) | Admitir nivel 2 y mostrarlo bien · rechazarlo | **Rechazar lo que no va «desde la derecha»** | El subconjunto declarado es el nivel 1. Admitir `1948-XX-12` perdía el día en la forma legible. | Quien conozca el día pero no el mes debe escribirlo como nota. Es un caso raro. |
| Elementos ISAD(G) sin dato del sistema (DES-07) | Columnas de texto · relaciones para todo · tabla única con fuente | **Tabla única** (`isadg.ELEMENTOS`): cada elemento sale del dato que el sistema ya tiene y se complementa con texto cuando no alcanza | Evita dos verdades: la forma de ingreso sale del lote, la valoración de la regla de retención, los originales de la instanciación física. El texto solo agrega lo que el sistema no sabe. | Once campos de texto más en la descripción. Se muestran plegados, como opcionales. |
| ISAD(G) en RiC-O (DES-07) | Inventar propiedades · `generalDescription` para todo · solo las que existen | **Solo las que existen** (`accruals`, `structure`, `generalDescription`, `physicalCharacteristicsNote`), y para el resto el motivo escrito | Ningún nombre inventado (regla del proyecto). El área 7 describe la descripción, no el documento, y RiC-O no la cubre. | Una exportación RiC-O no lleva la nota del archivero ni las reglas. La ficha ISAD(G) sí. |
| Recuperación del contexto del motor (DES-10) | Incrustaciones (vectores) · trigramas · trigramas con las otras formas del nombre | **Trigramas con las otras formas del nombre** | Las incrustaciones exigen un modelo y un servicio adicionales, posiblemente de pago (regla del proyecto). Las formas del nombre resuelven el caso real que señaló la auditoría (sigla, nombre antiguo) con lo que el archivista ya registra en la ficha de autoridad. | Un sinónimo que nadie registró como forma del nombre no se recupera. |
| Quién crea el fondo (DES-11) | Archivista · administrador | **Administrador** (se mantiene) | El fondo delimita el alcance de todo lo demás (permisos, vocabulario, instrumentos). Las secciones, series y expedientes sí los crea el archivista (CM-02). | Ninguno relevante. |

**Funciones de Ingest de OAIS (ISO 14721) que cubre el sistema (ING-06)**

| Función | Cubierta | Dónde |
|---|---|---|
| Recibir el envío (Receive Submission) | Sí | Lote de transferencia y carga |
| Asegurar la calidad (Quality Assurance) | Sí | Huella SHA-256, formato PRONOM, duplicados, OCR con confianza, comparación de huellas al confirmar |
| Acuse de recibo al productor | Sí | Acuse del lote (auditoría y descarga en JSON) |
| Generar el AIP | A demanda, en Preservación | El AIP BagIt con PREMIS se arma por instanciación o expediente cuando se pide. No es automático al ingresar: el AIP necesita la descripción, que llega después |
| Generar la información descriptiva | En Descripción | Fuera de la ingesta, por diseño del flujo |
| Coordinar las actualizaciones | Sí | Segunda copia al terminar la ingesta |
