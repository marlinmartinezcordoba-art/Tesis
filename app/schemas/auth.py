import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

Rol = Literal["archivista", "revisor", "consulta", "administrador"]


def _limpiar_nombre(valor: str) -> str:
    valor = " ".join(valor.split())
    if len(valor) < 3:
        raise ValueError("Escriba el nombre completo.")
    return valor


class IngresoIn(BaseModel):
    correo: str = Field(max_length=254)
    contrasena: str = Field(max_length=200)


class UsuarioBreve(BaseModel):
    id: uuid.UUID
    nombre: str
    correo: str
    rol: Rol
    rol_nombre: str
    iniciales: str


class SesionOut(BaseModel):
    token_acceso: str
    tipo: str = "bearer"
    expira_en: int  # segundos
    rol: Rol
    usuario: UsuarioBreve


class RecuperarIn(BaseModel):
    correo: str = Field(max_length=254)


class MensajeOut(BaseModel):
    mensaje: str


class EnlaceInfoOut(BaseModel):
    tipo: Literal["invitacion", "recuperacion"]
    nombre: str
    correo: str


class DefinirContrasenaIn(BaseModel):
    contrasena: str = Field(max_length=200)


class CambiarContrasenaIn(BaseModel):
    actual: str = Field(max_length=200)
    nueva: str = Field(max_length=200)


class PerfilOut(BaseModel):
    id: uuid.UUID
    nombre: str
    correo: str
    rol: Rol
    rol_nombre: str
    iniciales: str
    contrasena_cambiada_en: datetime | None


class UsuarioOut(BaseModel):
    id: uuid.UUID
    nombre: str
    correo: str
    rol: Rol
    rol_nombre: str
    iniciales: str
    activo: bool
    invitacion_pendiente: bool
    recuperacion_solicitada: bool
    ultimo_ingreso: datetime | None
    sesiones_abiertas: int
    creado_en: datetime


class UsuariosOut(BaseModel):
    usuarios: list[UsuarioOut]
    correo_configurado: bool


class UsuarioNuevoIn(BaseModel):
    nombre: str = Field(max_length=150)
    correo: EmailStr
    rol: Rol

    _nombre = field_validator("nombre")(_limpiar_nombre)


class UsuarioEdicionIn(BaseModel):
    nombre: str | None = Field(default=None, max_length=150)
    rol: Rol | None = None
    activo: bool | None = None

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, valor: str | None) -> str | None:
        return None if valor is None else _limpiar_nombre(valor)


class EntregaOut(BaseModel):
    enviado: bool
    mensaje: str
    enlace: str | None = None


class UsuarioCreadoOut(BaseModel):
    usuario: UsuarioOut
    entrega: EntregaOut
