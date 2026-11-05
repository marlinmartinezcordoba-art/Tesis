# Anexo: prueba de interoperabilidad con herramientas independientes

Fecha: 5 de noviembre de 2026.

**Pregunta:** ¿lo que RICORA publica lo leen herramientas distintas de las que lo producen?

## Muestras

- `../rico-ejemplo/fondo-de-prueba.ttl` y `.jsonld`: fondo completo de prueba (196 tripletas).
- Fondo de demostración, exportado de `/api/publico/rdf` (16 tripletas).
- `fondo-ead3.xml` (EAD3) y `agente-eac.xml` (EAC-CPF 2.0), exportados de `/api/publico/ead3` y `/api/publico/eac/{id}`.

## Herramientas

RICORA escribe el RDF con rdflib (Python). Para leerlo se usó **Oxigraph 0.5.11**, un motor RDF escrito en Rust, independiente de rdflib. Los XML se validaron con **xmllint** (libxml2 2.9.14) contra los esquemas oficiales de la SAA.

## Resultados

| Muestra | Herramienta | Resultado |
|---|---|---|
| fondo-de-prueba.ttl | Oxigraph | 196 tripletas; el mismo grafo que lee rdflib (isomorfo) |
| fondo-de-prueba.jsonld | Oxigraph | 196 tripletas; el mismo grafo |
| Fondo de demostración (Turtle) | Oxigraph | 16 tripletas; el mismo grafo |
| Fondo de demostración (JSON-LD) | Oxigraph | 16 tripletas; el mismo grafo |
| fondo-ead3.xml | xmllint + ead3.xsd (SAA) | Valida |
| agente-eac.xml | xmllint + eac.xsd (SAA) | Valida |

La lectura con Oxigraph quedó además dentro de la **Prueba de interoperabilidad** de la pantalla «Adopción de RiC», y se repite en cada despliegue (`tests/test_interoperabilidad.py`).

## Límites (para la tesis)

- No es una prueba con un sistema archivístico de otro proveedor, como AtoM o Archivematica. Demuestra que RICORA cumple las normas que esos sistemas leen: RDF 1.1, RiC-O 1.1, EAD3 y EAC-CPF 2.0.
- xmllint y la librería lxml de RICORA comparten libxml2. La validación XML es independiente del código de RICORA, pero no del motor de validación.
- Se intentó usar Apache Jena (riot y SHACL). No se ejecutó en el entorno de desarrollo, que no permite correr programas descargados. Queda como verificación adicional recomendada.
