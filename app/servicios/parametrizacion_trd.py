"""
Parametrización de la TRD y el CCD, en el orden de los SGDEA (Modelo de
requisitos para un SGDEA del AGN; mismo orden que siguen los sistemas de
gestión documental del país):

1. Versión de la TRD (acto que la aprueba, convalidación y vigencia).
2. Dependencias productoras: secciones y subsecciones con su código.
3. Banco terminológico: series, subseries y tipos documentales.
4. Matriz: por dependencia, cada serie o subserie con sus tipos, AG, AC,
   disposición final, soporte y procedimiento.
5. Aplicar la versión: se arma el cuadro en RiC-O (secciones, series y
   subseries como rico:RecordSet, reglas como rico:Rule con la vigencia de
   la versión), se valida contra la ontología y el perfil SHACL y, solo si es
   conforme, queda vigente; la anterior pasa a histórica.

Solo un borrador por fondo a la vez. Lo vigente y lo histórico no se editan:
para cambiar una TRD se abre una versión nueva (copia de la vigente) y se
aplica. Nada se borra: se anula.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import ahora
from app.models.recurso_documental import RecursoDocumental
from app.models.trd import CLASE_BANCO, SOPORTE, DependenciaTrd, FilaTrd, TerminoBanco, VersionTrd
from app.servicios import cuadro
from app.servicios.auditoria import registrar

DISPOSICIONES = ("ct", "e", "s", "m")


class ErrorTrd(Exception):
    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.codigo = codigo


def _texto(valor, largo: int) -> str | None:
    t = " ".join(str(valor or "").split())
    return t[:largo] or None


def _norm(valor) -> str:
    return cuadro._n(valor or "")


# --- Versiones -----------------------------------------------------------------------------------------


def _version_dict(db: Session, v: VersionTrd) -> dict:
    filas = db.scalar(select(func.count()).select_from(FilaTrd).where(FilaTrd.version_id == v.id,
                                                                     FilaTrd.estado == "vigente"))
    return {"id": str(v.id), "fondo_id": str(v.fondo_id), "numero": v.numero, "nombre": v.nombre,
            "acto_aprobacion": v.acto_aprobacion,
            "fecha_aprobacion": v.fecha_aprobacion, "convalidacion": v.convalidacion,
            "fecha_convalidacion": v.fecha_convalidacion, "vigente_desde": v.vigente_desde,
            "vigente_hasta": v.vigente_hasta, "estado": v.estado, "observaciones": v.observaciones,
            "filas": filas, "informe": v.informe, "creado_en": v.creado_en, "aplicado_en": v.aplicado_en,
            "editable": v.estado == "borrador", "ente_vigilancia": _nombre_ente(db, v.ente_vigilancia_id)}


def _nombre_ente(db: Session, ente_id) -> str | None:
    from app.models.descripcion import EntidadVocabulario

    e = db.get(EntidadVocabulario, ente_id) if ente_id else None
    return e.nombre if e is not None else None


def _poner_ente(db: Session, v: VersionTrd, nombre: str | None, usuario_id: uuid.UUID) -> None:
    """Quién vigila la aplicación de la TRD (RiC-R066): el AGN o el consejo territorial de
    archivos, como entidad corporativa del vocabulario del fondo. Vacío: se quita."""
    nombre = " ".join((nombre or "").split())
    if not nombre:
        v.ente_vigilancia_id = None
        return
    ente, _ = cuadro._de_vocabulario(db, v.fondo_id, "agente", nombre[:300], usuario_id, "entidad_corporativa")
    v.ente_vigilancia_id = ente.id


def versiones(db: Session, fondo: RecursoDocumental) -> list[dict]:
    return [_version_dict(db, v) for v in db.scalars(select(VersionTrd).where(VersionTrd.fondo_id == fondo.id)
                                                     .order_by(VersionTrd.numero.desc()))]


def version_de(db: Session, version_id: uuid.UUID) -> VersionTrd:
    v = db.get(VersionTrd, version_id)
    if v is None:
        raise ErrorTrd("La versión de la TRD no existe.", 404)
    return v


def _editable(v: VersionTrd) -> None:
    if v.estado != "borrador":
        raise ErrorTrd("Solo se edita una versión en borrador. Para cambiar la TRD vigente, abra una versión nueva "
                       "a partir de ella.", 409)


CAMPOS_VERSION = ("nombre", "acto_aprobacion", "fecha_aprobacion", "convalidacion", "fecha_convalidacion",
                  "vigente_desde", "observaciones")


def _poner_campos(v: VersionTrd, datos: dict) -> None:
    for campo in CAMPOS_VERSION:
        if campo not in datos:
            continue
        valor = datos[campo]
        if campo.startswith(("fecha_", "vigente_")):
            setattr(v, campo, valor if isinstance(valor, date) else None)
        elif campo == "observaciones":
            setattr(v, campo, (valor or "").strip()[:5000] or None)
        else:
            setattr(v, campo, _texto(valor, 300))
    if not v.nombre:
        raise ErrorTrd("La versión necesita un nombre (por ejemplo «TRD 2024»).")


def crear_version(db: Session, fondo: RecursoDocumental, datos: dict, usuario_id: uuid.UUID,
                  copiar_vigente: bool = True) -> VersionTrd:
    if db.scalar(select(VersionTrd.id).where(VersionTrd.fondo_id == fondo.id, VersionTrd.estado == "borrador")):
        raise ErrorTrd("Ya hay una versión en borrador: termínela o anúlela antes de abrir otra.", 409)
    numero = (db.scalar(select(func.max(VersionTrd.numero)).where(VersionTrd.fondo_id == fondo.id)) or 0) + 1
    v = VersionTrd(fondo_id=fondo.id, numero=numero, nombre=f"TRD versión {numero}", estado="borrador",
                   creado_por_id=usuario_id)
    _poner_campos(v, {"nombre": f"TRD versión {numero}"} | {k: x for k, x in datos.items() if x is not None})
    db.add(v)
    db.flush()
    if datos.get("ente_vigilancia"):
        _poner_ente(db, v, datos["ente_vigilancia"], usuario_id)
    copiadas = 0
    vigente = db.scalar(select(VersionTrd).where(VersionTrd.fondo_id == fondo.id, VersionTrd.estado == "vigente"))
    if copiar_vigente and vigente is not None:
        for f in db.scalars(select(FilaTrd).where(FilaTrd.version_id == vigente.id, FilaTrd.estado == "vigente")):
            db.add(FilaTrd(version_id=v.id, dependencia_id=f.dependencia_id, serie_id=f.serie_id,
                           subserie_id=f.subserie_id, tipos=list(f.tipos or []), gestion=f.gestion, central=f.central,
                           disposicion=f.disposicion, otras_disposiciones=list(f.otras_disposiciones or []),
                           soporte=f.soporte, procedimiento=f.procedimiento, funcion=f.funcion))
            copiadas += 1
    db.flush()
    registrar(db, modulo="instrumentos", accion="trd_version_creada", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=fondo.id,
              detalle=f"{v.nombre} (borrador)" + (f", copia de la {vigente.nombre}" if copiadas else ""),
              nuevo={"numero": numero, "filas_copiadas": copiadas})
    return v


def editar_version(db: Session, v: VersionTrd, datos: dict, usuario_id: uuid.UUID) -> VersionTrd:
    # Quién la vigila se puede completar también en la vigente o en una histórica: no
    # cambia la tabla aprobada, solo su contexto.
    if set(datos) - {"ente_vigilancia"} or v.estado == "anulada":
        _editable(v)
    anterior = {c: str(getattr(v, c)) if getattr(v, c) is not None else None for c in CAMPOS_VERSION}
    anterior["ente_vigilancia"] = _nombre_ente(db, v.ente_vigilancia_id)
    _poner_campos(v, datos)
    if "ente_vigilancia" in datos:
        _poner_ente(db, v, datos["ente_vigilancia"], usuario_id)
    db.flush()
    registrar(db, modulo="instrumentos", accion="trd_version_editada", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=v.fondo_id, detalle=v.nombre, anterior=anterior,
              nuevo={c: str(getattr(v, c)) if getattr(v, c) is not None else None for c in CAMPOS_VERSION}
              | {"ente_vigilancia": _nombre_ente(db, v.ente_vigilancia_id)})
    return v


def anular_version(db: Session, v: VersionTrd, usuario_id: uuid.UUID, motivo: str | None) -> None:
    _editable(v)
    v.estado = "anulada"
    db.flush()
    registrar(db, modulo="instrumentos", accion="trd_version_anulada", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=v.fondo_id, detalle=f"{v.nombre}: {motivo or 'sin motivo'}")


# --- Dependencias --------------------------------------------------------------------------------------


def _codigo_completo(d: DependenciaTrd, por_id: dict) -> str:
    cadena = [d]
    while cadena[0].superior_id and cadena[0].superior_id in por_id and len(cadena) < 12:
        cadena.insert(0, por_id[cadena[0].superior_id])
    codigo = None
    for x in cadena:
        codigo = cuadro.compone_dependencia(codigo, x.codigo)
    return codigo


def _dependencia_dict(d: DependenciaTrd, superior: DependenciaTrd | None, por_id: dict | None = None) -> dict:
    return {"id": str(d.id), "codigo": d.codigo, "nombre": d.nombre, "estado": d.estado,
            "superior_id": str(d.superior_id) if d.superior_id else None,
            "codigo_completo": _codigo_completo(d, por_id) if por_id else
            (cuadro.compone_dependencia(superior.codigo, d.codigo) if superior else d.codigo),
            "nivel": "subseccion" if d.superior_id else "seccion"}


def dependencias(db: Session, fondo: RecursoDocumental, incluir_anuladas: bool = False) -> list[dict]:
    todas = db.scalars(select(DependenciaTrd).where(DependenciaTrd.fondo_id == fondo.id)).all()
    por_id = {d.id: d for d in todas}
    salida = [_dependencia_dict(d, por_id.get(d.superior_id), por_id) for d in todas
              if incluir_anuladas or d.estado == "activa"]
    return sorted(salida, key=lambda x: (x["codigo_completo"] or "", x["nombre"]))


def _usada_en_aplicada(db: Session, columna, ident: uuid.UUID) -> bool:
    return bool(db.scalar(select(FilaTrd.id).join(VersionTrd, VersionTrd.id == FilaTrd.version_id)
                          .where(columna == ident, VersionTrd.estado.in_(("vigente", "historica"))).limit(1)))


def guardar_dependencia(db: Session, fondo: RecursoDocumental, datos: dict, usuario_id: uuid.UUID,
                        dependencia: DependenciaTrd | None = None) -> DependenciaTrd:
    codigo, nombre = _texto(datos.get("codigo"), 40), _texto(datos.get("nombre"), 300)
    if not codigo or not nombre:
        raise ErrorTrd("La dependencia necesita código y nombre.")
    superior_id = datos.get("superior_id") if dependencia is None else dependencia.superior_id
    if superior_id is not None:
        sup = db.get(DependenciaTrd, superior_id)
        if sup is None or sup.fondo_id != fondo.id or sup.estado != "activa":
            raise ErrorTrd("La sección superior no existe en este fondo.")
        # Una subsección puede ir dentro de otra (estructuras de tres o más niveles), sin ciclos.
        if dependencia is not None:
            cursor = sup
            while cursor is not None:
                if cursor.id == dependencia.id:
                    raise ErrorTrd("Una dependencia no puede quedar dentro de sí misma.")
                cursor = db.get(DependenciaTrd, cursor.superior_id) if cursor.superior_id else None
    repetida = db.scalar(select(DependenciaTrd).where(
        DependenciaTrd.fondo_id == fondo.id, DependenciaTrd.estado == "activa", DependenciaTrd.codigo == codigo,
        DependenciaTrd.superior_id.is_(None) if superior_id is None else DependenciaTrd.superior_id == superior_id))
    if repetida is not None and repetida is not dependencia:
        raise ErrorTrd(f"Ya hay una dependencia con el código {codigo}: «{repetida.nombre}».", 409)
    if dependencia is None:
        dependencia = DependenciaTrd(fondo_id=fondo.id, superior_id=superior_id, codigo=codigo, nombre=nombre)
        db.add(dependencia)
        anterior = None
    else:
        anterior = {"codigo": dependencia.codigo, "nombre": dependencia.nombre}
        if codigo != dependencia.codigo and _usada_en_aplicada(db, FilaTrd.dependencia_id, dependencia.id):
            raise ErrorTrd("El código ya se usó en una TRD aplicada y es parte del código de sus series: no se cambia. "
                           "Si la dependencia cambió de código, regístrela como nueva y anule esta.", 409)
        dependencia.codigo, dependencia.nombre = codigo, nombre
    db.flush()
    registrar(db, modulo="instrumentos", accion="trd_dependencia_guardada", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=fondo.id, detalle=f"{codigo} {nombre}",
              anterior=anterior, nuevo={"codigo": codigo, "nombre": nombre})
    return dependencia


def _en_borrador(db: Session, columna, ident: uuid.UUID) -> bool:
    return bool(db.scalar(select(FilaTrd.id).join(VersionTrd, VersionTrd.id == FilaTrd.version_id)
                          .where(columna == ident, FilaTrd.estado == "vigente", VersionTrd.estado == "borrador")
                          .limit(1)))


def anular_dependencia(db: Session, d: DependenciaTrd, usuario_id: uuid.UUID) -> None:
    if _en_borrador(db, FilaTrd.dependencia_id, d.id):
        raise ErrorTrd("La dependencia tiene filas en la versión en borrador: anúlelas primero.", 409)
    if db.scalar(select(DependenciaTrd.id).where(DependenciaTrd.superior_id == d.id, DependenciaTrd.estado == "activa")):
        raise ErrorTrd("La sección tiene subsecciones activas: anúlelas primero.", 409)
    d.estado = "anulada"
    db.flush()
    registrar(db, modulo="instrumentos", accion="trd_dependencia_anulada", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=d.fondo_id, detalle=f"{d.codigo} {d.nombre}")


# --- Banco terminológico -------------------------------------------------------------------------------


def _termino_dict(t: TerminoBanco, superior: TerminoBanco | None) -> dict:
    return {"id": str(t.id), "clase": t.clase, "codigo": t.codigo, "nombre": t.nombre, "definicion": t.definicion,
            "estado": t.estado, "superior_id": str(t.superior_id) if t.superior_id else None,
            "superior": superior.nombre if superior else None,
            "codigo_completo": cuadro._compone(superior.codigo, t.codigo) if superior else t.codigo}


def banco(db: Session, fondo: RecursoDocumental, clase: str | None = None, incluir_anulados: bool = False) -> list[dict]:
    todos = db.scalars(select(TerminoBanco).where(TerminoBanco.fondo_id == fondo.id)).all()
    por_id = {t.id: t for t in todos}
    salida = [_termino_dict(t, por_id.get(t.superior_id)) for t in todos
              if (clase is None or t.clase == clase) and (incluir_anulados or t.estado == "activo")]
    return sorted(salida, key=lambda x: (CLASE_BANCO.index(x["clase"]), x["codigo_completo"] or "", x["nombre"]))


def guardar_termino(db: Session, fondo: RecursoDocumental, datos: dict, usuario_id: uuid.UUID,
                    termino: TerminoBanco | None = None) -> TerminoBanco:
    clase = termino.clase if termino is not None else datos.get("clase")
    if clase not in CLASE_BANCO:
        raise ErrorTrd("El término es una serie, una subserie o un tipo documental.")
    nombre, codigo = _texto(datos.get("nombre"), 300), _texto(datos.get("codigo"), 40)
    definicion = (datos.get("definicion") or "").strip()[:5000] or None
    if not nombre:
        raise ErrorTrd("Falta el nombre.")
    if clase != "tipo_documental" and not codigo:
        raise ErrorTrd("Las series y subseries llevan código (el de la serie o subserie, sin el de la dependencia).")
    if clase == "tipo_documental":
        codigo = None
    superior_id = termino.superior_id if termino is not None else datos.get("superior_id")
    if clase == "subserie":
        sup = db.get(TerminoBanco, superior_id) if superior_id else None
        if sup is None or sup.fondo_id != fondo.id or sup.clase != "serie" or sup.estado != "activo":
            raise ErrorTrd("Una subserie necesita su serie.")
    else:
        superior_id = None
    hermanos = db.scalars(select(TerminoBanco).where(
        TerminoBanco.fondo_id == fondo.id, TerminoBanco.clase == clase, TerminoBanco.estado == "activo",
        TerminoBanco.superior_id.is_(None) if superior_id is None else TerminoBanco.superior_id == superior_id)).all()
    for h in hermanos:
        if h is termino:
            continue
        if codigo and h.codigo == codigo:
            raise ErrorTrd(f"El código {codigo} ya es de «{h.nombre}».", 409)
        if _norm(h.nombre) == _norm(nombre):
            raise ErrorTrd(f"«{nombre}» ya está en el banco terminológico.", 409)
    if termino is None:
        termino = TerminoBanco(fondo_id=fondo.id, clase=clase, superior_id=superior_id, codigo=codigo, nombre=nombre,
                               definicion=definicion)
        db.add(termino)
        anterior = None
    else:
        anterior = {"codigo": termino.codigo, "nombre": termino.nombre}
        columna = {"serie": FilaTrd.serie_id, "subserie": FilaTrd.subserie_id}.get(clase)
        if columna is not None and codigo != termino.codigo and _usada_en_aplicada(db, columna, termino.id):
            raise ErrorTrd("El código ya se usó en una TRD aplicada: no se cambia. Registre el término nuevo y anule "
                           "este.", 409)
        termino.codigo, termino.nombre, termino.definicion = codigo, nombre, definicion
    db.flush()
    registrar(db, modulo="instrumentos", accion="trd_termino_guardado", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=fondo.id,
              detalle=f"{clase.replace('_', ' ')}: {codigo or ''} {nombre}".replace("  ", " "),
              anterior=anterior, nuevo={"codigo": codigo, "nombre": nombre})
    return termino


def anular_termino(db: Session, t: TerminoBanco, usuario_id: uuid.UUID) -> None:
    columna = {"serie": FilaTrd.serie_id, "subserie": FilaTrd.subserie_id}.get(t.clase)
    if columna is not None and _en_borrador(db, columna, t.id):
        raise ErrorTrd("El término está en filas de la versión en borrador: anúlelas primero.", 409)
    if t.clase == "tipo_documental" and db.scalar(
            select(FilaTrd.id).join(VersionTrd, VersionTrd.id == FilaTrd.version_id)
            .where(FilaTrd.tipos.any(t.id), FilaTrd.estado == "vigente", VersionTrd.estado == "borrador").limit(1)):
        raise ErrorTrd("El tipo documental está en filas de la versión en borrador: quítelo de ellas primero.", 409)
    if t.clase == "serie" and db.scalar(select(TerminoBanco.id).where(TerminoBanco.superior_id == t.id,
                                                                      TerminoBanco.estado == "activo")):
        raise ErrorTrd("La serie tiene subseries activas: anúlelas primero.", 409)
    t.estado = "anulado"
    db.flush()
    registrar(db, modulo="instrumentos", accion="trd_termino_anulado", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=t.fondo_id, detalle=f"{t.codigo or ''} {t.nombre}".strip())


# --- Matriz --------------------------------------------------------------------------------------------


def _cargar(db: Session, modelo, ids) -> dict:
    ids = {i for i in ids if i}
    return {x.id: x for x in db.scalars(select(modelo).where(modelo.id.in_(ids)))} if ids else {}


def filas(db: Session, v: VersionTrd) -> list[dict]:
    """La matriz de la versión, con los nombres y los códigos compuestos."""
    lista = db.scalars(select(FilaTrd).where(FilaTrd.version_id == v.id, FilaTrd.estado == "vigente")
                       .order_by(FilaTrd.creado_en)).all()
    deps = _cargar(db, DependenciaTrd, [f.dependencia_id for f in lista])
    while faltan := [d.superior_id for d in deps.values() if d.superior_id and d.superior_id not in deps]:
        deps |= _cargar(db, DependenciaTrd, faltan)
    terminos = _cargar(db, TerminoBanco, [x for f in lista for x in (f.serie_id, f.subserie_id, *(f.tipos or []))])
    salida = []
    for f in lista:
        fc = _fila_cuadro(f, deps, terminos)
        c = cuadro.codigos_compuestos(fc)
        dep = deps[f.dependencia_id]
        salida.append({
            "id": str(f.id), "dependencia_id": str(f.dependencia_id), "serie_id": str(f.serie_id),
            "subserie_id": str(f.subserie_id) if f.subserie_id else None, "tipos": [str(t) for t in f.tipos or []],
            "dependencia": dep.nombre, "codigo_dependencia": c["subseccion"] or c["seccion"],
            "serie": terminos[f.serie_id].nombre, "subserie": terminos[f.subserie_id].nombre if f.subserie_id else None,
            "codigo": c["subserie"] or c["serie"],
            "nombres_tipos": [terminos[t].nombre for t in f.tipos or [] if t in terminos],
            "gestion": f.gestion, "central": f.central, "disposicion": f.disposicion,
            "otras_disposiciones": list(f.otras_disposiciones or []), "soporte": f.soporte,
            "procedimiento": f.procedimiento, "funcion": f.funcion})
    return sorted(salida, key=lambda x: (x["codigo_dependencia"] or "", x["codigo"] or ""))


def _fila_cuadro(f: FilaTrd, deps: dict, terminos: dict) -> cuadro.FilaCuadro:
    cadena = [deps[f.dependencia_id]]
    while cadena[0].superior_id and cadena[0].superior_id in deps:
        cadena.insert(0, deps[cadena[0].superior_id])
    seccion, subseccion = cadena[0], (cadena[-1] if len(cadena) > 1 else None)
    nodo = lambda x: cuadro.Nodo(x.codigo, x.nombre) if x else None  # noqa: E731
    fc = cuadro.FilaCuadro(fila=0, seccion=nodo(seccion), intermedias=[nodo(x) for x in cadena[1:-1]],
                           subseccion=nodo(subseccion), serie=nodo(terminos[f.serie_id]),
                           subserie=nodo(terminos.get(f.subserie_id)) if f.subserie_id else None,
                           tipos=[terminos[t].nombre for t in f.tipos or [] if t in terminos],
                           gestion=f.gestion, central=f.central, disposicion=f.disposicion,
                           otras_disposiciones=list(f.otras_disposiciones or []), procedimiento=f.procedimiento,
                           funcion=f.funcion, soporte=f.soporte)
    return cuadro.validar(fc)


def guardar_fila(db: Session, v: VersionTrd, datos: dict, usuario_id: uuid.UUID, fila: FilaTrd | None = None) -> FilaTrd:
    _editable(v)
    dep = db.get(DependenciaTrd, datos.get("dependencia_id")) if datos.get("dependencia_id") else None
    if dep is None or dep.fondo_id != v.fondo_id or dep.estado != "activa":
        raise ErrorTrd("Elija la dependencia productora.")
    serie = db.get(TerminoBanco, datos.get("serie_id")) if datos.get("serie_id") else None
    if serie is None or serie.fondo_id != v.fondo_id or serie.clase != "serie" or serie.estado != "activo":
        raise ErrorTrd("Elija la serie del banco terminológico.")
    subserie = None
    if datos.get("subserie_id"):
        subserie = db.get(TerminoBanco, datos["subserie_id"])
        if subserie is None or subserie.clase != "subserie" or subserie.superior_id != serie.id or subserie.estado != "activo":
            raise ErrorTrd("La subserie no es de esa serie.")
    tipos = list(dict.fromkeys(datos.get("tipos") or []))
    encontrados = _cargar(db, TerminoBanco, tipos)
    if any(t not in encontrados or encontrados[t].clase != "tipo_documental" or encontrados[t].fondo_id != v.fondo_id
           for t in tipos):
        raise ErrorTrd("Algún tipo documental no está en el banco terminológico del fondo.")
    disposicion = datos.get("disposicion")
    otras = [x for x in dict.fromkeys(datos.get("otras_disposiciones") or []) if x in DISPOSICIONES and x != disposicion]
    if disposicion is not None and disposicion not in DISPOSICIONES:
        raise ErrorTrd("La disposición final es CT, E, S o M.")
    if datos.get("soporte") is not None and datos["soporte"] not in SOPORTE:
        raise ErrorTrd("El soporte es físico, electrónico o híbrido.")
    for campo, nombre in (("gestion", "gestión"), ("central", "central")):
        x = datos.get(campo)
        if x is not None and (not isinstance(x, int) or isinstance(x, bool) or not 0 <= x <= 100):
            raise ErrorTrd(f"La retención en archivo de {nombre} es un número entero de años entre 0 y 100.")
    if (datos.get("gestion") is not None or datos.get("central") is not None) and disposicion is None:
        raise ErrorTrd("Tiene retención pero no disposición final (CT, E, S o M).")
    otra = db.scalar(select(FilaTrd).where(FilaTrd.version_id == v.id, FilaTrd.estado == "vigente",
                                           FilaTrd.dependencia_id == dep.id, FilaTrd.serie_id == serie.id,
                                           FilaTrd.subserie_id.is_(None) if subserie is None
                                           else FilaTrd.subserie_id == subserie.id))
    if otra is not None and otra is not fila:
        raise ErrorTrd("Esa serie o subserie ya está en la TRD de esa dependencia.", 409)
    valores = dict(dependencia_id=dep.id, serie_id=serie.id, subserie_id=subserie.id if subserie else None, tipos=tipos,
                   gestion=datos.get("gestion"), central=datos.get("central"), disposicion=disposicion,
                   otras_disposiciones=otras, soporte=datos.get("soporte"),
                   procedimiento=(datos.get("procedimiento") or "").strip()[:5000] or None,
                   funcion=_texto(datos.get("funcion"), 300))
    if fila is None:
        fila = FilaTrd(version_id=v.id, **valores)
        db.add(fila)
    else:
        for k, x in valores.items():
            setattr(fila, k, x)
    db.flush()
    registrar(db, modulo="instrumentos", accion="trd_fila_guardada", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=v.fondo_id,
              detalle=f"{v.nombre}: {dep.nombre} · {serie.nombre}" + (f" · {subserie.nombre}" if subserie else ""),
              nuevo={"gestion": valores["gestion"], "central": valores["central"], "disposicion": disposicion})
    return fila


def fila_de(db: Session, fila_id: uuid.UUID) -> tuple[FilaTrd, VersionTrd]:
    f = db.get(FilaTrd, fila_id)
    if f is None:
        raise ErrorTrd("La fila no existe.", 404)
    return f, db.get(VersionTrd, f.version_id)


def anular_fila(db: Session, f: FilaTrd, v: VersionTrd, usuario_id: uuid.UUID) -> None:
    _editable(v)
    f.estado = "anulada"
    db.flush()
    registrar(db, modulo="instrumentos", accion="trd_fila_anulada", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=v.fondo_id, detalle=v.nombre)


# --- Aplicar -------------------------------------------------------------------------------------------


def filas_cuadro(db: Session, v: VersionTrd) -> list[dict]:
    lista = db.scalars(select(FilaTrd).where(FilaTrd.version_id == v.id, FilaTrd.estado == "vigente")
                       .order_by(FilaTrd.creado_en)).all()
    deps = _cargar(db, DependenciaTrd, [f.dependencia_id for f in lista])
    while faltan := [d.superior_id for d in deps.values() if d.superior_id and d.superior_id not in deps]:
        deps |= _cargar(db, DependenciaTrd, faltan)
    terminos = _cargar(db, TerminoBanco, [x for f in lista for x in (f.serie_id, f.subserie_id, *(f.tipos or []))])
    salida = []
    for i, f in enumerate(lista, start=1):
        fc = _fila_cuadro(f, deps, terminos)
        fc.fila = i
        salida.append(fc.a_dict())
    return salida


def _requisitos(v: VersionTrd) -> list[str]:
    faltan = []
    if not v.acto_aprobacion:
        faltan.append("el acto administrativo que la aprueba")
    if not v.fecha_aprobacion:
        faltan.append("la fecha de aprobación")
    if not v.vigente_desde:
        faltan.append("la fecha desde la que rige")
    return faltan


def aplicar(db: Session, v: VersionTrd, usuario_id: uuid.UUID, crear: bool) -> tuple[dict, dict]:
    """Arma la versión en RiC-O y la valida. Con `crear`, si es conforme, la
    deja vigente y pasa la anterior a histórica (vigente hasta el día antes)."""
    _editable(v)
    faltan = _requisitos(v)
    if crear and faltan:
        raise ErrorTrd("Para aplicarla falta " + ", ".join(faltan) + ".")
    datos = filas_cuadro(db, v)
    if not datos:
        raise ErrorTrd("La versión no tiene filas: agregue al menos una serie en la matriz.")
    fondo = db.get(RecursoDocumental, v.fondo_id)
    anterior = db.scalar(select(VersionTrd).where(VersionTrd.fondo_id == v.fondo_id, VersionTrd.estado == "vigente"))
    desde = v.vigente_desde or date.today()
    if anterior is not None and anterior.vigente_desde and desde <= anterior.vigente_desde:
        raise ErrorTrd(f"La versión tiene que regir después de la vigente ({anterior.nombre}, desde "
                       f"{anterior.vigente_desde.isoformat()}).", 409)
    acto = v.acto_aprobacion + (f" del {v.fecha_aprobacion.isoformat()}" if v.fecha_aprobacion else "") \
        if v.acto_aprobacion else None
    info = {"numero": v.numero, "nombre": v.nombre, "acto": acto, "desde": desde}
    try:
        informe, validacion = cuadro.probar_y_aplicar(db, fondo, datos, usuario_id, crear=crear, version=info)
    except cuadro.ErrorCuadro as exc:
        raise ErrorTrd(str(exc), exc.codigo) from exc
    informe["faltan_para_aplicar"] = faltan
    # En RiC una serie existe porque una actividad la produce: se avisa (no se exige: la TRD del AGN
    # no trae la función; sale del manual de funciones y se asigna en la matriz).
    informe["series_sin_funcion"] = [(d["codigos"]["subserie"] or d["codigos"]["serie"] or "") + " "
                                     + (d["subserie"] or d["serie"])["nombre"] for d in datos if not d.get("funcion")]
    if crear and validacion["conforme"]:
        if anterior is not None:
            anterior.estado, anterior.vigente_hasta = "historica", desde - timedelta(days=1)
        v.estado, v.aplicado_por_id = "vigente", usuario_id
        v.aplicado_en = ahora()
        v.informe = {k: x for k, x in informe.items() if k not in ("faltan_para_aplicar", "series_sin_funcion")}
        db.flush()
        registrar(db, modulo="instrumentos", accion="trd_version_aplicada", usuario_id=usuario_id,
                  entidad_tipo="recurso_documental", entidad_id=v.fondo_id,
                  detalle=f"{v.nombre} vigente desde {desde.isoformat()} ({v.acto_aprobacion})"
                          + (f"; la {anterior.nombre} pasa a histórica" if anterior else ""),
                  nuevo={"version": v.numero, "conforme": True, "reglas": informe.get("reglas"),
                         "reglas_reemplazadas": informe.get("reglas_reemplazadas", 0)})
    return informe, validacion


# --- Cargar desde archivo ------------------------------------------------------------------------------


def importar(db: Session, v: VersionTrd, filas_leidas: list[dict], usuario_id: uuid.UUID) -> dict:
    """Llena el borrador con las filas confirmadas en la vista previa de un
    archivo (plantilla o TRD del AGN): crea en el banco y en las dependencias
    lo que falte, reutiliza lo que ya existe por código o por nombre."""
    _editable(v)
    leidas = [cuadro.FilaCuadro.de_dict(d) for d in filas_leidas]
    malas = [f for f in leidas if f.problemas]
    if malas:
        raise ErrorTrd(f"Corrija las {len(malas)} fila(s) con problemas (la primera es la {malas[0].fila}: "
                       f"{malas[0].problemas[0]})")
    fondo = db.get(RecursoDocumental, v.fondo_id)
    informe = {"dependencias": 0, "series": 0, "subseries": 0, "tipos_documentales": 0, "filas": 0, "repetidas": 0,
               "sin_funcion": sum(1 for f in leidas if not f.funcion)}

    def dependencia(nodo: cuadro.Nodo, superior: DependenciaTrd | None) -> DependenciaTrd:
        consulta = select(DependenciaTrd).where(DependenciaTrd.fondo_id == fondo.id, DependenciaTrd.estado == "activa",
                                                DependenciaTrd.superior_id.is_(None) if superior is None
                                                else DependenciaTrd.superior_id == superior.id)
        for d in db.scalars(consulta):
            if (nodo.codigo and d.codigo == nodo.codigo) or (not nodo.codigo and _norm(d.nombre) == _norm(nodo.nombre)):
                return d
        if not nodo.codigo:
            raise ErrorTrd(f"La dependencia «{nodo.nombre}» no tiene código: regístrela en Dependencias.")
        informe["dependencias"] += 1
        return guardar_dependencia(db, fondo, {"codigo": nodo.codigo, "nombre": nodo.nombre,
                                               "superior_id": superior.id if superior else None}, usuario_id)

    def termino(clase: str, nodo: cuadro.Nodo, superior: TerminoBanco | None = None) -> TerminoBanco:
        consulta = select(TerminoBanco).where(TerminoBanco.fondo_id == fondo.id, TerminoBanco.clase == clase,
                                              TerminoBanco.estado == "activo",
                                              TerminoBanco.superior_id.is_(None) if superior is None
                                              else TerminoBanco.superior_id == superior.id)
        for t in db.scalars(consulta):
            if (nodo.codigo and t.codigo == nodo.codigo) or _norm(t.nombre) == _norm(nodo.nombre):
                return t
        clave = {"serie": "series", "subserie": "subseries", "tipo_documental": "tipos_documentales"}[clase]
        informe[clave] += 1
        return guardar_termino(db, fondo, {"clase": clase, "codigo": nodo.codigo, "nombre": nodo.nombre,
                                           "superior_id": superior.id if superior else None}, usuario_id)

    for f in leidas:
        dep = dependencia(f.seccion, None)
        for n in [*f.intermedias, *([f.subseccion] if f.subseccion else [])]:
            dep = dependencia(n, dep)
        if not f.serie.codigo:
            raise ErrorTrd(f"La serie «{f.serie.nombre}» (fila {f.fila}) no tiene código.")
        serie = termino("serie", f.serie)
        subserie = None
        if f.subserie:
            if not f.subserie.codigo:
                raise ErrorTrd(f"La subserie «{f.subserie.nombre}» (fila {f.fila}) no tiene código.")
            subserie = termino("subserie", f.subserie, serie)
        tipos = [termino("tipo_documental", cuadro.Nodo(None, t)).id for t in f.tipos]
        ya = db.scalar(select(FilaTrd.id).where(FilaTrd.version_id == v.id, FilaTrd.estado == "vigente",
                                                FilaTrd.dependencia_id == dep.id, FilaTrd.serie_id == serie.id,
                                                FilaTrd.subserie_id.is_(None) if subserie is None
                                                else FilaTrd.subserie_id == subserie.id))
        if ya:
            informe["repetidas"] += 1
            continue
        db.add(FilaTrd(version_id=v.id, dependencia_id=dep.id, serie_id=serie.id,
                       subserie_id=subserie.id if subserie else None, tipos=tipos, gestion=f.gestion,
                       central=f.central, disposicion=f.disposicion, otras_disposiciones=f.otras_disposiciones,
                       soporte=f.soporte, procedimiento=f.procedimiento, funcion=f.funcion))
        db.flush()
        informe["filas"] += 1
    registrar(db, modulo="instrumentos", accion="trd_importada", usuario_id=usuario_id, entidad_tipo="recurso_documental",
              entidad_id=fondo.id, detalle=f"{v.nombre}: {informe['filas']} fila(s) desde un archivo", nuevo=informe)
    return informe


def cargar(db: Session, fondo: RecursoDocumental, filas_leidas: list[dict], usuario_id: uuid.UUID) -> tuple[VersionTrd, dict]:
    """El punto de partida de la parametrización: con el CCD y la TRD leídos de un
    archivo se configura el borrador completo del fondo (dependencias, banco de
    series, subseries y tipos, y la matriz). Si no hay borrador, se abre uno nuevo
    vacío: la tabla que se carga es la nueva TRD completa, no un ajuste de la vigente."""
    v = db.scalar(select(VersionTrd).where(VersionTrd.fondo_id == fondo.id, VersionTrd.estado == "borrador"))
    if v is None:
        v = crear_version(db, fondo, {}, usuario_id, copiar_vigente=False)
    return v, importar(db, v, filas_leidas, usuario_id)


# --- Fondo nuevo -----------------------------------------------------------------------------------------


def configurar_cuadro_nuevo(db: Session, fondo: RecursoDocumental, filas_leidas: list[dict], usuario_id: uuid.UUID,
                            version: dict | None) -> tuple[dict, dict, dict | None, bool]:
    """El cuadro de un fondo recién registrado, desde las filas del CCD y la TRD.
    Con el acto, su fecha y la vigencia, sale de la versión 1 de la TRD aplicada;
    sin ellos, el cuadro se crea y la versión 1 queda en borrador (`primera_version`).
    Devuelve el informe, la validación RiC-O, lo parametrizado y si la versión vino completa."""
    version = version or {}
    completa = bool(version.get("acto_aprobacion") and version.get("fecha_aprobacion") and version.get("vigente_desde"))
    if completa:
        v = crear_version(db, fondo, version | {"nombre": "TRD versión 1"}, usuario_id, copiar_vigente=False)
        parametrizado = importar(db, v, filas_leidas, usuario_id)
        informe, validacion = aplicar(db, v, usuario_id, crear=True)
        return informe, validacion, parametrizado, True
    informe = cuadro.aplicar(db, fondo, filas_leidas, usuario_id)
    return informe, cuadro.validar_rico(db, fondo), None, False


def primera_version(db: Session, fondo: RecursoDocumental, filas_leidas: list[dict], usuario_id: uuid.UUID,
                    informe: dict) -> dict | None:
    """Sin acto de aprobación, la TRD cargada queda como versión 1 en borrador: falta
    el acto y su vigencia para aplicarla. Si el archivo trae dependencias o series sin
    código, el cuadro se crea igual y la matriz se completa a mano."""
    punto = db.begin_nested()
    try:
        v = crear_version(db, fondo, {"nombre": "TRD versión 1"}, usuario_id, copiar_vigente=False)
        hecho = importar(db, v, filas_leidas, usuario_id)
    except ErrorTrd as exc:
        punto.rollback()
        informe["avisos"].append(f"La matriz de la TRD no se llenó sola ({exc}); complétela en Fondos › "
                                 "Matriz de la TRD.")
        return None
    punto.commit()
    informe["avisos"].append("La TRD quedó como versión 1 en borrador: registre el acto que la aprueba y su vigencia "
                             "y aplíquela en Fondos › Versiones de la TRD.")
    return hecho


def estado_version_1(db: Session, fondo: RecursoDocumental) -> dict | None:
    v1 = db.scalar(select(VersionTrd).where(VersionTrd.fondo_id == fondo.id).order_by(VersionTrd.numero))
    return {"nombre": v1.nombre, "estado": v1.estado} if v1 else None
