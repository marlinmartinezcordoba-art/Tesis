"""
Valida archivos PREMIS contra el esquema oficial PREMIS 3.0 de la Library
of Congress (lo descarga, con sus importaciones). Lo usa la integración
continua sobre el PREMIS que produce el sistema y sobre el anexo de la
tesis.

    python scripts/validar_premis.py archivo1.xml [archivo2.xml ...]
"""

import sys

import xmlschema

ESQUEMA = "https://www.loc.gov/standards/premis/v3/premis-v3-0.xsd"


def main(rutas: list[str]) -> int:
    esquema = xmlschema.XMLSchema(ESQUEMA)
    fallos = 0
    for ruta in rutas:
        errores = list(esquema.iter_errors(ruta))
        if errores:
            fallos += 1
            print(f"NO VÁLIDO  {ruta}")
            for e in errores[:10]:
                print(f"   - {e.reason} en {e.path}")
        else:
            print(f"válido     {ruta}  (PREMIS 3.0, {ESQUEMA})")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
