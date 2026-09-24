# MAZUCA

**Automatización archivística asistida por inteligencia artificial para archivos históricos.**

**MA**rlín · **ZU**lly · **CA**talina: tres autoras, tres sílabas y tres atributos del patrimonio documental: autenticidad, integridad y accesibilidad.

Prototipo demostrativo que acompaña la tesis de maestría en Gestión de la Información Documental
(Universidad de La Salle): *Incorporación de inteligencia artificial en la
automatización asistida de procesos archivísticos en archivos históricos del
orden nacional en Colombia*.

La plataforma aplica los lineamientos de la tesis: la IA propone, la persona
archivista decide, y cada acción queda registrada para proteger la
autenticidad, la integridad y la accesibilidad del patrimonio documental.

## Módulos

- `lineamientos`: criterios por proceso y atributo, con su fuente normativa, e informe de verificación por documento.
- `acervo`: documentos con elementos ISAD(G), hash SHA-256, bitácora de preservación encadenada (estilo PREMIS) y extracción de texto con OCR (Tesseract en español) para PDF, imágenes y texto plano.
- `acceso`: detección de datos personales (Ley 1581 de 2012), decisión humana (publicar, anonimizar o restringir) y aprobación controlada para el futuro portal de consulta.
- `asistencia`: sugerencias de IA con validación humana; dos proveedores intercambiables para la descripción asistida (ISAD(G)): uno en la nube con Claude (salida estructurada, verificación de evidencia) y uno local con spaCy en español (sin conexión a internet).

## Cómo ejecutarla

### Opción A: con Docker (recomendada para probar como en producción)

Requiere Docker Desktop (o Docker Engine) abierto. Usa PostgreSQL, igual que en DigitalOcean.

```bash
cp .env.example .env      # completa ANTHROPIC_API_KEY si vas a probar la IA en la nube
docker compose up --build
docker compose exec web python manage.py createsuperuser
```

Entra a http://localhost:8000/admin/. Para detenerla: `docker compose down` (agrega `-v` si además quieres borrar la base de datos de prueba).

### Opción B: en tu máquina, sin Docker

MAZUCA usa **siempre PostgreSQL** (en desarrollo, en Docker y en producción), para probar contra la misma base de datos en todos los entornos. Además de Tesseract con español y el modelo de spaCy en español, necesitas PostgreSQL instalado y corriendo (en Ubuntu/Debian: `sudo apt install postgresql tesseract-ocr tesseract-ocr-spa`; en Windows, el instalador de PostgreSQL y el de Tesseract de UB Mannheim). Para el proveedor de IA en la nube hace falta además una clave de Anthropic en la variable de entorno `ANTHROPIC_API_KEY`.

Crea el rol y la base de datos una sola vez (los valores por defecto que espera la aplicación son usuario `mazuca`, clave `mazuca`, base `mazuca`; puedes cambiarlos si defines tu propia `DATABASE_URL`):

```bash
sudo -u postgres psql -c "CREATE ROLE mazuca WITH LOGIN PASSWORD 'mazuca' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE mazuca OWNER mazuca;"
```

```bash
python3 -m venv .venv
.venv/bin/pip install -r plataforma/requirements.txt
cd plataforma
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py loaddata criterios_borrador
../.venv/bin/python manage.py createsuperuser
../.venv/bin/python manage.py runserver
```

Entra a http://127.0.0.1:8000/admin/. Pruebas: `../.venv/bin/python manage.py test tests` (el rol necesita `CREATEDB` porque Django crea una base de datos temporal para las pruebas).

Los criterios cargados son **borradores**; se reemplazan por los validados en la Fase 4.
Cómo se relaciona MAZUCA con la tesis: `docs/mazuca-valor-agregado.md`.
Cómo montarla en DigitalOcean, una vez probada aquí: `docs/despliegue-digitalocean.md`.
