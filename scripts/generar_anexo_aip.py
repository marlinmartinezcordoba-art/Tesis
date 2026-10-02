"""
Genera el anexo de la tesis: un paquete de información de archivo (AIP)
completo, producido por el sistema sobre una instanciación real del fondo
de prueba, con el mismo código que usa el botón «Exportar paquete de
preservación». Recorre el ciclo de preservación de punta a punta:

  ingesta real (huella SHA-256, Siegfried/PRONOM, texto) → segunda copia →
  descripción (fondo › serie › expediente › documento, RiC-R024/R025) →
  declaración de derechos en el fondo → verificación de integridad →
  migración aprobada a PDF/A-2b (Ghostscript) → exportación del AIP.

    python scripts/generar_anexo_aip.py <archivo.pdf> <carpeta de salida>

Usa la base y el almacenamiento configurados en el entorno; crea su propio
fondo de prueba y no toca ningún otro.
"""

import shutil
import sys
import uuid
import zipfile
from pathlib import Path

from app.db.base import ahora
from app.db.session import SessionLocal
from app.models.descripcion import Relacion
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.models.usuario import Usuario
from app.servicios import almacen, derechos, paquete, parametros, preservacion, procesamiento


def main(archivo: Path, salida: Path) -> int:
    with SessionLocal() as db:
        persona = Usuario(id=uuid.uuid4(), nombre="Archivista del fondo de prueba", rol="archivista", activo=True,
                          correo=f"anexo-{uuid.uuid4().hex[:8]}@ricora.local")
        db.add(persona)
        db.flush()
        fondo = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Fondo de prueba · Archivo Municipal",
                                  codigo_referencia="CO.AM", fechas_extremas="1930–1955", creado_por_id=persona.id)
        fondo.fondo_id = fondo.id
        db.add(fondo)
        db.flush()
        serie = RecursoDocumental(id=uuid.uuid4(), nivel="serie", titulo="Correspondencia", fondo_id=fondo.id,
                                  incluido_en_id=fondo.id, codigo_referencia="CO.AM.01", publicado_en=ahora())
        expediente = RecursoDocumental(id=uuid.uuid4(), nivel="expediente", titulo="Oficios de la Alcaldía, 1948",
                                       fondo_id=fondo.id, incluido_en_id=serie.id, codigo_referencia="CO.AM.01.003",
                                       fechas_extremas="1948", publicado_en=ahora())
        db.add_all([serie, expediente])
        db.flush()

        # 1. Ingesta real.
        inst_id = uuid.uuid4()
        with open(archivo, "rb") as f:
            ruta, tamano = almacen.guardar(f, fondo.id, inst_id, archivo.name, parametros.limite_ingesta_bytes(db))
        inst = Instanciacion(id=inst_id, fondo_id=fondo.id, expediente_destino_id=expediente.id,
                             nombre_original=archivo.name, ruta=ruta, tamano_bytes=tamano, estado="procesando",
                             paso="en_espera", cargado_por_id=persona.id)
        db.add(inst)
        db.commit()
        procesamiento.procesar(db, inst.id)
        db.refresh(inst)
        assert inst.estado == "listo_para_descripcion", inst.mensaje_error

        # 2. Descripción publicada (lo mínimo del grafo RiC que usa el contexto).
        documento = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo="Oficio 114 de 1948",
                                      fondo_id=fondo.id, incluido_en_id=expediente.id,
                                      codigo_referencia="CO.AM.01.003.114", fechas_extremas="1948",
                                      publicado_en=ahora(), publicado_por_id=persona.id)
        db.add(documento)
        db.flush()
        db.add(Relacion(origen_tipo="recurso_documental", origen_id=documento.id, destino_tipo="instanciacion",
                        destino_id=inst.id, tipo_relacion="asociacion", codigo_ric="has_or_had_instantiation",
                        origen="persona", confirmada_por_id=persona.id))

        # 3. Derechos del fondo (fondo histórico de acceso público).
        derechos.declarar(db, entidad_tipo="recurso_documental", entidad_id=fondo.id, base="estatuto", acceso="publico",
                          reproduccion="permitida",
                          fundamento="Ley 594 de 2000, art. 27 (acceso a documentos de archivo); Ley 1712 de 2014, art. 4",
                          nota="Fondo histórico sin información clasificada ni reservada identificada.",
                          vigente_hasta=None, usuario_id=persona.id)
        db.commit()

        # 4. Verificación de integridad (primaria y segunda copia) y migración aprobada.
        preservacion.verificar(db, inst, origen="manual", usuario_id=persona.id)
        db.commit()
        m = preservacion.migrar(db, inst, "pdfa_2b", persona.id)
        db.commit()
        assert m.estado == "completada", m.mensaje
        preservacion.verificar(db, inst, origen="periodica")
        db.commit()

        # 5. El paquete, con el mismo código del botón de la interfaz.
        zip_temporal, nombre = paquete.exportar_instanciacion(db, inst, persona.id)
        db.commit()

    salida.mkdir(parents=True, exist_ok=True)
    destino_zip = salida / nombre
    shutil.move(zip_temporal, destino_zip)
    carpeta = salida / nombre.removesuffix(".zip")
    shutil.rmtree(carpeta, ignore_errors=True)
    with zipfile.ZipFile(destino_zip) as z:
        z.extractall(salida)
    print(f"AIP: {destino_zip}\nCarpeta: {carpeta}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
