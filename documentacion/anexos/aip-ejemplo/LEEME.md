# Anexo · Paquete de información de archivo (AIP) de ejemplo

Paquete real producido por RICORA sobre una instanciación del fondo de prueba, con el mismo código del botón «Exportar paquete de preservación». Es la evidencia de la Definición de Terminado del Módulo 5 (ver `documentacion/modulo-5-preservacion.md`, §22–23).

- `ricora-aip-<uuid>.zip`: el paquete tal como lo descarga el sistema.
- `ricora-aip-<uuid>/`: el mismo paquete descomprimido, para leerlo aquí.

**Cómo validarlo:**

```
pip install bagit
bagit.py --validate ricora-aip-<uuid>/                      # BagIt 1.0: huellas de cada archivo
python scripts/validar_premis.py ricora-aip-<uuid>/data/metadatos/premis.xml   # PREMIS 3.0 contra el XSD oficial
```

**Cómo se produjo:** `python scripts/generar_anexo_aip.py "<Oficio 114 de 1948.pdf>" documentacion/anexos/aip-ejemplo`, con `DIRECTORIO_ALMACENAMIENTO=/data/almacen` y `RICORA_SEGUNDA_COPIA=/data/segunda_copia` (las mismas rutas del servidor).

El documento es material de prueba del proyecto, no un documento de archivo real.
