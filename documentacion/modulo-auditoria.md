# Módulo transversal · Auditoría

**Estado:** entregado, pendiente de validación.

---

## 1. Propósito

Registrar de forma automática e inalterable cada acción relevante de cualquier módulo, con el antes y el después cuando aplica, y cada inicio y cierre de sesión. Con ese registro se ofrecen tres consultas:

- la **historia de una entidad**;
- la **trazabilidad propia** de cada persona;
- el **panel consolidado semanal** por persona, para la administración.

## 2. Auditoría (qué se revisó antes de construirlo)

**Documentos revisados:**
- el prompt de auditoría (secciones 1 a 11; se recibieron dos copias idénticas);
- el diseño consolidado, Partes 7 y 8;
- el prompt de autenticación;
- lo ya construido.

**Lo que ya existía desde el primer módulo:**
- la tabla `registro_auditoria` **de solo anexar**, con un disparador de base de datos que rechaza cualquier UPDATE, DELETE o TRUNCATE, incluso del administrador;
- la **función única** `servicios/auditoria.registrar()`, que todos los módulos llaman dentro de la misma transacción de la acción;
- los eventos de inicio y cierre de sesión, incluido el cierre por expiración con la hora de la última actividad real.

**Faltaba:**
- las consultas y las pantallas;
- el catálogo legible de acciones;
- el cierre automático de las sesiones vencidas aunque nadie vuelva a entrar;
- la prueba explícita de que los seis módulos restantes registran cada acción comprometida;
- la prueba de extremo a extremo.

**Contradicción resuelta:** el prompt pide un `POST /auditoria/registrar` «de uso interno, nunca expuesto al frontend». Un endpoint HTTP siempre queda expuesto a quien llegue al servidor. **No se creó**: los módulos llaman a la función de Python en el mismo proceso, que es lo que el prompt busca (ver §19). Una prueba confirma que la ruta no existe.

## 3. Problema que resuelve

Un archivo público necesita demostrar quién hizo qué, cuándo y sobre qué documento:

- ante un órgano de control;
- ante una reclamación;
- para su propia gestión.

Y necesita hacerlo sin que nadie tenga que llevar registros a mano ni compilar informes semanales.

## 4. Usuarios

| Rol | Qué ve |
|---|---|
| Administrador | Toda la historia de cualquier entidad; el panel consolidado de todas las personas |
| Roles con auditoría «todo equipo» (p. ej. el perfil de referencia *auditor*) | Lo mismo que el administrador, porque así lo configura la administración en Roles |
| Archivista, revisor, descriptor, etc. (auditoría «propia») | Solo sus propias acciones, en su trazabilidad y en la historia de cualquier entidad |
| Consulta | Nada del módulo |

La regla se aplica con la misma dependencia de roles del módulo de autenticación (`acceso_modulo("auditoria")` y `Actor.ve_toda_la_auditoria`), no con una comprobación aparte.

## 5. Casos de uso

1. Desde una descripción, una entidad del vocabulario, una instanciación o un usuario, abrir su «Historial de auditoría» y ver la línea de tiempo con el antes y el después lado a lado.
2. Revisar la trazabilidad propia, filtrando por tipo de acción y por rango de fechas.
3. (Administración) Ver la semana del equipo: días hábiles trabajados, horas conectadas y acciones por tipo.
4. (Administración) Abrir a una persona y ver su semana sesión por sesión: inicio, fin, duración, motivo del cierre y acciones hechas en cada sesión.

## 6. Entidades RiC involucradas

Ninguna directamente. La auditoría registra eventos sobre las entidades de los demás módulos: Record Resource, Instantiation, Agent, Place y demás.

En términos de RiC-CM, cada evento es comparable a un **Event** (RiC-E14) con su **Agent** ejecutor. Se guarda como registro técnico del sistema, no como parte de la descripción archivística. Por eso nunca sale en el catálogo ni en los instrumentos.

## 7. Relaciones RiC involucradas

Ninguna nueva. El registro guarda `entidad_tipo` y `entidad_id`, que apuntan a la entidad afectada. Es un vínculo técnico, no una relación RiC.

## 8. Funcionalidades

**Mi trazabilidad:**
- filtros de tipo de acción (solo los tipos que la persona tiene) y de rango de fechas;
- lista cronológica con punto de color por módulo, nombre legible de la acción, detalle, fecha y hora, e insignia del módulo;
- «Ver más» para paginar.

**Panel consolidado:**
- selector de semana: anterior, siguiente o «Ir a» una fecha;
- una fila por persona con nombre, rol, días hábiles trabajados sobre los posibles (y los de fin de semana aparte), horas conectadas en números alineados, y las acciones como insignias de conteo por tipo;
- al hacer clic, el desglose sesión por sesión;
- una persona sin sesiones aparece con ceros, no se omite.

**Historial de una entidad:**
- migas de pan de vuelta a la entidad;
- tabla con fecha, usuario, acción y antes → después (el valor anterior tachado en rojo y el nuevo resaltado en verde).

**Enlace «Historial de auditoría»** en:
- la descripción publicada;
- el detalle del vocabulario;
- la ficha técnica de preservación;
- cada usuario de la gestión de usuarios.

**Catálogo de acciones** con nombre legible y grupo del panel, por ejemplo «Documentos cargados», «Descripciones validadas», «Entidades del vocabulario», «Instrumentos generados», «Verificaciones de integridad», «Migraciones» y «Administración». Una prueba exige que toda acción que aparezca en el código tenga su nombre.

## 9. Flujos

**Registro:**
1. Cada módulo llama a `registrar()` en la misma transacción de la acción.
2. Si la acción se guarda, el evento se guarda.
3. Si la acción falla, ninguno de los dos queda.

**Sesión:**
1. Autenticación registra el inicio al entrar y el cierre al salir, al cambiar la contraseña, al desactivar la cuenta o al revocar.
2. El trabajador cierra cada minuto las sesiones vencidas, con fin igual a la última actividad real.

**Panel:**
1. En cada consulta se toman los eventos de inicio de sesión de la semana (hora de Bogotá).
2. Se une cada uno con su cierre.
3. Se recorta cada sesión a los límites de la semana.
4. Se suman las duraciones y se cuentan los días locales tocados.
5. Se cuentan las acciones por grupo.

## 10. Pantallas

| Pantalla | Ruta |
|---|---|
| Mi trazabilidad | `/auditoria` |
| Panel consolidado (con permiso «todo equipo») | `/auditoria?vista=consolidado` |
| Historial de una entidad | `/auditoria/entidad/:tipo/:id` |

La entrada «Auditoría» aparece en la sección Sistema de la barra lateral, solo para roles con auditoría propia o de todo el equipo.

## 11. UX/UI

- **El panel dice lo que es:** «Datos objetivos de conexión y de acciones registradas, por persona. No es una calificación ni un ranking». No hay ordenamiento por productividad: las filas van por nombre.
- **Horas en formato humano** («3 h 45 min») con cifras tabulares alineadas a la derecha.
- **Días hábiles «2 de 3»:** en la semana en curso, solo cuentan los días hábiles que ya empezaron. El trabajo en fin de semana se muestra aparte, no infla el conteo.
- **En la historia de una entidad**, quien solo ve lo propio recibe el aviso «Usted ve solo sus propias acciones sobre esta entidad».
- El antes y el después se muestran solo cuando algo cambió. En una creación no hay nada que comparar.
- En móvil las tablas se desplazan dentro de su tarjeta (verificado a 390 px).

## 12. Modelo de datos

**Sin tablas nuevas.** Se usan:

- **`registro_auditoria`** (desde la migración 0001):
  - `id`, `fecha`, `usuario_id` (nulo si la acción es del sistema);
  - `modulo`, `accion`;
  - `entidad_tipo`, `entidad_id`;
  - `valor_anterior` y `valor_nuevo` (JSONB);
  - `detalle`, `ip`.

  Tiene índices por fecha, usuario, módulo, acción y entidad. El disparador `auditoria_solo_anexar` rechaza UPDATE, DELETE y TRUNCATE.
- **`sesiones`:** solo para saber si una sesión sin evento de cierre sigue abierta, y su última actividad.

**Configuración nueva:** `RICORA_ZONA_HORARIA` (por defecto `America/Bogota`). Define qué es un día y una semana en el panel. Se agregó `tzdata` para que no dependa del sistema operativo de la imagen.

## 13. API

| Método y ruta | Quién | Qué hace |
|---|---|---|
| `GET /api/auditoria/mi-trazabilidad?accion&modulo&desde&hasta&antes_de` | auditoría propia o todo | Acciones del usuario autenticado |
| `GET /api/auditoria/entidad/{id}?tipo=` | auditoría + acceso al módulo de la entidad | Historia de la entidad; solo lo propio si el rol ve «propia» |
| `GET /api/auditoria/acciones` | auditoría | Tipos de acción para los filtros |
| `GET /api/auditoria/consolidado?semana=AAAA-MM-DD` | «todo equipo» | Resumen semanal por persona |
| `GET /api/auditoria/consolidado/{usuario_id}?semana=` | «todo equipo» | Desglose sesión por sesión |

**Sin POST, PUT, PATCH ni DELETE:** una prueba recorre todas las rutas del módulo y confirma que solo existe GET. `POST /auditoria/registrar` no existe por HTTP (§2).

## 14. Uso de IA

**Ninguno.** El panel presenta datos objetivos. El prompt prohíbe expresamente calcular o interpretar productividad o desempeño.

## 15. Seguridad

- **Inalterable en tres capas:**
  - no hay ninguna ruta que escriba en la auditoría;
  - la función `registrar()` solo inserta;
  - la base de datos rechaza UPDATE, DELETE y TRUNCATE incluso a un administrador conectado directamente.
- **Visibilidad aplicada en el servidor y en cada consulta.** La trazabilidad propia filtra siempre por el usuario del token, nunca por un parámetro, y la historia de una entidad filtra por el usuario si el rol ve «propia». Nadie puede pedir los eventos de otro cambiando la dirección.
- **Para ver la historia de una entidad hay que tener acceso a su módulo.** Por ejemplo, un digitalizador sin acceso a vocabularios recibe 403 en la historia de una entidad del vocabulario.
- **Contraseñas y secretos nunca entran en el registro:** se registra que se cambió la contraseña, nunca el valor.

## 16. Auditoría (qué queda registrado)

El propio módulo **no escribe eventos**: es de solo lectura. Los eventos los escriben los demás módulos:

| Módulo | Acciones comprometidas por su prompt |
|---|---|
| Autenticación | inicio y cierre de sesión (incluida la expiración), usuario creado, rol cambiado, usuario desactivado o reactivado, roles creados o editados, contraseñas definidas o cambiadas, sesiones revocadas |
| Sistema | fondo registrado, parámetros cambiados, alertas atendidas |
| Ingesta | documento cargado, carga rechazada, duplicado confirmado o cancelado, error descartado, reintento |
| Descripción | descripción publicada, descripción corregida (con el antes y el después de cada campo) |
| Vocabularios | fusión (entidades, relaciones movidas, origen), sugerencia descartada |
| Instrumentos | inventario exportado, guía exportada |
| Preservación | integridad verificada, migración aprobada, completada o fallida |

## 17. Interoperabilidad

- Los eventos son JSON con antes y después: se pueden exportar a CSV o a PREMIS (eventos de preservación) cuando se pida.
- **Pendiente:** exportar el reporte semanal a hoja de cálculo. El prompt no lo pide, pero sería útil para informes de gestión.

## 18. Normativa aplicable

- **Ley 594 de 2000 (Ley General de Archivos)** y **Acuerdo 006 de 2014 del AGN:** trazabilidad y responsabilidad sobre los documentos.
- **ISO 15489-1:2016:** metadatos de proceso de gestión documental (quién, qué, cuándo).
- **ISO 23081:** metadatos para la gestión de documentos, eventos de gestión.
- **Ley 1581 de 2012 (protección de datos personales):** el registro guarda datos de actividad del personal. Por eso el panel solo lo ve quien la administración autoriza, y el propio prompt prohíbe calificar el desempeño. Conviene informar al equipo que el sistema registra la actividad.

## 19. Arquitectura

- **Escritura:** `servicios/auditoria.registrar()`, en la misma transacción de cada acción.
- **Lectura:** `servicios/trazabilidad.py` y `routers/auditoria.py`.
- **Sesiones:** `servicios/sesiones.py`, más el trabajador, que cierra las vencidas cada minuto.

### Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| **Cálculo del panel consolidado** (exigida por el prompt, §5) | **Al vuelo** en cada consulta; resumen precalculado por semana cerrada con un trabajo periódico (Celery + Redis, como sugiere el prompt, o el trabajador existente) | **Al vuelo** | Volumen real: un equipo de pocas personas sobre un fondo. Una semana tiene decenas de sesiones y cientos o pocos miles de eventos, y la consulta usa los índices por fecha, usuario y acción (milisegundos). Un resumen precalculado es una segunda copia que puede desincronizarse, por ejemplo si una sesión de la semana pasada se cierra hoy por expiración. Al vuelo, el panel siempre coincide con el registro. No hace falta Celery ni Redis | Si el equipo creciera a cientos de personas o a años de consulta masiva, habría que precalcular. Se haría en el trabajador existente, con el mismo patrón de los módulos 3 y 5, sin cambiar la pantalla |
| Fuente de las horas conectadas | La tabla `sesiones` (operativa, se actualiza); **los eventos de inicio y cierre de la auditoría** | **Eventos de auditoría**, con `sesiones` solo para las que siguen abiertas | La auditoría no se puede alterar: las horas del informe salen de una fuente con valor probatorio | Una sesión sin evento de cierre y sin fila abierta (datos incompletos) no se cuenta; no se inventa una duración |
| `POST /auditoria/registrar` | Exponerlo por HTTP con un secreto interno; **función de Python en el mismo proceso** | **Función** | El prompt lo quiere «interno, nunca expuesto al frontend». Todos los módulos viven en el mismo backend, y una ruta HTTP sería una puerta más que proteger. La función además comparte la transacción: no puede haber una acción sin su evento | Si algún día un módulo fuera un servicio aparte, necesitaría un canal autenticado |
| Días y semanas | UTC; **hora local del equipo** | **America/Bogota** (configurable) | Una sesión de las 8 p. m. en Bogotá es del mismo día, no del siguiente como diría UTC | Un equipo en otro huso horario cambia la variable `RICORA_ZONA_HORARIA` |
| Quién ve el panel | Solo el rol administrador; **el administrador y los roles a los que él dé «todo el equipo»** | **Permiso de auditoría «todo»** | Coherente con los roles configurables que pidió la autora (p. ej. un auditor interno). El administrador decide; por defecto, solo él lo tiene | Si la administración da ese permiso de más, esa persona verá la actividad de todos. Queda en auditoría cuando se edita el rol |
| Días «trabajados» | Cualquier día con sesión, sobre 7; **días hábiles sobre los hábiles posibles, más fines de semana aparte** | **Hábiles sobre posibles** | Refleja la jornada laboral colombiana sin castigar ni premiar el trabajo de fin de semana | Festivos: hoy cuentan como hábiles posibles. Se puede agregar un calendario de festivos |

## 20. Código (dónde vive, cómo se organiza)

```
app/servicios/auditoria.py          registrar(): la única función de escritura (desde el módulo 0)
app/servicios/trazabilidad.py       catálogo de acciones, historia, trazabilidad propia, consolidado, desglose
app/routers/auditoria.py            /api/auditoria (solo GET)
app/trabajador.py                   cierre de sesiones vencidas cada minuto
app/core/config.py                  RICORA_ZONA_HORARIA
frontend/src/pages/Auditoria.tsx    Mi trazabilidad, Panel consolidado, Historial de una entidad
frontend/src/components/Historia.tsx  enlace «Historial de auditoría» reutilizable
frontend/src/lib/auditoria.ts
tests/test_auditoria.py             incluida la prueba de extremo a extremo
tests/test_permisos_reales.py       matriz de roles contra los endpoints reales
```

## 21. Pruebas

**Proyecto completo: 145 pruebas, todas pasan.** Las de este módulo:

- **Extremo a extremo** (`test_ciclo_completo_de_los_siete_modulos_queda_en_auditoria`), con Siegfried y Ghostscript reales:
  1. La administradora registra el fondo, crea un usuario, le cambia el rol y lo desactiva.
  2. La archivista carga un PDF por la ingesta real.
  3. Lo describe (motor de prueba) y publica.
  4. Lo corrige con datos de control.
  5. Verifica que aparece en el vocabulario y fusiona una variante.
  6. Genera el inventario (que incluye el oficio con código y fecha) y exporta la guía.
  7. Verifica la integridad y migra a PDF/A.
  8. Cierra sesión.

  La prueba comprueba, **para cada una de las acciones comprometidas por los seis módulos restantes**, que hay **exactamente un** evento (o dos inicios de sesión, uno por persona), con su autor y con el antes y el después correctos:
  - rol revisor → consulta;
  - caja vacía → «1»;
  - absorbida «Alcaldia Mpal.»;
  - formato resultado `fmt/477`.

  Además comprueba que la archivista ve en su trazabilidad todo lo suyo y nada de la administradora.
- **Catálogo:** toda acción que aparece en el código tiene nombre legible.
- **Sesiones:** inicio y cierre por expiración sin intervención (lo que hace el trabajador cada minuto), con fin igual a la última actividad.
- **Panel:**
  - dos sesiones el mismo día (2 h 30 y 1 h 15) más una que cruza la medianoche (3 h) dan 6 h 45 exactas y 3 días;
  - las acciones se agrupan;
  - una persona sin sesiones aparece con ceros;
  - el desglose tiene la duración de cada sesión y sus acciones;
  - otra semana da cero.
- **Visibilidad con dos usuarios:**
  - la trazabilidad propia nunca trae eventos del otro;
  - en una entidad tocada por los dos, el archivista solo ve lo suyo y el administrador ve ambos;
  - el archivista recibe 403 en el panel y en el desglose de un compañero;
  - el filtro por tipo y fechas funciona;
  - consulta recibe 403;
  - sin acceso al módulo de la entidad, 403.
- **Nada se edita ni se borra:**
  - el módulo solo tiene rutas GET;
  - PUT, PATCH, DELETE y POST responden 405 incluso al administrador;
  - `/api/auditoria/registrar` no existe;
  - la prueba de autenticación confirma que la base de datos rechaza UPDATE, DELETE y TRUNCATE.

**Prueba de mutación:** al quitar el registro de auditoría de la exportación del inventario, la prueba de extremo a extremo falla con «instrumentos/inventario_exportado: 0 eventos».

**Verificación visual** en navegador real: Mi trazabilidad, panel consolidado con desglose, historial de una entidad y móvil a 390 px, sin errores de JavaScript.

## 22. Criterios de aceptación

| Criterio (prompt §10–11) | Cumple |
|---|---|
| Cada acción comprometida genera exactamente un evento con el antes y el después correctos | ✓ (extremo a extremo) |
| Inicio y cierre de sesión, incluida la expiración, generan su evento sin intervención | ✓ |
| La trazabilidad propia nunca trae eventos de otro usuario (dos usuarios de prueba) | ✓ |
| El archivista recibe error de permisos en el panel consolidado | ✓ |
| Una persona sin sesiones aparece con cero días y cero horas | ✓ |
| Ningún evento se edita ni se elimina por ningún endpoint, ni siendo administrador | ✓ |
| Horas de varias sesiones en un mismo día = suma exacta | ✓ |
| Decisión al vuelo o precalculado documentada con tabla completa | ✓ (§19) |
| Prueba de que cada uno de los seis módulos restantes registra sus acciones | ✓ |
| Prueba de integración de extremo a extremo de los siete módulos | ✓ |

**Pendiente honesto:**
- Los **festivos** colombianos cuentan hoy como días hábiles posibles.
- El reporte semanal no se exporta a hoja de cálculo.
- Conviene **informar al equipo** que el sistema registra su actividad de conexión (Ley 1581).

## 23. Evidencia concreta

Extracto real de la trazabilidad de la archivista tras el recorrido completo:

```
Cargó un documento            Ingesta         Oficio_114_1948.pdf
Publicó una descripción       Descripción     «Oficio de la Alcaldía Municipal sobre el estado del archivo»
Corrigió una descripción      Descripción     caja: — → 1 · código de referencia: — → CO-AM-114 …
Fusionó entidades             Vocabularios    «Alcaldia Mpal.» se fusionó en «Alcaldía Municipal» · 1 relación movida
Exportó un inventario         Instrumentos    1 renglón · 0 pendientes
Exportó una guía              Instrumentos
Verificó la integridad        Preservación    íntegra
Aprobó una migración          Preservación    → PDF/A-2b (automática)
Cerró sesión                  Autenticación   cierre voluntario
```

Los siete módulos dejan su rastro en un solo registro, con una sola función, y ninguna línea se puede borrar.
