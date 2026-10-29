# Importación de EAD y EAC-CPF

RiC-AG recomienda migrar desde las normas anteriores y enriquecer después. Muchos archivos del país ya tienen
inventarios en EAD y fichas de autoridad en EAC-CPF exportados de AtoM, ArchivesSpace u otros sistemas. RICORA
los recibe sin un segundo camino de creación: lo que entra pasa por la misma vista previa, validación y regla de
«todo o nada» que la importación de RiC-O.

## Qué hace

| Archivo | Dónde se carga | Qué pasa |
|---|---|---|
| EAD3 (2015) o EAD 2002 (`.xml`, `.ead`) | Ingesta › Cargar instrumentos › «Un fondo de otro sistema (RiC-O o EAD)» | Se convierte a un grafo RiC-O 1.1 y sigue la importación de RiC-O: vista previa, cuadro por la parametrización de la TRD, vocabulario, expedientes, documentos, relaciones; validado contra la ontología y el perfil SHACL. |
| EAC-CPF 2010 o 2.0 (`.xml`, o `.zip` con varios) | Autoridades y términos › «Importar autoridades en EAC-CPF» (solo administración) | Crea la ficha ISAAR(CPF) del agente o completa la que ya existe en el fondo, sin cambiar lo que ya tiene. |

En ambos casos nada se crea hasta que la persona confirma, y si un archivo tiene un error no entra ninguno.

## Correspondencia EAD → RiC-O

| EAD | RiC-O 1.1 |
|---|---|
| `<archdesc>`, `<c>`, `<c01>`…`<c12>` | `rico:RecordSet` con `rico:hasRecordSetType` (fonds, subfonds, series, subseries, file; `otherlevel` «sección», «subsección»…); `level="item"` → `rico:Record` |
| anidación | `rico:includesOrIncluded` |
| `<unittitle>` / `<unitid>` | `rico:title` / `rico:identifier` |
| `<unitdate>`, `<unitdatestructured>` | `rico:Date` con `rico:expressedDate` y `rico:normalizedDateValue` (EDTF), por `rico:hasOrHadAllMembersWithCreationDate` (conjuntos) o `rico:hasCreationDate` (documentos) |
| `<scopecontent>`, `<accessrestrict>`, `<userestrict>`, `<custodhist>`, `<arrangement>`, `<accruals>` | `rico:scopeAndContent`, `rico:conditionsOfAccess`, `rico:conditionsOfUse`, `rico:history`, `rico:structure`, `rico:accruals` |
| `<origination>` (persname, corpname, famname) | `rico:Person`, `rico:CorporateBody`, `rico:Family` como `rico:hasCreator` |
| `<controlaccess>`: agentes, `<subject>`, `<geogname>` | agente, concepto, `rico:Place`, como `rico:hasOrHadSubject` |
| `<genreform>` / `<function>` | `rico:DocumentaryFormType` / `rico:ActivityType` (al vocabulario) |
| `<dao>`, `<physdesc>`, `<bioghist>` | No se convierten; se cuentan con su motivo |

## Correspondencia EAC-CPF → ISAAR(CPF)

| EAC-CPF | Ficha de autoridad |
|---|---|
| `entityType` | Tipo: persona, entidad, familia |
| `nameEntry` autorizada / otras | Forma autorizada / otras formas del nombre |
| `entityId` con `localType` | Identificador con su esquema |
| `existDates` | Fechas de existencia (EDTF) |
| `biogHist`, `structureOrGenealogy`, `generalContext`, `occupation` | Historia, estructura o genealogía, contexto general, ocupación |
| área de control (`agencyName`, `sources`, `conventionDeclaration`, `languageDeclaration`, `maintenanceStatus`, `recordId`) | Institución, fuentes, reglas, idioma, estado de elaboración, notas de mantenimiento |
| `places`, `functions`, `mandates`, `legalStatus`, `cpfRelation`, `resourceRelation` | No se importan por aquí; se cuentan |

## Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo entra el EAD | Un importador propio de EAD a las tablas / convertir a RiC-O y reutilizar la importación de RiC-O | Convertir a RiC-O | Un solo camino de creación, ya probado y validado con SHACL; el grafo es la fuente de verdad | Lo que EAD expresa y no tiene correspondencia directa se pierde; por eso se cuenta en «omitidas» |
| Versiones de EAD | Solo EAD3 / EAD3 y EAD 2002 | Ambas | AtoM y muchos sistemas todavía exportan EAD 2002 | Variantes locales de `otherlevel` no reconocidas quedan sin tipo de conjunto: se ven en la vista previa |
| Objetos digitales `<dao>` | Descargarlos de la URL / no traerlos | No traerlos | Descargar de terceros abre la puerta a archivos sin control de integridad ni antivirus; los archivos entran por Carga de documentos con su verificación | La persona debe cargar los archivos aparte |
| `<bioghist>` del EAD | Pegarlo como historia del agente / remitir al EAC-CPF | Remitir al EAC-CPF | En EAD la historia no siempre dice de qué agente es; en EAC-CPF sí | Si el sistema origen no exporta EAC-CPF, la historia se escribe a mano |
| EAC-CPF sobre una ficha existente | Sobrescribir / completar sin pisar | Completar sin pisar | Nada se borra ni se reemplaza sin decisión humana; lo que choca queda como aviso | Un valor desactualizado en RICORA no se corrige solo: hay que revisarlo con el aviso |
| Relaciones del EAC-CPF (`cpfRelation`, `resourceRelation`) | Crearlas / contarlas | Contarlas | Los otros extremos de la relación pueden no existir en el fondo; crear agentes «huérfanos» ensucia el vocabulario | Las relaciones se registran a mano desde la ficha |
| Seguridad del XML | Parser por defecto / sin entidades ni red ni DTD | Sin entidades, sin red, sin DTD | Evita ataques de entidades externas (XXE) y descargas no pedidas | Un XML que dependa de una DTD externa para entidades con nombre puede leerse incompleto |
| Quién importa autoridades | Cualquier persona con permiso de vocabulario / solo administración | Solo administración | Crea muchas fichas de una vez; queda en la trazabilidad como «Importó autoridades en EAC-CPF» | La carga depende de una persona |

## Recomendación

Importe primero el fondo (EAD): crea el fondo y registra a los productores y agentes con su nombre. Después
importe las autoridades (EAC-CPF) en ese fondo: cada ficha cuya forma autorizada coincida con un agente ya
registrado lo completa en lugar de crear otro. Si un nombre se escribe distinto en los dos sistemas, quedarán
dos fichas: revíselas en «Sugerencias de fusión».

No cargue documentos con reserva legal mientras el servidor no tenga HTTPS.
