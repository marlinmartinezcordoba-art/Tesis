"""M11 · Administración y seguridad (/admin/usuarios): usuarios con rol
(RF-M11-01), proveedores de inteligencia artificial con prueba de conexión
antes de activarlos (RF-M11-02) y parámetros del sistema; el flujo "Dar de
alta un usuario y activar un proveedor de inteligencia artificial"."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import proveedores, roles
from .models import ConfiguracionSistema, ProveedorIAConfig

_PESTANAS = ("usuarios", "proveedores", "parametros")


def _volver(pestana="usuarios"):
    return redirect(f"/admin/usuarios/?pestana={pestana}")


def _enviar_invitacion(request, usuario, contrasena):
    """Paso 3 del flujo: invitación por correo. Sin servidor de correo
    configurado (EMAIL_HOST) se dice claramente, no se finge el envío."""
    if not usuario.email:
        return "Sin correo: comparta el usuario y la contraseña directamente."
    if not settings.EMAIL_HOST:
        return "Correo no configurado en el servidor (EMAIL_HOST): comparta la contraseña directamente."
    try:
        send_mail(
            "Acceso a RICORA",
            f"Hola {usuario.first_name or usuario.username}.\n\nSe creó tu cuenta en RICORA.\n"
            f"Usuario: {usuario.username}\nContraseña inicial: {contrasena}\n"
            f"Ingresa en {request.build_absolute_uri('/ric/entrar/')} y cámbiala al entrar.\n",
            settings.DEFAULT_FROM_EMAIL, [usuario.email], fail_silently=False,
        )
    except Exception as e:  # el error real se muestra, no se oculta
        return f"No fue posible enviar la invitación: {e}"
    return f"Invitación enviada a {usuario.email}."


def _crear_usuario(request):
    nombre_usuario = request.POST.get("username", "").strip()
    nombre_completo = request.POST.get("nombre_completo", "").strip()
    correo = request.POST.get("email", "").strip()
    contrasena = request.POST.get("password", "")
    confirmar = request.POST.get("password_confirmar", "")
    rol = request.POST.get("rol", roles.CONSULTA)
    errores = []

    if not nombre_usuario:
        errores.append("Indique un nombre de usuario.")
    elif User.objects.filter(username__iexact=nombre_usuario).exists():
        errores.append(f'Ya existe una cuenta con el nombre de usuario "{nombre_usuario}".')
    if contrasena != confirmar:
        errores.append("La contraseña y su confirmación no coinciden.")
    elif not contrasena:
        errores.append("Escriba una contraseña.")
    else:
        try:
            validate_password(contrasena)
        except ValidationError as e:
            errores.extend(e.messages)
    if rol not in roles.ROLES_ASIGNABLES:
        errores.append("Elija un rol válido: archivista, revisor o consulta.")
    if errores:
        return errores

    try:
        usuario = User.objects.create_user(username=nombre_usuario, password=contrasena, email=correo, first_name=nombre_completo)
    except IntegrityError:
        return [f'Ya existe una cuenta con el nombre de usuario "{nombre_usuario}".']
    roles.asignar_rol(usuario, rol)
    messages.success(request, f'Cuenta creada: "{nombre_usuario}", rol {roles.ETIQUETAS[rol].lower()}. {_enviar_invitacion(request, usuario, contrasena)}')
    return []


@roles.requiere_rol()
def admin_usuarios(request):
    errores = []
    if request.method == "POST":
        errores = _crear_usuario(request)
        if not errores:
            return _volver("usuarios")

    pestana = request.GET.get("pestana", "usuarios")
    if pestana not in _PESTANAS:
        pestana = "usuarios"
    usuarios = [
        {"usuario": u, "rol": roles.rol_de(u), "rol_etiqueta": roles.ETIQUETAS[roles.rol_de(u)]}
        for u in User.objects.order_by("-is_active", "username")
    ]
    return render(request, "ric/admin_usuarios.html", {
        "pestana": pestana,
        "errores": errores,
        "usuarios": usuarios,
        "roles": [(r, roles.ETIQUETAS[r]) for r in roles.ROLES_ASIGNABLES],
        "proveedores": ProveedorIAConfig.objects.all(),
        "opciones_proveedor": ProveedorIAConfig.Proveedor.choices,
        "config": ConfiguracionSistema.actual(),
        "correo_configurado": bool(settings.EMAIL_HOST),
        "modelos_por_defecto": {
            ProveedorIAConfig.Proveedor.GEMINI: settings.MAZUCA_MODELO_IA_GEMINI,
            ProveedorIAConfig.Proveedor.CLAUDE: settings.MAZUCA_MODELO_IA,
            ProveedorIAConfig.Proveedor.LOCAL: "es_core_news_md",
        },
    })


@roles.requiere_rol()
@require_POST
def admin_usuario_editar(request, pk):
    """RF-M11-01: editar el rol, desactivar o reactivar, restablecer la contraseña."""
    usuario = get_object_or_404(User, pk=pk)
    accion = request.POST.get("accion")
    if usuario.is_superuser and accion in ("cambiar_rol", "desactivar"):
        messages.error(request, "La cuenta superusuario no se puede degradar ni desactivar desde aquí.")
        return _volver("usuarios")
    if accion == "cambiar_rol":
        rol = request.POST.get("rol", "")
        if rol not in roles.ROLES_ASIGNABLES:
            messages.error(request, "Rol no válido.")
        else:
            roles.asignar_rol(usuario, rol)
            messages.success(request, f'"{usuario.username}" ahora es {roles.ETIQUETAS[rol].lower()}.')
    elif accion == "desactivar":
        if usuario.pk == request.user.pk:
            messages.error(request, "No puede desactivar su propia cuenta.")
        else:
            usuario.is_active = False
            usuario.save(update_fields=["is_active"])
            messages.info(request, f'Cuenta "{usuario.username}" desactivada: ya no puede iniciar sesión.')
    elif accion == "reactivar":
        usuario.is_active = True
        usuario.save(update_fields=["is_active"])
        messages.success(request, f'Cuenta "{usuario.username}" reactivada.')
    elif accion == "restablecer":
        contrasena = request.POST.get("password", "")
        if contrasena != request.POST.get("password_confirmar", ""):
            messages.error(request, "La contraseña y su confirmación no coinciden.")
        else:
            try:
                validate_password(contrasena, user=usuario)
            except ValidationError as e:
                messages.error(request, " ".join(e.messages))
            else:
                usuario.set_password(contrasena)
                usuario.save()
                messages.success(request, f'Contraseña de "{usuario.username}" restablecida.')
    else:
        messages.error(request, "Acción no reconocida.")
    return _volver("usuarios")


@roles.requiere_rol()
@require_POST
def admin_proveedor_agregar(request):
    proveedor = request.POST.get("proveedor", "")
    if proveedor not in ProveedorIAConfig.Proveedor.values:
        messages.error(request, "Elija un proveedor de la lista.")
        return _volver("proveedores")
    config = ProveedorIAConfig.objects.create(
        proveedor=proveedor, modelo=request.POST.get("modelo", "").strip(),
        clave_api=request.POST.get("clave_api", "").strip(), actualizado_por=request.user,
    )
    messages.success(request, f"{config} agregado. Pruebe la conexión antes de activarlo como fuente del motor de análisis.")
    return _volver("proveedores")


@roles.requiere_rol()
@require_POST
def admin_proveedor_probar(request, pk):
    """RF-M11-02: prueba de conexión real; el resultado queda guardado y
    habilita (o no) el botón de activar."""
    config = get_object_or_404(ProveedorIAConfig, pk=pk)
    exitosa, mensaje = proveedores.probar_conexion(config)
    config.prueba_exitosa = exitosa
    config.mensaje_prueba = mensaje
    config.ultima_prueba = timezone.now()
    config.actualizado_por = request.user
    config.save()
    (messages.success if exitosa else messages.error)(request, f"{config}: {mensaje}")
    return _volver("proveedores")


@roles.requiere_rol()
@require_POST
def admin_proveedor_activar(request, pk):
    config = get_object_or_404(ProveedorIAConfig, pk=pk)
    if request.POST.get("accion") == "desactivar":
        config.activo = False
        config.save(update_fields=["activo"])
        messages.info(request, f"{config} ya no es la fuente del motor de análisis.")
        return _volver("proveedores")
    if not config.prueba_exitosa:
        messages.error(request, "Pruebe la conexión con éxito antes de activar este proveedor.")
        return _volver("proveedores")
    ProveedorIAConfig.objects.exclude(pk=pk).update(activo=False)
    config.activo = True
    config.actualizado_por = request.user
    config.save()
    messages.success(request, f"{config} activado como fuente del motor de análisis.")
    return _volver("proveedores")


@roles.requiere_rol()
@require_POST
def admin_proveedor_eliminar(request, pk):
    config = get_object_or_404(ProveedorIAConfig, pk=pk)
    nombre = str(config)
    config.delete()
    messages.info(request, f"{nombre} eliminado.")
    return _volver("proveedores")


@roles.requiere_rol()
@require_POST
def admin_parametros(request):
    config = ConfiguracionSistema.actual()
    try:
        config.dias_limite_revision = int(request.POST.get("dias_limite_revision", config.dias_limite_revision))
        config.umbral_calidad_ocr = float(request.POST.get("umbral_calidad_ocr", config.umbral_calidad_ocr))
        config.umbral_confianza_revision = float(request.POST.get("umbral_confianza_revision", config.umbral_confianza_revision))
        config.umbral_similitud_vocabulario = float(request.POST.get("umbral_similitud_vocabulario", config.umbral_similitud_vocabulario))
    except ValueError:
        messages.error(request, "Los parámetros deben ser números.")
        return _volver("parametros")
    if not (0 <= config.umbral_calidad_ocr <= 100 and 0 <= config.umbral_confianza_revision <= 1 and 0 <= config.umbral_similitud_vocabulario <= 1 and config.dias_limite_revision >= 1):
        messages.error(request, "Rangos: días ≥ 1, calidad OCR 0-100, confianza y similitud entre 0 y 1.")
        return _volver("parametros")
    config.actualizado_por = request.user
    config.save()
    messages.success(request, "Parámetros guardados.")
    return _volver("parametros")
