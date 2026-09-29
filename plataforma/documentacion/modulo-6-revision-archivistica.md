# Módulo 6 · Revisión archivística

Sigue la estructura de 23 puntos de la sección 5 del prompt de desarrollo. El alcance lo fijan la historia de usuario 6, los requisitos RF-M6-01 a RF-M6-04 y los criterios de calidad CC-03, CC-04 y CC-08 de la especificación funcional.

## 1. Propósito
Que ninguna descripción llegue al catálogo sin una segunda mirada humana ficha por ficha. Lo que la IA propuso y el archivista aceptó en el análisis se vuelve a confirmar, se corrige o se rechaza con su motivo.

## 2. Auditoría (qué se revisó antes de construirlo)
La pantalla existente mostraba las fichas solo en lectura, con un único «Rechazar» por ficha. El revisor no tenía cómo confirmar ni corregir una ficha: no había campo editable ni «Aceptar», así que no se cumplían RF-M6-01 ni RF-M6-02. El bloqueo de publicación solo contaba lo pendiente del motor de análisis (M3), no lo pendiente de la revisión (RF-M6-04 incompleto). La baja confianza se marcaba, pero no se ordenaba primero (CC-04). El motivo obligatorio (RF-M6-03) y CC-03 ya se verificaban en el servidor.

## 3. Problema que resuelve
Antes, un documento podía publicarse sin que nadie hubiera confirmado cada entidad después del análisis, y la revisión era un visto bueno general.

## 4. Usuarios
- **Revisor:** rol principal según la historia 6.
- **Archivista:** también puede revisar.
- **Consulta:** no tiene acceso.

## 5. Casos de uso
- Revisar las fichas de un documento.
- Aceptar una ficha tal cual.
- Corregir el nombre y aceptar.
- Rechazar con motivo, lo que devuelve la ficha al análisis.
- Aprobar y publicar cuando no queda nada pendiente.
- Ver en la bandeja cuántas fichas faltan por revisar en cada documento.

## 6. Entidades RiC involucradas
Record (E04) y las entidades relacionadas: Person, CorporateBody, Family, Position (E08–E12), Mechanism (E13, el motor que propuso), Activity, Mandate, Rule, Date y Place.

## 7. Relaciones RiC involucradas
Todas las relaciones de RiC-CM 1.0 que el documento tenga aceptadas (R001–R086, validadas contra la matriz). CC-03 exige al menos una de procedencia (por ejemplo R027 has creator) para publicar. Las relaciones de clasificación (R024 expediente → documento y las de los instrumentos) no requieren revisión.

## 8. Funcionalidades
- **Estado de revisión por relación:**

  | Estado | Cuándo |
  |---|---|
  | Pendiente | Toda relación aceptada en el análisis |
  | Confirmada | El revisor la acepta tal cual |
  | Corregida | El revisor corrige el nombre y la acepta |
  | No aplica | Relaciones de clasificación archivística |

  Cada decisión guarda quién, cuándo y una nota.
- **Ficha a dos columnas:**
  - A la izquierda, lo propuesto: proveedor, modelo, confianza y cita textual con su página.
  - A la derecha, el campo editable del nombre, una nota opcional y los botones **Aceptar** y **Rechazar** de esa ficha.
- **Corrección protegida:** si la entidad también describe otros documentos, su nombre no se cambia desde aquí (quedaría cambiado en todos sin querer). La pantalla lo dice y remite a Vocabularios (M5) o al rechazo.
- **Rechazo en la misma ficha:** el campo de motivo es obligatorio y «Confirmar rechazo» se habilita solo con contenido; el servidor lo verifica igual. La ficha vuelve al análisis con su motivo y lo demás ya aceptado se conserva.
- **Orden:** primero las pendientes y, entre ellas, las de baja confianza (CC-04).
- **Avance:** una barra muestra «n de m fichas revisadas». «Aprobar y publicar» queda deshabilitado mientras haya pendientes, tanto en pantalla como en el servidor.
- **Cambios posteriores:** si el tipo de una relación se cambia después en el modelado (M4), la relación vuelve a «pendiente de revisión».
- **Bandeja:** muestra «n ficha(s) por revisar» por documento.

## 9. Flujos
- **Principal:** Relaciones (M4) → Revisión → Aceptar o corregir cada ficha → Aprobar y publicar → Catálogo (M8).
- **Alterno:** Rechazar → motivo → Confirmar rechazo → vuelta al análisis (M3) con la ficha marcada → nueva propuesta solo para lo que falta.

## 10. Pantallas
- `/revision/` (bandeja).
- `/revision/<id>/` (reescrita).

## 11. UX/UI
- **Decisión junto a su evidencia:** cada ficha tiene su decisión al lado de su evidencia; nunca hay un botón de aprobación general.
- **Borde de color:** naranja para las pendientes, rojo para las de baja confianza.
- **Barra de publicación fija abajo:** dice exactamente qué bloquea la publicación: elementos sin decidir en el análisis, fichas sin revisar o falta de procedencia (CC-03).
- **Campo apagado con aviso:** el campo de una entidad compartida aparece de solo lectura y explica por qué.

## 12. Modelo de datos
- En `RelacionRiC` se agregan los campos `revision`, `revisado_por`, `fecha_revision` y `nota_revision`.
- La migración 0022 llena los datos existentes:
  - Las relaciones de instrumentos y clasificación quedan en «no aplica».
  - Las de documentos ya publicados quedan confirmadas a nombre de quien las publicó, para no devolver al trabajo lo que ya estaba en el catálogo.

## 13. API
- `POST /revision/<id>/relacion/<rel>/confirmar/` recibe `nombre` y `nota`.
- `POST /revision/<id>/relacion/<rel>/rechazar/` recibe `motivo`, que es obligatorio.
- `POST /revision/<id>/aprobar/`.
- Las tres exigen el rol archivista o revisor.

## 14. Uso de IA
Ninguno en este módulo. Aquí se decide sobre lo que la IA propuso; la pantalla muestra qué motor lo propuso (Mechanism E13), con qué confianza y con qué cita.

## 15. Seguridad
- Rol verificado en cada acción.
- RF-M6-03, RF-M6-04 y CC-03 verificados en el servidor, no solo en la pantalla.
- Una relación de clasificación no se puede confirmar ni rechazar desde aquí.
- Un nombre compartido no se puede cambiar desde un solo documento.

## 16. Auditoría (qué queda registrado)
- **Aceptar, corregir o rechazar una ficha:** evento de validación en la bitácora encadenada del documento, con el antes, el después y la nota o el motivo.
- **Cambiar el nombre de una entidad:** «modificar» en `RegistroAuditoria` y la versión anterior en VersionRiC (nada se pierde).
- **Publicar:** evento de publicación.

## 17. Interoperabilidad
Solo lo revisado llega al catálogo y a las exportaciones RiC-O, JSON-LD y CSV (M8 y M9).

## 18. Normativa aplicable
- ISO 15489: control y evidencia de las decisiones.
- Acuerdo 003 de 2015: autenticidad e integridad.
- Principio «IA asistida, no automática» de la especificación (sección 25).

## 19. Arquitectura
| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Dónde vive la decisión del revisor | Tabla aparte de revisiones; campos en RelacionRiC | Campos en RelacionRiC | Una relación tiene una sola revisión vigente; el historial completo ya está en la bitácora y en VersionRiC | Si en el futuro se exigen dos revisores por ficha, habrá que pasar a una tabla |
| Corrección de una entidad compartida | Renombrar en todos; crear una copia; impedirlo y remitir a M5 | Impedirlo y remitir a M5 o al rechazo | Evita cambiar sin querer la descripción de otros documentos y evita duplicados | Un paso más para el revisor en ese caso |
| Relaciones de clasificación | Revisarlas también; excluirlas | Excluirlas («no aplica») | Provienen de la TRD y del expediente elegidos al cargar, no de la IA | — |
| Documentos ya publicados al migrar | Devolverlos a revisión; darlos por confirmados | Darlos por confirmados a nombre de quien los publicó | No retirar del catálogo trabajo ya aprobado | — |

## 20. Código
- `ric/models.py`: `RelacionRiC.Revision` y campos nuevos.
- `ric/migrations/0022_modulo6_revision.py`.
- `ric/flujo.py`: `pendientes_revision`.
- `ric/vistas_analisis.py`: `_fichas_revision`, `_documentos_que_usan`, `revision`, `revision_confirmar`, `revision_aprobar`, `revision_rechazar`, y M4 `cambiar_tipo`.
- `ric/instrumentos.py`: lo estructural queda en «no aplica».
- `ric/templates/ric/revision.html` y `_lista_documentos.html`.
- `config/urls.py`.

## 21. Pruebas
`tests/test_modulo6_revision_por_ficha.py` tiene 11 pruebas:
- Lo aceptado en el análisis llega pendiente.
- Publicación bloqueada en pantalla y en el servidor.
- Aceptar habilita publicar.
- Corregir el nombre deja versión y auditoría.
- Una entidad compartida no se renombra.
- Motivo obligatorio y vuelta al análisis.
- Baja confianza primero.
- Lo estructural no se revisa.
- Cambiar el tipo en M4 devuelve la relación a revisión.
- Consulta no revisa.
- La bandeja muestra lo pendiente.

`tests/test_m6_revision.py` se ajustó al nuevo flujo. Además se hizo una verificación en Chromium: «Confirmar rechazo» queda deshabilitado sin motivo.

## 22. Criterios de aceptación (historia de usuario 6)
- Campo editable junto a aceptar y rechazar de esa misma ficha, nunca un botón general (RF-M6-01 y RF-M6-02): **cumplido**.
- Rechazo sin motivo no permitido (RF-M6-03): **cumplido**, en pantalla y en el servidor.
- Con al menos un elemento pendiente, el botón de aprobar está deshabilitado y el documento no pasa al catálogo (RF-M6-04): **cumplido**, contando lo pendiente del análisis y de la revisión.

## 23. Evidencia concreta de aplicación de RiC
En el acta del Cabildo de 1810 hay dos fichas. «Cabildo de Santafé» es CorporateBody E11, con R027 has creator y el rol productor. «José Acevedo y Gómez» es Person E08, con R027 y confianza 0,40, así que aparece primero con la marca de baja confianza. Cada ficha cita el fragmento y la página, y dice qué Mechanism (E13) la propuso. La publicación exige una relación de procedencia confirmada (CC-03).

## Qué no hace (y qué pasa en cada error)
- **Separación de funciones:** no la impone, por decisión tomada al validar el módulo (29/09/2026) («puede revisar y validar la misma persona; no debo depender de más para seguir»). La pantalla y el historial siempre muestran quién aceptó en el análisis y quién revisó.
- **Tipo de relación:** no se corrige desde aquí (eso es M4); al cambiarlo, la ficha vuelve a revisión.
- **Si falla una acción:** la pantalla dice por qué (sin motivo, entidad compartida, relación de clasificación, pendientes o CC-03) y nada cambia.
