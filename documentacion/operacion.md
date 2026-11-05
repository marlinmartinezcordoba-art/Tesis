# Operación de RICORA

## Despliegue

Cada cambio que se sube a la rama `claude/plataforma-base` se publica solo. GitHub Actions corre todas las pruebas y despliega en el Droplet («Probar y desplegar en el Droplet»).

Para relanzar un despliegue: **Actions** → la última ejecución → **Re-run all jobs**.

**Sin caída (desde el 5-11-2026).** Mientras la web se reinicia, Caddy retiene cada petición y reintenta durante 90 segundos (`lb_try_duration`), en lugar de responder 502. La web declara su estado de salud contra `/api/salud`.

## Respaldos de la base

- **Automáticos y siempre activos.** El trabajador respalda la base con la frecuencia del parámetro `respaldo_frecuencia_horas` y prueba restaurarla en una base temporal (simulacro). Ya no dependen del módulo de preservación, que sigue apagado.
- **Dónde quedan.** En el volumen `respaldo` del mismo servidor. Eso protege contra errores humanos, pero no contra la pérdida del servidor.

### Copia fuera del servidor (la configura la administración)

Elija una de las dos opciones:

1. **Snapshots de DigitalOcean.** En el panel del Droplet: **Backups → Enable** (copia semanal de todo el servidor). Es lo más simple; tiene un costo pequeño.
2. **Descarga manual periódica.** **Usuarios y permisos → Puesta en marcha → Respaldos**, o la pantalla de respaldos cuando preservación está encendida. Descargue el respaldo y guárdelo en un disco o una nube institucional. Compruebe la huella SHA-256.

## Monitor externo (gratuito)

1. Cree una cuenta en un servicio de monitoreo, por ejemplo UptimeRobot.
2. Agregue un monitor HTTP(s) a `https://SU-DOMINIO/api/salud` cada 5 minutos.
3. Ponga su correo para las alertas.

## Motor de análisis (IA)

- **Hoy: Gemini**, con la clave en el secreto `GEMINI_API_KEY` de GitHub. El despliegue la escribe en el `.env` del servidor.
- **Protección de datos (Ley 1581, art. 26).** Antes de enviar un texto al motor, RICORA quita localmente los identificadores personales: cédulas, tarjetas de identidad, NUIP, pasaportes, fechas de nacimiento, correos, celulares, direcciones, cuentas e historias clínicas. Los reemplaza por su tipo entre corchetes. Aun así, no use el motor con documentos reservados, y para uso real use una clave de pago, cuyos datos no se usan para entrenar.
- **Más adelante: IA local.** El motor está aislado en `app/servicios/motor.py` (`motor_activo()`). Una IA local, por ejemplo con Ollama, entra como otra clase con el mismo método `proponer()`, sin cambiar la descripción ni la evaluación. Con IA local los textos no salen del servidor.

## Segundo factor de la administración

1. Active su propio segundo factor en **Mi perfil**.
2. Después, en los parámetros, ponga el rol administrador en `doble_factor_roles`.

No lo active antes de tener el suyo configurado: quedaría sin acceso.

## Ingreso

- **Bloqueo por cuenta:** 5 intentos fallidos bloquean la cuenta 15 minutos.
- **Bloqueo por equipo:** 20 intentos fallidos desde una misma dirección, en cualquier cuenta, bloquean esa dirección por el mismo tiempo.
