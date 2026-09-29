"""Ayuda de RICORA: qué hace cada pantalla y cómo se usa, paso a paso, en
lenguaje de archivo. La misma guía se abre desde el botón «Ayuda» de cada
pantalla (solo la de esa pantalla)."""

GUIAS = [
    {
        "clave": "inicio", "proceso": "Inicio", "titulo": "Inicio",
        "para_que": "Su pantalla de trabajo: lo que espera una acción suya, las alertas abiertas y los últimos documentos con su estado.",
        "pasos": [
            "En la barra superior, escriba un nombre, un lugar o una fecha para buscar en el catálogo (atajo: Ctrl K).",
            "En «Mi trabajo de hoy», cada recuadro dice cuántos documentos esperan una acción suya; al pulsarlo lo lleva a hacerla.",
            "En «Requieren atención» están las alertas críticas y altas: pulse una para ir a resolverla.",
            "En «Últimos documentos», el enlace de cada fila lleva al paso que sigue (Preprocesar, Analizar, Decidir, Revisar o Ver ficha).",
        ],
        "consejos": [
            "Las alertas críticas son revisiones atrasadas, errores del OCR y retenciones cumplidas; las altas, lo que vence pronto o el OCR de calidad baja.",
            "El logo RICORA del menú lateral siempre lo trae de vuelta aquí.",
        ],
    },
    # --- Instrumentos archivísticos ---
    {
        "clave": "vocabularios", "proceso": "Instrumentos archivísticos", "titulo": "Vocabularios y autoridades",
        "para_que": "Reúne los registros de autoridad validados (personas, instituciones, cargos, funciones, mandatos, fechas, lugares y formas documentales) y los instrumentos archivísticos: TRD, cuadro de clasificación y organigrama. La IA los consulta antes de proponer algo nuevo, para no duplicar.",
        "pasos": [
            "Antes de empezar a cargar documentos, abra «Precargar instrumentos archivísticos» e importe la TRD, el cuadro de clasificación y el organigrama (CSV o JSON).",
            "Filtre por clase con los botones (Personas, Mandatos, Formas documentales…).",
            "Escriba en el buscador para comprobar si una entrada ya existe antes de crearla.",
            "Abra una entrada para ver su ficha: datos, documentos que la usan, relaciones, y editar lo necesario.",
            "Pase de página con ‹ › al final de la tabla.",
        ],
        "consejos": [
            "Cada serie de la TRD queda como un mandato con su retención y disposición final; los documentos la heredan.",
            "Los cambios guardan la versión anterior y quién los hizo.",
        ],
    },
    {
        "clave": "vocabularios_duplicados", "proceso": "Instrumentos archivísticos", "titulo": "Posibles duplicados",
        "para_que": "Muestra pares de entradas con nombres muy parecidos (por ejemplo «Cabildo de Santafé» y «Cabildo de Santa Fe») que podrían ser la misma.",
        "pasos": [
            "Revise cada par y decida si son la misma entidad.",
            "Abra la entrada que debe quedar y use «Fusionar en esta»: las relaciones y documentos de la otra pasan a ella.",
            "Si no son la misma, déjelas como están.",
        ],
        "consejos": ["La entrada fusionada no se borra: queda en Eliminados con el motivo y se puede restaurar."],
    },
    # --- Captura y clasificación ---
    {
        "clave": "ingesta", "proceso": "Captura y clasificación", "titulo": "Cargar documentos",
        "para_que": "Ingresa documentos clasificados desde el primer momento: serie de la TRD → expediente → archivos. Verifica cada archivo, calcula su huella digital SHA-256 y rechaza duplicados.",
        "pasos": [
            "Paso 1 · Busque y elija la serie o subserie de la TRD (por nombre, código u oficina).",
            "Paso 2 · Elija «Crear un expediente nuevo» (escriba su nombre) o «Agregar a un expediente existente».",
            "Paso 3 · Arrastre los archivos o selecciónelos; también puede subir una carpeta completa (un expediente por carpeta).",
            "Pulse «Cargar» y siga la barra de avance de cada archivo. Si uno es rechazado, la fila dice por qué; use «Quitar».",
            "Paso 4 · Cuando no quede ninguna carga en curso, pulse «Enviar a preprocesamiento».",
        ],
        "consejos": [
            "Si varios archivos son partes de un mismo documento (escaneo partido), marque esa opción antes de cargar.",
            "Formatos admitidos: PDF, imágenes (JPG, PNG, TIFF, BMP), DOCX, TXT, MD, CSV y XML; máximo 200 MB por archivo.",
        ],
    },
    {
        "clave": "preproceso", "proceso": "Captura y clasificación", "titulo": "Preprocesamiento y OCR",
        "para_que": "Extrae el texto de cada archivo (OCR en imágenes y PDF escaneados), detecta el idioma y marca las páginas con lectura de baja calidad. Trabaja en segundo plano.",
        "pasos": [
            "Pulse «Procesar (OCR)» en un archivo o «Enviar a preprocesamiento todos los que no se han enviado».",
            "Siga el avance: sin enviar → en cola → procesando (página por página) → listo.",
            "Si aparece «calidad baja», abra la página indicada y decida: «Aceptar igual» o «Reescanear».",
            "Cuando está listo, el documento pasa solo al motor de análisis; pulse «Ver propuesta de entidades».",
        ],
        "consejos": [
            "Puede cerrar la pantalla: el trabajo continúa y al volver verá el estado.",
            "Si algo falla, la fila explica el motivo y ofrece «Reintentar»; el original nunca se modifica.",
        ],
    },
    # --- Descripción ---
    {
        "clave": "analisis_lista", "proceso": "Descripción", "titulo": "Análisis y relaciones",
        "para_que": "La IA propone las entidades del documento (quién lo produjo, a quién se refiere, fechas, lugares, funciones, normas) con la cita del texto que lo respalda. Usted decide cada una.",
        "pasos": [
            "Abra un documento de la lista.",
            "A la izquierda está el texto con los fragmentos resaltados; a la derecha, las pestañas Entidades propuestas, Forma documental, Avisos y Ya decididas.",
            "En cada ficha: corrija el nombre si hace falta y pulse «Aceptar», «Vincular» (si ya existe en vocabularios) o «Rechazar» con su motivo.",
            "Si no hay propuestas, pulse «Generar propuesta de entidades» (trabaja en segundo plano).",
            "Asigne la forma documental en su pestaña.",
            "Pulse «Continuar a relaciones» para ver el grafo del documento y corregir tipos de relación.",
        ],
        "consejos": [
            "Toque la cita de una ficha para ver dónde aparece en el texto.",
            "Si el servicio de IA en la nube está saturado, el sistema usa la IA local de respaldo y se lo dice.",
        ],
    },
    {
        "clave": "revision_lista", "proceso": "Descripción", "titulo": "Revisión archivística",
        "para_que": "Segunda mirada, ficha por ficha, a lo que se aceptó en el análisis. Nada se publica en el catálogo mientras quede una ficha sin revisar.",
        "pasos": [
            "Abra un documento de la bandeja (los que tienen «fichas por revisar» esperan por usted).",
            "Cada ficha muestra a la izquierda lo propuesto por la IA con su cita, y a la derecha el campo editable.",
            "Pulse «Aceptar» (tal cual o con el nombre corregido) o «Rechazar» escribiendo el motivo.",
            "La barra superior muestra cuántas fichas lleva revisadas.",
            "Cuando no quede ninguna pendiente, pulse «Aprobar y publicar».",
        ],
        "consejos": [
            "Las fichas de baja confianza aparecen primero y con borde rojo.",
            "Una ficha rechazada vuelve al análisis con su motivo; lo demás ya aceptado se conserva.",
            "Si el nombre de una entidad es compartido con otros documentos, se corrige en Vocabularios para no cambiarlo en todos.",
        ],
    },
    {
        "clave": "historial_lista", "proceso": "Descripción", "titulo": "Trazabilidad y auditoría",
        "para_que": "Muestra la línea de tiempo completa de cada documento: qué propuso la IA, qué decidió cada persona y cuándo, con el valor anterior y el nuevo de cada cambio.",
        "pasos": [
            "Abra el historial de un documento (también desde su ficha del catálogo con «Ver historial»).",
            "Filtre por Propuestas de IA, Decisiones humanas o Sistema.",
            "Abra un punto para ver qué campo cambió, el valor anterior (tachado) y el nuevo.",
            "Pulse «Ver estado en este punto» para ver la descripción completa tal como estaba en ese momento.",
            "Use «Exportar historial» (CSV o JSON) si necesita la evidencia fuera del sistema.",
        ],
        "consejos": ["El sello «Cadena de eventos verificada» confirma que ningún registro fue alterado."],
    },
    # --- Valoración ---
    {
        "clave": "valoracion", "proceso": "Valoración y disposición", "titulo": "Expedientes y retención",
        "para_que": "Muestra cada expediente con la retención que hereda de su serie de la TRD y la fase en que está (gestión, central o disposición final).",
        "pasos": [
            "Busque un expediente o filtre por fase.",
            "Abra uno para ver sus fechas, su retención y cuándo pasa a la siguiente fase.",
        ],
        "consejos": ["La retención no se escribe a mano: sale de la TRD cargada en Instrumentos archivísticos."],
    },
    {
        "clave": "valoracion_transferencias", "proceso": "Valoración y disposición", "titulo": "Transferencias y disposición final",
        "para_que": "Lista los expedientes que ya cumplieron su tiempo en gestión o en central y deben transferirse o aplicar su disposición final (conservación total, eliminación, medio tecnológico o selección).",
        "pasos": ["Revise la lista y prepare la transferencia o la disposición según indica cada expediente."],
        "consejos": ["El panel de indicadores avisa cuántos expedientes tienen la retención vencida o por vencer."],
    },
    {
        "clave": "valoracion_fuid", "proceso": "Valoración y disposición", "titulo": "Inventario FUID",
        "para_que": "Descarga el Formato Único de Inventario Documental con los expedientes del sistema.",
        "pasos": ["Pulse la opción del menú para descargar el FUID en CSV y ábralo en su hoja de cálculo."],
        "consejos": [],
    },
    # --- Consulta y exportación ---
    {
        "clave": "catalogo", "proceso": "Consulta y exportación", "titulo": "Catálogo",
        "para_que": "Busca documentos y entidades (personas, instituciones, fechas, lugares, funciones, normas) y navega de unos a otros. Cada rol ve solo lo que puede consultar.",
        "pasos": [
            "Escriba en el buscador; puede elegir una sugerencia con el mouse o con las flechas y Enter. No importan las tildes.",
            "Filtre por clase con el panel de la izquierda.",
            "Abra una tarjeta para ver la ficha completa con sus relaciones y documentos relacionados.",
            "Desde un documento use «Ver documento» (visor), «Ver en grafo» o «Ver historial».",
            "Marque documentos con «Seleccionar para exportar» y pulse «Exportar selección».",
        ],
        "consejos": ["Las cuentas de consulta solo ven documentos aprobados, publicados y de acceso abierto."],
    },
    {
        "clave": "exportar", "proceso": "Consulta y exportación", "titulo": "Exportación e interoperabilidad",
        "para_que": "Entrega la descripción de los documentos a otros sistemas en RiC-O (RDF), JSON-LD o CSV. Cada archivo se verifica antes de entregarlo y queda registrado.",
        "pasos": [
            "Elija el formato: RDF/RiC-O, JSON-LD o CSV (para Excel).",
            "Marque los documentos (los que vienen del catálogo aparecen ya marcados). Puede filtrar la lista.",
            "Pulse «Generar exportación» y espere la barra de avance.",
            "Pulse «Descargar». La exportación queda en el registro con su alcance, quién la pidió y su huella.",
        ],
        "consejos": ["El CSV se abre directamente en Excel con tildes y eñes correctas."],
    },
    # --- Indicadores ---
    {
        "clave": "panel", "proceso": "Indicadores", "titulo": "Panel de indicadores",
        "para_que": "Cifras vigentes del proceso: documentos ingestados, porcentaje validado, tiempo de revisión, pendientes y alertas.",
        "pasos": [
            "Elija el periodo arriba (semana, mes, trimestre, año o todo).",
            "Recorra las páginas con las flechas ‹ › (1 Resumen, 2 Trabajo en curso, 3 Actividad).",
            "Haga clic en una cifra para ver la lista exacta de documentos que la componen.",
            "Si aparece la alerta roja, púlsela para ver los documentos atrasados.",
        ],
        "consejos": ["El límite de días de la alerta se cambia en Administración → Parámetros."],
    },
    # --- Administración ---
    {
        "clave": "admin_usuarios", "proceso": "Administración", "titulo": "Usuarios y roles",
        "para_que": "Decide quién entra a RICORA y qué puede hacer: cada cuenta tiene exactamente uno de los cuatro roles.",
        "pasos": [
            "Pulse «Nuevo usuario», escriba el nombre y el correo; el nombre de usuario se sugiere solo a partir del correo.",
            "Elija el rol: archivista, revisor, consulta o administrador. Debajo de cada uno se explica lo que permite.",
            "Pulse «Guardar». La persona recibe un enlace para crear su propia contraseña; si el servidor no tiene correo, copie el enlace que aparece arriba y envíeselo.",
            "Para cambiar el nombre, el correo o el rol, pulse «Editar» en la fila de la cuenta.",
            "Desde «Editar» también puede reenviar la invitación, restablecer el acceso, cerrar sesiones o desactivar la cuenta.",
        ],
        "consejos": [
            "Usted nunca conoce ni escribe la contraseña de otra persona: cada quien crea la suya con el enlace, que sirve una sola vez.",
            "Nada se borra: una cuenta desactivada no puede entrar, pero conserva todo su historial.",
            "Siempre debe quedar al menos un administrador activo; el sistema no deja quitarle el rol al último.",
            "Use el buscador, el filtro de rol y «Solo activos» para encontrar una cuenta rápido.",
            "Quien olvida su contraseña la pide desde el ingreso («¿Olvidó su contraseña?»). Sin correo en el servidor, la solicitud aparece aquí arriba: pulse «Generar enlace» y hágaselo llegar.",
        ],
    },
    {
        "clave": "admin_proveedores", "proceso": "Administración", "titulo": "Proveedores de IA",
        "para_que": "Configura los servicios de inteligencia artificial que usa el motor de análisis para proponer entidades y relaciones.",
        "pasos": [
            "Pulse «Agregar proveedor» y elija el proveedor de la lista.",
            "Pegue la clave de acceso si el proveedor la pide (la IA local no la necesita).",
            "Pulse «Probar conexión»: si sale bien aparece el punto verde y se habilita «Guardar».",
            "Pulse «Guardar» para dejarlo como fuente del motor de análisis.",
            "En la tabla puede volver a probar, activar otro, dejar uno como respaldo automático o retirarlo.",
        ],
        "consejos": [
            "Ningún proveedor se guarda sin una prueba exitosa de esos mismos datos: si cambia la clave después de probar, hay que probar de nuevo.",
            "El respaldo automático se usa solo cuando el principal falla (saturado, sin conexión o sin cupo).",
            "La clave nunca se muestra completa: solo sus últimos cuatro caracteres.",
        ],
    },
    {
        "clave": "admin_parametros", "proceso": "Administración", "titulo": "Parámetros",
        "para_que": "Ajusta los valores que rigen el funcionamiento: cuándo una revisión se considera atrasada y los umbrales de calidad y confianza.",
        "pasos": [
            "Cambie el valor que necesite; debajo de cada uno se explica su efecto.",
            "Pulse «Guardar parámetros». El cambio aplica de inmediato en toda la plataforma.",
        ],
        "consejos": ["Queda registrado quién hizo el último cambio y cuándo, con el valor anterior y el nuevo en la auditoría."],
    },
    {
        "clave": "admin_auditoria", "proceso": "Administración", "titulo": "Auditoría",
        "para_que": "Muestra quién hizo qué, sobre qué y cuándo: ingresos, intentos fallidos, accesos denegados, creaciones, cambios, borrados y restauraciones.",
        "pasos": [
            "Filtre por usuario, acción, fechas u objeto y pulse «Filtrar».",
            "Abra «campo(s)» en una fila para ver el valor anterior y el nuevo de cada cambio.",
            "Pulse «CSV» para descargar lo filtrado.",
        ],
        "consejos": ["La auditoría solo se escribe: nadie la puede editar ni borrar desde la aplicación."],
    },
    {
        "clave": "admin_eliminados", "proceso": "Administración", "titulo": "Eliminados",
        "para_que": "Reúne todo lo que se retiró de las pantallas (borrado lógico), con quién lo retiró, cuándo y por qué.",
        "pasos": ["Busque el elemento en la lista.", "Pulse «Restaurar» para devolverlo a las pantallas con todo su historial."],
        "consejos": ["Nada se elimina de forma irreversible; cada restauración queda en la auditoría."],
    },
]

_POR_CLAVE = {g["clave"]: g for g in GUIAS}

# Pantallas de detalle que comparten la guía de su lista.
_EQUIVALENCIAS = {
    "analisis": "analisis_lista", "analisis_grafo": "analisis_lista", "analisis_relacion": "analisis_lista",
    "revision": "revision_lista", "historial": "historial_lista", "catalogo_ficha": "catalogo",
    "vocabulario_ficha": "vocabularios", "valoracion_expediente": "valoracion", "visor_documento": "catalogo",
    "ric_grafo": "catalogo", "preproceso_pagina": "preproceso",
}


def guia_de(url_name):
    if not url_name:
        return None
    if url_name.startswith("admin_"):
        return _POR_CLAVE.get(url_name, _POR_CLAVE["admin_usuarios"])
    return _POR_CLAVE.get(_EQUIVALENCIAS.get(url_name, url_name))
