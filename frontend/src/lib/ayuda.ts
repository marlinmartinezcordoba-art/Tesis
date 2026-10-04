// Guía de cada pantalla para la ambulancia de ayuda: qué hacer aquí, paso a
// paso, con los nombres que se ven en la pantalla. Una guía por ruta y, en
// las pantallas con varias vistas (las del árbol de la barra lateral), una por vista.

export interface Paso { titulo: string; texto: string }
export interface Guia { titulo: string; pasos: Paso[] }

const GUIAS: Record<string, Guia> = {
  ingesta: {
    titulo: "Ingesta",
    pasos: [
      { titulo: "Aquí entran los documentos al archivo digital.",
        texto: "Cada archivo que se carga recibe su huella digital (SHA-256), se identifica su formato contra PRONOM y se extrae su texto, o se reconoce con OCR si es una imagen." },
      { titulo: "Cargue los documentos.",
        texto: "En «Cargar documentos», elija o arrastre los archivos. Antes, verifique arriba que el fondo seleccionado es el correcto: todo queda en ese fondo." },
      { titulo: "Revise la cola.",
        texto: "En «Cola de ingesta» se ve cada archivo mientras se procesa. Si aparece «duplicado», decida si es el mismo documento; si hay un error, puede reintentar." },
      { titulo: "Atienda el OCR de baja confianza.",
        texto: "Si una imagen se leyó con poca confianza (por debajo del umbral, 70 por defecto), queda marcada y con alerta. No se detiene: en Descripción tendrá que leer el texto con más cuidado." },
      { titulo: "Cuando dice «listo para descripción», ya terminó aquí.",
        texto: "El documento pasa solo a Descripción, sin ningún traspaso manual." },
    ],
  },
  "descripcion:cola": {
    titulo: "Descripción · Por describir",
    pasos: [
      { titulo: "Los documentos listos para describir, en una sola lista.",
        texto: "Aquí llega todo lo que terminó la ingesta. Si otra persona está describiendo uno, aparece con su nombre y no se puede abrir a la vez." },
      { titulo: "Elija qué describir.",
        texto: "Marque uno o varios documentos (por ejemplo, todos los de un expediente) y pulse «Describir». El motor de IA lee el texto y prepara una propuesta." },
      { titulo: "Los ya publicados están en «Descritas».",
        texto: "Desde ahí puede abrir una descripción publicada para consultarla o corregirla." },
    ],
  },
  "descripcion:publicadas": {
    titulo: "Descripción · Descritas",
    pasos: [
      { titulo: "Las descripciones ya publicadas del fondo.",
        texto: "Ábralas para ver su ficha completa: entidades, fechas, partes documentales, archivos y su lugar en el árbol del fondo." },
      { titulo: "Para corregir, ábrala y pulse «Corregir».",
        texto: "La corrección queda en la auditoría con el valor anterior y el nuevo. Nada se borra." },
    ],
  },
  trabajo: {
    titulo: "Describiendo",
    pasos: [
      { titulo: "La propuesta del motor, para que usted decida.",
        texto: "A la izquierda, el documento. A la derecha, lo que el motor propone: título, alcance y contenido, y las entidades (agentes, lugares, fechas, actividades, mandatos y forma documental), cada una con el fragmento del texto de donde sale." },
      { titulo: "Revise cada entidad.",
        texto: "Use «Aceptar», «Editar» o descártela. Las de confianza baja vienen señaladas. Si el motor dice «existente», la reconoció en el vocabulario del fondo y la reutiliza." },
      { titulo: "Complete lo que el motor no ve.",
        texto: "Idioma (código ISO 639-3, como «spa»), condiciones de acceso y de uso, custodio si es distinto del productor, la actividad mayor y la secuencia con otro documento de la misma serie." },
      { titulo: "Si hace falta, describa una parte.",
        texto: "Un sello, una firma o un anexo se describen como parte documental: recorte la zona en la página y dele su tipo. El recorte queda como archivo propio, con su segunda copia." },
      { titulo: "Publique.",
        texto: "La barra de abajo dice cuántas entidades faltan por resolver. Con todo resuelto, pulse «Publicar descripción». Cada decisión frente al motor queda en la auditoría." },
    ],
  },
  registro: {
    titulo: "Descripción publicada",
    pasos: [
      { titulo: "La ficha completa de una descripción.",
        texto: "Título, nivel, alcance, entidades con su relación RiC, fechas en EDTF, partes documentales, archivos y la ruta en el árbol del fondo." },
      { titulo: "Para cambiar algo, pulse «Corregir».",
        texto: "Puede editar campos, agregar entidades o partes y completar los datos de control del inventario (código de referencia, caja, carpeta, folios, soporte). Lo que falte saldrá como pendiente en el inventario." },
      { titulo: "Revise la historia.",
        texto: "El enlace al historial de auditoría muestra cada cambio con el antes y el después y la propiedad de RiC-O que afecta." },
    ],
  },
  "vocabularios:vocabulario": {
    titulo: "Vocabularios",
    pasos: [
      { titulo: "El control de autoridad del fondo.",
        texto: "Cada agente, lugar, actividad, función, mandato y forma documental existe una sola vez, y todas las descripciones lo reutilizan." },
      { titulo: "Busque y filtre.",
        texto: "Por tipo, por nombre o por nivel de detalle (mínimo o completo). Los «mecanismos» son los programas que actúan en el sistema (el motor, Siegfried, Ghostscript), con su versión exacta." },
      { titulo: "Abra una entidad para completar su ficha.",
        texto: "Los agentes tienen las cuatro áreas de ISAAR-CPF: nombres, identificadores (VIAF, Wikidata), historia, existencia, línea de tiempo y relaciones con otros agentes." },
      { titulo: "Las funciones forman un árbol.",
        texto: "Cada tipo de actividad (función) puede tener una función superior. Así se arma el árbol de funciones y subfunciones del fondo." },
    ],
  },
  "vocabularios:sugerencias": {
    titulo: "Sugerencias de fusión",
    pasos: [
      { titulo: "Posibles duplicados, para que usted decida.",
        texto: "El sistema busca solo entidades muy parecidas y con pocas conexiones. Nunca fusiona por su cuenta." },
      { titulo: "Compare y decida.",
        texto: "Si son la misma, pulse «Aprobar fusión»: las descripciones pasan a la definitiva y la absorbida se conserva como histórica. Si no, pulse «Son distintas»." },
    ],
  },
  entidad: {
    titulo: "Ficha de autoridad",
    pasos: [
      { titulo: "Todo lo que el fondo sabe de esta entidad.",
        texto: "Las áreas de la ficha se abren y se cierran. La insignia junto al nombre dice si la ficha es mínima o completa." },
      { titulo: "Complete lo que falte.",
        texto: "Use «Agregar» en cada campo. En un lugar, las coordenadas, el tipo y el lugar mayor; en un mandato, quién lo expidió y la norma superior." },
      { titulo: "Si es un duplicado, fusiónela.",
        texto: "Con «Fusionar con otra entidad», al final. Queda en el historial de fusiones y en la auditoría." },
    ],
  },
  "instrumentos:catalogo": {
    titulo: "Instrumentos · Catálogo",
    pasos: [
      { titulo: "El fondo como un árbol para consultar.",
        texto: "Baje por niveles: fondo, sección, serie, expediente y documento. Solo aparece lo publicado." },
      { titulo: "Abra la ficha de un documento.",
        texto: "Sin datos internos (ni el origen ni la confianza del motor): es la vista de consulta." },
      { titulo: "El paquete de preservación del expediente.",
        texto: "Desde un expediente puede exportar el paquete de preservación (AIP) de todos sus archivos." },
    ],
  },
  "instrumentos:grafo": {
    titulo: "Instrumentos · Grafo",
    pasos: [
      { titulo: "El fondo como la red que realmente es.",
        texto: "Documentos, agentes, lugares, fechas y actividades unidos por sus relaciones RiC." },
      { titulo: "Explore.",
        texto: "Arrastre, acerque con la rueda y pulse un nodo para ver sus relaciones con su nombre en RiC-O. «Centrar aquí» recorre la red desde ese punto." },
    ],
  },
  "instrumentos:inventario": {
    titulo: "Instrumentos · Inventario",
    pasos: [
      { titulo: "El Formato Único de Inventario Documental, armado solo.",
        texto: "Elija el nivel desde el cual generarlo y revise la vista previa. Un renglón por unidad documental o expediente." },
      { titulo: "Los datos faltantes salen como «pendiente».",
        texto: "No bloquean la exportación, pero generan una alerta. Complételos en la descripción con «Corregir»." },
      { titulo: "Exporte a hoja de cálculo.",
        texto: "Queda registrado en la auditoría." },
    ],
  },
  "instrumentos:guia": {
    titulo: "Instrumentos · Guía",
    pasos: [
      { titulo: "La guía del fondo, con un borrador del motor.",
        texto: "El motor redacta el texto a partir de lo publicado en los niveles superiores." },
      { titulo: "Edítelo y exporte.",
        texto: "Corrija libremente el texto y expórtelo a documento de Word." },
    ],
  },
  "instrumentos:indice": {
    titulo: "Instrumentos · Índice",
    pasos: [
      { titulo: "Busque por nombre.",
        texto: "Agentes, lugares, formas documentales, actividades y normas del fondo, en orden alfabético. Escriba en el buscador para filtrar." },
      { titulo: "Toque un término para ver sus documentos.",
        texto: "Se despliegan los documentos publicados que lo citan; cada uno abre su ficha." },
      { titulo: "Solo puntos de acceso del contenido.",
        texto: "Los programas del sistema (mecanismos) no aparecen aquí." },
    ],
  },
  "instrumentos:rico": {
    titulo: "Instrumentos · RiC-O",
    pasos: [
      { titulo: "El fondo como datos enlazados en RiC-O 1.1.",
        texto: "La ontología oficial del Consejo Internacional de Archivos, con una dirección (URI) propia para cada descripción, agente o lugar." },
      { titulo: "Valide antes de compartir.",
        texto: "«Validar conformidad» revisa la exportación contra la ontología oficial (OWL) y contra las reglas del sistema (SHACL). Debe decir «conforme»; si no, lista qué falla." },
      { titulo: "Descargue.",
        texto: "En Turtle (.ttl) o JSON-LD. Lo clasificado o reservado no sale, salvo que usted lo incluya con permiso; queda en la auditoría." },
      { titulo: "La consulta pública de las URI está apagada.",
        texto: "Solo la administración la enciende, y solo debe hacerlo con el servidor en HTTPS y los derechos de acceso revisados." },
    ],
  },
  preservacion: {
    titulo: "Preservación digital",
    pasos: [
      { titulo: "El estado técnico de cada archivo, de un vistazo.",
        texto: "Las cifras de arriba resumen las alertas de integridad, de segunda copia y de riesgo de formato. Lo que requiere atención aparece primero." },
      { titulo: "Abra un archivo para actuar.",
        texto: "En su ficha: verificar integridad, migrar a un formato seguro (PDF/A, TIFF), declarar derechos y exportar el paquete de preservación." },
      { titulo: "La verificación también corre sola.",
        texto: "Cada 30 días por defecto compara la huella de la copia principal y de la segunda copia." },
    ],
  },
  "preservacion-ficha": {
    titulo: "Ficha de preservación",
    pasos: [
      { titulo: "Todo lo técnico de este archivo.",
        texto: "Formato PRONOM, huella SHA-256, tamaño, copia primaria y segunda copia con su estado, y el programa que lo identificó (enlazado a su ficha en Vocabularios)." },
      { titulo: "Verifique la integridad.",
        texto: "Recalcula la huella de las dos copias. Si una cambió, genera su alerta y ofrece restaurar o rehacer la copia, siempre con su aprobación." },
      { titulo: "Migre solo con aprobación.",
        texto: "Elija el formato destino y apruebe. El original nunca se toca: la versión nueva queda enlazada a él." },
      { titulo: "Exporte el paquete de preservación.",
        texto: "Un AIP en BagIt con el archivo, sus metadatos PREMIS y las cinco categorías de OAIS, listo para entregar a otro sistema." },
    ],
  },
  "preservacion-configuracion": {
    titulo: "Configuración de preservación",
    pasos: [
      { titulo: "Las reglas de preservación del fondo.",
        texto: "Cada cuánto se verifica la integridad, qué formatos se migran solos y dónde vive la segunda copia." },
      { titulo: "Cambie con cuidado.",
        texto: "Cada cambio queda en la auditoría con el valor anterior. La segunda copia hoy comparte el disco del servidor: para producción real conviene otro lugar." },
    ],
  },
  "auditoria:propia": {
    titulo: "Auditoría · Trazabilidad · Mis acciones",
    pasos: [
      { titulo: "Todo lo que usted hizo en el sistema.",
        texto: "En orden, con fecha, módulo y detalle. Nadie puede editar ni borrar estos registros. Se ven las 15 más recientes." },
      { titulo: "Filtre y exporte.",
        texto: "Por tipo de acción y por fechas. «Exportar todo a Excel» trae todo lo que cumple el filtro, no solo lo visible." },
      { titulo: "¿Y el equipo?",
        texto: "Si usted ve toda la auditoría, arriba a la derecha está «Equipo por semana»: el resumen de cada persona." },
    ],
  },
  "auditoria:consolidado": {
    titulo: "Auditoría · Trazabilidad · Equipo por semana",
    pasos: [
      { titulo: "La semana de cada persona del equipo.",
        texto: "Días trabajados, horas conectadas y acciones por tipo. Son datos objetivos, no una calificación." },
      { titulo: "Abra una fila para ver las sesiones.",
        texto: "Hora de inicio, fin y duración de cada una." },
    ],
  },
  "auditoria:decisiones": {
    titulo: "Auditoría · Decisiones de IA",
    pasos: [
      { titulo: "Cada propuesta del motor frente a lo que quedó publicado.",
        texto: "Aceptada, corregida, rechazada o agregada por la archivista, con la clase y la propiedad de RiC-O que afecta." },
      { titulo: "Filtre y descargue.",
        texto: "Por tipo de entidad, decisión y periodo. La hoja de cálculo sirve para el capítulo de resultados." },
      { titulo: "Cada decisión dice con qué instrucción se hizo.",
        texto: "El identificador se calcula solo; puede ponerle un nombre («v3») en «Versiones de la instrucción del motor»." },
      { titulo: "Esto mide aceptación, no calidad.",
        texto: "Quien decide ve la propuesta antes. Para medir la calidad del motor use el módulo Evaluación." },
    ],
  },
  "auditoria:hallazgos": {
    titulo: "Auditoría · Hallazgos de conformidad",
    pasos: [
      { titulo: "Las brechas frente a RiC y cómo se fueron cerrando.",
        texto: "Lo lleva el equipo a mano. Rojo es abierto, ámbar en corrección y verde cerrado." },
      { titulo: "Actualice el estado.",
        texto: "En cada tarjeta, «Cambiar estado o acción». El título y la descripción no se editan: son la historia." },
      { titulo: "Registre uno nuevo solo si es real.",
        texto: "No se borra nunca, así que no cree hallazgos de prueba." },
    ],
  },
  "auditoria-entidad": {
    titulo: "Historial de auditoría",
    pasos: [
      { titulo: "Cada cambio de esta entidad, con el antes y el después.",
        texto: "El valor anterior tachado y el nuevo resaltado." },
      { titulo: "La columna «Propiedad RiC-O».",
        texto: "Dice qué propiedad de RiC-O afectó el cambio. En cursiva aparece lo que no tiene propiedad confirmada; nunca se inventa." },
    ],
  },
  evaluacion: {
    titulo: "Evaluación ciega",
    pasos: [
      { titulo: "Para medir la calidad del motor frente a archivistas.",
        texto: "Cada documento se describe primero a ciegas, sin ver nunca la propuesta; luego con ella delante; y al final se califica." },
      { titulo: "El orden importa.",
        texto: "Haga primero «Describir a ciegas», luego «Describir con la propuesta» y por último «Calificar la propuesta». Una vez vista la propuesta de un documento, ya no se puede describir a ciegas." },
      { titulo: "Para la administración.",
        texto: "Cree la evaluación, agregue documentos aún sin describir, genere las propuestas (nadie las ve) e iníciela. Al final, «Ver resultados» muestra precisión, exhaustividad y F1. Al verlos, usted queda expuesta a las propuestas." },
    ],
  },
  buscar: {
    titulo: "Buscar en el archivo",
    pasos: [
      { titulo: "Una caja para todo.",
        texto: "Busca a la vez en la descripción, en el texto de los documentos (OCR), en los códigos de referencia, en los identificadores (VIAF, ORCID…) y en las autoridades. No importan tildes, mayúsculas ni plurales." },
      { titulo: "Frases y exclusiones.",
        texto: "Entre comillas busca la frase exacta («archivo municipal»); un guion delante excluye una palabra (-1950)." },
      { titulo: "Por qué aparece cada resultado.",
        texto: "Cada documento dice dónde coincidió: descripción, texto del documento, código de referencia o la autoridad que cita. Afine por nivel, por años o por agente." },
      { titulo: "Lo reservado no aparece.",
        texto: "El perfil de consulta solo busca en lo publicado y de acceso público (Ley 1712, arts. 18 y 19): lo reservado no sale ni en los resultados ni en los conteos." },
    ],
  },
  alertas: {
    titulo: "Panel de alertas",
    pasos: [
      { titulo: "Lo que requiere atención, en un solo lugar.",
        texto: "Integridad, segunda copia, formatos en riesgo, OCR de baja confianza y campos pendientes del inventario. Las críticas van primero." },
      { titulo: "Atienda y marque.",
        texto: "Vaya al documento desde la alerta, resuelva y pulse «Marcar atendida». Algunas se cierran solas cuando el problema desaparece." },
    ],
  },
  usuarios: {
    titulo: "Gestión de usuarios",
    pasos: [
      { titulo: "El equipo y lo que cada persona puede hacer.",
        texto: "Invite por correo con un rol (archivista, revisor, consulta o administración). La persona define su propia contraseña con el enlace." },
      { titulo: "Cambie el rol o desactive.",
        texto: "Con «Editar». Nada se borra: una cuenta desactivada conserva su historia." },
    ],
  },
  perfil: {
    titulo: "Mi perfil",
    pasos: [
      { titulo: "Sus datos y su contraseña.",
        texto: "Cambie su nombre o su contraseña. Al cambiar la contraseña, se cierran sus otras sesiones." },
    ],
  },
};

/** La guía de la pantalla actual, o null si no hay una. */
export function guiaPara(ruta: string, vista: string | null): Guia | null {
  if (ruta.startsWith("/ingesta")) return GUIAS.ingesta;
  if (ruta.startsWith("/descripcion/trabajo")) return GUIAS.trabajo;
  if (ruta.startsWith("/descripcion/registro")) return GUIAS.registro;
  if (ruta.startsWith("/descripcion")) return GUIAS[`descripcion:${vista === "publicadas" ? "publicadas" : "cola"}`];
  if (/^\/vocabularios\/.+/.test(ruta)) return GUIAS.entidad;
  if (ruta.startsWith("/vocabularios")) return GUIAS[`vocabularios:${vista === "sugerencias" ? "sugerencias" : "vocabulario"}`];
  if (ruta.startsWith("/instrumentos")) return GUIAS[`instrumentos:${vista || "catalogo"}`] || GUIAS["instrumentos:catalogo"];
  if (ruta.startsWith("/preservacion/instanciacion")) return GUIAS["preservacion-ficha"];
  if (ruta.startsWith("/preservacion/configuracion")) return GUIAS["preservacion-configuracion"];
  if (ruta.startsWith("/preservacion")) return GUIAS.preservacion;
  if (ruta.startsWith("/auditoria/entidad")) return GUIAS["auditoria-entidad"];
  if (ruta.startsWith("/auditoria")) return GUIAS[`auditoria:${vista || "propia"}`] || GUIAS["auditoria:propia"];
  if (ruta.startsWith("/evaluacion")) return GUIAS.evaluacion;
  if (ruta.startsWith("/alertas")) return GUIAS.alertas;
  if (ruta.startsWith("/buscar")) return GUIAS.buscar;
  if (ruta.startsWith("/usuarios")) return GUIAS.usuarios;
  if (ruta.startsWith("/perfil")) return GUIAS.perfil;
  return null;
}
