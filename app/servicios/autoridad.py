"""
Ficha de autoridad y vínculos del vocabulario (módulo 3, versión 2).

- Ficha de agente en las cuatro áreas de ISAAR (CPF): identificación
  (formas del nombre, identificadores con esquema, versión del mecanismo),
  descripción (existencia, historia, hitos, estatuto, estructura, contexto),
  relaciones (con otros agentes, fechadas) y control (reglas, nivel de
  detalle, fuentes; fechas de creación y revisión leídas de auditoría).
- Ficha ampliada de lugar: coordenadas, tipo, jerarquía y nombres históricos.
- Vínculos declarados desde vocabularios entre entidades del mismo fondo:
  cada uno es una fila de «relaciones» con su código del catálogo y su
  propiedad de RiC-O (app/servicios/ric_o.py). Ninguna jerarquía admite
  ciclos.
- Jerarquía función → subfunción entre tipos de actividad: SKOS broader,
  no RiC-O.

Nada se borra: un nombre, un identificador, un hito o un vínculo que sobra
queda «anulado», con quién y cuándo en auditoría.
"""

import uuid
from datetime import date
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import ahora
from app.models.descripcion import (
    ESQUEMA_EXTERNO, ESQUEMA_IDENTIFICADOR, ESTADO_ELABORACION, ESTATUTO_JURIDICO, TIPO_FUNCION, TIPO_HITO, TIPO_LUGAR, TIPO_NOMBRE_ENTIDAD,
    EntidadVocabulario, Hito, IdentificadorEntidad, NombreEntidad, Relacion,
)
from app.models.recurso_documental import RecursoDocumental
from app.servicios import fechas, ric_o
from app.servicios.auditoria import registrar

REGLAS_POR_DEFECTO = "ISAAR (CPF), 2.ª edición (Consejo Internacional de Archivos, 2004)"


class ErrorAutoridad(Exception):
    pass


# --- Campos de enriquecimiento ---------------------------------------------------------------

# Campos que se pueden editar por clase. El nombre base no: cambiarlo pasa
# por la verificación de duplicados del módulo de descripción.
# Área de control de ISAAR 5.4 e ISDF 5.4 (hallazgos VOC-01 y VOC-03): estado
# de elaboración, institución responsable, lenguas y escrituras, notas de
# mantenimiento (además de reglas y fuentes).
CAMPOS_CONTROL = ("reglas", "fuentes", "estado_elaboracion", "institucion_responsable", "lenguas", "escrituras",
                  "notas_mantenimiento")
CAMPOS_AGENTE = ("version", "existencia_edtf", "historia", "estatuto_juridico", "estructura", "contexto_general",
                 *CAMPOS_CONTROL)
# Función (ISDF; hallazgo VOC-03): tipo, código de clasificación (skos:notation),
# fechas, historia (nota de alcance) y el área de control.
CAMPOS_FUNCION = ("tipo_funcion", "codigo_clasificacion", "existencia_edtf", "historia", *CAMPOS_CONTROL)
CAMPOS_LUGAR = ("latitud", "longitud", "tipo_lugar", "historia")
CAMPOS_GENERALES = ("historia",)  # actividad, tipo de actividad, mandato: una nota de alcance
# Regla de retención (TRD): años en gestión y en central, disposición final y
# el procedimiento (en «historia»).
CAMPOS_REGLA = ("retencion_gestion_anios", "retencion_central_anios", "disposicion_final", "historia")

# Área de descripción de ISAAR: con uno solo de estos campos, la ficha deja
# de ser «mínima» y pasa a «parcial»; es «completa» con fechas de
# existencia, historia, al menos otro elemento del área y las fuentes.
AREA_DESCRIPCION = ("existencia_edtf", "historia", "estatuto_juridico", "estructura", "contexto_general")


def campos_de(e: EntidadVocabulario) -> tuple[str, ...]:
    if e.clase == "agente":
        return CAMPOS_AGENTE
    if e.clase == "tipo_actividad":
        return CAMPOS_FUNCION
    if e.clase == "lugar":
        return CAMPOS_LUGAR
    if e.clase == "regla":
        return CAMPOS_REGLA
    return CAMPOS_GENERALES


def _texto(valor, maximo: int | None = None) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise ErrorAutoridad("Se esperaba un texto.")
    valor = valor.strip()
    if maximo and len(valor) > maximo:
        raise ErrorAutoridad(f"El texto supera los {maximo} caracteres.")
    return valor or None


def _codigos(campo: str, valor) -> list[str] | None:
    """Lenguas (ISO 639-3) o escrituras (ISO 15924) del registro de autoridad."""
    from app.servicios import isadg
    from app.servicios.motor import idiomas_validos

    if valor in (None, "", []):
        return None
    lista = valor if isinstance(valor, list) else [x for x in str(valor).replace(";", ",").split(",")]
    lista = [str(x).strip() for x in lista if str(x).strip()]
    if campo == "lenguas":
        limpios = idiomas_validos(lista)
        if len(limpios) != len(lista):
            raise ErrorAutoridad("Las lenguas se indican con su código ISO 639-3 (spa, lat, eng…).")
        return limpios or None
    try:
        return isadg.escrituras_validas(lista)
    except isadg.ErrorIsadg as exc:
        raise ErrorAutoridad(str(exc)) from exc


def _numero(valor, minimo: float, maximo: float, nombre: str) -> float | None:
    if valor in (None, ""):
        return None
    try:
        n = float(valor)
    except (TypeError, ValueError) as exc:
        raise ErrorAutoridad(f"La {nombre} debe ser un número.") from exc
    if not minimo <= n <= maximo:
        raise ErrorAutoridad(f"La {nombre} debe estar entre {minimo:g} y {maximo:g}.")
    return round(n, 6)


def recalcular_nivel(db: Session, e: EntidadVocabulario) -> str:
    """ISAAR 5.4.5 / ISDF 5.4.5 (hallazgo VOC-01): «minimo» sin datos del área
    de descripción; «parcial» con alguno; «completo» con fechas de existencia,
    historia, al menos otro elemento (estatuto, estructura, contexto o un
    hito; en una función, su tipo y su código) y las fuentes."""
    if e.clase not in ("agente", "tipo_actividad"):
        return e.nivel_detalle
    if e.clase == "agente":
        hitos = db.scalar(select(Hito.id).where(Hito.agente_id == e.id, Hito.estado == "vigente").limit(1)) is not None
        alguno = any(getattr(e, c) for c in AREA_DESCRIPCION) or hitos
        otro = any(getattr(e, c) for c in ("estatuto_juridico", "estructura", "contexto_general")) or hitos
    else:
        alguno = any(getattr(e, c) for c in ("tipo_funcion", "codigo_clasificacion", "existencia_edtf", "historia"))
        otro = bool(e.tipo_funcion and e.codigo_clasificacion)
    if e.existencia_edtf and e.historia and otro and e.fuentes:
        e.nivel_detalle = "completo"
    else:
        e.nivel_detalle = "parcial" if alguno else "minimo"
    return e.nivel_detalle


def actualizar(db: Session, e: EntidadVocabulario, cambios: dict, usuario_id: uuid.UUID,
               ip: str | None = None) -> dict:
    """Aplica los campos de enriquecimiento permitidos para la clase y deja
    en auditoría solo lo que cambió, con el valor anterior y el nuevo."""
    if e.clase == "agente" and e.subtipo == "mecanismo" and (set(cambios) - {"version"} or e.version):
        # Solo consulta: el sistema lo registra con su versión cuando actúa. La única
        # edición es completar la versión que llegó vacía (VOC-07).
        raise ErrorAutoridad("Un mecanismo (software) es de solo consulta: su nombre y su versión los registra el "
                             "sistema. Solo se completa la versión cuando llegó vacía.")
    permitidos = campos_de(e)
    extra = [c for c in cambios if c not in permitidos]
    if extra:
        raise ErrorAutoridad(f"Campos que no se pueden editar en esta entidad: {', '.join(sorted(extra))}.")
    nuevos = {}
    for campo, valor in cambios.items():
        if campo == "existencia_edtf":
            texto = _texto(valor, 200)
            if texto:
                try:
                    i = fechas.interpretar(texto)
                except fechas.FechaInvalida as exc:
                    raise ErrorAutoridad(str(exc)) from exc
                if i.subtipo == "conjunto":
                    raise ErrorAutoridad("Las fechas de existencia son una fecha o un rango, no un conjunto.")
                nuevos["existencia_edtf"], nuevos["existencia_inicio"], nuevos["existencia_fin"] = i.edtf, i.inicio, i.fin
            else:
                nuevos["existencia_edtf"] = nuevos["existencia_inicio"] = nuevos["existencia_fin"] = None
        elif campo == "estatuto_juridico":
            v = _texto(valor)
            if v and v not in ESTATUTO_JURIDICO:
                raise ErrorAutoridad("El estatuto jurídico es pública, privada o mixta.")
            nuevos[campo] = v
        elif campo == "tipo_lugar":
            v = _texto(valor)
            if v and v not in TIPO_LUGAR:
                raise ErrorAutoridad("Tipo de lugar desconocido.")
            nuevos[campo] = v
        elif campo == "latitud":
            nuevos[campo] = _numero(valor, -90, 90, "latitud")
        elif campo == "longitud":
            nuevos[campo] = _numero(valor, -180, 180, "longitud")
        elif campo in ("retencion_gestion_anios", "retencion_central_anios", "disposicion_final"):
            from app.servicios import retencion

            if campo != "disposicion_final" and isinstance(valor, str):  # desde un campo de texto de la ficha
                valor = int(valor) if valor.strip().isdigit() else (None if not valor.strip() else -1)
            try:
                retencion.validar(valor if campo != "disposicion_final" else None,
                                  None, valor if campo == "disposicion_final" else None)
            except retencion.ErrorRetencion as exc:
                raise ErrorAutoridad(str(exc)) from exc
            nuevos[campo] = valor or None if campo == "disposicion_final" else valor
        elif campo in ("version", "reglas"):
            nuevos[campo] = _texto(valor, 120 if campo == "version" else 200)
        elif campo == "estado_elaboracion":
            v = _texto(valor)
            if v and v not in ESTADO_ELABORACION:
                raise ErrorAutoridad("El estado de elaboración es borrador, revisado o definitivo.")
            nuevos[campo] = v
        elif campo == "tipo_funcion":
            v = _texto(valor)
            if v and v not in TIPO_FUNCION:
                raise ErrorAutoridad("El tipo es función, subfunción, proceso, actividad o transacción (ISDF 5.1.1).")
            nuevos[campo] = v
        elif campo == "codigo_clasificacion":
            nuevos[campo] = _texto(valor, 40)
        elif campo == "institucion_responsable":
            nuevos[campo] = _texto(valor, 300)
        elif campo in ("lenguas", "escrituras"):
            nuevos[campo] = _codigos(campo, valor)
        else:
            nuevos[campo] = _texto(valor, 20000)
    if e.clase == "agente" and e.subtipo == "mecanismo":
        version = nuevos.get("version", e.version)
        if not version:
            raise ErrorAutoridad("Un mecanismo debe declarar su versión exacta (por ejemplo, la del modelo o la del "
                                 "programa de conversión).")
    if e.clase == "lugar":
        lat = nuevos.get("latitud", e.latitud)
        lon = nuevos.get("longitud", e.longitud)
        if (lat is None) != (lon is None):
            raise ErrorAutoridad("Las coordenadas llevan latitud y longitud juntas.")
    anterior, nuevo = {}, {}
    for campo, valor in nuevos.items():
        actual = getattr(e, campo)
        if actual != valor:
            anterior[campo] = actual.isoformat() if hasattr(actual, "isoformat") else actual
            nuevo[campo] = valor.isoformat() if hasattr(valor, "isoformat") else valor
            setattr(e, campo, valor)
    nivel_antes = e.nivel_detalle
    recalcular_nivel(db, e)
    if nivel_antes != e.nivel_detalle:
        anterior["nivel_detalle"], nuevo["nivel_detalle"] = nivel_antes, e.nivel_detalle
    if nuevo:
        registrar(db, modulo="vocabularios", accion="entidad_enriquecida", usuario_id=usuario_id,
                  entidad_tipo="entidad_vocabulario", entidad_id=e.id, anterior=anterior, nuevo=nuevo, ip=ip,
                  detalle=f"Ficha de «{e.nombre}»: {', '.join(sorted(k for k in nuevo if k != 'nivel_detalle'))}")
    return nuevo


# --- Nombres e identificadores ---------------------------------------------------------------


def agregar_nombre(db: Session, e: EntidadVocabulario, *, tipo: str, nombre: str, idioma: str | None,
                   regla: str | None, vigencia_edtf: str | None, usuario_id: uuid.UUID,
                   ip: str | None = None) -> NombreEntidad:
    if tipo not in TIPO_NOMBRE_ENTIDAD:
        raise ErrorAutoridad("Tipo de forma del nombre desconocido.")
    if tipo == "historica" and e.clase != "lugar":
        raise ErrorAutoridad("Los nombres históricos se registran en los lugares.")
    if tipo != "historica" and e.clase not in ("agente", "lugar", "tipo_actividad"):
        raise ErrorAutoridad("Las formas del nombre se registran en agentes, lugares y funciones.")
    nombre = _texto(nombre, 300)
    if not nombre:
        raise ErrorAutoridad("Falta el nombre.")
    inicio = fin = None
    vigencia = _texto(vigencia_edtf, 200)
    if vigencia:
        try:
            i = fechas.interpretar(vigencia)
        except fechas.FechaInvalida as exc:
            raise ErrorAutoridad(str(exc)) from exc
        vigencia, inicio, fin = i.edtf, i.inicio, i.fin
    from app.servicios.motor import idiomas_validos

    idioma = _texto(idioma, 12)
    if idioma and idiomas_validos([idioma]) != [idioma.lower()]:
        raise ErrorAutoridad("El idioma de una forma del nombre se indica con su código ISO 639-3 (spa, lat, eng…).")
    from app.servicios.vocabulario import normalizar

    n = NombreEntidad(entidad_id=e.id, tipo=tipo, nombre=nombre, nombre_normalizado=normalizar(nombre),
                      idioma=idioma.lower() if idioma else None,
                      regla=_texto(regla, 120),
                      vigencia_edtf=vigencia, inicio=inicio, fin=fin, creado_por_id=usuario_id)
    db.add(n)
    db.flush()
    registrar(db, modulo="vocabularios", accion="nombre_agregado", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=e.id, ip=ip,
              nuevo={"id": str(n.id), "tipo": tipo, "nombre": nombre, "vigencia": vigencia},
              detalle=f"Forma del nombre de «{e.nombre}»: {nombre}")
    return n


def agregar_identificador(db: Session, e: EntidadVocabulario, *, esquema: str, valor: str, usuario_id: uuid.UUID,
                          ip: str | None = None) -> IdentificadorEntidad:
    if esquema not in ESQUEMA_IDENTIFICADOR:
        raise ErrorAutoridad("Esquema de identificador desconocido.")
    valor = _texto(valor, 200)
    if not valor:
        raise ErrorAutoridad("Falta el valor del identificador.")
    if esquema == "wikidata" and not (valor[:1] == "Q" and valor[1:].isdigit()):
        raise ErrorAutoridad("Un identificador de Wikidata tiene la forma Q seguida de números, por ejemplo Q2841.")
    if esquema == "viaf" and not valor.isdigit():
        raise ErrorAutoridad("Un identificador VIAF es numérico.")
    if esquema == "isni" and not (len(valor.replace(" ", "")) == 16):
        raise ErrorAutoridad("Un ISNI tiene 16 caracteres.")
    if db.scalar(select(IdentificadorEntidad.id).where(IdentificadorEntidad.entidad_id == e.id,
                                                       IdentificadorEntidad.esquema == esquema,
                                                       IdentificadorEntidad.valor == valor,
                                                       IdentificadorEntidad.estado == "vigente")):
        raise ErrorAutoridad("Ese identificador ya está registrado.")
    i = IdentificadorEntidad(entidad_id=e.id, esquema=esquema, valor=valor, creado_por_id=usuario_id)
    db.add(i)
    db.flush()
    registrar(db, modulo="vocabularios", accion="identificador_agregado", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=e.id, ip=ip,
              nuevo={"id": str(i.id), "esquema": esquema, "valor": valor, "externo": esquema in ESQUEMA_EXTERNO},
              detalle=f"Identificador {esquema} de «{e.nombre}»: {valor}")
    return i


# URI de entidad canónicas que publica cada autoridad (hallazgo O-30): en RDF
# http://…/Q42 y https://…/Q42 son nodos distintos, así que owl:sameAs debe
# apuntar exactamente al que la autoridad usa en su propio grafo. Wikidata,
# VIAF y la Library of Congress publican sus entidades con «http»; ISNI, con
# «https» en su servicio de datos enlazados.
URI_EXTERNA = {
    "viaf": "http://viaf.org/viaf/{}",
    "wikidata": "http://www.wikidata.org/entity/{}",
    "isni": "https://isni.org/isni/{}",
    "lcnaf": "http://id.loc.gov/authorities/names/{}",
}


def uri_externa(esquema: str, valor: str) -> str | None:
    plantilla = URI_EXTERNA.get(esquema)
    return plantilla.format(valor.replace(" ", "")) if plantilla else None


# --- Hitos de la línea de tiempo institucional (rico:Event) ----------------------------------


def agregar_hito(db: Session, agente: EntidadVocabulario, *, tipo: str, descripcion: str, edtf: str,
                 usuario_id: uuid.UUID, ip: str | None = None, lugar_id: uuid.UUID | None = None,
                 afectados: list[dict] | None = None) -> Hito:
    if agente.clase != "agente":
        raise ErrorAutoridad("La línea de tiempo institucional es de un agente.")
    if tipo not in TIPO_HITO:
        raise ErrorAutoridad("Tipo de hito desconocido.")
    descripcion = _texto(descripcion, 500)
    if not descripcion:
        raise ErrorAutoridad("Describa brevemente el hito.")
    try:
        i = fechas.interpretar(_texto(edtf, 200) or "")
    except fechas.FechaInvalida as exc:
        raise ErrorAutoridad(str(exc)) from exc
    lugar = db.get(EntidadVocabulario, lugar_id) if lugar_id else None
    if lugar_id and (lugar is None or lugar.clase != "lugar" or lugar.fondo_id != agente.fondo_id):
        raise ErrorAutoridad("El lugar del hito debe ser un lugar del vocabulario de este fondo.")
    h = Hito(fondo_id=agente.fondo_id, agente_id=agente.id, tipo=tipo, descripcion=descripcion, edtf=i.edtf,
             inicio=i.inicio, fin=i.fin, creado_por_id=usuario_id, lugar_id=lugar.id if lugar else None)
    db.add(h)
    db.flush()
    # Un mismo hito (una fusión, el traslado de un fondo) afecta a varios
    # agentes o descripciones: una fila affects_or_affected por cada uno.
    for a in afectados or []:
        tipo_a, ident = a.get("tipo"), uuid.UUID(str(a.get("id")))
        otro = _clase_nodo(db, tipo_a, ident) if tipo_a in ("entidad_vocabulario", "recurso_documental") else None
        if otro is None or otro.fondo_id != agente.fondo_id or otro.id == agente.id or (
                isinstance(otro, EntidadVocabulario) and otro.clase != "agente"):
            raise ErrorAutoridad("Cada afectado debe ser otro agente o una descripción de este fondo.")
        db.add(Relacion(origen_tipo="hito", origen_id=h.id, destino_tipo=tipo_a, destino_id=otro.id,
                        tipo_relacion="temporal", codigo_ric="affects_or_affected", origen="persona",
                        confirmada_por_id=usuario_id))
    db.flush()
    antes = agente.nivel_detalle
    recalcular_nivel(db, agente)
    registrar(db, modulo="vocabularios", accion="hito_agregado", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=agente.id, ip=ip,
              anterior={"nivel_detalle": antes} if antes != agente.nivel_detalle else None,
              nuevo={"id": str(h.id), "tipo": tipo, "fecha": i.edtf, "descripcion": descripcion,
                     **({"nivel_detalle": agente.nivel_detalle} if antes != agente.nivel_detalle else {})},
              detalle=f"Hito de «{agente.nombre}» ({i.legible}): {descripcion}")
    return h


def hitos_de(db: Session, agente_id: uuid.UUID) -> list[dict]:
    filas = db.scalars(select(Hito).where(Hito.agente_id == agente_id, Hito.estado == "vigente")
                       .order_by(Hito.inicio.asc().nulls_last(), Hito.creado_en)).all()
    salida = []
    for h in filas:
        lugar = db.get(EntidadVocabulario, h.lugar_id) if h.lugar_id else None
        otros = db.scalars(select(Relacion).where(Relacion.origen_id == h.id, Relacion.estado == "vigente",
                                                  Relacion.codigo_ric == "affects_or_affected")).all()
        afectados = []
        for r in otros:
            otro = _clase_nodo(db, r.destino_tipo, r.destino_id)
            if otro is not None:
                afectados.append({"tipo": r.destino_tipo, "id": str(otro.id),
                                  "nombre": getattr(otro, "nombre", None) or otro.titulo})
        salida.append({"id": str(h.id), "tipo": h.tipo, "descripcion": h.descripcion, "edtf": h.edtf,
                       "fecha_legible": fechas.legible(h.edtf), "clase_rico": "rico:Event",
                       "propiedad_rico": ric_o.etiqueta("affects_or_affected"),
                       "lugar": {"id": str(lugar.id), "nombre": lugar.nombre} if lugar else None,
                       "afectados": afectados})
    return salida


# --- Anular un registro accesorio ---------------------------------------------------------------

TABLAS_ACCESORIAS = {"nombre": NombreEntidad, "identificador": IdentificadorEntidad, "hito": Hito}


def anular_accesorio(db: Session, e: EntidadVocabulario, clase: str, registro_id: uuid.UUID,
                     usuario_id: uuid.UUID, ip: str | None = None) -> None:
    modelo = TABLAS_ACCESORIAS[clase]
    campo = Hito.agente_id if clase == "hito" else modelo.entidad_id
    fila = db.scalar(select(modelo).where(modelo.id == registro_id, campo == e.id))
    if fila is None or fila.estado != "vigente":
        raise ErrorAutoridad("Ese registro no existe o ya se anuló.")
    fila.estado = "anulado"
    resumen = {"nombre": getattr(fila, "nombre", None), "valor": getattr(fila, "valor", None),
               "descripcion": getattr(fila, "descripcion", None)}
    antes = e.nivel_detalle
    recalcular_nivel(db, e)
    registrar(db, modulo="vocabularios", accion=f"{clase}_anulado", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=e.id, ip=ip,
              anterior={"id": str(registro_id), "estado": "vigente", **{k: v for k, v in resumen.items() if v},
                        **({"nivel_detalle": antes} if antes != e.nivel_detalle else {})},
              nuevo={"id": str(registro_id), "estado": "anulado",
                     **({"nivel_detalle": e.nivel_detalle} if antes != e.nivel_detalle else {})},
              detalle=f"Se anuló un {clase} de «{e.nombre}»")


# --- Vínculos declarados desde vocabularios ------------------------------------------------------


@dataclass(frozen=True)
class Vinculo:
    codigo: str  # código del catálogo (relaciones.codigo_ric)
    rol: str | None
    tipo_relacion: str
    origen: tuple[str, ...]  # clases del vocabulario que pueden ser origen de la fila
    destino: tuple[str, ...]  # clases del vocabulario, o «recurso:<niveles>»
    jerarquico: bool  # ¿forma una jerarquía? (sin ciclos)
    unico_superior: bool  # ¿a lo sumo un superior directo?
    directa: str  # lectura desde el origen
    inversa: str  # lectura desde el destino
    # Desde qué lado se declara en la interfaz: «origen» si la entidad que
    # se edita es el origen de la fila, «destino» si es el destino.
    se_declara_desde: str = "origen"
    # Varios superiores, cada uno con su vigencia y sin solaparse (un
    # municipio que fue de una provincia hasta 1886 y luego de un departamento).
    superiores_por_vigencia: bool = False


GRUPOS_VOCABULARIO = ("agente:grupo", "agente:entidad_corporativa", "agente:familia")

VINCULOS: dict[str, Vinculo] = {
    # Agente a agente (ISAAR 5.3): jerárquica, temporal, asociativa.
    "subordinado": Vinculo("has_or_had_subordinate", None, "asociacion", ("agente",), ("agente",), True, False,
                           "tiene o tuvo como subordinado a", "está o estuvo subordinado a"),
    "sucesor": Vinculo("has_successor", None, "temporal", ("agente",), ("agente",), True, False,
                       "tiene como sucesor a", "es sucesor de"),
    "asociado": Vinculo("is_agent_associated_with_agent", None, "asociacion", ("agente",), ("agente",), False, False,
                        "está asociado con", "está asociado con"),
    # Persona, cargo y grupo (ISAAR 5.3; RiC-R054, R055, R056, R005, R042),
    # validados por subtipo: «agente:persona» admite solo personas.
    "ocupa_cargo": Vinculo("occupies_or_occupied", None, "asociacion", ("agente:persona",), ("agente:cargo",), False,
                           False, "ocupa u ocupó el cargo", "es o fue ocupado por"),
    # Parentesco (ISAAR 5.3.2; rico:hasFamilyAssociationWith, hallazgo VOC-02), tipado por el rol.
    "progenitor_de": Vinculo("has_family_association_with", "progenitor", "asociacion", ("agente:persona",),
                             ("agente:persona",), False, False, "es padre o madre de", "es hijo o hija de"),
    "hermano_de": Vinculo("has_family_association_with", "hermano", "asociacion", ("agente:persona",),
                          ("agente:persona",), False, False, "es hermano o hermana de", "es hermano o hermana de"),
    "conyuge_de": Vinculo("has_family_association_with", "conyuge", "asociacion", ("agente:persona",),
                          ("agente:persona",), False, False, "es o fue cónyuge de", "es o fue cónyuge de"),
    "familiar_de": Vinculo("has_family_association_with", None, "asociacion", ("agente:persona",),
                           ("agente:persona",), False, False, "tiene parentesco con", "tiene parentesco con"),
    "miembro": Vinculo("has_or_had_member", None, "asociacion", GRUPOS_VOCABULARIO, ("agente:persona",), False,
                       False, "tiene o tuvo como miembro a", "es o fue miembro de"),
    "dirige": Vinculo("is_or_was_leader_of", None, "asociacion", ("agente:persona",), GRUPOS_VOCABULARIO, False,
                      False, "dirige o dirigió", "es o fue dirigido por"),
    "subdivision": Vinculo("has_or_had_subdivision", None, "inclusion", GRUPOS_VOCABULARIO, GRUPOS_VOCABULARIO, True,
                           False, "tiene o tuvo como subdivisión a", "es o fue subdivisión de"),
    "cargo_en": Vinculo("exists_or_existed_in", None, "inclusion", ("agente:cargo",), GRUPOS_VOCABULARIO, False,
                        False, "existe o existió en", "tiene o tuvo el cargo"),
    # Lugar de actuación de un agente (RiC-R075): se declara desde el agente.
    "lugar_agente": Vinculo("is_or_was_location_of", "actuacion", "espacial", ("lugar",), ("agente",), False, False,
                            "es o fue lugar de actuación de", "actúa o actuó en", se_declara_desde="destino"),
    # Lugar contenido en otro (RiC-R007): se declara desde el lugar contenido.
    "lugar_superior": Vinculo("contains_or_contained", None, "espacial", ("lugar",), ("lugar",), True, False,
                              "contiene a", "está dentro de", se_declara_desde="destino",
                              superiores_por_vigencia=True),
    # Actividad mayor y sub-actividad (rico:hasDirectSubevent): desde la sub-actividad.
    "actividad_mayor": Vinculo("has_direct_subevent", None, "inclusion", ("actividad",), ("actividad",), True, True,
                               "tiene como sub-actividad a", "es sub-actividad de", se_declara_desde="destino"),
    # Agente que ejerce la actividad (RiC-R060i): desde la actividad.
    "ejercida_por": Vinculo("performs_or_performed", None, "procedencia", ("agente",), ("actividad",), False, False,
                            "ejerce o ejerció", "es o fue ejercida por", se_declara_desde="destino"),
    # Mandato que regula una actividad (RiC-R063): desde la actividad.
    "mandato_actividad": Vinculo("regulates_or_regulated", None, "asociacion", ("mandato",), ("actividad",), False,
                                 False, "regula", "está regulada por", se_declara_desde="destino"),
    # Norma superior de la que deriva un mandato (R063, rol jerarquía normativa): desde el derivado.
    "mandato_superior": Vinculo("regulates_or_regulated", "jerarquia_normativa", "asociacion", ("mandato",),
                                ("mandato",), True, False, "es norma superior de", "desarrolla o deriva de",
                                se_declara_desde="destino"),
    # Mandato que crea al agente (R067, rol creación): desde el agente.
    "creado_por": Vinculo("authorizes", "creacion", "asociacion", ("mandato",), ("agente",), False, False,
                          "crea o establece a", "fue creado o establecido por", se_declara_desde="destino"),
    # Mandato que crea un tipo de actividad como competencia nueva (R063, rol creación).
    "competencia_creada_por": Vinculo("regulates_or_regulated", "creacion", "asociacion", ("mandato",),
                                      ("tipo_actividad",), False, False, "crea la competencia",
                                      "es una competencia creada por", se_declara_desde="destino"),
    # Entidad que expidió el mandato (RiC-R065): desde el mandato.
    "expedido_por": Vinculo("issued_by", None, "procedencia", ("mandato",), ("agente",), False, False,
                            "fue expedido por", "expidió"),
    # Regla de retención (TRD) que regula la serie o subserie (R063, rol «retencion»): desde la regla.
    "regla_serie": Vinculo("regulates_or_regulated", "retencion", "asociacion", ("regla",),
                           ("recurso:serie,subserie",), False, True, "regula la retención de",
                           "tiene su retención regulada por"),
    # Función ↔ serie que produce (TRD): R001, desde el tipo de actividad.
    "serie_producida": Vinculo("is_related_to", "serie_producida", "asociacion", ("tipo_actividad",),
                               ("recurso:serie,subserie",), False, False, "produce la serie", "es producida por la función"),
}


def _clase_nodo(db: Session, tipo: str, nodo_id: uuid.UUID):
    if tipo == "entidad_vocabulario":
        return db.get(EntidadVocabulario, nodo_id)
    return db.get(RecursoDocumental, nodo_id)


def _admite(clases: tuple[str, ...], nodo) -> bool:
    for c in clases:
        if c.startswith("recurso:"):
            if isinstance(nodo, RecursoDocumental) and nodo.nivel in c.split(":")[1].split(","):
                return True
        elif ":" in c:  # «clase:subtipo», p. ej. «agente:persona»
            clase, subtipo = c.split(":", 1)
            if isinstance(nodo, EntidadVocabulario) and nodo.clase == clase and nodo.subtipo == subtipo:
                return True
        elif isinstance(nodo, EntidadVocabulario) and nodo.clase == c:
            return True
    return False


def _fila_vigente(db: Session, v: Vinculo, origen_id, destino_id) -> Relacion | None:
    consulta = select(Relacion).where(Relacion.codigo_ric == v.codigo, Relacion.estado == "vigente",
                                      Relacion.origen_id == origen_id, Relacion.destino_id == destino_id)
    consulta = consulta.where(Relacion.rol == v.rol) if v.rol else consulta.where(Relacion.rol.is_(None))
    return db.scalar(consulta)


def _superiores(db: Session, v: Vinculo, nodo_id: uuid.UUID) -> list[uuid.UUID]:
    """Origen de las filas vigentes del vínculo cuyo destino es el nodo
    (en una jerarquía: sus superiores directos)."""
    consulta = select(Relacion.origen_id).where(Relacion.codigo_ric == v.codigo, Relacion.estado == "vigente",
                                                Relacion.destino_id == nodo_id)
    consulta = consulta.where(Relacion.rol == v.rol) if v.rol else consulta.where(Relacion.rol.is_(None))
    return list(db.scalars(consulta))


def _crearia_ciclo(db: Session, v: Vinculo, origen_id: uuid.UUID, destino_id: uuid.UUID) -> bool:
    """¿El destino ya está, directa o indirectamente, por encima del origen?"""
    pendientes, vistos = [origen_id], set()
    while pendientes:
        actual = pendientes.pop()
        if actual == destino_id:
            return True
        if actual in vistos:
            continue
        vistos.add(actual)
        pendientes.extend(_superiores(db, v, actual))
    return False


def _intervalo(edtf: str | None):
    if not edtf:
        return None
    i = fechas.interpretar(edtf)
    return (i.inicio or date.min, i.fin or date.max)


def _sin_solape(db: Session, v: Vinculo, nodo_id: uuid.UUID, vigencia: str | None) -> None:
    """Un segundo superior solo con vigencias que no se crucen (hallazgo CM-12)."""
    consulta = select(Relacion.fecha_edtf).where(Relacion.codigo_ric == v.codigo, Relacion.estado == "vigente",
                                                 Relacion.destino_id == nodo_id)
    existentes = list(db.scalars(consulta))
    if not existentes:
        return
    nuevo = _intervalo(vigencia)
    if nuevo is None or any(e is None for e in existentes):
        raise ErrorAutoridad("Ya tiene un lugar superior. Para declarar otro, indique la vigencia de cada uno "
                             "(por ejemplo «1857/1885» y «1886/»): un lugar no está en dos a la vez.")
    for e in existentes:
        a = _intervalo(e)
        if nuevo[0] < a[1] and a[0] < nuevo[1]:
            raise ErrorAutoridad(f"La vigencia se cruza con la de otro lugar superior ({fechas.legible(e)}).")


def vincular(db: Session, *, tipo: str, desde: EntidadVocabulario, con_tipo: str, con_id: uuid.UUID,
             usuario_id: uuid.UUID, fecha_edtf: str | None = None, nota: str | None = None,
             ip: str | None = None) -> Relacion:
    """Declara un vínculo desde la entidad que se edita (`desde`) hacia otra
    entidad o recurso (`con`). La fila se orienta según el vínculo: el origen
    y el destino de la fila son los de la propiedad de RiC-O."""
    v = VINCULOS.get(tipo)
    if v is None:
        raise ErrorAutoridad("Tipo de vínculo desconocido.")
    otro = _clase_nodo(db, con_tipo, con_id)
    if otro is None:
        raise ErrorAutoridad("La otra entidad no existe.")
    if v.se_declara_desde == "origen":
        origen, destino, destino_tipo, origen_tipo = desde, otro, con_tipo, "entidad_vocabulario"
    else:
        origen, destino, origen_tipo, destino_tipo = otro, desde, con_tipo, "entidad_vocabulario"
    if not _admite(v.origen, origen) or not _admite(v.destino, destino):
        raise ErrorAutoridad("Ese vínculo no se puede declarar entre estas dos entidades.")
    fondo_otro = otro.fondo_id
    if fondo_otro != desde.fondo_id:
        raise ErrorAutoridad("Solo se vinculan entidades del mismo fondo.")
    if origen.id == destino.id:
        raise ErrorAutoridad("Una entidad no se vincula consigo misma.")
    if any(getattr(x, "estado", "activa") != "activa" for x in (origen, destino) if isinstance(x, EntidadVocabulario)):
        raise ErrorAutoridad("No se vincula una entidad fusionada; use la definitiva.")
    if _fila_vigente(db, v, origen.id, destino.id) or (
            v.codigo == "is_agent_associated_with_agent" and _fila_vigente(db, v, destino.id, origen.id)) or (
            v.rol in ("hermano", "conyuge") and _fila_vigente(db, v, destino.id, origen.id)):
        raise ErrorAutoridad("Ese vínculo ya existe.")
    if v.unico_superior and _superiores(db, v, destino.id):
        raise ErrorAutoridad("Esta entidad ya tiene un superior directo; anule ese vínculo antes de declarar otro.")
    if v.jerarquico and _crearia_ciclo(db, v, origen.id, destino.id):
        raise ErrorAutoridad("Ese vínculo formaría un ciclo en la jerarquía.")
    vigencia = None
    if _texto(fecha_edtf, 200):
        try:
            vigencia = fechas.interpretar(fecha_edtf.strip()).edtf
        except fechas.FechaInvalida as exc:
            raise ErrorAutoridad(str(exc)) from exc
    if v.superiores_por_vigencia:
        _sin_solape(db, v, destino.id, vigencia)
    r = Relacion(origen_tipo=origen_tipo, origen_id=origen.id, destino_tipo=destino_tipo, destino_id=destino.id,
                 tipo_relacion=v.tipo_relacion, codigo_ric=v.codigo, rol=v.rol, origen="persona",
                 confirmada_por_id=usuario_id, fecha_edtf=vigencia, nota=_texto(nota, 500))
    db.add(r)
    db.flush()
    nombre_o = getattr(origen, "nombre", None) or getattr(origen, "titulo", "")
    nombre_d = getattr(destino, "nombre", None) or getattr(destino, "titulo", "")
    registrar(db, modulo="vocabularios", accion="vinculo_declarado", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=desde.id, ip=ip,
              nuevo={"relacion_id": str(r.id), "vinculo": tipo, "codigo_ric": v.codigo, "rol": v.rol,
                     "propiedad_rico": ric_o.etiqueta(v.codigo), "origen": str(origen.id), "destino": str(destino.id),
                     "vigencia": vigencia, "nota": r.nota},
              detalle=f"«{nombre_o}» {v.directa} «{nombre_d}»")
    return r


def anular_vinculo(db: Session, relacion_id: uuid.UUID, desde: EntidadVocabulario, usuario_id: uuid.UUID,
                   ip: str | None = None) -> None:
    r = db.get(Relacion, relacion_id)
    if r is None or r.estado != "vigente" or desde.id not in (r.origen_id, r.destino_id):
        raise ErrorAutoridad("Ese vínculo no existe o ya se anuló.")
    if not any(v.codigo == r.codigo_ric and v.rol == r.rol for v in VINCULOS.values()):
        raise ErrorAutoridad("Ese vínculo se corrige desde la descripción del documento.")
    r.estado, r.anulada_en, r.anulada_por_id = "anulada", ahora(), usuario_id
    registrar(db, modulo="vocabularios", accion="vinculo_anulado", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=desde.id, ip=ip,
              anterior={"relacion_id": str(r.id), "estado": "vigente", "codigo_ric": r.codigo_ric, "rol": r.rol},
              nuevo={"relacion_id": str(r.id), "estado": "anulada"},
              detalle="Se anuló un vínculo declarado en vocabularios")


def vinculos_de(db: Session, entidad_id: uuid.UUID) -> list[dict]:
    """Todos los vínculos vigentes de la entidad que corresponden al catálogo
    de vocabularios, leídos desde ella (directa o inversa)."""
    por_clave = {(v.codigo, v.rol): (t, v) for t, v in VINCULOS.items()}
    filas = db.scalars(select(Relacion).where(
        Relacion.estado == "vigente", (Relacion.origen_id == entidad_id) | (Relacion.destino_id == entidad_id),
        Relacion.codigo_ric.in_({v.codigo for v in VINCULOS.values()}))).all()
    salida = []
    for r in filas:
        clave = por_clave.get((r.codigo_ric, r.rol))
        if clave is None:
            continue
        tipo, v = clave
        es_origen = r.origen_id == entidad_id
        otro_tipo, otro_id = (r.destino_tipo, r.destino_id) if es_origen else (r.origen_tipo, r.origen_id)
        # Los vínculos que salen de una descripción (p. ej. la actividad de un
        # documento) se muestran igual; solo se anulan desde vocabularios los
        # que se declararon aquí.
        if otro_tipo not in ("entidad_vocabulario", "recurso_documental"):
            continue
        otro = _clase_nodo(db, otro_tipo, otro_id)
        p = ric_o.propiedad(r.codigo_ric)
        salida.append({
            "relacion_id": str(r.id), "vinculo": tipo, "codigo_ric": r.codigo_ric, "rol": r.rol,
            "sentido": "directa" if es_origen else "inversa",
            "etiqueta": v.directa if es_origen else v.inversa,
            "propiedad_rico": f"rico:{p.rico}" if es_origen else (f"rico:{p.inversa}" if p.inversa else None),
            "estado_mapeo": p.estado,
            "codigo_cm": p.codigo_cm if es_origen or not p.codigo_cm or p.inversa == p.rico
            else (p.codigo_cm[:-1] if p.codigo_cm.endswith("i") else p.codigo_cm + "i"),
            "vigencia": r.fecha_edtf, "vigencia_legible": fechas.legible(r.fecha_edtf) if r.fecha_edtf else None,
            "nota": r.nota,
            "declarado_en_vocabularios": r.confirmada_por_id is not None and r.fragmento is None,
            "con": ({"tipo": otro_tipo, "id": str(otro.id), "nombre": getattr(otro, "nombre", None) or otro.titulo,
                     "clase": getattr(otro, "clase", None), "subtipo": getattr(otro, "subtipo", None),
                     "nivel": getattr(otro, "nivel", None)} if otro else None),
        })
    return sorted(salida, key=lambda x: (x["vinculo"], (x["con"] or {}).get("nombre") or ""))


# --- Jerarquía SKOS de tipos de actividad (función → subfunción) --------------------------------


def fijar_concepto_superior(db: Session, concepto: EntidadVocabulario, superior_id: uuid.UUID | None,
                            usuario_id: uuid.UUID, ip: str | None = None) -> None:
    if concepto.clase != "tipo_actividad":
        raise ErrorAutoridad("Solo los tipos de actividad forman el árbol de funciones.")
    superior = None
    if superior_id is not None:
        superior = db.get(EntidadVocabulario, superior_id)
        if superior is None or superior.clase != "tipo_actividad" or superior.fondo_id != concepto.fondo_id:
            raise ErrorAutoridad("El superior debe ser otro tipo de actividad del mismo fondo.")
        if superior.estado != "activa":
            raise ErrorAutoridad("No se usa como superior una entidad fusionada.")
        # Sin ciclos: el nuevo superior no puede estar por debajo del concepto.
        actual, vistos = superior, set()
        while actual is not None:
            if actual.id == concepto.id:
                raise ErrorAutoridad("Ese superior formaría un ciclo en el árbol de funciones.")
            if actual.id in vistos:
                break
            vistos.add(actual.id)
            actual = db.get(EntidadVocabulario, actual.concepto_superior_id) if actual.concepto_superior_id else None
    anterior = concepto.concepto_superior_id
    if anterior == superior_id:
        return
    concepto.concepto_superior_id = superior_id
    registrar(db, modulo="vocabularios", accion="concepto_superior_cambiado", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=concepto.id, ip=ip,
              anterior={"skos:broader": str(anterior) if anterior else None},
              nuevo={"skos:broader": str(superior_id) if superior_id else None},
              detalle=f"«{concepto.nombre}» " + (f"pasa a depender de «{superior.nombre}»" if superior
                                                else "queda como función de primer nivel"))


def arbol_funciones(db: Session, fondo_id: uuid.UUID) -> list[dict]:
    """Árbol completo de tipos de actividad del fondo (skos:broader /
    skos:narrower), con tantos niveles como haya, y las series que produce
    cada función."""
    tipos = db.scalars(select(EntidadVocabulario).where(EntidadVocabulario.fondo_id == fondo_id,
                                                        EntidadVocabulario.clase == "tipo_actividad",
                                                        EntidadVocabulario.estado == "activa")
                       .order_by(EntidadVocabulario.nombre_normalizado)).all()
    v = VINCULOS["serie_producida"]
    series: dict[uuid.UUID, list[dict]] = {}
    for r, rec in db.execute(select(Relacion, RecursoDocumental).join(RecursoDocumental, RecursoDocumental.id == Relacion.destino_id)
                             .where(Relacion.codigo_ric == v.codigo, Relacion.rol == v.rol,
                                    Relacion.estado == "vigente",
                                    Relacion.origen_id.in_([t.id for t in tipos] or [uuid.uuid4()]))):
        series.setdefault(r.origen_id, []).append({"id": str(rec.id), "titulo": rec.titulo, "nivel": rec.nivel})
    hijos: dict[uuid.UUID | None, list[EntidadVocabulario]] = {}
    ids = {t.id for t in tipos}
    for t in tipos:
        padre = t.concepto_superior_id if t.concepto_superior_id in ids else None
        hijos.setdefault(padre, []).append(t)

    def nodo(t: EntidadVocabulario, camino: frozenset) -> dict:
        return {"id": str(t.id), "nombre": t.nombre, "series": series.get(t.id, []),
                "especificos": [nodo(h, camino | {t.id}) for h in hijos.get(t.id, []) if h.id not in camino]}

    return [nodo(t, frozenset()) for t in hijos.get(None, [])]


def ficha(db: Session, e: EntidadVocabulario) -> dict:
    """Todo lo que la ficha de la entidad muestra, según su clase."""
    from app.models.auditoria import RegistroAuditoria

    eventos = db.execute(select(RegistroAuditoria.fecha).where(RegistroAuditoria.entidad_id == str(e.id))
                         .order_by(RegistroAuditoria.fecha)).scalars().all()
    nombres = db.scalars(select(NombreEntidad).where(NombreEntidad.entidad_id == e.id,
                                                     NombreEntidad.estado == "vigente")
                         .order_by(NombreEntidad.tipo,
                                   func.coalesce(NombreEntidad.inicio, NombreEntidad.fin).asc().nulls_last(),
                                   NombreEntidad.nombre)).all()
    salida = {
        "campos": {c: (getattr(e, c).isoformat() if hasattr(getattr(e, c), "isoformat") else getattr(e, c))
                   for c in campos_de(e)},
        "nombres": [{"id": str(n.id), "tipo": n.tipo, "nombre": n.nombre, "idioma": n.idioma, "regla": n.regla,
                     "vigencia": n.vigencia_edtf, "vigencia_legible": fechas.legible(n.vigencia_edtf)}
                    for n in nombres],
        "vinculos": vinculos_de(db, e.id),
        "clase_rico": f"rico:{ric_o.clase_de('entidad_vocabulario', clase=e.clase, subtipo=e.subtipo)}",
        "control": {
            "identificador_registro": str(e.id),
            "reglas": e.reglas or (REGLAS_POR_DEFECTO if e.clase == "agente" else
                                   "ISDF, 1.ª edición (Consejo Internacional de Archivos, 2007)"
                                   if e.clase == "tipo_actividad" else None),
            "nivel_detalle": e.nivel_detalle if e.clase in ("agente", "tipo_actividad") else None,
            "estado_elaboracion": e.estado_elaboracion, "institucion_responsable": e.institucion_responsable,
            "lenguas": e.lenguas or [], "escrituras": e.escrituras or [],
            "notas_mantenimiento": e.notas_mantenimiento,
            # Creación y última revisión: de auditoría, nunca capturadas a mano.
            "creada_en": e.creado_en,
            "revisada_en": eventos[-1] if eventos else None,
        },
    }
    if e.clase == "agente":
        identificadores = db.scalars(select(IdentificadorEntidad).where(
            IdentificadorEntidad.entidad_id == e.id, IdentificadorEntidad.estado == "vigente")
            .order_by(IdentificadorEntidad.esquema)).all()
        salida["identificadores"] = [{"id": str(i.id), "esquema": i.esquema, "valor": i.valor,
                                      "externo": i.esquema in ESQUEMA_EXTERNO,
                                      "uri": uri_externa(i.esquema, i.valor)} for i in identificadores]
        salida["hitos"] = hitos_de(db, e.id)
        salida["existencia_legible"] = fechas.legible(e.existencia_edtf) if e.existencia_edtf else None
        salida["falta_version"] = e.subtipo == "mecanismo" and not e.version
        if e.subtipo == "mecanismo":
            from app.servicios.vocabulario import conteo_usos_mecanismo

            # Lo que hizo este programa en el sistema: la prueba de que
            # preservación y descripción lo reutilizan, no lo copian.
            salida["usos_tecnicos"] = conteo_usos_mecanismo(db, e.id)
    if e.clase == "lugar":
        salida["contiene"] = [x for x in salida["vinculos"] if x["vinculo"] == "lugar_superior" and x["sentido"] == "directa"]
    if e.clase == "tipo_actividad":
        superior = db.get(EntidadVocabulario, e.concepto_superior_id) if e.concepto_superior_id else None
        especificos = db.scalars(select(EntidadVocabulario).where(EntidadVocabulario.concepto_superior_id == e.id,
                                                                  EntidadVocabulario.estado == "activa")
                                 .order_by(EntidadVocabulario.nombre_normalizado)).all()
        salida["skos"] = {
            "broader": {"id": str(superior.id), "nombre": superior.nombre} if superior else None,
            "narrower": [{"id": str(x.id), "nombre": x.nombre} for x in especificos],
        }
        salida["actividades"] = _actividades_de_tipo(db, e.id)
    if e.clase == "actividad":
        from app.servicios.descripcion import contexto_actividad

        salida["contexto"] = contexto_actividad(db, e.id)
    if e.clase == "mandato":
        from app.servicios.descripcion import _fecha_de

        salida["expedicion"] = _fecha_de(db, e.id, "is_date_associated_with")
    return salida


def _actividades_de_tipo(db: Session, tipo_id: uuid.UUID) -> list[dict]:
    filas = db.execute(select(EntidadVocabulario).join(Relacion, Relacion.origen_id == EntidadVocabulario.id)
                       .where(Relacion.destino_id == tipo_id, Relacion.codigo_ric == "has_activity_type",
                              Relacion.estado == "vigente")).scalars().unique().all()
    return [{"id": str(a.id), "nombre": a.nombre} for a in filas]
