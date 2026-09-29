# Módulo 10 · Panel de indicadores

Este documento sigue la estructura de 23 puntos de la sección 5 del prompt de desarrollo. El alcance lo fijan la historia de usuario 10 y los requisitos RF-M10-01 a RF-M10-04.

## 1. Propósito
Que quien dirige el proceso vea en un vistazo, y para el periodo que elija, cuánto entra, cuánto está validado, cuánto tarda la revisión y qué está atrasado. De cada cifra puede llegar a los documentos concretos que la componen.

## 2. Auditoría (qué se revisó antes de construirlo)
Existía un panel con datos reales. Estos fueron los hallazgos:

| Aspecto | Hallazgo | Requisito afectado |
|---|---|---|
| Periodo | No había selector; la gráfica eran 8 semanas fijas | Historia 10 |
| «Tiempo promedio de revisión» | Medía el ciclo completo (carga → publicación), no la revisión | RF-M10-03 |
| Alerta de atraso | Solo contaba las propuestas pendientes del M3; un documento con todo aceptado pero sin revisar en el M6 no generaba alerta | RF-M10-04 |
| Cifras | Eran estáticas; hacer clic no llevaba a la lista de documentos que las componen | Tercer criterio de la historia 10 |
| % validado | Solo global, no por periodo | RF-M10-02 |

## 3. Problema que resuelve
Sin un panel, para dirigir el trabajo había que revisar documento por documento. Con cifras sin enlace, además, no se podía actuar sobre lo que el panel mostraba.

## 4. Usuarios
- **Administrador** (rol principal): ve todo y puede cambiar el límite de días de la alerta.
- **Archivista y revisor:** ven el panel completo, con cifras que enlazan a sus listas.
- **Consulta:** ve un panel reducido, sin enlaces a listas de trabajo interno.

## 5. Casos de uso
- Elegir el periodo: semana, mes, trimestre, año o todo.
- Leer las cifras.
- Ver la gráfica de ingreso.
- Hacer clic en una cifra y llegar a la lista filtrada.
- Hacer clic en la alerta de atraso y llegar a esa lista.
- Cambiar el límite de días (solo el administrador).

## 6. Entidades RiC involucradas
- Record (E04) e Instantiation (E06).
- Relaciones validadas y propuestas del motor (Mechanism E13), usadas como base de los estados.

## 7. Relaciones RiC involucradas
Todas las relaciones del documento, a través de su estado de análisis y de revisión.

## 8. Funcionalidades
- **Selector de periodo:** Última semana · Último mes (valor por defecto) · Último trimestre · Último año · Todo.
- **Documentos ingestados en el periodo** (RF-M10-01), junto con el número de archivos.
- **Porcentaje validado y publicado** (RF-M10-02) de los documentos ingestados en el periodo.
- **Tiempo promedio de revisión** (RF-M10-03). Mide desde el fin del análisis (la última entidad aceptada) hasta la publicación. Para los documentos publicados en el periodo se muestra también el ciclo completo, de la carga a la publicación.
- **Pendientes de revisión.** Cuenta los documentos sin publicar que tienen propuestas del motor por decidir **o** fichas sin revisar en el M6. Al lado se muestran cuántos están atrasados.
- **Alerta de atraso** (RF-M10-04). Un aviso rojo arriba indica cuántos documentos superan el límite y cuál es el más antiguo; al hacer clic se abre esa lista. El límite se configura en Administración → Parámetros.
- **Cada cifra enlaza a su lista.** La lista está en la bandeja de revisión (M6) con el filtro correspondiente e indica de qué cifra viene. Esto se comprobó: la cifra y el largo de la lista coinciden.
- **Gráfica de ingreso con granularidad según el periodo.** Por día en la semana y el mes, por semana en el trimestre y por mes en el año y en «todo». Cada barra lleva su número y la gráfica tiene descripción accesible.
- **Se conserva lo que ya había:** propuestas por estado, descripción incompleta (CC-02), documentos en curso, distribución de entidades, actividad reciente y retención vencida.

## 9. Flujos
Panel → elegir periodo → clic en una cifra o en la alerta → lista filtrada en la bandeja de revisión → abrir el documento.

## 10. Pantallas
- `/panel/?periodo=7|30|90|365|todo`.
- `/revision/?filtro=ingestados|validados|publicados|pendientes|atrasados|incompletos|sin_texto&periodo=`.

## 11. UX/UI
- **Tarjetas-enlace** con efecto al pasar el mouse y foco visible para teclado.
- **Selector de periodo** segmentado, con el periodo actual marcado.
- **Alerta roja** en la parte superior, fácil de ver.
- **Cifras que dicen qué miden y cómo,** por ejemplo «fin del análisis → publicación».

## 12. Modelo de datos
Sin cambios. Todo se calcula con los datos vigentes en cada consulta.

## 13. API
Sin API nueva. Los filtros son parámetros de la bandeja de revisión.

## 14. Uso de IA
No usa IA. Las cifras distinguen lo que propuso el motor de lo que decidieron las personas.

## 15. Seguridad
- Las listas filtradas exigen el rol archivista o revisor.
- El rol consulta ve solo cifras agregadas, sin enlaces a documentos.

## 16. Auditoría (qué queda registrado)
Consultar el panel no modifica nada, así que no se audita. Cada cifra sale de registros que ya están auditados.

## 17. Interoperabilidad
No aplica. Las cifras se pueden llevar a una hoja de cálculo desde la lista: marcar los documentos y exportarlos en CSV (M9).

## 18. Normativa aplicable
- Modelo Integrado de Planeación y Gestión (MIPG), dimensión de gestión documental: indicadores del Programa de Gestión Documental (PGD).
- ISO 30301: seguimiento y medición.

## 19. Arquitectura
| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Dónde se calculan las cifras | En la vista; en un módulo aparte | Módulo `ric/indicadores.py`, con la misma función para la cifra y para su lista | La cifra y la lista no pueden divergir | Se calcula en cada visita; para miles de documentos convendría guardarlo en caché |
| Qué es «tiempo de revisión» | Carga → publicación; fin del análisis → publicación | Fin del análisis → publicación, y además el ciclo completo | Es lo que pide RF-M10-03, sin perder el dato del ciclo | Un documento reabierto (rechazo y nuevo análisis) mide desde su último análisis |
| Qué cuenta como pendiente | Solo propuestas del M3; también fichas sin revisar del M6 | Ambas | Desde el M6, lo aceptado espera todavía la revisión | — |
| Dónde se ve la lista | Una pantalla nueva; la bandeja de revisión filtrada | La bandeja de revisión filtrada | Es lo que describe la historia 10 («lista filtrada en el módulo de revisión») | — |

## 20. Código
- `ric/indicadores.py`: `PERIODOS`, `ingestados`, `serie_ingesta`, `porcentaje_validado`, `tiempos_de_revision`, `esperando_revision`, `atrasados`, `FILTROS` y `documentos_de`.
- `ric/vistas_panel.py`: `panel`.
- `ric/vistas_analisis.py`: `revision_lista` con filtro.
- `ric/templates/ric/panel.html` y `ric/templates/ric/revision_lista.html`.

## 21. Pruebas
`tests/test_modulo10_indicadores.py` (7 pruebas):
- El selector cambia el volumen y la granularidad de la gráfica; un periodo inválido vuelve al mes.
- Porcentaje validado por periodo.
- Tiempo de revisión medido desde el fin del análisis.
- La alerta incluye las fichas sin revisar del M6 y respeta el límite configurable.
- Un documento publicado no cuenta como pendiente.
- Cada cifra enlaza a su lista, y esa lista contiene exactamente los documentos correctos.
- La cifra coincide con el largo de su lista.

`tests/test_m10_panel.py` se ajustó al panel por periodo.

## 22. Criterios de aceptación (historia de usuario 10)
- **Volumen por periodo, porcentaje validado y tiempo promedio de revisión, con los datos vigentes (RF-M10-01, 02 y 03):** cumplido, con selector de periodo.
- **Alerta visible cuando un pendiente supera el límite configurable (RF-M10-04):** cumplido, incluidas las fichas del M6.
- **Cada indicador lleva a la lista de documentos que compone ese número:** cumplido.

## 23. Evidencia concreta de aplicación de RiC
La cifra «pendientes de revisión» se calcula sobre el estado RiC de cada documento: las propuestas del motor (Mechanism E13) aún sin decidir y las relaciones RiC-CM aceptadas pero todavía sin revisar. «Validado» significa que todas las relaciones del Record pasaron la revisión humana y el documento se publicó. La cifra mide el grafo RiC, no un contador aparte.

## Qué no hace (y qué pasa en cada error)
- **Periodo personalizado:** no permite elegir fechas exactas, solo los cinco periodos. Se puede agregar.
- **Metas:** no compara contra metas del PGD, porque no hay metas cargadas en el sistema.
- **Sin datos en el periodo:** cada cifra lo dice, por ejemplo «sin publicaciones en el periodo»; nunca se inventan valores.
