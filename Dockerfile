# Una sola imagen: primero se compila la interfaz React y luego se copia al
# backend FastAPI, que la sirve junto con la API. Así el servidor de 2 GB
# no carga un servidor web adicional.

# Siegfried (identificación de formato contra PRONOM), compilado desde su
# código fuente, con el archivo de firmas de esa misma versión.
FROM golang:1.24-bookworm AS siegfried
ARG SIEGFRIED_VERSION=v1.11.9
RUN CGO_ENABLED=0 go install github.com/richardlehane/siegfried/cmd/sf@${SIEGFRIED_VERSION} \
    && mkdir -p /opt/siegfried \
    && cp /go/pkg/mod/github.com/richardlehane/siegfried@${SIEGFRIED_VERSION}/cmd/roy/data/default.sig /opt/siegfried/

FROM node:22-alpine AS interfaz
WORKDIR /interfaz
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RICORA_DIRECTORIO_INTERFAZ=/app/interfaz \
    DIRECTORIO_ALMACENAMIENTO=/data/almacen \
    RICORA_SIEGFRIED=/usr/local/bin/sf \
    RICORA_SIEGFRIED_HOME=/opt/siegfried
# OCR: Tesseract con el idioma español.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*
COPY --from=siegfried /go/bin/sf /usr/local/bin/sf
COPY --from=siegfried /opt/siegfried /opt/siegfried
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini docker-entrypoint.sh ./
COPY alembic ./alembic
COPY app ./app
COPY --from=interfaz /interfaz/dist ./interfaz
RUN useradd --create-home --uid 1000 ricora \
    && mkdir -p /data/almacen \
    && chown -R ricora:ricora /data \
    && chmod +x docker-entrypoint.sh
USER ricora
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
