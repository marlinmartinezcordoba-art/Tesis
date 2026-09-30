# RICORA · Archivo histórico

Sistema de descripción archivística multinivel y preservación digital de un fondo de archivo histórico, asistido por inteligencia artificial y modelado con **Records in Contexts** (RiC-CM 1.0 / RiC-O 1.1) del Consejo Internacional de Archivos.

Es un proyecto de tesis de maestría en Gestión de la Información Documental.

## Módulos

Se construyen uno a la vez; cada uno se valida antes de empezar el siguiente.

| Módulo | Estado | Documento |
|---|---|---|
| Autenticación y autorización (transversal) | Entregado; cierre transversal con los siete módulos pendiente de validación (rol revisor provisional) | [documentacion/modulo-autenticacion.md](documentacion/modulo-autenticacion.md) |
| 1 · Ingesta y digitalización | Entregado | [documentacion/modulo-1-ingesta.md](documentacion/modulo-1-ingesta.md) |
| 2 · Descripción multinivel asistida por IA | Entregado | [documentacion/modulo-2-descripcion.md](documentacion/modulo-2-descripcion.md) |
| 3 · Vocabularios y control de autoridad | Entregado | [documentacion/modulo-3-vocabularios.md](documentacion/modulo-3-vocabularios.md) |
| 4 · Generación de instrumentos de descripción | Entregado | [documentacion/modulo-4-instrumentos.md](documentacion/modulo-4-instrumentos.md) |
| 5 · Preservación digital | Entregado | [documentacion/modulo-5-preservacion.md](documentacion/modulo-5-preservacion.md) |
| Auditoría (transversal) | Entregado, pendiente de validación · incluye la prueba de extremo a extremo de los siete módulos | [documentacion/modulo-auditoria.md](documentacion/modulo-auditoria.md) |

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

Para las pruebas se necesita PostgreSQL con un usuario que pueda crear bases de datos:

```bash
.venv/bin/python -m pytest tests
```

## Despliegue

Cada cambio en la rama `claude/plataforma-base` corre las pruebas en GitHub Actions y, si pasan, se despliega en el servidor (`.github/workflows/deploy.yml`). Los secretos que usa están listados al inicio de ese archivo.

La versión anterior, hecha en Django, se conserva en la rama `respaldo/ricora-django-final`.
