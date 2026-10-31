"""
Estado de digitalización de un documento y verificación de cada copia (requisito 5).

El estado del documento (RiC-A39: borrador, definitivo, copia…) habla del
documento intelectual; la digitalización habla de sus instanciaciones. Por eso
es un estado aparte, calculado de lo que está registrado:

- sin_instanciaciones: no tiene original físico ni archivo;
- nacido_digital: tiene archivo y no tiene original físico (no se digitalizó);
- sin_digitalizar: tiene original físico y ninguna copia digital derivada;
- digitalizado: tiene copia derivada del original, sin verificar;
- verificado: la última verificación de cada copia pasó todas las comprobaciones;
- con_problemas: la última verificación de alguna copia encontró problemas.

«Digitalizado» no es «verificado»: lo segundo lo declara una persona,
comprobación por comprobación, y queda con su nombre y su fecha.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import ahora
from app.models.descripcion import Relacion
from app.models.digitalizacion import COMPROBACIONES, Digitalizacion, VerificacionDigitalizacion
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.models.usuario import Usuario
from app.servicios.auditoria import registrar

ESTADO_NOMBRE = {"sin_instanciaciones": "Sin original ni archivo", "nacido_digital": "Nacido digital",
                 "sin_digitalizar": "Sin digitalizar", "digitalizado": "Digitalizado, sin verificar",
                 "verificado": "Digitalización verificada", "con_problemas": "Digitalización con problemas"}


class ErrorDigitalizacion(ValueError):
    pass


def _instanciaciones(db: Session, recurso: RecursoDocumental) -> list[Instanciacion]:
    return list(db.scalars(select(Instanciacion).join(Relacion, Relacion.destino_id == Instanciacion.id).where(
        Relacion.origen_id == recurso.id, Relacion.codigo_ric == "has_or_had_instantiation",
        Relacion.estado == "vigente")))


def _pares(db: Session, fisicos: list[Instanciacion]) -> list[Relacion]:
    if not fisicos:
        return []
    return list(db.scalars(select(Relacion).where(
        Relacion.origen_id.in_([f.id for f in fisicos]), Relacion.codigo_ric == "has_or_had_derived_instantiation",
        Relacion.estado == "vigente").order_by(Relacion.creado_en)))


def relacion_de(db: Session, relacion_id: uuid.UUID) -> Relacion:
    r = db.get(Relacion, relacion_id)
    if r is None or r.codigo_ric != "has_or_had_derived_instantiation" or r.estado != "vigente":
        raise ErrorDigitalizacion("No es la digitalización de un original físico.")
    original = db.get(Instanciacion, r.origen_id)
    if original is None or original.estado != "registro_fisico":
        raise ErrorDigitalizacion("No es la digitalización de un original físico.")
    return r


def recurso_de(db: Session, relacion: Relacion) -> RecursoDocumental | None:
    return db.scalar(select(RecursoDocumental).join(Relacion, Relacion.origen_id == RecursoDocumental.id).where(
        Relacion.destino_id == relacion.origen_id, Relacion.codigo_ric == "has_or_had_instantiation",
        Relacion.estado == "vigente"))


def _pistas(db: Session, copia: Instanciacion) -> dict:
    """Lo que el sistema ya sabe y ayuda a verificar: la revisión de completitud del texto de la copia."""
    from app.servicios import completitud

    r = completitud.revisar(db, copia)
    return {"completitud": {"revisable": r.get("revisable"), "hallazgos": [h["detalle"] for h in r.get("hallazgos", [])],
                            "explicacion": r.get("explicacion")},
            "huella": copia.huella}


def estado(db: Session, recurso: RecursoDocumental) -> dict:
    instancias = _instanciaciones(db, recurso)
    fisicos = [i for i in instancias if i.estado == "registro_fisico"]
    digitales = [i for i in instancias if i.estado != "registro_fisico"]
    pares = _pares(db, fisicos)
    nombres = dict(db.execute(select(Usuario.id, Usuario.nombre)).all()) if pares else {}
    salida = []
    for rel in pares:
        original, copia = db.get(Instanciacion, rel.origen_id), db.get(Instanciacion, rel.destino_id)
        datos = db.scalar(select(Digitalizacion).where(Digitalizacion.relacion_id == rel.id))
        verificaciones = list(db.scalars(select(VerificacionDigitalizacion).where(
            VerificacionDigitalizacion.relacion_id == rel.id).order_by(VerificacionDigitalizacion.verificado_en.desc())))
        ultima = verificaciones[0] if verificaciones else None
        salida.append({
            "relacion_id": str(rel.id),
            "original": {"id": str(original.id), "nombre": original.nombre_original, "soporte": original.soporte},
            "copia": {"id": str(copia.id), "nombre": copia.nombre_original, "formato": copia.formato_nombre},
            "datos": {"responsable": datos.responsable, "fecha": datos.fecha.isoformat() if datos.fecha else None,
                      "equipo": datos.equipo, "resolucion_ppp": datos.resolucion_ppp, "nota": datos.nota} if datos else None,
            "estado": "digitalizado" if ultima is None else ("verificado" if ultima.resultado == "verificada" else "con_problemas"),
            "verificaciones": [{"id": str(v.id), "resultado": v.resultado, "comprobaciones": v.comprobaciones, "nota": v.nota,
                                "verificado_por": nombres.get(v.verificado_por_id), "verificado_en": v.verificado_en.isoformat()}
                               for v in verificaciones],
            "pistas": _pistas(db, copia),
        })
    if not instancias:
        general = "sin_instanciaciones"
    elif not fisicos:
        general = "nacido_digital"
    elif not salida:
        general = "sin_digitalizar"
    elif any(p["estado"] == "con_problemas" for p in salida):
        general = "con_problemas"
    elif all(p["estado"] == "verificado" for p in salida):
        general = "verificado"
    else:
        general = "digitalizado"
    return {"estado": general, "estado_nombre": ESTADO_NOMBRE[general], "digitalizaciones": salida,
            "digitales_sin_original": len(digitales) if not fisicos else 0,
            "comprobaciones": COMPROBACIONES}


def _texto(valor, maximo: int) -> str | None:
    if valor is None:
        return None
    valor = str(valor).strip()
    if len(valor) > maximo:
        raise ErrorDigitalizacion(f"El texto supera los {maximo} caracteres.")
    return valor or None


def registrar_datos(db: Session, relacion: Relacion, *, responsable: str | None, fecha: date | None, equipo: str | None,
                    resolucion_ppp: int | None, nota: str | None, usuario_id: uuid.UUID) -> Digitalizacion:
    """Quién digitalizó, cuándo, con qué equipo y a qué resolución. Se puede corregir: la auditoría
    guarda el valor anterior."""
    if fecha and fecha > date.today():
        raise ErrorDigitalizacion("La fecha de digitalización no puede ser futura.")
    if resolucion_ppp is not None and not 50 <= resolucion_ppp <= 4800:
        raise ErrorDigitalizacion("La resolución va entre 50 y 4800 ppp.")
    d = db.scalar(select(Digitalizacion).where(Digitalizacion.relacion_id == relacion.id))
    campos = ("responsable", "fecha", "equipo", "resolucion_ppp", "nota")
    anterior = {c: (getattr(d, c).isoformat() if c == "fecha" and getattr(d, c) else getattr(d, c)) for c in campos} if d else {}
    if d is None:
        d = Digitalizacion(id=uuid.uuid4(), relacion_id=relacion.id, registrado_en=ahora())
        db.add(d)
    d.responsable, d.fecha, d.equipo = _texto(responsable, 200), fecha, _texto(equipo, 200)
    d.resolucion_ppp, d.nota = resolucion_ppp, _texto(nota, 2000)
    d.registrado_por_id = usuario_id
    nuevo = {c: (getattr(d, c).isoformat() if c == "fecha" and getattr(d, c) else getattr(d, c)) for c in campos}
    db.flush()
    registrar(db, modulo="descripcion", accion="digitalizacion_registrada", usuario_id=usuario_id,
              entidad_tipo="instanciacion", entidad_id=relacion.destino_id,
              detalle="Datos de la digitalización (quién, cuándo, equipo, resolución)",
              anterior={k: v for k, v in anterior.items() if nuevo.get(k) != v} or None,
              nuevo={k: v for k, v in nuevo.items() if anterior.get(k) != v})
    return d


def verificar(db: Session, relacion: Relacion, *, comprobaciones: dict, nota: str | None,
              usuario_id: uuid.UUID) -> VerificacionDigitalizacion:
    """Una persona revisa la copia frente al original, comprobación por comprobación."""
    if set(comprobaciones) != set(COMPROBACIONES) or not all(isinstance(v, bool) for v in comprobaciones.values()):
        raise ErrorDigitalizacion("Marque cada comprobación: " + "; ".join(COMPROBACIONES.values()).lower() + ".")
    resultado = "verificada" if all(comprobaciones.values()) else "con_problemas"
    nota = _texto(nota, 2000)
    if resultado == "con_problemas" and not nota:
        raise ErrorDigitalizacion("Diga qué problema encontró (por ejemplo, «faltan los folios 12 y 13»).")
    v = VerificacionDigitalizacion(id=uuid.uuid4(), relacion_id=relacion.id, comprobaciones=comprobaciones,
                                   resultado=resultado, nota=nota, verificado_por_id=usuario_id, verificado_en=ahora())
    db.add(v)
    db.flush()
    registrar(db, modulo="descripcion", accion="digitalizacion_verificada", usuario_id=usuario_id,
              entidad_tipo="instanciacion", entidad_id=relacion.destino_id,
              detalle="Verificación de la digitalización: " + ("verificada" if resultado == "verificada" else "con problemas"),
              nuevo={"resultado": resultado, "comprobaciones": comprobaciones, "nota": nota})
    return v
