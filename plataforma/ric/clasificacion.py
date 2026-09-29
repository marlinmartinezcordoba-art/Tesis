"""Clasificación documental en la lógica de RiC: el cuadro de clasificación
materializado como Record Sets (RiC-E03) encadenados por inclusión.

    Fondo (la entidad)  >  Sección (oficina productora)  >  Serie / subserie
    (de la TRD)  >  Expediente  >  Documento (Record)  >  Archivo (Instantiation)

- La serie como Record Set "documenta" la Actividad de la TRD (R033) y, por
  ella, hereda la retención y la disposición final del Mandato. El
  expediente hereda la de su serie; el documento, la de su expediente.
- Sección y serie tienen procedencia (R026) en la oficina productora.
- `padre` / `record_set` son la referencia de conveniencia que permite la
  especificación v3; la pertenencia (incluida la múltiple) queda además como
  relación R024 "includes or included", validada contra la matriz RiC-CM.

Fondo, sección y serie se crean solos la primera vez que se usan, a partir
del organigrama y la TRD ya cargados en M5. Nada se duplica: cada nivel se
busca por su código (RiC-A22).
"""

from pathlib import Path

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q

from .instrumentos import R_ACTIVIDAD_EJECUTADA_POR, R_SUBORDINADO, _relacion_manual
from .models import Activity, CorporateBody, EventoRiC, Instantiation, Record, RecordSet, RelacionRiC, registrar_evento

R_INCLUYE = "R024"  # Record Set -> Record o Record Set "includes or included"
R_DOCUMENTA = "R033"  # Record Resource -> Activity "documents"
R_PROCEDENCIA = "R026"  # Record Resource -> Agent "has provenance"


def _ct(modelo):
    return ContentType.objects.get_for_model(modelo)


def entidad_raiz():
    """La entidad productora del fondo: la dependencia del organigrama que
    no depende de ninguna otra (origen de R045 sin ser destino de ninguna)."""
    ct = _ct(CorporateBody)
    subordinadas = RelacionRiC.objects.filter(relacion_id=R_SUBORDINADO, destino_content_type=ct).values_list("destino_object_id", flat=True)
    superiores = RelacionRiC.objects.filter(relacion_id=R_SUBORDINADO, origen_content_type=ct).values_list("origen_object_id", flat=True)
    raiz = CorporateBody.objects.filter(pk__in=superiores).exclude(pk__in=subordinadas).order_by("pk").first()
    return raiz or CorporateBody.objects.order_by("pk").first()


def oficina_de(actividad):
    """La oficina productora de una serie: destino de R060 desde su actividad."""
    rel = RelacionRiC.objects.filter(
        relacion_id=R_ACTIVIDAD_EJECUTADA_POR, origen_content_type=_ct(Activity), origen_object_id=actividad.pk,
    ).first()
    return rel.destino if rel is not None else None


def _conjunto(identificador, tipo, nombre, usuario, **valores):
    conjunto = RecordSet.objects.filter(identificador=identificador, tipo_conjunto=tipo).first() if identificador else None
    if conjunto is None:
        conjunto = RecordSet.objects.create(identificador=identificador, tipo_conjunto=tipo, nombre=nombre, creado_por=usuario, **valores)
        return conjunto, True
    return conjunto, False


def conjunto_fondo(usuario):
    raiz = entidad_raiz()
    if raiz is None:
        fondo, _ = _conjunto("FONDO", RecordSet.Tipo.FONDO, "Fondo documental", usuario)
        return fondo
    fondo, creado = _conjunto(f"FONDO {raiz.identificador or raiz.pk}", RecordSet.Tipo.FONDO, raiz.nombre, usuario)
    if creado:
        _relacion_manual(fondo, raiz, R_PROCEDENCIA, usuario)
    return fondo


def conjunto_seccion(oficina, usuario):
    fondo = conjunto_fondo(usuario)
    seccion, creada = _conjunto(f"SEC {oficina.identificador or oficina.pk}", RecordSet.Tipo.SECCION, oficina.nombre, usuario, padre=fondo)
    if creada:
        _relacion_manual(fondo, seccion, R_INCLUYE, usuario)
        _relacion_manual(seccion, oficina, R_PROCEDENCIA, usuario)
    return seccion


def conjunto_serie(actividad, usuario):
    """La serie o subserie de la TRD como Record Set, colgada de la sección
    de su oficina productora (o del fondo si la serie no tiene oficina)."""
    existente = RecordSet.objects.filter(actividad=actividad, tipo_conjunto__in=(RecordSet.Tipo.SERIE, RecordSet.Tipo.SUBSERIE)).first()
    if existente is not None:
        return existente
    oficina = oficina_de(actividad)
    padre = conjunto_seccion(oficina, usuario) if isinstance(oficina, CorporateBody) else conjunto_fondo(usuario)
    mandato = actividad.mandato
    tipo = RecordSet.Tipo.SUBSERIE if mandato is not None and mandato.codigo_subserie else RecordSet.Tipo.SERIE
    nombre = actividad.serie_trd or actividad.nombre
    serie, creada = _conjunto(actividad.identificador, tipo, nombre, usuario, padre=padre, actividad=actividad)
    if not serie.actividad_id:
        serie.actividad = actividad
        serie.save(update_fields=["actividad"])
    if creada:
        _relacion_manual(padre, serie, R_INCLUYE, usuario)
        _relacion_manual(serie, actividad, R_DOCUMENTA, usuario)
        if isinstance(oficina, CorporateBody):
            _relacion_manual(serie, oficina, R_PROCEDENCIA, usuario)
    return serie


def series_trd(q="", limite=40):
    """Series/subseries de la TRD (actividades con mandato) para el buscador
    de ingesta: por nombre, código u oficina."""
    qs = Activity.objects.filter(mandato__isnull=False).select_related("mandato")
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(identificador__icontains=q) | Q(mandato__codigo_serie=q))
    return list(qs.order_by("nombre")[:limite])


def expedientes_de(actividad):
    return RecordSet.objects.filter(tipo_conjunto=RecordSet.Tipo.EXPEDIENTE, padre__actividad=actividad).order_by("-fecha_registro")


@transaction.atomic
def crear_expediente(actividad, nombre, usuario, codigo="", fecha_apertura=None):
    """Un expediente nuevo dentro de la serie de `actividad`. Si ya existe
    uno con el mismo nombre en esa serie, se devuelve ese."""
    serie = conjunto_serie(actividad, usuario)
    expediente = serie.hijos.filter(tipo_conjunto=RecordSet.Tipo.EXPEDIENTE, nombre=nombre).first()
    if expediente is not None:
        return expediente, False
    expediente = RecordSet.objects.create(
        nombre=nombre, identificador=codigo, tipo_conjunto=RecordSet.Tipo.EXPEDIENTE, padre=serie,
        fecha_apertura=fecha_apertura, creado_por=usuario, serie_trd=serie.nombre,
    )
    _relacion_manual(serie, expediente, R_INCLUYE, usuario)
    return expediente, True


def _nombre_documento(archivo):
    return Path(archivo.name).stem.replace("_", " ").strip() or archivo.name


@transaction.atomic
def registrar_documentos(expediente, archivos, usuario, un_solo_documento=False, nombre_documento=""):
    """Los archivos cargados como documentos del expediente. Por defecto,
    cada archivo es un documento (Record) con su instanciación; con
    `un_solo_documento`, todos los archivos son partes (instanciaciones) de
    un mismo documento, para escaneos partidos. Devuelve las instanciaciones."""
    instanciaciones = []
    record = None
    if un_solo_documento:
        record = Record.objects.create(
            nombre=nombre_documento or _nombre_documento(archivos[0]), record_set=expediente, creado_por=usuario,
            serie_trd=expediente.serie_trd,
        )
        _relacion_manual(expediente, record, R_INCLUYE, usuario)
    for archivo in archivos:
        if not un_solo_documento:
            record = Record.objects.create(
                nombre=_nombre_documento(archivo), record_set=expediente, creado_por=usuario, serie_trd=expediente.serie_trd,
            )
            _relacion_manual(expediente, record, R_INCLUYE, usuario)
        instanciacion = Instantiation.objects.create(nombre=archivo.name, record_resource=record, archivo=archivo, creado_por=usuario)
        # RF-M1-04: usuario, fecha y hora de cada carga, en la bitácora encadenada.
        registrar_evento(
            instanciacion, EventoRiC.Tipo.INGESTA, agente=usuario,
            detalle={
                "archivo": archivo.name, "formato": instanciacion.formato, "tamano_bytes": instanciacion.tamano_bytes,
                "sha256": instanciacion.sha256, "expediente": expediente.nombre, "serie": expediente.serie_trd,
            },
        )
        instanciaciones.append(instanciacion)
    return instanciaciones


def expediente_de(record):
    """El expediente (o conjunto) al que pertenece un documento: la FK de
    conveniencia o, si no está, el origen de una R024 validada hacia él."""
    if record.record_set_id:
        return record.record_set
    rel = RelacionRiC.objects.filter(
        relacion_id=R_INCLUYE, destino_content_type=_ct(Record), destino_object_id=record.pk,
        origen_content_type=_ct(RecordSet),
    ).first()
    return rel.origen if rel is not None else None
