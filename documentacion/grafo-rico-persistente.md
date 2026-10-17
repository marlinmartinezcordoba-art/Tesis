# Grafo RiC-O persistente

**Versión:** 1.

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

> «La descripción publicada se guarda como grafo RiC-O 1.1 en un almacén de tripletas (Oxigraph, SPARQL 1.1), un grafo por fondo, validado contra la ontología oficial (OWL) y un perfil SHACL cada vez que cambia; la consulta, las URI persistentes y la exportación se sirven desde ese grafo. El trabajo de descripción (borradores, propuestas de la IA, revisión y auditoría) se gestiona en una base relacional.»

Es exacto y se puede demostrar: la pantalla RiC-O muestra cada grafo, sus tripletas, su huella y su conformidad, y el SPARQL público consulta el almacén. No conviene escribir «todo el sistema es RDF», porque no lo es (ver §3).

## 5. Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Dónde vive la descripción publicada | Solo tablas, traducidas al consultar; **grafo guardado y sincronizado**; RDF como única fuente | **Grafo guardado y sincronizado** (decisión de la autora) | La descripción se consulta y se entrega como RDF de verdad, sin reescribir el sistema antes de la sustentación | Dos lugares con los mismos datos: se mitiga con la marca en la misma transacción, la versión por grafo y la regla «nunca se sirve un grafo viejo» |
| Almacén de tripletas | Apache Jena Fuseki (Java); GraphDB (licencia); **Oxigraph** | **Oxigraph** | Libre (MIT/Apache), SPARQL 1.1 completo, sin máquina virtual de Java, se instala con pip y se prueba en memoria | Proyecto más joven que Jena; si hiciera falta, el grafo se rearma en otro almacén con `sincronizar-grafo` |
| Quién escribe en el almacén | Cada proceso abre el almacén; **un solo servicio** | **Un servicio** | El almacén en disco no admite dos procesos escribiendo a la vez | Un contenedor más; si se cae, la salud del servidor lo informa y las lecturas responden 503 con el motivo |
| Granularidad del rearmado | Por documento; **por fondo y alcance** | **Por fondo** | Es lo que define el grafo público (lo reservado depende del fondo completo) y es simple de verificar | Un fondo muy grande tarda más en rearmarse; para el caso de la tesis (decenas o cientos de documentos) son segundos |
| Cuándo se rearma | Al publicar; **en cada cambio, por el trabajador, y al leer si no está al día** | **Ambos** | El trabajador lo mantiene al día; la lectura garantiza que nunca se sirve uno viejo | Una lectura justo después de un cambio tarda lo que tarde el rearmado |
| Grafo público y completo | Un grafo y filtrar al consultar; **dos grafos** | **Dos** | Lo clasificado o reservado nunca está en el grafo que consulta el público; no depende de un filtro | El doble de espacio, despreciable a esta escala |
| Términos RiC en la interfaz | Solo ISAD(G); solo RiC; **los dos** | **Los dos** (decisión de la autora) | La archivista reconoce su término y ve con qué clase y tipo de RiC-O queda | Más texto en pantalla; va en letra pequeña |

## 6. Pruebas

| Archivo | Qué comprueba |
|---|---|
| `tests/test_grafo_rdf.py` (6) | El grafo guardado sigue cada cambio (título corregido → el viejo ya no está) y es conforme; si el almacén perdió un grafo (base restaurada sin su volumen), se rearma solo; una relación anulada marca su fondo; el trabajador sincroniza lo pendiente; estado y «rearmar» (solo administración) y la pieza de salud; el servicio HTTP exige su credencial, reemplaza de una vez, no acepta nombres de grafo ajenos y el cliente remoto da lo mismo que el embebido |
| `tests/test_cierre_bloque4_ins.py`, `tests/test_exportacion_rico.py` | El SPARQL, las URI y las descargas, ahora desde el almacén, siguen dando lo mismo (Turtle y JSON-LD isomorfos, lo reservado fuera) |
| `tests/test_terminos.py` | La equivalencia nivel → RiC-O de la interfaz está sincronizada con `ric_o.py` |
