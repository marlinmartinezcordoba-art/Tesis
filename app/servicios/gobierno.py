"""
Gobierno archivístico: el Programa de Gestión Documental (PGD) y el Plan
Institucional de Archivos (PINAR) como contexto RiC de la gestión.

No se crea un modelo propio: en RiC un plan adoptado por acto administrativo
es un mandato (rico:Mandate) y sus programas, proyectos y acciones son
actividades (rico:Activity) que ese mandato regula (rico:regulatesOrRegulated).
Así el plan queda en el grafo, se navega desde la ficha del mandato y los
documentos que documentan una de sus acciones (R033) aparecen bajo ella.

- El plan guarda su acto de adopción y su vigencia (EDTF).
- Lo creado no se borra: se anula desde la ficha de la autoridad, con auditoría.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios.auditoria import registrar

PLANES = {"pgd": ("PGD", "Programa de Gestión Documental"), "pinar": ("PINAR", "Plan Institucional de Archivos")}
TIPOS_ACCION = {"programa": "Programa", "proyecto": "Proyecto", "accion": "Acción"}


class ErrorGobierno(ValueError):
    pass


def _tipo_de(e: EntidadVocabulario) -> str | None:
    for clave, (sigla, nombre) in PLANES.items():
        if e.nombre.startswith(sigla + " ") or e.nombre.startswith(nombre):
            return clave
    return None


def listar(db: Session, fondo: RecursoDocumental) -> dict:
    from app.servicios import fechas, vocabulario

    mandatos = db.scalars(select(EntidadVocabulario).where(
        EntidadVocabulario.fondo_id == fondo.id, EntidadVocabulario.clase == "mandato",
        EntidadVocabulario.estado == "activa").order_by(EntidadVocabulario.nombre)).all()
    planes = []
    for m in mandatos:
        tipo = _tipo_de(m)
        if tipo is None:
            continue
        ids = [r.destino_id for r in db.scalars(select(Relacion).where(
            Relacion.origen_id == m.id, Relacion.codigo_ric == "regulates_or_regulated", Relacion.estado == "vigente",
            Relacion.destino_tipo == "entidad_vocabulario"))]
        acciones = db.scalars(select(EntidadVocabulario).where(
            EntidadVocabulario.id.in_(ids), EntidadVocabulario.clase == "actividad",
            EntidadVocabulario.estado == "activa").order_by(EntidadVocabulario.nombre)).all() if ids else []
        docs = vocabulario._documentos_por_entidad(db, [a.id for a in acciones]) if acciones else {}
        planes.append({"id": str(m.id), "tipo": tipo, "sigla": PLANES[tipo][0], "nombre": m.nombre,
                       "acto": m.historia, "vigencia": m.existencia_edtf,
                       "documento": {k: (m.soporte or {}).get(k) for k in ("nombre", "tamano", "huella", "formato")}
                       if m.soporte else None,
                       "vigencia_legible": fechas.legible(m.existencia_edtf) if m.existencia_edtf else None,
                       "acciones": [{"id": str(a.id), "nombre": a.nombre, "documentos": len(docs.get(a.id, ()))}
                                    for a in acciones]})
    return {"fondo": {"id": str(fondo.id), "titulo": fondo.titulo}, "planes": planes,
            "faltan": [PLANES[t][0] for t in PLANES if not any(p["tipo"] == t for p in planes)]}


def vigencia_edtf(texto: str | None) -> str:
    """«Vigencia 2025 – 2028», «2025-2028» o «2025 a 2028» como intervalo EDTF («2025/2028»)."""
    import re

    t = " ".join((texto or "").split())
    m = re.fullmatch(r"(?:vigencia\s*)?(\d{4})\s*(?:[-–—/]|a|al|hasta)\s*(\d{4})", t, re.IGNORECASE)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.fullmatch(r"(?:vigencia\s*)?(\d{4})", t, re.IGNORECASE)
    return m.group(1) if m else t


def crear_plan(db: Session, fondo: RecursoDocumental, *, tipo: str, vigencia: str, acto: str | None,
               usuario_id: uuid.UUID) -> EntidadVocabulario:
    from app.servicios import fechas, vocabulario

    if tipo not in PLANES:
        raise ErrorGobierno("El plan es el PGD o el PINAR.")
    acto = " ".join((acto or "").split())
    if acto and len(acto) < 5:
        raise ErrorGobierno("El acto administrativo es opcional; si lo escribe, póngalo completo (p. ej. «Resolución 123 de 2024»).")
    try:
        i = fechas.interpretar(vigencia_edtf(vigencia))
    except fechas.FechaInvalida as exc:
        raise ErrorGobierno(f"Vigencia: {exc}. Escríbala como «2025-2028» o «2025/2028».") from exc
    sigla, nombre = PLANES[tipo]
    m = vocabulario.crear(db, fondo_id=fondo.id, clase="mandato", nombre=f"{sigla} {fechas.legible(i.edtf)} · {nombre}",
                          subtipo="otro", origen="persona", confianza=None, motor=None, usuario_id=usuario_id)
    m.historia = f"Adoptado por {acto}." if acto else None
    m.existencia_edtf, m.existencia_inicio, m.existencia_fin = i.edtf, i.inicio, i.fin
    registrar(db, modulo="vocabularios", accion="plan_registrado", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=m.id, detalle=m.nombre, nuevo={"acto": acto, "vigencia": i.edtf})
    return m


LIMITE_SOPORTE = 50 * 1024 * 1024


def adjuntar(db: Session, plan: EntidadVocabulario, *, contenido: bytes, nombre: str, usuario_id: uuid.UUID) -> dict:
    """Guarda el documento del plan (cualquier formato) con su huella. Uno nuevo reemplaza al anterior, que
    queda en el almacenamiento y en la auditoría."""
    import hashlib
    import io
    import mimetypes

    from app.servicios import almacen

    if plan.clase != "mandato" or _tipo_de(plan) is None:
        raise ErrorGobierno("Ese mandato no es un PGD ni un PINAR.")
    if not contenido:
        raise ErrorGobierno("El archivo está vacío.")
    if len(contenido) > LIMITE_SOPORTE:
        raise ErrorGobierno("El archivo supera 50 MB.")
    relativa, tamano = almacen.guardar(io.BytesIO(contenido), plan.fondo_id, uuid.uuid4(), nombre, LIMITE_SOPORTE)
    anterior = plan.soporte
    plan.soporte = {"nombre": nombre, "ruta": relativa, "tamano": tamano, "huella": hashlib.sha256(contenido).hexdigest(),
                    "formato": mimetypes.guess_type(nombre)[0] or "application/octet-stream"}
    registrar(db, modulo="vocabularios", accion="plan_documento_adjuntado", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=plan.id, detalle=f"{plan.nombre}: {nombre}",
              anterior=anterior, nuevo={k: v for k, v in plan.soporte.items() if k != "ruta"})
    return plan.soporte


def agregar_accion(db: Session, plan: EntidadVocabulario, *, tipo: str, nombre: str,
                   usuario_id: uuid.UUID) -> EntidadVocabulario:
    from app.servicios import autoridad, vocabulario

    if plan.clase != "mandato" or _tipo_de(plan) is None:
        raise ErrorGobierno("Ese mandato no es un PGD ni un PINAR.")
    if tipo not in TIPOS_ACCION:
        raise ErrorGobierno("Es un programa, un proyecto o una acción.")
    nombre = " ".join((nombre or "").split())
    if len(nombre) < 3:
        raise ErrorGobierno("Escriba el nombre del programa, proyecto o acción.")
    a = vocabulario.crear(db, fondo_id=plan.fondo_id, clase="actividad", nombre=f"{TIPOS_ACCION[tipo]}: {nombre}",
                          subtipo=None, origen="persona", confianza=None, motor=None, usuario_id=usuario_id)
    db.flush()
    autoridad.vincular(db, tipo="mandato_actividad", desde=a, con_tipo="entidad_vocabulario", con_id=plan.id,
                       usuario_id=usuario_id)
    return a
