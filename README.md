# RICORA · Archivo histórico

Sistema de descripción archivística multinivel y preservación digital de un fondo de archivo histórico, asistido por inteligencia artificial y modelado con **Records in Contexts** (RiC-CM 1.0 / RiC-O 1.1) del Consejo Internacional de Archivos.

Es un proyecto de tesis de maestría en Gestión de la Información Documental.

## Módulos

Se construyen uno a la vez; cada uno se valida antes de empezar el siguiente.

| Módulo | Estado | Documento |
|---|---|---|
| Autenticación y autorización (transversal) | Entregado | [documentacion/modulo-autenticacion.md](documentacion/modulo-autenticacion.md) |
| 1 · Ingesta y digitalización (v1.1: confianza del OCR) | Entregado, pendiente de validación | [documentacion/modulo-1-ingesta.md](documentacion/modulo-1-ingesta.md) |
| 2 · Descripción multinivel asistida por IA (v3: parte documental, idioma, condiciones, secuencia, custodia, sub-actividad, contexto de vocabulario) | Entregado, pendiente de validación | [documentacion/modulo-2-descripcion.md](documentacion/modulo-2-descripcion.md) |
| 3 · Vocabularios y control de autoridad (v2: ISAAR-CPF completo, lugar ampliado, funciones SKOS, mecanismos) | Entregado, pendiente de validación | [documentacion/modulo-3-vocabularios.md](documentacion/modulo-3-vocabularios.md) |
| 4 · Instrumentos de descripción, con la **exportación RiC-O 1.1** (Turtle, JSON-LD, URI `/id/…`, conformidad OWL + SHACL) | Entregado, pendiente de validación | [documentacion/modulo-4-instrumentos.md](documentacion/modulo-4-instrumentos.md) · anexo: [exportación de ejemplo](documentacion/anexos/rico-ejemplo/) |
| 5 · Preservación digital (v2.2: segunda copia, PREMIS, AIP BagIt, agentes mecanismo) | Entregado, pendiente de validación | [documentacion/modulo-5-preservacion.md](documentacion/modulo-5-preservacion.md) · anexo: [AIP de ejemplo](documentacion/anexos/aip-ejemplo/) |
| Auditoría (transversal, v7: hallazgos de conformidad, propiedad RiC-O, versión de la instrucción) | Entregado, pendiente de validación · incluye la prueba de extremo a extremo | [documentacion/modulo-auditoria.md](documentacion/modulo-auditoria.md) |
| Evaluación ciega (objetivo 3 de la tesis) | Entregado; el método lo debe validar la autora | [documentacion/modulo-evaluacion.md](documentacion/modulo-evaluacion.md) |
| Grafo de contexto del fondo (Instrumentos › Grafo, v2: filtros, ficha de entidad, exportación del fragmento) | Entregado, pendiente de validación | [documentacion/grafo-contexto.md](documentacion/grafo-contexto.md) · anexo: [capturas](documentacion/anexos/grafo-contexto/) |
| Rediseño de navegación (árbol de submódulos, historial reciente con Excel, visor sin descarga, estados vacíos) | Entregado, pendiente de validación | [documentacion/rediseno-navegacion.md](documentacion/rediseno-navegacion.md) · anexo: [capturas](documentacion/anexos/rediseno-navegacion/) |

**Conformidad con RiC-O 1.1:** todo nombre de clase y de propiedad sale de un único mapeo (`app/servicios/ric_o.py`), verificado contra el OWL oficial incluido en el repositorio (`app/recursos/ric-o/`). La verificación es una prueba automática. El detalle de cada decisión está en [documentacion/anexos/verificacion-ric-o-1-1.md](documentacion/anexos/verificacion-ric-o-1-1.md).

## Arquitectura

- **Backend:** FastAPI + SQLAlchemy 2 + Alembic, en `app/`.
- **Interfaz:** React + Vite + TypeScript, en `frontend/`. En producción la sirve el mismo backend.
- **Base de datos:** PostgreSQL 16.
- **Organización:** monolito modular con Docker Compose, una instancia por entidad y un `.env` por instancia.
- **HTTPS:** opcional, con Caddy, cuando hay un nombre propio (`RICORA_DOMINIO`).
- **Borrado:** nada se elimina de forma irreversible; los borrados son lógicos y quedan auditados.

## Desarrollo local

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest httpx
export DATABASE_URL=postgresql+psycopg2://ricora:ricora@localhost:5432/ricora RICORA_SECRET_KEY=$(openssl rand -hex 32)
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload         # API en :8000
cd frontend && npm install && npm run dev        # interfaz en :5173
```

Para las pruebas del servidor (304) se necesita PostgreSQL con un usuario que pueda crear bases de datos, y Siegfried, Tesseract y Ghostscript instalados (las pruebas usan las herramientas reales):

```bash
.venv/bin/python -m pytest tests
cd frontend && npm test   # pruebas de la interfaz (árbol de navegación), sin servidor
```

## Despliegue

Cada cambio en la rama `claude/plataforma-base` corre las pruebas en GitHub Actions y, si pasan, se despliega en el servidor (`.github/workflows/deploy.yml`). Los secretos que usa están listados al inicio de ese archivo.

La versión anterior, hecha en Django, se conserva en la rama `respaldo/ricora-django-final`.
