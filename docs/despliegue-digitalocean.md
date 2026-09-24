# Cómo montar MAZUCA en DigitalOcean

> Primero pruébala en tu máquina con Docker (ver README, "Opción A"). Cuando
> funcione ahí igual que la esperas, sigue estos pasos.

## 1. Elige cómo desplegarla

| Opción | Cuándo usarla |
|---|---|
| **App Platform** (recomendado para empezar) | Lee el `Dockerfile` del repositorio directamente. No hay que administrar el servidor ni Nginx. Más sencillo y suficiente para un prototipo. |
| **Droplet** con Docker | Si más adelante necesitas control total del servidor (por ejemplo, para instalar algo específico del archivo histórico). Requiere que tú administres actualizaciones y seguridad del sistema operativo. |

Para el prototipo de la tesis, **App Platform** es la ruta más simple.

## 2. Crea la base de datos gestionada

En el panel de DigitalOcean: **Databases → Create Database Cluster → PostgreSQL 16**. El plan más pequeño alcanza para un prototipo.

Cuando esté lista, copia su **Connection String** (empieza con `postgresql://...`). Esa es tu `DATABASE_URL`.

## 3. Crea la aplicación en App Platform

1. **Apps → Create App → conecta tu repositorio de GitHub** (`marlinmartinezcordoba-art/Tesis`, rama `claude/plataforma-base` o la que uses en producción).
2. DigitalOcean detecta el `Dockerfile` en la raíz del repositorio y lo usa automáticamente.
3. En **Environment Variables**, agrega (marca "Encrypt" en las sensibles):

   | Variable | Valor |
   |---|---|
   | `DJANGO_SECRET_KEY` | Una clave propia (genera una con `python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
   | `DJANGO_DEBUG` | `0` |
   | `DJANGO_ALLOWED_HOSTS` | El dominio que te asigne App Platform, por ejemplo `mazuca-xxxxx.ondigitalocean.app` |
   | `DJANGO_BEHIND_PROXY` | `1` |
   | `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://mazuca-xxxxx.ondigitalocean.app` |
   | `DATABASE_URL` | La cadena de conexión del paso 2 |
   | `ANTHROPIC_API_KEY` | Tu clave de Anthropic (para la descripción asistida en la nube) |
   | `MAZUCA_MODELO_IA` | `claude-opus-5` (opcional, es el valor por defecto) |

4. Puerto: `8000` (el que expone el `Dockerfile`).

## 4. Almacenamiento de los documentos

Los archivos que suban las personas archivistas (`media/`) **no deben quedar solo en el disco del contenedor**: en App Platform ese disco no es permanente y se pierde en cada despliegue. Para producción real, agrega un **DigitalOcean Space** (almacenamiento de objetos, compatible con S3) y configura `django-storages` para que `MEDIA` se guarde ahí. Esto queda pendiente de implementar; por ahora, para las pruebas de la tesis con documentos de dominio público, el disco temporal es suficiente.

## 5. Primer despliegue

Con la app creada, DigitalOcean construye la imagen y corre `docker-entrypoint.sh`, que aplica las migraciones, carga los criterios de ejemplo (solo si la base está vacía) y arranca el servidor.

Cuando termine, crea el primer usuario administrador desde la consola de App Platform (**Console** → abre una terminal en el contenedor):

```bash
python manage.py createsuperuser
```

## 6. Después de cada cambio

Si conectaste el despliegue automático, cada `git push` a la rama configurada dispara un nuevo despliegue. Si prefieres desplegar manualmente, usa el botón **Deploy** en el panel de la app.

## Recordatorios de seguridad

- Nunca subas `.env` ni ninguna clave al repositorio (ya están en `.gitignore`).
- Mantén el repositorio de GitHub privado mientras el proyecto no esté sustentado.
- Usa solo documentos de dominio público o con autorización expresa en las pruebas que hagas en DigitalOcean.
