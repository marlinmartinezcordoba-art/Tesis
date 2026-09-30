# Una sola imagen: primero se compila la interfaz React y luego se copia al
# backend FastAPI, que la sirve junto con la API. Así el servidor de 2 GB
# no carga un servidor web adicional.

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
    DIRECTORIO_ALMACENAMIENTO=/data/almacen
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
