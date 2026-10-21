# Pertenencia múltiple y colecciones

**Versión:** 1.
**Pedido de la autora:** cerrar la brecha más visible frente a RiC: en RiC-CM un documento puede pertenecer a varios conjuntos a la vez, y los conjuntos se anidan sin niveles fijos.

## 1. Qué hay

- **Un lugar orgánico y otras pertenencias.**
  - Cada descripción tiene **un** lugar orgánico, el del cuadro de clasificación (`incluido_en`). Lo exige el principio de procedencia y el orden original (decisión CM-21 de la auditoría de conformidad).
  - Además puede estar en **otros conjuntos**, como pertenencia adicional (`rico:isOrWasIncludedIn`, relación con rol «adicional»).
  - La exportación RiC-O dice todas las inclusiones.
- **El nivel «Colección»** es un `rico:RecordSet` de tipo **`rst:Collection`**, el individuo oficial de RiC-O.
  - Reúne documentos de distintas series sin sacarlos de su lugar: una colección facticia, una selección temática, documentos para una exposición.
  - Va en el fondo o **dentro de otra colección** (anidamiento libre).
  - No entra al cuadro orgánico: un expediente no puede tener una colección como lugar orgánico, ni una colección puede quedar dentro de una serie.
  - En EAD3 sale con `level="collection"`.
- **Pantalla:** en la ficha de cada descripción (Descripción › Descritas › abrir), la tarjeta **«Pertenece también a»**:
  - muestra los otros conjuntos;
  - si es una colección, muestra lo que reúne;
  - permite **incluir en otro conjunto**: en una ventana se elige una colección o agrupación existente, o se crea una colección nueva en el mismo paso;
  - permite **quitar** una pertenencia: queda anulada, no se borra, y queda en la auditoría.
- **La lista del lugar orgánico no ofrece colecciones.** Las agrupaciones para una pertenencia adicional se piden aparte (`niveles-superiores?adicional=true`).
- **Grafo como fuente de verdad.** Con varios conjuntos, el lugar orgánico no se deduce del grafo RiC-O (no se sabría cuál es): va en el grafo de control. La ida y vuelta sigue exacta.

## 2. Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cuántos conjuntos | Uno solo; varios iguales; **uno orgánico más otros** | **Uno orgánico más otros** (CM-21, se mantiene) | RiC permite varios; el principio de procedencia y el cuadro de clasificación exigen saber cuál es el original | Dos maneras de «estar incluido»: la pantalla las separa (lugar orgánico / pertenece también a) |
| Tipo del conjunto artificial | Un nivel propio sin tipo; **`rst:Collection`** | **`rst:Collection`** | Es el individuo oficial de RiC-O para agregaciones artificiales; no hace falta inventar uno | Ninguno: la exportación sigue conforme |
| Dónde va la colección | Dentro del cuadro; **en el fondo o en otra colección** | **Fondo o colección** | Una colección no es parte de la estructura orgánica; anidarla libremente es lo que permite RiC | Una colección que reúne documentos de varios fondos no cabe: el sistema la limita al mismo fondo |
| Quitar una pertenencia | Borrar; **anular** | **Anular** | Regla de la autora: nada se borra; queda la constancia | Ninguno |

## 3. Pruebas

| Archivo | Qué comprueba |
|---|---|
| `tests/test_colecciones.py` (2) | Crear una colección y una subcolección. No se aceptan ni una colección dentro de una serie ni un expediente con una colección como lugar orgánico. La pertenencia adicional deja intacta la orgánica. La colección muestra lo que reúne. RiC-O (`rst:Collection` y las dos inclusiones). El grafo sigue exacto. Quitar (anulada, con auditoría, sin tocar la orgánica). La lista del lugar orgánico no ofrece colecciones. |
| `tests/test_cierre_cm02.py` | La inclusión adicional y sus límites (mismo fondo, sin ciclos, sin repetir) |
