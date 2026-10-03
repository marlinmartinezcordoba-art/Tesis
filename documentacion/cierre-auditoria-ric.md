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
