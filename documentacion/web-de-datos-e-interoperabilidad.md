# Web de datos e interoperabilidad

Estado de las cuatro mejoras propuestas frente a RiC, revisadas en el código el 5 de noviembre de 2026.

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Enlazar autoridades con vocabularios externos | Escribir el identificador a mano / búsqueda asistida | Ya existía el registro manual (Wikidata, VIAF, ISNI, LCNAF, ORCID, ROR, GeoNames → `owl:sameAs`). Se agrega **«Buscar en Wikidata»** en la ficha: propone candidatos con su descripción y su VIAF (P214); la archivista confirma | Enlazar sin escribir códigos, sin enlaces automáticos | Un homónimo mal confirmado; por eso se muestra la descripción y se pide confirmar |
| Consulta SPARQL pública | Solo interna / pública de solo lectura | Ya existía: `/api/publico/sparql`, de solo lectura, sobre lo público de un fondo o de todo el acervo; nunca incluye lo clasificado o reservado | Reutilización por otras instituciones | Ninguno nuevo |
| Cobertura de RiC | Las clases usadas / todo RiC-CM | Ya existía: atributos 42 de 42 y relaciones 85 de 85 de RiC-CM 1.0, medidos por `tests/test_cobertura_ric.py` | La cobertura se mide, no se declara | Ninguno nuevo |
| Pruebas de interoperabilidad | Solo pruebas automáticas / también en pantalla | Existían las pruebas de ida y vuelta. Se agrega la **Prueba de interoperabilidad** en «Adopción de RiC»: RiC-O 1.1, SHACL, cuatro formatos RDF releídos idénticos, reimportación con el importador de RiC-O, EAD3 y EAC-CPF contra los esquemas de la SAA y enlaces `owl:sameAs` | Evidencia que se muestra en vivo en la sustentación | Ninguno: no guarda nada y usa solo lo público |

Pruebas: `tests/test_wikidata.py` (Wikidata simulado), `tests/test_interoperabilidad.py`.

Privacidad: a Wikidata solo se envía el nombre de la autoridad.
