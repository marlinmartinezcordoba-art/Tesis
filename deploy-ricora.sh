#!/bin/bash
# Instalación en un Droplet nuevo de DigitalOcean (Ubuntu 24.04): instala
# Docker, descarga RICORA, lo levanta, y deja un cron que revisa cada 5
# minutos si hay cambios nuevos en GitHub para actualizarse solo.
#
# Uso, desde la consola del Droplet (como root):
#   curl -fsSL https://raw.githubusercontent.com/marlinmartinezcordoba-art/Tesis/claude/plataforma-base/deploy-ricora.sh | bash
set -e

echo "Instalando Docker..."
apt-get update -qq
apt-get install -y -qq docker.io docker-compose-plugin git openssl
systemctl enable --now docker

IP=$(curl -s http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address)
echo "IP pública detectada: ${IP}"

echo "Descargando RICORA..."
mkdir -p /root/ricora
cd /root/ricora
if [ -d .git ]; then
  git fetch origin claude/plataforma-base
  git reset --hard origin/claude/plataforma-base
else
  git clone -b claude/plataforma-base https://github.com/marlinmartinezcordoba-art/Tesis.git .
fi

if [ ! -f .env ]; then
  echo "Creando .env..."
  cat > .env <<ENVEOF
DJANGO_SECRET_KEY=$(openssl rand -hex 32)
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=${IP},localhost,127.0.0.1
DJANGO_BEHIND_PROXY=0
DJANGO_CSRF_TRUSTED_ORIGINS=
ANTHROPIC_API_KEY=
MAZUCA_MODELO_IA=claude-opus-5
POSTGRES_PASSWORD=$(openssl rand -hex 16)
MAZUCA_PUERTO=80
ENVEOF
fi

echo "Levantando RICORA (puede tardar varios minutos la primera vez)..."
docker compose up --build -d

echo "Configurando actualización automática cada 5 minutos..."
cat > /root/actualizar.sh <<'SHEOF'
#!/bin/bash
cd /root/ricora
git fetch origin claude/plataforma-base
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/claude/plataforma-base)" ]; then
  git reset --hard origin/claude/plataforma-base
  docker compose up --build -d
fi
SHEOF
chmod +x /root/actualizar.sh
(crontab -l 2>/dev/null | grep -v actualizar.sh; echo "*/5 * * * * /root/actualizar.sh >> /root/actualizar.log 2>&1") | crontab -

echo ""
echo "Listo. Entra en unos minutos a: http://${IP}/ric/"
