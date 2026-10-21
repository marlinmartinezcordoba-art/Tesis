# Grafo RiC-O persistente

**Versión:** 2: el grafo pasa a ser la fuente de verdad de lo publicado.

**Pedido de la autora:** que la descripción no solo se traduzca a RiC-O al exportar, sino que viva como grafo RDF. También que la interfaz muestre el término RiC junto al término archivístico de cada nivel.

## 1. Qué cambió

**Antes:** el grafo RiC-O se armaba desde las tablas cada vez que alguien pedía una consulta SPARQL, una URI `/id/` o una descarga. No existía guardado en ninguna parte.

**Ahora:**
- **El grafo vive guardado** en un almacén de tripletas (Oxigraph, libre, con SPARQL 1.1). Hay un grafo con nombre por fondo y alcance:
  - `urn:ricora:grafo:<fondo>:publico`: sin lo clasificado ni lo reservado (Ley 1712);
  - `urn:ricora:grafo:<fondo>:completo`: todo.
- **Cada cambio queda marcado** en la misma transacción que lo produce. Esto vale para cualquier cambio que entre en el grafo de un fondo: una descripción, una relación, una entidad del vocabulario, una instanciación, un nombre o una fecha.
- **El trabajador rearma el grafo marcado**, lo valida contra RiC-O 1.1 (OWL y el perfil SHACL) y lo reemplaza en el almacén de una sola vez. Quien consulta ve el grafo anterior o el nuevo, nunca uno a medias.
- **Leen del almacén, no de las tablas:**
  - el punto SPARQL (la consulta corre en Oxigraph);
  - las URI `/id/…`;
  - la descarga RiC-O (Turtle y JSON-LD), pública y con permiso;
  - la validación de conformidad;
  - el fragmento del grafo y el paquete de difusión (DIP).
- **Nunca se sirve un grafo viejo.** Si alguien lee un grafo que todavía no está al día, se rearma antes de responder.
- **Queda constancia de cada grafo guardado:**
  - versión de los datos y versión guardada;
  - fecha;
  - número de tripletas;
  - huella SHA-256 de las N-Triples ordenadas, que da el mismo valor para el mismo grafo;
  - si es conforme con RiC-O 1.1 y cuántos problemas OWL y resultados SHACL tuvo;
  - el error, si lo hubo.
- **Pantalla Instrumentos › RiC-O, tarjeta «Grafo RiC-O guardado»:** muestra el estado de cada grafo. La administración puede «Rearmar ahora», y esa acción queda en la auditoría.
- **Línea de comandos:** `python -m app.cli sincronizar-grafo` rearma todos los grafos. Sirve después de restaurar la base, porque el grafo siempre se puede reconstruir desde ella.
- **Salud del servidor:** `/api/salud` informa si el almacén responde (pieza `grafo_rdf`).

### En producción

El almacén vive en su propio servicio (`grafo`, la misma imagen, volumen `grafo`). Es el único proceso que escribe; la web y el trabajador lo usan por la red interna de Docker con una credencial derivada de la clave del sistema. No publica ningún puerto. En pruebas y desarrollo se abre dentro del mismo proceso (en memoria o en `RICORA_GRAFO_DIRECTORIO`).

## 1 bis. El grafo es la fuente de verdad de lo publicado (versión 2)

**Pedido de la autora:** que la fuente de verdad deje de ser la base relacional. Alcance elegido: **lo publicado** (la descripción archivística). Borradores, propuestas de la IA, usuarios, auditoría y evaluación siguen en tablas: no son descripción, y buena parte no tiene expresión en RiC-O 1.1.

**Qué significa, en concreto:**

1. **Tres grafos por fondo en el almacén.**
   - `…:completo` y `…:publico`: la descripción en RiC-O 1.1.
   - `…:control`: **solo lo que RiC-O 1.1 no puede expresar** y el sistema necesita, por ejemplo:
     - procedencia y confianza de cada dato (si lo propuso la IA o lo escribió una persona);
     - años de retención de la TRD;
     - archivo y huella de cada instanciación;
     - rol, fragmento y estado de cada relación;
     - estado e historia de las entidades;
     - fechas de registro y quién registró.

   El grafo de control nunca se publica: ni el SPARQL, ni las URI, ni las descargas lo ven. Se escribe con el grafo completo en una sola actualización.
2. **RiC-O primero.** Cada dato se lee del grafo RiC-O si allí queda exacto. Solo si no, va al grafo de control. En la base de prueba (72 filas), **121 de los 134 datos descriptivos que RiC-O puede expresar (90 %) se reconstruyen directamente desde RiC-O**: títulos, códigos, alcance y contenido, condiciones de acceso y de uso, historia, notas, jerarquía, forma documental, nombres, fechas y extremos de las relaciones. Los 13 restantes son de entidades o documentos que no se publican (mecanismos, entidades anuladas o reservadas) y van completos en el control.
3. **Ida y vuelta exacta.** Desde el almacén se pueden rehacer las tablas de lo publicado de un fondo, columna por columna. La prueba es tablas → grafo → tablas sin una sola diferencia. Se comprobó con la base de prueba: dos fondos y 97 filas, 0 diferencias.
4. **Publicar es escribir en el grafo validado.** Al publicar o corregir una descripción, el grafo del fondo se arma, **se valida contra RiC-O 1.1 (OWL y SHACL)** y se escribe en el almacén antes de confirmar. Si no es conforme, la publicación se rechaza con el motivo y no queda nada a medias.
5. **El grafo gana.**
   - Cada media hora, el trabajador compara las tablas con el grafo guardado. Si alguien cambió las tablas por fuera del sistema (con SQL directo, una restauración parcial…), crea la alerta «Las tablas no coinciden con el grafo RiC-O».
   - En **Instrumentos › RiC-O** cualquiera puede «Comparar tablas con el grafo». La administración puede además «Rehacer las tablas desde el grafo», y eso queda en la auditoría.
   - Por línea de comandos: `python -m app.cli reconstruir-desde-grafo`.
6. **Recuperación.** Con el volumen del grafo y las tablas de usuarios, la descripción publicada se rehace desde el grafo.

**Cómo fluye un cambio:**
1. La archivista trabaja en el espacio de trabajo: borrador, propuestas de la IA, tablas.
2. Publica: el grafo se arma y se valida, se escribe en el almacén y se confirma.
3. Las tablas de lo publicado quedan como **proyección** del grafo, para que las pantallas respondan rápido. Si una vez difieren, se rehacen desde él.

**Límites (para decirlo con exactitud):**
- **Lo que gana es el grafo de lo publicado.** Los cambios que hace el propio sistema por su camino normal (formularios, trabajador, fusión de entidades) se llevan al grafo; lo que se cambia por fuera se detecta y se corrige desde el grafo.
- **La reconstrucción necesita las tablas que no son descripción** (usuarios, lotes de transferencia), porque las filas las citan. Esas se respaldan con la base.
- **Las pantallas siguen leyendo la proyección relacional**, no el grafo en cada consulta, por rendimiento.

## 2. Términos RiC junto a los niveles

- **Dónde aparece:** junto al nombre archivístico de cada nivel (fondo, sección, serie, subserie, expediente, unidad documental, parte), en la ficha, el registro, el espacio de trabajo, «Publicadas», el vocabulario y el cuadro de clasificación. Muestra la clase y el tipo de agrupación con que ese nivel se guarda en RiC-O. Por ejemplo, «Serie» lleva `rico:RecordSet · rst:Series`.
- **Niveles sin tipo oficial en RiC-O** (sección, subsección, subserie): se muestran con «≈» y el tipo oficial más cercano, que es el `skos:broadMatch` que se exporta. Por ejemplo, «Subserie» lleva `rico:RecordSet · ≈ rst:Series`.
- **Una sola fuente:** la equivalencia sale de `ric_o.py` y se genera para la interfaz con `python -m app.cli terminos`. La pantalla no lleva una copia propia.

## 3. Lo que sigue en PostgreSQL, y por qué

- **El trabajo diario:**
  - borradores y propuestas del motor;
  - bloqueo de edición;
  - versiones de cada descripción;
  - usuarios, roles y permisos;
  - auditoría encadenada;
  - evaluación ciega.

  Nada de esto es descripción publicada. Necesita transacciones, bloqueos y restricciones que una base relacional da y un almacén de tripletas no.
- **El grafo de contexto visual** (Instrumentos › Grafo). Sigue consultando las tablas, con filtros por estado, origen y fechas que no están en RiC-O, como «propuesto por el motor» o «anulado». Lo que se exporta desde esa pantalla sí sale del grafo guardado.

## 4. Cómo decirlo en la tesis

> «La descripción publicada tiene como fuente de verdad un grafo RiC-O 1.1 en un almacén de tripletas (Oxigraph, SPARQL 1.1), un grafo por fondo: publicar es escribir en él, validado antes contra la ontología oficial (OWL) y un perfil SHACL. Lo que RiC-O 1.1 no puede expresar se conserva en un grafo de control interno. Desde ese almacén se reconstruyen exactamente las tablas de lo publicado, que el sistema usa como proyección para responder rápido. El proceso de trabajo (borradores, propuestas de la IA, revisión y auditoría) se gestiona en una base relacional.»

Se puede demostrar: la prueba de ida y vuelta, la pantalla RiC-O (estado de cada grafo, comparación y reconstrucción) y el SPARQL público. No conviene escribir «todo el sistema es RDF», porque no lo es (ver §3).

## 5. Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Dónde vive la descripción publicada | Solo tablas, traducidas al consultar; **grafo guardado y sincronizado**; RDF como única fuente | **Grafo guardado y sincronizado** (decisión de la autora) | La descripción se consulta y se entrega como RDF de verdad, sin reescribir el sistema antes de la sustentación | Dos lugares con los mismos datos: se mitiga con la marca en la misma transacción, la versión por grafo y la regla «nunca se sirve un grafo viejo» |
| Almacén de tripletas | Apache Jena Fuseki (Java); GraphDB (licencia); **Oxigraph** | **Oxigraph** | Libre (MIT/Apache), SPARQL 1.1 completo, sin máquina virtual de Java, se instala con pip y se prueba en memoria | Proyecto más joven que Jena; si hiciera falta, el grafo se rearma en otro almacén con `sincronizar-grafo` |
| Quién escribe en el almacén | Cada proceso abre el almacén; **un solo servicio** | **Un servicio** | El almacén en disco no admite dos procesos escribiendo a la vez | Un contenedor más; si se cae, la salud del servidor lo informa y las lecturas responden 503 con el motivo |
| Granularidad del rearmado | Por documento; **por fondo y alcance** | **Por fondo** | Es lo que define el grafo público (lo reservado depende del fondo completo) y es simple de verificar | Un fondo muy grande tarda más en rearmarse; para el caso de la tesis (decenas o cientos de documentos) son segundos |
| Cuándo se rearma | Al publicar; **en cada cambio, por el trabajador, y al leer si no está al día** | **Ambos** | El trabajador lo mantiene al día; la lectura garantiza que nunca se sirve uno viejo | Una lectura justo después de un cambio tarda lo que tarde el rearmado |
| Grafo público y completo | Un grafo y filtrar al consultar; **dos grafos** | **Dos** | Lo clasificado o reservado nunca está en el grafo que consulta el público; no depende de un filtro | El doble de espacio, despreciable a esta escala |
| Fuente de verdad | Tablas (grafo derivado); **grafo de lo publicado**; todo en RDF | **Grafo de lo publicado** (decisión de la autora) | Lo archivístico vive validado en RiC-O; lo que es proceso (borradores, IA, usuarios, auditoría) no es descripción y en buena parte no cabe en RiC-O 1.1 | Dos representaciones de lo mismo: la comparación periódica y la reconstrucción las mantienen iguales, y el grafo gana |
| Lo que RiC-O no expresa | Perderlo; extender RiC-O con propiedades propias en el grafo público; **grafo de control interno** | **Grafo de control** | Sin él, el grafo no basta para reconstruir el sistema; publicarlo mezclaría datos internos (procedencia de la IA, rutas de archivo) con la descripción | El control usa un vocabulario propio (`urn:ricora:control#`), no RiC-O: se declara como tal |
| Qué se lee de RiC-O | Todo del control (más simple); **RiC-O primero, control solo para lo inexacto** | **RiC-O primero** | Así el grafo RiC-O es de verdad la fuente, no una copia decorativa: el 90 % de lo descriptivo se lee de él | Cada lector de RiC-O debe dar el valor exacto; si no, el dato va al control (lo garantiza la prueba de ida y vuelta) |
| Cuándo se valida | Después de publicar (alerta); **antes de publicar (bloquea)** | **Antes** | Nada no conforme entra a la fuente de verdad | Publicar tarda unos segundos más (OWL y SHACL) |
| Diferencias entre tablas y grafo | Corregir solas; **avisar y que la administración rehaga** | **Avisar y rehacer a mano** | Rehacer en automático, ante un error del cargador, cambiaría datos sin que nadie lo vea | Mientras nadie actúe, la pantalla puede mostrar el dato alterado; la alerta es de severidad alta |
| Términos RiC en la interfaz | Solo ISAD(G); solo RiC; **los dos** | **Los dos** (decisión de la autora) | La archivista reconoce su término y ve con qué clase y tipo de RiC-O queda | Más texto en pantalla; va en letra pequeña |

## 6. Pruebas

| Archivo | Qué comprueba |
|---|---|
| `tests/test_grafo_rdf.py` (6) | El grafo guardado sigue cada cambio (título corregido → el viejo ya no está) y es conforme; si el almacén perdió un grafo (base restaurada sin su volumen), se rearma solo; una relación anulada marca su fondo; el trabajador sincroniza lo pendiente; estado y «rearmar» (solo administración) y la pieza de salud; el servicio HTTP exige su credencial, reemplaza de una vez, no acepta nombres de grafo ajenos y el cliente remoto da lo mismo que el embebido |
| `tests/test_cierre_bloque4_ins.py`, `tests/test_exportacion_rico.py` | El SPARQL, las URI y las descargas, ahora desde el almacén, siguen dando lo mismo (Turtle y JSON-LD isomorfos, lo reservado fuera) |
| `tests/test_grafo_fuente.py` (5) | Ida y vuelta exacta (tablas → grafo → tablas, columna por columna); RiC-O primero (el título y la jerarquía no se repiten en el control; la procedencia del dato sí va); el grafo gana (cambios y borrados por fuera se detectan y se corrigen desde el grafo); el control nunca sale (SPARQL, completo, público); publicar valida y escribe el grafo en el mismo momento, y lo no conforme no se publica; comparar y rehacer por la API (solo administración) y la alerta del trabajador |
| `tests/test_terminos.py` | La equivalencia nivel → RiC-O de la interfaz está sincronizada con `ric_o.py` |
