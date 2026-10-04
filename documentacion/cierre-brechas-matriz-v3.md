# Cierre de brechas de la matriz maestra v3.0

Base: la auditoría del 4 de octubre de 2026 (`RICORA_MATRIZ_MAESTRA_REQUISITOS_v3_0_auditada.xlsx`). En esa fecha, de los 51 requisitos, 30 cumplían, 18 eran parciales, 1 no cumplía y 2 no existían.

## Cómo se trabaja

1. **Se cierra por lotes**, del riesgo más alto al más bajo, y cada brecha con su prueba automatizada.
2. **Un requisito pasa a CUMPLE solo con evidencia**: el archivo y la prueba que lo demuestra. Lo que queda pendiente se dice; no se presenta como cerrado.
3. **Cada lote actualiza la matriz**: estado, evidencia y riesgo residual, en la hoja «Cierres».
4. **Cada lote se despliega con el CI en verde.**

## Lote 1 · Seguridad y operación

| Requisito | Antes | Después | Qué se hizo | Evidencia |
|---|---|---|---|---|
| RF-SEC-003 Segundo factor | No existe | Cumple | TOTP (RFC 6238) sin dependencias nuevas, con 8 códigos de respaldo de un solo uso (solo se guardan sus huellas). Un código usado no vuelve a servir. Ingreso en dos pasos con un desafío de 5 minutos que no sirve como token de acceso. Obligatoriedad por rol desde **Usuarios › Roles**; si el rol lo exige, la persona solo entra a Mi perfil hasta configurarlo. El administrador lo restablece si alguien pierde el teléfono, con auditoría | `app/core/doble_factor.py`, `app/routers/auth.py`, migración `0033`, `tests/test_brechas_lote1.py` (vectores del RFC 6238, ingreso en dos pasos, rol obligatorio, restablecimiento) |
| RF-AUD-002 Proteger la auditoría | Parcial | Cumple | Cada evento guarda la huella SHA-256 de su contenido unida a la del anterior, calculada por la base de datos al insertar y bajo un candado. Si alguien desactiva el disparador y altera o borra un evento, la cadena se rompe desde ahí. Ruta `GET /api/auditoria/cadena`. La revisión semanal guarda el sello (último eslabón) y Auditoría muestra si la cadena está íntegra | migración `0032`, `app/servicios/auditoria.py::verificar_cadena`, `tests/test_brechas_lote1.py` (alterar y borrar con el disparador desactivado) |
| RF-OPS-001 Salud, respaldos, métricas | Parcial | Parcial (avanza) | `/api/salud` revisa de verdad la base de datos (con la migración vigente), el almacén (existe, se escribe, espacio libre), el latido del trabajador y el último respaldo probado. Solo la caída de la base da 503; lo demás marca «degradado» con el motivo y no expone datos | `app/servicios/salud.py`, `app/trabajador.py`, `tests/test_brechas_lote1.py::test_salud_dice_que_falta_y_solo_la_base_tumba_el_servicio` |
| NFR-10 Observabilidad | Parcial | Parcial (avanza) | Un monitor externo gratuito puede consultar `/api/salud` sin sesión | ídem |
| NFR-01 Seguridad | Parcial | Parcial (avanza) | Segundo factor y auditoría encadenada | ídem |

### Decisiones del lote 1

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Tipo de segundo factor | SMS; correo; TOTP; llaves físicas (WebAuthn) | TOTP | Gratis, funciona sin red en el teléfono, tiene aplicaciones libres (Aegis, FreeOTP) y no depende de un operador. El SMS es inseguro y cuesta; WebAuthn exige HTTPS y llaves | Perder el teléfono: se resuelve con los códigos de respaldo o con el restablecimiento del administrador |
| Biblioteca para TOTP | pyotp; implementación propia | Implementación propia (unas 40 líneas con `hmac`) | No agrega dependencias a la imagen. Se prueba contra los vectores oficiales del RFC 6238 | Un error de implementación; lo cubren los vectores del RFC |
| Secreto TOTP en la base | Cifrado; en claro | En claro en la columna, nunca devuelto ni auditado | No hay biblioteca de cifrado en la imagen y cifrar con una clave del mismo servidor protege poco: quien lee la base suele leer también la configuración | Robo de la base: el atacante podría generar códigos. Mitigación pendiente: cifrar con una clave externa |
| Obligatoriedad | Fija para administradores; parámetro por rol | Parámetro por rol, vacío por defecto | Cada entidad decide. Encenderlo para el administrador obliga a configurarlo en el siguiente ingreso | Que nadie lo encienda: **recomendación: exigirlo al rol administrador en producción** |
| Quién calcula la cadena | La aplicación; la base de datos | La base de datos (disparador) | Ningún módulo puede olvidarse de encadenar ni hacerlo distinto. El orden se asigna bajo un candado, así que transacciones simultáneas no bifurcan la cadena | Las escrituras de auditoría se hacen de una en una: aceptable para el volumen de un archivo |
| Anclaje externo | Ninguno; servicio de sellado de tiempo; sello en la revisión semanal | Sello en la revisión semanal y visible en Auditoría | Sin costo. Quien revisa anota el sello y queda en la exportación a Excel. Si alguien rehace toda la cadena, el sello anotado deja de coincidir | El dueño de la base podría rehacer la cadena entera entre dos revisiones; el sello anotado fuera lo delata |
| Código HTTP de la salud | 503 ante cualquier falla; solo ante la base | Solo ante la base | Un trabajador detenido o un respaldo atrasado no impiden consultar ni describir. Tumbar el servicio por eso haría más daño | Un monitor que solo mire el código no verá lo «degradado»: debe leer `estado` |

## Lote 2 · Recuperación ante desastres

| Requisito | Antes | Después | Qué se hizo | Evidencia |
|---|---|---|---|---|
| NFR-04 RPO/RTO por escenario | No existe | Cumple | Cinco escenarios con su mecanismo: archivo dañado, error humano, base corrupta, pérdida del servidor y secuestro de datos. Cada uno tiene objetivos de pérdida máxima (RPO) y de tiempo de vuelta (RTO) como parámetros del administrador, y el sistema los compara con lo medido: horas desde el último respaldo y desde la última descarga del paquete, y duración real del último simulacro. Se ven en **Preservación › Configuración › Recuperación ante desastres** | `app/servicios/recuperacion.py::estado`, `tests/test_brechas_lote2.py::test_rpo_y_rto_por_escenario_frente_a_lo_medido` |
| NFR-07 Restauración probada | Parcial | Cumple | El **paquete de recuperación** es un solo .tar con el volcado de la base, todos los documentos del almacén y un manifiesto con la huella de cada archivo, el sello de la auditoría y la migración, leídos en la misma instantánea del volcado. El **simulacro integral** lo restaura en una base y una carpeta nuevas y verifica las filas de las tablas clave, la huella de cada archivo y la cadena de la auditoría; mide el tiempo de cada paso. Corre solo cada N días (parámetro) o a mano. En un servidor nuevo: `python -m app.cli restaurar-paquete paquete.tar`, que se niega a restaurar sobre una base con datos | `app/servicios/recuperacion.py`, migración `0034`, `tests/test_brechas_lote2.py` (restauración completa, archivo alterado, base con datos, ruta maliciosa en el .tar) |
| TC-11 Restaurar y comprobar integridad | Parcial | Cumple | Lo anterior, con pg_dump y pg_restore reales | ídem |
| RF-OPS-001 Respaldo fuera del servidor | Parcial | Parcial (solo faltan métricas) | El paquete descargable incluye los archivos, no solo la base. Su descarga cuenta como copia externa del respaldo y cierra la alerta de «sin copia fuera del servidor» | `recuperacion.registrar_descarga`; ruta `GET /api/preservacion/recuperacion/{id}/descargar` |
| RF-GOV-001 Varias organizaciones | Parcial | No aplica | Fuera del alcance de la tesis, por decisión acordada | — |
| NFR-05 Escalado horizontal | No cumple | No aplica | Fuera del alcance de la tesis, por decisión acordada | — |

### Decisiones del lote 2

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Dónde va la copia fuera del servidor | Almacenamiento en la nube (S3, Drive); disco externo del administrador | Descarga del administrador a un disco fuera del servidor y fuera de línea | Sin costo y sin credenciales de terceros en el servidor. Una copia fuera de línea resiste el secuestro de datos, que también cifraría una copia en la nube conectada | Que nadie lo descargue: el sistema lo mide (RPO del escenario) y avisa |
| Qué lleva el paquete | Solo la base; base + archivos; todo, con las claves incluidas | Base + archivos + manifiesto, sin claves | Sin los archivos no se recuperan los documentos. Con las claves dentro, perder el disco sería perder también los secretos | Hay que guardar las claves aparte, en el gestor de secretos |
| Coherencia entre base y archivos | Listar los archivos al empacar; listarlos en la instantánea del volcado | En la instantánea del volcado | Lo restaurado y lo empaquetado coinciden exactamente aunque se carguen documentos mientras se arma | Ninguno |
| Dónde se prueba | En otro servidor; en una base y una carpeta efímeras del mismo servidor | Efímeras del mismo servidor, automático | Sin costo y repetible. Prueba el paquete, no la instalación | No mide el tiempo de instalar un servidor nuevo: se suman 2 h estimadas y documentadas |
| Un archivo que falta en el disco | Detener el paquete; empacar lo que hay y avisar | Empacar lo que hay; el faltante queda en el manifiesto y genera una alerta alta | Un solo archivo perdido no puede dejar al archivo sin copia de recuperación. Se repone desde la segunda copia (hallazgo de la prueba visual del lote 2) | Que se ignore la alerta: queda abierta hasta el próximo paquete completo |
| Cuántos paquetes conservar en el servidor | Todos; los dos últimos | Los dos últimos | Cada paquete ocupa tanto como el almacén entero | El disco: la salud avisa si queda menos del 5 % |
| Objetivos por defecto | — | RPO de 168 h (7 días), RTO de 8 h, prueba semanal | Coinciden con el aviso existente de copia externa cada 7 días y con una jornada laboral para volver a operar | La entidad debe ajustarlos según su valoración del riesgo |

## Lote 3 · Endurecimiento

| Requisito | Antes | Después | Qué se hizo | Evidencia |
|---|---|---|---|---|
| NFR-01 Seguridad | Parcial | Parcial (avanza; pasa a Cumple cuando el despliegue confirme HTTPS) | **HTTPS sin comprar dominio**: si no hay nombre propio, el despliegue usa `<ip-con-guiones>.sslip.io`, un nombre gratuito que apunta a la IP del servidor, y Caddy obtiene el certificado de Let's Encrypt. Quien entre por la dirección numérica se envía al nombre con HTTPS. **Sin caída silenciosa**: si el HTTPS falla, RICORA sigue disponible por HTTP, pero lo dice en tres lugares: un aviso en el resumen del despliegue de GitHub, una franja roja en el ingreso y en cada pantalla («no cargue documentos clasificados o reservados») y la salud del sistema en «degradado». **Cabeceras**: política de contenido (CSP) que solo admite código propio, prohíbe incrustar RICORA en otros sitios y bloquea objetos; HSTS de un año solo cuando la conexión es HTTPS. **Contraseña del administrador**: el despliegue ya no la restablece; solo la fija al crear la cuenta o si se pide expresamente con `RICORA_ADMIN_RESTABLECER=1` | `app/main.py` (cabeceras), `Caddyfile`, `.github/workflows/deploy.yml`, `app/servicios/salud.py::_conexion`, `frontend/src/components/SinCifrar.tsx`, `app/cli.py::cuenta_administradora`, `tests/test_brechas_lote3.py`, `frontend/src/pruebas/sinCifrar.test.ts` |

### Decisiones del lote 3

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Nombre para el certificado | Comprar un dominio; certificado autofirmado; nombre gratuito sslip.io | sslip.io, con el dominio propio como opción (`RICORA_DOMINIO`) | Let's Encrypt no emite certificados para una IP sola. sslip.io es gratuito y no requiere registro; un certificado autofirmado haría que el navegador advierta en cada ingreso y entrena a las personas a ignorar avisos | Depende de un servicio de terceros para resolver el nombre y de sus límites de emisión. Para producción institucional: un dominio propio. `RICORA_DOMINIO=ninguno` lo desactiva |
| Si el HTTPS falla | Detener el despliegue; seguir en HTTP en silencio (como antes); seguir en HTTP avisando | Seguir en HTTP avisando en tres lugares | Detener el despliegue deja al archivo sin servicio por un problema de red (p. ej. el puerto 443 cerrado en el cortafuegos). Callarlo era el defecto de la auditoría | Que alguien cargue un documento reservado pese a la franja: la franja aparece antes de ingresar la contraseña |
| Redirección desde la IP | Ninguna; permanente (301); temporal (302) | Temporal | Si el HTTPS fallara después, un 301 quedaría memorizado en los navegadores y RICORA sería inaccesible por la IP | Ninguno |
| Política de contenido | Ninguna; estricta sin estilos en línea; estricta en guiones y permisiva en estilos | Guiones solo propios; estilos propios y en línea | React aplica estilos en línea (posiciones del grafo, barras de progreso). Los guiones, que son el riesgo real de robo de sesión, quedan restringidos a RICORA. La documentación de la API (`/api/docs`) tiene su propia política porque usa Swagger desde un CDN | Un estilo en línea inyectado podría alterar la apariencia, no ejecutar código |
| HSTS | Siempre; solo con HTTPS; con precarga | Solo con HTTPS, un año, sin precarga | En HTTP la cabecera no tiene efecto y, con un nombre prestado como sslip.io, la precarga comprometería un dominio que no es nuestro | Si se vuelve a HTTP con el mismo nombre, los navegadores que ya entraron exigirán HTTPS durante un año: por eso la vuelta a HTTP usa la IP, no el nombre |
| Contraseña del administrador en cada despliegue | Restablecerla siempre (como antes); no tocarla nunca; solo al crear o a pedido | Solo al crear la cuenta o con `RICORA_ADMIN_RESTABLECER=1` | Restablecerla deshacía el cambio hecho en «Mi perfil» y dejaba la contraseña viviendo para siempre en un secreto. Sin una salida, quien la olvide queda fuera | Que el secreto `RICORA_ADMIN_RESTABLECER=1` quede puesto: el despliegue lo advierte para que se borre |

**Pendiente para cerrar NFR-01:** confirmar en el registro del despliegue que el certificado se emitió («HTTPS activo en https://…»). Si el aviso dice que el puerto 443 no responde, hay que abrirlo en el cortafuegos del Droplet (DigitalOcean › Networking › Firewalls), sin costo.

## Pendiente (lotes siguientes)

| Lote | Requisitos | Qué falta |
|---|---|---|
| Métricas | RF-OPS-001, NFR-10 | Métricas de uso y de rendimiento expuestas para un monitor |
| 4 · Búsqueda | RF-SEARCH-001/002 | Buscador de texto completo (PostgreSQL) sobre texto, metadatos e identificadores, que respete la Ley 1712 |
| 5 · Evidencia de la IA | RF-AI-002, RF-OCR-001 | Propuesta del motor como registro propio con fecha y versión; página y bloque de cada fragmento |
| 6 · Versiones y API | RF-RIC-001/002, RF-INT-003 | Versiones consultables de cada descripción; esquemas de respuesta en OpenAPI con prueba |
