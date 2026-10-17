# Catalogación y metadatos: tesauros, guía de campos y documentos cargados por error

**Versión:** 2 (agrega el cuadro de clasificación y la TRD).
**Pedido de la autora:**
- fortalecer la descripción desde la catalogación y los metadatos;
- usar tesauros (el de la UNESCO y el ambiental de Minambiente) para normalizar;
- que cada etiqueta explique por qué es relevante y cómo se relaciona con lo demás;
- eliminar los documentos cargados por error (solo la administración, si nunca se describieron, con constancia);
- leer Excel y PDF.

- parametrizar el cuadro de clasificación (CCD) y la tabla de retención (TRD), en Excel o PDF, para que el sistema sepa a qué fondo, sección y serie pertenece cada documento.

## 1. Tesauros y materias

### Qué hace

- **Importar un tesauro** (solo la administración), en uno de dos formatos:
  - **SKOS** (Turtle, RDF/XML, N-Triples o JSON-LD), como el Tesauro de la UNESCO, que se descarga libre (licencia CC BY-SA 3.0 IGO).
  - **Tabla Excel o CSV**, para un tesauro que no publica SKOS, como el ambiental de Minambiente. Columnas:
    - Término preferente;
    - Usado por (términos no preferentes, separados por «;»);
    - Término general;
    - Nota de alcance;
    - URI;
    - Código.

  Toma las etiquetas en español, omite los conceptos retirados (`owl:deprecated`) y une cada concepto con su término general. El mismo archivo no se importa dos veces (huella SHA-256).
- **Normalizar un término.** Se compara sin tildes ni mayúsculas:
  - Si es el **preferente**, se usa tal cual.
  - Si es **no preferente** («archivos históricos»), lleva al preferente («Archivo histórico»).
  - Si no coincide con ninguno, se ofrecen los **parecidos** (trigramas). Si tampoco hay parecidos, queda como **término local** del fondo, marcado como tal.
- **Materia** es una clase nueva del vocabulario del fondo: `rico:Concept`, y además `skos:Concept`.
  - Hay una sola materia por concepto y por fondo, así que dos documentos con el mismo tema, escrito distinto, llegan al **mismo nodo del grafo**.
  - Se une al documento con la relación «Materia»: `rico:hasOrHadSubject`, rol `materia`.
  - Al exportar, lleva `skos:exactMatch` hacia el concepto de origen; la exportación sigue siendo conforme con el OWL y con el SHACL.
- **Constancia.** Toda normalización (lo escrito y el término preferente que quedó) se registra en la auditoría como «Normalizó una materia con un tesauro».
- **Anular un tesauro.** No se borra. Deja de ofrecerse para normalizar, y las materias ya normalizadas conservan su concepto.

### Dónde está

- **Vocabularios › Tesauros:**
  - los tesauros importados;
  - un probador de la normalización;
  - el formulario de importación.
- **Descripción** (agregar o corregir una entidad): el tipo «Materia (tema)». Mientras se escribe, sugiere el término preferente o los parecidos.
- **Línea de comandos:** `python -m app.cli importar-tesauro <archivo o URL>`. El servidor de producción tiene internet y puede descargar el SKOS de la UNESCO directamente.

### Lo que no se pudo hacer desde aquí

- La red de este entorno de desarrollo no llega a vocabularies.unesco.org ni a bibliovirtual.minambiente.gov.co, así que no se importó ninguno de los dos tesauros reales; se probó con muestras.
- El tesauro de Minambiente es una página para navegar, no un archivo descargable. Para cargarlo hay que pasarlo a la tabla Excel de arriba, o pedir el archivo a la entidad.
- En los dos casos, revise la licencia antes de importar.

## 2. Guía de los campos

- **Cada campo de la descripción** tiene un ⓘ que dice:
  - **qué es**, **por qué importa** y **con qué se relaciona**;
  - un **ejemplo**;
  - sus normas: elemento ISAD(G), propiedad RiC-O, cardinalidad y fila del Esquema de Metadatos del AGN.

  Ejemplo: el título cita la AGN-REC-02 (obligatorio) y la AGN-FUID-02.
- **Cada tipo de entidad** (agente, lugar, fecha, actividad, función, norma, forma documental, materia) tiene la misma ayuda en el formulario.
- **Una sola fuente:** el texto está en `app/servicios/guia_metadatos.py`.
  - ISAD(G) y RiC-O salen del catálogo de atributos.
  - El AGN sale del perfil (`perfil_agn.py`), por el campo del sistema. Una fila puede cubrir varios campos: el volumen documental cubre folios, caja y carpeta.
  - Una prueba exige que ningún campo ni tipo de entidad quede sin explicación.
- **API:** `GET /api/descripcion/guia`.

## 3. Documentos cargados por error

- **Quién y dónde:** solo la administración, con el botón «Eliminar» de «Por describir». Pide el motivo, de 5 caracteres o más.
- **Cuándo se puede:** solo si el documento **nunca se describió**. Se rechaza (409, con la razón) en estos casos:
  - ya fue descrito, aunque después se anulara: es parte del fondo y su retiro va por valoración, con TRD y acta;
  - alguien lo está describiendo;
  - está en una evaluación ciega;
  - tiene versiones derivadas o recortes;
  - tiene migración, segunda copia o restauración;
  - es el acta de un lote de transferencia.
- **Qué se borra:** el registro y el archivo, de forma definitiva. Con ellos se van las verificaciones técnicas que el sistema hizo solo sobre ese archivo.
- **Qué queda en la auditoría encadenada** («Eliminó un documento cargado por error»):
  - nombre, tamaño, huella SHA-256 y formato;
  - fondo y fecha de carga;
  - quién lo eliminó, cuándo y el motivo.

## 4. Excel y PDF en la ingesta

- **PDF:** ya se leía (capa de texto u OCR).
- **Excel** (`.xlsx`, `.xlsm`): ahora se extrae el texto de cada hoja, fila por fila, con el nombre de la hoja y las celdas separadas por « | ». Así un inventario o un FUID en Excel se puede buscar y describir. Un Excel dañado o protegido queda como error legible.

## 5. Cuadro de clasificación (CCD) y tabla de retención (TRD)

### Qué hace

- **Dos formas de cargarlo** (solo la administración), en **Instrumentos › Cuadro de clasificación y TRD**:
  - **La plantilla Excel del sistema.** Se descarga desde la misma pantalla. Una fila por serie o subserie, con estas columnas:
    - código y nombre de la sección (dependencia), de la subsección, de la serie y de la subserie;
    - tipos documentales, separados por «;»;
    - retención en archivo de gestión (AG) y en archivo central (AC), en años;
    - disposición final: CT, E, S, M (se marca con «X»);
    - procedimiento;
    - función (tipo de actividad) que produce la serie.

    Una celda vacía repite el valor de la fila de arriba, como se diligencia a mano.
  - **La TRD en el formato habitual del AGN**, en Excel o en PDF:
    - columnas D, S y Sb;
    - la columna «Series, subseries y tipos documentales», con la serie en mayúsculas y sus tipos debajo, sin código;
    - AG y AC; CT, E, M y S; procedimiento.

    La dependencia sale del encabezado («Dependencia productora: 110 Secretaría General»).
- **Vista previa obligatoria.** El sistema muestra fila por fila lo que entendió: sección, serie, subserie, códigos, tipos, tiempos y disposición. Las filas con problemas quedan en rojo y no se pueden marcar. Por ejemplo:
  - una serie sin nombre;
  - retención sin disposición final;
  - años que no son número.

  **Nada se crea hasta que la administración confirma**, y puede desmarcar las filas que no quiera.
- **Al confirmar** se crea, todo o nada:
  - la **sección** (y subsección), unida a la dependencia como **agente productor** (`rico:hasCreator`);
  - la **serie** y la **subserie**, con **código compuesto** (sección 110, serie 110.2, subserie 110.2.1), anidadas con `rico:isOrWasIncludedIn`;
  - la **regla de retención** de la TRD, unida a la serie o subserie que regula; los expedientes la **heredan**;
  - los **tipos documentales** en el vocabulario de formas documentales;
  - la **función**, unida a la serie que produce.
- **Repetir la carga no duplica.** Lo que ya existe con el mismo código se reutiliza y el informe lo dice: «N nivel(es) que ya existían». Si un código ya pertenece a otro nivel (por ejemplo, una serie que en el archivo es sección), se rechaza todo.
- **Constancia:** «Cargó el cuadro de clasificación y la TRD» en la auditoría, con el conteo de lo creado.

### Cómo se usa después

- **Ingesta:** primero se elige la **serie o subserie** del cuadro (con su ruta: sección › serie › subserie). El expediente de destino se filtra por esa serie, y allí mismo se puede crear un expediente nuevo («+ Nuevo expediente en esta serie»). Así, cada documento sabe desde la carga a qué fondo, sección y serie pertenece.
- **Instrumentos:** el árbol del cuadro muestra la retención y la disposición de cada nivel y cuántos expedientes tiene cada serie.
- **Exportación RiC-O:** las agrupaciones del cuadro son `rico:RecordSet` con su tipo (sección, serie, subserie). La exportación sigue siendo conforme con el OWL y con el SHACL.

### Límites (para tener presentes)

- **La lectura del PDF es aproximada.** Funciona con PDF que tienen capa de texto y tabla con líneas (como los que exporta Word o Excel). Una TRD **escaneada** no se lee: hay que pasarla a la plantilla Excel. Por eso la vista previa es obligatoria.
- **Cada TRD tiene su propia diagramación.** Si una entidad usa columnas distintas a las del formato del AGN, se recomienda la plantilla del sistema.
- **Fuera del alcance de la tesis.** El cuadro y la TRD son gestión documental (archivo de gestión y central); la tesis trata la descripción de archivos históricos. Aquí sirven para ubicar cada documento en su contexto de producción. Para un fondo histórico **sin TRD**, el cuadro puede reconstruirse con la plantilla, a partir de la organización del fondo (o de la Tabla de Valoración Documental, TVD), dejando vacías las columnas de retención.

## 6. Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Dónde vive el tesauro | En el vocabulario de cada fondo; **tablas propias compartidas** | **Compartidas** | Un tesauro es un instrumento externo, el mismo para todos los fondos; copiarlo en cada uno multiplicaría miles de conceptos | Ninguno: la materia del fondo sí es del fondo y apunta al concepto |
| Cómo se carga | Consulta en línea a la UNESCO; **importar archivos (SKOS, Excel, CSV)** | **Importar** | No depende de que un sitio externo esté disponible; sirve para tesauros sin SKOS; la versión importada queda fija y auditada | Hay que reimportar cuando el tesauro publica una versión nueva (se anula la anterior) |
| Qué se normaliza | Agentes, lugares y todo; **las materias (temas)** | **Materias** | Los agentes y los lugares ya tienen control de autoridades (verificación de parecidos y fusión). El tema era lo que faltaba (AGN-FUID-14 «Palabras clave o temas») | Si el fondo necesita normalizar lugares con un tesauro geográfico, es otro paso |
| Término que no está en el tesauro | Rechazarlo; **dejarlo como término local** | **Local, marcado** | Ningún tesauro cubre todo un archivo histórico; rechazar obligaría a forzar un término que no corresponde | Términos locales que se dupliquen: los ataja la misma verificación de parecidos del vocabulario |
| Clase en RiC-O | rico:Thing; **rico:Concept + skos:Concept** | **Concept** | RiC-O 1.1 tiene rico:Concept («una idea… o categoría»), que admite hasOrHadSubject; SKOS permite el exactMatch | Ninguno: la exportación pasa el OWL y el SHACL |
| Eliminar un documento | Retiro lógico; **borrado real con constancia** | **Borrado real** (decisión de la autora) | Un archivo cargado por error nunca fue documento del fondo; la constancia (nombre, huella, quién, cuándo y por qué) queda en la auditoría, que no se puede alterar | Un borrado equivocado no se deshace. Por eso solo la administración puede borrar, con motivo, y nunca lo ya descrito |
| Formato de carga del CCD y la TRD | Solo plantilla propia; solo el formato del AGN; **los dos** | **Los dos** (pedido de la autora) | La plantilla es exacta y no depende de la diagramación; el formato del AGN es el que ya tienen las entidades | El formato del AGN varía entre entidades: lo que no se entienda aparece marcado en la vista previa |
| Lectura del PDF | OCR de la tabla; **texto y líneas de la tabla (pdfplumber, libre)** | **Texto y líneas** | Exacto en los PDF que exporta Word o Excel; sin servicios de pago | Un PDF escaneado no se lee; se pide la plantilla |
| Crear directamente o revisar primero | Crear al subir; **vista previa y confirmación** | **Vista previa** | Un cuadro mal leído crearía series equivocadas en el fondo, y estas no se borran (solo se anulan) | Un paso más para la administración |
| Fallas en una carga | Crear lo que se pueda; **todo o nada** | **Todo o nada** | Un cuadro a medias deja series sin su sección o sin su regla, y es difícil de detectar | Un solo error detiene la carga: el mensaje dice qué fila y por qué |
| Identidad de cada nivel | El nombre; **el código** | **Código** (y, si no hay código, el nombre bajo el mismo nivel superior) | El código es lo que la TRD fija; los nombres cambian de una versión a otra | Si una nueva versión de la TRD **cambia** códigos, crea niveles nuevos; los anteriores no se anulan solos |
| Dónde va la retención | En el expediente; **en la serie o subserie** | **Serie o subserie, heredada** | Así funciona la TRD: regula la serie, no cada expediente | Ninguno: el expediente puede tener una regla propia si hace falta |
| La guía de campos | Textos en la pantalla; **una fuente en el servidor** | **Servidor** | El mismo texto sirve a la pantalla, a la documentación y a las pruebas; las normas salen de los catálogos, no se copian | La autora debe revisar los textos: son una propuesta archivística |

## 7. Pruebas

| Archivo | Qué comprueba |
|---|---|
| `tests/test_tesauros.py` (5) | Importar SKOS (español, retirados, término general, sin repetir); importar Excel y CSV; normalización (sin tildes, no preferente → preferente, parecidos); la materia normalizada al publicar es un solo nodo para dos documentos; término local; exportación conforme con exactMatch; elegir el concepto; anular sin cambiar lo descrito |
| `tests/test_guia_metadatos.py` (2) | Ningún campo ni tipo de entidad sin explicación; la guía une cada campo con ISAD(G), RiC-O y el AGN (también varios campos por fila) |
| `tests/test_eliminar_documento.py` (4) | Solo la administración, con motivo; queda la constancia; no se elimina lo descrito, lo que está en edición ni lo que está en una evaluación; lectura de Excel y de un Excel dañado |
| `tests/test_cuadro.py` (4) | La TRD del AGN en Excel y en PDF se entiende igual (códigos compuestos, tipos, AG/AC, CT + M); la plantilla se descarga y se lee; aplicar crea secciones, series, subseries, reglas, tipos y productor, y al repetir reutiliza sin duplicar; el árbol; exportación conforme; todo o nada; solo la administración carga |
| `tests/test_terminos.py` | El término «Materia» está en el vocabulario único de relaciones |
