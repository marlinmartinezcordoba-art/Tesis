# Tabla de valoración documental (TVD)

Fecha: 22 de octubre de 2026. Norma: Acuerdo 004 de 2019 del AGN (elaboración, aprobación, convalidación e
implementación de TRD y TVD).

## 1. Qué es en RICORA

La TVD valora el **fondo acumulado**: los documentos producidos antes de que la entidad tuviera TRD. Se elabora
por **periodos institucionales**: cada cambio de estructura orgánica abre un periodo (por ejemplo, el Ministerio de
Ambiente tiene la TVD del MAVDT, periodo 2006–2011, y la del MADS, periodo único 2011–2017).

En RICORA la TVD sigue el mismo recorrido de la TRD (*Instrumentos archivísticos › TVD*):

1. **Abrir la TVD de un periodo**: nombre del periodo, fechas (empieza y termina), acto de aprobación,
   convalidación y ente que vigila.
2. **Cargarla desde el archivo** (Excel, PDF con texto, Word, CSV o .zip) o llenar la matriz a mano.
   Las dependencias y el banco de series son los del fondo (*Ajustar*).
3. **Matriz**: por dependencia del periodo, cada serie o subserie con sus tipos documentales, la retención en archivo
   central, la disposición final y el procedimiento. La TVD no lleva retención en archivo de gestión.
4. **Validar en RiC-O y aplicar**: se arma el cuadro del periodo y queda vigente.

## 2. Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Dónde vive la TVD | a) Un módulo aparte con tablas propias. b) La misma parametrización de la TRD con un campo «instrumento». | **b** | Mismo recorrido (versión, dependencias, banco, matriz, aplicar en RiC-O) y mismas validaciones; dos módulos se desalinearían. | Cada consulta de versiones debe filtrar por instrumento: cubierto en el servicio, el avance de Inicio y la exportación. |
| A qué documentos se aplica una regla de la TVD | a) Desde la aprobación hacia adelante, como la TRD. b) A los documentos producidos en el periodo institucional. | **b** | La TVD valora lo producido en el periodo, no lo que se produce después. El motor de retención ya elige la regla por la fecha final del expediente: un expediente de 2008 se valora con la TVD 2006–2011 y uno de 2020 con la TRD. | Un expediente sin fechas toma la regla abierta (la TRD) o, si no hay, la primera: hay que completar las fechas extremas. |
| Varias TVD | Varias vigentes, una por periodo, sin traslaparse. | Sí | Cada documento se valora con una sola TVD. Si dos periodos se cruzan, aplicar se detiene y dice con cuál. | Ninguno. |
| TVD corregida del mismo periodo | a) Editar la vigente. b) Versión nueva del mismo periodo que la reemplaza. | **b** | Nada se borra: la anterior pasa a histórica y la regla que cambia se anula con la nota de quién la reemplaza; la que no cambia sigue. | Ninguno. |
| Retención en archivo de gestión | Pedirla o no. | No | La TVD fija la permanencia en archivo central y la disposición final: los documentos ya no están en gestión. | Si un instrumento la trae, se guarda igual (no se descarta). |
| RiC-O | Una rico:Rule por TVD, de tipo «Tabla de valoración documental», con su periodo (rico:isAssociatedWithDate), el acto como rico:Mandate («Acto de aprobación de la TVD») y por partes las reglas de su periodo. | Sí | Igual que la TRD (rico:Rule que regula el fondo), con el periodo que valora en lugar de la vigencia. | Validado con OWL y SHACL en las pruebas. |

## 3. Evidencia

- `alembic/versions/0047_tvd.py`: instrumento, periodo y fechas en la versión; numeración por instrumento.
- `app/servicios/parametrizacion_trd.py`: requisitos de la TVD, `_tvd_anterior` (reemplazo y traslape).
- `app/servicios/cuadro.py`: `_regla_tvd` (la regla rige el periodo; no cierra la de la TRD).
- `app/servicios/exportacion_rico.py`: la TVD como rico:Rule de su tipo, con su periodo.
- `frontend/src/pages/Fondos.tsx` (pantalla TVD) y `components/ParametrizacionTrd.tsx` (versiones y matriz por
  instrumento).
- `tests/test_tvd.py`: periodo valorado y TRD después; traslape; reemplazo de la TVD del mismo periodo; requisitos;
  borradores de TRD y TVD a la vez; exportación conforme.
