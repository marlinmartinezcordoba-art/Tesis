#!/bin/sh
# Punto de entrada del contenedor: aplica migraciones, carga los criterios
# de ejemplo la primera vez, recolecta los archivos estáticos y arranca
# el servidor. Pensado para Docker Compose (desarrollo) y para
# DigitalOcean (App Platform o un Droplet).
set -e

echo "Aplicando migraciones..."
python manage.py migrate --noinput

# Solo carga los criterios de ejemplo si la tabla está vacía, para no
# sobrescribir los que ya haya cargado la entidad en la Fase 4.
python manage.py shell -c "
from lineamientos.models import Criterio
if not Criterio.objects.exists():
    from django.core.management import call_command
    call_command('loaddata', 'criterios_borrador')
    print('Criterios de ejemplo cargados (borrador).')
else:
    print('Ya hay criterios cargados; no se modifican.')
"

echo "Configuración inicial (superusuario y proveedor de IA desde el entorno)..."
python manage.py configurar_inicial || echo "Aviso: la configuración inicial falló; la aplicación arranca igual."

echo "Recolectando archivos estáticos..."
python manage.py collectstatic --noinput

# Tiempo de espera amplio: una carga de 200 MB por una conexión lenta no debe
# cortarse a mitad. Con un proxy delante (Caddy, despliegue) la carga llega
# ya completa y el trabajador no queda ocupado mientras sube.
echo "Iniciando RICORA..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-600}"
