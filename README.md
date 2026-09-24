# Plataforma de automatización archivística asistida por IA

Prototipo de la tesis de maestría en Gestión de la Información Documental
(Universidad de La Salle): *Incorporación de inteligencia artificial en la
automatización asistida de procesos archivísticos en archivos históricos del
orden nacional en Colombia*.

La plataforma aplica los lineamientos de la tesis: la IA propone, la persona
archivista decide, y cada acción queda registrada para proteger la
autenticidad, la integridad y la accesibilidad del patrimonio documental.

## Módulos

- `lineamientos`: criterios por proceso y atributo, con su fuente normativa, e informe de verificación por documento.
- `acervo`: documentos con elementos ISAD(G), hash SHA-256, bitácora de preservación encadenada (estilo PREMIS) y extracción de texto con OCR (Tesseract en español) para PDF, imágenes y texto plano.
- `asistencia`: sugerencias de IA con validación humana y proveedores de IA intercambiables.

## Cómo ejecutarla

Requiere Tesseract con el idioma español (en Ubuntu/Debian: `sudo apt install tesseract-ocr tesseract-ocr-spa`; en Windows, el instalador de UB Mannheim).

```bash
python3 -m venv .venv
.venv/bin/pip install -r plataforma/requirements.txt
cd plataforma
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py loaddata criterios_borrador
../.venv/bin/python manage.py createsuperuser
../.venv/bin/python manage.py runserver
```

Entra a http://127.0.0.1:8000/admin/. Pruebas: `../.venv/bin/python manage.py test tests`.

Los criterios cargados son **borradores**; se reemplazan por los validados en la Fase 4.
El ajuste metodológico está en `docs/ajuste-metodologico.md`.
