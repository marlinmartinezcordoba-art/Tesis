# RICORA · Automatización archivística asistida por IA
# Imagen para desarrollo local con Docker y para DigitalOcean (App Platform
# o un Droplet). Basada en Python slim + Tesseract (OCR en español).

FROM python:3.11-slim

# Tesseract con español: usado por acervo/extraccion.py.
# libpq: cliente de PostgreSQL, requerido por psycopg.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-spa libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY plataforma/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download es_core_news_md

COPY plataforma/ .

ENV PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=0

RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
