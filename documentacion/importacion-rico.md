# Importar un fondo descrito en RiC-O

## Qué hace

En **Fondos › 1. Cargar CCD y TRD › «Un fondo en RiC-O de otro sistema»** se carga
un archivo RiC-O 1.1 (Turtle, RDF/XML, JSON-LD o N-Triples, hasta 50 MB). El
sistema lo lee, muestra lo que trae, lo valida y solo entonces lo crea.

La importación es el espejo de la exportación (`app/servicios/exportacion_rico.py`).
Lee las mismas clases y propiedades que RICORA escribe y las lleva a sus tablas
por los mismos caminos que usa una persona.

| Lo que trae el RiC-O | Adónde va |
|---|---|
| `rico:RecordSet` de tipo `rst:Fonds` en la raíz | El fondo, con sus fechas, alcance e historia. |
| Secciones, subsecciones, series y subseries (`rico:hasRecordSetType`, o deducidas del árbol) | Las filas del CCD y la TRD. El fondo se registra con ellas **por la parametrización**, como en el asistente: versión 1 vigente si se da el acto, o en borrador si no. |
| La regla de una serie (`rico:Rule` que la regula) | La retención (AG, AC, disposición), si su texto la dice así: «2 año(s) en el archivo de gestión…», como la escribe RICORA. RiC-O no tiene propiedades para años. |
| `rst:File` y `rico:Record` | Expedientes y documentos dentro de su serie o subserie, con título, código, alcance, historia, condiciones y fechas. |
| `rst:Collection` | Colecciones. |
| `rico:Person`, `CorporateBody`, `Family`, `Group`, `Position`, `Agent`, `Place`, `DocumentaryFormType`, `Activity`, `ActivityType`, `Mandate`, `skos:Concept` | Vocabulario del fondo, sin duplicar por nombre. |
| Tripletas entre dos nodos importados con una propiedad del catálogo (o su inversa) | Relaciones, con su rol (productor, remitente, destinatario, autor, custodio, materia, lugar…), si el dominio y el rango la admiten. |

Al final se arma el grafo del fondo y se valida contra la ontología oficial (OWL)
y el perfil SHACL. Si no es conforme, o si algo falla, no queda nada creado.

## Cómo se deducen los niveles

Cuando un conjunto no declara su tipo, el sistema lo deduce por su lugar en el árbol:

- Si solo contiene documentos, es un expediente, o una serie si cuelga del fondo o de una sección.
- Si contiene expedientes o documentos, es una serie, o una subserie dentro de una serie.
- Si solo contiene conjuntos de conjuntos, es una sección, o una subsección dentro de una sección.

## Lo que no se importa (y lo dice)

La vista previa y el resultado cuentan cada omisión con su motivo:

- **Instanciaciones.** Los archivos no viajan en el RDF; se cargan en Carga de documentos.
- **Partes documentales** (`rico:RecordPart`).
- **Mecanismos.** El sistema registra los suyos.
- **La vigencia de los nodos `rico:Relation`.** Se toma la tripleta directa.
- **Propiedades entre clases que su dominio o rango no admiten.**
- **Relaciones con un extremo que no se importó.**

## Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Por dónde entra el cuadro | Crear las series directo desde el RDF; convertirlas en filas del CCD y la TRD y pasar por la parametrización | Por la parametrización | Es la regla del sistema: el cuadro solo nace de la TRD. Así un fondo importado queda igual que uno registrado a mano: versiones, dependencias, banco y matriz. | Lo que el RDF no dice de la TRD (acto, vigencia, retención en texto libre) hay que completarlo después. |
| Series sin sección | Inventar una sección; rechazar el archivo; pedir la dependencia productora | Pedirla, sugiriendo el productor del fondo | Muchos sistemas publican Fondo › Serie. El CCD exige la dependencia productora, y elegirla es un acto archivístico que no se hace en silencio. | Si el productor real era otro, la persona debe cambiar la sugerencia. |
| Retención | Ignorarla; leerla del texto de la regla | Leerla si el texto sigue la forma de RICORA | RiC-O no tiene propiedades para años de retención. Entre instancias de RICORA, la ida y vuelta es exacta. | Las reglas de otros sistemas llegan sin años: la matriz queda para completar a mano. |
| Validar antes de crear | Crear y avisar; validar y deshacer si no es conforme | Validar y deshacer | El mismo criterio que el asistente y la parametrización: nada fuera de RiC-O. | Un archivo con un solo error no entra hasta corregirlo en origen. |
| Archivos | Descargar las URL de las instanciaciones; no importarlos | No importarlos | Descargar de terceros sin control de integridad rompe la cadena de custodia (huella, formato, OCR). | Hay que cargar los archivos aparte. |
| Duplicados del vocabulario | Crear todo; unir por nombre normalizado | Unir por nombre | Evita dos «Notaría Primera» en el mismo fondo. Las fusiones finas se hacen en Posibles duplicados. | Dos homónimos distintos quedan unidos hasta separarlos. |

## Pruebas

`tests/test_importacion_rico.py`:

- **Ida y vuelta.** Un fondo de RICORA exportado en Turtle se importa igual: cuadro, retención, documento, remitente y fechas, conforme con RiC-O.
- **RiC-O externo sin secciones.** Se deducen los niveles, se pide la dependencia productora, se importan el productor, el remitente y el lugar.
- **Permisos y formato.** Solo la administración importa, y un archivo que no es RiC-O se rechaza.
