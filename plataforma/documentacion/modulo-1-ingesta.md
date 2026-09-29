# Módulo 1 · Ingesta: carga de archivos pesados y visor documental

Estructura de 23 puntos (sección 5 del prompt de desarrollo). Alcance fijado por la sección 7 del prompt ("visor documental y carga de archivos pesados"), la auditoría de arquitectura (preguntas 11, 17 y 18; sección F, protección de archivos cargados) y la historia de usuario 1.

## 1. Propósito
Que todo documento entre al sistema con su integridad comprobada desde el primer byte, clasificado en su serie y expediente, y que cualquiera con permiso pueda verlo junto a su contexto archivístico sin salir de la pantalla.

## 2. Auditoría (qué se revisó antes de construirlo)
Existía la carga clasificada por serie y expediente con huella SHA-256 y bitácora. Faltaba: validación del contenido contra la extensión (se confiaba en la extensión), rechazo de duplicados, carga por archivo con avance real (un formulario único que subía todo junto), fila roja con «Quitar», botón de preprocesamiento bloqueado durante la carga, límites para archivos grandes, visor documental (solo había una vista de imagen en la ruta de calidad baja). Se encontró además un hueco de seguridad: la entrega del archivo original no verificaba el rol, cualquier sesión descargaba cualquier archivo conociendo su número.

## 3. Problema que resuelve
Cargas grandes que bloqueaban la pantalla sin saber qué pasaba; archivos disfrazados (un ejecutable con extensión .pdf) aceptados; el mismo archivo ingresado dos veces; y la necesidad de ver el documento abriendo el original aparte, sin contexto.

## 4. Usuarios
Archivista (carga, preprocesa, ve todo). Revisor (ve todo). Consulta (ve solo documentos publicados y archivos de acceso abierto).

## 5. Casos de uso
Cargar uno o varios archivos o una carpeta; ver el avance por archivo; ver por qué se rechazó un archivo y quitarlo; enviar a preprocesamiento cuando no quedan cargas; abrir un documento en el visor, hojearlo, ampliarlo, girarlo, comparar imagen y texto extraído, saltar a su expediente, serie o entidades relacionadas.

## 6. Entidades RiC involucradas
Record (E04, el documento), Instantiation (E06, cada archivo), Record Set (E03, fondo, sección, serie y expediente), Activity y Mandate (serie de la TRD y su retención), Agent, Date, Place (en el panel de contexto).

## 7. Relaciones RiC involucradas
R024 includes or included (expediente → documento, creada al cargar), R025 has or had instantiation (documento → archivo, por la llave foránea), R015 (reescaneo derivado de otra instanciación), y todas las relaciones validadas del documento en el panel, agrupadas por categoría.

## 8. Funcionalidades
- Carga archivo por archivo al punto `ingesta_archivo`, con barra de avance real, un archivo a la vez, para que un archivo pesado o rechazado no bloquee a los demás.
- Validación antes de guardar: extensión admitida, tamaño máximo configurable (200 MB por defecto), archivo no vacío y contenido que corresponde a la extensión (firma de PDF, PNG, JPEG, TIFF, BMP; DOCX como ZIP con `word/document.xml`; texto sin bytes nulos; XML que empieza por `<`).
- Huella SHA-256 calculada por bloques antes de guardar; si ya existe un archivo con la misma huella, se rechaza diciendo cuál es.
- Tipo MIME verificado guardado en la instanciación (formato técnico de la especificación v5).
- Filas: cargando con porcentaje → «SHA-256 ✓» con enlace al visor, o fila roja con el motivo y «Quitar».
- «Enviar a preprocesamiento» deshabilitado mientras quede una carga en curso o no haya ninguna lista.
- Carpeta como expediente, partes de un mismo documento y reescaneo, también en la carga por archivo.
- Formulario de respaldo sin JavaScript con las mismas validaciones; no crea el expediente si ningún archivo sirve.
- Visor: PDF con pdf.js servido localmente; JPG y PNG directos; TIFF y BMP convertidos a PNG página a página al vuelo, sin copias; texto y DOCX como texto extraído. Página, zoom, ajustar al ancho, giro, teclas ← →, pestaña de texto extraído por página.
- Panel de contexto RiC: ruta fondo › sección › serie › expediente navegable, serie de la TRD con retención y fase, entidades relacionadas por categoría con enlace a su ficha, evidencia de cada relación en la página que se está viendo, instanciaciones con tipo MIME, tamaño, huella, condición de acceso, tipo de copia y derivación.
- Acceso: una sola regla (`ric/acceso_documentos.py`) para catálogo, visor y archivo original.

## 9. Flujos
Serie → expediente → archivos → cada fila avanza → «SHA-256 ✓» o fila roja → Quitar → Enviar a preprocesamiento → Preprocesamiento → nombre del archivo → visor. Desde la ficha del catálogo: «Ver documento». Desde análisis: «Ver documento en el visor».

## 10. Pantallas
`/ingesta/` (reescrita), `/documentos/<id>/visor/` (nueva), enlaces en preprocesamiento, análisis y ficha del catálogo.

## 11. UX/UI
El avance es el real de la subida; al 100 % dice «calculando huella…» mientras el servidor calcula el SHA-256. El motivo del rechazo se lee en la misma fila. Las flechas del visor esperan a que pdf.js abra el archivo. El PDF abre ajustado al ancho, sin recortes.

## 12. Modelo de datos
`Instantiation.tipo_mime` (nuevo). Acción de auditoría «consultar». Migración 0019. Sin tablas nuevas.

## 13. API
`POST /ingesta/archivo/` (multipart: `archivo`, `serie_id`, `expediente_id` | `expediente_nuevo` + `expediente_codigo` + `fecha_apertura`, `ruta`, `un_solo_documento` + `documento_id` + `nombre_documento`, `reemplaza_id`) → 201 con la fila en JSON, 400 con `error`, 401 sin sesión, 403 sin rol. `GET /documentos/<id>/visor/?inst=&pagina=`, `GET /ric/archivo/<id>/`, `GET /ric/archivo/<id>/pagina/<n>.png`.

## 14. Uso de IA
No aplica. El visor muestra la evidencia textual de las relaciones propuestas por el motor y validadas por una persona.

## 15. Seguridad
Contenido verificado contra la extensión, tamaño máximo, archivos vacíos rechazados, `X-Content-Type-Options: nosniff` y tipo MIME explícito al servir, control de rol en la carga (JSON 401/403) y en la entrega del original y de cada página. Corregido el hueco de descarga sin control de rol.

## 16. Auditoría (qué queda registrado)
Cada carga en la bitácora encadenada (archivo, formato, tipo MIME, tamaño, huella, expediente, serie) y como «crear» en `RegistroAuditoria`; cada apertura del visor como «consultar» (documento, archivo, página); cada acceso denegado al original.

## 17. Interoperabilidad
El archivo original se sirve con su tipo MIME real; la huella SHA-256 y el tipo MIME quedan listos para PREMIS (fixity, format).

## 18. Normativa aplicable
Acuerdo 003 de 2015 y Ley 594 de 2000 (integridad y autenticidad del documento electrónico), Ley 1712 de 2014 (condiciones de acceso), OWASP (carga de archivos), ISO 15489.

## 19. Arquitectura
| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Carga de archivos pesados | Formulario único; carga por archivo; carga por trozos reanudable (tus) | Carga por archivo con XHR y avance | Da avance real y aislamiento de errores sin infraestructura nueva; Django escribe a disco por encima de 2,5 MB | Un archivo de más de 200 MB por conexión inestable no se reanuda: se vuelve a subir. La carga reanudable queda como mejora si una entidad la necesita |
| Validación de tipo | Confiar en la extensión; `python-magic` (libmagic); firmas propias | Firmas propias de los 12 formatos admitidos | Cero dependencias del sistema operativo, cubre exactamente lo que se acepta | Un archivo con firma válida pero contenido malicioso interno no se detecta; no hay antivirus |
| Visor PDF | Visor nativo del navegador; pdf.js | pdf.js 3.11 servido localmente | Mismo comportamiento en todos los navegadores, sin salir a internet, permite sincronizar página con texto y evidencia | Tamaño de la librería (1,4 MB) |
| TIFF | Convertir y guardar copia; convertir al vuelo | Al vuelo, página a página | No se crean copias sin decisión archivística (las copias son instanciaciones con R015) | Costo de CPU por página vista; mitigado con caché del navegador |
| Tiempo de espera | 120 s; 600 s | 600 s en gunicorn | Una carga lenta de 200 MB no se corta | Un trabajador queda ocupado durante la subida hasta que haya proxy delante (Caddy, despliegue) |

## 20. Código
`ric/carga.py` (validación, huella, duplicados, registro), `ric/acceso_documentos.py` (regla única de acceso), `ric/vistas_ingesta.py` (`ingesta_archivo`, `ingesta`), `ric/vistas_visor.py`, `ric/templates/ric/ingesta.html`, `ric/templates/ric/visor.html`, `ric/static/ric/js/pdfjs/` (pdf.js con su licencia Apache 2.0), `ric/roles.py` (`requiere_rol_api`), migración 0019.

## 21. Pruebas
`tests/test_modulo1_ingesta.py` (16): archivo válido con huella y fila, contenido que no coincide con la extensión (PDF, PNG, DOCX, texto binario, vacío), formato no soportado y tamaño máximo, duplicado por huella, partes de un documento y carpeta como expediente, PNG/TIFF/DOCX válidos, sesión y rol, pantalla con botón y límites, visor PDF con contexto RiC y auditoría, relaciones y evidencia por página, TIFF convertido a PNG, consulta solo publicado y abierto (visor y original), texto como texto, firmas unitarias, TIFF sin preprocesar hojeado completo. Además se probó el flujo real en Chromium con una conexión limitada: avance, botón bloqueado, fila roja, Quitar, preprocesamiento y visor.

## 22. Criterios de aceptación (historia de usuario 1)
- Archivo soportado → SHA-256, fila en la tabla, usuario, fecha y hora (RF-M1-01, 02, 04): cumplido.
- Archivo no soportado → rechazado antes de continuar, motivo en la misma fila (RF-M1-03): cumplido, y extendido a contenido falso y duplicados.
- Algún archivo cargando → «Enviar a preprocesamiento» deshabilitado: cumplido.

## 23. Evidencia concreta de aplicación de RiC
En el visor de «oficio prueba» el panel muestra la ruta Ministerio de Ambiente › Despacho del Ministro › Derechos de petición › Expediente, la serie TRD 1000-24 con «gestión 3 años · central 7 años · Selección», la relación R024 que liga el documento a su expediente, y la instanciación con su tipo MIME y su huella. Cada elemento es un enlace a su entidad RiC, no un texto.

## Qué no hace (y qué pasa en cada error)
- El preprocesamiento sigue dentro de la petición web: con varios archivos grandes, «Enviar a preprocesamiento» puede tardar minutos. Es el alcance del módulo 2 (Celery y Redis).
- No hay antivirus ni carga reanudable.
- Si se pierde la conexión durante una carga, esa fila queda roja con «se perdió la conexión»; los demás archivos siguen.
- Si expira la sesión durante una carga larga, el servidor responde 401 y la fila lo dice.
