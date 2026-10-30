# Ficha ISDIAH de la institución que custodia los fondos

RICORA integraba en un solo modelo ISAD(G), ISAAR(CPF) e ISDF; faltaba ISDIAH, la norma para describir las
instituciones que custodian archivos. Ahora una entidad corporativa del vocabulario puede llevar, además de su
ficha ISAAR, los datos que solo ISDIAH pide, y declarar qué fondos custodia.

## Qué se registra

| Área ISDIAH | Dónde queda en RICORA |
|---|---|
| 5.1 Identificación (forma autorizada, otras formas, tipo de institución) | En la ficha ISAAR que ya existía: nombre, otras formas del nombre, tipo de entidad |
| 5.2 Contacto (dirección, teléfono, correo, sitio web, persona de contacto) | **Nuevo:** área «Institución que custodia archivos (ISDIAH)» |
| 5.3 Descripción (historia, estructura, mandatos) | En la ficha ISAAR, en la línea de tiempo y en los mandatos |
| 5.3.2 Contexto geográfico; 5.3.5 Políticas de ingreso; 5.3.6 Edificios; 5.3.8 Instrumentos publicados | **Nuevo** |
| 5.3.7 Fondos que custodia | **Nuevo:** vínculo «Custodia o custodió el fondo», con su vigencia. Sale en RiC-O como `rico:hasOrHadHolder` (RiC-R039i) con su `rico:RecordResourceHoldingRelation` |
| 5.4 Acceso (horarios, condiciones, accesibilidad) | **Nuevo** |
| 5.5 Servicios (investigación, reproducción, espacios públicos) | **Nuevo** |
| 5.6 Control | En el área de control de la ficha ISAAR |

## Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Dónde vive la ficha de la institución | Una tabla aparte / la misma autoridad (entidad corporativa) con un área ISDIAH | La misma autoridad | En RiC la institución custodia es un `rico:CorporateBody` como cualquier otro: un solo registro con su ficha ISAAR, su historia y sus vínculos. Una tabla aparte duplicaría la identidad | — |
| Qué datos nuevos se guardan | Toda la norma / solo lo que ISAAR no tiene | Solo lo que ISAAR no tiene | La identidad, la historia, la estructura y el control ya están en la ficha ISAAR | — |
| Cómo salen en RiC-O | Inventar propiedades / no exportarlos | No exportar el contacto, el acceso ni los servicios; sí la custodia | RiC-O 1.1 no tiene propiedades para dirección, horarios o servicios. Inventarlas haría el grafo no conforme. Quedan en la ficha y en el grafo de control (declarado en `ric_o.SIN_PROPIEDAD`) | Otro sistema que lea el RiC-O no verá el contacto; lo verá en la consulta pública cuando exista el portal |
| Reserva de la institución custodia | Oculta si solo la cita el fondo / pública si el fondo lo es | Pública si el fondo lo es | La regla de reserva no contaba el fondo como documento visible, y escondía a quien solo estaba unido al fondo: su institución custodia y su productor. Ahora el fondo cuenta, salvo que el fondo mismo sea reservado | — |
| Validación | Texto libre / formato de correo y sitio web | Correo con formato válido y sitio web con http(s) | Evita datos de contacto inservibles | — |

## Lo que falta

- Mostrar la ficha de la institución en el portal público por entidad (fase siguiente).
- Exportar en EAG (Encoded Archival Guide), el formato XML de ISDIAH que usa el Portal Europeo de Archivos, si
  algún día se necesita intercambiar la guía con otro sistema.
