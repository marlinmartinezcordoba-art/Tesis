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

> **Estado desde el 8-11-2026: IA local apagada.** Por lentitud sin tarjeta gráfica, la administración decidió trabajar solo con Gemini. El código y el modelo descargado se conservan: para encenderla, cree en GitHub el secreto `RICORA_MOTOR_IA` con el valor `local` y vuelva a desplegar. Lo que sigue describe cómo funciona cuando está encendida.

Desde el 7-11-2026 RICORA trabaja con **dos motores juntos**: Gemini (en la nube, con la clave del secreto `GEMINI_API_KEY`) y una **IA local** (Ollama con Qwen 2.5 de 14B, en el mismo servidor).

| Tarea | Cómo responde | Por qué |
|---|---|---|
| Descripción y evaluación | **Consenso**: proponen los dos por separado y RICORA los combina. Lo que proponen los dos sube su confianza; lo que propone uno solo queda en 0,6 (por debajo del umbral de revisión) y marcado con el motor que lo propuso | Más precisión, y cada motor revisa al otro. Las dos respuestas se guardan enteras: con una sola corrida se mide Gemini solo, la IA local sola y el consenso |
| Asistente | **Gemini con Google Search** (grounding): responde en segundos y cita sus fuentes. Si Gemini no responde, contesta la IA local | Rapidez y respuestas al día; se prefieren fuentes oficiales (AGN, ICA) |
| Lectura de TRD, CCD y TVD; guía del fondo | **IA local**; si falla, Gemini | Son instrumentos públicos y la lectura no debe detenerse |

- **Evaluación con un solo motor.** La evaluación no se deja iniciar si sus propuestas se hicieron con motores distintos (por ejemplo, si en el consenso respondió uno solo). «Generar las propuestas del motor» rehace las que no coinciden. La generación corre en segundo plano y se guarda documento por documento.
- **Velocidad.** Sin tarjeta gráfica, el modelo de 14B tarda de 5 a 10 minutos por documento. En la evaluación no afecta: las propuestas se generan antes de que entren los expertos.
- **Protección de datos (Ley 1581, art. 26).** Antes de enviar un texto a Gemini (también la pregunta del asistente), RICORA quita localmente cédulas, tarjetas de identidad, NUIP, pasaportes, fechas de nacimiento, correos, celulares, direcciones, cuentas e historias clínicas. La IA local no envía nada fuera del servidor. Aun así, no use el motor con documentos reservados.
- **Configuración.** El despliegue enciende la IA local si el servidor tiene 12 GB de memoria o más (perfil `ia-local`, servicio `ia_local`, 13 GB de límite) y descarga el modelo una sola vez (unos 9 GB). Variables: `RICORA_MODELO_LOCAL` (por defecto `qwen2.5:14b`), `RICORA_MOTOR_DESCRIPCION` (`consenso` o `solo_local`), y el secreto `RICORA_MOTOR_IA` (`local` o `gemini`) para forzar uno.
- **Servidor.** 4 vCPU y 16 GB (DigitalOcean, 84 USD al mes, noviembre de 2026).

## Segundo factor de la administración

1. Active su propio segundo factor en **Mi perfil**.
2. Después, en los parámetros, ponga el rol administrador en `doble_factor_roles`.

No lo active antes de tener el suyo configurado: quedaría sin acceso.

## Ingreso

- **Bloqueo por cuenta:** 5 intentos fallidos bloquean la cuenta 15 minutos.
- **Bloqueo por equipo:** 20 intentos fallidos desde una misma dirección, en cualquier cuenta, bloquean esa dirección por el mismo tiempo.
