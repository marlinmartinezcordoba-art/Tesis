"""
Paquete de información de difusión (DIP, OAIS · ISO 14721:2012, hallazgo PRE-12).

La auditoría encontró que el sistema producía el AIP (para preservar) pero
no el DIP (para entregar al usuario). El DIP no es el AIP recortado: lleva
lo que el consultante necesita y nada de lo que no debe ver.

Contenido del .zip:
- contenido/: la copia de acceso de cada archivo público de la descripción
  (si hubo migración, la versión migrada vigente; nunca uno restringido por
  su declaración de derechos);
- descripcion/isadg.json e isadg.txt: la ficha ISAD(G) de la descripción;
- descripcion/ric-o.ttl: su descripción RiC-O (la misma que resuelve /id/);
- descripcion/iiif-manifest.json: el manifiesto IIIF para un visor externo;
- manifest-sha256.txt: la huella de cada archivo del paquete;
- LEEME.txt: qué es, de dónde sale y qué se dejó fuera (cuántos, no cuáles).

Solo se arma para una descripción publicada y visible en el subconjunto
público (el mismo filtro de los datos abiertos, INS-02).
"""

import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

from rdflib import URIRef
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.descripcion import Relacion
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import almacen, derechos, exportacion_rico, intercambio, isadg
from app.servicios.paquete import _sha256, nombre_seguro

LEEME = """PAQUETE DE INFORMACIÓN DE DIFUSIÓN (DIP) · {sistema}

Modelo: OAIS (ISO 14721:2012). Es la versión para consulta de la
descripción «{titulo}»{codigo}. No es el paquete de preservación (AIP): no
lleva la historia técnica ni la información de los archivos restringidos.

Generado el {fecha}.

contenido/
    Copia de acceso de {n} archivo(s) público(s) de la descripción.
descripcion/isadg.json · descripcion/isadg.txt
    Ficha ISAD(G) (26 elementos) de la descripción.
descripcion/ric-o.ttl
    La misma descripción en RiC-O 1.1 (Turtle).
descripcion/iiif-manifest.json
    Manifiesto IIIF Presentation 3.0 para abrir las páginas en un visor.
manifest-sha256.txt
    Huella SHA-256 de cada archivo del paquete.
{fuera}
Condiciones de uso: {condiciones}
"""


class ErrorDip(Exception):
    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.codigo = codigo


def _vigente(db: Session, inst: Instanciacion) -> Instanciacion:
    """La copia de acceso: la migración más reciente lista, si la hay."""
    actual = inst
    while True:
        hija = db.scalar(select(Instanciacion).where(Instanciacion.derivada_de_id == actual.id,
                                                     Instanciacion.estado == "listo_para_descripcion")
                         .order_by(Instanciacion.cargado_en.desc()).limit(1))
        if hija is None:
            return actual
        actual = hija


def instancias_de(db: Session, recurso: RecursoDocumental) -> tuple[list[Instanciacion], int]:
    """(copias de acceso públicas, cuántas se dejaron fuera por restricción)."""
    ids = db.scalars(select(Relacion.destino_id).where(
        Relacion.origen_id == recurso.id, Relacion.codigo_ric == "has_or_had_instantiation",
        Relacion.estado == "vigente", Relacion.destino_tipo == "instanciacion")).all()
    publicas, fuera = [], 0
    for i in sorted((db.get(Instanciacion, x) for x in ids), key=lambda i: i.cargado_en if i else ahora()):
        if i is None or i.estado != "listo_para_descripcion":
            continue
        acceso = _vigente(db, i)
        if derechos.instanciacion_restringida(db, i) or derechos.instanciacion_restringida(db, acceso):
            fuera += 1
            continue
        publicas.append(acceso)
    return publicas, fuera


def _texto_ficha(ficha: list[dict]) -> str:
    lineas = []
    for e in ficha:
        lineas.append(f"{e['elemento']} {e['nombre']}: {e['valor'] or '—'}")
    return "\n".join(lineas) + "\n"


def armar(db: Session, recurso: RecursoDocumental, base_publica: str) -> Path:
    """Arma el .zip en el directorio temporal y devuelve su ruta (el que
    llama la borra después de enviarla)."""
    fondo = db.get(RecursoDocumental, recurso.fondo_id)
    ex = exportacion_rico.exportar(db, fondo, incluir_restringidos=False)
    nodo = URIRef(exportacion_rico.base() + str(recurso.id))
    rdf = exportacion_rico.serializar(exportacion_rico.descripcion_de(ex, nodo), "turtle")
    ficha = isadg.ficha(db, recurso)
    publicas, fuera = instancias_de(db, recurso)
    manifiesto = intercambio.manifiesto_iiif(db, recurso, base_publica)

    temporal = almacen.raiz() / ".temporal"
    temporal.mkdir(parents=True, exist_ok=True)
    descriptor, ruta = tempfile.mkstemp(prefix="dip-", suffix=".zip", dir=temporal)
    os.close(descriptor)
    huellas: list[tuple[str, str]] = []
    raiz = f"ricora-dip-{recurso.id}"

    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        def poner(nombre: str, datos: bytes) -> None:
            z.writestr(f"{raiz}/{nombre}", datos)
            huellas.append((hashlib.sha256(datos).hexdigest(), nombre))

        usados: set[str] = set()
        for inst in publicas:
            nombre = nombre_seguro(inst.nombre_original)
            if nombre in usados:
                nombre = f"{inst.id}-{nombre}"
            usados.add(nombre)
            origen = almacen.ruta_absoluta(inst.ruta)
            if _sha256(origen) != inst.huella:
                raise ErrorDip(f"«{inst.nombre_original}» no tiene la huella de la ingesta: verifique su integridad "
                               "antes de entregarlo.", 409)
            z.write(origen, f"{raiz}/contenido/{nombre}")
            huellas.append((inst.huella, f"contenido/{nombre}"))
        poner("descripcion/isadg.json", json.dumps(ficha, ensure_ascii=False, indent=2, default=str).encode("utf-8"))
        poner("descripcion/isadg.txt", _texto_ficha(ficha).encode("utf-8"))
        poner("descripcion/ric-o.ttl", rdf)
        poner("descripcion/iiif-manifest.json", json.dumps(manifiesto, ensure_ascii=False, indent=2).encode("utf-8"))
        texto_fuera = (f"\nQuedaron fuera {fuera} archivo(s) por su declaración de derechos (clasificados o "
                       "reservados, Ley 1712 de 2014).\n" if fuera else "")
        poner("LEEME.txt", LEEME.format(
            sistema=settings.nombre_sistema, titulo=recurso.titulo,
            codigo=f" ({recurso.codigo_referencia})" if recurso.codigo_referencia else "",
            fecha=ahora().isoformat(timespec="seconds"), n=len(publicas), fuera=texto_fuera,
            condiciones=recurso.condiciones_uso or "las que indique la institución que custodia el fondo.")
            .encode("utf-8"))
        z.writestr(f"{raiz}/manifest-sha256.txt", "".join(f"{h}  {n}\n" for h, n in huellas))
    return Path(ruta)
