# Piloto Ministerio de Ambiente: lectura del CCD y la TRD en el formato de la entidad

Fecha: 22 de octubre de 2026.

## 1. Qué pasó

Se cargaron los cuadros de clasificación documental (CCD) publicados por el Ministerio
de Ambiente y Desarrollo Sostenible:

| Instrumento | Páginas / filas | Resultado antes | Resultado ahora |
|---|---|---|---|
| CCD V1 2017–2021 (PDF, versión 2, código P-A-DOC-36) | 37 págs., 501 filas | «No se reconoció el formato» | 317 series y subseries, 0 con problemas, jerarquía de 3 niveles con sus códigos (1000 › 1100 › 1101; serie 1101.09; subserie 1101.09.15) |
| CCD V2 2022 (PDF, versión 5, código F-A-DOC-36) | 4.686 filas | 3.432 filas «sin sección» | 393 series y subseries leídas con sus tipos documentales; todas marcadas porque **ninguna dependencia trae código** |

El lector solo entendía dos formas: la plantilla del sistema y el formato de TRD del
AGN (series, subseries y tipos en una misma columna). El CCD del Ministerio tiene otra:
una fila por serie, subserie o tipo documental, la jerarquía de dependencias en varias
columnas (sección, subsección 1, 2, 3, 4) y un «CÓDIGO» suelto que es el de la
dependencia productora.

## 2. Hallazgos sobre los instrumentos

1. **El CCD V2 (2022) no trae el código de ninguna dependencia.** La columna «CÓDIGO
   SECCIÓN / SUBSECCIÓN» está vacía en las 2.676 filas de datos. Sin ese código, el de
   la serie (Derechos de petición = 24) se repite en todas las dependencias y no
   identifica la serie en el cuadro.
2. **El CCD V2 tiene series con códigos contradictorios**: «Proyectos de ley» con 87,
   88 y 89; «Informes» con 27 y 34.
3. **La estructura orgánica tiene hasta cuatro niveles** (Secretaría General ›
   Subdirección Administrativa y Financiera › Grupo de Gestión Documental).
4. El CCD V1 sí trae los códigos de las dependencias, pero corresponde a otra estructura
   orgánica (2017–2021): no se toman sus códigos para el V2.

Pendiente: la TRD V2 2022 (.zip, 12,6 MB), la TRD V1 (.zip, 44,7 MB) y las TVD (22,6 y
40,4 MB) no se pudieron descargar en el entorno de desarrollo (el conector de Drive
entrega hasta 10 MB y la descarga directa no está permitida en la red del entorno).

## 3. Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Formatos que se leen | a) Solo plantilla y formato AGN. b) Reconocer las columnas por su nombre, estén donde estén. | **b** | Cada entidad arma su CCD y su TRD a su manera; exigir la plantilla traslada el trabajo a la persona y abre errores de transcripción. | Un encabezado muy distinto puede no reconocerse: el mensaje dice qué columna falta y la plantilla sigue disponible. |
| Archivos | Excel (.xlsx), PDF con texto, Word (.docx), CSV y .zip con varios de ellos. Los .xls y .doc antiguos se piden guardados en el formato nuevo. | Todos | Las TRD se publican en PDF, se aprueban en Word y se entregan en .zip por dependencia. | Un PDF escaneado no tiene texto: se dice así, no se intenta leer la tabla con OCR (el error en tablas sería alto y silencioso). |
| Jerarquía de dependencias | a) Dos niveles (sección y subsección), aplanando los intermedios. b) Subsecciones anidadas sin límite. | **b** | La estructura orgánica real tiene hasta cuatro niveles; aplanarla falsea la procedencia. RiC-O admite rico:RecordSet dentro de rico:RecordSet. | Más niveles en el cuadro y en la parametrización; cubierto con prueba de extremo a extremo y validación OWL/SHACL. |
| Código de una dependencia dentro de otra | a) Componerlo (100 › 100.110). b) Tomarlo completo cuando ambos son números del mismo largo (100 › 110; 4000 › 4106). | **b** | Así codifican las entidades (Acuerdo 004 de 2019): la serie 2 de la oficina 110 es 110.2, no 100.110.2. Un código corto o con letras sí se compone. | Fondos ya cargados con la regla anterior: al reaplicar, la dependencia se reconoce por su nombre y conserva su código; la serie se compone desde el código que ya tiene. |
| Dependencia sin código en el archivo | a) Inventarlo. b) Tomarlo de otro instrumento por nombre. c) Marcar la fila. | **c** | El código lo fija el instrumento aprobado, no el sistema. La TRD convalidada o el registro en Dependencias lo completan. | La carga del V2 queda detenida hasta tener los códigos: es lo correcto. |
| Serie con varios códigos | a) Escoger uno. b) Marcar la fila. | **b** | No corresponde corregir un instrumento oficial en silencio. | Ninguno. |
| Celdas combinadas y saltos de página | Heredar la dependencia y la serie de la fila anterior cuando vienen vacías; unir el renglón que el PDF partió (empieza en minúscula). | Sí | Es como se ve el instrumento impreso. | Un tipo documental que empiece en minúscula se uniría al anterior; se ve en la vista previa antes de crear. |

## 4. Evidencia

- `app/servicios/cuadro.py`: `_desde_tabla`, `_columnas_libres`, `_tipos_en`,
  `_filas_word`, `_filas_csv`, `_filas_zip`, `compone_dependencia`.
- `app/servicios/parametrizacion_trd.py`: dependencias anidadas, sin ciclos; código
  completo por la cadena.
- `app/servicios/descripcion.py`: una subsección puede ir dentro de otra.
- `tests/test_formatos_trd.py`: CCD jerárquico de 3 niveles, lo que falta marcado, Excel
  con encabezado en dos filas y celdas combinadas, Word, .zip, formatos no legibles, y
  el cuadro aplicado con subsecciones anidadas conforme a RiC-O.
