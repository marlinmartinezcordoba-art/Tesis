"""
Módulo transversal de autenticación y autorización.

Rutas públicas (sin sesión): ingresar, renovar, salir, pedir recuperación,
consultar un enlace y definir contraseña con él. Todo lo demás exige
sesión, y la gestión de usuarios exige además el rol administrador.
"""

import uuid
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import correo
from app.core.config import settings
from app.core.permisos import (
    ADMINISTRADOR,
    NOMBRE_ROL,
    Actor,
    acceso_modulo,
    usuario_actual,
)
from app.core.seguridad import (
    cifrar_contrasena,
    crear_token_acceso,
    huella,
    problemas_contrasena,
    verificar_contrasena,
)
from app.db.base import ahora
from app.db.session import get_db
from app.models.auditoria import RegistroAuditoria
from app.models.sesion import Sesion
from app.models.token_acceso import TokenUnUso
from app.models.usuario import Usuario
from app.schemas.auth import (
    CambiarContrasenaIn,
    DefinirContrasenaIn,
    EnlaceInfoOut,
    EntregaOut,
    IngresoIn,
    MensajeOut,
    PerfilOut,
    RecuperarIn,
    SesionOut,
    UsuarioBreve,
    UsuarioCreadoOut,
    UsuarioEdicionIn,
    UsuarioNuevoIn,
    UsuarioOut,
    UsuariosOut,
)
from app.servicios import enlaces, sesiones
from app.servicios.auditoria import Accion, ip_de, registrar

router = APIRouter(prefix="/api/auth", tags=["Autenticación y autorización"])

GALLETA = "ricora_renovacion"
RUTA_GALLETA = "/api/auth"

MENSAJE_INGRESO_FALLIDO = "Correo o contraseña incorrectos."
MENSAJE_RECUPERACION = (
    "Si el correo está registrado, le llegará un enlace para definir una contraseña nueva. "
    "El enlace sirve una sola vez y vence en poco tiempo."
)
MENSAJE_ENLACE_INVALIDO = "El enlace no es válido, ya se usó o ya venció. Pida uno nuevo."


# --- utilidades ----------------------------------------------------------------


def _normalizar(correo_texto: str) -> str:
    return correo_texto.strip().lower()


def _breve(usuario: Usuario) -> UsuarioBreve:
    return UsuarioBreve(
        id=usuario.id,
        nombre=usuario.nombre,
        correo=usuario.correo,
        rol=usuario.rol,
        rol_nombre=NOMBRE_ROL[usuario.rol],
        iniciales=usuario.iniciales,
    )


def _poner_galleta(response: Response, valor: str) -> None:
    response.set_cookie(
        GALLETA,
        valor,
        max_age=settings.horas_maximas_sesion * 3600,
        path=RUTA_GALLETA,
        httponly=True,
        secure=settings.galleta_segura,
        samesite="strict",
    )


def _borrar_galleta(response: Response) -> None:
    response.delete_cookie(GALLETA, path=RUTA_GALLETA, httponly=True, secure=settings.galleta_segura, samesite="strict")


def _respuesta_sesion(response: Response, usuario: Usuario, sesion: Sesion, galleta: str) -> SesionOut:
    token, segundos = crear_token_acceso(usuario.id, sesion.id, usuario.rol)
    _poner_galleta(response, galleta)
    response.headers["Cache-Control"] = "no-store"
    return SesionOut(token_acceso=token, expira_en=segundos, rol=usuario.rol, usuario=_breve(usuario))


def _intentos_fallidos_recientes(db: Session, correo_normalizado: str, usuario: Usuario | None) -> int:
    desde = ahora() - timedelta(minutes=settings.minutos_bloqueo)
    if usuario is not None:
        ultimo_ingreso = db.scalar(
            select(func.max(Sesion.iniciada_en)).where(Sesion.usuario_id == usuario.id)
        )
        if ultimo_ingreso and ultimo_ingreso > desde:
            desde = ultimo_ingreso
    return db.scalar(
        select(func.count(RegistroAuditoria.id)).where(
            RegistroAuditoria.accion == Accion.INGRESO_FALLIDO,
            RegistroAuditoria.entidad_id == huella(correo_normalizado),
            RegistroAuditoria.fecha > desde,
        )
    ) or 0


def _administradores_activos(db: Session) -> int:
    return db.scalar(
        select(func.count(Usuario.id)).where(Usuario.rol == ADMINISTRADOR, Usuario.activo.is_(True))
    ) or 0


def _usuario_out(db: Session, usuario: Usuario) -> UsuarioOut:
    ultimo = db.scalar(select(func.max(Sesion.iniciada_en)).where(Sesion.usuario_id == usuario.id))
    abiertas = db.scalar(
        select(func.count(Sesion.id)).where(Sesion.usuario_id == usuario.id, Sesion.cerrada_en.is_(None))
    ) or 0
    solicitud = db.scalar(
        select(func.max(TokenUnUso.creado_en)).where(
            TokenUnUso.usuario_id == usuario.id,
            TokenUnUso.tipo == "recuperacion",
            TokenUnUso.usado_en.is_(None),
            TokenUnUso.creado_en > ahora() - timedelta(hours=24),
        )
    )
    recuperacion = bool(solicitud) and (
        usuario.contrasena_cambiada_en is None or usuario.contrasena_cambiada_en < solicitud
    )
    return UsuarioOut(
        id=usuario.id,
        nombre=usuario.nombre,
        correo=usuario.correo,
        rol=usuario.rol,
        rol_nombre=NOMBRE_ROL[usuario.rol],
        iniciales=usuario.iniciales,
        activo=usuario.activo,
        invitacion_pendiente=usuario.invitacion_pendiente,
        recuperacion_solicitada=recuperacion,
        ultimo_ingreso=ultimo,
        sesiones_abiertas=abiertas,
        creado_en=usuario.creado_en,
    )


def _validar_contrasena(contrasena: str, correo_usuario: str) -> None:
    problemas = problemas_contrasena(contrasena, correo_usuario)
    if problemas:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=" ".join(problemas))


# --- rutas públicas --------------------------------------------------------------


@router.post("/login", response_model=SesionOut, summary="Iniciar sesión con correo y contraseña")
def ingresar(datos: IngresoIn, request: Request, response: Response, db: Session = Depends(get_db)):
    sesiones.cerrar_vencidas(db)
    correo_normalizado = _normalizar(datos.correo)
    usuario = db.scalar(select(Usuario).where(Usuario.correo == correo_normalizado))
    ip = ip_de(request)

    if _intentos_fallidos_recientes(db, correo_normalizado, usuario) >= settings.intentos_fallidos_maximos:
        registrar(db, modulo="autenticacion", accion=Accion.INGRESO_BLOQUEADO,
                  usuario_id=usuario.id if usuario else None, entidad_tipo="correo",
                  entidad_id=huella(correo_normalizado), ip=ip)
        db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Espere {settings.minutos_bloqueo} minutos e intente de nuevo.",
        )

    # Mismo mensaje si el correo no existe, si la contraseña no coincide,
    # si la cuenta está desactivada o si aún no definió contraseña.
    valida = verificar_contrasena(datos.contrasena, usuario.contrasena_hash if usuario else None)
    if not valida or usuario is None or not usuario.activo:
        registrar(db, modulo="autenticacion", accion=Accion.INGRESO_FALLIDO,
                  usuario_id=usuario.id if usuario else None, entidad_tipo="correo",
                  entidad_id=huella(correo_normalizado), ip=ip)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=MENSAJE_INGRESO_FALLIDO)

    sesion, galleta = sesiones.abrir(db, usuario, ip=ip, navegador=request.headers.get("user-agent"))
    db.commit()
    return _respuesta_sesion(response, usuario, sesion, galleta)


@router.post("/refresh", response_model=SesionOut, summary="Renovar el token de acceso con la galleta de sesión")
def renovar(response: Response, db: Session = Depends(get_db),
            ricora_renovacion: str | None = Cookie(default=None)):
    sesiones.cerrar_vencidas(db)
    db.commit()
    try:
        sesion, galleta = sesiones.renovar(db, ricora_renovacion)
    except sesiones.RenovacionInvalida:
        respuesta = JSONResponse({"detail": "sesion_cerrada"}, status_code=status.HTTP_401_UNAUTHORIZED)
        _borrar_galleta(respuesta)
        return respuesta
    usuario = db.get(Usuario, sesion.usuario_id)
    db.commit()
    return _respuesta_sesion(response, usuario, sesion, galleta)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Cerrar la sesión actual")
def salir(request: Request, db: Session = Depends(get_db),
          ricora_renovacion: str | None = Cookie(default=None)):
    if ricora_renovacion and "." in ricora_renovacion:
        sid_texto, secreto = ricora_renovacion.split(".", 1)
        try:
            sesion = db.get(Sesion, uuid.UUID(sid_texto))
        except ValueError:
            sesion = None
        if sesion is not None and sesion.cerrada_en is None and sesion.huella_renovacion == huella(secreto):
            sesiones.cerrar(db, sesion, "cierre_voluntario", ip=ip_de(request))
            db.commit()
    respuesta = Response(status_code=status.HTTP_204_NO_CONTENT)
    _borrar_galleta(respuesta)
    return respuesta


def _enviar_recuperacion_en_segundo_plano(nombre: str, correo_usuario: str, token: str) -> None:
    try:
        correo.enviar_recuperacion(nombre, correo_usuario, enlaces.url_de(token), settings.minutos_token_recuperacion)
    except (correo.CorreoNoConfigurado, correo.CorreoFallido):
        # La persona ve el mismo mensaje de siempre; el administrador ve en
        # Usuarios que esa cuenta pidió recuperar la contraseña.
        pass


@router.post("/recuperar", response_model=MensajeOut, status_code=status.HTTP_202_ACCEPTED,
             summary="Pedir un enlace de recuperación (responde igual exista o no el correo)")
def pedir_recuperacion(datos: RecuperarIn, request: Request, tareas: BackgroundTasks, db: Session = Depends(get_db)):
    ip = ip_de(request)
    correo_normalizado = _normalizar(datos.correo)
    recientes = db.scalar(
        select(func.count(RegistroAuditoria.id)).where(
            RegistroAuditoria.accion == Accion.SOLICITUD_RECUPERACION,
            RegistroAuditoria.ip == ip,
            RegistroAuditoria.fecha > ahora() - timedelta(hours=1),
        )
    ) or 0
    usuario = db.scalar(select(Usuario).where(Usuario.correo == correo_normalizado))
    registrar(db, modulo="autenticacion", accion=Accion.SOLICITUD_RECUPERACION,
              usuario_id=usuario.id if usuario else None, entidad_tipo="correo",
              entidad_id=huella(correo_normalizado),
              detalle="limite_por_hora" if recientes >= settings.recuperaciones_por_hora else None, ip=ip)
    if recientes < settings.recuperaciones_por_hora and usuario is not None and usuario.activo:
        token = enlaces.crear(db, usuario, "recuperacion", ip=ip)
        tareas.add_task(_enviar_recuperacion_en_segundo_plano, usuario.nombre, usuario.correo, token)
    db.commit()
    return MensajeOut(mensaje=MENSAJE_RECUPERACION)


@router.get("/token/{token}", response_model=EnlaceInfoOut, summary="Consultar si un enlace de un solo uso sigue vigente")
def consultar_enlace(token: str, db: Session = Depends(get_db)):
    encontrado = enlaces.vigente(db, token)
    if encontrado is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=MENSAJE_ENLACE_INVALIDO)
    registro, usuario = encontrado
    return EnlaceInfoOut(tipo=registro.tipo, nombre=usuario.nombre, correo=usuario.correo)


@router.post("/recuperar/{token}", response_model=MensajeOut,
             summary="Definir la contraseña con un enlace de invitación o de recuperación")
def definir_contrasena(token: str, datos: DefinirContrasenaIn, request: Request, db: Session = Depends(get_db)):
    encontrado = enlaces.vigente(db, token)
    if encontrado is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=MENSAJE_ENLACE_INVALIDO)
    registro, usuario = encontrado
    _validar_contrasena(datos.contrasena, usuario.correo)
    momento = ahora()
    registro.usado_en = momento
    usuario.contrasena_hash = cifrar_contrasena(datos.contrasena)
    usuario.contrasena_cambiada_en = momento
    ip = ip_de(request)
    # Por seguridad, cualquier sesión abierta con la contraseña anterior se cierra.
    sesiones.cerrar_todas(db, usuario.id, "cambio_contrasena", ip=ip)
    registrar(db, modulo="autenticacion", accion=Accion.CONTRASENA_DEFINIDA, usuario_id=usuario.id,
              entidad_tipo="usuario", entidad_id=usuario.id, nuevo={"via": registro.tipo}, ip=ip)
    db.commit()
    return MensajeOut(mensaje="Su contraseña quedó definida. Ya puede iniciar sesión.")


# --- sesión propia -----------------------------------------------------------------


@router.get("/perfil", response_model=PerfilOut, summary="Datos de la cuenta con sesión abierta")
def perfil(actor: Actor = Depends(usuario_actual)):
    u = actor.usuario
    return PerfilOut(id=u.id, nombre=u.nombre, correo=u.correo, rol=u.rol, rol_nombre=NOMBRE_ROL[u.rol],
                     iniciales=u.iniciales, contrasena_cambiada_en=u.contrasena_cambiada_en)


@router.patch("/perfil/contrasena", response_model=MensajeOut, summary="Cambiar la propia contraseña")
def cambiar_contrasena(datos: CambiarContrasenaIn, request: Request, actor: Actor = Depends(usuario_actual),
                       db: Session = Depends(get_db)):
    usuario = actor.usuario
    if not verificar_contrasena(datos.actual, usuario.contrasena_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="La contraseña actual no es correcta.")
    if datos.nueva == datos.actual:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La contraseña nueva debe ser distinta de la actual.")
    _validar_contrasena(datos.nueva, usuario.correo)
    usuario.contrasena_hash = cifrar_contrasena(datos.nueva)
    usuario.contrasena_cambiada_en = ahora()
    ip = ip_de(request)
    otras = sesiones.cerrar_todas(db, usuario.id, "cambio_contrasena", excepto=actor.sesion.id, ip=ip)
    registrar(db, modulo="autenticacion", accion=Accion.CONTRASENA_CAMBIADA, usuario_id=usuario.id,
              entidad_tipo="usuario", entidad_id=usuario.id, nuevo={"otras_sesiones_cerradas": otras}, ip=ip)
    db.commit()
    return MensajeOut(mensaje="Contraseña actualizada." + (" Se cerraron sus otras sesiones abiertas." if otras else ""))


# --- gestión de usuarios (solo administrador) ----------------------------------------

usuarios = APIRouter(prefix="/api/auth", tags=["Autenticación y autorización"],
                     dependencies=[Depends(acceso_modulo("usuarios"))])


@usuarios.get("/usuarios", response_model=UsuariosOut, summary="Listar usuarios (filtrable)")
def listar_usuarios(q: str | None = None, rol: str | None = None, activo: bool | None = None,
                    db: Session = Depends(get_db)):
    consulta = select(Usuario)
    if q:
        patron = f"%{q.strip().lower()}%"
        consulta = consulta.where(or_(func.lower(Usuario.nombre).like(patron), Usuario.correo.like(patron)))
    if rol:
        consulta = consulta.where(Usuario.rol == rol)
    if activo is not None:
        consulta = consulta.where(Usuario.activo.is_(activo))
    filas = db.scalars(consulta.order_by(Usuario.activo.desc(), Usuario.nombre)).all()
    return UsuariosOut(usuarios=[_usuario_out(db, u) for u in filas], correo_configurado=settings.correo_configurado)


@usuarios.post("/usuarios", response_model=UsuarioCreadoOut, status_code=status.HTTP_201_CREATED,
               summary="Crear un usuario y enviarle la invitación")
def crear_usuario(datos: UsuarioNuevoIn, request: Request, actor: Actor = Depends(usuario_actual),
                  db: Session = Depends(get_db)):
    correo_normalizado = _normalizar(str(datos.correo))
    if db.scalar(select(Usuario.id).where(Usuario.correo == correo_normalizado)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Ya existe un usuario con ese correo.")
    usuario = Usuario(id=uuid.uuid4(), nombre=datos.nombre, correo=correo_normalizado, rol=datos.rol,
                      activo=True, creado_por_id=actor.id)
    db.add(usuario)
    db.flush()
    ip = ip_de(request)
    token = enlaces.crear(db, usuario, "invitacion", ip=ip)
    registrar(db, modulo="autenticacion", accion=Accion.USUARIO_CREADO, usuario_id=actor.id,
              entidad_tipo="usuario", entidad_id=usuario.id,
              nuevo={"nombre": usuario.nombre, "correo": usuario.correo, "rol": usuario.rol}, ip=ip)
    db.commit()
    entrega = enlaces.entregar(usuario, "invitacion", token)
    registrar(db, modulo="autenticacion", accion=Accion.ENLACE_ENVIADO, usuario_id=actor.id,
              entidad_tipo="usuario", entidad_id=usuario.id,
              nuevo={"tipo": "invitacion", "por_correo": entrega.enviado}, ip=ip)
    db.commit()
    return UsuarioCreadoOut(usuario=_usuario_out(db, usuario), entrega=EntregaOut(**entrega.__dict__))


def _usuario_o_404(db: Session, usuario_id: uuid.UUID) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El usuario no existe.")
    return usuario


@usuarios.patch("/usuarios/{usuario_id}", response_model=UsuarioOut,
                summary="Editar nombre o rol, desactivar o reactivar un usuario")
def editar_usuario(usuario_id: uuid.UUID, datos: UsuarioEdicionIn, request: Request,
                   actor: Actor = Depends(usuario_actual), db: Session = Depends(get_db)):
    usuario = _usuario_o_404(db, usuario_id)
    es_propio = usuario.id == actor.id
    ip = ip_de(request)

    if datos.rol is not None and datos.rol != usuario.rol:
        if es_propio:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Nadie puede cambiar su propio rol.")
        if usuario.rol == ADMINISTRADOR and usuario.activo and _administradores_activos(db) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                detail="Es el único administrador activo: asigne primero el rol a otra persona.")
    if datos.activo is False and usuario.activo:
        if es_propio:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No puede desactivar su propia cuenta.")
        if usuario.rol == ADMINISTRADOR and _administradores_activos(db) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="No se puede desactivar al único administrador activo.")

    anterior, nuevo = {}, {}
    if datos.nombre is not None and datos.nombre != usuario.nombre:
        anterior["nombre"], nuevo["nombre"] = usuario.nombre, datos.nombre
        usuario.nombre = datos.nombre
    if datos.rol is not None and datos.rol != usuario.rol:
        anterior["rol"], nuevo["rol"] = usuario.rol, datos.rol
        usuario.rol = datos.rol
    if anterior:
        registrar(db, modulo="autenticacion", accion=Accion.USUARIO_EDITADO, usuario_id=actor.id,
                  entidad_tipo="usuario", entidad_id=usuario.id, anterior=anterior, nuevo=nuevo, ip=ip)

    if datos.activo is not None and datos.activo != usuario.activo:
        usuario.activo = datos.activo
        if datos.activo:
            registrar(db, modulo="autenticacion", accion=Accion.USUARIO_REACTIVADO, usuario_id=actor.id,
                      entidad_tipo="usuario", entidad_id=usuario.id,
                      anterior={"activo": False}, nuevo={"activo": True}, ip=ip)
        else:
            sesiones.cerrar_todas(db, usuario.id, "cuenta_desactivada", por=actor.id, ip=ip)
            registrar(db, modulo="autenticacion", accion=Accion.USUARIO_DESACTIVADO, usuario_id=actor.id,
                      entidad_tipo="usuario", entidad_id=usuario.id,
                      anterior={"activo": True}, nuevo={"activo": False}, ip=ip)
    db.commit()
    return _usuario_out(db, usuario)


@usuarios.post("/usuarios/{usuario_id}/enlace", response_model=EntregaOut,
               summary="Enviar de nuevo la invitación, o un enlace de recuperación")
def enviar_enlace(usuario_id: uuid.UUID, request: Request, actor: Actor = Depends(usuario_actual),
                  db: Session = Depends(get_db)):
    usuario = _usuario_o_404(db, usuario_id)
    if not usuario.activo:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Reactive la cuenta antes de enviarle un enlace.")
    if usuario.id == actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Para su propia cuenta use «Mi perfil» o «Olvidé mi contraseña».")
    tipo = "invitacion" if usuario.invitacion_pendiente else "recuperacion"
    ip = ip_de(request)
    token = enlaces.crear(db, usuario, tipo, ip=ip)
    db.commit()
    entrega = enlaces.entregar(usuario, tipo, token)
    registrar(db, modulo="autenticacion", accion=Accion.ENLACE_ENVIADO, usuario_id=actor.id,
              entidad_tipo="usuario", entidad_id=usuario.id, nuevo={"tipo": tipo, "por_correo": entrega.enviado}, ip=ip)
    db.commit()
    return EntregaOut(**entrega.__dict__)


@usuarios.post("/usuarios/{usuario_id}/cerrar-sesiones", response_model=MensajeOut,
               summary="Revocar todas las sesiones abiertas de un usuario")
def cerrar_sesiones(usuario_id: uuid.UUID, request: Request, actor: Actor = Depends(usuario_actual),
                    db: Session = Depends(get_db)):
    usuario = _usuario_o_404(db, usuario_id)
    excepto = actor.sesion.id if usuario.id == actor.id else None
    ip = ip_de(request)
    n = sesiones.cerrar_todas(db, usuario.id, "revocada_administrador", excepto=excepto, por=actor.id, ip=ip)
    registrar(db, modulo="autenticacion", accion=Accion.SESIONES_REVOCADAS, usuario_id=actor.id,
              entidad_tipo="usuario", entidad_id=usuario.id, nuevo={"sesiones_cerradas": n}, ip=ip)
    db.commit()
    return MensajeOut(mensaje=f"Se cerraron {n} sesión(es)." if n else "No tenía sesiones abiertas.")


@usuarios.post("/correo/prueba", response_model=MensajeOut, summary="Enviar un correo de prueba al propio administrador")
def probar_correo(actor: Actor = Depends(usuario_actual)):
    try:
        correo.enviar_prueba(actor.usuario.correo)
    except correo.CorreoNoConfigurado:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="El envío de correo aún no está configurado en el servidor.")
    except correo.CorreoFallido as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            detail=f"El servidor de correo rechazó el envío ({exc}). Revise usuario y contraseña de aplicación.")
    return MensajeOut(mensaje=f"Correo de prueba enviado a {actor.usuario.correo}.")
