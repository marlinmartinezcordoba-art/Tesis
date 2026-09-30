#!/bin/bash
# Instalación de RICORA en un servidor nuevo (Ubuntu 24.04, como root):
#   curl -fsSL https://raw.githubusercontent.com/marlinmartinezcordoba-art/Tesis/claude/plataforma-base/deploy-ricora.sh | bash
# Después, cada cambio en la rama se despliega con GitHub Actions
# (.github/workflows/deploy.yml), que primero corre las pruebas.
set -e

apt-get update -qq
apt-get install -y -qq curl git openssl
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

IP=$(curl -s http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address || hostname -I | awk '{print $1}')

mkdir -p /root/ricora
cd /root/ricora
if [ -d .git ]; then
  git fetch origin claude/plataforma-base
  git reset --hard origin/claude/plataforma-base
else
  git clone -b claude/plataforma-base https://github.com/marlinmartinezcordoba-art/Tesis.git .
fi

if [ ! -f .env ]; then
  cat > .env <<ENVEOF
RICORA_SECRET_KEY=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 16)
RICORA_PUERTO=80
RICORA_URL_PUBLICA=http://${IP}
ENVEOF
fi

docker compose up --build -d
echo "RICORA quedó en http://${IP}. Cree la cuenta administradora con:"
echo "  RICORA_ADMIN_CORREO=... RICORA_ADMIN_PASSWORD=... docker compose exec -T -e RICORA_ADMIN_CORREO -e RICORA_ADMIN_PASSWORD web python -m app.cli cuenta-administradora"
