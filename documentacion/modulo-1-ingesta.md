# Módulo 1 · Ingesta y digitalización

**Estado:** versión 1.1 (confianza del reconocimiento óptico de caracteres), pendiente de validación.

**Qué cambió en la versión 1.1.** Antes, el OCR extraía el texto pero no guardaba qué tan confiable era la lectura. Ahora:

- cada documento leído por OCR guarda su confianza (0 a 100);
- si queda por debajo de un umbral configurable, recibe la marca `ocr_baja_confianza` y aparece en el panel de alertas;
- descripción muestra la confianza y una advertencia junto al texto, antes de que el archivista valide cualquier propuesta del motor.

---

## 1. Propósito

Recibe cualquier archivo que el archivista cargue y lo prepara para el resto del sistema:

1. calcula su huella digital;
2. identifica su formato técnico contra el registro PRONOM;
3. extrae su texto cuando hace falta;
4. deja el documento en un estado a partir del cual trabaja el módulo de descripción.

No describe nada ni decide nada sobre el contenido.

## 2. Auditoría (qué se revisó antes de construirlo)

- **Documentos revisados:** el prompt del módulo 1, el diseño consolidado (Parte 2) y el mockup «Sistema RIC · Ingesta» (Cargar documentos y Cola de ingesta).
- **Lo que había en el andamiaje:**
  - una sola ruta de carga, con la lista de formatos cerrada a 6;
  - el archivo se leía entero en memoria;
  - un duplicado se rechazaba con un error en vez de preguntar al archivista;
  - el nombre del archivo en disco era la huella, así que dos cargas del mismo archivo compartían archivo físico;
  - sin estados ni procesamiento en segundo plano.

  Todo esto se reemplazó.
- **Lo que no existía y el módulo necesita:**
  - **Fondo.** El mockup muestra un «fondo histórico activo», y los duplicados se buscan «en el fondo», pero ningún documento dice quién crea el fondo. Decisión: lo registra el administrador (§19).
  - **Panel central de alertas.** La Definición de Terminado lo exige ya, aunque la decisión «entidad propia o auditoría» el prompt se la asigna al módulo 4. Se tomó aquí porque se necesita ahora (§19). El módulo 4 debe reutilizarla, no reabrirla.
  - **Tabla de parámetros**, para el límite de tamaño configurable.

## 3. Problema que resuelve

Sin una ingesta confiable, el resto del sistema trabaja sobre archivos sin integridad verificable, sin formato conocido y sin texto. En particular:

- el módulo de preservación no tendría sobre qué vigilar;
- el motor de descripción no tendría texto que analizar.

## 4. Usuarios

| Rol | Qué hace |
|---|---|
| Archivista | Carga, ve la cola, decide duplicados, reintenta o descarta errores, atiende alertas |
| Administrador | Lo mismo, y además registra fondos y cambia el límite de tamaño |
| Revisor (provisional) | Ve la cola y el panel de alertas, sin actuar |
| Consulta | No entra a ingesta |

## 5. Casos de uso

1. Cargar uno o varios archivos, arrastrándolos o con el explorador, con o sin expediente de destino.
2. Ver el avance del procesamiento de cada archivo.
3. Decidir sobre un posible duplicado: es distinto (continúa) o cancelar (se elimina).
4. Reintentar o descartar un documento con error.
5. Revisar en el panel de alertas los documentos cuyo formato no se identificó.
6. (Administrador) Registrar el fondo histórico y cambiar el tamaño máximo por archivo.

## 6. Entidades RiC involucradas

- **Instantiation (RiC-E06).** Se crea al cargar, con sus atributos técnicos desde el primer instante: formato (identificador PRONOM, nombre, versión, MIME), tamaño, huella digital y algoritmo, y fecha de carga. Queda sola, sin Record Resource, hasta que la vincule el módulo de descripción.
- **Record Resource (RiC-E02), nivel fondo.** Es un Record Set de tipo fondo que registra el administrador; aquí se usa solo como contenedor. El expediente de destino también es un Record Resource, pero lo crea el módulo de descripción. Mientras no existan expedientes, el selector ofrece solo «Sin asignar, decidir en descripción».

## 7. Relaciones RiC involucradas

- Ninguna relación RiC se crea en este módulo, como indica el prompt.
- El expediente de destino queda como una **intención** (`expediente_destino_id`), no como relación. La relación Instantiation → Record Resource (RiC-R025 *has instantiation*) la crea descripción al publicar.
- La inclusión (RiC-R024) queda preparada en `incluido_en_id` para cuando descripción cree los niveles inferiores.

## 8. Funcionalidades

- **Carga de cualquier formato**, en lote:
  - cada archivo sube con su propia barra de avance;
  - los que exceden el límite se marcan en rojo antes de subir, sin bloquear a los demás;
  - el servidor vuelve a verificar el límite;
  - los archivos vacíos se rechazan.
- **Procesamiento automático**, sin intervención, en un proceso aparte (el «trabajador»):
  1. huella SHA-256;
  2. duplicado exacto en el mismo fondo;
  3. formato contra PRONOM con Siegfried;
  4. texto: capa de texto si existe, OCR si es imagen o PDF escaneado.
- **Estados:** `procesando`, `duplicado_pendiente`, `error` y `listo_para_descripcion`. No hay cola ni traspaso: el estado decide qué pantalla muestra el documento.
- **Formato no identificado:**
  - el documento llega igual a `listo_para_descripcion`, con `formato_no_identificado = verdadero`;
  - se crea una alerta en el panel central.

  Se considera no identificado si Siegfried no encuentra firma, o si solo coincide la extensión del nombre: eso no es una identificación contra las firmas del registro.
- **Errores legibles:** archivo dañado, vacío o ilegible, PDF protegido, herramienta no disponible en el servidor. Nunca se muestra una traza técnica.
- **Confianza del OCR (versión 1.1):**
  - Tesseract devuelve, en la misma pasada que el texto, una tabla con la confianza de cada palabra;
  - la confianza del documento es el promedio de todas sus palabras en todas sus páginas, de 0 a 100, y se guarda junto con cuántas palabras la sostienen;
  - si el documento traía capa de texto, el campo queda **vacío**, no en cero: cero significa que el OCR no reconoció nada; vacío, que no se usó OCR;
  - por debajo del umbral, el documento recibe la marca `ocr_baja_confianza` y una alerta ámbar, con un enlace directo a la cola de descripción;
  - la marca nunca detiene la transición a `listo_para_descripcion`: es una señal para leer con cuidado, no un bloqueo.
- **Parámetros configurables:** límite por archivo (500 MB por defecto) y confianza mínima del OCR (70 sobre 100 por defecto). Solo el administrador los cambia, en la misma pantalla de carga. El umbral nuevo rige para lo que se procese después; lo ya procesado conserva su marca.
- **Almacenamiento** en `DIRECTORIO_ALMACENAMIENTO`, con el nombre propio de la instanciación (nunca el nombre original).
- **Panel central de alertas:** pendientes y atendidas; una alerta se marca atendida con una nota y nunca se borra.

## 9. Flujos

**Carga**

1. El administrador ya registró el fondo.
2. En «Cargar documentos», el archivista elige, si quiere, el expediente de destino.
3. Arrastra o selecciona los archivos y ve la lista con el peso de cada uno; los que exceden el límite aparecen en rojo con «Demasiado pesado».
4. Pulsa «Cargar N archivos». Cada archivo sube con su barra y se marca «Cargado».
5. Aparece el aviso «N archivos cargados. El sistema ya los está procesando.»

**Procesamiento**

1. El trabajador toma el documento en espera más antiguo.
2. La barra avanza paso a paso: «Calculando huella digital», «Buscando duplicados en el fondo», «Identificando formato (PRONOM)», «Reconociendo texto (OCR) · página 3 de 12».
3. El documento termina en `listo_para_descripcion` (desaparece de la cola), en `duplicado_pendiente` o en `error`.

**Duplicado**

1. La cola muestra: «La misma huella digital ya existe en el fondo: «X», cargado el …».
2. «Es distinto, continuar»: sigue desde la identificación de formato, sin recalcular la huella.
3. «Cancelar carga»: se elimina el registro y el archivo físico. Es la única eliminación real del módulo, porque el archivo nunca llegó a integrarse al fondo.

**Error**

- «Reintentar»: vuelve a procesar desde el principio (huella incluida).
- «Descartar»: se elimina igual que un duplicado cancelado.

**Cola vacía**

Aparece un estado explícito: «No hay nada pendiente en la ingesta. Todo lo cargado ya pasó a descripción», con cuántos documentos quedaron listos en las últimas 24 horas.

## 10. Pantallas

| Ruta | Pantalla | Quién |
|---|---|---|
| `/ingesta` pestaña «Cargar documentos» | Selector de expediente, zona de arrastre, lista previa y barra de confirmación | Archivista, administrador |
| `/ingesta` pestaña «Cola de ingesta» (con contador) | Tarjetas Procesando, Posible duplicado y Con error, o estado vacío | Archivista, administrador, revisor |
| `/alertas` | Panel central de alertas (Pendientes / Atendidas) | Archivista, administrador, revisor |

En todas las pantallas del sistema la barra superior muestra el **fondo activo** (con selector si hay varios) y el botón **Alertas** con su contador.

## 11. UX/UI

- **Mockup:** «Sistema RIC · Ingesta» (pestañas, zona punteada, filas con ícono de archivo y peso, insignia roja «Demasiado pesado», barra de confirmación «N de M listos», barras de avance, botones de decisión). Se mantiene la paleta de tono medio que eligió la autora.
- **Avance en vivo:** la cola se actualiza cada 3 segundos mientras hay algo procesándose, y cada 20 cuando no.
- **Confirmaciones:** «Cancelar carga» y «Descartar» piden confirmación, porque borran el archivo.
- **Móvil:** sin desplazamiento horizontal a 390 px.

## 12. Modelo de datos

Migraciones `alembic/versions/0002_ingesta.py` y `0010_ocr_y_codigos_ric_o.py` (versión 1.1).

| Tabla | Campos clave |
|---|---|
| `recursos_documentales` | id, nivel (fondo…unidad_documental), titulo, fechas_extremas, incluido_en_id, fondo_id, creado_por_id. Descripción la ampliará |
| `instanciaciones` | fondo_id, expediente_destino_id, nombre_original, ruta, tamano_bytes, **estado**, paso, progreso, detalle_paso, tomado_en, intentos, mensaje_error, **huella**, algoritmo_huella, duplicado_de_id, duplicado_confirmado, **formato_puid, formato_nombre, formato_version, formato_mime, formato_base, formato_no_identificado, herramienta_identificacion**, texto_extraido, origen_texto, paginas, **confianza_ocr, palabras_ocr, ocr_baja_confianza** (1.1), cargado_por_id, cargado_en, procesado_en |
| `alertas` | tipo, severidad, modulo, fondo_id, entidad_tipo, entidad_id, mensaje, detalle, creada_en, atendida_en, atendida_por_id, nota_atencion. Índice único parcial: nunca dos alertas pendientes del mismo tipo sobre la misma entidad |
| `parametros` | clave, valor (JSON), actualizado_en, actualizado_por_id. Valores por defecto: `ingesta_limite_mb = 500`, `ingesta_umbral_ocr = 70` |

`herramienta_identificacion` guarda con qué se identificó el formato, por ejemplo «siegfried 1.11.9 · PRONOM DROID_SignatureFile_V125.xml; container-signature-20260119.xml». Es trazabilidad PREMIS: el módulo de preservación sabrá contra qué versión del registro se identificó cada archivo.

## 13. API

Todas bajo `/api`.

| Método y ruta | Acceso | Qué hace |
|---|---|---|
| `POST /ingesta/cargar` | Archivista, administrador | Multipart: `archivos` (uno o varios), `fondo_id` y `expediente_id` opcional. Devuelve el resultado por archivo (aceptado con su id, o rechazado con el motivo) |
| `GET /ingesta/cola?fondo_id=` | + revisor | Procesando (con avance), duplicados (con la referencia a la original) y errores (con el mensaje). **Nunca** incluye `listo_para_descripcion` |
| `POST /ingesta/{id}/confirmar-duplicado` | Archivista, administrador | Continúa el procesamiento |
| `DELETE /ingesta/{id}` | Archivista, administrador | Cancela un duplicado o descarta un error: elimina el registro y el archivo |
| `POST /ingesta/{id}/reintentar` | Archivista, administrador | Reprocesa desde el principio un documento en error |
| `GET /ingesta/limite` / `PUT /ingesta/limite` | Lectura: ingesta. Cambio: solo administrador | Tamaño máximo por archivo |
| `GET /ingesta/umbral-ocr` / `PUT /ingesta/umbral-ocr` | Lectura: ingesta. Cambio: solo administrador | Confianza mínima del OCR, de 0 a 100 (1.1). El cambio queda en auditoría con el valor anterior y el nuevo |
| `GET /fondos`, `POST /fondos`, `GET /fondos/{id}/expedientes` | Leer: cualquier sesión. Registrar: administrador | Fondos y expedientes de destino |
| `GET /alertas?fondo_id=&atendidas=`, `POST /alertas/{id}/atender` | Leer: archivista, administrador, revisor. Atender: archivista, administrador | Panel central de alertas |

**Nota sobre el revisor.** El prompt de ingesta dice que los endpoints son para «archivista o administrador». El prompt de autenticación le da al revisor lectura en todos los módulos de trabajo. Se aplicó el de autenticación, que es la matriz única: el revisor **ve** la cola pero no ejecuta ninguna acción. Si usted prefiere que no la vea, es un cambio de una línea en la matriz.

## 14. Uso de IA

Ninguna decisión de IA en esta etapa, como exige el diseño consolidado. El OCR (Tesseract) es reconocimiento de caracteres, no un modelo que decida algo archivístico.

## 15. Seguridad

- **Sesión antes que archivo:** la carga verifica sesión y rol **antes** de leer el archivo. Nadie sin permiso puede hacer que el servidor reciba 500 MB, y una subida larga no se rechaza porque el token venció a mitad de camino.
- **Memoria:** el archivo se copia a disco por bloques de 1 MB, sin cargarlo en memoria, y se corta al pasar el límite.
- **Nombres:** el nombre original nunca se usa como ruta. Se toma solo el último tramo (`../../etc/x` queda en `x`), se guarda en la base de datos, y el archivo en disco se llama con el identificador de la instanciación. Hay una comprobación de que ninguna ruta sale del almacenamiento.
- **Errores:** los mensajes son legibles; el detalle técnico queda solo en el registro del servidor.
- **Trabajador:** es un proceso aparte y sin puertos. Si el OCR de un archivo pesado falla, la web sigue respondiendo.
- **Eliminación real:** solo en cancelación de duplicado y descarte de error, con registro en auditoría del nombre, el tamaño y la huella.

## 16. Auditoría (qué queda registrado)

En el registro único, de solo anexar:

- `documento_cargado`: nombre, tamaño, fondo, expediente;
- `carga_rechazada`: nombre y motivo;
- `duplicado_confirmado`: estado anterior y nuevo;
- `carga_cancelada` y `carga_descartada`: todos los datos del documento eliminado;
- `reintento`;
- `parametro_cambiado`: límite anterior y nuevo;
- `fondo_registrado`;
- `alerta_atendida`: con la nota.

## 17. Interoperabilidad

- **PRONOM:** el identificador de formato (PUID, por ejemplo `fmt/18` para PDF 1.4) es el estándar internacional de preservación digital. Lo entienden DROID, Archivematica, Preservica y cualquier sistema OAIS.
- **Huella:** SHA-256 con el algoritmo registrado, como exige PREMIS (*fixity*).
- **Parámetros de OCR:** el idioma se cambia con `RICORA_IDIOMA_OCR`, que por defecto es `spa`.

## 18. Normativa aplicable

- **Acuerdo 006 de 2014 del AGN (Sistema Integrado de Conservación):** integridad verificable desde el ingreso mediante la huella.
- **NTC-ISO 14721 (OAIS):** este módulo cubre la función de *Ingesta* y alimenta a *Almacenamiento* y *Planeación de la preservación*.
- **PREMIS:** atributos de objeto registrados en la Instantiation: formato, tamaño, huella y algoritmo, y herramienta de identificación.
- **Ley 1712 de 2014:** todo queda en la trazabilidad de auditoría.

## 19. Arquitectura

- **Web (FastAPI):** recibe la carga y responde de inmediato con el id de cada instanciación.
- **Trabajador (`app/trabajador.py`, mismo código, contenedor aparte):** toma los documentos en `procesando` con `SELECT … FOR UPDATE SKIP LOCKED` y los procesa de a uno.
- **Recuperación ante reinicios:** si el servidor se reinicia a mitad de un documento, el trabajador lo retoma. Cada paso actualiza una señal de vida, y un documento sin señal por 10 minutos se vuelve a tomar.
- **Imagen Docker:** incluye Siegfried compilado desde su código fuente (con el archivo de firmas de su versión) y Tesseract con idioma español.

### Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| **Herramienta de identificación de formato contra PRONOM** (exigida por el prompt, §7) | (a) **DROID** 6.x (Archivos Nacionales del Reino Unido, Java, se invoca como proceso externo); (b) **Siegfried** (binario Go, mismas firmas DROID de PRONOM, incluidas las de contenedor); (c) **FIDO** (Python, Open Preservation Foundation) | **(b) Siegfried 1.11.9** con firmas DROID V125 y contenedor 20260119 | Da el mismo resultado PRONOM que DROID sin exigir Java: DROID necesita una JVM de 200–400 MB de memoria, que en un servidor de 2 GB compite con la base de datos y el OCR. Es un solo binario de 12 MB, rápido en lotes, con salida JSON fácil de leer. Se compila en la imagen desde el código fuente, con la versión fija. FIDO es más lento y su soporte de firmas de contenedor es menor | Dependencia de un binario externo (no una librería nativa de Python): si falta, el documento queda en error con el mensaje «Avise al administrador», nunca identificado a medias. Las firmas quedan congeladas en la versión de la imagen; actualizarlas es subir `SIEGFRIED_VERSION` en el Dockerfile |
| Cuándo se considera «no identificado» | Solo si Siegfried dice `UNKNOWN`; también cuando la coincidencia es solo por extensión | **También solo por extensión** | Una coincidencia por el nombre del archivo no es una identificación contra el registro; el prompt prohíbe identificar por extensión | Algún formato legítimo sin firma en PRONOM queda marcado. Es justamente lo que el panel debe mostrar para revisión |
| Procesamiento asíncrono | FastAPI BackgroundTasks (dentro del proceso web); Celery + Redis; **trabajador propio que consulta la base de datos** | **Trabajador propio** | El estado `procesando` ya es la cola, así que no hace falta otra. Sobrevive reinicios (BackgroundTasks pierde el trabajo). No suma Redis ni Celery (unos 100 MB) al servidor de 2 GB. Un fallo del OCR no tumba la web | Procesa de a un documento; un lote grande de PDF escaneados tarda (unos 5–10 s por página en 1 vCPU). Si hiciera falta paralelismo, basta levantar otro trabajador: `SKIP LOCKED` ya lo admite |
| **Motor de OCR, con confianza real por palabra** (prompt 1.1, §7, segunda decisión) | (a) **Tesseract 5**: confianza por palabra en su salida TSV, local, sin costo; (b) **servicio en la nube** (Google Document AI, AWS Textract, Azure): mejor con manuscritos, cobra por página y saca el documento del servidor; (c) **solución mixta**: Tesseract para lo mecanografiado y nube para lo manuscrito | **(a) Tesseract 5, idioma español, salidas `txt` y `tsv` en una sola pasada** | Cumple el requisito no negociable de una confianza real por palabra. Se mantienen dos reglas del proyecto: ningún recurso pagado y ningún documento enviado fuera sin necesidad. La solución mixta exigiría pagar por página y decidir antes qué documento es manuscrito. En cambio, la confianza misma hace esa separación: un manuscrito mal leído queda bajo el umbral y llega marcado a descripción | Con manuscritos, la transcripción será pobre. El sistema no lo oculta: los marca. Si la evaluación de la tesis muestra que el fondo es mayoritariamente manuscrito, la opción (c) queda como trabajo futuro y se documenta como limitación |
| Cómo resumir la confianza de un documento | Promedio por palabra; por línea; mediana; mínimo por página | **Promedio por palabra de todas las páginas, con el número de palabras** | Es lo que pide el prompt. Se guarda también cuántas palabras lo sostienen: un 90 sobre tres palabras no vale lo mismo que sobre tres mil | Un documento largo con una página muy mala puede quedar sobre el umbral; se verá en el texto, pero no en la marca. Si pasa en el fondo de prueba, se agrega la peor página como dato aparte |
| Documento sin OCR | Confianza 0; 100; vacío | **Vacío** | Cero significaría una extracción fallida; vacío dice que no aplicó, como exige el prompt | Ninguno |
| Documentos leídos por OCR antes de la versión 1.1 | Inventar un valor; dejarlos vacíos | **Vacíos** | No se inventa una confianza que no se midió; un reintento la calcula | Hasta reprocesarlos, no aparecen como dudosos |
| Texto y páginas de PDF | poppler (`pdftotext`, `pdftoppm`); **pypdfium2** | **pypdfium2** | Librería de Python con PDFium incluido: extrae la capa de texto y pasa cada página a imagen sin programas externos, página por página y sin cargar el PDF entero en memoria | Un PDF con capa de texto muy pobre (menos de 25 caracteres por página) se trata como escaneado y pasa por OCR |
| Mecanismo de alertas del panel central (el prompt 4 pide decidirlo; se necesitaba ya aquí) | Entidad propia `Alerta`; reutilizar auditoría filtrando por tipo de evento | **Entidad propia** | Una alerta tiene ciclo de vida (pendiente → atendida, con quién y nota), y la auditoría es de solo anexar e inmutable. Mezclarlas obligaría a reconstruir el estado a partir de eventos en cada consulta. Sirve igual para preservación e instrumentos | El módulo de instrumentos debe reutilizar esta tabla, no reabrir la decisión |
| Quién crea el fondo | Descripción; el administrador | **El administrador** (botón en Ingesta) | El fondo es el punto de partida: sin él no hay dónde cargar ni contra qué buscar duplicados. Descripción creará los niveles inferiores | Si usted prefiere otro lugar para registrar fondos, es un cambio de pantalla, no de datos |

## 20. Código (dónde vive, cómo se organiza)

```
app/models/instanciacion.py, recurso_documental.py, alerta.py, parametro.py
app/servicios/almacen.py        guardar por bloques, rutas seguras, borrar
app/servicios/formato.py        Siegfried / PRONOM
app/servicios/texto.py          capa de texto, OCR página por página con confianza por palabra
app/servicios/procesamiento.py  los 4 pasos, estados, errores legibles
app/servicios/alertas.py        panel central (crear, atender)
app/servicios/parametros.py     parámetros del administrador
app/trabajador.py               proceso en segundo plano
app/routers/ingesta.py, fondos.py, alertas.py
frontend/src/pages/Ingesta.tsx, Alertas.tsx; lib/fondo.tsx; components/RegistrarFondo.tsx
```

## 21. Pruebas

31 pruebas en `tests/test_ingesta.py`, **con Siegfried y Tesseract reales**, sin simulación. Si faltan las herramientas, las pruebas fallan: no se saltan. Se exigen en GitHub Actions antes de cada despliegue.

- **Carga única hasta listo:** huella SHA-256 correcta, PUID `x-fmt/111`, herramienta registrada, texto, archivo guardado con nombre propio, evento de auditoría.
- **Tipos de archivo:** PDF digital con capa de texto; PDF escaneado con OCR (reconoce «ARCHIVO MUNICIPAL»); imagen PNG con OCR.
- **Lote mixto:** texto, PDF dañado y PNG quedan cada uno en su estado. El mensaje de error es legible y sin traza.
- **Límite de tamaño:**
  - un archivo de más de 1 MB con el límite en 1 MB se rechaza sin afectar a los demás del lote, y no se guarda;
  - el cambio del límite queda auditado con valor anterior y nuevo;
  - el valor por defecto es 500 MB;
  - solo el administrador lo cambia, y un valor inválido se rechaza.
- **Casos de borde:** archivo vacío rechazado; nombre malicioso (`../../etc/…`) contenido dentro del almacenamiento.
- **Duplicados:**
  - confirmar lleva hasta listo, y no se puede confirmar dos veces;
  - cancelar elimina el registro y el archivo, mientras la original queda intacta;
  - el mismo archivo en otro fondo no es duplicado.
- **Formato no identificado:** llega a listo con la marca, aparece en `/api/alertas`, se atiende con nota y queda en auditoría.
- **Errores:**
  - reintento de un documento en error: vuelve a empezar desde la huella y llega a listo;
  - descartar un error elimina registro y archivo;
  - no se puede descartar ni reintentar lo que ya está listo;
  - sin Siegfried, el error dice «Avise al administrador».
- **La cola nunca devuelve** un documento en `listo_para_descripcion`.
- **Confianza del OCR (1.1):**
  - la confianza guardada es exactamente el promedio de las confianzas por palabra que dio Tesseract, y el número de palabras coincide;
  - un PDF con capa de texto deja la confianza vacía, no en cero;
  - una copia borrosa (confianza cercana a 56) queda marcada, aparece en el panel de alertas, llega igual a descripción y la cola de descripción recibe la confianza y la marca;
  - un OCR que no reconoce ninguna palabra da 0, distinto de vacío;
  - el umbral vale 70 por defecto; solo el administrador lo cambia (403 para el archivista, 422 fuera de 0 a 100), el cambio queda en auditoría, y con umbral 40 la misma copia ya no queda marcada;
  - el reintento borra la confianza anterior para volver a calcularla.
- **Trabajador:** no toma un documento que otro está procesando, y retoma uno abandonado hace más de 10 minutos.
- **Expedientes y fondos:** expediente de destino opcional; el de otro fondo se rechaza; solo el administrador registra fondos, sin nombres repetidos.
- **Permisos:**
  - sin sesión, todos los endpoints responden 401;
  - el rol consulta recibe 403 en todos;
  - el revisor ve la cola y recibe 403 en toda acción, incluida atender alertas;
  - la prueba de barrido de rutas del módulo de autenticación también cubre las rutas nuevas.

**Verificación visual** en navegador real, con el servidor y el trabajador corriendo de verdad:

- sin fondo;
- registrar fondo;
- cambiar el límite a 2 MB;
- seis archivos, uno «Demasiado pesado»;
- subida;
- cola procesando;
- cola con duplicado y error;
- panel de alertas con el formato no identificado;
- vista en móvil.

## 22. Criterios de aceptación

| Criterio (prompt §10–11) | Cumple |
|---|---|
| Carga única con transición completa hasta `listo_para_descripcion` | ✓ |
| Lote mixto con cada archivo en su estado de forma independiente | ✓ |
| Rechazo por tamaño sin afectar a los demás del lote | ✓ |
| Duplicado exacto por huella, con las dos rutas (confirmar y cancelar) | ✓ |
| Formato no identificable: llega a listo con la marca y aparece en el panel de alertas | ✓ |
| Reintento de un documento en error | ✓ |
| `GET /ingesta/cola` nunca devuelve `listo_para_descripcion` | ✓ |
| Todos los endpoints rechazan sin token o con rol sin permiso | ✓ |
| Herramienta de identificación documentada con tabla de decisión | ✓ (§19) |
| El panel central de alertas ya muestra el formato no identificado | ✓ |
| Auditoría registra cada carga, confirmación de duplicado y descarte | ✓ |
| Límite configurable (500 MB por defecto) y `DIRECTORIO_ALMACENAMIENTO` reutilizado | ✓ |
| (1.1) Todo texto por OCR guarda su confianza como promedio por palabra; con capa de texto queda vacío, no en cero | ✓ |
| (1.1) Umbral configurable, 70 por defecto; la marca `ocr_baja_confianza` aparece en el panel de alertas y no bloquea | ✓ |
| (1.1) Descripción muestra la confianza y la advertencia junto al texto | ✓ |
| (1.1) Motor de OCR documentado con tabla de decisión, considerando el fondo mixto | ✓ (§19) |

**Pendiente honesto.** La imagen Docker instala Tesseract desde los repositorios de Debian. En el entorno donde se construyó no se pudo comprobar ese paso, porque la red bloquea esos servidores; sí se comprobaron la compilación de Siegfried en Docker y el funcionamiento de ambas herramientas fuera de Docker. El registro del despliegue imprime la versión de Siegfried y los idiomas de Tesseract instalados en el servidor, como verificación.

## 23. Evidencia concreta de aplicación de RiC

Después de cargar, la Instantiation existe sola, con sus atributos técnicos de RiC-CM (formato, extensión, identificador y fecha), en espera de su Record Resource. Por ejemplo:

```
Instantiation 7f3c…  estado: listo_para_descripcion
  nombre_original: Oficio_114_1948.pdf      fondo: Correspondencia municipal (Record Set, nivel fondo)
  formato: fmt/18 · Acrobat PDF 1.4 · application/pdf   (PRONOM, siegfried 1.11.9, DROID V125)
  tamaño: 671 B · huella SHA-256: 4b1e…      cargado: 30-09-2026 por Marlín Martínez
  texto: capa_de_texto, 1 página             record_resource: (ninguno aún: lo crea descripción)
  confianza OCR: (vacía: no hubo OCR)
```

Una copia borrosa del mismo oficio, leída por OCR, queda así:

```
Instantiation 2a91…  estado: listo_para_descripcion
  texto: ocr, 1 página · confianza OCR 56,3 / 100 sobre 9 palabras · ocr_baja_confianza: sí (umbral 70)
  alerta: «copia_borrosa.png: el texto se leyó por OCR con confianza 56,3 sobre 100 (umbral 70)…»
```

La confianza es un dato técnico de la Instantiation, no del contenido. Califica la transcripción derivada del soporte y no se exporta con la descripción.

Esto es la separación de RiC-CM entre el contenido intelectual (Record) y su soporte técnico (Instantiation): el mismo oficio podrá tener después una segunda Instantiation (por ejemplo, su migración a PDF/A en preservación) sin duplicar su descripción.
