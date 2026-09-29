"""M11 · Administración y seguridad (/admin/usuarios): usuarios con rol
(RF-M11-01), proveedores de inteligencia artificial con prueba de conexión
antes de activarlos (RF-M11-02) y parámetros del sistema; el flujo "Dar de
alta un usuario y activar un proveedor de inteligencia artificial"."""

import hashlib
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import auditoria_acciones, invitaciones, proveedores, roles
from .models import ConfiguracionSistema, ProveedorIAConfig, RegistroAuditoria

_PESTANAS = ("usuarios", "proveedores", "parametros", "auditoria", "eliminados")


def _volver(pestana="usuarios"):
    return redirect(f"/admin/usuarios/?pestana={pestana}")


def _entregar_invitacion(request, usuario, prefijo):
    """Envía la invitación y, si no salió por correo, deja el enlace a la
    vista del administrador (una sola vez) para que lo copie."""
    enviada, mensaje, url = invitaciones.enviar(request, usuario)
    if enviada:
        messages.success(request, f"{prefijo} {mensaje}")
    else:
        messages.warning(request, f"{prefijo} {mensaje}")
        request.session["ricora_invitacion"] = {"usuario": usuario.get_username(), "url": url}
    auditoria_acciones.registrar_accion("modificar", objeto=usuario, detalle={"invitacion": "enviada por correo" if enviada else "enlace entregado al administrador"})


def _datos_usuario(request):
    return {
        "username": request.POST.get("username", "").strip(),
        "nombre_completo": request.POST.get("nombre_completo", "").strip(),
        "email": request.POST.get("email", "").strip().lower(),
        "rol": request.POST.get("rol", ""),
    }


def _validar_usuario(datos, usuario=None):
    errores = []
    otros = User.objects.exclude(pk=usuario.pk) if usuario else User.objects.all()
    if usuario is None:
        if not datos["username"]:
            errores.append("Indique un nombre de usuario (con él se inicia sesión).")
        elif not re.fullmatch(r"[\w.@+-]+", datos["username"]):
            errores.append("El nombre de usuario solo admite letras, números y . @ + - _ (sin espacios).")
        elif otros.filter(username__iexact=datos["username"]).exists():
            errores.append(f"Ya existe una cuenta con el nombre de usuario «{datos['username']}».")
    if not datos["nombre_completo"]:
        errores.append("Escriba el nombre de la persona.")
    if not datos["email"]:
        errores.append("Escriba el correo: a él llega la invitación.")
    else:
        try:
            validate_email(datos["email"])
        except ValidationError:
            errores.append("El correo no tiene un formato válido.")
        else:
            if otros.filter(email__iexact=datos["email"]).exists():
                errores.append(f"El correo {datos['email']} ya pertenece a otra cuenta.")
    if datos["rol"] not in roles.ROLES_ASIGNABLES:
        errores.append("Elija uno de los cuatro roles: archivista, revisor, consulta o administrador.")
    return errores


def _crear_usuario(request):
    """RF-M11-01: nombre, correo y exactamente un rol; la contraseña la crea
    la propia persona con el enlace de invitación."""
    datos = _datos_usuario(request)
    errores = _validar_usuario(datos)
    if errores:
        return errores, datos
    try:
        with transaction.atomic():
            usuario = User.objects.create_user(username=datos["username"], email=datos["email"], first_name=datos["nombre_completo"])
            usuario.set_unusable_password()
            usuario.save(update_fields=["password"])
            roles.asignar_rol(usuario, datos["rol"])
    except IntegrityError:
        return [f"Ya existe una cuenta con el nombre de usuario «{datos['username']}»."], datos
    _entregar_invitacion(request, usuario, f"Cuenta creada: «{usuario.username}», rol {roles.ETIQUETAS[datos['rol']].lower()}.")
    return [], {}


def _filas_usuarios():
    filas = []
    for u in User.objects.order_by("-is_active", "first_name", "username"):
        rol = roles.rol_de(u)
        nombre = u.get_full_name() or u.username
        filas.append({
            "usuario": u, "rol": rol, "rol_etiqueta": roles.ETIQUETAS[rol], "nombre": nombre,
            "iniciales": "".join(p[0] for p in nombre.split()[:2]).upper() or u.username[:2].upper(),
            "pendiente": invitaciones.pendiente(u),
            "ultimo_admin": roles.es_ultimo_administrador(u),
        })
    return filas


@roles.requiere_rol()
def admin_usuarios(request):
    errores, datos = [], {}
    if request.method == "POST":
        errores, datos = _crear_usuario(request)
        if not errores:
            return _volver("usuarios")

    pestana = request.GET.get("pestana", "usuarios")
    if pestana not in _PESTANAS:
        pestana = "usuarios"
    contexto_extra = {}
    if pestana == "auditoria":
        contexto_extra = _contexto_auditoria(request)
    elif pestana == "eliminados":
        contexto_extra = {"eliminados": _eliminados()}
    filas = _filas_usuarios()
    return render(request, "ric/admin_usuarios.html", {
        **contexto_extra,
        "pestana": pestana,
        "errores": errores,
        "datos": datos,
        "usuarios": filas,
        "total_activos": sum(1 for f in filas if f["usuario"].is_active),
        "invitacion": request.session.pop("ricora_invitacion", None),
        "dias_invitacion": invitaciones.dias_vigencia(),
        "roles": [(r, roles.ETIQUETAS[r], roles.DESCRIPCIONES[r]) for r in roles.ROLES_ASIGNABLES],
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
    """RF-M11-01: editar nombre, correo y rol; desactivar o reactivar;
    restablecer el acceso (nueva invitación) y cerrar sesiones."""
    usuario = get_object_or_404(User, pk=pk)
    accion = request.POST.get("accion")
    try:
        if accion == "editar":
            datos = _datos_usuario(request)
            errores = _validar_usuario(datos, usuario)
            if errores:
                for e in errores:
                    messages.error(request, e)
                return _volver("usuarios")
            usuario.first_name, usuario.last_name, usuario.email = datos["nombre_completo"], "", datos["email"]
            with transaction.atomic():
                usuario.save(update_fields=["first_name", "last_name", "email"])
                roles.asignar_rol(usuario, datos["rol"])
            messages.success(request, f"Cuenta «{usuario.username}» actualizada: {roles.ETIQUETAS[datos['rol']].lower()}.")
        elif accion == "desactivar":
            if usuario.pk == request.user.pk:
                messages.error(request, "No puede desactivar su propia cuenta.")
            elif roles.es_ultimo_administrador(usuario):
                raise roles.UltimoAdministrador("Es el único administrador activo: no se puede desactivar.")
            else:
                usuario.is_active = False
                usuario.save(update_fields=["is_active"])
                cerradas = auditoria_acciones.cerrar_sesiones_de(usuario, motivo="cuenta desactivada")
                messages.info(request, f"Cuenta «{usuario.username}» desactivada: ya no puede iniciar sesión ({cerradas} sesión(es) abierta(s) cerrada(s)). Su historial se conserva.")
        elif accion == "reactivar":
            usuario.is_active = True
            usuario.save(update_fields=["is_active"])
            messages.success(request, f"Cuenta «{usuario.username}» reactivada.")
        elif accion == "restablecer":
            if usuario.pk == request.user.pk:
                messages.error(request, "Para cambiar su propia contraseña use un enlace que le genere otro administrador.")
                return _volver("usuarios")
            pendiente = invitaciones.pendiente(usuario)
            usuario.set_unusable_password()
            usuario.save(update_fields=["password"])
            cerradas = auditoria_acciones.cerrar_sesiones_de(usuario, motivo="acceso restablecido")
            prefijo = (f"Invitación de «{usuario.username}» renovada." if pendiente else
                       f"Acceso de «{usuario.username}» restablecido: su contraseña anterior dejó de servir ({cerradas} sesión(es) cerrada(s)).")
            _entregar_invitacion(request, usuario, prefijo)
        elif accion == "cerrar_sesiones":
            cerradas = auditoria_acciones.cerrar_sesiones_de(usuario, motivo="revocación manual del administrador")
            messages.info(request, f"{cerradas} sesión(es) de «{usuario.username}» cerrada(s).")
        else:
            messages.error(request, "Acción no reconocida.")
    except roles.UltimoAdministrador as e:
        messages.error(request, str(e))
    return _volver("usuarios")


_SAL_PRUEBA = "ricora-prueba-proveedor"
_VIGENCIA_PRUEBA = 15 * 60  # segundos: la prueba sirve para guardar durante 15 minutos


def _huella(proveedor, modelo, clave):
    """Lo probado y lo guardado deben ser lo mismo: si cambia el proveedor, el
    modelo o la clave después de probar, la prueba deja de valer."""
    return hashlib.sha256(f"{proveedor}|{modelo}|{clave}".encode()).hexdigest()


def _datos_proveedor(request):
    return (request.POST.get("proveedor", ""), request.POST.get("modelo", "").strip(), request.POST.get("clave_api", "").strip())


@roles.requiere_rol_api()
@require_POST
def admin_proveedor_probar_nuevo(request):
    """RF-M11-02, paso 6 del flujo: prueba de conexión real de un proveedor
    que todavía no se ha guardado. Si sale bien, entrega un comprobante
    firmado que el servidor exige para guardarlo."""
    proveedor, modelo, clave = _datos_proveedor(request)
    if proveedor not in ProveedorIAConfig.Proveedor.values:
        return JsonResponse({"ok": False, "mensaje": "Elija un proveedor de la lista."}, status=400)
    exitosa, mensaje = proveedores.probar_conexion(ProveedorIAConfig(proveedor=proveedor, modelo=modelo, clave_api=clave))
    auditoria_acciones.registrar_accion("modificar", exitoso=exitosa, detalle={"prueba_proveedor": proveedor, "modelo": modelo, "resultado": mensaje})
    comprobante = signing.dumps({"h": _huella(proveedor, modelo, clave), "m": mensaje}, salt=_SAL_PRUEBA) if exitosa else ""
    return JsonResponse({"ok": exitosa, "mensaje": mensaje, "comprobante": comprobante})


@roles.requiere_rol()
@require_POST
def admin_proveedor_agregar(request):
    """RF-M11-02: no se guarda un proveedor sin una prueba de conexión
    exitosa de esos mismos datos, hecha en los últimos 15 minutos."""
    proveedor, modelo, clave = _datos_proveedor(request)
    if proveedor not in ProveedorIAConfig.Proveedor.values:
        messages.error(request, "Elija un proveedor de la lista.")
        return _volver("proveedores")
    try:
        prueba = signing.loads(request.POST.get("comprobante", ""), salt=_SAL_PRUEBA, max_age=_VIGENCIA_PRUEBA)
    except signing.SignatureExpired:
        messages.error(request, "La prueba de conexión venció (15 minutos). Pruebe de nuevo antes de guardar.")
        return _volver("proveedores")
    except signing.BadSignature:
        messages.error(request, "Pruebe la conexión con éxito antes de guardar el proveedor.")
        return _volver("proveedores")
    if prueba.get("h") != _huella(proveedor, modelo, clave):
        messages.error(request, "Los datos cambiaron después de la prueba. Pruebe la conexión de nuevo antes de guardar.")
        return _volver("proveedores")
    with transaction.atomic():
        config = ProveedorIAConfig.objects.create(
            proveedor=proveedor, modelo=modelo, clave_api=clave, actualizado_por=request.user,
            prueba_exitosa=True, mensaje_prueba=prueba.get("m", ""), ultima_prueba=timezone.now(),
        )
        if request.POST.get("activar"):
            ProveedorIAConfig.objects.exclude(pk=config.pk).update(activo=False)
            config.activo = True
            config.save(update_fields=["activo"])
    if config.activo:
        messages.success(request, f"{config} guardado y activado como fuente del motor de análisis.")
    else:
        messages.success(request, f"{config} guardado. Puede activarlo o usarlo como respaldo cuando lo necesite.")
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
