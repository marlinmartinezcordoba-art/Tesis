# Parametrización de la TRD y el CCD

## Qué se pidió

Que la tabla de retención documental (TRD) y el cuadro de clasificación (CCD)
se parametricen como en los sistemas de gestión documental electrónica de
archivo (SGDEA) que se usan en el país, y que el menú diga con claridad dónde
está cada cosa.

## De dónde sale el orden

Los manuales de ControlDoc y Mercurio no son públicos. Se tomó el orden que
piden los requisitos del Archivo General de la Nación para un SGDEA. Es el
mismo que sigue el manual público de la TRD de Orfeo:

1. Dependencias productoras (secciones y subsecciones) con su código.
2. Banco terminológico de series, subseries y tipos documentales.
3. Matriz de la TRD por dependencia: serie o subserie, tipos documentales,
   retención en archivo de gestión (AG) y central (AC), disposición final
   (CT, E, S, M), soporte y procedimiento.
4. Versión de la TRD: acto administrativo que la aprueba, convalidación y
   fecha desde la que rige. Las versiones anteriores se conservan.
5. Carga desde una plantilla o un archivo plano.

Fuentes:

- Modelo de requisitos para un SGDEA, AGN:
  https://www.archivogeneral.gov.co/caja_de_herramientas/docs/11.%20instrumentos/MODELO%20DE%20REQUISITOS%20PARA%20UN%20SGDEA.pdf
- Anexo técnico del modelo de requisitos, ANI:
  https://www.ani.gov.co/sites/default/files/230924-modelo-de-requisitos-sddea_anexo-tecnico.pdf
- Manual de la TRD en Orfeo:
  https://avante.gov.co/wp-content/uploads/2025/05/7.17.8-Manual-trd.pdf

## Todo parte de cargar los instrumentos

El recorrido empieza en **Fondos › 1. Cargar CCD y TRD**. Se carga el archivo del
cuadro y la tabla de retención (plantilla del sistema o formato del AGN, en Excel
o PDF) y el sistema configura, de una vez:

- el fondo (si es nuevo),
- las dependencias productoras (secciones y subsecciones),
- el banco de series, subseries y tipos documentales,
- la matriz de retención por dependencia,
- la versión de la TRD: vigente si se dio el acto que la aprueba, su fecha y la
  vigencia; si no, en borrador.

Al terminar, un resumen dice cuánto se configuró, con enlaces a los pasos de
ajuste manual (2. Dependencias, 3. Series, subseries y tipos, 4. Matriz) y a
5. Aplicar y versiones. Cada pantalla de ajuste lo recuerda: lo que muestra salió
de la carga, y los cambios valen al aplicar la versión.

Para un fondo que ya existe, «Una versión nueva de la TRD» abre el borrador de la
versión siguiente y lo llena con el archivo; la vigente sigue rigiendo hasta que
se aplique la nueva.

## Dónde está en el menú

**Fondos**

| Entrada                   | Qué se hace ahí                                                                  |
|---------------------------|----------------------------------------------------------------------------------|
| 1. Cargar CCD y TRD | El punto de partida: un fondo nuevo o una versión nueva, configurados desde el archivo. |
| 2. Dependencias | Ajuste manual de secciones y subsecciones con su código. |
| 3. Series, subseries y tipos | Ajuste manual del banco terminológico. |
| 4. Matriz de la TRD | Ajuste manual de la tabla de retención por dependencia. Se edita en el borrador y se consulta en las demás. |
| 5. Aplicar y versiones | Acto de aprobación, vigencia, validación en RiC-O y aplicación; historia de las versiones. |
| Cuadro de clasificación | El cuadro que resultó de aplicar la TRD. Solo consulta. |
| Fondos del archivo | Lista de fondos y elegir con cuál se trabaja. |

## Cómo queda en RiC

Las tablas de parametrización (`trd_versiones`, `trd_dependencias`,
`trd_banco`, `trd_filas`) son la mesa de trabajo. Lo que vale en RiC-O se crea
al aplicar una versión:

| Parametrización        | RiC-O                                                              |
|------------------------|--------------------------------------------------------------------|
| Dependencia            | `rico:RecordSet` de nivel sección o subsección; la dependencia como `rico:CorporateBody` productor |
| Serie y subserie       | `rico:RecordSet` (`rst:Series`), con su código compuesto           |
| Tipo documental        | `rico:DocumentaryFormType`                                         |
| Retención de una fila  | `rico:Rule` unida a su serie o subserie por `rico:regulatesOrRegulated`. La relación (`rico:RuleRelation`) lleva la vigencia de la versión. |

Aplicar una versión arma todo dentro de un punto de guardado. Después lo valida
contra la ontología oficial (OWL) y el perfil SHACL. Si no es conforme, se
deshace y no queda nada a medias.

## La retención cuando cambia la TRD

Supongamos que la versión 2 cambia la retención de una serie que en la
versión 1 era de 2 + 8 años y conservación total. Lo que pasa:

- La regla de la versión 1 no se borra ni se modifica. Su relación con la
  serie se cierra el día anterior a la vigencia de la versión 2, por ejemplo
  `2019-03-01/2024-06-30`.
- Se crea la regla de la versión 2, vigente desde su fecha, por ejemplo
  `2024-07-01/`.
- Cada expediente se rige por la regla vigente en su fecha final: la fecha
  en que se cerró, según sus fechas extremas.
  - Un expediente cerrado en 2021 conserva los 2 + 8 años.
  - Uno de 2025 toma la retención nueva.
  - Sin fechas, toma la vigente.

## Un solo camino para el cuadro

El cuadro de clasificación sale de la TRD aprobada. Por ningún otro camino se
crean secciones, subsecciones, series o subseries sueltas.

| Lo que se intenta | Qué pasa ahora |
|---|---|
| Registrar un fondo sin cuadro | No se puede. El fondo se registra en el asistente con su cuadro (Excel o PDF) y se valida en RiC-O antes de crearse. Si se da el acto que aprueba la TRD, su fecha y la vigencia, nace con la versión 1 vigente. Si no, la versión 1 queda en borrador. |
| Crear una sección, subsección, serie o subserie desde Descripción | Se rechaza. Solo la crea aplicar una versión de la TRD. Desde Descripción se crean expedientes y colecciones. |
| Describir varios documentos juntos como «serie» o «subserie» | Se rechaza. Varios documentos se describen como un expediente de su serie. |
| Publicar un documento o expediente suelto en el fondo o en una sección | En un fondo con cuadro se rechaza. Va dentro de una serie, una subserie o un expediente de ellas. |
| Renombrar, recodificar o mover una serie desde su descripción | Se rechaza. Se hace con una versión nueva de la TRD. El alcance, la historia y las entidades sí se describen. |
| Crear una regla de retención suelta, unirla a otra serie, desunirla o cambiarle los años y la disposición en Autoridades y términos | Se rechaza. La retención la fija la TRD. En la ficha de la regla solo se completa el texto del procedimiento. |
| Aplicar un cuadro directo desde un archivo, sin versión | Se retiró. El archivo se carga en una versión de la TRD (Versiones de la TRD › Cargar desde archivo). |

Las colecciones (rst:Collection) sí se crean a mano. No son parte del cuadro
orgánico: reúnen documentos por pertenencia adicional sin sacarlos de su
serie.

## Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Orden de los pasos | Copiar una pantalla de un producto comercial; seguir el modelo de requisitos del AGN | Requisitos del AGN, con el orden del manual público de Orfeo | Los manuales de ControlDoc y Mercurio no son públicos. El AGN es la norma que esos productos cumplen. | Diferencias de nombres frente a lo que la autora usa en su trabajo. Se pueden ajustar sin cambiar el modelo. |
| Dónde viven los pasos | Pestañas dentro de una pantalla; entradas del menú lateral | Entradas del menú Fondos | Las pestañas se habían quitado del sistema (R1). Cada paso queda con nombre propio y su dirección. | Menú más largo en Fondos (seis entradas). |
| Versiones de la TRD | Editar la TRD vigente; versiones con borrador, vigente e histórica | Versiones; un borrador a la vez | El AGN pide conservar las TRD anteriores con su acto de aprobación. Editar en sitio borraría la historia. | Hay que abrir una versión nueva para cualquier cambio, aunque sea pequeño. La versión nueva copia la vigente para aliviarlo. |
| Retención que cambia | Sobrescribir la regla; regla nueva con vigencia y la anterior cerrada | Regla nueva fechada; la anterior se cierra, no se borra | Cada expediente se valora con la TRD con que se produjo. En RiC-O la vigencia de la relación es nativa (`rico:RuleRelation` con fecha). | Un expediente sin fechas extremas toma la regla vigente. |
| Qué fecha decide la versión | Fecha inicial; fecha final del expediente | Fecha final (cierre) | La retención se cuenta desde el cierre del expediente en el archivo de gestión. | Expedientes abiertos que cruzan dos versiones toman la de su fecha final conocida. |
| Requisitos para aplicar | Aplicar sin acto; exigir acto, fecha de aprobación y vigencia | Exigir los tres | Sin acto administrativo la TRD no es válida. Sin vigencia no se pueden fechar las reglas. | Validar sí funciona sin ellos, y la pantalla dice qué falta. |
| Banco terminológico | Nombres libres en cada fila; banco único del fondo | Banco del fondo con código propio | Una serie (Actas, 2) se usa en varias dependencias con el mismo nombre normalizado. El código compuesto (110.2) sale solo. | Una entidad que use códigos de serie distintos por dependencia registra términos distintos. |
| Tablas de parametrización en el grafo | Llevarlas a RiC-O; dejarlas como mesa de trabajo | Mesa de trabajo; lo aplicado es RiC-O | Las filas en borrador no son descripción archivística. Lo aplicado (agrupaciones, reglas, tipos, productor) sí está en el grafo. | La versión como acto administrativo se lee en la descripción de cada regla, no como entidad propia del grafo. |
| Registro del fondo con su TRD | Pedir el acto en el asistente; dejar la versión 1 en borrador | Versión 1 en borrador | El asistente ya es largo. El acto se completa después y, al aplicarla, fecha las reglas que se crearon. | Un fondo puede quedar con la versión 1 sin aplicar. La pantalla y el aviso del asistente lo dicen. |
| Nada se borra | Borrar dependencias o términos sin uso; anularlos | Anular | Regla del proyecto. Lo usado en el borrador no se anula hasta quitarlo de la matriz. Los códigos usados en una TRD aplicada no cambian. | Quedan registros anulados en las tablas. |
| Cuadro solo desde la TRD | Dejar crear series en Descripción; crearlas solo al aplicar la TRD | Solo desde la TRD | Evita series sueltas, con nombres o códigos que no están en la tabla aprobada. Es el control que piden los requisitos del AGN para un SGDEA. | Una serie que falta en la TRD obliga a abrir una versión nueva. Es lo correcto en la norma, aunque sea más lento. |
| Fondo sin cuadro | Permitirlo; exigir el cuadro al registrar | Exigirlo | Sin cuadro, los documentos quedarían sueltos en el fondo. Un fondo histórico sin TRD registra igual su cuadro, sin las columnas de retención. | Un fondo acumulado sin cuadro reconstruido no se puede registrar todavía. Hay que levantar primero el cuadro. |
| Documentos sueltos en un fondo con cuadro | Permitirlos; exigir serie o subserie | Exigirla | Todo documento tiene un lugar en el cuadro: es lo que hace posible heredar la retención. | Los fondos anteriores a este cambio sin series no se ven afectados. |
| Reglas de retención en Autoridades y términos | Editables; solo consulta | Solo consulta (salvo el texto del procedimiento) | Una retención cambiada fuera de la TRD no tendría acto que la respalde. | Corregir un error de digitación exige una versión nueva de la TRD. |
| Punto de partida | Pantallas sueltas (dependencias, series, matriz) llenadas a mano; cargar los instrumentos y ajustar después | Cargar primero; ajustar a mano después | Así trabaja un archivo: el CCD y la TRD ya existen aprobados y se cargan. El ajuste manual corrige lo que el archivo no traía o se leyó mal. | Un PDF mal escaneado obliga a corregir más a mano. La vista previa marca las filas con problemas antes de cargar. |
| Quién parametriza | Archivista; administración | Administración (consulta: quien lee la descripción) | La TRD es un instrumento aprobado por la entidad, no una descripción. | La autora puede querer abrirlo a un rol de archivo. Se cambia en los permisos. |

## Pruebas

`tests/test_parametrizacion_trd.py`:

- Parametrizar, validar sin crear, exigir el acto y la vigencia, y aplicar
  conforme con RiC-O.
- Una versión nueva cierra la regla anterior. Cada expediente toma la regla
  de su fecha.
- El archivo de la TRD llena el borrador sin duplicar.
- Solo la administración parametriza, y lo que está en uso no se anula.
- La versión 1 fecha las reglas que se cargaron antes de la parametrización.
