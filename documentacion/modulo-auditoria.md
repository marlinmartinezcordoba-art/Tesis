# Módulo transversal · Auditoría

**Versión:** 7 (prompt «Módulo transversal, Auditoría», versión con hallazgos de conformidad).
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

---

## Versión 7 · Hallazgos de conformidad, propiedad RiC-O e identificador de la instrucción

Lo que la versión 7 del prompt agrega y cómo quedó. La decisión técnica del §6 (consolidado y resumen de decisiones calculados al vuelo, sin trabajo periódico) no cambia: sigue en §19.

### Hallazgos de conformidad (§5bis)

- **Registro manual, solo administrador.** Título, descripción de la brecha, componentes (de los siete módulos), estado (abierto, en corrección, cerrado), fecha de apertura, fecha de cierre y acción tomada o pendiente. Del hallazgo creado solo cambian el estado, la fecha de cierre y la acción: la API rechaza cualquier otro campo (422). Un hallazgo cerrado tiene siempre fecha de cierre y uno abierto no: lo exige la base de datos (restricción `ck_hallazgo_cierre`).
- **Toda creación y todo cambio quedan en la auditoría** (`hallazgo_creado`, `hallazgo_actualizado`, con el estado antes y después). Así la historia de cómo se cerró cada brecha es ella misma auditable.
- **Pantalla:** pestaña «Hallazgos de conformidad», con filtros por estado y por componente, cifras por estado, tarjetas en rojo, ámbar o verde, formulario para registrar, edición del estado y de la acción, y **hoja de cálculo con los mismos filtros**.
- **Sembrados desde el primer despliegue** (migración 0014), cada uno con su evento de creación en la auditoría. **Estado real al 3 de octubre de 2026, no optimista:**

| N.º | Hallazgo | Estado | Por qué ese estado |
|---|---|---|---|
| 1 | Punto de acceso dereferenciable y exportación RDF sin sesión | **En corrección** | Construido y probado (también sin sesión), pero en el servidor la resolución pública está apagada hasta tener HTTPS. Se cierra al encenderla y dejar la evidencia |
| 2 | Confianza del OCR | Cerrado | Commit 5cac380 |
| 3 | Vocabulario del fondo desconocido para el motor | Cerrado | Commit 629f203 |
| 4 | Cobertura parcial de las 85 relaciones de RiC-CM | **En corrección** | 25 de 85 códigos (29 %), más 2 propiedades propias de RiC-O. Cerrarlo es decidir si la cobertura parcial es delimitación de la tesis (lo decide la autora) o se amplía |
| 5 | Ficha ISAAR-CPF incompleta | Cerrado | Commit 69fc720; la relación asociativa (R044) quedó verificada contra el OWL |
| 6 | Tipo de actividad, mandato y sub-actividades | Cerrado | Commits f9e1aae, 69fc720 y 629f203 |
| 7 | Solo fechas exactas | Cerrado | Commit f9e1aae (EDTF) |
| 8 | Sin OAIS, PREMIS, segunda copia ni plan | **En corrección** | Lo técnico está; falta que la autora confirme el fundamento normativo colombiano del plan, y la segunda copia comparte disco |
| 9 | Cobertura entidad por entidad | Cerrado | Commits 69fc720, 629f203 y 497eff8; verificado contra el OWL |
| 10 | Secuencia, custodia, jerarquía normativa, idioma y condiciones | Cerrado | Commits 5cac380 y 629f203; exportados en 3765cd5 |
| 11 | El mecanismo del vocabulario existía pero nadie lo usaba | Cerrado | Encontrado en esta ronda; commit 497eff8 |
| 12 | `rico:title` anotado como RiC-A40 (es *Structure*) | Cerrado | Encontrado al validar la exportación; commit 3765cd5 |
| 13 | Tipo de mandato con la propiedad genérica | Cerrado | Commit 3765cd5 |
| 14 | El índice de términos habría listado los programas | Cerrado | Commit 497eff8 |

Los hallazgos 11 a 14 no estaban en el prompt: los encontró la propia depuración de esta ronda y se registran para que el capítulo de evaluación cuente el proceso real. **La fecha de apertura de los diez primeros (2 de octubre de 2026) es la de la revisión experta según el material disponible; conviene que la autora la confirme.**

### Columna «propiedad RiC-O» (§7 y §10)

- **Trazabilidad por entidad:** columna propia. Si el evento es sobre una relación (un vínculo entre agentes, una decisión del motor), muestra la propiedad de RiC-O de esa relación, con su código RiC-CM al pasar el cursor. Si el evento cambia campos, cada campo lleva la suya: `rico:title`, `rico:conditionsOfAccess`…
- **Nunca se inventa un nombre.** Todo sale del mapeo único verificado contra el OWL (`ric_o.CAMPO_RICO`, `ric_o.propiedad_de_codigo`). Lo que no está ahí se muestra **atenuado y en cursiva**: «literal pendiente de confirmación» (por ejemplo, la caja o la carpeta del inventario) o «sin propiedad en RiC-O» (calendario, nivel de detalle, fuentes, estructura del agente).
- **Panel de decisiones de IA:** junto al tipo, la **clase de RiC-O** (`rico:CorporateBody`, `rico:Date`…), y una columna **«Propiedad RiC-O»** con la relación que la decisión afecta (`rico:hasCreator`, `rico:documents`, `rico:hasDocumentaryFormType`…). En una rechazada, la que habría tenido. Desde esta versión la publicación guarda en cada evento el código de la relación que de verdad creó (`codigo_ric`). En las decisiones anteriores se reconstruye con la misma regla rol → relación de la publicación. La hoja de cálculo trae las dos columnas.
- Se agregó **«Idioma»** al filtro de tipos: faltaba desde la versión 3 de descripción.

### Identificador de la instrucción y etiqueta (§5)

- El identificador ya era un resumen SHA-256 de la instrucción y del esquema de respuesta, truncado a 8 caracteres. Ahora el cálculo es una función (`motor.version_de`) con su **prueba de determinismo**: el mismo texto da el mismo valor; un carácter distinto, otro.
- **Etiqueta legible opcional** («v3»), solo administrador, en la tarjeta «Versiones de la instrucción del motor» del panel de decisiones. Muestra cada versión presente en las decisiones (y la vigente), cuántas decisiones tiene y entre qué fechas se usó. La etiqueta acompaña al identificador y **no lo reemplaza**. Solo se pone o se cambia: no se quita, porque nada se borra, y el nombre anterior queda en la auditoría (`version_prompt_etiquetada`). Una etiqueta no puede nombrar dos versiones.

### Seguridad

- Hallazgos y etiquetas: solo administrador. El archivista recibe 403 al consultar, crear o editar.
- Las rutas de escritura están en un enrutador aparte (`auditoria.gestion`). La regla «la auditoría solo se lee» sigue igual para el registro: la prueba enumera las rutas de escritura, que son exactamente las tres de hallazgos y etiquetas.
- **Un evento de decisión de IA tampoco se puede editar ni borrar**, ni siquiera con SQL directo: el disparador de la base lo rechaza. La prueba lo intenta y comprueba que el valor no cambió.
- Las horas de Auditoría se muestran en la zona de Bogotá en todas las tablas. Antes, dos de ellas usaban la del navegador y no coincidían con el resto.

### Modelo de datos (migración 0014)

`hallazgos_conformidad` (número único, título, descripción, componentes, estado, fechas, acción, autor) y `etiquetas_version_prompt` (versión, etiqueta única, nota, quién y cuándo). Reversible. Al bajar no se borran los eventos de la siembra, porque el registro es de solo anexar.

### API

| Método y ruta | Permiso | Qué hace |
|---|---|---|
| `GET /api/auditoria/hallazgos?estado&componente` | administrador | Lista, conteo total y conteo filtrado |
| `GET /api/auditoria/hallazgos/hoja-de-calculo` | administrador | Los mismos, con los mismos filtros, en `.xlsx` |
| `POST /api/auditoria/hallazgos` | administrador | Registrar (queda «abierto», con su número) |
| `PATCH /api/auditoria/hallazgos/{id}` | administrador | Solo estado, fecha de cierre y acción |
| `GET /api/auditoria/versiones-prompt` | administrador | Versiones con decisiones, fechas de uso y etiqueta |
| `PUT /api/auditoria/versiones-prompt/{version}` | administrador | Poner o cambiar la etiqueta |
| `GET /api/auditoria/decisiones-ia` | administrador | Ahora con `clase_rico`, `propiedad_rico` y `version_etiqueta` |
| `GET /api/auditoria/entidad/{id}` | según el módulo de la entidad | Ahora con `propiedad_rico` por evento y por cambio |

### Pruebas

`tests/test_auditoria_v7.py`, 10 pruebas:
- los 14 hallazgos sembrados con su estado real (1, 4 y 8 en corrección; los demás cerrados con fecha) y su evento de creación;
- crear → en corrección → cerrado → reabrir, con un evento por cambio, el antes y el después del estado y la fecha de cierre automática;
- el título no se edita, y sin cambio no hay evento;
- filtros y hoja de cálculo con los mismos filtros; el archivista recibe 403 en todo;
- determinismo del identificador;
- la etiqueta acompaña al identificador en el panel y su cambio queda auditado;
- clase y propiedad RiC-O de cada decisión (productor → `hasCreator` R027, destinatario → `hasAddressee`, lugar rechazado → `hasOrHadSubject`, actividad → `documents`, mandato → `regulatesOrRegulated`, función → `hasActivityType`, forma documental, título → `title`, fecha → `isCreationDateOf`);
- trazabilidad: `rico:title` verificada y la caja como literal pendiente;
- un vínculo entre agentes muestra `hasOrHadSubordinate` (R045);
- todo campo con propiedad existe en el mapeo verificado.

**De extremo a extremo** (`tests/test_auditoria.py`, ampliada). Ingesta → descripción con **una propuesta aceptada, una corregida y una rechazada** → vocabularios (fusión) → inventario y guía → verificación y migración → paquete de preservación → exportación RiC-O y su conformidad → un hallazgo registrado y pasado a corrección. Cada acción comprometida por los siete módulos queda en la auditoría el número exacto de veces:
- una decisión por propuesta, más el título y el alcance;
- cuatro mecanismos: Siegfried, RICORA, el motor y Ghostscript;
- dos segundas copias;
- las tres decisiones con su tipo bien calculado.

**Ningún evento se edita ni se borra:** ampliada a un evento de decisión de IA, también por SQL directo.

**Mutaciones** detectadas: no registrar el cambio de un hallazgo; inventar la propiedad de un campo en vez de marcarlo pendiente.

**El proyecto llega a 275 pruebas.** Verificación visual de las pestañas Hallazgos y Decisiones en escritorio y a 390 px, sin errores ni desplazamiento horizontal.

### Evidencia: cadena completa en el panel de decisiones

Sobre el fondo de prueba, el oficio 210 de 1948 («Oficio de la Secretaría de Gobierno sobre los permisos de las fiestas de 1948»). El motor (`gemini-de-prueba` en desarrollo) propuso siete valores con la instrucción `3c5a7af7`. La archivista los aceptó, y el panel muestra cada uno con su clase y su propiedad:
- productor `rico:CorporateBody` · `rico:hasCreator`;
- destinatario · `rico:hasAddressee`;
- actividad `rico:Activity` · `rico:documents`;
- fecha `rico:Date` · `rico:isCreationDateOf`;
- idioma `rico:Language` · `rico:hasOrHadLanguage`;
- título · `rico:title`;
- alcance · `rico:scopeAndContent`.

Las cifras del resumen salen de esos mismos eventos.

