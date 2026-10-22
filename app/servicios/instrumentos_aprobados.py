"""
Instrumentos de descripción aprobados: el FUID, la guía y el índice como
documentos fijos (modelo en app/models/instrumento_aprobado.py).

- Aprobar arma el archivo con las mismas funciones que la descarga (desde el grafo), lo guarda
  en el almacenamiento con su huella SHA-256 y deja constancia de quién, cuándo
  y con qué acta. La versión vigente anterior del mismo instrumento y nivel
  queda «reemplazada», no se borra.
- Un FUID con campos obligatorios sin dato no se aprueba (Acuerdo 042 de 2002):
  el inventario en pantalla dice cuáles faltan.
- El índice aprobado es el de consulta pública: sin lo clasificado ni lo reservado.
- Descargar comprueba la huella: si el archivo cambió en el disco, lo dice en
  vez de entregarlo como si fuera el aprobado.
- Anular exige motivo; el archivo y la fila se conservan.
"""

import hashlib
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import ahora
from app.models.instrumento_aprobado import TIPO_INSTRUMENTO, InstrumentoAprobado
from app.models.recurso_documental import RecursoDocumental
from app.servicios import almacen, instrumentos
from app.servicios.auditoria import registrar

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ErrorAprobacion(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


def indice_xlsx(indice: dict) -> bytes:
    """El índice de consulta en hoja de cálculo: un renglón por término y documento."""
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Font

    nombre_clase = {"agente": "Agentes", "lugar": "Lugares", "forma_documental": "Formas documentales",
                    "actividad": "Actividades", "tipo_actividad": "Funciones", "mandato": "Mandatos"}
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Índice"
    hoja.append([f"ÍNDICE DE CONSULTA · {indice['fondo']['titulo']}"])
    hoja["A1"].font = Font(bold=True, size=13)
    hoja.append([])
    hoja.append(["Clase", "Término", "Documento", "Nivel"])
    for celda in hoja[3]:
        celda.font = Font(bold=True)
    for grupo in indice["grupos"]:
        for letra in grupo["letras"]:
            for e in letra["entidades"]:
                for d in e["descripciones"]:
                    hoja.append([nombre_clase.get(grupo["clase"], grupo["clase"]), e["nombre"], d["titulo"],
                                 instrumentos.NIVEL_NOMBRE.get(d["nivel"], d["nivel"])])
    for col, ancho in zip("ABCD", (22, 40, 60, 20)):
        hoja.column_dimensions[col].width = ancho
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _contenido(db: Session, tipo: str, recurso: RecursoDocumental, fondo: RecursoDocumental, texto: str | None,
               encabezado: dict | None) -> tuple[bytes, str, str, str]:
    """(contenido, tipo MIME, extensión, título)."""
    if tipo == "inventario":
        inventario = instrumentos.filas_inventario(db, recurso)
        if not inventario["filas"]:
            raise ErrorAprobacion("El inventario no tiene renglones: no hay nada publicado en ese nivel.")
        if inventario["pendientes"]:
            raise ErrorAprobacion(f"El inventario tiene {inventario['pendientes']} campos obligatorios del FUID sin "
                                  "dato. Complételos antes de aprobarlo (la vista previa dice cuáles).")
        return (instrumentos.inventario_xlsx(inventario, encabezado), XLSX, ".xlsx",
                f"Inventario documental · {recurso.titulo}")
    if tipo == "guia":
        if not (texto or "").strip():
            raise ErrorAprobacion("La nota de presentación de la guía está vacía.")
        return instrumentos.guia_docx(db, fondo, texto), DOCX, ".docx", f"Guía del fondo · {fondo.titulo}"
    indice = instrumentos.indice(db, fondo, ver_restringidos=False)
    if not any(g["total"] for g in indice["grupos"]):
        raise ErrorAprobacion("El índice está vacío: ningún término lleva a documentos publicados.")
    return indice_xlsx(indice), XLSX, ".xlsx", f"Índice de consulta · {fondo.titulo}"


def aprobar(db: Session, *, tipo: str, recurso: RecursoDocumental, usuario_id: uuid.UUID, acta: str | None,
            fecha_acta: date | None, texto: str | None = None, encabezado: dict | None = None,
            ip: str | None = None) -> InstrumentoAprobado:
    if tipo not in TIPO_INSTRUMENTO:
        raise ErrorAprobacion("Tipo de instrumento desconocido.")
    fondo = db.get(RecursoDocumental, recurso.fondo_id or recurso.id)
    if tipo != "inventario" and recurso.id != fondo.id:
        raise ErrorAprobacion("La guía y el índice se aprueban para el fondo completo.")
    # Lo aprobado se arma con lo que dice el grafo RiC-O (app/servicios/lectura.py).
    from app.servicios import lectura

    with lectura.desde_el_grafo(db, fondo) as ldb:
        contenido, mime, extension, titulo = _contenido(ldb, tipo, lectura.en(ldb, recurso), lectura.en(ldb, fondo),
                                                        texto, encabezado)
    anterior = db.scalar(select(InstrumentoAprobado).where(
        InstrumentoAprobado.tipo == tipo, InstrumentoAprobado.recurso_id == recurso.id,
        InstrumentoAprobado.estado == "vigente").with_for_update())
    version = (db.scalar(select(func.max(InstrumentoAprobado.version)).where(
        InstrumentoAprobado.tipo == tipo, InstrumentoAprobado.recurso_id == recurso.id)) or 0) + 1
    ident = uuid.uuid4()
    hoy = ahora()
    relativa = f"{fondo.id}/instrumentos/{hoy:%Y}/{ident}{extension}"
    destino = almacen.ruta_absoluta(relativa)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "xb") as salida:
        salida.write(contenido)
    if anterior is not None:
        anterior.estado = "reemplazado"
        db.flush()  # libera el índice único de «vigente» antes de insertar el nuevo
    nuevo = InstrumentoAprobado(
        id=ident, fondo_id=fondo.id, recurso_id=recurso.id, tipo=tipo, version=version,
        titulo=f"{titulo} · versión {version}", ruta=relativa, formato_mime=mime, tamano_bytes=len(contenido),
        huella=hashlib.sha256(contenido).hexdigest(), acta=(acta or "").strip()[:200] or None, fecha_acta=fecha_acta,
        aprobado_por_id=usuario_id, aprobado_en=hoy, reemplaza_id=anterior.id if anterior else None)
    db.add(nuevo)
    db.flush()
    registrar(db, modulo="instrumentos", accion="instrumento_aprobado", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=recurso.id, detalle=nuevo.titulo, ip=ip,
              nuevo={"instrumento": str(nuevo.id), "tipo": tipo, "version": version, "huella": nuevo.huella,
                     "acta": nuevo.acta, "reemplaza": str(anterior.id) if anterior else None})
    return nuevo


def leer(db: Session, instrumento: InstrumentoAprobado) -> bytes:
    contenido = almacen.ruta_absoluta(instrumento.ruta).read_bytes()
    if hashlib.sha256(contenido).hexdigest() != instrumento.huella:
        raise ErrorAprobacion("El archivo guardado no coincide con la huella del aprobado: fue alterado. "
                              "Revise Preservación y restáurelo desde la copia.", 409)
    return contenido


def anular(db: Session, instrumento: InstrumentoAprobado, *, motivo: str, usuario_id: uuid.UUID,
           ip: str | None = None) -> InstrumentoAprobado:
    if instrumento.estado == "anulado":
        raise ErrorAprobacion("Ese instrumento ya está anulado.", 409)
    if len((motivo or "").strip()) < 10:
        raise ErrorAprobacion("Escriba el motivo de la anulación (al menos 10 caracteres).")
    era_vigente = instrumento.estado == "vigente"
    instrumento.estado, instrumento.motivo_anulacion = "anulado", motivo.strip()
    instrumento.anulado_por_id, instrumento.anulado_en = usuario_id, ahora()
    db.flush()
    if era_vigente and instrumento.reemplaza_id:
        # Vuelve a regir la versión que este había reemplazado, si sigue en pie.
        previa = db.get(InstrumentoAprobado, instrumento.reemplaza_id)
        if previa is not None and previa.estado == "reemplazado":
            previa.estado = "vigente"
    registrar(db, modulo="instrumentos", accion="instrumento_anulado", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=instrumento.recurso_id, detalle=instrumento.titulo, ip=ip,
              nuevo={"instrumento": str(instrumento.id), "motivo": instrumento.motivo_anulacion})
    return instrumento


def listar(db: Session, fondo_id: uuid.UUID) -> list[dict]:
    from app.models.usuario import Usuario

    filas = db.execute(select(InstrumentoAprobado, RecursoDocumental.titulo, Usuario.nombre)
                       .join(RecursoDocumental, RecursoDocumental.id == InstrumentoAprobado.recurso_id)
                       .join(Usuario, Usuario.id == InstrumentoAprobado.aprobado_por_id)
                       .where(InstrumentoAprobado.fondo_id == fondo_id)
                       .order_by(InstrumentoAprobado.aprobado_en.desc())).all()
    return [{"id": str(i.id), "tipo": i.tipo, "tipo_nombre": TIPO_INSTRUMENTO[i.tipo], "version": i.version,
             "titulo": i.titulo, "nivel": {"id": str(i.recurso_id), "titulo": titulo}, "estado": i.estado,
             "huella": i.huella, "tamano_bytes": i.tamano_bytes, "acta": i.acta,
             "fecha_acta": i.fecha_acta.isoformat() if i.fecha_acta else None, "aprobado_por": nombre,
             "aprobado_en": i.aprobado_en.isoformat(), "motivo_anulacion": i.motivo_anulacion}
            for i, titulo, nombre in filas]
