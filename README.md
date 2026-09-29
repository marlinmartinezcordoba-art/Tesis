# RICORA

**Automatización archivística asistida por inteligencia artificial para archivos históricos.**

Nombre anterior del prototipo: MAZUCA (**MA**rlín · **ZU**lly · **CA**talina, las tres autoras).

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
- `asistencia`: sugerencias de IA con validación humana; dos proveedores intercambiables (nube con Claude, local sin conexión) para descripción asistida (ISAD(G), con relaciones tipadas RiC), clasificación asistida y valoración asistida (la plataforma nunca ofrece eliminar documentos). Incluye auditoría periódica por muestreo (`manage.py auditoria_muestra`) de la exactitud y el sesgo de las sugerencias de IA ya aceptadas.
- Exportación de metadatos a **Dublin Core** y **PREMIS** desde la lista de documentos (`acervo/exportacion.py`).

## Decisiones de arquitectura (especificación funcional v5)

- **Grafo RiC sobre PostgreSQL relacional.** Las entidades RiC-CM son tablas con herencia multitabla y las relaciones (`RelacionRiC`) llevan el código oficial RiC-Rxxx verificado contra `ric/fixtures/ric_matrix.json`; el lienzo del módulo de relaciones y el RDF/JSON-LD se construyen desde ahí. La especificación recomienda Apache AGE (extensión de grafo sobre el mismo PostgreSQL) para consultas tipo Cypher cuando hagan falta: los recorridos actuales son de un salto y no lo necesitan todavía, así que AGE queda como ruta de crecimiento, no como dependencia.
- **Búsqueda de texto completo nativa de PostgreSQL** (diccionario `spanish`, `pg_trgm` para similitud de nombres en la detección de duplicados), sin Elasticsearch ni Meilisearch: cero infraestructura nueva para el volumen esperado, con ruta de migración si crece.
- **Instrumentos primero.** Organigrama (entidades corporativas con jerarquía R045, cargos como RiC-E12 con R054/R056), TRD (cada serie como Mandato con retención y disposición, Actividad y formas documentales) y cuadro de clasificación se cargan antes de encender el motor (criterio CC-05).
- **El motor de análisis es un agente del grafo** (RiC-E13 Mechanism, con proveedor y versión del modelo): cada propuesta queda ligada al mecanismo que la generó.

## Cómo ejecutarla

### Opción A: con Docker (recomendada para probar como en producción)

Requiere Docker Desktop (o Docker Engine) abierto. Usa PostgreSQL, igual que en DigitalOcean.

```bash
cp .env.example .env      # completa GEMINI_API_KEY si vas a probar la IA en la nube
docker compose up --build
docker compose exec web python manage.py createsuperuser
```

Entra a http://localhost:8080/admin/. Si ese puerto ya está ocupado en tu máquina, cambia `MAZUCA_PUERTO` en `.env` (por ejemplo a `8081`) y entra por ese puerto. Para detenerla: `docker compose down` (agrega `-v` si además quieres borrar la base de datos de prueba).

### Opción B: en tu máquina, sin Docker

RICORA usa **siempre PostgreSQL** (en desarrollo, en Docker y en producción), para probar contra la misma base de datos en todos los entornos. Además de Tesseract con español y el modelo de spaCy en español, necesitas PostgreSQL instalado y corriendo (en Ubuntu/Debian: `sudo apt install postgresql tesseract-ocr tesseract-ocr-spa`; en Windows, el instalador de PostgreSQL y el de Tesseract de UB Mannheim). Para el proveedor de IA en la nube (Gemini, el que se usa activamente) hace falta además una clave en la variable de entorno `GEMINI_API_KEY`; Claude sigue disponible como alternativa con `ANTHROPIC_API_KEY`.

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
../.venv/bin/python manage.py loaddata cuadro_demo  # opcional: un cuadro de clasificación de ejemplo
../.venv/bin/python manage.py createsuperuser
../.venv/bin/python manage.py sembrar_mads   # opcional: organigrama + 54 TRD del Ministerio de Ambiente en el vocabulario (M5)
../.venv/bin/python manage.py runserver
```

Entra a http://127.0.0.1:8000/admin/. Pruebas: `../.venv/bin/python manage.py test tests` (el rol necesita `CREATEDB` porque Django crea una base de datos temporal para las pruebas).

Los criterios cargados son **borradores**; se reemplazan por los validados en la Fase 4.
Cómo se relaciona RICORA con la tesis (ajuste metodológico aprobado: el software es el eje central, no un anexo): `docs/mazuca-eje-central.md`. El capítulo de lineamientos: `docs/lineamientos-tesis.md`.
Cómo montarla en DigitalOcean, una vez probada aquí: `docs/despliegue-digitalocean.md`.
