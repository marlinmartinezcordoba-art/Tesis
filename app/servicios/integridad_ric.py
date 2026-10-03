"""
Integridad semántica de la tabla de relaciones (hallazgo CM-19 de la
auditoría RiC).

La tabla `relaciones` es polimórfica: la base de datos no sabe qué clase
de RiC tiene cada extremo. Este guardián se engancha a cualquier sesión de
SQLAlchemy (evento before_flush) y rechaza, antes de escribir, toda fila
nueva cuyo código no tenga propiedad en el mapeo único (ric_o.PROPIEDADES)
o cuyo origen o destino no sea de una clase que esa propiedad admite.
Así una ruta futura no puede crear filas que el grafo muestre y la
exportación descarte en silencio.
"""

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario, Fecha, Hito, Relacion
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import ric_o

MODELOS = {"recurso_documental": RecursoDocumental, "entidad_vocabulario": EntidadVocabulario,
           "instanciacion": Instanciacion, "fecha": Fecha, "hito": Hito}


class RelacionNoConforme(ValueError):
    pass


def _nodo(sesion: Session, tipo: str, ident):
    modelo = MODELOS.get(tipo)
    if modelo is None:
        return None
    for objeto in sesion.new:  # creado en esta misma escritura
        if isinstance(objeto, modelo) and objeto.id == ident:
            return objeto
    return sesion.get(modelo, ident)


def clase(sesion: Session, tipo: str, ident) -> str | None:
    nodo = _nodo(sesion, tipo, ident)
    if nodo is None:
        return None
    if tipo == "recurso_documental":
        return ric_o.clase_de(tipo, nivel=nodo.nivel)
    if tipo == "entidad_vocabulario":
        return ric_o.clase_de(tipo, clase=nodo.clase, subtipo=nodo.subtipo)
    return ric_o.clase_de(tipo)


def comprobar(sesion: Session, r: Relacion) -> None:
    p = ric_o.propiedad(r.codigo_ric)
    if p is None:
        raise RelacionNoConforme(f"El código «{r.codigo_ric}» no tiene propiedad en el mapeo RiC-O del sistema.")
    c_o, c_d = clase(sesion, r.origen_tipo, r.origen_id), clase(sesion, r.destino_tipo, r.destino_id)
    if c_o is None or c_d is None:
        raise RelacionNoConforme(f"Relación «{r.codigo_ric}» con un extremo que no existe.")
    if not ric_o.uso_valido(r.codigo_ric, c_o, c_d):
        raise RelacionNoConforme(f"rico:{p.rico} no admite {c_o} → {c_d} (origen admitido: {', '.join(p.origen)}; "
                                 f"destino: {', '.join(p.destino)}).")


@event.listens_for(Session, "before_flush")
def _antes_de_escribir(sesion: Session, contexto, instancias) -> None:
    for objeto in list(sesion.new):
        if isinstance(objeto, Relacion):
            comprobar(sesion, objeto)
