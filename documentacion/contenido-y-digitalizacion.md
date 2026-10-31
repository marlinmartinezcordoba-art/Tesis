# Requisitos 2 y 5: tipo de contenido y estado de digitalización

Se construyeron con las dos objeciones que la autora aceptó.

## Requisito 2: tipo de contenido

**Pedido:** un valor «Texto e imagen».
**Construido:** el tipo de contenido admite **varios valores a la vez**. Un oficio con fotografías se describe
con «Texto» e «Imagen fija». En RiC-O, `rico:hasContentOfType` admite varios valores; cada uno sale como un concepto.

- **Catálogo:** los siete tipos de RiC-CM (texto, imagen fija, imagen cartográfica, imagen en movimiento, sonido,
  notación musical, datos), más los que agregue la administración desde el mismo campo («Agregar un tipo»), sin
  tocar el código.
- **Un tipo en uso no se retira**, para que ningún documento quede con un valor sin nombre.
- **Los documentos ya descritos** conservan su único tipo como el primero de la lista.

## Requisito 5: estado de digitalización

**Pedido:** un estado «Digitalizado».
**Construido:** un **estado de digitalización aparte** del estado del documento. El estado del documento (RiC-A39:
borrador, definitivo, copia…) habla del documento intelectual; la digitalización habla de sus instanciaciones.

| Estado | Cuándo |
|---|---|
| Sin original ni archivo | No tiene ninguna instanciación |
| Nacido digital | Tiene archivo y no tiene original físico |
| Sin digitalizar | Tiene original físico y ninguna copia digital derivada |
| Digitalizado, sin verificar | Tiene copia derivada del original y nadie la ha verificado |
| Digitalización verificada | La última verificación de cada copia pasó las cuatro comprobaciones |
| Digitalización con problemas | La última verificación de alguna copia encontró problemas |

- **Datos de la digitalización:** quién digitalizó (puede ser un operador externo), cuándo, con qué equipo y a qué
  resolución. Se corrigen con su valor anterior en la auditoría.
- **Verificación:** una persona marca cuatro comprobaciones:
  - completa (todas las páginas o folios);
  - legible;
  - fiel (orientación, color y escala);
  - íntegra (abre y su huella coincide).

  Si falta alguna, debe decir qué problema encontró. Cada verificación queda con su nombre y su fecha, ninguna se
  borra, y vale la última. Como ayuda, la pantalla muestra lo que la revisión automática de completitud encontró en
  el texto de la copia.
- **En RiC-O:**
  - la digitalización sigue siendo la actividad que afecta al original y resulta en la copia (RiC-AG), ahora con
    la fecha real y con quién, equipo y resolución;
  - cada verificación es otra actividad que afecta a la copia, con su fecha y su resultado.

## Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| «Texto e imagen» | Un valor nuevo / varios valores | Varios valores | RiC-O admite varios; un valor combinado duplica conceptos y no escala (texto y plano, imagen y sonido…) | — |
| Tipos nuevos | En el código / los agrega la administración | Los agrega la administración | El requisito pide ampliarlo sin programar | Tipos mal nombrados: se agregan de uno en uno y solo la administración puede hacerlo |
| «Digitalizado» | Un valor más del estado del documento / un estado aparte | Estado aparte | Un documento puede ser «definitivo» y «digitalizado» a la vez; mezclarlos obligaría a elegir uno | — |
| Cómo se sabe que está digitalizado | Que alguien lo marque / calcularlo | Calcularlo de la relación original → copia | No puede decir «digitalizado» si no hay copia derivada registrada | Si no se registra el original físico, el archivo figura como nacido digital |
| Verificación | Una casilla / comprobaciones con historial | Cuatro comprobaciones con nombre, fecha e historial | «Digitalizado» no es «verificado», y una verificación debe poder auditarse | — |
| Quién digitalizó | Un usuario del sistema / un texto | Un texto | Muchas veces lo hace un operador externo o una empresa contratada | No queda como agente enlazado en el grafo, sino en la descripción de la actividad |
