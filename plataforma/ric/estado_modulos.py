"""Estado honesto de los 20 módulos de la Matriz Maestra (F01-F20), para
mostrarlo dentro de la propia plataforma — no solo en un documento aparte.

Se actualiza a mano cada vez que se completa o audita un módulo; es
deliberadamente simple (una lista de dicts) para que no dependa de nada
más y sea fácil de revisar en una sola lectura.
"""

COMPLETO = "completo"
PENDIENTE = "pendiente"
PARCIAL = "parcial"
NO_CONSTRUIDO = "no"

ETIQUETA_ESTADO = {
    COMPLETO: "Completo y probado",
    PENDIENTE: "Existe, falta auditar",
    PARCIAL: "Construido a medias",
    NO_CONSTRUIDO: "Sin construir",
}

MODULOS = [
    {"codigo": "F01", "nombre": "Ingesta y preservación de evidencia", "estado": COMPLETO,
     "descripcion": "Subes uno o varios archivos a la vez. El sistema calcula su huella digital (hash) y nunca modifica el original.",
     "nota": "Es lo que en el panel técnico de Django se llama \"Instantiation\" — se renombró a "
             "\"Ingesta de documentos (F01/F02)\" para que se reconozca con el nombre de tu Matriz Maestra.",
     "detalle": "Dónde: menú \"Subir documento\", o Panel técnico → Motor RiC → “Ingesta de documentos (F01/F02)”."},
    {"codigo": "F02", "nombre": "OCR", "estado": COMPLETO,
     "descripcion": "Extrae el texto de documentos escaneados y guarda en qué página, y en qué posición exacta de la imagen, está cada palabra.",
     "detalle": "Se ejecuta solo al subir un archivo, junto con F01."},
    {"codigo": "F03", "nombre": "Comprensión documental", "estado": COMPLETO,
     "descripcion": "Reconoce encabezado, título, campos (PARA/DE/ASUNTO), fechas, secciones, artículos, firmas y tablas reales de Word.",
     "detalle": "Se ejecuta solo al subir un archivo. Se ve en “Componentes estructurales” dentro de cada documento (panel técnico).",
     "nota": "No detecta sellos ni tablas dentro de imágenes o PDF escaneados — requiere analizar la imagen píxel por píxel, y no está construido."},
    {"codigo": "F04", "nombre": "Segmentación", "estado": COMPLETO,
     "descripcion": "Si un archivo trae varios documentos juntos, te lo señala para que decidas si separarlos.",
     "detalle": "Dónde: Panel técnico → “Propuestas de segmentación (F04)”."},
    {"codigo": "F05", "nombre": "IA multimodal", "estado": PENDIENTE,
     "descripcion": "La IA lee un documento (texto e imagen) y propone entidades, atributos y relaciones, citando su evidencia y confianza.",
     "detalle": "Se le envía la imagen/PDF real a la IA, no solo el texto de OCR (antes no era realmente \"multimodal\"). "
                "Gemini es ahora el proveedor de IA en la nube que se usa activamente (Panel técnico → “Proponer "
                "relaciones (IA en la nube, Gemini)”); Claude se dejó como alternativa. Falta: probarlo con la API "
                "real de Gemini (aquí solo se pudo probar con el cliente simulado, sin clave configurada) y el "
                "resto de la auditoría.",
     "nota": "De paso se corrigió un bug real: con varios archivos en un mismo expediente, se le pasaba uno arbitrario "
             "a la IA; ahora se usa el que más texto tiene."},
    {"codigo": "F06", "nombre": "Evidencia de propuesta", "estado": COMPLETO,
     "descripcion": "Cada afirmación de la IA debe enlazar al documento, página, fragmento y posición exacta que la respalda.",
     "detalle": "La bandeja de validación ahora enlaza al documento original y, cuando es una imagen escaneada con "
                "coordenadas de OCR (F02), resalta la evidencia sobre la imagen real — antes solo se citaba el texto."},
    {"codigo": "F07", "nombre": "Motor RiC", "estado": COMPLETO,
     "descripcion": "Guarda entidades, atributos, relaciones e identificadores siguiendo el modelo oficial RiC-CM 1.0, con validaciones antes de guardar.",
     "detalle": "El diagrama oficial RiC-CM que compartiste ya coincide con lo implementado. Se auditó contra la "
                "propia Matriz Maestra (que pide \"...IDs, versionado y validaciones\") y faltaba el versionado: "
                "editar una entidad o relación ya existente sobrescribía sus valores anteriores sin dejar rastro. "
                "Ahora cada vez que se guarda un cambio sobre algo que ya existía, se conserva una fotografía de "
                "cómo estaba antes — se ve en Panel técnico → “Versiones (historial RiC)”, de solo lectura.",
     "nota": "Si guardar la edición falla por una validación (por ejemplo una relación que rompería una regla de "
             "RiC-CM), no queda ninguna fotografía huérfana: primero se valida, y solo si el cambio de verdad se "
             "aplica se guarda su historial."},
    {"codigo": "F08", "nombre": "Validación archivista", "estado": PARCIAL,
     "descripcion": "Aprobar, corregir, rechazar, vincular a algo existente, fusionar o separar — la decisión siempre la toma una persona.",
     "detalle": "Se auditó contra su propia descripción, verbo por verbo. \"Vincular a algo existente\" y "
                "\"rechazar\" ya funcionaban. \"Corregir\" existía en el modelo pero la bandeja no tenía ningún "
                "campo para escribir el nombre corregido — ahora sí (se edita antes de \"Aceptar\"). "
                "\"Fusionar\" no existía en absoluto: si dos propuestas creaban la misma entidad con el nombre "
                "escrito distinto, no había forma de unirlas después. Ahora, desde el panel técnico, seleccione "
                "dos o más entidades del mismo tipo (persona, lugar, entidad corporativa...) y \"Fusionar en otra "
                "entidad seleccionada\": elige cuál sobrevive, sus relaciones y propuestas pendientes se mueven a "
                "ella, y se guarda una fotografía de la fusionada antes de borrarla (ver Versiones, historial RiC).",
     "nota": "\"Separar\" sigue sin construir a propósito: separar una entidad en qué, con qué criterio, es una "
             "decisión de diseño tuya, no algo que se pueda deducir de la auditoría. Además, \"fusionar\" no "
             "aplica a Record Set ni Record Part: otras filas dependen de ellos directamente (jerarquía "
             "documental), no solo por relación RiC, así que fusionarlos se dejó fuera para no arrastrar esa "
             "decisión por accidente."},
    {"codigo": "F09", "nombre": "Motor de reglas", "estado": PENDIENTE,
     "descripcion": "Antes de guardar una relación entre dos entidades, verifica que respete las reglas oficiales de RiC-CM.",
     "detalle": "Existe y ya se probó bastante en el camino (por ejemplo al construir F04). Pendiente una auditoría formal propia."},
    {"codigo": "F10", "nombre": "Desambiguación", "estado": NO_CONSTRUIDO,
     "descripcion": "Detectar sola cuando una persona o entidad nueva podría ser un duplicado de una que ya existe, y sugerirlo.",
     "detalle": "Falta construir. Hoy solo se puede vincular a mano cuando tú misma reconoces que ya existe."},
    {"codigo": "F11", "nombre": "Aprendizaje asistido", "estado": PENDIENTE,
     "descripcion": "Usa decisiones ya validadas por ti como ejemplo para mejorar las próximas propuestas de la IA.",
     "detalle": "Existe. Pendiente de auditar."},
    {"codigo": "F12", "nombre": "RiC-O / RDF", "estado": PENDIENTE,
     "descripcion": "Convierte el grafo ya validado al formato RDF, el estándar semántico oficial de RiC-O 1.1.",
     "detalle": "Existe (exportación en Turtle y RDF-XML). Pendiente de auditar."},
    {"codigo": "F13", "nombre": "Grafo de conocimiento", "estado": PENDIENTE,
     "descripcion": "Muestra visualmente cómo se conectan las entidades y relaciones ya validadas.",
     "detalle": "Existe (pantalla de Grafo). Pendiente de auditar."},
    {"codigo": "F14", "nombre": "Búsqueda semántica", "estado": PARCIAL,
     "descripcion": "Buscar por palabra en el texto extraído y en los nombres de entidades ya funciona. Buscar por significado o contexto todavía no.",
     "detalle": "Falta: búsqueda por significado, más allá de coincidencia de texto."},
    {"codigo": "F15", "nombre": "Auditoría", "estado": PENDIENTE,
     "descripcion": "Registra quién hizo qué y cuándo, encadenado de forma que alterar o borrar un registro rompe la cadena y se nota.",
     "detalle": "Existe (bitácora + muestreo de auditoría). Pendiente de auditar."},
    {"codigo": "F16", "nombre": "Seguridad", "estado": COMPLETO,
     "descripcion": "Roles y permisos distintos según la tarea: quién puede solo consultar, quién puede validar, quién puede administrar.",
     "detalle": "Dos perfiles: archivista (ingiere, valida, entra también al panel técnico) e invitado de consulta "
                "(busca, ve el grafo validado, exporta — sin subir ni validar). Pantalla de ingreso propia en "
                "/ric/entrar/, porque la del admin de Django rechaza a cualquiera sin perfil de personal. Toda "
                "pantalla exige sesión, incluido el archivo original de cada documento.",
     "nota": "Se crea un invitado de consulta como cualquier usuario, desde Panel técnico → Usuarios, sin marcar "
             "la casilla \"Es staff\"."},
    {"codigo": "F17", "nombre": "Laboratorio de evaluación", "estado": PENDIENTE,
     "descripcion": "Calcula métricas de calidad del sistema (precisión, tiempo, correcciones) con datos reales, nunca inventados.",
     "detalle": "Existe (pantalla de Evaluación, M01-M14). Pendiente de auditar."},
    {"codigo": "F18", "nombre": "API", "estado": PARCIAL,
     "descripcion": "Endpoints para conectar RICORA con otros sistemas: ingesta, IA, validación, RDF, búsqueda y grafo.",
     "detalle": "Falta: solo existen 3 conexiones técnicas (grafo, SPARQL, métricas), no una API completa."},
    {"codigo": "F19", "nombre": "Exportación", "estado": PARCIAL,
     "descripcion": "Exportar el trabajo hecho en distintos formatos: RDF, JSON, CSV, o paquetes de evidencia.",
     "detalle": "Falta: hoy solo se exporta a RDF."},
    {"codigo": "F20", "nombre": "Administración de modelos", "estado": NO_CONSTRUIDO,
     "descripcion": "Una pantalla para elegir o cambiar el proveedor de IA, y ver cuánto cuesta cada uso.",
     "detalle": "Falta construir esa pantalla. Hoy elegir Gemini o Claude es una acción distinta en el panel "
                "técnico (Registros → seleccionar → \"Proponer relaciones...\"), y qué modelo exacto de cada uno "
                "se configura por variable de entorno — no hay ninguna pantalla para cambiarlo ni para ver costos."},
]


def resumen():
    conteo = {COMPLETO: 0, PENDIENTE: 0, PARCIAL: 0, NO_CONSTRUIDO: 0}
    for m in MODULOS:
        conteo[m["estado"]] += 1
    return conteo
