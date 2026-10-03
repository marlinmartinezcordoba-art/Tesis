# Auditoría de especialización RiC

Fecha: 3 de octubre de 2026. Pregunta: ¿qué tan implementado está RiC en RICORA y qué le falta para ser un sistema especializado en RiC, y no solo un sistema que exporta RiC?

## 1. Cómo se midió

- **Contra la ontología oficial.** La referencia es `app/recursos/ric-o/RiC-O_1-1.rdf`, no la documentación del proyecto.
- **Uso real.** Un complemento de pytest intercepta cada exportación que hacen las pruebas y registra las clases y propiedades RiC-O que salen de verdad. La cifra es un piso: lo que ninguna prueba ejerce no se cuenta.
- **Atributos de RiC-CM.** La correspondencia RiC-A ↔ propiedad se toma de `rico:RiCCMCorrespondingComponent` en el propio OWL.

## 2. Diagnóstico

RICORA **produce RiC conforme**: ningún término fuera del OWL, validación contra el OWL y contra el perfil SHACL antes de exportar, y URI que se pueden consultar una por una. Pero **todavía no es nativo en RiC**: el fondo parte todo el sistema (agentes, permisos, exportación), no importa RiC-O y, antes de este cierre, no decía con qué certeza afirmaba cada relación.

| # | Brecha | Prioridad | Estado |
|---|---|---|---|
| 1 | No se exportaban la certeza, la fuente ni el estado de cada relación | Alta | **Cerrada** |
| 2 | Datos que el sistema ya tenía y no mapeaba a RiC-O | Alta | **Cerrada**, con dos correcciones al diagnóstico (abajo) |
| 3 | Fechas sin tipo (SingleDate, DateRange, DateSet; RiC-A42) | Media | Abierta |
| 4 | No importa RiC-O, EAD3 ni EAC-CPF | Alta | Abierta (decisión de alcance) |
| 5 | Una autoridad por fondo, sin procedencia múltiple | Alta | Abierta (decisión de alcance, VOC-05) |
| 6 | Grafo generado al vuelo por fondo, sin almacén RDF ni SPARQL entre fondos | Media-alta | Abierta |
| 7 | Atributos de tipología (A07, A10, A12, A15, A18, A20, A30, A33, A37) | Media | Abierta |
| 8 | Group, autor y acumulador | Baja | **Cerrada** (era más grave de lo reportado) |
| 9 | Infraestructura: segunda copia en el mismo disco, datos abiertos apagados | — | No es código |

### Correcciones al propio diagnóstico, encontradas al cerrar

- **Ubicación física.** `rico:PhysicalLocation` es la delimitación física de un **Lugar** (Place), no la ubicación de una caja en el depósito. Mapear caja y carpeta ahí habría sido un error de conformidad. La ubicación del original sigue contada como omitida: RiC-O 1.1 no tiene una propiedad de dato para la ubicación de una Instantiation.
- **Integridad.** `rico:integrityNote` es la **completitud intelectual** de un recurso, no la verificación de huella. La fijeza va en `rico:authenticityNote` («no ha sido alterado ni corrompido»), cuyo dominio admite la Instantiation.
- **Estado del registro.** `rico:RecordState` describe el estado de producción del documento (borrador, original, copia), no el de la descripción. Publicado o borrador es el estado de la ficha, así que no se mapea ahí. El sistema no registra la tradición documental, por eso no se exporta.
- **Brecha 8.** Autor y acumulador no estaban «mapeados sin probar»: eran **códigos reservados**, y el sistema rechazaba crearlos.

## 3. Lo que se cerró

| Brecha | Qué sale ahora en RiC-O | Pruebas |
|---|---|---|
| 1 | Cada relación exportada es un nodo `rico:Relation` con la clase más específica de RiC-O 1.1, orientada como la define el OWL, con: `relationSource` (persona o motor de análisis, y el fragmento citado si el archivo no está restringido); `relationCertainty` (alta, media o baja, con la confianza del motor), solo si la propuso el motor y nadie la corrigió; y `relationState` (vigente o terminada), solo si su vigencia lo dice. | `tests/test_especializacion_ric.py` (5) y `tests/test_exportacion_rico.py` |
| 2 | `rico:Extent` con `quantity` (decimal) y `unitOfMeasurement`: folios del documento; bytes y páginas del archivo. `qualityOfRepresentationNote` (RiC-A34) con la confianza del OCR. `authenticityNote` (RiC-A03) con la huella de ingreso, la última verificación y la validación del formato. `migrationDate` y `derivationDate`. | `tests/test_especializacion_ric.py` (3) |
| 8 | `rico:hasAuthor` (RiC-R079) y `rico:hasAccumulator` (RiC-R028) mapeados, con roles «autor» y «acumulador» al describir y en la interfaz. `rico:Group` exportado. Nodos `AuthorshipRelation`, `AccumulationRelation` y `MembershipRelation`. | `tests/test_especializacion_ric.py`, `tests/test_especializacion_ric_autoria.py` (3) |

Cada exportación de estas pruebas pasa, además, la verificación OWL y el perfil SHACL, que ahora tiene formas para `rico:Relation` (fuente, destino y certeza con su patrón) y `rico:Extent` (cantidad decimal y unidad).

## 4. Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Qué relaciones llevan nodo | Solo las de agentes y mandatos (VOC-06) · todas | **Todas** | La certeza y la fuente valen para cualquier relación. La mayoría de las que propone el motor son de documento a agente. | El grafo crece unas cinco tripletas por relación. |
| Clase del nodo | Siempre `rico:Relation` · la más específica | **La más específica** que tiene RiC-O 1.1 (CreationRelation, WholePartRelation, MigrationRelation…), y `rico:Relation` si no hay una | Un consumidor RiC puede filtrar por tipo de relación sin leer la tripleta binaria. | Si RiC-O cambia la jerarquía, hay que revisar el mapeo. La prueba contra el OWL lo detecta. |
| Orientación | La de la tripleta del sistema · la del OWL | **La del OWL**: PerformanceRelation, RecordResourceHoldingRelation y TypeRelation van al revés | Cada clase define su fuente y su destino. Copiar la tripleta habría invertido el sentido en esas tres. | Ninguno conocido. |
| Certeza | Número suelto · categoría · ambos | **Categoría con el número**: «alta (confianza del motor: 0.93)». Umbrales del sistema: 0,8 y 0,5 | La categoría se lee sin contexto y el número permite reanalizar. Los umbrales son del sistema, no de RiC-O, y así se documentan. | Otro sistema puede usar otros umbrales. |
| Certeza de lo corregido | La del motor · ninguna | **Ninguna** si una persona la corrigió (`motor_editado`) o la registró | La confianza del motor describe su propuesta, no lo que quedó después de la corrección. | Lo registrado por una persona sale sin certeza, no como «cierta». Así no se inventa una certeza que nadie midió. |
| Nombre del motor en la fuente | Nombrarlo · no | **No** se nombra | Se mantiene la decisión anterior: el motor no se exporta como agente. La fuente dice «propuesta por el motor de análisis». | Quien consulte no sabe qué motor fue. Queda en la auditoría interna. |
| Fragmento citado | Siempre · nunca · solo si el archivo es público | **Solo si el archivo del que sale no está restringido** | Citar un fragmento es publicar parte del contenido. Si el archivo está reservado, se omite y se cuenta. | Ninguno conocido. |
| Confianza de los atributos | Exportarla · no | **No** (alcance, idiomas…) | RiC-O solo tiene certeza para una relación, no para un atributo. Inventar una propiedad rompería la conformidad. | Esa procedencia queda solo en el sistema. |
| Cantidad decimal | `"12"` · `"12.0"` | **`"12.0"`** (forma canónica) | Turtle y JSON-LD leen igual la forma canónica; con «12», las dos serializaciones dejaban de coincidir. | Ninguno. |
| Autor | Mismo rol que productor · rol propio con el dominio del OWL | **Rol propio**: solo en una unidad documental, y solo persona, grupo o cargo | Es lo que dice `rico:hasAuthor`. Una entidad corporativa o una familia van como productor. | El motor de análisis no propone autor ni acumulador: se declaran a mano. |
| Comprobación de rango en el mapeo | Clase exacta · la clase o una subclase | **La clase o una subclase** (InstantiationExtent ⊂ Extent) | Es la semántica de RDFS: si el rango es una clase, una instancia de su subclase lo cumple. | Ninguno. |

## 5. Cobertura antes y después

Ver la sección 6, que se completa con la medición sobre la batería completa.
