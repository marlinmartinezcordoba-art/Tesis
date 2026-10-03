"""
Lote de transferencia y paquete de envío (hallazgos ING-01, ING-02 e ING-06).

Un lote agrupa lo que llega en una misma transferencia, con su procedencia
(quién remite, de qué dependencia, con qué acta; Ley 594 de 2000). Se abre,
se le cargan los archivos (la ingesta de siempre: huella, formato, texto) y
se confirma. Al confirmar:

1. se arma el paquete de envío (SIP) en BagIt 1.0 (RFC 8493), con los
   archivos tal como llegaron y su huella SHA-256, y los datos de la
   transferencia en bag-info.txt;
2. se registra la custodia anterior: la dependencia de origen tuvo cada
   archivo hasta la fecha del acta (has_or_had_holder, con su tramo);
3. queda el acuse de recibo (lo que se recibió, cuándo y quién lo recibió)
   en la auditoría y disponible para descargar.

Los archivos del SIP son enlaces duros a los guardados por la ingesta (el
mismo archivo en el disco, sin ocupar espacio de nuevo); si el sistema de
archivos no lo permite, se copian.
"""

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.instanciacion import Instanciacion
from app.models.lote import FORMA_INGRESO, NOMBRE_FORMA_INGRESO, LoteIngesta
from app.models.recurso_documental import RecursoDocumental
from app.servicios import almacen, fechas
from app.servicios.auditoria import registrar


class ErrorLote(ValueError):
    pass


def _texto(valor: str | None, maximo: int | None = None) -> str | None:
    valor = (valor or "").strip()
    return (valor[:maximo] if maximo else valor) or None


def _agente(db: Session, fondo_id: uuid.UUID, agente_id: uuid.UUID | None, que: str) -> EntidadVocabulario | None:
    if agente_id is None:
        return None
    a = db.get(EntidadVocabulario, agente_id)
    if a is None or a.clase != "agente" or a.fondo_id != fondo_id or a.estado != "activa":
        raise ErrorLote(f"{que} debe ser un agente vigente del vocabulario de este fondo.")
    return a


def crear(db: Session, *, fondo: RecursoDocumental, forma_ingreso: str, remitente_id: uuid.UUID | None,
          dependencia_origen_id: uuid.UUID | None, acta_numero: str | None, acta_fecha_edtf: str | None,
          observaciones: str | None, usuario_id: uuid.UUID, ip: str | None = None) -> LoteIngesta:
    if forma_ingreso not in FORMA_INGRESO:
        raise ErrorLote("Forma de ingreso desconocida.")
    remitente = _agente(db, fondo.id, remitente_id, "Quien remite")
    dependencia = _agente(db, fondo.id, dependencia_origen_id, "La dependencia de origen")
    fecha = None
    if _texto(acta_fecha_edtf):
        try:
            fecha = fechas.interpretar(acta_fecha_edtf.strip()).edtf
        except fechas.FechaInvalida as exc:
            raise ErrorLote(f"La fecha del acta: {exc}") from exc
    if forma_ingreso.startswith("transferencia") and not (dependencia and _texto(acta_numero)):
        raise ErrorLote("Una transferencia lleva la dependencia de origen y el número del acta de transferencia.")
    anio = ahora().year
    n = (db.scalar(select(func.count(LoteIngesta.id)).where(LoteIngesta.fondo_id == fondo.id)) or 0) + 1
    lote = LoteIngesta(id=uuid.uuid4(), fondo_id=fondo.id, numero=f"L-{anio}-{n:04d}", forma_ingreso=forma_ingreso,
                       remitente_id=remitente.id if remitente else None,
                       dependencia_origen_id=dependencia.id if dependencia else None,
                       acta_numero=_texto(acta_numero, 60), acta_fecha_edtf=fecha,
                       observaciones=_texto(observaciones, 5000), estado="abierto", creado_por_id=usuario_id,
                       creado_en=ahora())
    db.add(lote)
    db.flush()
    registrar(db, modulo="ingesta", accion="lote_creado", usuario_id=usuario_id, entidad_tipo="lote_ingesta",
              entidad_id=lote.id, ip=ip, detalle=f"Lote {lote.numero} · {NOMBRE_FORMA_INGRESO[forma_ingreso]}",
              nuevo={"numero": lote.numero, "forma_ingreso": forma_ingreso, "acta": lote.acta_numero,
                     "fecha_acta": fecha, "remitente": remitente.nombre if remitente else None,
                     "dependencia_origen": dependencia.nombre if dependencia else None})
    return lote


def abierto(db: Session, lote_id: uuid.UUID, fondo_id: uuid.UUID) -> LoteIngesta:
    lote = db.get(LoteIngesta, lote_id)
    if lote is None or lote.fondo_id != fondo_id:
        raise ErrorLote("El lote no pertenece a este fondo.")
    if lote.estado != "abierto":
        raise ErrorLote(f"El lote {lote.numero} está {lote.estado}: ya no recibe archivos.")
    return lote


def archivos_de(db: Session, lote: LoteIngesta) -> list[Instanciacion]:
    # Lo descartado en la ingesta (duplicado o error) se elimina de verdad:
    # nunca llegó a integrarse, así que tampoco forma parte del lote.
    return list(db.scalars(select(Instanciacion).where(Instanciacion.lote_id == lote.id)
                           .order_by(Instanciacion.cargado_en)).all())


def fijar_acta(db: Session, lote: LoteIngesta, instanciacion_id: uuid.UUID, usuario_id: uuid.UUID,
               ip: str | None = None) -> None:
    """El acta escaneada es uno de los archivos del propio lote."""
    if lote.estado != "abierto":
        raise ErrorLote("El acta se fija antes de confirmar el lote.")
    inst = db.get(Instanciacion, instanciacion_id)
    if inst is None or inst.lote_id != lote.id or inst.estado != "listo_para_descripcion":
        raise ErrorLote("El acta debe ser uno de los archivos del lote que ya terminaron la ingesta.")
    lote.acta_instanciacion_id = inst.id
    registrar(db, modulo="ingesta", accion="lote_acta_fijada", usuario_id=usuario_id, entidad_tipo="lote_ingesta",
              entidad_id=lote.id, ip=ip, detalle=f"Acta del lote {lote.numero}: «{inst.nombre_original}»",
              nuevo={"acta_instanciacion": str(inst.id)})


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while bloque := f.read(almacen.TAMANO_BLOQUE):
            h.update(bloque)
    return h.hexdigest()


def _enlazar(origen: Path, destino: Path) -> None:
    try:
        os.link(origen, destino)
    except OSError:
        shutil.copy2(origen, destino)


def _nombre_unico(nombre: str, usados: set[str]) -> str:
    base, punto, ext = nombre.rpartition(".")
    candidato, n = nombre, 1
    while candidato in usados:
        n += 1
        candidato = f"{base}-{n}.{ext}" if punto else f"{nombre}-{n}"
    usados.add(candidato)
    return candidato


def _armar_sip(db: Session, lote: LoteIngesta, archivos: list[Instanciacion]) -> None:
    relativa = Path("sip") / str(lote.fondo_id) / f"{lote.numero}-{str(lote.id)[:8]}"
    bolsa = almacen.raiz() / relativa
    if bolsa.exists():
        shutil.rmtree(bolsa)
    (bolsa / "data").mkdir(parents=True)
    usados: set[str] = set()
    filas = []
    for inst in archivos:
        nombre = _nombre_unico(inst.nombre_original.replace("/", "_"), usados)
        destino = bolsa / "data" / nombre
        _enlazar(almacen.ruta_absoluta(inst.ruta), destino)
        huella = _sha256(destino)
        if inst.huella and huella != inst.huella:
            shutil.rmtree(bolsa)
            raise ErrorLote(f"«{inst.nombre_original}» no coincide con la huella registrada en la ingesta: el lote "
                            "no se confirma. Revise la integridad del archivo.")
        filas.append((huella, f"data/{nombre}", inst))
    (bolsa / "manifest-sha256.txt").write_text("".join(f"{h}  {r}\n" for h, r, _ in filas), encoding="utf-8")
    (bolsa / "bagit.txt").write_text("BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n", encoding="utf-8")
    fondo = db.get(RecursoDocumental, lote.fondo_id)
    dependencia = db.get(EntidadVocabulario, lote.dependencia_origen_id) if lote.dependencia_origen_id else None
    remitente = db.get(EntidadVocabulario, lote.remitente_id) if lote.remitente_id else None
    total = sum((bolsa / r).stat().st_size for _, r, _ in filas)
    info = {
        "Source-Organization": dependencia.nombre if dependencia else "",
        "Contact-Name": remitente.nombre if remitente else "",
        "External-Identifier": f"Acta {lote.acta_numero}" if lote.acta_numero else "",
        "External-Description": f"{NOMBRE_FORMA_INGRESO[lote.forma_ingreso]} al fondo «{fondo.titulo}»"
                                + (f" ({fechas.legible(lote.acta_fecha_edtf)})" if lote.acta_fecha_edtf else ""),
        "Bag-Group-Identifier": lote.numero,
        "Internal-Sender-Identifier": f"urn:uuid:{lote.id}",
        "Bag-Software-Agent": f"{settings.nombre_sistema} (ingesta)",
        "Bagging-Date": ahora().date().isoformat(),
        "Payload-Oxum": f"{total}.{len(filas)}",
    }
    (bolsa / "bag-info.txt").write_text("".join(f"{k}: {v}\n" for k, v in info.items() if v), encoding="utf-8")
    # Correspondencia archivo del paquete → Instantiation del sistema.
    (bolsa / "ricora-lote.json").write_text(json.dumps({
        "lote": lote.numero, "forma_ingreso": lote.forma_ingreso, "acta": lote.acta_numero,
        "fecha_acta_edtf": lote.acta_fecha_edtf,
        "archivos": [{"ruta": r, "sha256": h, "instanciacion": f"urn:uuid:{i.id}", "formato_puid": i.formato_puid}
                     for h, r, i in filas]}, ensure_ascii=False, indent=2), encoding="utf-8")
    etiquetas = [bolsa / n for n in ("bagit.txt", "bag-info.txt", "manifest-sha256.txt", "ricora-lote.json")]
    (bolsa / "tagmanifest-sha256.txt").write_text("".join(f"{_sha256(p)}  {p.name}\n" for p in etiquetas),
                                                  encoding="utf-8")
    lote.sip_ruta, lote.sip_archivos, lote.sip_bytes = relativa.as_posix(), len(filas), total
    lote.sip_huella = _sha256(bolsa / "tagmanifest-sha256.txt")


def confirmar(db: Session, lote: LoteIngesta, usuario_id: uuid.UUID, ip: str | None = None) -> dict:
    if lote.estado != "abierto":
        raise ErrorLote(f"El lote {lote.numero} ya está {lote.estado}.")
    archivos = archivos_de(db, lote)
    if not archivos:
        raise ErrorLote("El lote no tiene archivos.")
    pendientes = [i.nombre_original for i in archivos if i.estado != "listo_para_descripcion"]
    if pendientes:
        raise ErrorLote(f"Hay {len(pendientes)} archivo(s) sin terminar la ingesta (procesando, posible duplicado o "
                        f"con error): {', '.join(pendientes[:5])}. Resuélvalos o descártelos antes de confirmar.")
    _armar_sip(db, lote, archivos)
    lote.estado, lote.confirmado_en, lote.confirmado_por_id = "confirmado", ahora(), usuario_id
    # Custodia anterior: la dependencia de origen, hasta la fecha del acta.
    if lote.dependencia_origen_id:
        from app.servicios import descripcion

        tramo = None
        if lote.acta_fecha_edtf and fechas.subtipo_de(lote.acta_fecha_edtf) == "simple":
            tramo = f"/{lote.acta_fecha_edtf.rstrip('?~%')}"
        for inst in archivos:
            ya = db.scalar(select(Relacion.id).where(
                Relacion.origen_id == inst.id, Relacion.codigo_ric == "has_or_had_holder",
                Relacion.destino_id == lote.dependencia_origen_id, Relacion.estado == "vigente"))
            if ya is None:
                descripcion.custodio_de_instanciacion(
                    db, inst, lote.dependencia_origen_id, tramo,
                    f"Custodia antes de la transferencia (lote {lote.numero}"
                    + (f", acta {lote.acta_numero})" if lote.acta_numero else ")"), usuario_id)
    recibo = acuse(db, lote)
    registrar(db, modulo="ingesta", accion="lote_confirmado", usuario_id=usuario_id, entidad_tipo="lote_ingesta",
              entidad_id=lote.id, ip=ip,
              detalle=f"Lote {lote.numero} recibido: {lote.sip_archivos} archivo(s); paquete de envío BagIt "
                      f"{lote.sip_huella[:12]}…",
              nuevo={"archivos": lote.sip_archivos, "bytes": lote.sip_bytes, "sip_huella": lote.sip_huella,
                     "acuse": recibo})
    return recibo


def anular(db: Session, lote: LoteIngesta, motivo: str, usuario_id: uuid.UUID, ip: str | None = None) -> None:
    if lote.estado != "abierto":
        raise ErrorLote("Solo se anula un lote abierto; uno confirmado ya tiene acuse de recibo.")
    if not _texto(motivo):
        raise ErrorLote("Indique el motivo de la anulación.")
    lote.estado, lote.motivo_anulacion = "anulado", _texto(motivo, 2000)
    for inst in archivos_de(db, lote):
        inst.lote_id = None  # los archivos siguen en la ingesta, sin lote
    registrar(db, modulo="ingesta", accion="lote_anulado", usuario_id=usuario_id, entidad_tipo="lote_ingesta",
              entidad_id=lote.id, ip=ip, detalle=f"Lote {lote.numero} anulado: {lote.motivo_anulacion}",
              anterior={"estado": "abierto"}, nuevo={"estado": "anulado", "motivo": lote.motivo_anulacion})


def _nombre(db: Session, entidad_id) -> str | None:
    e = db.get(EntidadVocabulario, entidad_id) if entidad_id else None
    return e.nombre if e else None


def resumen(db: Session, lote: LoteIngesta) -> dict:
    archivos = archivos_de(db, lote)
    return {
        "id": str(lote.id), "numero": lote.numero, "estado": lote.estado, "forma_ingreso": lote.forma_ingreso,
        "forma_ingreso_nombre": NOMBRE_FORMA_INGRESO[lote.forma_ingreso],
        "remitente": {"id": str(lote.remitente_id), "nombre": _nombre(db, lote.remitente_id)} if lote.remitente_id else None,
        "dependencia_origen": {"id": str(lote.dependencia_origen_id), "nombre": _nombre(db, lote.dependencia_origen_id)}
        if lote.dependencia_origen_id else None,
        "acta_numero": lote.acta_numero, "acta_fecha_edtf": lote.acta_fecha_edtf,
        "acta_fecha_legible": fechas.legible(lote.acta_fecha_edtf) if lote.acta_fecha_edtf else None,
        "acta_instanciacion_id": str(lote.acta_instanciacion_id) if lote.acta_instanciacion_id else None,
        "observaciones": lote.observaciones, "creado_en": lote.creado_en.isoformat(),
        "confirmado_en": lote.confirmado_en.isoformat() if lote.confirmado_en else None,
        "motivo_anulacion": lote.motivo_anulacion,
        "archivos": [{"id": str(i.id), "nombre": i.nombre_original, "estado": i.estado, "huella": i.huella}
                     for i in archivos],
        "listos": sum(1 for i in archivos if i.estado == "listo_para_descripcion"),
        "sip": {"huella": lote.sip_huella, "archivos": lote.sip_archivos, "bytes": lote.sip_bytes}
        if lote.sip_huella else None,
    }


def acuse(db: Session, lote: LoteIngesta) -> dict:
    """Acuse de recibo (OAIS, función Receive Submission): qué se recibió,
    con qué huellas, cuándo y bajo qué acta."""
    fondo = db.get(RecursoDocumental, lote.fondo_id)
    return {
        "sistema": settings.nombre_sistema, "fondo": fondo.titulo, "lote": lote.numero,
        "forma_ingreso": NOMBRE_FORMA_INGRESO[lote.forma_ingreso], "acta": lote.acta_numero,
        "fecha_acta": fechas.legible(lote.acta_fecha_edtf) if lote.acta_fecha_edtf else None,
        "dependencia_origen": _nombre(db, lote.dependencia_origen_id), "remitente": _nombre(db, lote.remitente_id),
        "recibido_en": lote.confirmado_en.isoformat() if lote.confirmado_en else None,
        "paquete_bagit_sha256": lote.sip_huella, "total_archivos": lote.sip_archivos, "total_bytes": lote.sip_bytes,
        "archivos": [{"nombre": i.nombre_original, "sha256": i.huella, "formato": i.formato_nombre}
                     for i in archivos_de(db, lote)],
    }


def forma_ingreso_de(db: Session, recurso: RecursoDocumental) -> str | None:
    """ISAD-G 3.2.4 a partir de los lotes por los que llegaron sus archivos."""
    lotes = db.scalars(select(LoteIngesta).join(Instanciacion, Instanciacion.lote_id == LoteIngesta.id)
                       .join(Relacion, Relacion.destino_id == Instanciacion.id)
                       .where(Relacion.origen_id == recurso.id, Relacion.codigo_ric == "has_or_had_instantiation",
                              Relacion.estado == "vigente", LoteIngesta.estado == "confirmado")
                       .distinct()).all()
    partes = []
    for lote in sorted(lotes, key=lambda x: x.numero):
        texto = NOMBRE_FORMA_INGRESO[lote.forma_ingreso]
        if lote.dependencia_origen_id:
            texto += f" desde {_nombre(db, lote.dependencia_origen_id)}"
        if lote.acta_numero:
            texto += f", acta {lote.acta_numero}"
        if lote.acta_fecha_edtf:
            texto += f" ({fechas.legible(lote.acta_fecha_edtf)})"
        partes.append(f"{texto} · lote {lote.numero}")
    return "; ".join(partes) or None
