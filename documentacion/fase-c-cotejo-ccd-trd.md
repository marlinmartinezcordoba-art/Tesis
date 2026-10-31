# Fase C: cotejo del CCD con la TRD y paquete con varios instrumentos (requisitos 3 y 4)

## Cotejo del CCD con la TRD

Cuando la entidad entrega el cuadro de clasificación (CCD) y la tabla de retención (TRD) por separado, como en el
piloto de MinAmbiente, no siempre coinciden. En el paso 2 de «TRD y CCD», «Subir el CCD» los compara por código
compuesto (110, 110.2, 110.2.1) y dice:

| Hallazgo | Por qué importa |
|---|---|
| Series y subseries del CCD **sin retención** en la TRD | Lo más grave: esos documentos no tendrían tiempo de conservación ni disposición final |
| Series y subseries de la TRD que **no están en el CCD** | La TRD retiene algo que el cuadro no clasifica |
| El mismo código con **otro nombre** | Uno de los dos está desactualizado o mal transcrito (no cuentan mayúsculas ni tildes) |
| La misma serie en **otra dependencia** | La serie cambió de productor en uno de los dos |
| Dependencias que están en uno y no en el otro, o con otro nombre | La estructura orgánica no es la misma |

- El archivo del CCD se guarda con su huella, marcado como CCD, junto con el resultado. «Volver a cotejar» repite el
  cotejo con la TRD tal como quedó después de corregirla.
- Si algo no coincide, queda una alerta en el panel: alta si hay series sin retención, media si no. Un cotejo
  posterior sin diferencias la atiende sola.
- El cotejo no corrige nada: decide la persona (corregir la TRD en el paso 3 o pedir el CCD correcto).

## Paquete con varios instrumentos

Un .zip con varios archivos (la TRD, el CCD, una TVD) se lee de una vez.

- El sistema sugiere qué es cada archivo: por su nombre («TVD…», «CCD…», «Cuadro…») y, si el nombre no lo dice, por si
  trae retención (sin retención, es un CCD). La persona lo confirma o lo cambia.
- Cada archivo va a su lugar:
  - la TRD llena la versión en preparación;
  - la TVD abre su propio borrador, cuyo periodo se completa en la pantalla de la TVD;
  - el CCD se coteja con la TRD.
- El .zip queda guardado una sola vez, por su huella. Cada fila dice de qué archivo del paquete y de qué fila salió.

## Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo se emparejan | Por nombre / por código compuesto | Por código | Es lo que el Acuerdo 004 de 2019 fija como identificador de la serie en los dos instrumentos | Un CCD con otra codificación sale todo como diferente; se ve de inmediato |
| Qué dependencias se comparan | Toda la estructura / la productora de cada serie | La productora | La TRD se organiza por la dependencia que produce; las secciones superiores sin series no se comparan | Una sección intermedia renombrada no se detecta |
| Corregir | Automático / decide la persona | Decide la persona | No se sabe cuál de los dos documentos está bien | — |
| Alerta | Siempre / solo con diferencias | Solo con diferencias, y se atiende sola si un cotejo posterior coincide | El panel muestra lo pendiente, no la historia | — |
| Qué es cada archivo del paquete | Lo decide el sistema / lo sugiere y la persona confirma | Sugiere y confirma | El nombre del archivo no siempre lo dice | — |
| TVD en el paquete | Varias / una | Una | Cada TVD es un periodo y va en su propio borrador; varias se mezclarían | Las demás TVD se cargan una por una desde «TVD» |
