# Una sola imagen: primero se compila la interfaz React y luego se copia al
# backend FastAPI, que la sirve junto con la API. Así el servidor de 2 GB
# no carga un servidor web adicional.

# Siegfried (identificación de formato contra PRONOM), compilado desde su
# código fuente, con el archivo de firmas de esa misma versión.
FROM golang:1.26-bookworm AS siegfried
ARG SIEGFRIED_VERSION=v1.11.9
RUN CGO_ENABLED=0 go install github.com/richardlehane/siegfried/cmd/sf@${SIEGFRIED_VERSION} \
    && mkdir -p /opt/siegfried \
    && cp /go/pkg/mod/github.com/richardlehane/siegfried@${SIEGFRIED_VERSION}/cmd/roy/data/default.sig /opt/siegfried/

# Validadores de formato (hallazgo PRE-09): veraPDF (PDF/A) y JHOVE con su
# módulo TIFF, resueltos desde Maven Central con versiones fijas
# (infra/validadores/pom.xml). Solo se copian los .jar a la imagen final.
FROM maven:3.9-eclipse-temurin-21 AS validadores
COPY infra/validadores/pom.xml /tmp/validadores/pom.xml
RUN mvn -q -f /tmp/validadores/pom.xml dependency:copy-dependencies -DoutputDirectory=/opt/validadores/lib

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
    RICORA_SEGUNDA_COPIA=/data/segunda_copia \
    RICORA_SIEGFRIED=/usr/local/bin/sf \
    RICORA_SIEGFRIED_HOME=/opt/siegfried \
    RICORA_VALIDADORES=/opt/validadores \
    JAVA_HOME=/opt/java/openjdk \
    PATH=/opt/java/openjdk/bin:$PATH
# OCR: Tesseract con el idioma español. Preservación: Ghostscript (PDF → PDF/A).
# Respaldo de la base: pg_dump y pg_restore de PostgreSQL 16, la misma
# versión del servidor (el cliente de Debian es 15 y no vuelca un servidor
# 16), desde el repositorio oficial de PostgreSQL.
# Antivirus: ClamAV (apagado por defecto, RICORA_ANTIVIRUS=1 lo enciende;
# sus firmas se bajan con freshclam y ocupan cerca de 1 GB de memoria).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa ghostscript curl ca-certificates \
       clamav clamav-freshclam \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=siegfried /go/bin/sf /usr/local/bin/sf
COPY --from=siegfried /opt/siegfried /opt/siegfried
# Java solo para los validadores: el JRE de Temurin 21, sin el resto de la imagen.
COPY --from=eclipse-temurin:21-jre /opt/java/openjdk /opt/java/openjdk
COPY --from=validadores /opt/validadores/lib /opt/validadores/lib
COPY infra/validadores/jhove.conf /opt/validadores/jhove.conf
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini docker-entrypoint.sh ./
COPY alembic ./alembic
COPY app ./app
COPY --from=interfaz /interfaz/dist ./interfaz
RUN useradd --create-home --uid 1000 ricora \
    && mkdir -p /data/almacen /data/segunda_copia /data/respaldo \
    && chown -R ricora:ricora /data \
    && chmod +x docker-entrypoint.sh
USER ricora
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
