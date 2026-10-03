# Rediseño de navegación y experiencia de usuario

**Versión:** 1.
**Estado:** entregado, pendiente de validación por la autora.
**Estructura:** los diecinueve puntos del prompt «Rediseño de navegación y experiencia de usuario de RICORA», con las desviaciones declaradas y sus tablas de decisión.

---

## Antes de leer: lo que el prompt daba por hecho y no era cierto

| Lo que dice el prompt | Lo que hay en el sistema | Qué se hizo |
|---|---|---|
| Reutilizar «el visor con soporte IIIF que el módulo de instrumentos ya especifica en su sección sexta sexies» | **No existía ningún visor IIIF**, ni un servidor de imágenes IIIF. Lo que sí existía era el renderizador de páginas del espacio de descripción, que convierte PDF e imágenes a PNG para recortar partes documentales | Se generalizó **ese** renderizador en un visor único, que se usa en la cola de ingesta, en Por describir, en el espacio de trabajo y en la ficha del catálogo. **No es IIIF** y no se presenta como tal (§5 y tabla de decisión) |
| «en la ficha de instrumentos donde ya estaba previsto» | La ficha del catálogo no tenía visor | Se agregó, con su propia regla: solo el archivo de una descripción publicada |
| Un elemento «Inicio» en la barra | No hay pantalla de inicio. Cada rol entra a su primer módulo | No se inventó. Si la autora la quiere, es una pantalla nueva |
| «quince hallazgos como los que este panel ya tiene» | Son **14** | Sin efecto en el diseño: todos contraídos por defecto |
| El resultado del último simulacro de restauración de la base de datos | El respaldo probado de la base de datos **no está construido** | La línea de tiempo lo muestra como **pendiente**, sin inventar un resultado |
| Documentos «marcados en riesgo de seguridad» | No existe una marca de riesgo de *seguridad*. Existen el riesgo de **integridad** (la huella no coincide) y el de **obsolescencia** del formato | Se muestran los dos, con esos nombres y con enlace a Preservación. Si la autora quiso decir otra cosa (por ejemplo, archivos con macros), es una detección nueva |
| La exportación del fragmento del grafo con `POST` | Ver `grafo-contexto.md` | `GET` |

---

## 1. Qué hace

Unifica la navegación en un solo árbol de submódulos y resuelve con un patrón único el historial que crece sin límite. También evita que ninguna pantalla quede en blanco sin explicación e integra un visor de documentos donde hacía falta. **Ningún módulo cambia lo que hace.**

## 2. Los cuatro problemas transversales

1. **Dos mapas de navegación:** la barra lateral llevaba al módulo y una fila de pestañas, a la vista. Además, las pestañas de Ingesta, Descripción, Vocabularios y Usuarios **no quedaban en la dirección de la página**: no se podía enlazar una vista ni volver a ella con «atrás».
2. **Un historial sin límite y sin exportación completa:** Mi trazabilidad paginaba con «Ver más».
3. **Espacio vacío** bajo las vistas cortas.
4. **No había un visor** para mirar un documento sin descargarlo, salvo para recortar partes.

## 3. Barra lateral como árbol de submódulos

- **Módulos con vistas:** cada uno es un botón expandible (flecha, `aria-expanded`) y sus vistas son enlaces indentados:
  - Ingesta: Cargar documentos, Cola de ingesta;
  - Descripción: Por describir, Descritas;
  - Vocabularios: Vocabulario, Sugerencias de fusión;
  - Instrumentos: Catálogo, Grafo, Inventario, Guía, Índice, RiC-O;
  - Preservación: Panel, Configuración;
  - Auditoría: Mi trazabilidad, Panel consolidado, Decisiones de IA, Hallazgos de conformidad;
  - Usuarios: Usuarios, Roles y permisos.
- **Evaluación** es un enlace simple, sin flecha.
- **Cada rol ve solo sus vistas.** Si a un rol le queda una sola vista, el módulo es un enlace simple. Por ejemplo, Auditoría para quien solo ve su trazabilidad, o Preservación sin Configuración para quien no administra.
- **Expansión:**
  - el módulo de la vista activa se **expande solo** al llegar, también desde un enlace directo;
  - los demás empiezan contraídos;
  - **acordeón: un solo módulo abierto a la vez.** Al pasar a otro módulo, o al tocar el nombre de otro, las vistas del anterior se esconden solas; tocar el abierto lo cierra. *(Cambio pedido por la autora tras ver la primera versión: con varios abiertos la barra se volvía una lista larga. El prompt permitía varios a la vez.)*
- **Vista activa:** fondo distinto y barra de acento a la izquierda, con `aria-current="page"`.
- **Cada vista vive en la dirección:** `?vista=` para las vistas internas, y una ruta propia para Configuración de preservación. El componente `useVista` es el único que las lee. Si se pide una vista que el rol no tiene, cae en la primera permitida.
- **Las filas de pestañas horizontales desaparecieron** de las siete pantallas. El encabezado muestra el título de la vista y su descripción.
- La **Configuración de preservación** dejó de ser un botón suelto en la esquina.
- **Pantallas angostas** (760 px o menos): el árbol se vuelve un **menú desplegable** (botón «Menú»), sin desplazamiento horizontal. Se comprobó a 390 px.
- La **ambulancia de ayuda** ya distingue cada vista, porque ahora todas están en la dirección.

## 4. Historial reciente con exportación completa a Excel

- **Componentes compartidos:** `ExportarExcel` (botón «Exportar todo a Excel») y `AvisoReciente` («Se muestran los N más recientes de M. El resto está en la exportación a Excel.»).
- **Construcción del archivo:** todas las hojas nuevas se arman con `app/servicios/hoja.py`, en un solo lugar. Encabezado en negrita, fechas en hora de Bogotá, columnas con ancho legible y la primera fila fija.
- **Cómo exporta:** la exportación **reutiliza los filtros de la vista**, sin un segundo juego, y trae **todo** lo que los cumple, no solo lo visible.

| Vista | Visibles | Exportación |
|---|---|---|
| Mi trazabilidad | **15** («Ver más» eliminado: la vista ya no pagina) | Todas las acciones de quien consulta que cumplen los filtros. Columnas extra: identificador del evento, código de la acción, tipo e identificador de la entidad, propiedad RiC-O, cambios antes y después, y el **agente mecanismo** (motor y versión) cuando el evento lo cita |
| Panel consolidado | Todas las personas de la semana (ver la tabla de decisión) | La semana seleccionada completa: hoja por persona y hoja **Sesiones**, sesión por sesión |
| Decisiones de IA | **25** | Hoja **Resumen**, con los conteos y porcentajes (aceptadas, corregidas, rechazadas y cobertura) por tipo y en total, y hoja **Decisiones**, completa. Sirve tal cual para el capítulo de evaluación |
| Hallazgos de conformidad | Todos, **contraídos** a número, título y estado. Se expanden al tocarlos, y hay «Expandir todos» y «Contraer todos» | La hoja que ya existía, con el mismo botón |
| Descritas | **15**, las más recientes primero | Todas las descripciones publicadas del fondo |

- **Recomendado por el prompt, no aplicado todavía:**
  - el historial de verificaciones y migraciones de una instanciación;
  - la lista del vocabulario cuando supera varias decenas.

  Hoy son listas cortas. El componente está listo para ellas.

## 5. Visor de documentos

`VisorDocumento` es un solo componente que muestra:
- las páginas como **imagen PNG generada por el servidor** (PDF e imágenes, con navegación de página);
- o el **texto extraído**, cuando el formato no se puede mostrar como imagen (por ejemplo, un .txt).

| Dónde | Cómo |
|---|---|
| Cola de ingesta | **Previsualizar** en los posibles duplicados (y **Ver el que ya existe**, para comparar antes de decidir) y en los que tienen error |
| Cargar documentos | **Previsualizar** en cada fila de la actividad reciente, antes de asignar el expediente |
| Por describir | **Previsualizar** en cada documento de la lista |
| Espacio de trabajo de descripción | **Embebido junto al formulario**, encima del texto resaltado de cada documento |
| Ficha del catálogo | **Ver** junto a cada archivo |

**Reglas, iguales en los cuatro puntos de entrada:**
- **el visor nunca entrega el archivo original**: no tiene botón de descarga y el servidor solo devuelve PNG;
- un documento con acceso **clasificado o reservado**, propio o heredado del expediente, devuelve **403** a quien no tiene sesión de archivista (escritura en ingesta, descripción o catálogo);
- en el catálogo, además, solo se ve el archivo de una descripción **publicada**.

## 6. Ingesta

- **Cargar documentos:** debajo del área de arrastre va **Actividad reciente de ingesta**: los últimos 5 archivos con su formato, tamaño, fecha y destino («Descrito en…», «Asignado a…», «Pendiente de asignar», «Posible duplicado»), más el enlace a la cola. Si el fondo no tiene nada, aparece en su lugar **Cómo empezar** en tres pasos.
- **Cola de ingesta:** «Previsualizar» y, si quedan menos de 5 pendientes, **Estado general de la ingesta del fondo**: documentos ingresados, con texto reconocido y en riesgo. El riesgo sale del **mismo cálculo del panel de preservación**, sin una consulta paralela.

## 7. Descripción

- **Por describir:**
  - «Previsualizar» en cada documento y el visor embebido al describir;
  - con menos de 5 pendientes, **Su trabajo reciente**: lo que usted validó hoy y el total del fondo. Lo de hoy se cuenta con el grupo «Descripciones validadas» de la auditoría, que es **el mismo dato del panel consolidado**: publicadas, corregidas y recortadas, y así se rotula;
  - cola vacía: estado vacío con **Cargar documentos**.
- **Descritas:** las 15 más recientes y la exportación completa. Si está vacía, estado vacío con **Ir a Por describir**.

## 8. Vocabularios

- **Vocabulario:** si el filtro no deja nada, «Ninguna entidad cumple el filtro activo», con **Limpiar filtro**. Si el vocabulario está vacío, explica que se llena solo al publicar.
- **Sugerencias de fusión:** si no hay ninguna, explica qué la dispara (nombres muy parecidos y pocas conexiones, con un ejemplo) y que la lista vacía no es un error.

## 9. Instrumentos

- **Catálogo:** con menos de 6 unidades en el nivel, una fila de **accesos directos** (Grafo, Inventario, Guía, Índice, RiC-O), cada uno con su icono y una frase.
- **Inventario, Guía, Índice y RiC-O:** al final, un recordatorio de para qué sirve cada uno y para quién:
  - inventario: control interno;
  - guía: lector externo;
  - índice: búsqueda por nombre;
  - RiC-O: verificar la ontología.

  Va siempre (es una línea) y no solo cuando el resultado es corto: detectar «corto» en cuatro instrumentos distintos agregaba lógica sin beneficio.
- **Grafo:** ver `grafo-contexto.md`.

## 10. Preservación

- **Panel:** debajo, **Últimos eventos de preservación**, cada uno con fecha e icono de resultado:
  - última verificación de integridad (íntegros y con problema);
  - última migración;
  - última restauración desde la segunda copia;
  - **simulacro de restauración de la base de datos: pendiente**, porque no existe todavía.
- **Configuración:** ahora es una vista del árbol.

## 11. Auditoría

Ver §4. Además, el encabezado de cada vista es su propio título.

## 12. Evaluación

Sin evaluaciones, la pantalla explica las **tres fases del protocolo**:
1. a ciegas;
2. asistida;
3. calificación de 1 a 5 en exactitud, completitud y pertinencia.

Explica también qué se calcula al cerrar.

## 13. Usuarios

- **Usuarios:** el aviso de correo sin configurar se cierra con **×** y queda reducido a una línea discreta («Correo sin configurar…», con «Ver detalle»). **Sigue así al recargar** mientras el correo siga sin configurar. Es una preferencia de quien mira, guardada solo en su navegador. Si el navegador no guarda nada, el aviso vuelve a verse completo y no se rompe nada.
- **Roles y permisos:** es una vista del árbol. No se le agregó contenido, porque una tabla corta no es un espacio vacío.

## 14. Calidad

- **Componentes reutilizables, cada uno escrito una sola vez:** `EstadoVacio`, `ExportarExcel`/`AvisoReciente`, `VisorDocumento`/`BotonPrevisualizar`/`VentanaVisor`, `useVista` y `ArbolNavegacion`.
- **Accesibilidad:**
  - cada botón nuevo tiene texto o `aria-label`;
  - el árbol usa `aria-expanded`, `aria-controls` y `aria-current`;
  - los paneles cierran con Esc;
  - todo es alcanzable con el teclado.
- **Sin colisiones de estilos:** se verificó que ninguna clase CSS nueva pisara una existente. La línea de tiempo de Preservación casi alteraba la de la ficha de autoridad, y se renombró antes de entregar.

## 15. Ajustes al prompt del grafo

Los tres están aplicados: el Grafo como vista de Instrumentos, el estado vacío con acción y el patrón de historial en la pestaña Relaciones (ver `grafo-contexto.md`).

## 16. Qué no cambia

- Ningún contrato de datos existente cambió. Hay dos ampliaciones compatibles:
  - `GET /api/auditoria/mi-trazabilidad` acepta `limite` y devuelve `total`;
  - `GET /api/auditoria/decisiones-ia` acepta `limite`.
- **Ninguna entidad, relación ni campo** se agregó o quitó. No hay migración de base de datos.
- **Ningún flujo de aprobación o publicación** cambió.

## 17. API agregada

| Ruta | Para qué | Permiso |
|---|---|---|
| `GET /api/auditoria/trazabilidad/exportar` | Mi trazabilidad completa, con los filtros de la vista | Sesión (cada quien la suya) |
| `GET /api/auditoria/panel-consolidado/exportar?semana=` | La semana completa: personas y sesiones | Ver toda la auditoría |
| `GET /api/auditoria/decisiones-ia/exportar` | Las decisiones con su resumen (alias de la hoja que ya existía) | Administración |
| `GET /api/ingesta/{id}/previsualizar` (y `/{pagina}`) | Visor desde la ingesta | Lectura de ingesta y regla de acceso |
| `GET /api/descripcion/{id}/previsualizar` (y `/{pagina}`) | Visor desde la descripción | Lectura de descripción y regla de acceso |
| `GET /api/instrumentos/previsualizar/{id}` (y `/{pagina}`) | Visor de la ficha del catálogo | Lectura del catálogo, regla de acceso y solo lo publicado |
| `GET /api/ingesta/recientes`, `GET /api/ingesta/resumen` | Actividad reciente y estado general | Lectura de ingesta |
| `GET /api/descripcion/productividad`, `GET /api/descripcion/publicadas/exportar` | Su trabajo reciente y Descritas en Excel | Lectura de descripción |
| `GET /api/preservacion/eventos-recientes` | Línea de tiempo | Lectura de preservación |

Todas son GET y exigen sesión. Las dos pruebas que recorren todas las rutas reales (sesión obligatoria y que el revisor no pueda escribir) siguen en verde.

## 18. Pruebas automatizadas

**Interfaz.** Es nuevo: **Vitest con Testing Library**, gratuitos, y el CI ahora corre `npm test`. Están en `frontend/src/pruebas/navegacion.test.tsx`, 6 pruebas:
1. Llegar por la dirección de una vista interna (Sugerencias de fusión) **expande su módulo y la resalta**; los demás quedan contraídos.
2. **Acordeón:** abrir Instrumentos revela **exactamente** sus 6 vistas, en orden, y esconde las de Vocabularios; tocar el módulo abierto lo cierra.
3. Recorrer Ingesta → Descripción › Descritas → Instrumentos › Grafo deja abierto **solo** Instrumentos.
4. Elegir una vista navega a ella y pasa a ser la resaltada.
5. Configuración de preservación es una vista del árbol con ruta propia.
6. Cada rol ve solo sus vistas, y un módulo con una sola vista es un enlace simple.

Se comprobó que las pruebas **detectan una falla**: al quitar la expansión automática fallaban 4 de las 5 originales, y al volver al comportamiento de varios módulos abiertos fallan las 2 del acordeón.

**Servidor.** `tests/test_rediseno.py`, 9 pruebas:
1. Mi trazabilidad muestra 15. **El Excel trae los 22 registros que cumplen el filtro**, con las columnas extra.
2. Cada quien exporta solo su trazabilidad.
3. Panel consolidado y decisiones se exportan completos. Archivista: 403; sin sesión: 401.
4. Previsualizar desde ingesta y desde descripción devuelve un **PNG generado, nunca el PDF original**. Una página inexistente da 422.
5. **Quien no es archivista recibe 403** al previsualizar un documento reservado, por herencia del expediente, en los tres puntos de entrada. La archivista sí lo ve.
6. En el catálogo, solo el archivo de una descripción publicada.
7. Actividad reciente (5, la más reciente primero, con su destino) y resumen de la ingesta.
8. Productividad (cuenta solo lo de quien consulta) y Descritas en Excel.
9. Línea de tiempo de preservación, vacía y después de una verificación.

**Una de estas pruebas encontró un error real antes de entregar:** la ruta de Mi trazabilidad ignoraba el parámetro `limite`, y la pantalla habría mostrado 200 registros en vez de 15. Quedó corregido.

**Suite completa del servidor:** 304 pruebas en verde (eran 282). Son 13 nuevas del grafo y 9 de este rediseño.

**Pendiente, y no se oculta:** el aviso de correo que sigue cerrado al recargar se comprobó en el navegador (Playwright), pero no tiene prueba automática en el CI.

## 19. Definición de terminado

- [x] Las ocho pantallas recorridas en el navegador, a 1360 px y a 390 px. Ninguna conserva pestañas horizontales y en todas la vista activa queda resaltada.
- [x] Evidencia en `documentacion/anexos/rediseno-navegacion/`:
  1. árbol abierto desde la dirección;
  2. acordeón, antes y después (con varios abiertos frente a uno solo);
  3. Cargar con actividad reciente;
  4. visor sin descarga;
  5. Mi trazabilidad con 15 y el botón de exportar;
  6. *(no se guardó: la exportación a Excel se completó en el navegador, pero el archivo contenía la auditoría real del entorno de desarrollo; su contenido lo verifica la prueba 1)*;
  7. hallazgos contraídos;
  8. catálogo con accesos directos;
  9. preservación con la línea de tiempo;
  10. evaluación;
  11. menú desplegable en celular.
- [x] El prompt del grafo se implementó ya con los tres ajustes de §15.
- [ ] **Validación de la autora**, en particular:
  1. aceptar que el visor no es IIIF (o decidir instalar un servidor IIIF gratuito, ver la tabla);
  2. qué quiso decir con «riesgo de seguridad»;
  3. si quiere una pantalla de Inicio.

---

## Tablas de decisión

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Visor de documentos | (a) Servidor IIIF (Cantaloupe, gratuito, Java) con un visor Mirador u OpenSeadragon; (b) **el renderizador de páginas existente** (pypdfium2 y Pillow a PNG) | **(b)** | Ya estaba probado y desplegado. No suma un servicio Java al servidor (memoria del Droplet) ni una caché de imágenes. Cumple lo que pide el prompt: ver sin descargar y respetar el nivel de acceso | **No es interoperable IIIF**: otro visor no puede consumir estas imágenes. Si la tesis necesita IIIF (por ejemplo, para enlazar con otra institución), la opción (a) se suma detrás de la misma API sin cambiar la interfaz |
| Dónde vive la vista activa | Estado interno de cada pantalla; **la dirección (`?vista=`)** | **La dirección** | Permite enlazar una vista, volver con «atrás», que el árbol la resalte y que la ambulancia la distinga | Ninguno práctico |
| Árbol en pantallas angostas | Barra horizontal con desplazamiento (la de antes); **menú desplegable** | **Menú desplegable** | El prompt pide no desplazar en horizontal. Siete módulos con sus vistas no caben en una fila | Un toque más para cambiar de módulo en el celular |
| Panel consolidado: ¿15 personas? | Recortar a 15; **la lista completa de la semana** | **Completa** | La lista va en orden **alfabético**, no por fecha: llamar «más recientes» a las 15 primeras sería falso. Lo reciente es la semana, y ya se muestra primero | Con muchas personas la tabla es larga; la exportación la trae igual |
| Hallazgos | El patrón de historial; **contraer por tarjeta** | **Contraer** (lo pide el prompt) | Crecen por ronda de revisión, no por uso diario | Ninguno |
| Pruebas de interfaz | Ninguna (como antes); Playwright en el CI; **Vitest con Testing Library** | **Vitest** | El prompt exige probar el árbol. Vitest corre en segundos, sin navegador ni servidor, y es gratuito | Simula el DOM: no prueba el CSS. Para eso están las capturas |
| Propósito de los instrumentos | Solo cuando el resultado es corto; **siempre** | **Siempre** | Es una línea al final. Detectar «corto» en cuatro instrumentos distintos agregaba lógica sin beneficio | Ninguno |
| Aviso de correo cerrado | En el servidor (por usuario); **en el navegador** | **Navegador** | Es una preferencia de lectura, no un dato del sistema. Si el navegador no guarda nada, el aviso vuelve completo | Cambiar de navegador lo muestra otra vez completo |

---

## Ajustes posteriores pedidos por la autora (versión 1.1)

Pedidos después de usar la versión 1 en una pantalla de 600 px de alto.

| Pedido | Qué se hizo | Por qué |
|---|---|---|
| «No quiero esos espacios en blanco»: franja vacía a la derecha | El contenido usa **todo el ancho** (se quitó el máximo de 1060 px) | En pantallas anchas sobraba una columna entera |
| Reubicar la ambulancia | Pasa a la **barra superior**, junto a Alertas; su tarjeta se abre debajo | Flotando abajo a la derecha necesitaba que esa franja quedara libre |
| El grafo en pantalla completa se cortaba y no se podía bajar | El lienzo se ajusta al **alto de la ventana** (`calc(100vh − …)`), en vista normal y en pantalla completa; en pantalla completa se oculta el título para ganar espacio | Medía 600 px fijos: en una pantalla de 600 px de alto no cabía |
| Instrumentos mostraba tarjetas que repetían los submódulos | Se quitaron. En su lugar, en la portada del fondo: **Resumen del fondo**. Muestra la composición por nivel y los archivos, los productores, los lugares más citados y las formas documentales. **Avisa si las fechas de los documentos quedan fuera de las fechas extremas declaradas del fondo** (`GET /api/instrumentos/resumen`) | Las tarjetas eran redundantes con el árbol (desviación consciente de §9 del prompt). El resumen aporta información que no está en ninguna otra pantalla |
| ¿Panel consolidado y Mi trazabilidad son lo mismo? | **No son lo mismo**: uno es el registro de cada acción propia y el otro, un resumen por persona y por semana. Se **unificaron en una sola entrada, «Trazabilidad»**, con dos modos: «Mis acciones» y «Equipo por semana». El segundo solo se ofrece a quien ve toda la auditoría | Son dos miradas sobre lo mismo, la trazabilidad; dos entradas del menú lo hacían parecer duplicado. Auditoría pasa de 4 a 3 vistas |

### Índice y Vocabulario: uno para consultar, otro para trabajar (versión 1.2)

**Pedido de la autora:** «el índice y el vocabulario son lo mismo; si uno es interno y otro para consulta, sepáralos».

**Diagnóstico del perfil de consulta**, recorrido con un usuario de prueba en el entorno de desarrollo:
- ya no veía Vocabularios: solo tiene lectura del catálogo;
- veía **Inventario** y **Guía**, que solo decían «Su rol puede consultar el catálogo, pero no generar instrumentos»: dos pantallas vacías;
- el **Índice** listaba términos con «0 documentos» y sus nombres no llevaban a ningún documento;
- los conteos se calculaban desde la base completa, sin la regla de visibilidad.

| Decisión | Qué se hizo |
|---|---|
| Separar los dos instrumentos | **Vocabularios** es la herramienta interna: fichas ISAAR, fusiones, sugerencias. El **Índice** es la puerta de consulta por nombres: solo lo ve **quien no tiene acceso a Vocabularios** (el perfil de consulta). Así el equipo interno no ve los mismos términos dos veces |
| Un índice que sirva para consultar | Cada término se despliega en **los documentos que lo citan**, y cada documento abre su ficha. Tiene buscador por nombre. Un término sin documentos visibles **no se lista**: no es un punto de acceso, y se sigue administrando en Vocabularios |
| La misma visibilidad en todos los instrumentos | El índice cuenta solo lo publicado y, para quien no es archivista, nada clasificado ni reservado. Es la misma regla del grafo y de la exportación RiC-O |
| Pantallas que el perfil no puede usar | **Inventario** y **Guía** solo aparecen a quien puede generar instrumentos |
| El menú del perfil de consulta | El grupo se llama «Consulta del archivo», no «Trabajo archivístico» |

**Hallazgo para la autora.** El **Catálogo** muestra una unidad documental cuya serie superior sigue en **borrador**: «Oficio 210», bajo la serie «Permisos». La exportación RiC-O, el grafo y el índice no la muestran, porque cuelga de un nivel sin publicar. El catálogo sí la muestra, saltándose ese nivel. Hay que decidir una regla: publicar la serie, o que el catálogo tampoco la muestre mientras su nivel superior esté en borrador.

### Lo que ve el perfil de consulta frente al índice de información clasificada y reservada (versión 1.3)

La autora entregó como referencia un **índice de información clasificada y reservada** (Ley 1712 de 2014, artículos 18 y 19). Tiene 168 activos de información:
- **Clasificación:** 138 son información pública clasificada (IPC, art. 18) y 30, información pública reservada (IPR, art. 19).
- **Alcance:** 131 tienen **reserva parcial** y 37, **reserva total**.
- **Plazos:** entre 1 y 15 años; el más frecuente es 15.

**Fugas encontradas y corregidas.** Todas usan ahora la misma regla del grafo, el índice y la exportación RiC-O (`exportacion_rico._recursos`):

| Dónde | Qué pasaba | Ahora |
|---|---|---|
| **Catálogo** (árbol y ficha) | Mostraba al perfil de consulta las descripciones clasificadas o reservadas | No las muestra; abrir una por su dirección da 404 |
| **Ficha pública** (`/api/catalogo/registros/{id}`) | Igual | Igual que el catálogo |
| Conteo «N documentos de esta entidad» | Contaba también lo reservado, lo que revela que existe | Solo cuenta lo que quien consulta puede ver |
| **Grafo**: selector de raíz y nodos | Ofrecía y dibujaba personas o entidades citadas **solo** en documentos reservados: un dato personal (Ley 1581 de 2012) | Para quien no es archivista, una entidad solo aparece si lleva a algún documento visible |
| Catálogo: documento bajo un nivel en borrador | Lo mostraba saltándose el nivel sin publicar | Ya no; aplica la misma regla que la exportación RiC-O |

**Lo que el sistema todavía no hace, y la autora debe decidir.**

1. **Reserva parcial.** RICORA solo sabe ocultar una descripción completa. Con 131 de 168 activos en reserva parcial, eso es **sobre-restringir**: el artículo 21 de la Ley 1712 obliga a entregar la parte no reservada. Para hacerlo bien hace falta una «versión pública» de la descripción, que oculte solo los campos o las partes documentales reservadas.
2. **Vencimiento del plazo.** La declaración de derechos guarda «vigente hasta», pero el sistema **no levanta la reserva al vencer**. Mantenerla es el lado seguro. Lo correcto es una alerta que avise al archivista para que la revise y la levante.
3. **Cargar el índice por serie y subserie.** La reserva se declara por descripción y se hereda hacia abajo: declararla en una serie cubre todo lo que contiene, igual que el índice declara por serie. No hay todavía una carga masiva desde el archivo del índice.

### Leyenda y desplazamiento del grafo; la copia de conservación

- **La leyenda es interactiva.** Tocar un tipo lo oculta o lo muestra en el dibujo, junto con sus relaciones; la raíz nunca se oculta. Cada tipo muestra cuántos hay, y «Mostrar todos» vuelve al grafo completo.
- **Desplazamiento:**
  - la rueda del ratón **sube y baja** por el grafo (con Mayús, a los lados) sin mover la página;
  - Ctrl + rueda o el gesto de pellizco acercan y alejan;
  - a la derecha hay botones ▲ ▼, + y −, un deslizador de acercamiento y «ajustar»;
  - con el lienzo seleccionado, las flechas del teclado desplazan.
- **Dos instanciaciones no son un duplicado.** Una migración de formato (por ejemplo, a PDF/A-2b) crea la **versión de conservación** y el original nunca se borra. RiC-O declara las dos instanciaciones del documento, y así sigue la exportación. El grafo, en cambio, dibuja la copia **colgando de su original** («migrada a») y la rotula «versión de conservación», para que no parezca un archivo repetido.
