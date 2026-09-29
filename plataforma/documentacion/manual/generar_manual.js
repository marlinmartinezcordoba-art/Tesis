const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, ImageRun, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, LevelFormat, TableOfContents, PageBreak, Footer, Header, PageNumber,
} = require("docx");

const DIR = __dirname;
const guias = JSON.parse(fs.readFileSync(path.join(DIR, "guias.json"), "utf8"));
const G = Object.fromEntries(guias.map((g) => [g.clave, g]));
const turtle = fs.readFileSync(path.join(DIR, "ejemplo.ttl"), "utf8").trim().split("\n");

const AZUL = "2F5FD0", NARANJA = "C2410C", GRIS = "515B6D", FONDO = "E8EDF7", FONDO2 = "F3F5F9";
const ANCHO = 9360; // carta con márgenes de 1": 6,5 pulgadas

// ---- utilidades --------------------------------------------------------
const numeraciones = [];
let nLista = 0;
function t(texto, op = {}) { return new TextRun({ text: texto, ...op }); }
// texto con **negritas** simples
function rico(texto, op = {}) {
  return texto.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((s) =>
    s.startsWith("**") ? new TextRun({ text: s.slice(2, -2), bold: true, ...op }) : new TextRun({ text: s, ...op }));
}
function p(texto, op = {}) { return new Paragraph({ children: rico(texto), spacing: { after: 120, line: 300 }, ...op }); }
function h1(texto) { return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [t(texto)], pageBreakBefore: true }); }
function h2(texto) { return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [t(texto)] }); }
function h3(texto) { return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [t(texto)] }); }
function vinetas(items) {
  return items.map((x) => new Paragraph({ children: rico(x), numbering: { reference: "vinetas", level: 0 }, spacing: { after: 80, line: 290 } }));
}
function pasos(items) {
  const ref = `pasos-${nLista++}`;
  numeraciones.push({ reference: ref, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] });
  return items.map((x) => new Paragraph({ children: rico(x), numbering: { reference: ref, level: 0 }, spacing: { after: 80, line: 290 } }));
}
function nota(etiqueta, texto, color = NARANJA) {
  return new Paragraph({
    children: [t(etiqueta + " ", { bold: true, color }), ...rico(texto)],
    shading: { type: ShadingType.CLEAR, fill: FONDO2, color: "auto" },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color, space: 8 } },
    spacing: { before: 80, after: 160, line: 290 }, indent: { left: 120, right: 120 },
  });
}
function imagen(archivo, pie) {
  const ruta = path.join(DIR, archivo);
  if (!fs.existsSync(ruta)) return [];
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(ruta), transformation: { width: 600, height: 351 },
        altText: { title: pie, description: pie, name: archivo } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [t(pie, { italics: true, size: 18, color: GRIS })] }),
  ];
}
const borde = { style: BorderStyle.SINGLE, size: 4, color: "C9D1DE" };
const bordes = { top: borde, bottom: borde, left: borde, right: borde };
function tabla(anchos, filas, encabezado = true) {
  return new Table({
    width: { size: ANCHO, type: WidthType.DXA }, columnWidths: anchos,
    rows: filas.map((fila, i) => new TableRow({
      tableHeader: encabezado && i === 0,
      children: fila.map((celda, j) => new TableCell({
        borders: bordes, width: { size: anchos[j], type: WidthType.DXA },
        shading: encabezado && i === 0 ? { type: ShadingType.CLEAR, fill: AZUL, color: "auto" } : (i % 2 === 0 ? { type: ShadingType.CLEAR, fill: FONDO2, color: "auto" } : undefined),
        margins: { top: 70, bottom: 70, left: 110, right: 110 },
        children: String(celda).split("\n").map((linea) => new Paragraph({ spacing: { after: 40, line: 264 },
          children: encabezado && i === 0 ? [t(linea, { bold: true, color: "FFFFFF", size: 19 })] : rico(linea, { size: 19 }) })),
      })),
    })),
  });
}
function codigo(lineas) {
  return lineas.map((l, i) => new Paragraph({
    children: [t(l || " ", { font: "Courier New", size: 17 })],
    shading: { type: ShadingType.CLEAR, fill: "EEF1F6", color: "auto" }, spacing: { after: 0, line: 240 },
    indent: { left: 200, right: 200 }, keepLines: true,
  }));
}
function espacio() { return new Paragraph({ children: [t("")], spacing: { after: 60 } }); }

// Sección del manual a partir de la guía de ayuda de la propia plataforma
function seccionManual(clave, capturas = [], extra = []) {
  const g = G[clave];
  const out = [h3(g.titulo), p("**Para qué sirve.** " + g.para_que), p("**Cómo se usa:**")];
  out.push(...pasos(g.pasos));
  if (g.consejos && g.consejos.length) out.push(...g.consejos.map((c) => nota("Tenga en cuenta:", c)));
  out.push(...extra);
  capturas.forEach(([archivo, pie]) => out.push(...imagen(archivo, pie)));
  return out;
}

// ---- contenido ---------------------------------------------------------
const hijos = [];

// Portada
hijos.push(
  new Paragraph({ spacing: { before: 1800 }, alignment: AlignmentType.CENTER, children: [t("RIC", { bold: true, size: 72, color: AZUL }), t("ORA", { bold: true, size: 72, color: "EA7A2E" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 }, children: [t("Plataforma de gestión y descripción archivística basada en Records in Contexts", { size: 26, color: GRIS })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [t("Manual de usuario", { bold: true, size: 40 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 800 }, children: [t("y aplicación del modelo RiC-CM 1.0 / RiC-O 1.1 en la plataforma", { size: 28 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [t("Marlín Jhaneth Martínez Córdoba", { bold: true, size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [t("Maestría en Gestión de la Información Documental", { size: 22, color: GRIS })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [t("Documento de avance para tutoría · septiembre de 2026", { size: 22, color: GRIS })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [t("Plataforma en línea: http://159.89.95.122/", { size: 22, color: AZUL })] }),
  new Paragraph({ children: [new PageBreak()] }),
  new Paragraph({ heading: HeadingLevel.HEADING_1, children: [t("Contenido")] }),
  new TableOfContents("Contenido", { hyperlink: true, headingStyleRange: "1-2" }),
);

// Parte I
hijos.push(
  h1("1. Qué es RICORA"),
  p("RICORA es una plataforma web de gestión y descripción archivística construida sobre el modelo conceptual **Records in Contexts (RiC-CM 1.0)** y su ontología **RiC-O 1.1**, publicados por el Consejo Internacional de Archivos (ICA-EGAD). Su propósito es que la descripción de un documento no sea una ficha aislada sino una **red de contexto**: quién lo produjo, a quién se refiere, en qué función o actividad se originó, cuándo, dónde y bajo qué norma, con cada vínculo expresado como una entidad y una relación RiC."),
  p("La plataforma combina tres elementos:"),
  ...vinetas([
    "**Instrumentos archivísticos como punto de partida:** la Tabla de Retención Documental (TRD), el cuadro de clasificación y el organigrama se cargan una vez y se convierten en entidades RiC (mandatos, actividades, entidades corporativas, cargos). Todo documento entra ya clasificado por serie y expediente.",
    "**Inteligencia artificial asistida:** un motor de análisis lee el texto del documento y propone las entidades y relaciones RiC que encuentra, **siempre con la cita textual que lo respalda**. La IA propone; la persona decide.",
    "**Control archivístico humano:** cada propuesta se acepta, se corrige o se rechaza con motivo; luego hay una segunda revisión ficha por ficha antes de publicar. Nada se publica sin revisar y nada se borra de forma irreversible.",
  ]),
  h2("1.1 Principios de diseño"),
  tabla([2600, 6760], [
    ["Principio", "Cómo se cumple en la plataforma"],
    ["La IA propone, la persona decide", "Toda propuesta queda pendiente hasta que una persona la acepta, corrige o rechaza; ninguna decisión archivística es automática."],
    ["Evidencia verificable", "Cada propuesta trae el fragmento literal del documento; el sistema comprueba que ese texto exista en la página antes de aceptarla (criterio CC-01)."],
    ["Integridad", "Cada archivo recibe su huella digital SHA-256 al cargarse; los eventos de descripción se encadenan con hash, de modo que cualquier alteración se detecta."],
    ["Nada se borra", "Todo retiro es un borrado lógico con motivo, restaurable desde Administración → Eliminados; cada cambio guarda su versión anterior."],
    ["Acceso según la ley", "Lo reservado o sin publicar no se muestra al rol de consulta (Ley 1712 de 2014, Ley 1581 de 2012)."],
  ]),
  h2("1.2 Estado del avance"),
  p("El desarrollo se organizó por módulos, cada uno cerrado con su Definición de Terminado, su documentación de 23 puntos y la validación de la autora antes de pasar al siguiente."),
  tabla([900, 4060, 4400], [
    ["Módulo", "Nombre", "Estado"],
    ["M0", "Autenticación, autorización y auditoría", "Validado"],
    ["M1", "Ingesta y visor documental", "Validado"],
    ["M2", "Preprocesamiento y OCR", "Validado"],
    ["M3", "Motor de análisis RiC", "Construido y en uso; sin revisión formal con la metodología"],
    ["M4", "Modelado de relaciones", "Construido y en uso; sin revisión formal con la metodología"],
    ["M5", "Vocabularios y autoridades", "Construido y en uso; sin revisión formal con la metodología"],
    ["M6", "Revisión archivística", "Validado"],
    ["M7", "Trazabilidad", "Validado"],
    ["M8", "Catálogo y consulta", "Validado"],
    ["M9", "Exportación e interoperabilidad", "Validado"],
    ["M10", "Panel de indicadores", "Validado"],
    ["M11", "Administración y seguridad", "Entregado, pendiente de validación"],
  ]),
  espacio(),
  p("La plataforma cuenta con **625 pruebas automatizadas** que se ejecutan completas antes de cada publicación, y está desplegada en un servidor propio (Django 5.2 y PostgreSQL, con cola de procesamiento para el OCR y una IA local de respaldo), sin servicios pagos adicionales."),
);

// Parte II · Manual
hijos.push(
  h1("2. Manual de usuario"),
  p("Este manual sigue el recorrido de un documento por el proceso archivístico. Los pasos de cada pantalla son los mismos que la plataforma muestra en su ayuda integrada, de modo que el manual y el sistema dicen lo mismo."),
  h2("2.1 Ingreso y recuperación de la contraseña"),
  ...pasos([
    "Abra la plataforma en el navegador. Aparece la pantalla de ingreso con la presentación de RICORA a la izquierda.",
    "Escriba su **usuario** y su **contraseña**; con «Mostrar» puede ver lo que escribió. Pulse **Entrar**.",
    "Si olvidó la contraseña, pulse **«¿Olvidó su contraseña?»**, escriba su usuario o su correo y pulse «Pedir restablecimiento». Recibirá un enlace (por correo, o por medio del administrador si el servidor no tiene correo configurado) para crear una contraseña nueva.",
    "Las personas nuevas no reciben una contraseña: reciben un **enlace de invitación** de un solo uso con el que crean la suya.",
  ]),
  nota("Seguridad:", "la sesión se cierra tras 60 minutos sin actividad y la cuenta se bloquea 15 minutos después de 5 intentos fallidos. Todo queda en la auditoría."),
  ...imagen("01_ingreso.png", "Figura 1. Pantalla de ingreso."),
  h2("2.2 Cómo está organizada la pantalla"),
  ...vinetas([
    "**Menú lateral (izquierda):** los procesos archivísticos en orden — Instrumentos archivísticos, Captura y clasificación, Descripción, Valoración y disposición, Consulta y exportación, Indicadores y Administración. Cada proceso se despliega con un clic y muestra sus pantallas.",
    "**Barra superior:** buscador del catálogo (atajo Ctrl K), fecha y hora, y su nombre con su rol. Al pulsar su nombre aparece «Cerrar sesión».",
    "**Ambulancia (abajo a la derecha):** abre la ayuda de la pantalla en la que usted está, paso a paso («Paso 1 de N»).",
    "**Rutas de un documento:** en las pantallas de un documento, una barra de pasos (Captura → Preproceso y OCR → Motor de análisis → Relaciones → Revisión archivística → Catálogo) muestra en qué etapa va.",
  ]),
  ...imagen("22_ayuda.png", "Figura 2. La ambulancia abre la ayuda de cada pantalla, un paso a la vez."),
  h2("2.3 Roles"),
  p("Cada cuenta tiene **exactamente uno** de los cuatro roles. El menú solo muestra lo que el rol puede usar y el servidor niega cualquier otra acción (queda registrada como acceso denegado)."),
  tabla([1800, 7560], [
    ["Rol", "Qué puede hacer"],
    ["Archivista", "Carga y preprocesa documentos, decide las propuestas de la IA, modela relaciones, aprueba y publica."],
    ["Revisor", "Revisa ficha por ficha, aprueba y publica o rechaza con motivo; no carga documentos."],
    ["Consulta", "Consulta el catálogo publicado y de acceso abierto, exporta y ve los indicadores."],
    ["Administrador", "Todo lo anterior, más usuarios, proveedores de IA, parámetros, auditoría y eliminados."],
  ]),
  h2("2.4 Inicio"),
  ...seccionManual("inicio", [["02_inicio.png", "Figura 3. Inicio: «Mi trabajo de hoy», «Requieren atención», cifras y últimos documentos."]]),
  h2("2.5 Instrumentos archivísticos"),
  ...seccionManual("vocabularios", [["03_vocabularios.png", "Figura 4. Vocabularios y autoridades, por clase de entidad RiC."]]),
  ...seccionManual("vocabularios_duplicados"),
  h2("2.6 Captura y clasificación"),
  ...seccionManual("ingesta", [["04_ingesta.png", "Figura 5. Carga por serie de la TRD → expediente → archivos."]]),
  ...seccionManual("preproceso", [["05_preproceso.png", "Figura 6. Preprocesamiento y OCR con su estado."]]),
  h2("2.7 Descripción"),
  ...seccionManual("analisis_lista", [
    ["07_analisis.png", "Figura 7. Análisis: el texto con las menciones resaltadas y, a la derecha, las fichas propuestas con su relación RiC, su confianza y su cita."],
    ["08_grafo.png", "Figura 8. Modelado de relaciones: el documento al centro y sus entidades, cada línea con su relación RiC-O."],
  ]),
  ...seccionManual("revision_lista", [["10_revision.png", "Figura 9. Revisión archivística ficha por ficha: a la izquierda lo propuesto, a la derecha la decisión."]]),
  ...seccionManual("historial_lista", [["11_historial.png", "Figura 10. Trazabilidad: línea de tiempo con la cadena de eventos verificada."]]),
  h2("2.8 Valoración y disposición"),
  ...seccionManual("valoracion", [["12_valoracion.png", "Figura 11. Expedientes con su fase y su retención heredada de la TRD."]]),
  ...seccionManual("valoracion_transferencias", [["13_transferencias.png", "Figura 12. Listas de transferencia primaria y de disposición final."]]),
  ...seccionManual("valoracion_fuid"),
  h2("2.9 Consulta y exportación"),
  ...seccionManual("catalogo", [["14_catalogo.png", "Figura 13. Catálogo: búsqueda por documentos, personas, instituciones, fechas y lugares."]]),
  ...seccionManual("exportar", [
    ["16_exportar.png", "Figura 14. Exportación en RiC-O (Turtle, RDF/XML), JSON-LD y CSV, con su registro."],
    ["17_sparql.png", "Figura 15. Consultas SPARQL sobre el grafo RiC."],
  ]),
  h2("2.10 Indicadores"),
  ...seccionManual("panel", [["18_panel.png", "Figura 16. Panel de indicadores por periodo; cada cifra lleva a su lista."]]),
  h2("2.11 Administración"),
  ...seccionManual("admin_usuarios", [["19_usuarios.png", "Figura 17. Usuarios y roles."]]),
  ...seccionManual("admin_proveedores", [["20_proveedores.png", "Figura 18. Proveedores de IA con su prueba de conexión."]]),
  ...seccionManual("admin_parametros"),
  ...seccionManual("admin_auditoria", [["21_auditoria.png", "Figura 19. Auditoría de acciones con filtros y descarga."]]),
  ...seccionManual("admin_eliminados"),
);

// Parte III · Dónde aplica RiC
hijos.push(
  h1("3. Dónde aplica RiC en la plataforma y cómo lo hace"),
  p("RiC no es una capa que se agrega al final: es el **modelo de datos** de la plataforma. Cada tabla principal corresponde a una entidad de RiC-CM, cada vínculo entre ellas es una relación RiC identificada por su código, y la salida hacia otros sistemas es RiC-O. Este capítulo muestra, etapa por etapa, qué parte del modelo se aplica y cómo."),
  h2("3.1 Las entidades RiC-CM implementadas"),
  p("La plataforma implementa las **19 entidades** de la jerarquía de RiC-CM 1.0, respetando su herencia (por ejemplo, una Entidad corporativa es un Grupo, que es un Agente, que es una Cosa). La tabla muestra cada entidad con su clase en RiC-O."),
  tabla([900, 2600, 2700, 3160], [
    ["Código", "Entidad RiC-CM", "Clase RiC-O", "Uso en la plataforma"],
    ["E01", "Thing", "rico:Thing", "Raíz común: nombre (A28), identificador (A22), descripción general (A43)."],
    ["E02", "Record Resource", "rico:RecordResource", "Base de todo recurso documental."],
    ["E03", "Record Set", "rico:RecordSet", "Fondo, sección, serie, subserie y expediente (tipo de agrupación, A36)."],
    ["E04", "Record", "rico:Record", "Cada documento, con su forma documental (A17)."],
    ["E05", "Record Part", "rico:RecordPart", "Partes de un documento (p. ej. anexos)."],
    ["E06", "Instantiation", "rico:Instantiation", "Cada archivo cargado: formato, extensión, huella digital, páginas."],
    ["E07", "Agent", "rico:Agent", "Base de los agentes."],
    ["E08", "Person", "rico:Person", "Personas mencionadas o productoras."],
    ["E09", "Group", "rico:Group", "Grupos."],
    ["E10", "Family", "rico:Family", "Familias."],
    ["E11", "Corporate Body", "rico:CorporateBody", "Entidades y dependencias del organigrama."],
    ["E12", "Position", "rico:Position", "Cargos del organigrama."],
    ["E13", "Mechanism", "rico:Mechanism", "El motor de IA, con su proveedor y versión (A41)."],
    ["E14", "Event", "rico:Event", "Eventos."],
    ["E15", "Activity", "rico:Activity", "Funciones y actividades (de la TRD y el cuadro)."],
    ["E16", "Rule", "rico:Rule", "Normas."],
    ["E17", "Mandate", "rico:Mandate", "Series de la TRD (con su retención) y leyes citadas."],
    ["E18", "Date", "rico:Date", "Fechas normalizadas en ISO 8601 / EDTF."],
    ["E22", "Place", "rico:Place", "Lugares (con código DANE cuando existe)."],
  ]),
  espacio(),
  p("Además de las entidades, la plataforma conoce las **85 relaciones** y los **42 atributos** de RiC-CM 1.0 con su correspondencia en RiC-O 1.1 (matriz tomada de los documentos oficiales del ICA). Cada relación guarda su código (por ejemplo **R027 has creator**), su origen y su destino, su grado de certeza (RiC-RA01), su descripción (RA03) y su fuente (RA05)."),
  h2("3.2 RiC en cada etapa del proceso"),
  tabla([1900, 3560, 3900], [
    ["Etapa", "Qué hace el sistema", "Cómo se expresa en RiC"],
    ["Instrumentos archivísticos", "Carga la TRD, el cuadro de clasificación y el organigrama.", "Cada serie de la TRD → **Mandate (E17)** con su retención; su función → **Activity (E15)** unida con **R063 regulates**; la oficina → **Corporate Body (E11)** con **R060 is or was performed by**. Organigrama: jerarquía con **R045 has or had subordinate**; funcionarios con **R054 occupies** (Persona → Cargo) y **R056 exists or existed in** (Cargo → Grupo)."],
    ["Captura y clasificación", "Cada documento entra por su serie y su expediente; se calcula la huella SHA-256.", "Cadena de **Record Set (E03)**: fondo > sección > serie > expediente, unida con **R024 includes or included**; el documento es un **Record (E04)** y cada archivo una **Instantiation (E06)**; procedencia con **R026 has provenance** y función con **R033 documents**."],
    ["Descripción (IA)", "El motor lee el texto y propone entidades y relaciones con su cita.", "Solo propone relaciones que RiC-CM admite para un Record (dominio y rango); cada propuesta tiene como agente un **Mechanism (E13)** con su proveedor y versión."],
    ["Modelado de relaciones", "Grafo interactivo del documento; permite corregir el tipo de relación.", "La lista de relaciones posibles entre dos entidades se calcula con el dominio y rango de RiC-CM; el motor de reglas rechaza cualquier relación inválida al guardar."],
    ["Revisión archivística", "Segunda mirada ficha por ficha antes de publicar.", "Exige al menos una **relación de procedencia confirmada** (p. ej. **R027 has creator**) para publicar."],
    ["Trazabilidad", "Línea de tiempo de cada documento.", "Cada paso de la descripción queda como evento con su agente (persona o Mecanismo) en una cadena con hash; cada cambio de una relación guarda su versión anterior."],
    ["Valoración y disposición", "Calcula fases y listas de transferencia e inventario FUID.", "El expediente hereda el **Mandate** de su serie; la retención del mandato define la fase."],
    ["Consulta", "Catálogo por documentos y por entidades.", "Navegación por el grafo: de un documento a sus agentes, fechas, lugares, actividades y mandatos, y de ahí a otros documentos."],
    ["Intercambio", "Exportación y consultas.", "Salida en **RiC-O 1.1** (Turtle, RDF/XML, JSON-LD) y consultas **SPARQL** sobre el grafo."],
  ]),
  h2("3.3 Ejemplo: de un texto a la red RiC"),
  p("El oficio de prueba «Oficio 112-2025» dice, entre otras cosas: «ALCALDÍA MAYOR DE BOGOTÁ … Bogotá D.C., 20 de julio de 2025 … DE: Juan Pérez, Jefe de Archivo … conforme a la Ley 594 de 2000». El motor de análisis propone:"),
  tabla([2800, 2400, 4160], [
    ["Mención en el texto", "Entidad RiC", "Relación con el documento"],
    ["ALCALDÍA MAYOR DE BOGOTÁ", "Corporate Body (E11)", "R027 has creator (productor) — cita en la página 1, verificada"],
    ["Juan Pérez, Jefe de Archivo", "Person (E08) y Position (E12)", "Autor del documento; ocupa el cargo (R054)"],
    ["20 de julio de 2025", "Date (E18), normalizada 2025-07-20", "R080 is creation date of"],
    ["Bogotá D.C.", "Place (E22)", "Lugar de producción"],
    ["Ley 594 de 2000", "Mandate (E17)", "Norma citada (solo se acepta con cita textual, criterio CC-06)"],
  ]),
  espacio(),
  p("Una vez aceptadas y revisadas, las relaciones se exportan en RiC-O. Este es el resultado real, generado por la plataforma, para el «Acta del Cabildo de Santafé, 20 de julio de 1810»:"),
  ...codigo(turtle),
  espacio(),
  p("Se observa que el documento es un **rico:Record** con su forma documental, que **José Acevedo y Gómez** es un **rico:Person** unido con **rico:hasAuthor** (y su inversa **rico:isAuthorOf**), y que la actividad «Formación de la Junta Suprema de Gobierno» es un **rico:Activity** unida como tema con **rico:hasOrHadSubject**. Cualquier sistema que entienda RiC-O puede leer estos datos sin conocer RICORA."),
  h2("3.4 Lo que todavía no aplica (límites declarados)"),
  ...vinetas([
    "**Relaciones reificadas:** la exportación RiC-O emite cada relación como un enlace directo; la certeza, la descripción y la fuente de la relación (RA01, RA03, RA05) se guardan en la plataforma pero todavía no se exportan como **rico:Relation**.",
    "**Validación formal de la exportación:** hoy se verifica que el archivo RiC-O se pueda volver a leer y que contenga todos los documentos pedidos; no hay validación SHACL contra la ontología.",
    "**Extensiones locales:** los campos de la TRD (retención en gestión y central, disposición final) y la evidencia textual con su posición en la página no son conceptos de RiC-CM; son extensiones de la normativa colombiana y del método de trabajo, documentadas como tales.",
  ]),
);

// Parte IV · El sistema especializado
hijos.push(
  h1("4. Qué hace el sistema especializado en RiC"),
  p("Además de guardar datos con estructura RiC, la plataforma tiene componentes que **razonan con el modelo**. Estos son los que la hacen un sistema especializado en RiC y no un gestor documental genérico."),
  h2("4.1 Motor de análisis consciente del modelo"),
  ...vinetas([
    "A la IA no se le pide «extraer entidades» en general: se le entrega **solo la lista de relaciones que RiC-CM admite** para un Record, con los tipos de entidad que pueden estar al otro lado (personas, grupos, familias, entidades corporativas, cargos, actividades, mandatos, fechas y lugares).",
    "Se le entregan también las entradas ya existentes del vocabulario de autoridades, para que **reutilice** en lugar de duplicar.",
    "Cada propuesta vuelve con: código de relación RiC, tipo de entidad, nombre, **cita literal**, confianza (alta 0,9 · media 0,7 · baja 0,4), rol en el documento y, cuando aplica, la fecha normalizada, el tipo de norma o el código DANE del lugar.",
    "El motor es intercambiable: Gemini o Claude en la nube, spaCy u Ollama (modelo de lenguaje) en el propio servidor. Si el principal falla, usa el **respaldo automático** y lo dice.",
  ]),
  h2("4.2 Motor de reglas RiC-CM"),
  p("Cada vez que se guarda una relación —la proponga la IA o la cree una persona— el sistema comprueba contra la matriz de RiC-CM que el **origen y el destino sean de los tipos permitidos** para esa relación. Por ejemplo, **R054 occupies or occupied** solo admite Persona → Cargo; una relación con un código que no existe en RiC-CM se rechaza. Es imposible guardar una relación que el modelo no permite."),
  h2("4.3 Criterios de calidad de la descripción"),
  tabla([900, 3000, 5460], [
    ["Criterio", "Qué exige", "Qué hace el sistema"],
    ["CC-01", "Evidencia real", "Si la cita no aparece en el texto del documento, la propuesta se rechaza (y queda registrada con el motivo)."],
    ["CC-02", "Nada desaparece en silencio; descripción mínima", "Toda propuesta descartada se conserva; el documento se marca incompleto si le falta forma documental, agente o fecha."],
    ["CC-03", "Procedencia correcta", "Una relación de procedencia no puede apuntar a un destinatario o a alguien solo mencionado; no se publica sin procedencia confirmada."],
    ["CC-04", "Atención a lo dudoso", "Las fichas con confianza menor a 0,70 aparecen primero en la revisión y marcadas."],
    ["CC-05", "Autoridades únicas", "Si ya existe una entrada parecida (similitud ≥ 0,80), se sugiere reutilizarla."],
    ["CC-06", "Normas con cita", "Un mandato o regla sin cita textual explícita se rechaza."],
    ["CC-07", "Coherencia temporal", "Una fecha de creación posterior a la ingesta se señala como conflicto para que la persona decida."],
    ["CC-08", "Origen de cada decisión", "Cada relación dice si vino de la IA o de una corrección manual."],
  ]),
  h2("4.4 Autoridades y desambiguación"),
  p("Antes de crear una entidad, el sistema busca entradas parecidas en el vocabulario de autoridades (similitud por trigramas, sin distinguir tildes ni mayúsculas) y descarta como iguales a las que tienen identificadores distintos. La pantalla de **Posibles duplicados** muestra pares candidatos; la **fusión** la decide una persona y conserva el historial de ambas."),
  h2("4.5 Grafo navegable"),
  p("Cada documento y cada entidad se pueden ver como grafo. Las relaciones se agrupan por su sentido archivístico en siete categorías de color —procedencia, gestión y custodia, temporal, inclusión, espacial, identidad y asociación— y, al pulsar una línea, el sistema ofrece solo las relaciones RiC válidas entre esas dos entidades."),
  h2("4.6 Interoperabilidad RiC-O y SPARQL"),
  p("Toda la descripción validada se exporta en RiC-O 1.1 (Turtle, RDF/XML, N3, JSON-LD) y en CSV. Cada exportación se verifica (se vuelve a leer), recibe su huella SHA-256 y queda registrada. Sobre el mismo grafo se pueden hacer **consultas SPARQL** de solo lectura desde la plataforma, respetando lo que cada rol puede ver."),
  h2("4.7 Trazabilidad encadenada"),
  p("Cada paso de la descripción (extracción, propuesta de la IA, validación humana, publicación, exportación) es un evento con su agente, encadenado con el anterior mediante hash SHA-256. La línea de tiempo del documento indica si la cadena está íntegra y permite ver cómo estaba la descripción en cualquier momento pasado."),
  h2("4.8 Métricas de evaluación"),
  p("La plataforma define 14 métricas (M01 a M14) para evaluar el sistema. Hoy calcula con datos reales la tasa de aprobación, de corrección y de rechazo de las propuestas, la trazabilidad (propuestas con evidencia) y la consistencia RiC. La **precisión y el exhaustivo (recall)** del motor (M01, M02) quedan pendientes de un conjunto de documentos con la descripción correcta hecha por archivistas, que sirva de referencia; ese conjunto es una tarea natural del capítulo de evaluación de la tesis."),
);

// Parte V
hijos.push(
  h1("5. Pendientes y próximos pasos"),
  ...vinetas([
    "Validación del módulo M11 · Administración y seguridad.",
    "Revisión formal, con la misma metodología, de los módulos construidos antes (M3 motor de análisis, M4 modelado de relaciones y M5 vocabularios).",
    "Dominio propio con HTTPS y copias de seguridad programadas de la base de datos y los archivos.",
    "Conjunto de evaluación con descripción de referencia para medir precisión y exhaustividad del motor (M01, M02).",
    "Exportación de las relaciones reificadas (rico:Relation con certeza, descripción y fuente) y validación SHACL.",
    "Correo institucional en el servidor para que las invitaciones y los restablecimientos lleguen solos.",
  ]),
);

const doc = new Document({
  creator: "Marlín Jhaneth Martínez Córdoba",
  title: "RICORA · Manual de usuario y aplicación de RiC",
  styles: {
    default: { document: { run: { font: "Arial", size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 34, bold: true, font: "Arial", color: AZUL }, paragraph: { spacing: { before: 120, after: 220 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 27, bold: true, font: "Arial", color: "1C2433" }, paragraph: { spacing: { before: 280, after: 140 }, outlineLevel: 1, keepNext: true } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 23, bold: true, font: "Arial", color: NARANJA }, paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: { config: [
    { reference: "vinetas", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
    ...numeraciones,
  ] },
  features: { updateFields: true },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [t("RICORA · Manual de usuario y aplicación de RiC", { size: 16, color: GRIS })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [t("Página ", { size: 16, color: GRIS }), new TextRun({ children: [PageNumber.CURRENT], size: 16, color: GRIS })] })] }) },
    children: hijos,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const salida = process.argv[2] || path.join(DIR, "RICORA_Manual_de_usuario_y_aplicacion_RiC.docx");
  fs.writeFileSync(salida, buf);
  console.log("escrito", salida, buf.length);
});
