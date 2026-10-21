# Arquitectura de RICORA: tablas de trabajo y grafo RiC-O como fuente de verdad

Documento para el capítulo de diseño de la tesis. Dice qué es nativo de RiC en
RICORA, qué no lo es y por qué. Los detalles técnicos están en
`grafo-rico-persistente.md`, `parametrizacion-trd.md`, `importacion-rico.md` y
`disposicion-final.md`.

## La arquitectura en una frase

> La descripción archivística publicada vive en un grafo RiC-O 1.1 (un almacén de
> tripletas, un grafo por fondo), que es su fuente de verdad. El trabajo que lleva a
> publicarla vive en una base relacional: borradores, propuestas de la IA,
> parametrización de la TRD, usuarios y auditoría.

## Las dos capas

| | Tablas de trabajo (PostgreSQL) | Grafo RiC-O (Oxigraph, SPARQL 1.1) |
|---|---|---|
| Qué guarda | Lo que todavía no es descripción: borradores, propuestas del motor, bloqueos de edición, versiones, la TRD en borrador, usuarios, roles, auditoría encadenada, evaluación. También una **proyección** de lo publicado, para responder rápido. | La descripción publicada en RiC-O 1.1: recursos, agentes, lugares, fechas, reglas, actividades, relaciones. Lo que RiC-O no puede expresar va a un grafo de control interno, que nunca se publica. |
| Quién escribe | Las pantallas, el trabajador y la API. | Solo publicar, aplicar la TRD, registrar una disposición o importar. Antes de escribir se valida contra la ontología (OWL) y el perfil SHACL; si no es conforme, no se escribe nada. |
| Quién lee | Las pantallas (por rendimiento). | El SPARQL público, las URI de los datos enlazados, las descargas RiC-O y la comparación con las tablas. |
| Si difieren | Gana el grafo. El trabajador lo detecta y alerta; la administración rehace las tablas desde el grafo (ida y vuelta exacta, probada). | — |

## Qué es nativo de RiC (verificado en el código y en las pruebas)

1. **La descripción publicada.** Sus clases y relaciones son las de RiC-O 1.1 (RecordSet, Record, Instantiation, agentes, lugares, actividades, mandatos, reglas, fechas, identificadores), con la vigencia de cada relación.
2. **El cuadro de clasificación.** Solo nace de la TRD: las secciones, series y subseries se crean al aplicar una versión, nunca sueltas.
3. **La TRD como instrumento.** Cada versión es una `rico:Rule` con su vigencia, regulada por el acto que la aprueba (`rico:Mandate`). Sus partes son las reglas de retención de cada serie, y cada expediente se rige por la regla vigente en su fecha.
4. **La disposición y las transferencias como hechos.** Cada una es una `rico:Activity`, con su tipo, quién la ejerció, su fecha, la regla que la mandó y lo que afectó. Nada se borra.
5. **La función que produce cada serie.** Es un `rico:ActivityType` relacionado con la serie. El sistema avisa qué series no la tienen.
6. **Interoperabilidad en los dos sentidos.** El sistema exporta RiC-O (Turtle y JSON-LD), sirve las URI por negociación de contenido y ofrece SPARQL. También importa RiC-O de otros sistemas por el mismo camino de la parametrización, y cuenta lo que omite con su motivo.

## Qué no es nativo, y por qué está bien así

| Lo que no es RDF | Por qué |
|---|---|
| Borradores, propuestas de la IA, bloqueo de edición | No son descripción todavía. Necesitan transacciones y bloqueos que un almacén de tripletas no da. |
| Usuarios, permisos, auditoría encadenada | No son información archivística. La auditoría necesita orden e inmutabilidad (cadena de huellas), que se garantizan mejor en tablas. |
| La TRD en borrador (dependencias, banco, matriz) | Es la mesa de trabajo del instrumento. Lo aplicado sí está en el grafo. |
| Las pantallas leen la proyección relacional | Por rendimiento. La proyección se puede rehacer desde el grafo en cualquier momento. |

## Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Fuente de verdad | Todo en tablas; todo en el grafo (editar con SPARQL Update); lo publicado en el grafo y el trabajo en tablas | Lo publicado en el grafo, el trabajo en tablas | La descripción es lo que debe ser RiC. El proceso de trabajo necesita transacciones, bloqueos, restricciones y una auditoría que la base relacional resuelve bien. Editar todo con SPARQL Update obligaría a reimplementar todo eso sin ganar conformidad. | Dos copias de lo publicado. Se mitiga con la comparación periódica, la alerta y la reconstrucción desde el grafo. |
| Cuándo se escribe el grafo | Cada noche; en cada cambio, después de validar | En cada cambio, después de validar | Lo publicado nunca queda fuera de RiC-O, ni un minuto. | Publicar tarda lo que tarda validar el fondo. |
| Lo que RiC-O no expresa | Perderlo; inventar propiedades; un grafo de control separado | Grafo de control separado, nunca publicado | No se contamina el RiC-O público con propiedades inventadas, y la ida y vuelta es exacta. | El grafo de control es propio de RICORA; otro sistema no lo entiende, y no lo necesita. |

## Cómo decirlo en la tesis (sin exagerar)

> «RICORA es un sistema de descripción archivística nativo de RiC en lo que
> describe: la descripción publicada, el cuadro de clasificación, la TRD como
> instrumento y la disposición final se expresan y validan en RiC-O 1.1, y esa
> representación es la fuente de verdad. El proceso de trabajo (borradores,
> asistencia de la IA, parametrización, usuarios y auditoría) se gestiona en una
> base relacional, por razones de transaccionalidad, concurrencia e integridad
> de la auditoría.»

No conviene escribir «todo el sistema es RDF»: no lo es, y la tabla de arriba
explica por qué no debe serlo.
