"""Precarga de los instrumentos archivísticos en M5 (insumo obligatorio
antes de encender el motor de análisis, según la especificación):

- La Tabla de Retención Documental (TRD) alimenta, por cada serie o
  subserie de cada oficina productora, un Mandato (RiC-E17) que carga la
  retención y la disposición final, una Actividad (RiC-E15, la función)
  ligada a ese Mandato y ejecutada por la oficina, y las formas
  documentales (tipos documentales) que produce esa serie. Así lo corrige
  la especificación v3: la retención varía serie por serie, no por forma
  documental.
- El Cuadro de Clasificación Documental alimenta las actividades/funciones
  y su dependencia responsable.
- El organigrama alimenta las entidades corporativas con su jerarquía y,
  si trae funcionarios, las personas con su cargo y la oficina en la que
  ejercen.

Sin esto, CC-05 no tiene contra qué verificar y el motor propondría una
función o un agente nuevo por documento.

Cada instrumento se acepta como CSV (separador , o ;, encabezados en
español) o como JSON con la misma estructura que la semilla del
Ministerio de Ambiente (ric/fixtures/mads). Cada fila es idempotente: se
busca por código o por nombre y se actualiza, nunca se duplica, y solo se
reescribe (dejando versión en el historial) cuando algo cambió de verdad.
"""

import csv
import datetime
import io
import json
import re
import unicodedata
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from .models import Activity, CorporateBody, EventoRiC, FormaDocumental, Mandate, Person, RelacionRiC, registrar_evento

# Relaciones RiC-CM verificadas (ric_matrix.json) que materializan cada instrumento.
R_ACTIVIDAD_EJECUTADA_POR = "R060"  # Activity -> Agent "is or was performed by"
R_SUBORDINADO = "R045"  # Agent -> Agent "has or had subordinate"
R_REGULA = "R063"  # Rule -> Thing "regulates or regulated" (Mandato de la serie -> Actividad)
R_MIEMBRO = "R055"  # Group -> Person "has or had member" (oficina -> funcionario)

COLUMNAS = {
    "trd": {
        "obligatorias": ("serie",),
        "opcionales": (
            "codigo_oficina", "oficina", "codigo_serie", "codigo_subserie", "subserie",
            "tipos_documentales", "forma_documental", "definicion", "soporte",
            "retencion_gestion", "retencion_central", "disposicion_final", "procedimiento", "vigencia",
        ),
    },
    "ccd": {"obligatorias": ("funcion",), "opcionales": ("tipo", "dependencia", "descripcion")},
    "organigrama": {
        "obligatorias": ("dependencia",),
        "opcionales": ("dependencia_superior", "sigla", "codigo", "funcionario", "cargo"),
    },
}
_DISPOSICIONES = {
    "conservacion total": "CT", "ct": "CT",
    "eliminacion": "E", "e": "E",
    "seleccion": "S", "s": "S",
    "medio tecnologico": "MT", "mt": "MT", "digitalizacion": "MT", "d": "MT", "m/d": "MT", "m": "MT",
}
_CAMPO_DISPOSICION = {codigo: campo for campo, codigo, _ in Mandate.DISPOSICIONES}
TIPO_MANDATO_TRD = "Tabla de Retención Documental"
TIPO_ACTIVIDAD_SERIE = "serie TRD"


class ErrorDeImportacion(Exception):
    pass


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.strip().lower().replace(" ", "_").replace("/", "_")


def leer_csv(contenido):
    """Filas como dicts con claves normalizadas (sin tildes, minúsculas,
    espacios -> _). Detecta el separador (; o ,)."""
    if isinstance(contenido, bytes):
        try:
            contenido = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            contenido = contenido.decode("latin-1")
    muestra = contenido[:2048]
    separador = ";" if muestra.count(";") > muestra.count(",") else ","
    lector = csv.DictReader(io.StringIO(contenido), delimiter=separador)
    filas = []
    for fila in lector:
        limpia = {_normalizar(k): (v or "").strip() for k, v in fila.items() if k}
        if any(limpia.values()):
            filas.append(limpia)
    return filas


def _es_json(contenido):
    if isinstance(contenido, bytes):
        contenido = contenido.lstrip(b"\xef\xbb\xbf")
    return contenido.lstrip()[:1] in ("[", "{", b"[", b"{")


def _leer_json(contenido):
    if isinstance(contenido, bytes):
        contenido = contenido.decode("utf-8-sig")
    try:
        return json.loads(contenido)
    except json.JSONDecodeError as e:
        raise ErrorDeImportacion(f"El JSON no se pudo leer: {e}.")


def _validar_columnas(filas, tipo):
    if not filas:
        raise ErrorDeImportacion("El archivo no tiene filas con datos.")
    faltan = [c for c in COLUMNAS[tipo]["obligatorias"] if c not in filas[0]]
    if faltan:
        raise ErrorDeImportacion(
            f"Faltan las columnas obligatorias: {', '.join(faltan)}. "
            f"Columnas esperadas: {', '.join(COLUMNAS[tipo]['obligatorias'] + COLUMNAS[tipo]['opcionales'])}."
        )


def _entero(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return int(valor)
    try:
        return int(float(str(valor).replace(",", ".")))
    except ValueError:
        return None


def _fecha(valor):
    if not valor:
        return None
    if isinstance(valor, datetime.date):
        return valor
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(str(valor).strip(), formato).date()
        except ValueError:
            continue
    return None


def _codigos_disposicion(valor):
    """Las casillas CT/E/MT/S de la TRD a partir de un dict {"CT": true},
    una lista ["CT", "S"] o un texto "CT, S" / "Conservación total"."""
    if not valor:
        return set()
    if isinstance(valor, dict):
        return {_DISPOSICIONES.get(str(k).strip().lower()) for k, v in valor.items() if v} - {None}
    if isinstance(valor, str):
        valor = re.split(r"[,;+/]", valor.lower().replace("m/d", "mt"))
    codigos = set()
    for parte in valor:
        clave = _normalizar(str(parte)).replace("_", " ")
        if clave in _DISPOSICIONES:
            codigos.add(_DISPOSICIONES[clave])
    return codigos


def _sentencia(texto):
    """'PROYECTOS DE LEY' -> 'Proyectos de ley'; deja igual lo que no esté todo en mayúsculas."""
    texto = (texto or "").strip()
    if texto.isupper():
        return texto[:1] + texto[1:].lower()
    return texto


def _asignar(objeto, **valores):
    """Asigna solo lo que cambia y dice si hubo cambio — así una recarga
    idéntica no deja versiones vacías en el historial (F07)."""
    cambio = False
    for campo, valor in valores.items():
        if valor is None or valor == "":
            continue
        if getattr(objeto, campo) != valor:
            setattr(objeto, campo, valor)
            cambio = True
    return cambio


def _relacion_manual(origen, destino, relacion_id, usuario):
    ya = RelacionRiC.objects.filter(
        relacion_id=relacion_id,
        origen_content_type__model=type(origen).__name__.lower(), origen_object_id=origen.pk,
        destino_content_type__model=type(destino).__name__.lower(), destino_object_id=destino.pk,
    ).exists()
    if ya:
        return False
    RelacionRiC(
        relacion_id=relacion_id, origen=origen, destino=destino, validado_por=usuario,
        fecha_validacion=timezone.now(), estado=RelacionRiC.Estado.ACEPTADA,
        fuente_relacion="Instrumento archivístico precargado (M5)",
    ).save()
    return True


def _corporativa(nombre, usuario, codigo=""):
    """Oficina por código (RiC-A22 identificador) si lo hay, si no por nombre."""
    entidad = None
    if codigo:
        entidad = CorporateBody.objects.filter(identificador=codigo).first()
    if entidad is None and nombre:
        entidad = CorporateBody.objects.filter(nombre=nombre).first()
    if entidad is None:
        entidad = CorporateBody.objects.create(nombre=nombre or codigo, identificador=codigo, creado_por=usuario)
        return entidad, True
    # Encontrada por código: el nombre autorizado ya registrado (organigrama)
    # manda; la TRD puede escribirlo con una variante y no debe renombrarla.
    if _asignar(entidad, identificador=codigo):
        entidad.modificado_por = usuario
        entidad.save()
    return entidad, False


# ---------------------------------------------------------------------------
# TRD
# ---------------------------------------------------------------------------

def _series_desde_json(datos):
    """Acepta la lista de oficinas de la semilla MADS ({codigo_oficina,
    nombre_oficina, vigencia, series: [...]}) o un objeto {"oficinas": [...]}."""
    if isinstance(datos, dict):
        datos = datos.get("oficinas") or datos.get("series") or []
    if not isinstance(datos, list):
        raise ErrorDeImportacion("El JSON de la TRD debe ser una lista de oficinas con sus series.")
    oficinas = []
    for o in datos:
        if "series" not in o:  # lista plana de series con su oficina dentro
            o = {"codigo_oficina": o.get("codigo_oficina", ""), "nombre_oficina": o.get("oficina", ""), "vigencia": o.get("vigencia"), "series": [o]}
        oficinas.append({
            "codigo": str(o.get("codigo_oficina") or o.get("codigo") or "").strip(),
            "nombre": (o.get("nombre_oficina") or o.get("oficina") or o.get("nombre") or "").strip(),
            "vigencia": o.get("vigencia"),
            "series": [{
                "codigo_serie": str(s.get("codigo_serie") or "").strip(),
                "codigo_subserie": str(s.get("codigo_subserie") or "").strip(),
                "serie": (s.get("nombre_serie") or s.get("serie") or "").strip(),
                "subserie": (s.get("nombre_subserie") or s.get("subserie") or "").strip(),
                "tipos": [t.strip() for t in (s.get("tipos_documentales") or []) if t and t.strip()],
                "soporte": ", ".join(s["soporte"]) if isinstance(s.get("soporte"), list) else (s.get("soporte") or ""),
                "gestion": _entero(s.get("archivo_gestion_anios", s.get("retencion_gestion"))),
                "central": _entero(s.get("archivo_central_anios", s.get("retencion_central"))),
                "disposicion": _codigos_disposicion(s.get("disposicion_final")),
                "procedimiento": (s.get("procedimiento_resumen") or s.get("procedimiento") or "").strip(),
                "vigencia": s.get("vigencia") or o.get("vigencia"),
            } for s in o.get("series", []) if (s.get("nombre_serie") or s.get("serie"))],
        })
    return oficinas


def _series_desde_csv(filas):
    """Una fila por serie (tipos separados por |) o una fila por tipo
    documental (columna forma_documental): se agrupan por oficina y serie."""
    oficinas = {}
    for fila in filas:
        if not fila.get("serie"):
            continue
        clave_oficina = (fila.get("codigo_oficina", ""), fila.get("oficina", ""))
        oficina = oficinas.setdefault(clave_oficina, {"codigo": clave_oficina[0], "nombre": clave_oficina[1], "vigencia": fila.get("vigencia"), "series": {}})
        clave_serie = (fila.get("codigo_serie", ""), fila.get("codigo_subserie", ""), fila["serie"], fila.get("subserie", ""))
        serie = oficina["series"].setdefault(clave_serie, {
            "codigo_serie": clave_serie[0], "codigo_subserie": clave_serie[1], "serie": clave_serie[2], "subserie": clave_serie[3],
            "tipos": [], "definiciones": {}, "soporte": fila.get("soporte", ""),
            "gestion": _entero(fila.get("retencion_gestion")), "central": _entero(fila.get("retencion_central")),
            "disposicion": _codigos_disposicion(fila.get("disposicion_final")),
            "procedimiento": fila.get("procedimiento", ""), "vigencia": fila.get("vigencia"),
        })
        tipos = [t.strip() for t in fila.get("tipos_documentales", "").split("|") if t.strip()]
        if fila.get("forma_documental"):
            tipos.append(fila["forma_documental"])
            if fila.get("definicion"):
                serie["definiciones"][fila["forma_documental"]] = fila["definicion"]
        for t in tipos:
            if t not in serie["tipos"]:
                serie["tipos"].append(t)
    return [{**o, "series": list(o["series"].values())} for o in oficinas.values()]


def _identificador_serie(codigo_oficina, serie):
    codigo = serie["codigo_serie"]
    if codigo and serie["codigo_subserie"]:
        codigo = f"{codigo}.{serie['codigo_subserie']}"
    partes = [p for p in (codigo_oficina, codigo) if p]
    return f"TRD {'-'.join(partes)}" if partes else ""


def _buscar_o_crear(modelo, identificador, nombre, usuario, **valores):
    """Busca por identificador (o por nombre si no lo hay); crea con todos
    los valores de una vez, o actualiza solo si algo cambió. Devuelve
    (objeto, creado)."""
    obj = None
    if identificador:
        obj = modelo.objects.filter(identificador=identificador).first()
    if obj is None:
        obj = modelo.objects.filter(nombre=nombre, identificador=identificador).first()
    if obj is None:
        limpios = {k: v for k, v in valores.items() if v is not None and v != ""}
        return modelo.objects.create(nombre=nombre, identificador=identificador, creado_por=usuario, **limpios), True
    if _asignar(obj, nombre=nombre, **valores):
        obj.modificado_por = usuario
        obj.save()
    return obj, False


def cargar_series(oficinas, usuario):
    """El corazón de la TRD: por cada serie/subserie de cada oficina, un
    Mandato con la retención, una Actividad (función) ligada a él y a la
    oficina, y sus formas documentales."""
    resumen = {"oficinas": 0, "mandatos": 0, "actividades": 0, "formas": 0, "vinculos": 0, "relaciones": 0, "series": 0}
    for oficina in oficinas:
        dependencia = None
        if oficina["codigo"] or oficina["nombre"]:
            dependencia, creada = _corporativa(oficina["nombre"], usuario, codigo=oficina["codigo"])
            resumen["oficinas"] += creada
        for serie in oficina["series"]:
            resumen["series"] += 1
            identificador = _identificador_serie(oficina["codigo"], serie)
            nombre_serie = _sentencia(serie["serie"])
            if serie["subserie"]:
                nombre_serie = f"{nombre_serie} · {_sentencia(serie['subserie'])}"
            etiqueta_trd = identificador or "TRD"
            nombre_mandato = f"{etiqueta_trd} {nombre_serie}"
            descripcion = f"Serie de la Tabla de Retención Documental"
            if dependencia is not None:
                descripcion += f" · oficina productora {oficina['codigo'] + ' ' if oficina['codigo'] else ''}{dependencia.nombre}"

            valores = dict(
                tipo_mandato=TIPO_MANDATO_TRD, descripcion_general=descripcion,
                codigo_serie=serie["codigo_serie"], codigo_subserie=serie["codigo_subserie"], serie_trd=nombre_serie,
                tiempo_retencion_archivo_gestion=serie["gestion"], tiempo_retencion_archivo_central=serie["central"],
                soporte=serie["soporte"], procedimiento=serie["procedimiento"], vigencia=_fecha(serie["vigencia"]),
            )
            if serie["disposicion"]:
                valores.update({campo: codigo in serie["disposicion"] for codigo, campo in _CAMPO_DISPOSICION.items()})
            mandato, creado = _buscar_o_crear(Mandate, identificador, nombre_mandato, usuario, **valores)
            resumen["mandatos"] += creado

            nombre_actividad = f"{nombre_serie} · {dependencia.nombre}" if dependencia is not None else nombre_serie
            actividad, creada = _buscar_o_crear(
                Activity, identificador, nombre_actividad, usuario,
                tipo_actividad=TIPO_ACTIVIDAD_SERIE, mandato=mandato, serie_trd=nombre_serie,
            )
            resumen["actividades"] += creada
            resumen["relaciones"] += _relacion_manual(mandato, actividad, R_REGULA, usuario)
            if dependencia is not None:
                resumen["relaciones"] += _relacion_manual(actividad, dependencia, R_ACTIVIDAD_EJECUTADA_POR, usuario)

            existentes = set(actividad.formas_documentales.values_list("pk", flat=True))
            for nombre_tipo in serie["tipos"]:
                forma = FormaDocumental.objects.filter(nombre__iexact=nombre_tipo).first()
                if forma is None:
                    forma = FormaDocumental.objects.create(nombre=nombre_tipo, creado_por=usuario, definicion=serie.get("definiciones", {}).get(nombre_tipo, ""))
                    resumen["formas"] += 1
                elif serie.get("definiciones", {}).get(nombre_tipo) and not forma.definicion:
                    forma.definicion = serie["definiciones"][nombre_tipo]
                    forma.modificado_por = usuario
                    forma.save()
                if forma.pk not in existentes:
                    actividad.formas_documentales.add(forma)
                    existentes.add(forma.pk)
                    resumen["vinculos"] += 1
                if not forma.serie_trd:
                    forma.serie_trd = nombre_serie
                    forma.save(update_fields=["serie_trd"])
    return resumen


@transaction.atomic
def importar_trd(contenido, usuario):
    if _es_json(contenido):
        oficinas = _series_desde_json(_leer_json(contenido))
        filas = sum(len(o["series"]) for o in oficinas)
    else:
        filas_csv = leer_csv(contenido)
        _validar_columnas(filas_csv, "trd")
        oficinas = _series_desde_csv(filas_csv)
        filas = len(filas_csv)
    if not oficinas:
        raise ErrorDeImportacion("El archivo no tiene series con datos.")
    resumen = cargar_series(oficinas, usuario)
    registrar_evento(None, EventoRiC.Tipo.INGESTA, agente=usuario, detalle={"instrumento": "TRD", **resumen})
    return {"series": resumen["series"], "mandatos": resumen["mandatos"], "actividades": resumen["actividades"],
            "formas_documentales": resumen["formas"], "relaciones": resumen["relaciones"], "filas": filas}


# ---------------------------------------------------------------------------
# CCD
# ---------------------------------------------------------------------------

@transaction.atomic
def importar_ccd(contenido, usuario):
    filas = leer_csv(contenido)
    _validar_columnas(filas, "ccd")
    creadas = actualizadas = relaciones = 0
    for fila in filas:
        nombre = fila["funcion"]
        if not nombre:
            continue
        actividad, creada = Activity.objects.get_or_create(nombre=nombre, defaults={"creado_por": usuario})
        tipo = _normalizar(fila.get("tipo", "")).replace("_", " ")
        if _asignar(actividad, tipo_actividad=tipo, descripcion_general=fila.get("descripcion", "")) or creada:
            actividad.modificado_por = usuario
            actividad.save()
        creadas += creada
        actualizadas += not creada
        if fila.get("dependencia"):
            dependencia, _ = _corporativa(fila["dependencia"], usuario)
            relaciones += _relacion_manual(actividad, dependencia, R_ACTIVIDAD_EJECUTADA_POR, usuario)
    registrar_evento(None, EventoRiC.Tipo.INGESTA, agente=usuario, detalle={"instrumento": "CCD", "creadas": creadas, "actualizadas": actualizadas, "relaciones": relaciones})
    return {"creadas": creadas, "actualizadas": actualizadas, "relaciones": relaciones, "filas": len(filas)}


# ---------------------------------------------------------------------------
# Organigrama
# ---------------------------------------------------------------------------

def _organigrama_desde_json(datos):
    """{"entidades": [[codigo, nombre, superior_codigo], ...],
    "personas": [[nombre, cargo, codigo_entidad], ...]} (la semilla MADS)."""
    if not isinstance(datos, dict) or "entidades" not in datos:
        raise ErrorDeImportacion('El JSON del organigrama debe tener "entidades" y, opcionalmente, "personas".')
    entidades = [{"codigo": str(e[0] or ""), "nombre": e[1], "superior": str(e[2] or "")} for e in datos["entidades"]]
    personas = [{"nombre": p[0], "cargo": p[1], "codigo": str(p[2] or "")} for p in datos.get("personas", [])]
    return entidades, personas


def _organigrama_desde_csv(filas):
    entidades, personas = [], []
    for fila in filas:
        if not fila.get("dependencia"):
            continue
        codigo = fila.get("codigo") or fila.get("sigla", "")
        entidades.append({"codigo": codigo, "nombre": fila["dependencia"], "superior": fila.get("dependencia_superior", "")})
        if fila.get("funcionario"):
            personas.append({"nombre": fila["funcionario"], "cargo": fila.get("cargo", ""), "codigo": codigo or fila["dependencia"]})
    return entidades, personas


@transaction.atomic
def importar_organigrama(contenido, usuario):
    if _es_json(contenido):
        entidades, personas = _organigrama_desde_json(_leer_json(contenido))
        filas = len(entidades) + len(personas)
    else:
        filas_csv = leer_csv(contenido)
        _validar_columnas(filas_csv, "organigrama")
        entidades, personas = _organigrama_desde_csv(filas_csv)
        filas = len(filas_csv)
    creadas = relaciones = funcionarios = 0
    por_clave = {}
    for e in entidades:
        dependencia, creada = _corporativa(e["nombre"], usuario, codigo=e["codigo"])
        creadas += creada
        por_clave[e["codigo"] or e["nombre"]] = dependencia
        por_clave.setdefault(e["nombre"], dependencia)
    for e in entidades:
        if not e["superior"]:
            continue
        superior = por_clave.get(e["superior"])
        if superior is None:
            superior, _ = _corporativa(e["superior"], usuario)
            por_clave[e["superior"]] = superior
        relaciones += _relacion_manual(superior, por_clave[e["codigo"] or e["nombre"]], R_SUBORDINADO, usuario)
    for p in personas:
        if not p["nombre"]:
            continue
        persona, creada = Person.objects.get_or_create(nombre=p["nombre"], defaults={"creado_por": usuario, "tipo_ocupacion": p["cargo"]})
        funcionarios += creada
        if not creada and _asignar(persona, tipo_ocupacion=p["cargo"]):
            persona.modificado_por = usuario
            persona.save()
        oficina = por_clave.get(p["codigo"])
        if oficina is not None:
            relaciones += _relacion_manual(oficina, persona, R_MIEMBRO, usuario)
    registrar_evento(None, EventoRiC.Tipo.INGESTA, agente=usuario, detalle={"instrumento": "organigrama", "creadas": creadas, "funcionarios": funcionarios, "relaciones": relaciones})
    return {"creadas": creadas, "funcionarios": funcionarios, "relaciones": relaciones, "filas": filas}


IMPORTADORES = {"trd": importar_trd, "ccd": importar_ccd, "organigrama": importar_organigrama}


# ---------------------------------------------------------------------------
# Semilla MADS (ric/fixtures/mads): organigrama + 54 TRD oficiales
# ---------------------------------------------------------------------------

RUTA_SEMILLA_MADS = Path(__file__).resolve().parent / "fixtures" / "mads"


def semilla_mads_disponible():
    return (RUTA_SEMILLA_MADS / "organigrama.json").exists() and (RUTA_SEMILLA_MADS / "trd.json").exists()


def sembrar_mads(usuario):
    """Carga primero el organigrama (para que cada serie encuentre su oficina
    por código) y después las TRD. Devuelve los dos resúmenes."""
    if not semilla_mads_disponible():
        raise ErrorDeImportacion("La semilla MADS no está en ric/fixtures/mads.")
    organigrama = importar_organigrama((RUTA_SEMILLA_MADS / "organigrama.json").read_bytes(), usuario)
    trd = importar_trd((RUTA_SEMILLA_MADS / "trd.json").read_bytes(), usuario)
    return {"organigrama": organigrama, "trd": trd}
