# Anexo · Exportación RiC-O 1.1 del fondo de prueba

Exportación real producida por RICORA con el mismo código de la pestaña **Instrumentos › RiC-O** («Descargar Turtle», «Descargar JSON-LD», «Validar conformidad»). Es la evidencia del objetivo 2 de la tesis: la arquitectura es conforme a RiC-O, y eso se **comprueba** sobre los datos, no solo se afirma.

- `fondo-de-prueba.ttl`: el fondo en Turtle.
- `fondo-de-prueba.jsonld`: el mismo grafo en JSON-LD. Las dos serializaciones son isomorfas; una prueba lo comprueba.
- `conformidad.json`: el reporte de conformidad tal como lo entrega `GET /api/exportacion/conformidad`.

## Qué dice el reporte

| Comprobación | Resultado |
|---|---|
| Contra el OWL oficial de RiC-O 1.1 (2025-05-22): cada clase y cada propiedad existe; cada tripleta respeta el dominio y el rango declarados, con sus superclases; ningún predicado fuera de RiC-O, RDF, RDFS, SKOS y OWL | **Conforme**, 0 problemas |
| Contra el perfil SHACL del sistema (`app/recursos/ric-o/perfil-ricora.shacl.ttl` más una forma por relación generada desde el mapeo único): 41 formas | **Conforme** |
| El mapeo único (`app/servicios/ric_o.py`) contra el OWL | 0 problemas |

**196 tripletas.** Por clase: 1 RecordSet (el fondo), 1 Record, 1 RecordPart (el sello recortado), 2 Instantiation, 5 CorporateBody, 1 Group, 3 Place, 2 Activity, 2 ActivityType (SKOS), 2 Mandate, 9 Date, 2 Event (línea de tiempo del agente), y los nodos de apoyo: AgentName, PlaceName, Identifier, IdentifierType, LegalStatus, PlaceType, MandateType, Language.

## Lo que no se exportó, y por qué (lo dice el propio reporte)

- **1 borrador sin publicar.** Los borradores no salen nunca.
- **1 descripción bajo un nivel no exportado.** Es un dato de la siembra de prueba: una unidad documental publicada bajo una serie que se creó sin publicar. En el sistema real no ocurre (solo la descripción crea niveles, y siempre publicados). Se descarta en vez de colgarla del fondo, para no exponer una estructura que nadie publicó.
- **1 estructura interna de un agente.** `rico:structure` solo admite Instantiation y RecordResource. RiC expresa la estructura de un agente con relaciones entre agentes (`rico:hasOrHadSubordinate`, que sí sale).
- **2 relaciones con un extremo no exportado** (las que apuntaban a lo anterior).

Además, por regla, nunca salen el origen ni la confianza de un dato (motor o persona), ni los agentes mecanismo (los programas que actúan en el sistema).

## Cómo validarlo por fuera del sistema

```
pip install rdflib pyshacl
python -c "import rdflib; g=rdflib.Graph().parse('fondo-de-prueba.ttl'); print(len(g))"
pyshacl -s ../../../app/recursos/ric-o/perfil-ricora.shacl.ttl -e ../../../app/recursos/ric-o/RiC-O_1-1.rdf fondo-de-prueba.ttl
```

El segundo comando valida solo las formas escritas a mano; las formas de las relaciones las genera el sistema desde el mapeo (`app/servicios/conformidad_rico.py`).

Las URI empiezan por `http://localhost:8000/id/` porque se generó en el entorno de desarrollo. En el servidor llevan su dirección pública.

Los datos son material de prueba del proyecto, no documentos de archivo reales.
