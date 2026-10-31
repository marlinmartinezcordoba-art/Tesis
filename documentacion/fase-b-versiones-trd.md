# Fase B: versiones de la TRD (requisitos 3 y 7)

## Qué hace

1. **El archivo original se conserva.**
   - Al leer la TRD, el archivo se guarda tal como llegó, por su huella SHA-256. Si se sube dos veces el mismo, queda
     una sola copia.
   - Al guardar las filas, la versión cita ese archivo: nombre, huella, tamaño y filas cargadas.
   - En el paso 1 de «TRD y CCD» se ve y se descarga.
2. **Cada fila dice de dónde salió.** En la matriz, al pasar el cursor sobre la serie: «Salió de "trd-2024.pdf", fila
   12» (o la parte del .zip). Una fila escrita a mano lo dice también.
3. **Comparar dos versiones.**
   - En el paso 2, la versión en preparación se compara con la que rige.
   - En «Cuadro y versiones», se comparan dos versiones cualesquiera.
   - Por cada serie (por su código compuesto: 110.2, 110.2.1) dice si es nueva, si se retira o qué cambió: tipos
     documentales que se agregan o se quitan, años en archivo de gestión y central, disposición final, soporte,
     procedimiento, función y dependencia.
4. **Registros afectados.** Los expedientes y documentos descritos en las series que cambian o se retiran, separados
   por qué TRD los rige:
   - **conservan la anterior** los cerrados antes de la fecha desde la que rige la nueva;
   - **pasan a la nueva** los abiertos o los cerrados después.

   Es la misma regla con que el sistema calcula la retención de cada expediente (Acuerdo AGN 004 de 2019).
5. **Con qué TRD se clasificó cada descripción.** Al publicarse, queda anotada la versión que rige. Cambia solo si la
   descripción se mueve a otro lugar del cuadro. Se ve en la ficha: «Clasificado con: TRD versión 1 · Resolución 045».

## Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo se guarda el original | Con la versión / por su huella | Por su huella | El mismo archivo no se duplica, y la huella prueba que es el mismo que se leyó | Se guarda también lo que se leyó y no se llegó a cargar (ocupa disco, pero es poco) |
| Qué cita la versión | Lo que diga la pantalla / lo comprobado | Solo si el archivo existe y su huella coincide | Nadie puede citar un archivo que no se leyó | — |
| Cómo se emparejan las series | Por nombre / por código compuesto | Por código compuesto | El código es estable entre versiones; el nombre se corrige con frecuencia | Si una serie cambia de código, sale como retirada y nueva; la comparación lo muestra así |
| Qué registros se afectan | Todos los de la serie / según su fecha final | Según su fecha final | Cada expediente se valora con la TRD vigente cuando se cerró; la nueva no cambia lo cerrado antes | Un expediente sin fechas cuenta como abierto y pasa a la nueva |
| Con qué versión se clasificó | Calcularla cada vez / anotarla al publicar | Anotarla | Es un hecho del momento de clasificar; calcularla después podría dar otra si cambian las fechas | Las descripciones publicadas antes de esto no la tienen; la ficha lo dice |

## Lo que falta de los requisitos 3 y 4

- Cargar varios instrumentos en un solo paquete (CCD, TRD y TVD juntos, cada uno en su lugar).
- Cotejar el CCD contra la TRD y alertar cuando no coinciden (fase C).
