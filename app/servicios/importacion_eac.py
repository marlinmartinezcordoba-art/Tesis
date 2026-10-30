"""
Autoridades en EAC-CPF (2.0 de 2022 o la versión de 2010) importadas a la
ficha ISAAR(CPF) del vocabulario de un fondo.

Un EAC-CPF describe una persona, una familia o una entidad: su nombre, sus
otras formas, sus identificadores, sus fechas de existencia, su historia, su
estructura y el área de control. Se lee y se muestra antes de crear nada; al
confirmar:

- si el fondo ya tiene un agente con ese nombre (normalizado), se completa su
  ficha sin pisar lo que ya tenía (lo distinto queda como aviso para revisar);
- si no, se crea el agente, como lo crearía una persona en Autoridades.

Cada campo pasa por las mismas validaciones de la ficha (fechas EDTF,
identificadores con su esquema, idiomas ISO 639-3) y cada cambio queda en la
auditoría. Lo que EAC-CPF trae y la ficha no recibe por este camino (lugares,
funciones y relaciones con otros agentes, que se vinculan en la ficha) queda
contado, con su motivo. Se acepta un archivo o un .zip con varios.
"""

import hashlib
import io
import uuid
import zipfile
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import ESQUEMA_IDENTIFICADOR, EntidadVocabulario
from app.servicios import fechas
from app.servicios.auditoria import registrar
from app.servicios.importacion_ead import _hijos, _texto, _todo, es_eac, raiz_xml

MAX_BYTES = 30 * 1024 * 1024
SUBTIPO = {"person": "persona", "corporatebody": "entidad_corporativa", "family": "familia"}
ESTADO = {"revised": "revisado", "new": "borrador", "derived": "borrador", "cancelled": "borrador",
          "deleted": "borrador", "deletedreplaced": "borrador", "deletedsplit": "borrador"}


class ErrorEac(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


def _uno(e, *ruta):
    actual = e
    for nombre in ruta:
        actual = next(iter(_hijos(actual, nombre)), None) if actual is not None else None
    return actual


def _fecha(e) -> str | None:
    """La fecha estándar de un <date>, <fromDate>/<toDate> (o el texto, si no la trae)."""
    if e is None:
        return None
    return e.get("standardDate") or e.get("standarddate") or (_texto(e) or None)


def _existencia(descripcion) -> str | None:
    existencia = _uno(descripcion, "existDates")
    if existencia is None:
        return None
    rango = next(iter(_todo(existencia, "dateRange")), None)
    if rango is not None:
        desde = _fecha(next(iter(_todo(rango, "fromDate")), None))
        hasta = _fecha(next(iter(_todo(rango, "toDate")), None))
        candidato = f"{desde or '..'}/{hasta or '..'}"
    else:
        candidato = _fecha(next(iter(_todo(existencia, "date")), None))
    if not candidato:
        return None
    try:
        return fechas.interpretar(candidato).edtf
    except fechas.FechaInvalida:
        return None


def _parrafos(e) -> str | None:
    if e is None:
        return None
    partes = [_texto(p) for p in _todo(e, "p")] or [_texto(e)]
    return "\n\n".join(p for p in partes if p) or None


def _nombre(entrada) -> str:
    partes = [_texto(p) for p in _hijos(entrada, "part")]
    return ", ".join(p for p in partes if p) or _texto(entrada)


def leer_autoridad(raiz) -> dict:
    """Lo que dice un EAC-CPF, ya en los campos de la ficha ISAAR."""
    control = _uno(raiz, "control")
    cpf = _uno(raiz, "cpfDescription")
    identidad = _uno(cpf, "identity")
    if identidad is None:
        raise ErrorEac("El EAC-CPF no tiene <identity>: no describe un agente.")
    tipo = _uno(identidad, "entityType")
    valor_tipo = (tipo.get("value") or _texto(tipo) if tipo is not None else "").replace(" ", "").lower()
    subtipo = SUBTIPO.get(valor_tipo)
    if subtipo is None:
        raise ErrorEac(f"Tipo de entidad desconocido en el EAC-CPF: «{valor_tipo or 'sin tipo'}».")
    entradas = _todo(identidad, "nameEntry")
    autorizadas = [n for n in entradas if (n.get("status") or "") == "authorized"] \
        or [n for p in _todo(identidad, "authorizedForm") for n in entradas[:1]] or entradas[:1]
    if not autorizadas:
        raise ErrorEac("El EAC-CPF no trae ningún nombre (<nameEntry>).")
    nombre = _nombre(autorizadas[0])
    otras = []
    for n in entradas:
        if n is autorizadas[0]:
            continue
        idioma = n.get("languageOfElement") or n.get("{http://www.w3.org/XML/1998/namespace}lang")
        otras.append({"nombre": _nombre(n), "tipo": "paralela" if idioma else "otra",
                      "idioma": (idioma or "")[:3].lower() or None})
    identificadores = []
    for i in _todo(identidad, "identityId") + _todo(identidad, "entityId"):
        esquema = (i.get("localType") or "").lower()
        identificadores.append({"esquema": esquema if esquema in ESQUEMA_IDENTIFICADOR else "otro",
                                "valor": _texto(i)})
    descripcion = _uno(cpf, "description")
    campos = {
        "existencia_edtf": _existencia(descripcion) if descripcion is not None else None,
        "historia": _parrafos(_uno(descripcion, "biogHist")) if descripcion is not None else None,
        "estructura": _parrafos(_uno(descripcion, "structureOrGenealogy")) if descripcion is not None else None,
        "contexto_general": _parrafos(_uno(descripcion, "generalContext")) if descripcion is not None else None,
    }
    if subtipo == "persona" and descripcion is not None:
        ocupacion = next(iter(_todo(descripcion, "occupation")), None)
        campos["ocupacion"] = _texto(next(iter(_todo(ocupacion, "term")), ocupacion)) or None if ocupacion is not None \
            else None
    if control is not None:
        agencia = next(iter(_todo(control, "agencyName")), None)
        campos["institucion_responsable"] = _texto(agencia) or None
        fuentes = [_texto(s) for s in _todo(control, "source")]
        campos["fuentes"] = "; ".join(f for f in fuentes if f) or None
        convencion = next(iter(_todo(control, "conventionDeclaration")), None)
        campos["reglas"] = (_texto(convencion) or None)[:200] if convencion is not None and _texto(convencion) else None
        lenguas = [x.get("languageCode") for x in _todo(control, "languageDeclaration") if x.get("languageCode")] + \
            [x.get("languageCode") for x in _todo(control, "language") if x.get("languageCode")]
        campos["lenguas"] = [x[:3].lower() for x in lenguas] or None
        estado = (control.get("maintenanceStatus") or _texto(_uno(control, "maintenanceStatus")) or "")
        campos["estado_elaboracion"] = ESTADO.get(estado.replace(" ", "").lower())
        registro = _texto(_uno(control, "recordId"))
        campos["notas_mantenimiento"] = (f"Importada de EAC-CPF (registro {registro}"
                                         + (f", {campos['institucion_responsable']}" if campos.get("institucion_responsable")
                                            else "") + ").") if registro else "Importada de EAC-CPF."
    omitidas = Counter()
    if descripcion is not None:
        for nombre_el, motivo in (("place", "lugares (vincúlelos en la ficha)"),
                                  ("function", "funciones (vincúlelas en la ficha)"),
                                  ("mandate", "mandatos (vincúlelos en la ficha)"),
                                  ("legalStatus", "estatuto jurídico (elíjalo en la ficha: pública, privada o mixta)")):
            if _todo(descripcion, nombre_el):
                omitidas[motivo] += len(_todo(descripcion, nombre_el))
    relaciones = _todo(cpf, "cpfRelation") + _todo(cpf, "relation")
    if relaciones:
        omitidas["relaciones con otros agentes o recursos (se registran en la ficha, «Vínculos»)"] += len(relaciones)
    return {"nombre": nombre, "subtipo": subtipo, "otras_formas": [o for o in otras if o["nombre"]],
            "identificadores": [i for i in identificadores if i["valor"]],
            "campos": {k: v for k, v in campos.items() if v}, "omitidas": dict(omitidas)}


def _archivos(contenido: bytes, nombre: str) -> list[tuple[str, bytes]]:
    if len(contenido) > MAX_BYTES:
        raise ErrorEac("El archivo pasa de 30 MB.", 413)
    if nombre.lower().endswith(".zip"):
        try:
            paquete = zipfile.ZipFile(io.BytesIO(contenido))
        except zipfile.BadZipFile as exc:
            raise ErrorEac("El .zip está dañado.") from exc
        salida = []
        for info in sorted(paquete.infolist(), key=lambda i: i.filename):
            if info.is_dir() or not info.filename.lower().endswith(".xml") or "__MACOSX" in info.filename:
                continue
            if info.file_size > MAX_BYTES:
                raise ErrorEac(f"«{info.filename}» es demasiado grande.", 413)
            salida.append((info.filename.rsplit("/", 1)[-1], paquete.read(info)))
        if not salida:
            raise ErrorEac("El .zip no trae archivos .xml.")
        return salida[:500]
    return [(nombre, contenido)]


def leer(contenido: bytes, nombre: str) -> list[dict]:
    autoridades = []
    for archivo, datos in _archivos(contenido, nombre):
        raiz = raiz_xml(datos)
        if not es_eac(raiz):
            autoridades.append({"archivo": archivo, "error": "No es un EAC-CPF (la raíz no es <eac-cpf> ni <eac>)."})
            continue
        try:
            autoridades.append({"archivo": archivo, **leer_autoridad(raiz)})
        except ErrorEac as exc:
            autoridades.append({"archivo": archivo, "error": str(exc)})
    return autoridades


def _existente(db: Session, fondo_id: uuid.UUID, nombre: str) -> EntidadVocabulario | None:
    from app.servicios.vocabulario import del_fondo_o_compartida, normalizar

    # Las autoridades son de la institución: completa la que ya exista en cualquier fondo (la de este primero).
    return db.scalar(select(EntidadVocabulario).where(
        del_fondo_o_compartida(fondo_id), EntidadVocabulario.clase == "agente",
        EntidadVocabulario.estado == "activa", EntidadVocabulario.nombre_normalizado == normalizar(nombre))
        .order_by(EntidadVocabulario.fondo_id != fondo_id, EntidadVocabulario.creado_en).limit(1))


def vista_previa(db: Session, fondo_id: uuid.UUID, contenido: bytes, nombre: str) -> dict:
    autoridades = leer(contenido, nombre)
    for a in autoridades:
        if "error" not in a:
            e = _existente(db, fondo_id, a["nombre"])
            a["accion"] = "completar" if e is not None else "crear"
            a["existente_id"] = str(e.id) if e is not None else None
            if e is not None and e.fondo_id != fondo_id:  # autoridad compartida, registrada en otro fondo
                from app.models.recurso_documental import RecursoDocumental

                a["fondo_registro"] = db.get(RecursoDocumental, e.fondo_id).titulo
    return {"autoridades": autoridades, "huella": hashlib.sha256(contenido).hexdigest(),
            "resumen": {"crear": sum(1 for a in autoridades if a.get("accion") == "crear"),
                        "completar": sum(1 for a in autoridades if a.get("accion") == "completar"),
                        "con_error": sum(1 for a in autoridades if "error" in a)}}


def importar(db: Session, fondo_id: uuid.UUID, contenido: bytes, nombre: str, usuario_id: uuid.UUID) -> dict:
    """Crea o completa los agentes. Todo o nada: si una ficha no pasa las validaciones, no queda ninguna."""
    from app.servicios import autoridad, vocabulario

    autoridades = leer(contenido, nombre)
    malas = [a for a in autoridades if "error" in a]
    if malas:
        raise ErrorEac(f"«{malas[0]['archivo']}»: {malas[0]['error']}")
    informe = {"creadas": 0, "completadas": 0, "avisos": [], "omitidas": Counter()}
    punto = db.begin_nested()
    try:
        for a in autoridades:
            e = _existente(db, fondo_id, a["nombre"])
            if e is None:
                e = vocabulario.crear(db, fondo_id=fondo_id, clase="agente", nombre=a["nombre"], subtipo=a["subtipo"],
                                      origen="persona", confianza=None, motor=None, usuario_id=usuario_id)
                db.flush()
                informe["creadas"] += 1
            else:
                informe["completadas"] += 1
                if e.subtipo != a["subtipo"]:
                    informe["avisos"].append(f"«{e.nombre}» es {e.subtipo} aquí y {a['subtipo']} en el EAC-CPF: "
                                             "se dejó como estaba.")
            cambios = {}
            for campo, valor in a["campos"].items():
                actual = getattr(e, campo, None)
                if actual in (None, "", []):
                    cambios[campo] = valor
                elif actual != valor and campo not in ("notas_mantenimiento",):
                    informe["avisos"].append(f"«{e.nombre}»: el campo «{campo}» ya tenía un valor distinto; se "
                                             "conservó (revise la ficha).")
            if cambios:
                autoridad.actualizar(db, e, cambios, usuario_id)
            for o in a["otras_formas"]:
                try:
                    autoridad.agregar_nombre(db, e, tipo=o["tipo"], nombre=o["nombre"], idioma=o["idioma"],
                                             regla=None, vigencia_edtf=None, usuario_id=usuario_id)
                except autoridad.ErrorAutoridad as exc:
                    informe["avisos"].append(f"«{e.nombre}», forma «{o['nombre']}»: {exc}")
            for i in a["identificadores"]:
                try:
                    autoridad.agregar_identificador(db, e, esquema=i["esquema"], valor=i["valor"], usuario_id=usuario_id)
                except autoridad.ErrorAutoridad as exc:
                    informe["avisos"].append(f"«{e.nombre}», identificador {i['valor']}: {exc}")
            informe["omitidas"].update(a["omitidas"])
        registrar(db, modulo="vocabularios", accion="eac_importado", usuario_id=usuario_id,
                  entidad_tipo="recurso_documental", entidad_id=fondo_id,
                  detalle=f"{len(autoridades)} autoridad(es) de {nombre}",
                  nuevo={"huella": hashlib.sha256(contenido).hexdigest(), "creadas": informe["creadas"],
                         "completadas": informe["completadas"]})
    except autoridad.ErrorAutoridad as exc:
        punto.rollback()
        raise ErrorEac(str(exc)) from exc
    except Exception:
        punto.rollback()
        raise
    punto.commit()
    informe["omitidas"] = dict(informe["omitidas"])
    return informe
