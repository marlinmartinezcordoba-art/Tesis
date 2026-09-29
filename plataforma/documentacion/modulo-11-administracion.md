# Módulo 11 · Administración y seguridad

Este documento sigue la estructura de 23 puntos de la sección 5 del prompt de desarrollo. El alcance lo fijan la historia de usuario 11 y los requisitos RF-M11-01 a RF-M11-03. La pantalla toma como referencia visual la administración de usuarios de TribuIA, que aportó la autora.

## 1. Propósito
Que el administrador decida quién entra a RICORA y con qué rol, y qué inteligencia artificial alimenta el motor de análisis. Además, que ninguna acción del sistema quede al alcance de un rol que no le corresponde.

## 2. Auditoría (qué se revisó antes de construirlo)
Existía una versión de este módulo, construida antes de aplicar la metodología y nunca revisada. Estos fueron los hallazgos:

| Aspecto | Hallazgo | Requisito afectado |
|---|---|---|
| Roles | Solo se podían asignar tres; el administrador era la cuenta superusuario, que no se podía asignar ni retirar desde la pantalla | RF-M11-01 («exactamente uno de los cuatro roles») |
| Invitación | El administrador escribía la contraseña inicial y el correo la enviaba en texto plano | RF-M11-01 y seguridad |
| Edición | No se podía cambiar el nombre ni el correo, solo el rol | RF-M11-01 («puede editarse») |
| Proveedor de IA | Se guardaba **antes** de probar la conexión; la prueba solo era obligatoria para activarlo | RF-M11-02 («no permite guardarlo sin probar») |
| Control por rol | Cada vista tenía su decorador, pero ninguna prueba recorría **todas** las rutas | RF-M11-03 («sin excepción») |
| Último administrador | Nada impedía quedar sin administrador si se asignaba el rol | Continuidad del servicio |
| Mensaje de acceso denegado | Decía «requiere el rol ;» (vacío) en las rutas solo de administrador | Claridad |
| Pantalla | Formularios en línea por fila, sin buscador ni filtros | Historia 11, UX |
| Estado de los módulos | Pestaña técnica del desarrollo dentro del sistema | Retirada a pedido de la autora |

## 3. Problema que resuelve
Sin este módulo, el alta de personas pasaba por la consola del servidor y la configuración de la IA por variables de entorno. Además, el administrador conocía la contraseña de cada persona, y nada garantizaba que una ruta nueva quedara protegida por rol.

## 4. Usuarios
- **Administrador** (rol principal): gestiona cuentas, proveedores de IA, parámetros, auditoría y eliminados.
- **Persona invitada:** usa el enlace de invitación para crear su propia contraseña.
- **Archivista, revisor y consulta:** no entran a este módulo. Su intento queda registrado como acceso denegado.

## 5. Casos de uso
- Crear una cuenta con nombre, correo, nombre de usuario y uno de los cuatro roles.
- Recibir la invitación y crear la propia contraseña.
- Editar el nombre, el correo y el rol.
- Desactivar y reactivar una cuenta.
- Restablecer el acceso o reenviar la invitación.
- Cerrar las sesiones abiertas de una cuenta.
- Buscar y filtrar cuentas.
- Agregar un proveedor de IA: probar la conexión y luego guardar, y dejarlo o no como fuente del motor.
- Volver a probar, activar, dejar como respaldo o retirar un proveedor.
- Ajustar los parámetros. Consultar la auditoría y restaurar eliminados (estas dos pantallas vienen del M0).

## 6. Entidades RiC involucradas
- **Mechanism (RiC-E13):** cada proveedor y versión de modelo que el administrador activa se convierte, al primer análisis, en un agente Mecanismo del grafo, con sus características técnicas (RiC-A41).
- **Person (RiC-E08):** es la figura con que RiC describe a quien actúa. Las cuentas de usuario no se publican como entidades del grafo (ver la decisión en el punto 19), pero su nombre queda como agente de cada evento de descripción.

## 7. Relaciones RiC involucradas
Ninguna relación nueva. El módulo decide qué Mecanismo propone relaciones (proveedor activo) y qué Personas pueden confirmarlas (roles). Cada propuesta conserva el identificador de su Mecanismo, y cada decisión humana conserva el nombre de su autor en el EventoRiC.

## 8. Funcionalidades
- **Cuatro roles, exactamente uno por cuenta.** Administrador = `is_superuser`, archivista = `is_staff`, revisor = grupo «revisor» y consulta = ninguna marca. Asignar un rol fija o quita las tres marcas a la vez, así nunca quedan dos roles.
- **Invitación con enlace de un solo uso.** La cuenta nace sin contraseña utilizable. El enlace (token de Django) deja de servir en cuanto se crea la contraseña y vence a los 3 días. Si el servidor tiene correo, se envía solo; si no, se le entrega el enlace al administrador una sola vez, para que lo haga llegar.
- **Protección del último administrador.** No se le puede quitar el rol ni desactivar mientras sea el único administrador activo.
- **Nadie se desactiva a sí mismo ni restablece su propio acceso.**
- **Restablecer acceso.** La contraseña actual deja de servir, se cierran las sesiones abiertas y la persona recibe un enlace nuevo.
- **Proveedores de IA.** La prueba de conexión se hace **antes** de guardar. Si sale bien, el servidor entrega un comprobante firmado con la huella de proveedor, modelo y clave, válido 15 minutos. «Guardar» exige ese comprobante: si los datos cambiaron o el comprobante venció, se niega. La clave solo se muestra enmascarada (sus últimos 4 caracteres).
- **Pantalla por pestañas** (desde el menú lateral): Usuarios y roles · Proveedores de IA · Parámetros · Auditoría · Eliminados.
- **Ayuda de la ambulancia** propia de cada pestaña.

## 9. Flujos
**Alta de una cuenta:**
1. Usuarios y roles → «Nuevo usuario».
2. Nombre y correo. El nombre de usuario se sugiere a partir del correo.
3. Elegir el rol: cada opción explica lo que permite.
4. «Guardar»: la invitación se envía por correo, o aparece el enlace para copiarlo.
5. La persona abre el enlace, crea su contraseña y entra por el ingreso.

**Proveedor de IA:**
1. Proveedores de IA → «Agregar proveedor».
2. Elegir el proveedor y pegar la clave.
3. «Probar conexión»: punto verde y «Guardar» habilitado.
4. «Guardar»: queda activo como fuente del motor.

Si se cambia un dato después de probar, el punto vuelve a gris y «Guardar» se deshabilita.

## 10. Pantallas
- `/admin/usuarios/?pestana=usuarios|proveedores|parametros|auditoria|eliminados`.
- `/ric/invitacion/<uid>/<token>/`: crear contraseña. Tiene el estilo del ingreso y es pública, porque el enlace es la credencial.

## 11. UX/UI
Referencia: TribuIA.
- **Encabezado:** título de la pestaña con su explicación y el botón principal a la derecha («Nuevo usuario», «Agregar proveedor»).
- **Filtros en el navegador:** buscador por nombre, usuario o correo; menú de rol; botón «Solo activos»; contador de cuentas.
- **Tabla:** iniciales con el color del rol, nombre y correo, insignia de rol, estado (Activo / Invitación pendiente / Inactivo), último acceso («hace 3 horas», «Nunca») y botón «Editar».
- **Ventanas centradas** (`<dialog>` nativo, Escape cierra) para crear, editar y agregar proveedor. Las acciones de riesgo piden confirmación.
- **Estado de la prueba de conexión:** indicador de estado (gris, naranja mientras prueba, verde o rojo) con el mensaje real del proveedor.

## 12. Modelo de datos
Sin tablas nuevas:
- Se usan `auth.User` (con `set_unusable_password` para la cuenta invitada), el grupo «revisor» y `ProveedorIAConfig` (`prueba_exitosa`, `mensaje_prueba` y `ultima_prueba` quedan fijados al guardar).
- El comprobante de la prueba no se guarda: es un valor firmado con `SECRET_KEY` que viaja en el formulario.

## 13. API
- `POST /admin/usuarios/proveedores/probar/` (solo administrador) responde JSON `{ok, mensaje, comprobante}`. Sin sesión devuelve 401; sin rol, 403.
- El resto son formularios POST con CSRF.

## 14. Uso de IA
El módulo no usa IA: la configura. La prueba de conexión hace una llamada mínima real al proveedor, por ejemplo «Responde únicamente: OK» con 5 tokens en Gemini, o la carga del modelo local.

## 15. Seguridad
- Todas las vistas llevan `requiere_rol()` (solo administrador). El punto JSON usa `requiere_rol_api()`.
- El administrador nunca conoce contraseñas ajenas.
- El token de invitación se invalida con el uso.
- Validadores de contraseña de Django en la invitación.
- Correo único por cuenta; nombre de usuario sin espacios.
- Claves de API enmascaradas en pantalla y en la auditoría.
- Comprobante de prueba firmado, atado a los datos y con vencimiento.
- Último administrador protegido.

## 16. Auditoría (qué queda registrado)
- **Registro automático de cada `User` guardado,** con los valores antes y después (nombre, correo, activo, marcas de rol). La contraseña queda como `***`.
- **Cambio de rol:** `{rol: anterior → nuevo}`.
- **Invitación:** si salió por correo o si el enlace se entregó al administrador, y cuándo la persona creó su contraseña.
- **Cada prueba de conexión,** exitosa o fallida, con el mensaje del proveedor.
- **Accesos denegados por rol,** con la ruta y el rol.
- **Sesiones revocadas.**

## 17. Interoperabilidad
El Mecanismo (RiC-E13) que nace del proveedor activo se exporta en RiC-O con el resto del grafo (M9). Así, quien reciba los datos sabe qué modelo propuso cada relación.

## 18. Normativa aplicable
- **Ley 1581 de 2012** (datos personales): mínimo necesario (nombre y correo), y el administrador no conoce credenciales.
- **Ley 1712 de 2014:** el acceso por rol sostiene la clasificación de la información.
- **Acuerdo 003 de 2015 del AGN (SGDEA):** usuarios, roles, trazabilidad de acciones y conservación de la cuenta desactivada con su historial.
- **Principio del proyecto:** nada se elimina de forma irreversible. Las cuentas se desactivan y los proveedores se retiran con borrado lógico.

## 19. Arquitectura
| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo se representa el administrador | Grupo «administrador»; `is_superuser` | `is_superuser` | Ya era el rol que «puede todo» en todo el código (`roles.puede`); agregar otro grupo creaba dos fuentes de verdad | Un administrador también entra al panel técnico de Django; es coherente con su rol |
| Contraseña inicial | El administrador la escribe; enlace de invitación | Enlace de un solo uso | El administrador no debe conocer credenciales ajenas (Ley 1581); el correo nunca lleva una contraseña | Sin correo configurado, el enlace se entrega por otro medio; vence en 3 días |
| Correo | Servicio de envío pago; SMTP opcional | SMTP opcional (`EMAIL_HOST`) y, si no hay, el enlace a la vista del administrador | «Trabaja con lo que hay»: sin recursos pagos; nunca se finge un envío | Si el administrador comparte el enlace por un canal inseguro, cualquiera que lo abra primero crea la contraseña; vence en 3 días y solo sirve una vez |
| «No guardar sin probar» | Guardar y exigir prueba solo para activar; probar en el servidor al guardar; comprobante firmado | Comprobante firmado de 15 minutos, con la huella de los datos | Cumple la letra del requisito sin repetir la prueba, que con la IA local puede tardar | Si el proveedor cae en esos 15 minutos, se guarda igual; la prueba se puede repetir desde la tabla |
| Filtros de la tabla | En el servidor; en el navegador | En el navegador | Pocas cuentas; respuesta inmediata al escribir | Con miles de cuentas convendría paginar en el servidor |
| Cuentas en el grafo RiC | Publicar cada usuario como Person; dejarlos fuera | Fuera del grafo público; su nombre queda como agente de cada evento | Una cuenta no es una entidad archivística descrita; publicarla expondría datos personales | — |
| Estado de los módulos | Pestaña en Administración; fuera del sistema | Fuera del sistema | Pedido de la autora: no mostrar residuos del desarrollo | — |

## 20. Código
- `ric/roles.py`: cuatro roles, `DESCRIPCIONES`, `asignar_rol` (exactamente un rol), `es_ultimo_administrador` y `UltimoAdministrador`.
- `ric/invitaciones.py`: `enlace`, `usuario_de`, `pendiente` y `enviar`.
- `ric/vistas_admin.py`: `_validar_usuario`, `_crear_usuario`, `admin_usuario_editar` (editar / desactivar / reactivar / restablecer / cerrar sesiones), `admin_proveedor_probar_nuevo`, `admin_proveedor_agregar` (con comprobante) y las demás acciones de proveedores y parámetros.
- `ric/vistas_acceso.py`: `invitacion`.
- `ric/templates/ric/admin_usuarios.html` e `invitacion.html`.
- `ric/ayuda.py`: guías por pestaña.
- `ric/templatetags/ric_extras.py`: filtro `hace`.
- `docker-entrypoint.sh`: gunicorn con hilos (la plataforma ya no se cuelga con solicitudes lentas).
- `.github/workflows/deploy.yml`: verificación de que RICORA responde tras cada despliegue.

## 21. Pruebas
`tests/test_modulo11_administracion.py` (26 pruebas):
- **Usuarios** (12):
  - solo el administrador administra;
  - alta con cada uno de los cuatro roles y marcas coherentes;
  - enlace entregado una sola vez sin correo;
  - invitación por correo sin contraseña;
  - el enlace crea la contraseña (coincidencia y validadores) y luego deja de servir;
  - enlace alterado o de una cuenta inactiva;
  - siete validaciones al crear;
  - edición auditada;
  - siempre queda un administrador;
  - desactivar y reactivar, pero no a sí mismo;
  - restablecer el acceso cierra las sesiones;
  - tabla con filtros, insignias y ventanas.
- **Proveedores** (10):
  - no se guarda sin prueba;
  - probar y guardar como fuente;
  - una prueba fallida no da comprobante y queda auditada;
  - datos cambiados después de probar;
  - comprobante vencido;
  - el punto de prueba exige administrador (401/403);
  - volver a probar uno guardado;
  - un solo proveedor activo;
  - el proveedor activo alimenta el motor;
  - retirar es borrado lógico.
- **Parámetros** (1): guardar con validación de rangos.
- **RF-M11-03** (3):
  - **se recorren todas las rutas del sistema** (más de 60, por GET y por POST): ninguna responde sin sesión, salvo las públicas a propósito (ingreso, invitación y salida);
  - todas las rutas de Administración niegan el acceso a archivista, revisor y consulta, y queda registrado;
  - matriz rol × pantalla.

Se ajustaron `test_modulo0_seguridad.py` (restablecer sin contraseña escrita por el administrador; edición en lugar de «cambiar rol») y `test_ayuda_e_ingreso.py` (guía por pestaña).

## 22. Criterios de aceptación (historia de usuario 11)
- **Una cuenta nueva queda con exactamente uno de los cuatro roles y puede editarse o desactivarse después (RF-M11-01):** cumplido, con la invitación del paso 3 del flujo.
- **Un proveedor de IA recién agregado no se puede guardar sin probar primero la conexión (RF-M11-02):** cumplido. El servidor lo exige y no depende solo del botón deshabilitado.
- **Toda acción de un usuario autenticado se restringe según su rol, sin excepción (RF-M11-03):** cumplido, y demostrado con la prueba que recorre todas las rutas.

## 23. Evidencia concreta de aplicación de RiC
Al activar, por ejemplo, Gemini con el modelo `gemini-3.5-flash`, el primer análisis crea en el grafo un agente `Mechanism` con identificador `motor:gemini:gemini-3.5-flash` y sus características técnicas (RiC-A41). Cada propuesta de ese análisis guarda `mecanismo_id` en su EventoRiC. En el historial del documento (M7) y en la exportación RiC-O (M9) se ve qué Mecanismo propuso cada relación y qué persona, con qué rol, la confirmó. La configuración de este módulo es la que determina quién es el agente de cada paso de la descripción.

## Qué no hace (y qué pasa en cada error)
- **Borrar cuentas:** no se puede, a propósito. Se desactivan y conservan su historial.
- **Sin correo en el servidor:** lo dice y entrega el enlace; nunca simula el envío. Si el envío falla, muestra el error real y también entrega el enlace.
- **Enlace vencido, usado o alterado:** pantalla «Este enlace ya no sirve», que indica pedir uno nuevo.
- **Proveedor que no responde en la prueba:** muestra el mensaje en lenguaje claro (clave inválida, modelo no disponible, límite de uso, sin conexión) y no habilita «Guardar».
- **Rol del único administrador:** no se puede cambiar; lo explica en la ventana de edición.
- **Autenticación de dos factores e inicio de sesión institucional (LDAP o Microsoft 365):** no están. Son extensiones posibles.
