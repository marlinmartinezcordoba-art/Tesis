# Conformidad con RiC-O 1.1

Corrección transversal, hecha antes de revisar M3, M4 y M5. Afecta la exportación (M9), el SPARQL y el grafo.

## Auditoría (qué se encontró)
Se verificó el grafo completo de la plataforma contra la ontología oficial `RiC-O_1-1.rdf` del ICA-EGAD, incluida sin cambios en `ric/ontologia/`.

| Hallazgo | Cantidad (base local) | Causa |
|---|---|---|
| Atributos de «tipo» exportados como texto suelto (p. ej. `rico:hasDocumentaryFormType "acta"`) | 829 | En RiC-O, 20 de los 42 atributos son **propiedades de objeto** cuyo rango es una clase (`rico:DocumentaryFormType`, `rico:ActivityType`, `rico:Language`, `rico:RecordSetType`, `rico:MandateType`…); se emitían como literales |
| Un documento exportado con dos URI (`record/10` y `recordresource/10`) | 1 | Una relación guardó su origen con la clase general (herencia multitabla) y el exportador la tomó tal cual; en ese nivel RiC-O no admite el idioma |
| URI de entidades que no llevaban a ningún lado (`…/ric/entidad/…`) | Todas | La ruta no existía |
| Relaciones fuera del dominio o del rango de RiC-O | 0 | — |

## Qué se hizo
- **Validador** (`ric/conformidad.py`): revisa cada tripleta contra la ontología oficial. Comprueba que las clases y las propiedades existan, que las propiedades de objeto apunten a entidades y las de dato a textos, y que se respeten el dominio y el rango, incluida la jerarquía de clases y las uniones `owl:unionOf`.
- **Tipos como individuos:** cada atributo de tipo se emite como un individuo de su clase RiC-O, con su `rico:name` y una URI estable (`…/ric/entidad/tipo/ActivityType/funcion`). Qué atributo es de objeto y cuál de dato lo decide la ontología, no una lista hecha a mano. La forma documental controlada (M5) reemplaza al texto libre.
- **Una URI por entidad:** cada entidad se exporta con su clase más precisa (`rdf.mas_especifica`).
- **URI que se abren:** `…/ric/entidad/<tipo>/<id>`.
  - Desde un navegador, lleva a la ficha del catálogo.
  - Si la pide un programa (`Accept: text/turtle`, `application/rdf+xml` o `application/ld+json`, o `?formato=`), entrega el RDF.
  - Los tipos y la forma documental también se resuelven.
  - Todo exige sesión y respeta la visibilidad por rol.
- **Verificación en cada exportación:** el mensaje dice «✓ Conforme con la ontología RiC-O 1.1» o lista las observaciones.
- **Comando** `python manage.py verificar_rico`: verifica el grafo completo. El despliegue lo ejecuta y deja el resultado en su registro.

## Decisiones
| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Contra qué verificar | Formas SHACL propias; la ontología oficial | La ontología oficial RiC-O 1.1 | Es la fuente primaria; unas formas escritas a mano podrían equivocarse igual que el exportador | No valida cardinalidades ni reglas que RiC-O no declara como dominio o rango |
| Qué hacer si una exportación no es conforme | Bloquearla; entregarla con aviso | Entregarla con el aviso y las observaciones | El exportador ya produce 0 hallazgos; una observación indica un caso nuevo que la persona debe conocer, no una razón para perder el archivo | Alguien podría ignorar el aviso: queda en el mensaje de la exportación y en el registro del despliegue |
| Identidad de un tipo | Un individuo por entidad; uno por valor | Uno por valor (`tipo/<Clase>/<valor>`) | Todas las actividades de tipo «Función» comparten el mismo individuo, como un vocabulario | Dos grafías del mismo valor dan dos individuos; se unifican corrigiendo el valor |
| Acceso a las URI | Público; con sesión | Con sesión y visibilidad por rol | La plataforma guarda documentos sin publicar y reservados (Ley 1712, Ley 1581) | Todavía no son datos enlazados abiertos; abrirlos es una decisión institucional |

## Pruebas
`tests/test_conformidad_rico.py` (13 pruebas):
- la ontología se carga;
- toda URI de la matriz RiC existe en RiC-O (19 entidades, 85 relaciones, 42 atributos);
- el validador detecta textos donde va una entidad, propiedades inventadas y rangos incorrectos;
- el grafo con documentos, agentes, cargos, funciones, mandatos, fechas y lugares, y con nueve tipos de relación, es conforme;
- los tipos salen como individuos;
- hay una sola URI por entidad;
- el comando `verificar_rico` funciona;
- el mensaje de la exportación informa la conformidad;
- las URI se abren según quién las pida y respetan la sesión y el rol.

## Qué falta
- **Relaciones reificadas** (`rico:Relation`, con fechas de vigencia, certeza y fuente): se harán con la revisión de M3, M4 y M5.
- **Datos enlazados abiertos:** las URI exigen sesión.
