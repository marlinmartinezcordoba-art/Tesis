# Grafo de contexto del fondo (Instrumentos › Grafo)

**Versión:** 2. La versión 1 era la pestaña «Grafo» de Instrumentos (commit `9b380ed`).
**Estado:** entregado, pendiente de validación por la autora.
**Estructura:** los catorce puntos del prompt «Visualización interactiva del grafo de contexto», con las tablas de decisión que exige su §8 y las desviaciones declaradas.

---

## Antes de leer: lo que el prompt daba por hecho y no era cierto

| Lo que dice el prompt | Lo que hay en el sistema | Qué se hizo |
|---|---|---|
| «el grafo que la base de datos ya mantiene mediante Apache AGE» | AGE **no** está instalado. El grafo vive en tablas relacionales (`relaciones`, la jerarquía de `recursos_documentales` y la forma documental). Así se decidió y documentó en `modulo-2-descripcion.md` (decisión «Dónde se guarda el grafo») | Se mantiene la decisión. La consulta acotada a 1–3 saltos se hace en SQL por lotes y se midió (§7). AGE sigue siendo la evolución posible si algún día hacen falta caminos largos |
| Una pantalla nueva | Ya existía la pestaña «Grafo» (d3-force + SVG) | Se rehizo esa pestaña según este prompt; no hay dos grafos |
| Siete tipos de entidad | El sistema ya modela once tipos RiC que pueden aparecer en el grafo: los siete, más Record Part, Documentary Form Type, Activity Type y Mandate | La leyenda muestra siempre los siete; los otros cuatro solo cuando están en pantalla, con icono y color propios. Ocultarlos habría mentido sobre el fondo |
| Filtro de estado «borrador, pendiente de revisión o publicado» | En el sistema no existe el estado «pendiente de revisión» (`ESTADO_REVISION = ("validado",)`), y los borradores **nunca** se dibujan: son propuestas que nadie validó | El filtro ofrece los dos estados reales de una descripción visible: **publicada** y **publicada, reabierta para corregir** |
| `POST …/exportar` | Una prueba del sistema recorre todas las rutas: quien solo lee (el revisor) recibe 403 en cualquier POST. Exportar es una consulta, y la exportación RiC-O del fondo ya es GET | **GET** `…/exportar`. Con POST, el revisor no podría exportar lo que puede ver, o habría que debilitar esa prueba |
| Paleta `#eef0f5` / `#3b5bdb` «ya validada en la demostración de auditoría» | La paleta vigente de RICORA es `#e6eaf0` / `#2f5fd0` (regla de la autora: conservar los colores actuales). Las tipografías Source Serif 4 e Inter ya estaban | Se conservan los colores generales. Solo los **siete colores de tipo de entidad** del prompt entran, y solo en el grafo |

**Dos defectos de la versión 1, encontrados al probar esta, también corregidos:**
1. **La parte documental colgaba del documento por «incluye».** La jerarquía se deducía siempre como inclusión (RiC-R024), y un oficio con su sello mostraba dos relaciones, «incluye» y «tiene la parte». La exportación RiC-O ya usaba la correcta, `rico:hasOrHadConstituent` (RiC-R003), así que **el grafo contradecía a la exportación**. Ahora la jerarquía de una parte es constitutiva, como en la exportación.
2. **Las relaciones de las versiones 2 y 3 salían sin su propiedad RiC-O** (partes, custodio, secuencia…). La tabla que usaba el grafo era anterior a ellas. Ahora la propiedad sale del **mapeo único** `ric_o.propiedad`, el mismo de la exportación.

**Hallazgo de seguridad corregido en esta entrega.** La pestaña anterior le mostraba al rol de consulta las descripciones con acceso **clasificado o reservado**. La exportación RiC-O ya las ocultaba; el grafo no. Ahora el grafo usa la **misma función de visibilidad** de la exportación (`exportacion_rico._recursos`), así que lo que no se exporta tampoco se dibuja. La ruta antigua `/api/instrumentos/grafo` quedó como alias del servicio nuevo, con la misma regla.

---

## 1. Qué hace esta pantalla

Dibuja como grafo interactivo el entorno RiC de una entidad raíz (el fondo, un expediente, un agente…). Expande la exploración a 1, 2 o 3 saltos y filtra por tipo de entidad, tipo de relación, rango de fechas y estado. Abre el detalle de cualquier entidad tocada sin salir del grafo. No edita nada.

## 2. Ubicación y encabezado

- Es la vista **Grafo** dentro del árbol de **Instrumentos** (Catálogo, Grafo, Inventario, Guía, Índice, RiC-O), según el rediseño de navegación. No es un elemento de primer nivel.
- **Encabezado:** «Grafo del fondo» y, debajo, la entidad raíz con una flecha desplegable. El desplegable agrupa por tipo: agrupaciones, documentos, agentes, lugares… Cambiarla recentra el grafo y conserva saltos y filtros.
- **Dirección:** la raíz queda en la dirección de la página (`?vista=grafo&centro=tipo:id`), así que se puede enlazar. Los botones «Ver en grafo» del vocabulario y de la ficha del catálogo la usan.

## 3. Barra de herramientas

1. **Buscar en el grafo:** resalta y centra el primer nodo cuyo nombre coincide. No toca los filtros. Si nada coincide, lo dice.
2. **Filtros**, con un contador de filtros activos. El panel tiene:
   - tipo de entidad (los once tipos);
   - tipo de relación (el catálogo curado, en español, con la propiedad RiC-O al pasar el cursor);
   - rango de fechas, desde y hasta;
   - estado;
   - «Limpiar filtros».
3. **Profundidad:** control segmentado «Relaciones directas · 2 saltos · 3 saltos». Nunca más de 3.
4. **Pantalla completa:** el lienzo ocupa la ventana y se ocultan la barra lateral, el detalle y la ambulancia. Se sale con el botón o con Esc.

## 4. El lienzo

- **Disposición por fuerzas** (d3-force): los nodos se repelen y las relaciones son resortes. El resorte es **más corto cuanto más relaciones comparten sus extremos**, así que los grupos muy relacionados quedan juntos.
- Se arrastran los nodos, se hace zoom con la rueda o con **+ / − / ajustar** (esquina inferior izquierda) y se desplaza arrastrando el fondo.
- **Leyenda fija** arriba a la izquierda, nunca oculta. En celular pasa encima del lienzo, en fila, para no tapar nodos.
- **Nodos:** círculo del color del tipo, icono de trazo dentro y **nombre siempre visible** debajo. La raíz va más grande y con borde.
- **Relaciones:** línea con flecha si la relación tiene dirección; la única simétrica del catálogo, «asociado con», va sin flecha. La etiqueta está en español, al lado de la línea; la propiedad RiC-O exacta aparece al pasar el cursor.
- **Desviación declarada:** con más de 60 relaciones, o con el zoom muy alejado, las etiquetas de relación solo se ven en las relaciones del nodo señalado o elegido. Con todas visibles se tapan entre sí y no se lee ninguna. El panel de detalle las lista todas en texto.
- **Transición, no parpadeo:** al cambiar filtros o saltos, los nodos que siguen conservan su lugar y el lienzo se atenúa mientras llega la respuesta.
- **Estado vacío, nunca un lienzo en blanco:**
  - por filtro: «Ningún nodo pasa los filtros activos», con **Limpiar filtros** y la explicación de que el recorrido no atraviesa lo filtrado;
  - sin relaciones: «Esta entidad todavía no tiene relaciones registradas», con **Elegir otra entidad raíz**.

## 5. Tipos de entidad: icono y color

| Tipo RiC | Nombre en pantalla | Icono (trazo 1,8) | Color claro / oscuro |
|---|---|---|---|
| Record Set | Agrupación documental | pila de documentos | `#2a78d6` / `#3987e5` |
| Record | Documento | documento con renglones | ídem (misma familia) |
| Record Part | Parte documental | documento con un recuadro | ídem, más claro |
| Agent | Agente | persona en un círculo | `#008300` |
| Activity | Actividad | engranaje | `#eda100` / `#c98500` |
| Date | Fecha | calendario | `#4a3aa7` / `#9085e9` |
| Place | Lugar | marcador | `#e87ba4` / `#d55181` |
| Instantiation | Archivo | documento con esquina doblada | `#1baf7a` / `#199e70` |
| Activity Type | Tipo de actividad | dos recuadros enlazados | familia ámbar |
| Mandate | Mandato o norma | balanza | familia ámbar |
| Documentary Form Type | Forma documental | etiqueta | `#64748b` / `#94a3b8` |

**El color nunca es la única señal.** Cada nodo lleva icono y etiqueta de texto. En ámbar y magenta claro el icono va en tinta oscura, porque el blanco no contrasta.

**Para que la autora decida:** en el resto del sistema el agente es **violeta** (`--agent`), en tarjetas e insignias. En este grafo, siguiendo la captura del prompt, es **verde**, y el violeta pasa a la fecha. La misma entidad tiene así dos colores según la pantalla. Se puede unificar en cualquiera de los dos sentidos; es una línea de CSS.

## 6. Panel de detalle

- **Encabezado:** «Entidad seleccionada», con cierre (×), insignia del tipo con su color y el nombre como título.
- **Tres pestañas:**
  - **Resumen**, con los campos clave según el tipo y un icono por campo. Agrupación o documento: identificador, título, nivel, alcance, fechas y estado. Agente: nombre, tipo y existencia. Lugar: tipo y coordenadas. Fecha: forma legible, expresión y EDTF. Archivo: formato, tamaño y páginas.
  - **Atributos (n):** el resto de los campos propios.
  - **Relaciones (n):** cada relación en su sentido natural, por ejemplo «Alcalde de Tunja → tiene como subordinado → esta entidad». El nombre del otro extremo recentra el grafo y conserva los filtros.
- **Patrón de historial reciente:** con más de 15 relaciones se ven las 15 más recientes y el enlace **Exportar todas a Excel**, el mismo de todo el sistema.
- **Botones:**
  - **Abrir entidad** lleva a su módulo: documento o agrupación a la ficha del catálogo, entidad a Vocabularios, archivo a Preservación. Una fecha no tiene ficha propia, y el botón dice por qué.
  - **Ver en contexto** recentra el grafo en esa entidad.
  - **Exportar** ofrece Turtle o JSON-LD.
- Tocar el lienzo vacío cierra el panel. Si un filtro saca la entidad del dibujo, el panel también se cierra.

## 7. De dónde vienen los datos

`GET /api/grafo/{tipo}/{id}` recibe:
- `saltos`, de 1 a 3;
- `tipo_entidad[]`, `tipo_relacion[]`, `fecha_desde`, `fecha_hasta` y `estado[]`;
- `fondo_id` opcional. Solo es obligatorio si la raíz es una fecha, porque una fecha no pertenece a un fondo.

Devuelve los nodos (tipo, familia RiC, nombre, estado, fechas y salto) y las relaciones (código, propiedad RiC-O, etiqueta y dirección).

**Cómo se recorre** (`app/servicios/grafo.py`):
1. Se calculan una sola vez:
   - las descripciones visibles del fondo, con la función de la exportación RiC-O;
   - sus fechas: las extremas y las de sus nodos Date;
   - las reabiertas.
2. Por cada salto, una consulta trae las relaciones vigentes de la frontera, más la jerarquía y la forma documental.
3. Los nodos nuevos se cargan **en lote**, un SELECT por tabla.

**Los filtros se aplican durante el recorrido.** Lo que no pasa no aparece y no se atraviesa. Por eso, desde el fondo con el filtro «solo agentes» no se llega a ningún agente: el camino pasa por agrupaciones y documentos. La pantalla lo explica en su estado vacío.

**Fechas:**
- se excluye lo que cae fuera del rango;
- lo que **no tiene fecha no se excluye**, porque no hay evidencia de que caiga fuera;
- la raíz siempre se muestra.

**Prueba de carga** (`tests/test_grafo_contexto.py::test_carga_con_un_fondo_de_mas_de_quinientas_entidades`):
- **Fondo de prueba:** 5 series, 50 expedientes, 250 documentos, 150 agentes, 50 lugares y 250 fechas. Son **756 entidades** y más de 1.000 relaciones.
- **Resultados** en el entorno de pruebas (PostgreSQL 16 local):

| Raíz | Saltos | Tiempo | Nodos devueltos |
|---|---|---|---|
| Fondo | 3 | **0,16 s** | 300, **truncado** (a 3 saltos hay 306 descripciones) |
| Un agente | 3 | **0,06 s** | 21 |

- **Decisión** (la que el prompt pide cuando el resultado no es satisfactorio): el tiempo sí lo es. El límite no se pone por rendimiento de la base de datos sino por **legibilidad y fluidez del dibujo**. Hay un máximo de **300 nodos**, con aviso explícito («El grafo se truncó en 300 entidades… reduzca los saltos, aplique un filtro o elija una raíz más específica»).
- **No se agrega indexación:** la consulta ya usa los índices de `origen_id` y `destino_id`.
- La prueba exige menos de 3 s, no más de 300 nodos y el truncamiento desde el fondo.

## 8. Decisión técnica: librería de dibujo

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo se dibuja el grafo | (a) **force-graph sobre canvas** (`force-graph`, `react-force-graph`); (b) **Cytoscape.js**; (c) **d3-force + SVG propio** | **(c) d3-force + SVG**, la que ya usaba la versión 1 | Con el máximo de 300 nodos, SVG es fluido. Cada nodo es un elemento accesible: se recorre con el teclado, tiene nombre para lectores de pantalla y responde a Enter. Usa la paleta y la tipografía de RICORA sin estilos ajenos, y suma unos 15 kB. Canvas obliga a reconstruir a mano la accesibilidad y la selección. Cytoscape pesa cerca de 400 kB y trae su propio sistema de estilos | **Por encima de unos 300 a 400 nodos visibles a la vez, el SVG deja de ser fluido** al arrastrar, porque el navegador recalcula el DOM en cada cuadro. Por eso el máximo de 300 coincide con ese umbral |
| Si producción exige más | Subir el máximo; agrupar; pasar a canvas | **Primero agrupar**, después canvas | Más de 300 nodos no se leen aunque se dibujen. Lo útil es plegar los documentos de un expediente en un solo nodo. Si aun así hace falta, el lienzo se cambia por canvas (o WebGL con `force-graph`) sin cambiar la API: la simulación d3-force es la misma | Agrupar exige definir el nivel de plegado; queda como trabajo futuro |
| Máximo de nodos | 150 (versión 1); **300**; sin límite | **300**, con aviso | La medición (§7) muestra que la consulta no es el cuello de botella. 300 es el umbral de fluidez del SVG | Un fondo grande a 3 saltos desde la raíz siempre se trunca. Es intencional |
| Dónde viven los datos del grafo | Apache AGE; **tablas relacionales** | Tablas (sin cambios) | Ver `modulo-2-descripcion.md`. La medición confirma que SQL por lotes basta para 1–3 saltos | Caminos largos (más de 6 saltos) serían más naturales en Cypher |
| Filtros: en el recorrido o al final | Filtrar el resultado; **cortar el recorrido** | **Cortar el recorrido** | Filtrar al final deja islas sueltas, nodos que solo se conectaban por algo oculto, y el grafo miente sobre la estructura | «Solo agentes» desde el fondo da vacío. La pantalla lo explica |
| Quién ve lo reservado | Regla de la exportación (escritura en el catálogo); **sesión de archivista** | Escritura en **descripción o** en el catálogo | El prompt dice «sin sesión de archivista». El rol archivista describe pero no escribe en el catálogo; con la regla de la exportación no vería lo que él mismo describió | El rol de revisor (solo lectura) tampoco lo ve. Es coherente con la exportación |

## 9. Flujo funcional

1. Estado inicial: centrado en el fondo activo, con relaciones directas.
2. Cambiar la raíz recarga, conservando saltos y filtros.
3. Cambiar los saltos pide de nuevo el subgrafo.
4. Aplicar un filtro también lo pide de nuevo, con transición.
5. Tocar un nodo abre el detalle sin mover el resto. Tocar el lienzo vacío lo cierra.
6. Exportar descarga **solo lo visible**. El nombre del archivo lo deja claro: `ricora-fragmento-<raíz>-<n>-saltos-<filtros>.ttl`, por ejemplo `ricora-fragmento-Fondo-de-prueba-Archivo-Municipal-1-saltos-sin-filtros.ttl`.

## 10. API

| Ruta | Para qué |
|---|---|
| `GET /api/grafo/opciones?fondo_id=` | Tipos, relaciones (con su propiedad RiC-O), estados y entidades que pueden ser raíz |
| `GET /api/grafo/{tipo}/{id}` | El subgrafo acotado (§7) |
| `GET /api/grafo/{tipo}/{id}/ficha` | Resumen, atributos y las 15 relaciones más recientes, con el total |
| `GET /api/grafo/{tipo}/{id}/relaciones/exportar` | Todas las relaciones de la entidad, en Excel |
| `GET /api/grafo/{tipo}/{id}/exportar?formato=turtle\|jsonld` | El fragmento visible en RiC-O. Lo genera **el mismo servicio de la exportación del fondo**, recortado a las entidades y relaciones visibles y a sus nodos de apoyo. Queda en la auditoría (`grafo_exportado`) |
| `GET /api/instrumentos/grafo` | Alias de la versión 1 (sin filtros), con la misma regla de acceso |

Todas exigen sesión y lectura del catálogo. Lo clasificado o reservado solo lo ve quien tiene sesión de archivista (§8).

## 11. Qué no construye

- No edita entidades ni relaciones: eso se hace en su módulo.
- No recorre más de 3 saltos.
- No sustituye al catálogo.
- No tiene versión pública sin sesión, aunque la API ya aplica la regla que esa versión necesitaría.

## 12. Sistema de diseño

- **Tipografía:** Source Serif 4 en los títulos e Inter en el texto. Ya estaban.
- **Iconos:** de trazo 1,8, como los de la barra lateral.
- **Colores generales:** los vigentes de RICORA, no los de la demostración (ver la tabla inicial).
- **Colores de tipo de entidad:** los del prompt, como variables `--g-*` con su versión oscura. Son distintos de los colores de estado (correcto, advertencia, alerta).

## 13. Pruebas automatizadas

`tests/test_grafo_contexto.py`, 13 pruebas:

1. Con 1, 2 y 3 saltos se devuelve **exactamente** lo alcanzable en una topología conocida: 2, 4 y 9 nodos. 4 saltos devuelve 422.
2. Primer nivel de un documento: agente, lugar, forma documental, archivo, fecha y expediente, cada uno con su tipo RiC.
3. El filtro por tipo excluye los nodos y sus relaciones. El recorrido no atraviesa lo filtrado.
4. Filtro por tipo de relación.
5. El filtro por fechas excluye lo que cae fuera. Lo que no tiene fecha se conserva, y también la raíz.
6. Filtro por estado: publicada o reabierta.
7. **El rol de consulta nunca recibe lo reservado**, ni heredado del expediente: no aparece en el grafo, y la ficha y la exportación dan 404. La ruta antigua aplica la misma regla.
8. La ficha trae resumen, atributos y relaciones con su sentido y su propiedad RiC-O.
9. Con 23 relaciones se ven 15, y el Excel trae las 23.
10. **La exportación contiene exactamente las entidades visibles.** Toda tripleta entre dos entidades corresponde a una relación visible, y JSON-LD dice lo mismo que Turtle.
11. Carga con 756 entidades (§7).
12. La parte documental cuelga del documento por `rico:hasOrHadConstituent`, como en la exportación.
13. El panel de filtros ofrece **solo los tipos de relación que el fondo usa**, todos con su propiedad RiC-O. No ofrece todo el catálogo: 20 de sus códigos aún no tienen propiedad RiC-O, la deuda de las relaciones pendientes de validar.

## 14. Definición de terminado

- [x] Tabla de decisión de la librería (§8), con el umbral (unos 300–400 nodos) y qué se haría distinto.
- [x] Prueba de carga con más de 500 entidades y su resultado real (§7).
- [x] Evidencia en `documentacion/anexos/grafo-contexto/`:
  1. inicial;
  2. dos saltos;
  3. cambio de raíz a un agente;
  4. panel de filtros;
  5. filtro aplicado;
  6. detalle con relaciones;
  7. pantalla completa.
- [ ] **Validación de la autora**, en particular:
  1. el color del agente (verde en el grafo, violeta en el resto);
  2. que el filtro de estado ofrezca solo los dos estados reales;
  3. GET en vez de POST para exportar.

## 15. Ajuste v1.4: lienzo libre, al estilo de un mapa mental

La autora pidió moverse en cualquier dirección con clic sostenido, sin botones, y que barras y filtros se aparten mientras arrastra, como en un mapa mental.

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo desplazarse | Botones ▲ ▼ · barras de desplazamiento · arrastre libre | Arrastre libre con clic sostenido; se quitan ▲ ▼ | El arrastre ya existía, pero fallaba: el cálculo del desplazamiento se leía tarde y el lienzo casi no se movía. Se corrigió y ahora sigue al puntero aunque salga del lienzo. Los botones ▲ ▼ sobraban. | Con teclado no hay arrastre. Siguen las flechas, la rueda y los botones + y −. |
| Qué se oculta al arrastrar | Nada · solo los filtros · todo lo que tapa el lienzo | Encabezado, barra de búsqueda y filtros, leyenda, controles y panel de detalle se desvanecen, sin desaparecer del todo, y vuelven al soltar | Se ve solo el grafo mientras se mueve. Desvanecer no cambia la distribución de la pantalla, así que el lienzo no salta. | Queda un hueco claro arriba durante el arrastre. Es intencional, para que el lienzo no se mueva. |
| Fondo del lienzo | Liso · cuadrícula de puntos fija · cuadrícula que se mueve con el dibujo | Cuadrícula de puntos que se mueve y escala con el dibujo | Da la sensación de lienzo infinito, como Mindomo, y deja ver que el arrastre funciona aunque no haya nodos a la vista. | Ninguno relevante. Usa un patrón SVG y no carga imágenes. |
| Arrastrar sobre un nodo | Mueve el lienzo · mueve el nodo | Mueve el nodo, como antes | Así se pueden reacomodar entidades superpuestas. | Hay que empezar el arrastre en un espacio vacío para mover el lienzo. |

Prueba: un recorrido con Playwright arrastra 150 px y luego otros 300 px saliendo del lienzo. El dibujo se desplaza esa misma distancia y barra, leyenda y controles quedan en opacidad 0 durante el arrastre y en 1 al soltar.
