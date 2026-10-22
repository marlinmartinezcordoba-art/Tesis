"""
El grafo RiC-O como fuente de verdad de la descripción publicada.

Cada fondo vive en el almacén de tripletas en tres grafos con nombre:

- «completo»: la descripción en RiC-O 1.1 (lo que se exporta con permiso);
- «publico»: lo mismo sin lo clasificado ni lo reservado;
- «control»: solo lo que RiC-O 1.1 no puede expresar y el sistema necesita
  para reconstruirse (procedencia del dato, años de retención, archivo y
  huella de cada instanciación, rol y fragmento de cada relación, estado e
  historia de las entidades…). Nunca se publica.

Regla: cada dato se lee del grafo RiC-O si allí queda exacto; solo si no,
del grafo de control. `reconstruir` vuelve a armar las tablas de lo
publicado desde el almacén (el grafo gana), y `diferencias` dice en qué no
coinciden. La prueba de ida y vuelta (tablas → grafo → tablas) es exacta.
"""

import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, or_, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.descripcion import (Actividad, EntidadVocabulario, Fecha, Hito, IdentificadorEntidad, NombreEntidad,
                                    Relacion)
from app.models.instanciacion import Instanciacion
from app.models.preservacion import DeclaracionDerechos
from app.models.recurso_documental import RecursoDocumental
from app.servicios import ric_o

CONTROL = Namespace("urn:ricora:control#")
RICO = Namespace(ric_o.RICO)
SKOS = Namespace(ric_o.SKOS)

# En el orden en que se cargan (cada tabla después de aquellas a las que apunta).
TABLAS = (RecursoDocumental, EntidadVocabulario, Fecha, Actividad, NombreEntidad, IdentificadorEntidad, Hito,
          Instanciacion, DeclaracionDerechos, Relacion)
POR_NOMBRE = {m.__tablename__: m for m in TABLAS}


class ErrorControl(RuntimeError):
    pass


# --- Qué es «lo publicado» de un fondo -------------------------------------------------------------


def foto(db: Session, fondo_id) -> dict[str, dict[uuid.UUID, dict]]:
    """Las filas de las tablas de la descripción de un fondo, columna por columna."""
    salida: dict[str, dict] = {}

    def tomar(modelo, condicion):
        # Directo de la tabla (no de la sesión): lo que de verdad está guardado.
        tabla = modelo.__table__
        filas = db.execute(select(tabla).where(condicion(tabla))).mappings().all()
        salida[modelo.__tablename__] = {f["id"]: dict(f) for f in filas}
        return salida[modelo.__tablename__]

    db.flush()
    tomar(RecursoDocumental, lambda t: t.c.fondo_id == fondo_id)
    entidades = list(tomar(EntidadVocabulario, lambda t: t.c.fondo_id == fondo_id))
    for modelo in (Actividad, Hito, Instanciacion, DeclaracionDerechos):
        tomar(modelo, lambda t: t.c.fondo_id == fondo_id)
    tomar(NombreEntidad, lambda t: t.c.entidad_id.in_(entidades))
    tomar(IdentificadorEntidad, lambda t: t.c.entidad_id.in_(entidades))
    propios = (set(salida["recursos_documentales"]) | set(entidades) | set(salida["instanciaciones"])
               | set(salida["hitos"]) | set(salida["actividades"]))
    relaciones = tomar(Relacion, lambda t: or_(t.c.origen_id.in_(propios), t.c.destino_id.in_(propios)))
    fechas_ = {r["destino_id"] for r in relaciones.values() if r["destino_tipo"] == "fecha"} | {
        r["origen_id"] for r in relaciones.values() if r["origen_tipo"] == "fecha"}
    tomar(Fecha, lambda t: t.c.id.in_(fechas_))
    return salida


# --- Lo que se lee del grafo RiC-O ------------------------------------------------------------------


def _id_de(nodo, base: str):
    texto = str(nodo) if nodo is not None else ""
    if not texto.startswith(base):
        return None
    try:
        return uuid.UUID(texto[len(base):].split("/")[0])
    except ValueError:
        return None


def _valor(g: Graph, s, propiedad):
    v = g.value(s, propiedad)
    return str(v) if v is not None else None


def _lectores(base: str) -> dict[str, dict]:
    """Por tabla: columna → función (grafo, fila) que da su valor desde RiC-O.
    La fila trae al menos el id y lo que vino del grafo de control."""
    def u(fila):
        return URIRef(base + str(fila["id"]))

    def texto(prop):
        return lambda g, f: _valor(g, u(f), RICO[prop])

    def padre(g, f):
        # Con pertenencias adicionales hay varios conjuntos: solo si hay uno se sabe cuál es el
        # orgánico; si no, el dato va en el control (así la lectura nunca depende del orden).
        padres = {p for prop in (ric_o.PROPIEDADES["includes_or_included"].rico,
                                 ric_o.PROPIEDADES["has_or_had_constituent"].rico)
                  for p in g.subjects(RICO[prop], u(f))}
        return _id_de(next(iter(padres)), base) if len(padres) == 1 else None

    def forma(g, f):
        return _id_de(g.value(u(f), RICO[ric_o.APOYO["forma_documental"][0]]), base)

    def fecha_libre(sufijo, prop):
        return lambda g, f: _valor(g, URIRef(f"{u(f)}/{sufijo}"), RICO[prop])

    def folios(g, f):
        v = g.value(URIRef(f"{u(f)}/extension/folios"), RICO[ric_o.ATRIBUTOS["cantidad"][0]])
        return int(Decimal(str(v))) if v is not None else None

    def formas_miembros(g, f):
        return sorted(i for i in (_id_de(o, base) for o in g.objects(u(f), RICO[ric_o.APOYO["formas_miembros"][0]]))
                      if i is not None)

    def nombre_entidad(g, f):
        return _valor(g, u(f), RICO.name) or _valor(g, u(f), RICO.title)

    def superior(g, f):
        return _id_de(g.value(u(f), SKOS[ric_o.SKOS_BROADER]), base)

    def nombre_alterno(g, f):
        return _valor(g, URIRef(f"{base}{f.get('entidad_id')}/nombre/{f['id']}"), RICO[ric_o.ATRIBUTOS["valor_textual"][0]])

    def extremo(cual):
        def leer(g, f):
            nodo = u(f)
            fuente, destino = g.value(nodo, RICO[ric_o.RELACION_ORIGEN]), g.value(nodo, RICO[ric_o.RELACION_DESTINO])
            if fuente is None or destino is None:
                return None
            if f.get("codigo_ric") in ric_o.RELACION_INVERTIDA:
                fuente, destino = destino, fuente
            return _id_de(fuente if cual == "origen" else destino, base)
        return leer

    a = ric_o.ATRIBUTOS
    return {
        "recursos_documentales": {
            "titulo": texto(a["titulo"][0]), "codigo_referencia": texto(a["identificador"][0]),
            "alcance_contenido": texto(a["alcance_contenido"][0]), "condiciones_acceso": texto(a["condiciones_acceso"][0]),
            "condiciones_uso": texto(a["condiciones_uso"][0]), "historia_archivistica": texto(a["historia"][0]),
            "nuevos_ingresos": texto(a["nuevos_ingresos"][0]), "organizacion": texto(a["organizacion"][0]),
            "nota": texto(a["descripcion_general"][0]), "incluido_en_id": padre, "forma_documental_id": forma,
            "tipo_parte_id": forma, "fechas_extremas": fecha_libre("fechas-extremas", a["fecha_expresada"][0]),
            "fechas_extremas_edtf": fecha_libre("fechas-extremas", a["fecha_normalizada"][0]), "folios": folios,
            "formas_miembros": formas_miembros, "nota_integridad": texto(a["integridad"][0]),
        },
        "entidades_vocabulario": {
            "nombre": nombre_entidad, "historia": texto(a["historia"][0]),
            "contexto_general": texto(a["descripcion_general"][0]), "concepto_superior_id": superior,
            "codigo_clasificacion": lambda g, f: _valor(g, u(f), SKOS.notation),
        },
        "fechas": {"expresion": texto(a["fecha_expresada"][0])},
        "hitos": {"descripcion": texto(a["nombre"][0])},
        "nombres_entidad": {"nombre": nombre_alterno},
        "relaciones": {"origen_id": extremo("origen"), "destino_id": extremo("destino")},
    }


# --- Valores ↔ literales ----------------------------------------------------------------------------


def _literal(valor) -> Literal:
    if isinstance(valor, bool):
        return Literal("true" if valor else "false", datatype=XSD.boolean)
    if isinstance(valor, int):
        return Literal(str(valor), datatype=XSD.integer)
    if isinstance(valor, float):
        return Literal(repr(valor), datatype=XSD.double)
    if isinstance(valor, Decimal):
        return Literal(str(valor), datatype=XSD.decimal)
    if isinstance(valor, datetime):
        return Literal(valor.isoformat(), datatype=XSD.dateTime)
    if isinstance(valor, date):
        return Literal(valor.isoformat(), datatype=XSD.date)
    if isinstance(valor, uuid.UUID):
        return Literal(str(valor))
    if isinstance(valor, (list, dict)):
        return Literal(json.dumps(valor, ensure_ascii=False, sort_keys=True, default=str), datatype=RDF.JSON)
    return Literal(str(valor))


def _desde_literal(columna, lit) -> object:
    texto, tipo = str(lit), columna.type
    if isinstance(tipo, UUID):
        return uuid.UUID(texto)
    if isinstance(tipo, Boolean):
        return texto in ("true", "1")
    if isinstance(tipo, Integer):
        return int(texto)
    if isinstance(tipo, Float):
        return float(texto)
    if isinstance(tipo, Numeric):
        return Decimal(texto)
    if isinstance(tipo, DateTime):
        return datetime.fromisoformat(texto.replace("Z", "+00:00"))
    if isinstance(tipo, Date):
        return date.fromisoformat(texto)
    if isinstance(tipo, ARRAY) and isinstance(tipo.item_type, UUID):
        return [uuid.UUID(x) for x in json.loads(texto)]
    if isinstance(tipo, (ARRAY, JSONB)):
        return json.loads(texto)
    return texto


# --- Tablas → grafo de control ---------------------------------------------------------------------


def grafo_control(fotografia: dict, completo: Graph, base: str) -> Graph:
    """Lo que el grafo RiC-O no dice exacto, como tripletas de control."""
    g = Graph()
    g.bind("ctl", CONTROL)
    lectores = _lectores(base)
    for tabla, filas in fotografia.items():
        propios = lectores.get(tabla, {})
        for ident, fila in filas.items():
            s = URIRef(f"urn:ricora:fila:{ident}")
            g.add((s, CONTROL.tabla, Literal(tabla)))
            g.add((s, CONTROL.id, Literal(str(ident))))
            for columna, valor in fila.items():
                if columna == "id":
                    continue
                lector = propios.get(columna)
                if lector is not None and lector(completo, fila) == valor:
                    continue  # RiC-O lo dice exacto: no se repite
                if valor is None:
                    if lector is not None:  # RiC-O diría algo y la tabla no: se declara el vacío
                        g.add((s, CONTROL[columna], CONTROL.vacio))
                    continue
                g.add((s, CONTROL[columna], _literal(valor)))
    return g


# --- Grafo → tablas ----------------------------------------------------------------------------------


def filas_desde_grafo(completo: Graph, control: Graph, base: str) -> dict[str, dict[uuid.UUID, dict]]:
    lectores = _lectores(base)
    salida: dict[str, dict] = {m.__tablename__: {} for m in TABLAS}
    for s in set(control.subjects(CONTROL.tabla, None)):
        tabla = str(control.value(s, CONTROL.tabla))
        modelo = POR_NOMBRE.get(tabla)
        if modelo is None:
            raise ErrorControl(f"Tabla desconocida en el grafo de control: {tabla}")
        columnas = {c.name: c for c in modelo.__table__.columns}
        fila = {"id": uuid.UUID(str(control.value(s, CONTROL.id)))}
        declaradas = set()
        for p, o in control.predicate_objects(s):
            nombre_col = str(p)[len(str(CONTROL)):]
            if nombre_col in ("tabla", "id") or nombre_col not in columnas:
                continue
            declaradas.add(nombre_col)
            fila[nombre_col] = None if o == CONTROL.vacio else _desde_literal(columnas[nombre_col], o)
        for columna, lector in lectores.get(tabla, {}).items():
            if columna not in declaradas:
                fila[columna] = lector(completo, fila)
        for columna in columnas:
            fila.setdefault(columna, None)
        salida[tabla][fila["id"]] = fila
    return salida


def _normal(v):
    return v


def diferencias(actual: dict, esperado: dict, limite: int = 50) -> list[dict]:
    """Dónde no coinciden las tablas (actual) con el grafo (esperado)."""
    salida = []
    for tabla in POR_NOMBRE:
        a, e = actual.get(tabla, {}), esperado.get(tabla, {})
        for ident in sorted(set(a) | set(e), key=str):
            if ident not in e:
                salida.append({"tabla": tabla, "id": str(ident), "columna": None, "problema": "está en las tablas y no en el grafo"})
            elif ident not in a:
                salida.append({"tabla": tabla, "id": str(ident), "columna": None, "problema": "está en el grafo y no en las tablas"})
            else:
                for col in e[ident]:
                    if _normal(a[ident].get(col)) != _normal(e[ident].get(col)):
                        salida.append({"tabla": tabla, "id": str(ident), "columna": col, "problema": "valor distinto"})
            if len(salida) >= limite:
                return salida
    return salida


def cargar(db: Session, filas: dict[str, dict]) -> dict[str, int]:
    """Escribe en las tablas lo que dice el grafo (inserta o actualiza, fila por fila).
    Las claves que apuntan a otra tabla de la descripción se ponen en un segundo paso,
    para no depender del orden."""
    conteo = {}
    diferidas: list[tuple] = []
    tablas_propias = {m.__tablename__ for m in TABLAS}
    for modelo in TABLAS:
        tabla = modelo.__table__
        filas_t = list(filas.get(modelo.__tablename__, {}).values())
        if not filas_t:
            continue
        aplazar = [c.name for c in tabla.columns if c.nullable and any(
            fk.column.table.name in tablas_propias for fk in c.foreign_keys)]
        if modelo is RecursoDocumental:  # padres antes que hijos
            filas_t.sort(key=lambda f: (f["nivel"] != "fondo", f["incluido_en_id"] is not None))
        for fila in filas_t:
            primera = {k: (None if k in aplazar else v) for k, v in fila.items()}
            sentencia = pg_insert(tabla).values(**primera)
            sentencia = sentencia.on_conflict_do_update(index_elements=[tabla.c.id],
                                                        set_={k: sentencia.excluded[k] for k in primera if k != "id"})
            db.execute(sentencia)
            if any(fila.get(k) is not None for k in aplazar):
                diferidas.append((tabla, fila["id"], {k: fila[k] for k in aplazar}))
        conteo[modelo.__tablename__] = len(filas_t)
    for tabla, ident, valores in diferidas:
        db.execute(tabla.update().where(tabla.c.id == ident).values(**valores))
    db.expire_all()
    return conteo
