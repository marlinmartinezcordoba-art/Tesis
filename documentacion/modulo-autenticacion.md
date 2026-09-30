# Módulo transversal · Autenticación y autorización

**Estado:** entregado, pendiente de validación.
**Pendiente explícito:** el alcance del rol **revisor** es **provisional**, hasta que la autora lo confirme. Hoy tiene solo lectura en los módulos de trabajo, sin publicar, aprobar, fusionar ni migrar nada.

---

## 1. Propósito

Controla tres cosas:

- quién entra al sistema y con qué rol;
- qué puede hacer cada rol en cada uno de los demás módulos;
- que una persona recupere el acceso a su cuenta sin intervención manual del administrador.

Además activa el registro único de auditoría, en el que escribirán los demás módulos.

## 2. Auditoría (qué se revisó antes de construirlo)

- **Prompts revisados:** el prompt maestro, el prompt del módulo de autenticación, el de auditoría y el diseño consolidado de los siete módulos (Partes 1, 7 y 8).
- **Mockup:** «Sistema RIC · Acceso» (inicio de sesión, recuperación, gestión de usuarios, mi perfil).
- **Andamiaje `sistema-ric` (FastAPI):**
  - el modelo `Usuario` no tenía ningún campo de contraseña;
  - no había `bcrypt`, `passlib` ni JWT;
  - ningún router verificaba identidad ni rol;
  - `tests/` estaba vacío.
- **Decisiones de la autora en esta etapa:**
  - reescribir en FastAPI + React tal como dicen los documentos;
  - retirar todo lo antiguo;
  - conservar el nombre RICORA y la paleta de tono medio;
  - usar el catálogo curado de relaciones del andamiaje.
- **Retiro de la versión Django, sin pérdida:**
  - el código queda en la rama `respaldo/ricora-django-final` y en el `.zip` entregado a la autora;
  - la base de datos anterior queda intacta en su volumen del servidor, que no se borra.

## 3. Problema que resuelve

Sin identidad ni roles no se puede verificar ningún criterio de aceptación de los demás módulos. Todos asumen «un archivista autenticado», «solo el administrador» o «el archivista ve solo lo suyo». Este módulo es el prerrequisito de todos ellos.

## 4. Usuarios

| Rol | Qué hace en este módulo |
|---|---|
| Administrador | Crea cuentas, cambia rol y nombre, desactiva y reactiva, reenvía enlaces, cierra sesiones, prueba el correo |
| Archivista, revisor, consulta | Ingresan, recuperan su contraseña, ven su perfil y cambian su contraseña |
| Persona invitada | Define su contraseña con el enlace de un solo uso |

## 5. Casos de uso

1. Iniciar sesión con correo y contraseña.
2. Cerrar sesión.
3. Mantener la sesión abierta mientras se trabaja; que se cierre sola tras 60 minutos sin actividad.
4. Olvidé mi contraseña: pedir un enlace y definir una nueva.
5. El administrador crea una cuenta; la persona recibe la invitación y define su contraseña.
6. El administrador cambia el rol o el nombre de alguien.
7. El administrador desactiva o reactiva una cuenta.
8. El administrador reenvía la invitación o envía un enlace de contraseña.
9. El administrador cierra todas las sesiones de alguien (por ejemplo, un equipo perdido).
10. Cualquier persona ve su perfil y cambia su contraseña.
11. El despliegue restablece la cuenta administradora si perdió el rol, quedó desactivada o se olvidó la contraseña.

## 6. Entidades RiC involucradas

Ninguna entidad archivística. Las cuentas no son `Agent` de RiC: son personas del equipo que *trabajan* el fondo, no agentes *del* fondo.

El vínculo con RiC está en la auditoría: cada entidad que se cree después llevará quién la creó o validó (`creado_por_id`), y eso sale de aquí.

## 7. Relaciones RiC involucradas

Ninguna. El catálogo curado de relaciones RiC-R (`app/models/enums.py`, `CODIGO_RELACION_RIC`) se incorporó ya al código, tomado del andamiaje; lo usarán descripción, vocabularios y preservación.

## 8. Funcionalidades

- **Inicio de sesión** con correo y contraseña:
  - el mensaje de error es el mismo si el correo no existe, si la contraseña es incorrecta, si la cuenta está desactivada o si aún no se definió contraseña;
  - tras 5 intentos fallidos en 15 minutos, el correo queda bloqueado 15 minutos (también para correos que no existen, para no revelar cuáles sí).
- **Sesión:**
  - token de acceso JWT de 15 minutos;
  - renovación con una galleta HttpOnly, que se rota en cada uso;
  - cierre por inactividad (60 minutos) o por el máximo absoluto (10 horas);
  - revocación inmediata por el administrador.
- **Recuperación:**
  - la respuesta es idéntica exista o no el correo;
  - el enlace sirve una vez y vence en 30 minutos; solo sirve el último pedido;
  - máximo 5 solicitudes por hora por dirección IP;
  - al restablecer, se cierran todas las sesiones de la cuenta.
- **Invitación:** el enlace es de un solo uso y vence en 72 horas. El administrador nunca conoce ni define la contraseña.
- **Reglas de contraseña**, visibles mientras se escribe y verificadas otra vez en el servidor:
  - al menos 10 caracteres;
  - al menos una letra y al menos un número;
  - no puede ser una contraseña común;
  - no puede contener la parte inicial del correo.
- **Gestión de usuarios:** listado filtrable por nombre o correo, rol y estado; crear, editar nombre o rol, desactivar o reactivar, reenviar enlace, cerrar sesiones. Protecciones:
  - nadie cambia su propio rol ni se desactiva a sí mismo;
  - no se puede dejar el sistema sin administrador activo.
- **Mi perfil:** los datos son de solo lectura. El cambio de contraseña pide la actual y cierra las demás sesiones.
- **Correo de prueba**, para verificar la configuración.
- **Autorización por rol:** una dependencia única, `acceso_modulo`, que usarán todos los módulos.

## 9. Flujos

**Invitación**

1. El administrador llena nombre, correo y rol y pulsa «Crear usuario y enviar invitación».
2. Llega el correo con el enlace `/acceso/<token>`.
3. La persona abre el enlace, ve su nombre y define la contraseña (con las reglas visibles).
4. Queda en «Iniciar sesión» con el aviso «Su contraseña quedó definida».

Si el correo no está configurado o falla, el administrador ve el enlace **una sola vez**, con el botón «Copiar», y lo entrega por otro medio.

**Recuperación**

1. «Olvidé mi contraseña» → la persona escribe su correo.
2. Aparece siempre el mismo mensaje.
3. Si la cuenta existe, llega el enlace de 30 minutos.
4. La persona define la contraseña nueva, se cierran sus sesiones y vuelve a «Iniciar sesión».

Si el correo no está configurado, la solicitud aparece en «Usuarios» como «Pidió recuperar contraseña», y el administrador le envía el enlace desde allí.

**Sesión**

1. Al ingresar se obtienen el token de 15 minutos (en memoria) y la galleta de renovación.
2. Cuando el token vence, la interfaz lo renueva sola y repite la petición.
3. Tras 60 minutos sin actividad, la sesión se cierra y queda el evento de cierre por expiración.
4. Al recargar la página, la sesión se recupera con la galleta.

## 10. Pantallas

| Ruta | Pantalla | Quién |
|---|---|---|
| `/ingresar` | Iniciar sesión | Sin sesión |
| `/recuperar` | Recuperar contraseña | Sin sesión |
| `/acceso/:token` | Definir contraseña (invitación o recuperación) | Quien tenga el enlace |
| `/usuarios` | Gestión de usuarios | Administrador |
| `/perfil` | Mi perfil | Cualquier rol |

## 11. UX/UI

- **Diseño:** según el mockup «Sistema RIC · Acceso» y el sistema de diseño del consolidado:
  - Source Serif 4 para títulos e Inter para el resto;
  - tarjeta centrada, sin barra lateral, para las pantallas de acceso;
  - barra lateral fija con grupos «Trabajo archivístico» y «Sistema»;
  - tarjetas de 12 px con borde sutil y sin sombras;
  - insignias de rol y de estado;
  - avatar de iniciales;
  - formulario desplegable de nuevo usuario.
- **Paleta:** la de tono medio que eligió la autora (fondo `#e6eaf0`, superficie `#f7f8fa`, barra `#1f2b47`, acento azul `#2f5fd0`), en lugar de la terracota del documento. Los colores semánticos siguen el documento: verde (correcto), naranja (advertencia), rojo (error), azul grisáceo (procesos) y morado (agentes). Hay tema oscuro automático.
- **Barra lateral:** solo muestra los módulos ya construidos. Hoy es «Usuarios» para el administrador; cada módulo se suma al entregarse, sin pantallas vacías ni «en construcción».
- **Topbar:** el selector «Fondo histórico activo» del mockup aparecerá con el módulo de ingesta, cuando existan fondos.
- **Móvil:** sin desplazamiento horizontal a 390 px.

## 12. Modelo de datos

| Tabla | Campos clave | Nota |
|---|---|---|
| `usuarios` | id (UUID), nombre, correo (único, minúsculas), rol, activo, contrasena_hash (bcrypt, vacía hasta aceptar la invitación), contrasena_cambiada_en, creado_por_id | Nunca se borra; se desactiva |
| `sesiones` | id, usuario_id, huella_renovacion (SHA-256), iniciada_en, ultima_actividad, vence_en, cerrada_en, motivo_cierre, ip, navegador | Alimenta horas conectadas y días trabajados (auditoría) |
| `tokens_un_uso` | id, usuario_id, tipo (invitación o recuperación), huella (SHA-256), vence_en, usado_en, anulado_en | El token en claro solo existe en el enlace |
| `registro_auditoria` | id, fecha, usuario_id, modulo, accion, entidad_tipo, entidad_id, valor_anterior (JSONB), valor_nuevo (JSONB), detalle, ip | **Solo anexar:** un disparador de PostgreSQL rechaza UPDATE, DELETE y TRUNCATE |

Migración: `alembic/versions/0001_autenticacion_y_auditoria.py`.

## 13. API

Todas bajo `/api/auth`. Los nombres son los del prompt; `contraseña` va sin tilde en la URL.

| Método y ruta | Acceso | Qué hace |
|---|---|---|
| `POST /login` | Público | Correo y contraseña → token JWT, rol y galleta de renovación |
| `POST /refresh` | Galleta | Token nuevo y galleta rotada |
| `POST /logout` | Galleta | Cierra la sesión |
| `POST /recuperar` | Público | Siempre responde igual; envía el enlace si la cuenta existe |
| `GET /token/{token}` | Público | Dice si un enlace sigue vigente y de quién es |
| `POST /recuperar/{token}` | Público | Define la contraseña (invitación o recuperación) |
| `GET /perfil` | Sesión | Datos propios |
| `PATCH /perfil/contrasena` | Sesión | Cambia la propia contraseña (pide la actual) |
| `GET /usuarios` | Administrador | Listado con filtros `q`, `rol`, `activo` |
| `POST /usuarios` | Administrador | Crea la cuenta y envía la invitación |
| `PATCH /usuarios/{id}` | Administrador | Nombre, rol o estado |
| `POST /usuarios/{id}/enlace` | Administrador | Reenvía la invitación o un enlace de contraseña |
| `POST /usuarios/{id}/cerrar-sesiones` | Administrador | Revoca las sesiones abiertas |
| `POST /correo/prueba` | Administrador | Correo de prueba a la propia cuenta |

Documentación interactiva: `/api/docs`.

## 14. Uso de IA

No aplica.

## 15. Seguridad

- **Contraseñas:** bcrypt (12 rondas) vía passlib. Nunca se guardan en claro, nunca van a registros, nunca salen en una respuesta (hay una prueba que lo verifica).
- **Tiempo de respuesta:** el inicio de sesión tarda lo mismo exista o no el correo, porque siempre compara contra un hash señuelo.
- **Token de acceso:** vive solo en la memoria de la página, no en `localStorage`.
- **Galleta de renovación:** HttpOnly, `SameSite=Strict` y limitada a `/api/auth`. Con HTTPS es además `Secure`.
- **Rotación:** si alguien presenta un secreto de renovación ya usado, se cierra la sesión (motivo «reutilizacion_token»).
- **Rol:** se lee de la base de datos en cada petición. Un cambio de rol rige desde la petición siguiente, sin esperar a que venza el token.
- **Enlaces de correo:** se arman con `RICORA_URL_PUBLICA` y no con el encabezado `Host`, para que nadie pueda hacer que el sistema envíe enlaces hacia otro servidor.
- **Límites por IP:** la IP del cliente solo se toma del proxy cuando la aplicación está detrás de Caddy, para que no se puedan saltar los límites falsificando la IP.
- **Cabeceras:** `X-Content-Type-Options`, `X-Frame-Options: DENY` y `Referrer-Policy: no-referrer`.
- **Riesgo aceptado:** sin nombre de dominio, el sistema funciona por HTTP en la dirección numérica, y las contraseñas viajan sin cifrar por la red. No se deben cargar documentos sensibles hasta activar HTTPS (`RICORA_DOMINIO`).

## 16. Auditoría (qué queda registrado)

**Sesión:**

- `inicio_sesion`
- `cierre_sesion`, con motivo:
  - voluntario;
  - expiración, con la hora de la última actividad real;
  - revocada por el administrador;
  - cambio de contraseña;
  - cuenta desactivada;
  - reutilización de token.

**Seguridad:**

- `ingreso_fallido`
- `ingreso_bloqueado`
- `solicitud_recuperacion`
- `contrasena_definida`
- `contrasena_cambiada`

**Administración:**

- `usuario_creado`
- `usuario_editado`, con valor anterior y nuevo
- `usuario_desactivado`
- `usuario_reactivado`
- `enlace_enviado`
- `sesiones_revocadas`
- `cuenta_administradora_restablecida`, cuando lo hace el despliegue, con usuario vacío porque lo hace el sistema

El evento se guarda en la misma transacción que la acción: no puede haber acción sin evento, ni evento de algo que no ocurrió.

## 17. Interoperabilidad

- Autenticación estándar: OAuth2 *bearer* con JWT HS256, y documentación OpenAPI en `/api/openapi.json`.
- Correo por SMTP estándar: sirve con cualquier proveedor (Gmail o el relevo SMTP de un servicio transaccional) sin cambiar código.

## 18. Normativa aplicable

- **Ley 1581 de 2012** (protección de datos personales): solo se guardan nombre, correo y rol, lo mínimo para operar. No hay autorregistro. Una cuenta desactivada conserva su trazabilidad.
- **Ley 1712 de 2014** (transparencia): la trazabilidad inalterable permite rendir cuentas de quién hizo qué.
- **Acuerdo 006 de 2014 del AGN y NTC-ISO 15489:** integridad y trazabilidad de las acciones sobre los documentos, mediante un registro de solo anexar.

## 19. Arquitectura

- **Monolito modular:** FastAPI (API bajo `/api`) y React + Vite + TypeScript (interfaz compilada que sirve el mismo proceso), sobre PostgreSQL 16, con Docker Compose y Caddy opcional para HTTPS.
- **Consumo en el servidor:** 66 MB la aplicación y 42 MB la base de datos, medido en contenedor.
- **CI:** cada cambio corre las pruebas y la compilación de la interfaz, y solo si pasan se despliega.

### Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Envío de correo transaccional | (a) Proveedor transaccional por API (Brevo, Resend); (b) SMTP directo desde un servidor propio de correo; (c) SMTP autenticado contra una cuenta existente (Gmail con contraseña de aplicación), configurable | **(c)**, con el código SMTP genérico | Sistema académico de un solo fondo y pocos correos al mes. No exige dominio propio (Resend sí). Es gratis. Si Gmail bloquea, basta cambiar las variables al relevo SMTP de Brevo, sin tocar código. (b) terminaría en spam: el Droplet no tiene reputación de envío | Gmail limita unos 500 envíos al día y puede pedir revalidar. Sin correo configurado, el enlace se le muestra una vez al administrador |
| Vigencia de la sesión | Token largo de 8 h; token de 15 min con renovación; sesión de servidor sin JWT | **Token de 15 min, renovación rotativa, cierre por 60 min de inactividad o 10 h de máximo** | El prompt exige JWT de expiración corta con renovación. Una hora de inactividad no interrumpe la lectura de un documento y cierra un equipo olvidado. 10 h cubren una jornada | Una galleta robada sirve hasta el primer uso legítimo siguiente (la rotación la delata) |
| Revocación antes de que venza el token | Lista negra de tokens; versión de token en el usuario; **sesión en base de datos** | **Sesión en base de datos** | El token lleva el id de la sesión, y cada petición comprueba que siga abierta. Revocar es cerrar una fila, con efecto inmediato. La misma tabla da las horas conectadas para auditoría | Una consulta extra por petición, despreciable con un equipo pequeño |
| Vigencia del enlace de recuperación | 15 min; 30 min; 1 h | **30 min** (el consolidado dice «media hora») | Da tiempo a que llegue el correo y a abrirlo, sin dejar un enlace útil por horas | Si el correo tarda más, se pide otro |
| Vigencia de la invitación | 30 min; 72 h; 7 días | **72 h** | Una persona nueva puede no revisar el correo el mismo día. Es de un solo uso y se anula al reenviar | Un enlace de invitación interceptado sirve hasta 3 días |
| Librería JWT | python-jose; **PyJWT** | **PyJWT** | Mantenida activamente; python-jose lleva años sin versiones | Ninguno relevante |
| Cierre de sesiones vencidas | Tarea periódica con Celery; **cierre perezoso** (en cada ingreso y renovación, y al usar un token de una sesión vencida) | **Perezoso** | Sin Celery todavía, y con un equipo pequeño siempre hay un ingreso que barre las vencidas. El cierre registra la hora de la última actividad, no la del barrido, así que las horas no se inflan | Si nadie ingresa en días, el evento de cierre se escribe tarde, pero con la hora correcta |
| Servir la interfaz | Contenedor nginx aparte (andamiaje); **el mismo FastAPI** | **Mismo proceso** | Ahorra un contenedor en 2 GB | Archivos estáticos algo menos eficientes que nginx, irrelevante con pocos usuarios |
| Imagen de base de datos | Apache AGE ya; **PostgreSQL 16 (Debian)** ahora | **PostgreSQL 16** | AGE no se usa en este módulo; su tabla de decisión va con descripción, cuando haya grafo que consultar. Se elige Debian, la misma base de la imagen de AGE, para poder cambiar de imagen sin migrar datos | Si AGE se confirma, se cambia la imagen (misma versión mayor) |

## 20. Código (dónde vive, cómo se organiza)

```
app/
  core/config.py        configuración por variables de entorno
  core/seguridad.py     bcrypt, JWT, reglas de contraseña, secretos
  core/permisos.py      roles, matriz, dependencias usuario_actual / acceso_modulo
  core/correo.py        envío SMTP y plantillas
  models/               usuario, sesion, token_acceso, auditoria, enums (RiC)
  servicios/auditoria.py  registrar(): única función de auditoría
  servicios/sesiones.py   abrir, renovar, cerrar, cerrar_vencidas
  servicios/enlaces.py    enlaces de un solo uso
  routers/auth.py       rutas del módulo
  cli.py                cuenta-administradora (despliegue)
alembic/                migraciones
frontend/src/           React: lib/ (api, sesion, reglas), components/, pages/
tests/                  pytest contra PostgreSQL real
```

## 21. Pruebas

50 pruebas en `tests/test_autenticacion.py`, contra PostgreSQL con las migraciones reales. Cada prueba corre en una transacción que se revierte al final.

- **Ingreso:**
  - correcto;
  - mensaje genérico idéntico para correo inexistente y contraseña errada;
  - cuenta desactivada;
  - cuenta sin contraseña;
  - bloqueo, también para correos inexistentes;
  - ninguna respuesta expone el hash.
- **Sesión:**
  - sin token o con token falso;
  - token vencido y renovación;
  - rotación y reutilización de un secreto viejo;
  - cierre voluntario con evento;
  - expiración por inactividad con la hora de la última actividad;
  - barrido de sesiones vencidas;
  - revocación inmediata por el administrador.
- **Recuperación:**
  - respuesta idéntica exista o no el correo;
  - un solo uso;
  - vencimiento a los 30 minutos;
  - solo sirve el último enlace;
  - cierre de sesiones;
  - reglas de contraseña;
  - límite por hora con respuesta idéntica;
  - solicitud visible para el administrador sin correo configurado.
- **Invitación:**
  - flujo completo;
  - el administrador nunca conoce la contraseña;
  - enlace mostrado una vez sin correo;
  - correo duplicado;
  - reenvío que anula el anterior.
- **Gestión:**
  - solo el administrador administra (probado con los otros 3 roles);
  - filtros;
  - cambio de rol auditado con valor anterior y nuevo;
  - desactivar y reactivar;
  - nadie cambia su propio rol por ningún endpoint;
  - nadie se desactiva a sí mismo;
  - perfil y cambio de contraseña.
- **Permisos:**
  - una prueba por cada uno de los 4 roles contra lectura y escritura (GET, POST, PATCH, DELETE) de cada módulo;
  - el revisor no escribe en ningún módulo;
  - sin sesión, nada responde;
  - el rol se lee de la base de datos y no del token.
- **Barrido de rutas:** toda ruta no pública de la aplicación exige sesión. Se comprobó que la prueba falla si se agrega una ruta desprotegida.
- **Auditoría:** UPDATE, DELETE y TRUNCATE sobre el registro fallan por el disparador.
- **Cuenta administradora del despliegue:** creación, restablecimiento y respaldo con el usuario anterior.

**Verificación visual** con navegador real: inicio de sesión, error, recuperación, invitación con enlace mostrado, desactivación, edición, menú, perfil, móvil a 390 px y tema oscuro. En el mismo recorrido se probó de extremo a extremo: invitar, definir contraseña, ingresar, redirigir por rol y recuperar la sesión al recargar.

## 22. Criterios de aceptación

| Criterio (prompt §10–11) | Cumple |
|---|---|
| Ingreso correcto y fallido con el mismo mensaje genérico | ✓ |
| Cuenta desactivada no ingresa con contraseña correcta | ✓ |
| Recuperación responde igual exista o no el correo; el token funciona una vez y deja de funcionar al vencer | ✓ |
| Solo el administrador crea, edita o desactiva | ✓ |
| Nadie cambia su propio rol por ningún endpoint | ✓ |
| Cada rol recibe exactamente sus permisos en cada módulo (una prueba por rol) | ✓ (sobre la dependencia que usarán los módulos; ver nota) |
| El revisor no escribe en ningún módulo | ✓ |
| Decisión de correo y las dos vigencias documentadas antes de implementar | ✓ (§19) |
| El alcance del revisor queda marcado como provisional | ✓ (encabezado y §4) |

**Nota honesta:** los módulos operativos todavía no existen. La matriz de permisos se prueba sobre la misma dependencia `acceso_modulo` que usará cada router, con una ruta de lectura y otras de escritura por módulo. Además, la prueba de barrido obliga a que cualquier ruta que se agregue exija sesión. Cuando cada módulo se construya, su propia prueba repetirá la matriz sobre sus rutas reales.

## 23. Evidencia concreta de aplicación de RiC

Este módulo no crea entidades RiC. Lo que aporta a RiC es verificable así:

1. **Catálogo curado ya en el código:** 32 códigos RiC-R (`CODIGO_RELACION_RIC` en `app/models/enums.py`), con su número oficial (por ejemplo `has_creator` RiC-R027, `migrated_into` RiC-R015). Lo usarán los módulos siguientes.
2. **Base de la procedencia del trabajo descriptivo:** cada acción deja, en un registro que la base de datos impide alterar, quién la hizo y los valores anteriores y nuevos. Cuando descripción publique un Record Resource, esa traza permitirá distinguir lo que propuso el motor (que en RiC-CM puede modelarse como `Mechanism`, RiC-E13) de lo que validó una persona.

---

## Ampliación · Roles configurables (a pedido de la autora)

**Qué cambió.** Los roles ya no son una lista fija en el código: viven en la tabla `roles` (migración `0004_roles.py`), y la columna `usuarios.rol` apunta a ella. Ninguna cuenta perdió su rol en la migración.

**Roles que vienen creados:**

| Rol | Tipo | Referencia en sistemas archivísticos | Acceso |
|---|---|---|---|
| Administrador | Base, no se modifica | Administrador (AtoM, ArchivesSpace, Archivematica) | Todo, más usuarios, roles y configuración |
| Archivista | Base, no se modifica | — (rol del diseño) | Trabaja en los cinco módulos; su auditoría |
| Revisor | Base, no se modifica | — (provisional) | Consulta los cinco módulos; su auditoría |
| Consulta | Base, no se modifica | Usuario autenticado / investigador (AtoM) | Solo el catálogo |
| Coordinador de archivo | De referencia, ajustable | Repository manager (ArchivesSpace), Editor (AtoM) | Trabaja en todo; auditoría de todo el equipo; no administra usuarios |
| Auxiliar de digitalización e ingesta | De referencia, ajustable | Captura/producción (Modelo SGDEA), Basic data entry (ArchivesSpace) | Trabaja en ingesta; consulta descripción |
| Descriptor / catalogador | De referencia, ajustable | Contributor (AtoM), Advanced data entry (ArchivesSpace) | Trabaja en descripción, vocabularios e instrumentos; consulta ingesta y preservación |
| Responsable de preservación digital | De referencia, ajustable | Manager (Archivematica); funciones OAIS de planeación de la preservación | Trabaja en preservación; consulta ingesta, descripción e instrumentos |
| Auditor | De referencia, ajustable | Auditoría / control interno (Modelo de requisitos SGDEA) | Consulta todo; auditoría de todo el equipo |

**Niveles de acceso por módulo:**

- Ingesta, descripción, vocabularios, instrumentos y preservación: **sin acceso / consultar / trabajar**. Trabajar incluye consultar.
- Catálogo: **sin acceso / consultar**.
- Auditoría: **sin acceso / solo lo propio / todo el equipo**.

**Reglas:**

- La gestión de usuarios, roles y configuración es siempre y solo del Administrador. Así ningún rol creado puede darse a sí mismo más poder.
- Los cuatro roles base no se modifican.
- Un rol no se borra: se desactiva, y solo si ninguna cuenta activa lo tiene.
- Un cambio de permisos rige desde la petición siguiente de cada persona.
- Crear y editar roles queda en auditoría (`rol_creado`, `rol_editado`, con el valor anterior y el nuevo).

**Decisión**

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Roles libres frente a los cuatro del documento | Solo los 4 del prompt; roles libres sin plantilla; **4 base fijos, perfiles archivísticos de referencia y roles propios** | La tercera | La autora pidió crear roles y que correspondan a los de los sistemas archivísticos. Los 4 del diseño siguen intactos | Una persona puede crear un rol con más acceso del debido: se mitiga porque solo el Administrador crea roles y todo queda auditado |

**Pruebas:** 6 nuevas (101 en total):

- vienen los roles base y los de referencia;
- un rol creado rige sus permisos, incluso al cambiarlos;
- los roles base no se modifican;
- se rechazan niveles inválidos y nombres repetidos;
- no se desactiva un rol en uso;
- solo el Administrador gestiona roles.

---

## Cierre transversal · con los siete módulos construidos

Cuando se entregó este módulo solo existían ingesta y descripción. La matriz de permisos se había probado con rutas de ensayo, una de lectura y una de escritura por módulo. Ahora que existen los siete módulos, se agregaron pruebas **contra los endpoints reales** (`tests/test_permisos_reales.py`):

- **Cada uno de los cuatro roles** contra un endpoint real de lectura y uno de escritura de cada módulo: ingesta, descripción, vocabularios, instrumentos, preservación, auditoría (propia y panel) y usuarios. Se exige exactamente esta tabla:

| Rol | Trabajo (5 módulos) | Catálogo de instrumentos | Auditoría propia | Panel consolidado | Usuarios |
|---|---|---|---|---|---|
| Administrador | leer y escribir | ✓ | ✓ | ✓ | ✓ |
| Archivista | leer y escribir | ✓ | ✓ | ✗ | ✗ |
| Revisor (**provisional**) | solo leer | ✓ | ✓ | ✗ | ✗ |
| Consulta | ✗ | ✓ (única puerta) | ✗ | ✗ | ✗ |

- **El revisor contra todas las rutas que modifican algo** en la aplicación real, sin excepción. La prueba recorre la aplicación y encuentra más de 30 rutas POST, PUT, PATCH y DELETE de los siete módulos; todas le responden 403. Si un módulo futuro agrega una ruta de escritura sin la dependencia de permisos, esta prueba falla sola.
- **Sin sesión**, todos los endpoints de los siete módulos responden 401.

**Cierre por expiración sin intervención.** Antes, las sesiones vencidas se cerraban (con su evento) solo cuando alguien entraba o renovaba la sesión. Ahora, además, el trabajador en segundo plano las cierra cada minuto. Así el evento de cierre por expiración existe aunque nadie vuelva a entrar, y el panel consolidado de auditoría no muestra sesiones «en curso» que ya terminaron.

**Sigue pendiente de su validación:** el alcance del rol **revisor** es **provisional**. Hoy tiene solo lectura en los cinco módulos de trabajo y su propia auditoría. No publica, no aprueba, no fusiona ni migra nada.
