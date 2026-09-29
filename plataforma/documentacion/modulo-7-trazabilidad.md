# Módulo 7 · Trazabilidad

Este documento sigue la estructura de 23 puntos de la sección 5 del prompt de desarrollo. El alcance lo fijan la historia de usuario 7 y los requisitos RF-M7-01 a RF-M7-03.

## 1. Propósito
Poder demostrar, para cualquier documento:
- quién hizo qué, cuándo y qué cambió;
- cómo estaba la descripción en cualquier momento anterior.

Es la evidencia de la «IA asistida, no automática»: lo que propuso el motor queda separado de lo que decidió cada persona.

## 2. Auditoría (qué se revisó antes de construirlo)
Ya existían la bitácora encadenada por hash (EventoRiC), la auditoría de cambios (módulo 0) y las versiones de cada entidad y relación (VersionRiC). Se encontraron cinco carencias:
- La línea de tiempo mostraba el detalle como texto técnico recortado: no decía qué campo cambió ni sus valores anterior y nuevo.
- «Ver estado» reconstruía solo el tipo y el estado de las relaciones: no incluía los datos del documento ni el nombre que tenía entonces cada entidad.
- Una relación borrada lógicamente después desaparecía también del pasado.
- No había exportación.
- No había acceso desde la ficha del catálogo.
- La elección de la forma documental no quedaba en la bitácora del documento. Esto incumplía RF-M7-01.

## 3. Problema que resuelve
Antes, para reconstruir una decisión había que consultar la base de datos a mano.

## 4. Usuarios
Revisor (rol principal) y archivista. El rol consulta no tiene acceso.

## 5. Casos de uso
- Ver el historial desde la revisión, la barra de pasos o la ficha del catálogo.
- Filtrar la línea de tiempo por propuestas de IA, decisiones humanas o sistema.
- Abrir un punto para ver qué cambió.
- Ver la descripción completa en ese punto.
- Exportar el historial.

## 6. Entidades RiC involucradas
- Record (E04) y sus Instantiation (E06).
- Todas las entidades relacionadas.
- Mechanism (E13), que identifica al motor que propuso cada cosa.

## 7. Relaciones RiC involucradas
Todas las relaciones del documento, incluidas las rechazadas y las retiradas. Del historial no se omite nada.

## 8. Funcionalidades
- **Línea de tiempo unificada.** Cada punto proviene de un evento de la bitácora: carga, extracción, propuesta de IA, validación, corrección, rechazo, publicación o exportación. Los cambios de campo auditados en ese mismo instante, y por la misma persona, se agregan al punto. Un cambio auditado sin evento propio aparece como punto aparte.
- **Cada punto muestra** fecha, hora, responsable y archivo. Al abrirlo se ve una tabla con el campo, el valor anterior y el valor nuevo, y además los datos del evento: confianza, motor, motivo, nota y evidencia verificada.
- **Colores por actor:** IA, persona, sistema y error.
- **Filtros:** todo, IA, decisiones humanas y sistema.
- **«Ver estado en este punto»** muestra la descripción completa en ese instante, en solo lectura:
  - nombre, forma documental, idioma y si estaba publicado;
  - cada relación con su estado de análisis y de revisión;
  - el nombre que la entidad tenía entonces;
  - las relaciones retiradas después.
- **Verificación de la cadena de hash.** Si alguien alterara o borrara un evento, el historial lo muestra.
- **Exportar historial** en CSV (una fila por cambio) o en JSON (incluye el hash de cada evento y el resultado de la verificación). La propia exportación queda registrada.
- **La elección de forma documental** ahora queda en la bitácora con su valor anterior y nuevo.

## 9. Flujos
Ficha del catálogo, revisión o barra de pasos → Historial → abrir un punto → Ver estado en este punto → Volver al estado actual → Exportar historial.

## 10. Pantallas
- `/documentos/<id>/historial/` (reescrita).
- `/documentos/<id>/historial/exportar/?formato=csv|json` (nueva).
- Botón «Ver historial» en la ficha del catálogo.

## 11. UX/UI
- **Dos zonas a pantalla completa**, cada una con su propio desplazamiento: la línea de tiempo y el estado.
- **En ventanas angostas** las dos zonas pasan a ser pestañas, así nada se apila.
- **Valores anterior y nuevo:** el anterior se muestra tachado en rojo y el nuevo en verde.

## 12. Modelo de datos
Sin tablas nuevas. Se usan EventoRiC, RegistroAuditoria y VersionRiC, que ya existían.

## 13. API
`GET /documentos/<id>/historial/exportar/?formato=csv|json` (rol archivista o revisor).

## 14. Uso de IA
No usa IA. El historial muestra qué propuso el motor y con qué confianza, separado de las decisiones humanas.

## 15. Seguridad
- **Acceso por rol:** solo archivista y revisor.
- **Solo lectura:** el historial no se puede editar desde la aplicación.
- **Integridad verificable:** la cadena de hash permite comprobar que no se alteró.

## 16. Auditoría (qué queda registrado)
Cada exportación del historial queda como «consultar» en la auditoría, con el formato usado.

## 17. Interoperabilidad
El JSON incluye, por cada evento, el hash del evento y el hash anterior. Esto sigue el modelo de eventos de PREMIS y queda listo para un paquete de preservación.

## 18. Normativa aplicable
- ISO 15489: metadatos de gestión y trazabilidad de los procesos.
- ISO 23081.
- Acuerdo 003 de 2015: autenticidad e integridad.
- PREMIS: eventos de preservación.

## 19. Arquitectura
| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Fuente del historial | Tabla nueva de historial; unir las fuentes existentes | Unir bitácora, auditoría y versiones | Ya registran todo sin excepción; una tabla nueva duplicaría datos y podría desincronizarse | La agrupación de un evento con sus cambios usa una ventana de 3 segundos y la misma persona; dos acciones simultáneas de la misma persona podrían verse en un solo punto (sin pérdida de datos) |
| Reconstrucción de un instante | Guardar una fotografía completa en cada evento; componer desde las versiones | Componer desde VersionRiC | No duplica almacenamiento; cada entidad ya guarda su estado anterior a cada cambio | Los campos que no son propios (llaves foráneas) no se versionan; la forma documental se reconstruye desde su nombre (`tipo_forma_documental`) |
| Formato de exportación | PDF; CSV; JSON | CSV y JSON | El CSV se abre en una hoja de cálculo y sirve como evidencia; el JSON conserva los hash para verificar | — |

## 20. Código
- `ric/trazabilidad.py`: `linea_de_tiempo`, `descripcion_en` y `exportar`.
- `ric/vistas_analisis.py`: `historial`, `historial_exportar`, y el evento de `analisis_forma`.
- `ric/templates/ric/historial.html` y `ric/templates/ric/catalogo_ficha.html`.
- `config/urls.py`.

## 21. Pruebas
`tests/test_modulo7_trazabilidad.py` tiene 10 pruebas:
- Propuesta y decisiones con fecha y responsable.
- Cada punto muestra el valor anterior y el nuevo.
- Se conserva el historial completo tras un rechazo.
- «Ver estado» reconstruye el nombre original y la revisión pendiente.
- Una relación retirada después sigue en el estado de antes.
- La pantalla está en solo lectura.
- La forma documental queda en la bitácora.
- La exportación en CSV y JSON queda auditada.
- Hay enlace desde el catálogo.
- El rol consulta no tiene acceso.

`tests/test_m7_historial.py` se ajustó al nuevo diseño. Además se hizo una verificación en Chromium.

## 22. Criterios de aceptación (historia de usuario 7)
- **RF-M7-01:** toda propuesta y decisión queda registrada con fecha y responsable, sin excepción. Cumplido, incluida la forma documental, que antes faltaba.
- **RF-M7-02:** se conserva el registro completo, no solo la última decisión. Cumplido.
- **RF-M7-03:** «Ver estado en este punto» reconstruye la descripción tal como estaba en ese momento exacto. Cumplido, con los datos del documento y los nombres de las entidades de ese momento.

## 23. Evidencia concreta de aplicación de RiC
En el acta del Cabildo de 1810 el historial muestra estos pasos:
1. La propuesta del Mechanism (E13) «motor … demo 1»: R027 con confianza 0,4 y la evidencia verificada.
2. La aceptación humana.
3. La corrección en revisión: «Cabildo de Santafé» → «Cabildo de Santa Fe».

«Ver estado» en el primer punto muestra el documento todavía sin relaciones. En el punto previo a la corrección, la entidad aparece con su nombre original.

## Qué no hace (y qué pasa en cada error)
- **Eventos sin archivo asociado:** los que no tienen una Instantiation (una relación entre dos personas, sin documento) no entran en la cadena del documento. Es una limitación conocida, documentada en EventoRiC.
- **Parámetros inválidos:** una fecha inválida en `momento` se ignora y se muestra el estado actual.
