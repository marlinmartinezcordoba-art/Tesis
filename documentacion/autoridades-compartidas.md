# Autoridades compartidas entre fondos

RiC-CM pide que cualquier entidad (una persona, una institución) sea un punto de acceso de primer nivel y que los
documentos de fondos distintos se puedan conectar a través de ella. Hasta ahora el vocabulario de RICORA era
**por fondo**: la misma persona en dos fondos eran dos fichas sin vínculo interno. Ahora las autoridades son de
la institución.

## Qué cambia

- **Son compartidas** las personas, familias, entidades, grupos y cargos.
- **Siguen siendo de cada fondo**:
  - los mecanismos (cada programa con su versión);
  - los lugares, las formas documentales, las actividades, los tipos de actividad, los mandatos y las materias.
- **Al describir en cualquier fondo**, el sistema encuentra la autoridad aunque se haya registrado en otro y dice
  dónde: «autoridad registrada en "Correspondencia municipal"». Reutilizarla no crea una ficha nueva.
- **Las fichas duplicadas** que ya existen en fondos distintos se sugieren en «Sugerencias de fusión» de los dos
  fondos. Al fusionarlas:
  - las descripciones pasan a citar la ficha definitiva;
  - la URI de la absorbida redirige para siempre a la definitiva.
- **El vocabulario de un fondo** muestra lo registrado en él y las autoridades de otros fondos que cita, con su
  fondo de registro. La casilla «Autoridades de toda la institución» muestra todas.
- **La importación de EAC-CPF** completa la autoridad que ya exista en cualquier fondo, y la vista previa dice en
  cuál está.
- **Las personas usuarias del sistema** (registradas como agentes cuando actúan) son una sola en la institución
  desde ahora. Los registros duplicados que ya existían no se unen solos.

## Cómo funciona por dentro

Cada autoridad conserva su **fondo de registro**, el fondo donde se creó:
- su fila vive en el grafo de control de ese fondo;
- los demás fondos la **citan** por su URI.

Así cada fila sigue perteneciendo a un solo grafo de control. La ida y vuelta tablas → grafo → tablas y la
reconstrucción desde el grafo no cambian; las pruebas comprueban que los grafos de los dos fondos siguen
coincidiendo con las tablas.

- **Grafo de cada fondo:** incluye las autoridades que cita, aunque se hayan registrado en otro.
- **Si cambia la ficha de una autoridad:** se rehacen el grafo de su fondo de registro y el de cada fondo que la cita.
- **La consulta de un fondo:** prepara también la proyección de los fondos de registro de las autoridades que cita.
- **La URI `/id/…` de una autoridad:** se busca en su fondo de registro y después en los que la citan. Lo mismo hace
  la ficha EAC-CPF pública.

## Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Dónde vive la autoridad | Sin fondo (registro aparte) / con un fondo de registro y citada desde otros | Fondo de registro | El grafo RiC-O, su control y la reconstrucción trabajan por fondo. Con un fondo de registro, cada fila sigue en un solo grafo de control y nada de eso cambia | La ficha se edita desde cualquier fondo, pero se guarda en el grafo del de registro |
| Qué se comparte | Todo el vocabulario / solo las autoridades | Solo las autoridades (personas, familias, entidades, grupos, cargos) | Son las que ISAAR(CPF) trata como registro único. Los tipos documentales y las actividades salen de la TRD de cada fondo. Los lugares podrían compartirse, pero se dejó para una fase siguiente | «Bogotá» sigue existiendo una vez por fondo |
| Mecanismos | Compartidos / de cada fondo | De cada fondo | Cada programa queda con su versión exacta en el fondo donde actuó, que es lo que la preservación necesita | — |
| Duplicados que ya existen | Unirlos solos por nombre / sugerirlos | Sugerirlos | «Secretaría General» de dos instituciones son dos entidades distintas con el mismo nombre: unirlas es una decisión archivística | Hay que revisar las sugerencias |
| Reutilización al describir | Automática / la persona elige | La persona elige, viendo el fondo de registro | Igual que dentro de un fondo: nada se vincula sin confirmación | — |
| Reserva (Ley 1712) | Por fondo de registro / por cada fondo que la cita | Por cada fondo | Una autoridad que un fondo solo conoce por documentos reservados no se nombra en el grafo público de ese fondo, aunque en otro sea pública | — |
| Relaciones entre fondos | Abrirlas ya / después | Solo a través de autoridades | Un documento de un fondo puede citar a una autoridad de otro. Las relaciones directas entre documentos de fondos distintos (pertenencia, secuencia, respuesta) son la siguiente fase | — |

## Lo que falta

1. **Relaciones directas entre documentos de fondos distintos y con recursos de otras instituciones (URI externas).**
   Se apoya en esto.
2. **Lugares compartidos.**
3. **Consulta pública por entidad**: una página legible para personas y la URI `/id/…` en HTML.
