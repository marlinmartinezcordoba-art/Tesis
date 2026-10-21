# Disposición final y transferencias como hechos de RiC

## Qué faltaba

La TRD dice qué se hace con cada serie al cumplir su retención. El sistema
guardaba la regla, pero no el hecho: cuando un expediente se eliminaba, se
seleccionaba o pasaba a conservación total, no quedaba en el grafo con quién,
cuándo y con qué acta. De las transferencias solo quedaba la custodia anterior.

## Qué hace ahora

**Fondos › Disposición final** muestra el calendario de retención del fondo. Para
cada expediente (y cada documento suelto en una serie) muestra:

- la regla que lo rige;
- la fecha en que cumple su retención: su fecha final más los años en el archivo de gestión y en el central;
- lo que manda la TRD.

Hay filtros para lo que cumplió, lo que sigue en retención y lo ya dispuesto.

La administración elige expedientes con la misma disposición y la registra con
su acta: número, fecha y quién la ejecuta. Queda una **`rico:Activity`** con:

| Dato | En RiC-O |
|---|---|
| Tipo (eliminación documental, selección, conservación total, medio técnico) | `rico:hasActivityType` → `rico:ActivityType` |
| Quién la ejecutó (comité o dependencia) | `rico:performsOrPerformed` (R060i), desde el agente |
| Fecha del acta | `rico:isDateAssociatedWith` (R068), desde el `rico:Date` |
| La regla de la TRD que la mandó | `rico:regulatesOrRegulated` (R063), desde la `rico:Rule` |
| El acta, si está descrita en el fondo | `rico:documents` (R033), desde la descripción |
| Lo que afectó | `rico:affectsOrAffected` (R059), con rol «disposicion» |

Al confirmar un lote (transferencia, donación, compra…) queda también una
`rico:Activity`, por ejemplo «Transferencia primaria · lote L-2026-0001 · acta
AT-014». La ejercen la dependencia de origen y el remitente, lleva la fecha del
acta y afectó a cada archivo recibido.

## Reglas

- Solo se dispone lo que la TRD manda: la disposición de la regla vigente en la fecha del expediente.
- Solo lo que ya cumplió su retención, a la fecha del acta. Un expediente sin fecha final no se dispone, porque no se sabe si cumplió.
- Lo dispuesto no se dispone dos veces.
- Nada se borra. El expediente eliminado sigue descrito; su estado se lee de la actividad que lo afectó. Es la evidencia de la eliminación, como el inventario que acompaña el acta.
- Antes de guardar se valida en RiC-O. Solo la administración registra.

## Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo se registra lo ejecutado | Un estado en el expediente; una tabla de actas; una `rico:Activity` | `rico:Activity` del vocabulario del fondo | Es un hecho con agente, fecha, norma y objetos afectados: en RiC eso es una actividad. Queda en el grafo y se consulta por SPARQL. | El estado de disposición se deduce de la relación; si alguien anula esa relación a mano, el expediente aparecería sin disponer (la auditoría lo registra). |
| Qué pasa con lo eliminado | Borrar la descripción; marcarla; dejarla y unirla a la actividad | Dejarla, unida a la actividad | Regla del proyecto: nada se borra. Además, la descripción es la evidencia de qué se eliminó. | El catálogo muestra descripciones de documentos que ya no existen físicamente; la ficha dice que se eliminaron. |
| Control de la TRD | Permitir cualquier disposición; exigir la de la regla y la retención cumplida | Exigir las dos | Disponer fuera de la TRD o antes de tiempo es lo que la norma prohíbe. | Un caso excepcional (orden judicial) no entra por aquí; se documenta aparte. |
| Desde cuándo se cuenta | Fecha inicial; fecha final del expediente | Fecha final | La retención corre desde el cierre del expediente. | Un expediente con fechas mal descritas vence mal; el calendario muestra las fechas para revisarlas. |
| Transferencias | Solo la custodia anterior; además una actividad | Además una actividad | La custodia dice quién lo tenía; la actividad dice el hecho de la transferencia, con su acta y su fecha. | — |

## Pruebas

- `tests/test_disposicion.py`: el calendario; que se rechace lo que la TRD no manda o lo que no ha cumplido; que nada se disponga dos veces; que la descripción se conserve; la actividad en el grafo conforme; y que solo la administración registre.
- `tests/test_cierre_ing01_ing02.py`: la transferencia como actividad, ejercida por la dependencia y el remitente, con la fecha del acta y el archivo afectado.
