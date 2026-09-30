#!/bin/sh
# Arranque del contenedor: espera la base de datos, aplica las migraciones
# pendientes y levanta el servidor.
set -e

echo "Esperando la base de datos..."
python - <<'EOF'
import time
from sqlalchemy import create_engine, text
from app.core.config import settings

motor = create_engine(settings.database_url)
for intento in range(60):
    try:
        with motor.connect() as c:
            c.execute(text("SELECT 1"))
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("La base de datos no respondió en 2 minutos.")
EOF

if [ "$1" = "trabajador" ]; then
  # El trabajador no aplica migraciones (las aplica la web); si aún no
  # están, espera y reintenta solo.
  exec python -m app.trabajador
fi

echo "Aplicando migraciones..."
alembic upgrade head

# Solo detrás de Caddy (HTTPS) se confía en la IP que informa el proxy; si
# la aplicación está expuesta directamente, nadie puede falsificar su IP
# con un encabezado para saltarse los límites de intentos.
if [ "${RICORA_DETRAS_DE_PROXY:-0}" = "1" ]; then
  PROXY="--proxy-headers --forwarded-allow-ips=*"
else
  PROXY="--no-proxy-headers"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 $PROXY --timeout-keep-alive 5
