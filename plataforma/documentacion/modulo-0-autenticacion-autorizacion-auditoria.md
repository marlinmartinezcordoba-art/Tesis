# Módulo transversal 0 · Autenticación, autorización y auditoría

Documentado con la estructura de 23 puntos que exige la sección 5 del prompt de desarrollo. Base de código: RICORA (Django 5.2 + PostgreSQL), el repositorio real y desplegado; decisión registrada en la sección 19.

## 1. Propósito
Que ninguna acción del sistema ocurra sin una persona autenticada, con un rol que la autorice, y que toda acción humana quede registrada con quién, qué, sobre qué, cuándo y con qué valores antes y después. Sin esto ningún criterio de aceptación de los otros módulos es verificable.

## 2. Auditoría (qué se revisó antes de construirlo)
Se verificó el repositorio real contra la sección 3 del prompt. Existían: inicio y cierre de sesión (sesión de servidor), contraseñas con hash PBKDF2, control de rol en todas las vistas (`ric.roles.requiere_rol`), bitácora de preservación encadenada (`EventoRiC`) y versionado de entidades (`VersionRiC`), 480 pruebas. Faltaban: bcrypt, política explícita de expiración y revocación de sesión, bloqueo por intentos fallidos, un registro único de acciones humanas con antes/después, borrado lógico universal (tres borrados físicos: entidad duplicada tras fusión, instanciaciones desde el panel técnico, configuración de proveedor de IA) y el rol "administrador" con ese nombre.

## 3. Problema que resuelve
Cierra el perímetro de seguridad y la trazabilidad de acciones humanas que la Definición de Terminado exige a todo módulo, sin reescribir lo que ya funcionaba.

## 4. Usuarios
Administrador (crea cuentas, asigna roles, revoca sesiones, consulta la auditoría, restaura eliminados), archivista, revisor y consulta (los cuatro roles de la especificación, RF-M11-01).

## 5. Casos de uso
Iniciar y cerrar sesión; intento fallido y bloqueo; acceso denegado por rol; crear, editar, desactivar y reactivar usuario; restablecer contraseña; cerrar sesiones de una cuenta; consultar y exportar la auditoría; eliminar lógicamente y restaurar.

## 6. Entidades RiC involucradas
Ninguna nueva. Todas las entidades RiC (Record Resource, Instantiation, Agent y subtipos, Event/Activity, Rule/Mandate, Date, Place) heredan el borrado lógico; también la forma documental (RiC-A17 como tabla) y las relaciones.

## 7. Relaciones RiC involucradas
Al borrar lógicamente una entidad, sus `RelacionRiC` (cualquier código RiC-R) quedan marcadas con el mismo motivo y desaparecen del grafo; al restaurarla, las relaciones se restauran una a una desde Administración si procede.

## 8. Funcionalidades
- Contraseñas con bcrypt (`BCryptSHA256PasswordHasher`); las existentes se rehashean al siguiente ingreso.
- Sesión de servidor con expiración por inactividad (60 min por defecto, `RICORA_SESION_MINUTOS`), renovada en cada petición, cerrada al cerrar el navegador, cookies `HttpOnly`, `SameSite=Lax` y `Secure` detrás del proxy HTTPS.
- Revocación: al desactivar una cuenta, restablecer su contraseña o por decisión del administrador se cierran todas sus sesiones abiertas.
- Bloqueo: cinco intentos fallidos en quince minutos para un usuario bloquean el ingreso sin comprobar la contraseña.
- Control por rol en todas las pantallas; cada acceso denegado se audita.
- `RegistroAuditoria` con valores antes y después, consulta con filtros y exportación CSV.
- Borrado lógico universal con motivo, papelera y restauración.

## 9. Flujos
Entrar → panel. Fallo ×5 → bloqueo 15 min. Consulta pide /ingesta → mensaje de rol + registro "acceso denegado". Administrador desactiva cuenta → sesiones cerradas → la persona es devuelta a entrar en su siguiente clic. Fusionar duplicado → el duplicado queda en Eliminados → Restaurar.

## 10. Pantallas
`/ric/entrar/` (con mensaje de bloqueo), `/admin/usuarios/` pestañas Usuarios (botón Cerrar sesiones), Auditoría (filtros por usuario, acción, fechas, objeto; CSV) y Eliminados (Restaurar).

## 11. UX/UI
Mensajes en lenguaje claro; el bloqueo dice cuántos intentos y cuánto esperar; la auditoría muestra el diferencial "antes → después" plegado por registro; las contraseñas y claves de API aparecen siempre como `***`.

## 12. Modelo de datos
`RegistroAuditoria(usuario, usuario_nombre, accion, content_type, object_id, objeto_texto, antes, despues, detalle, exitoso, ip, agente_usuario, fecha)`. Mixin `BorradoLogico(eliminado, eliminado_en, eliminado_por, motivo_eliminacion)` con manager por defecto que excluye lo eliminado (`objects`) y `todos` para restaurar. Unicidad del nombre de forma documental solo entre activas (restricción condicional). Migración `0018`.

## 13. API
Rutas de servidor: `POST /ric/entrar/`, `POST /ric/salir/`, `POST /admin/usuarios/<id>/` (acciones cambiar_rol, desactivar, reactivar, restablecer, cerrar_sesiones), `GET /admin/usuarios/?pestana=auditoria|eliminados`, `GET /admin/usuarios/auditoria.csv`, `POST /admin/usuarios/restaurar/`. No hay API JSON pública en este módulo (ver 19).

## 14. Uso de IA
No aplica. El motor de análisis ya está modelado como agente RiC-E13 y sus propuestas llevan proveedor y versión.

## 15. Seguridad
bcrypt, sesión corta y revocable, cookies seguras, CSRF, bloqueo de fuerza bruta, control de rol por vista, auditoría inmutable desde la aplicación, secretos enmascarados. HTTPS lo aporta el proxy del despliegue (pendiente en el servidor, ver 19).

## 16. Auditoría (qué queda registrado)
iniciar_sesion, cerrar_sesion, login_fallido, bloqueo_login, acceso_denegado, crear, modificar (con diferencial), eliminar (con motivo y relaciones arrastradas), restaurar, sesiones_cerradas, cambio de rol. Además siguen `EventoRiC` (documentos, motor, exportaciones) y `VersionRiC` (fotografías de entidades).

## 17. Interoperabilidad
Exportación CSV de la auditoría; la bitácora de preservación sigue disponible por documento.

## 18. Normativa aplicable
OWASP Top 10 (autenticación, control de acceso, registro), Ley 1581 de 2012 (mínima exposición de datos en registros), Acuerdo 003 de 2015 y Ley 594 de 2000 (trazabilidad y no destrucción de la información archivística), ISO 15489 (auditoría del sistema).

## 19. Arquitectura
| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Base de código | Reescribir en FastAPI+React; mantener Django; Django + React | Mantener Django | Los documentos auditaron el andamiaje, no el repositorio real; Django ya tenía autenticación, roles, admin y 480 pruebas | La tabla de arquitectura de la tesis nombra FastAPI/React; se corrige el párrafo |
| Autenticación | JWT + bcrypt; sesión de servidor; OAuth2 | Sesión de servidor + bcrypt | Las pantallas las sirve el mismo servidor; la sesión en base de datos permite revocación inmediata, que JWT no ofrece sin lista de revocación | Si se expone una API a otro sistema, se añade autenticación por token en ese momento |
| Autorización | RBAC; ABAC | RBAC, cuatro roles | Instancia única por entidad | Ninguno relevante |
| Auditoría | Tabla propia; reutilizar EventoRiC | Tabla propia `RegistroAuditoria` + señales de modelo | EventoRiC es bitácora de preservación por documento; las acciones humanas necesitan diferencial y cobertura de todas las entidades | Volumen: la siembra completa genera miles de filas; se acepta, es auditoría |
| Borrado | Físico con confirmación; lógico | Lógico universal | Regla no negociable del proyecto | Datos "eliminados" siguen ocupando espacio; se acepta |

## 20. Código
`ric/auditoria_acciones.py` (middleware, señales, revocación, bloqueo), `ric/vistas_acceso.py` (ingreso), `ric/roles.py`, `ric/models.py` (`BorradoLogico`, `RegistroAuditoria`), `ric/vistas_admin.py` (auditoría, eliminados, sesiones), `ric/templates/ric/admin_usuarios.html`, `ric/templates/ric/login.html`, `config/settings.py`, migración `ric/migrations/0018_*`.

## 21. Pruebas
`tests/test_modulo0_seguridad.py`: login válido e inválido, bloqueo tras cinco intentos, expiración de sesión, revocación al desactivar y al restablecer, acceso sin permiso y con permiso por rol, redirección sin sesión, auditoría de crear/modificar con antes y después, pantalla y CSV de auditoría, borrado lógico en fusión, arrastre de relaciones, unicidad condicional, proveedor de IA. Más las pruebas existentes de roles y administración.

## 22. Criterios de aceptación
RF-M11-01, RF-M11-03 y la sección 7 del prompt: registro solo por administrador; contraseñas nunca en claro ni en registros; expiración corta con renovación; revocación diseñada y probada; control de rol en todas las rutas; auditoría activa desde este módulo; pruebas del flujo completo.

## 23. Evidencia concreta de aplicación de RiC
En Administración → Eliminados, una entidad corporativa fusionada aparece con motivo "Fusionada en «…»"; sus relaciones RiC (por ejemplo R027 "has creator") figuran como eliminadas con el mismo motivo en la auditoría, y al restaurarla vuelve al vocabulario sin perder su historial de versiones. La evidencia no es la etiqueta "RiC" sino que el grafo se cierra y se reabre sin destruir nada.

## Qué no hace (y qué pasa en cada error)
- No autorregistro: `/ric/entrar/` no tiene "crear cuenta".
- No JWT ni API externa.
- No MFA (documentado como mejora futura).
- Bloqueo por usuario, no por IP: un atacante con muchos usuarios no se frena por esta vía (sí queda auditado).
- Un intento contra un usuario inexistente también cuenta y se audita.
- Si la auditoría no puede escribirse (fallo de base de datos), la acción falla: no hay acción sin registro.
