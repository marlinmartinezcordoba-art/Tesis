"""
Índice de información clasificada y reservada (Ley 1712 de 2014, art. 20;
Decreto 1081 de 2015, art. 2.1.1.5.2.1), hallazgo INS-08.

Se arma con las declaraciones de derechos vigentes cuyo acceso es
clasificado o reservado, sobre descripciones o archivos del fondo. Es un
instrumento de la entidad que la ley obliga a publicar: lista qué se
reserva y por qué, sin revelar el contenido (no incluye alcance y
contenido ni texto del documento).
"""

import io
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.instanciacion import Instanciacion
from app.models.preservacion import DeclaracionDerechos
from app.models.recurso_documental import RecursoDocumental
from app.servicios import derechos, fechas
from app.servicios.derechos import ACCESO_RESTRINGIDO

# Columnas del Decreto 1081 de 2015, art. 2.1.1.5.2.1, en su orden.
COLUMNAS = [
    ("categoria", "Nombre o título de la categoría de información"),
    ("titulo", "Nombre o título de la información"),
    ("idioma", "Idioma"),
    ("soporte", "Medio de conservación o soporte"),
    ("fecha_generacion", "Fecha de generación de la información"),
    ("responsable_produccion", "Nombre del responsable de la producción de la información"),
    ("responsable_informacion", "Nombre del responsable de la información"),
    ("objetivo", "Objetivo legítimo de la excepción"),
    ("fundamento", "Fundamento constitucional o legal"),
    ("excepcion", "Excepción total o parcial"),
    ("fecha_calificacion", "Fecha de la calificación"),
    ("plazo", "Plazo de la clasificación o reserva"),
    ("estado", "Estado"),
]
CATEGORIA = {"clasificado": "Información pública clasificada (art. 18)",
             "reservado": "Información pública reservada (art. 19)"}


def _recurso_de(db: Session, d: DeclaracionDerechos) -> tuple[RecursoDocumental | None, Instanciacion | None]:
    if d.entidad_tipo == "recurso_documental":
        return db.get(RecursoDocumental, d.entidad_id), None
    inst = db.get(Instanciacion, d.entidad_id)
    recursos = derechos.recursos_de(db, inst) if inst else []
    return (recursos[0] if recursos else None), inst


def _productores(db: Session, recurso: RecursoDocumental | None) -> str | None:
    if recurso is None:
        return None
    nombres = db.scalars(select(EntidadVocabulario.nombre).join(Relacion, Relacion.destino_id == EntidadVocabulario.id)
                         .where(Relacion.origen_id == recurso.id, Relacion.codigo_ric == "has_creator",
                                Relacion.estado == "vigente")).all()
    return ", ".join(nombres) or None


def indice(db: Session, fondo: RecursoDocumental, hoy: date | None = None) -> list[dict]:
    hoy = hoy or date.today()
    filas = []
    declaraciones = db.scalars(select(DeclaracionDerechos).where(
        DeclaracionDerechos.fondo_id == fondo.id, DeclaracionDerechos.vigente.is_(True),
        DeclaracionDerechos.acceso.in_(ACCESO_RESTRINGIDO)).order_by(DeclaracionDerechos.creada_en)).all()
    for d in declaraciones:
        recurso, inst = _recurso_de(db, d)
        if recurso is None and inst is None:
            continue
        titulo = recurso.titulo if recurso else inst.nombre_original
        if inst is not None:
            titulo = f"{inst.nombre_original} (archivo de «{recurso.titulo}»)" if recurso else inst.nombre_original
        fecha_gen = None
        if recurso is not None:
            fecha_gen = recurso.fechas_extremas or (fechas.legible(recurso.fechas_extremas_edtf)
                                                    if recurso.fechas_extremas_edtf else None)
        filas.append({
            "categoria": CATEGORIA[d.acceso],
            "titulo": titulo,
            "idioma": ", ".join(recurso.idiomas or []) if recurso else None,
            "soporte": (recurso.soporte if recurso else None) or ("Digital" if inst else None),
            "fecha_generacion": fecha_gen,
            "responsable_produccion": _productores(db, recurso),
            "responsable_informacion": fondo.titulo,
            "objetivo": d.nota,
            "fundamento": d.fundamento,
            "excepcion": "Total" if d.entidad_tipo == "recurso_documental" else "Parcial (un archivo)",
            "fecha_calificacion": d.creada_en.date().isoformat(),
            "plazo": d.vigente_hasta.isoformat() if d.vigente_hasta else "Sin plazo declarado",
            "estado": "Vigente" if derechos.restringe(d, hoy) else "Vencida: el documento ya es público (art. 22)",
        })
    return filas


def xlsx(fondo: RecursoDocumental, filas: list[dict]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Índice"
    hoja.append(["ÍNDICE DE INFORMACIÓN CLASIFICADA Y RESERVADA (Ley 1712 de 2014, art. 20)"])
    hoja["A1"].font = Font(bold=True, size=13)
    hoja.append([f"Fondo: {fondo.titulo}", f"Fecha: {date.today().strftime('%d/%m/%Y')}"])
    hoja.append([])
    hoja.append([nombre for _, nombre in COLUMNAS])
    for celda in hoja[4]:
        celda.font, celda.alignment = Font(bold=True), Alignment(wrap_text=True, vertical="center")
    for f in filas:
        hoja.append([f.get(c) for c, _ in COLUMNAS])
    for j in range(1, len(COLUMNAS) + 1):
        hoja.column_dimensions[hoja.cell(row=4, column=j).column_letter].width = 24
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()
