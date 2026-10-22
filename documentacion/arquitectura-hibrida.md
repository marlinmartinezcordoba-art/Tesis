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
| Quién lee | Las pantallas de trabajo (descripción, vocabularios, parametrización). | El SPARQL público, las URI de los datos enlazados, las descargas RiC-O, la comparación con las tablas y, **desde el 22 de octubre de 2026, toda la consulta**: catálogo, ficha, resumen, índice, inventario FUID, guía, instrumentos aprobados y buscador, a través de una proyección rehecha desde el grafo (ver abajo). |
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
| Las pantallas de trabajo leen las tablas | Quien describe trabaja sobre borradores que todavía no están validados en RiC-O. La consulta ya no lee las tablas de trabajo: lee lo que dice el grafo. |

## La consulta lee del grafo (22 de octubre de 2026)

Antes, todo lo que veía un lector salía de las tablas de trabajo, y el grafo
solo se usaba para descargar, para SPARQL y para comparar. Ahora la consulta
lee una **proyección rehecha desde el grafo guardado**
(`app/servicios/lectura.py`):

1. Cuando el grafo de un fondo cambia, se leen del almacén de tripletas el
   grafo completo y el de control.
2. Con ellos se reconstruyen las filas de la descripción
   (`grafo_control.filas_desde_grafo`, la misma ida y vuelta exacta que ya
   estaba probada).
3. Esas filas se escriben en un esquema aparte de PostgreSQL, `lectura`, con
   las mismas tablas de la descripción.
4. El catálogo, la ficha, el resumen, el índice, el inventario FUID, la guía,
   los instrumentos aprobados, el buscador y el árbol de las URI públicas leen
   de ese esquema.

La prueba que lo demuestra (`tests/test_consulta_desde_grafo.py`): se cambia el
título de un documento directamente en la tabla de trabajo, sin pasar por el
sistema. La ficha, el catálogo, el buscador y el FUID siguen mostrando el título
del grafo, y la comparación periódica detecta la diferencia.

Medido (servidor de desarrollo):

| Fondo | Rehacer la proyección | Primera consulta tras un cambio | Consulta sin cambios |
|---|---|---|---|
| 5 a 14 descripciones | 0,07 a 0,3 s | 0,2 a 2 s | 7 a 11 ms |
| 500 documentos (sintético) | 4 s | 7 s (3 s de sincronizar el grafo y validarlo, 4 s de proyección) | 10 ms |

Para que nadie espere esos segundos, el trabajador rehace la proyección justo
después de sincronizar el grafo. La espera solo la ve quien consulta en el
instante siguiente a un cambio, antes de que el trabajador pase.

### Decisiones de la consulta desde el grafo

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo lee la consulta el grafo | SPARQL en cada pantalla; proyección rehecha desde el grafo | Proyección rehecha desde el grafo | Las reglas de la consulta (reserva de la Ley 1712, fechas heredadas, retención, conteos) ya existen y están probadas sobre tablas. Reescribirlas en SPARQL duplicaría las reglas y su riesgo. Con la proyección hay una sola implementación y cambia de dónde vienen los datos. | La proyección es una copia más. Se rehace sola cuando el grafo cambia y una prueba demuestra que dice lo mismo que el grafo. |
| Dónde vive la proyección | Otra base; un esquema aparte en la misma base | Esquema `lectura` | Se consulta con el mismo código y en la misma transacción; las tablas que no son descripción (usuarios, alertas, preservación) siguen en el esquema público. | Si una migración cambia una tabla de la descripción, la proyección la rehace sola la próxima vez (compara las columnas). |
| Si el almacén de tripletas no responde | Error; leer las tablas de trabajo | Leer las tablas y dejarlo en el registro | Que un lector no se quede sin catálogo por una falla de infraestructura. La salud del sistema ya avisa que el almacén falla. | Mientras dure la falla, la consulta no es «desde el grafo». Queda en el registro. |
| Cuándo se rehace | En cada consulta; cuando el grafo cambia | Cuando el grafo cambia, y el trabajador la deja lista | Sin cambios cuesta 10 ms. | La primera consulta justo después de un cambio puede tardar segundos en un fondo grande. |
| Qué queda leyendo tablas | Nada; el trabajo | Las pantallas de trabajo (describir, vocabularios, TRD) | El trabajo en curso todavía no es RiC-O validado. | Ninguno para la consulta. Es el límite declarado de la arquitectura híbrida. |

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
> representación es la fuente de verdad. Todo lo que se consulta (catálogo,
> fichas, buscador e instrumentos de descripción) se lee de ese grafo. El proceso de trabajo (borradores,
> asistencia de la IA, parametrización, usuarios y auditoría) se gestiona en una
> base relacional, por razones de transaccionalidad, concurrencia e integridad
> de la auditoría.»

No conviene escribir «todo el sistema es RDF»: no lo es, y la tabla de arriba
explica por qué no debe serlo.
