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

from . import auditoria_acciones, proveedores, roles
from .models import ConfiguracionSistema, ProveedorIAConfig, RegistroAuditoria

_PESTANAS = ("usuarios", "proveedores", "parametros", "auditoria", "eliminados", "modulos")


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
    contexto_extra = {}
    if pestana == "auditoria":
        contexto_extra = _contexto_auditoria(request)
    elif pestana == "eliminados":
        contexto_extra = {"eliminados": _eliminados()}
    elif pestana == "modulos":
        from .modulos import MODULOS_ESPEC, modulo_espec

        contexto_extra = {"estado_modulos": [modulo_espec(n) for n in sorted(MODULOS_ESPEC)]}
    return render(request, "ric/admin_usuarios.html", {
        **contexto_extra,
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
            ProveedorIAConfig.Proveedor.OLLAMA: settings.RICORA_MODELO_OLLAMA,
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
            cerradas = auditoria_acciones.cerrar_sesiones_de(usuario, motivo="cuenta desactivada")
            messages.info(request, f'Cuenta "{usuario.username}" desactivada: ya no puede iniciar sesión ({cerradas} sesión(es) abierta(s) cerrada(s)).')
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
                cerradas = auditoria_acciones.cerrar_sesiones_de(usuario, motivo="contraseña restablecida")
                messages.success(request, f'Contraseña de "{usuario.username}" restablecida; {cerradas} sesión(es) abierta(s) cerrada(s).')
    elif accion == "cerrar_sesiones":
        cerradas = auditoria_acciones.cerrar_sesiones_de(usuario, motivo="revocación manual del administrador")
        messages.info(request, f'{cerradas} sesión(es) de "{usuario.username}" cerrada(s).')
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
    if request.POST.get("accion") in ("respaldo", "quitar_respaldo"):
        # Respaldo automático: si el principal falla, el motor usa este.
        poner = request.POST["accion"] == "respaldo"
        if poner and not config.prueba_exitosa:
            messages.error(request, "Pruebe la conexión con éxito antes de usar este proveedor como respaldo.")
            return _volver("proveedores")
        if poner:
            ProveedorIAConfig.objects.exclude(pk=pk).update(es_respaldo=False)
        config.es_respaldo = poner
        config.actualizado_por = request.user
        config.save()
        messages.success(request, f"{config} {'queda como respaldo automático del motor de análisis' if poner else 'ya no es respaldo'}.")
        return _volver("proveedores")
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
    if config.activo:
        config.activo = False
        config.save(update_fields=["activo"])
    config.eliminar(request.user, motivo="Retirado desde Administración")
    messages.info(request, f"{nombre} retirado (borrado lógico, queda en la auditoría).")
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


# ---------------------------------------------------------------------------
# Auditoría de acciones y papelera (borrado lógico)
# ---------------------------------------------------------------------------

def _filtrar_auditoria(request):
    qs = RegistroAuditoria.objects.select_related("usuario", "content_type")
    usuario = request.GET.get("usuario", "").strip()
    accion = request.GET.get("accion", "").strip()
    desde, hasta = request.GET.get("desde", "").strip(), request.GET.get("hasta", "").strip()
    q = request.GET.get("q", "").strip()
    if usuario:
        qs = qs.filter(usuario_nombre__icontains=usuario)
    if accion:
        qs = qs.filter(accion=accion)
    if desde:
        qs = qs.filter(fecha__date__gte=desde)
    if hasta:
        qs = qs.filter(fecha__date__lte=hasta)
    if q:
        qs = qs.filter(objeto_texto__icontains=q)
    return qs


def _contexto_auditoria(request):
    qs = _filtrar_auditoria(request)
    return {
        "registros": qs[:300], "total_auditoria": qs.count(),
        "acciones": RegistroAuditoria.Accion.choices,
        "filtro": {k: request.GET.get(k, "") for k in ("usuario", "accion", "desde", "hasta", "q")},
    }


def _eliminados(limite=200):
    """Lo borrado lógicamente, a partir de los registros de auditoría de
    borrado que todavía no tienen una restauración posterior."""
    filas = []
    for r in RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ELIMINAR).select_related("content_type")[: limite * 2]:
        if r.content_type is None:
            continue
        modelo = r.content_type.model_class()
        gestor = getattr(modelo, "todos", None)
        objeto = gestor.filter(pk=r.object_id).first() if gestor is not None else None
        if objeto is None or not getattr(objeto, "eliminado", False):
            continue
        filas.append({"registro": r, "objeto": objeto, "tipo": modelo._meta.verbose_name, "slug": r.content_type.model})
        if len(filas) >= limite:
            break
    return filas


@roles.requiere_rol()
def admin_auditoria_csv(request):
    import csv

    from django.http import HttpResponse

    salida = HttpResponse("\ufeff", content_type="text/csv; charset=utf-8")
    salida["Content-Disposition"] = f'attachment; filename="auditoria_{timezone.now():%Y%m%d_%H%M}.csv"'
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(["fecha", "usuario", "accion", "exitoso", "tipo", "objeto", "antes", "despues", "detalle", "ip"])
    for r in _filtrar_auditoria(request)[:5000]:
        escritor.writerow([r.fecha.isoformat(), r.usuario_nombre, r.get_accion_display(), r.exitoso,
                           r.content_type.model if r.content_type else "", r.objeto_texto, r.antes, r.despues, r.detalle, r.ip])
    auditoria_acciones.registrar_accion("modificar", detalle={"exportacion_auditoria": True, "filtro": dict(request.GET.items())})
    return salida


@roles.requiere_rol()
@require_POST
def admin_restaurar(request):
    from django.contrib.contenttypes.models import ContentType

    ct = get_object_or_404(ContentType, app_label="ric", model=request.POST.get("modelo", ""))
    modelo = ct.model_class()
    objeto = get_object_or_404(getattr(modelo, "todos", modelo._base_manager), pk=request.POST.get("pk"))
    if not getattr(objeto, "eliminado", False):
        messages.info(request, f"«{objeto}» no estaba eliminado.")
    else:
        objeto.restaurar(request.user)
        messages.success(request, f"«{objeto}» restaurado.")
    return _volver("eliminados")
