"""Lectura y cambio de los parámetros que ajusta el administrador."""

import uuid
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.parametro import Parametro
from app.servicios.auditoria import registrar


@dataclass(frozen=True)
class Definicion:
    defecto: Any
    validar: Callable[[Any], str | None]  # devuelve el problema, o None si el valor sirve
    descripcion: str


def _entero_entre(minimo: int, maximo: int) -> Callable[[Any], str | None]:
    def validar(valor: Any) -> str | None:
        if not isinstance(valor, int) or isinstance(valor, bool) or not minimo <= valor <= maximo:
            return f"Debe ser un número entero entre {minimo} y {maximo}."
        return None

    return validar


DEFINICIONES: dict[str, Definicion] = {
    "ingesta_limite_mb": Definicion(500, _entero_entre(1, 20000), "Tamaño máximo por archivo en la ingesta, en megabytes."),
    "fusion_similitud_pct": Definicion(60, _entero_entre(30, 100),
                                       "Similitud mínima (%) entre dos entidades para sugerir fusionarlas."),
    "fusion_max_conexiones": Definicion(10, _entero_entre(0, 10000),
                                        "Conexiones máximas de cada entidad para sugerir fusionarlas («pocas conexiones»)."),
    "fusion_horas_deteccion": Definicion(24, _entero_entre(1, 720), "Cada cuántas horas se buscan candidatos a fusión."),
    "preservacion_frecuencia_dias": Definicion(30, _entero_entre(1, 365),
                                               "Cada cuántos días se verifica la integridad de todo el fondo."),
    "preservacion_formatos": Definicion(None, lambda v: _formatos(v), "Formatos soportados para migración automática."),
    "preservacion_segunda_ubicacion": Definicion(None, lambda v: _segunda_ubicacion(v),
                                                 "Lugar donde se guarda la segunda copia de cada instanciación."),
}


def _segunda_ubicacion(valor: Any) -> str | None:
    """Solo uno de los lugares que declaró quien opera el servidor."""
    from app.servicios.segunda_copia import ubicaciones

    if valor not in [str(u) for u in ubicaciones()]:
        return "Elija uno de los lugares de almacenamiento declarados en el servidor."
    return None


def _formatos(valor: Any) -> str | None:
    """Tabla de formatos soportados: lista de filas {id, origen, origen_mime,
    destino, conversor, activo}. El conversor debe existir en el código y
    producir ese destino (ver servicios/preservacion.py)."""
    from app.servicios.preservacion import CONVERSORES

    if not isinstance(valor, list) or len(valor) > 50:
        return "La tabla de formatos debe ser una lista (máximo 50 filas)."
    for fila in valor:
        if not isinstance(fila, dict):
            return "Cada fila debe tener origen, tipos MIME, destino y conversor."
        mimes = fila.get("origen_mime")
        if not isinstance(fila.get("origen"), str) or not fila["origen"].strip() or len(fila["origen"]) > 80:
            return "Cada fila necesita un nombre de origen (máximo 80 caracteres)."
        if not isinstance(mimes, list) or not mimes or not all(isinstance(m, str) and 3 <= len(m) <= 100 and "/" in m
                                                               for m in mimes):
            return "Cada fila necesita al menos un tipo MIME de origen, como application/pdf o image/*."
        conversor = CONVERSORES.get(fila.get("conversor"))
        if conversor is None:
            return f"Conversor desconocido: {fila.get('conversor')}."
        if fila.get("destino") != conversor.destino:
            return f"El conversor «{conversor.nombre}» produce {conversor.destino}, no {fila.get('destino')}."
        if not isinstance(fila.get("activo"), bool):
            return "Cada fila debe indicar si está activa."
    return None


def leer(db: Session, clave: str) -> Any:
    fila = db.get(Parametro, clave)
    return fila.valor if fila is not None else DEFINICIONES[clave].defecto


def cambiar(db: Session, clave: str, valor: Any, usuario_id: uuid.UUID, modulo: str, ip: str | None = None) -> None:
    definicion = DEFINICIONES[clave]
    problema = definicion.validar(valor)
    if problema:
        raise ValueError(problema)
    fila = db.get(Parametro, clave)
    anterior = fila.valor if fila is not None else definicion.defecto
    if anterior == valor:
        return
    if fila is None:
        fila = Parametro(clave=clave, valor=valor)
        db.add(fila)
    fila.valor = valor
    fila.actualizado_por_id = usuario_id
    registrar(db, modulo=modulo, accion="parametro_cambiado", usuario_id=usuario_id, entidad_tipo="parametro",
              entidad_id=clave, anterior={clave: anterior}, nuevo={clave: valor}, ip=ip)


def limite_ingesta_bytes(db: Session) -> int:
    return int(leer(db, "ingesta_limite_mb")) * 1024 * 1024
