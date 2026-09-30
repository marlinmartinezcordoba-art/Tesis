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
}


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
