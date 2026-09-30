"""
Autorización por rol (RBAC) para todo el sistema.

Aquí vive la única comprobación de identidad y de permisos. Cada módulo
importa estas dependencias; ninguno hace la suya. El rol se lee siempre
de la base de datos en cada petición, nunca de lo que diga el navegador
ni del propio token: si un administrador cambia el rol de alguien, el
cambio rige desde la petición siguiente.

Matriz de permisos (sección 2 del prompt de autenticación):

| Módulo        | administrador | archivista            | revisor (provisional) | consulta             |
|---------------|---------------|-----------------------|-----------------------|----------------------|
| Ingesta       | leer/escribir | leer/escribir         | solo leer             | —                    |
| Descripción   | leer/escribir | leer/escribir         | solo leer             | —                    |
| Vocabularios  | leer/escribir | leer/escribir         | solo leer             | —                    |
| Instrumentos  | leer/escribir | leer/escribir         | solo leer             | solo catálogo/índice |
| Preservación  | leer/escribir | leer/escribir (*)     | solo leer             | —                    |
| Auditoría     | todo          | solo su trazabilidad  | solo su trazabilidad  | —                    |
| Usuarios      | todo          | —                     | —                     | —                    |

(*) La configuración de preservación es solo del administrador.

El alcance del revisor es provisional: solo lectura en los módulos de
trabajo hasta que la autora del proyecto confirme sus capacidades.
"""

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.seguridad import TokenInvalido, leer_token_acceso
from app.db.session import get_db
from app.models.sesion import Sesion
from app.models.usuario import Usuario
from app.servicios import sesiones

ADMINISTRADOR = "administrador"
ARCHIVISTA = "archivista"
REVISOR = "revisor"
CONSULTA = "consulta"
ROLES = (ARCHIVISTA, REVISOR, CONSULTA, ADMINISTRADOR)

NOMBRE_ROL = {
    ADMINISTRADOR: "Administrador",
    ARCHIVISTA: "Archivista",
    REVISOR: "Revisor",
    CONSULTA: "Consulta",
}

MODULOS_TRABAJO = ("ingesta", "descripcion", "vocabularios", "instrumentos", "preservacion")

_TRABAJO = {"leer": {ADMINISTRADOR, ARCHIVISTA, REVISOR}, "escribir": {ADMINISTRADOR, ARCHIVISTA}}

MATRIZ: dict[str, dict[str, set[str]]] = {
    **{m: _TRABAJO for m in MODULOS_TRABAJO},
    # En auditoría cada endpoint filtra además por persona (el archivista
    # solo ve lo suyo); el panel consolidado exige administrador.
    "auditoria": {"leer": {ADMINISTRADOR, ARCHIVISTA, REVISOR}, "escribir": set()},
    "usuarios": {"leer": {ADMINISTRADOR}, "escribir": {ADMINISTRADOR}},
}

# Catálogo e índice de instrumentos: la única puerta del rol consulta.
LECTURA_CATALOGO = {ADMINISTRADOR, ARCHIVISTA, REVISOR, CONSULTA}

_METODOS_LECTURA = {"GET", "HEAD", "OPTIONS"}


@dataclass
class Actor:
    usuario: Usuario
    sesion: Sesion

    @property
    def id(self) -> uuid.UUID:
        return self.usuario.id

    @property
    def rol(self) -> str:
        return self.usuario.rol


_bearer = HTTPBearer(auto_error=False)


def _no_autenticado(codigo: str = "no_autenticado") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=codigo,
        headers={"WWW-Authenticate": "Bearer"},
    )


def sin_permiso() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Su rol no tiene permiso para esta acción.")


def usuario_actual(
    request: Request,
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Actor:
    """Dependencia base: exige un token de acceso válido de una sesión
    abierta y de una cuenta activa. 401 «token_expirado» le indica a la
    interfaz que renueve; cualquier otro 401 la lleva al inicio de sesión."""
    if credenciales is None or credenciales.scheme.lower() != "bearer":
        raise _no_autenticado()
    try:
        datos = leer_token_acceso(credenciales.credentials)
    except TokenInvalido as exc:
        raise _no_autenticado("token_expirado" if str(exc) == "expirado" else "no_autenticado") from exc

    sesion = db.get(Sesion, datos.sesion_id)
    if sesion is None or sesion.usuario_id != datos.usuario_id or sesion.cerrada_en is not None:
        raise _no_autenticado("sesion_cerrada")
    if sesiones.vencida(sesion):
        sesiones.cerrar(db, sesion, "expiracion")
        db.commit()
        raise _no_autenticado("sesion_cerrada")

    usuario = db.get(Usuario, datos.usuario_id)
    if usuario is None or not usuario.activo:
        sesiones.cerrar(db, sesion, "cuenta_desactivada")
        db.commit()
        raise _no_autenticado("sesion_cerrada")

    sesiones.registrar_actividad(db, sesion)
    actor = Actor(usuario=usuario, sesion=sesion)
    request.state.actor = actor
    return actor


def requiere_roles(*roles: str):
    permitidos = set(roles)

    def _dependencia(actor: Actor = Depends(usuario_actual)) -> Actor:
        if actor.rol not in permitidos:
            raise sin_permiso()
        return actor

    return _dependencia


def acceso_modulo(modulo: str):
    """Dependencia de router: lectura para GET, escritura para todo lo
    demás, según MATRIZ. Por construcción, un rol sin escritura (revisor,
    consulta) no puede ejecutar ninguna petición que modifique algo."""
    if modulo not in MATRIZ:
        raise ValueError(f"Módulo sin permisos definidos: {modulo}")

    def _dependencia(request: Request, actor: Actor = Depends(usuario_actual)) -> Actor:
        tipo = "leer" if request.method in _METODOS_LECTURA else "escribir"
        if actor.rol not in MATRIZ[modulo][tipo]:
            raise sin_permiso()
        return actor

    _dependencia.modulo = modulo  # para la prueba que recorre todas las rutas
    return _dependencia


solo_administrador = requiere_roles(ADMINISTRADOR)
lectura_catalogo = requiere_roles(*LECTURA_CATALOGO)
