"""Inicio de sesión con bloqueo por intentos fallidos (OWASP: fuerza bruta).
Tras INTENTOS_MAXIMOS fallos en MINUTOS_BLOQUEO minutos para un mismo
nombre de usuario, el sistema rechaza el ingreso sin siquiera comprobar la
contraseña, y lo deja en la auditoría."""

from django.contrib.auth.views import LoginView

from .auditoria_acciones import INTENTOS_MAXIMOS, MINUTOS_BLOQUEO, bloqueado, registrar_accion


class IngresoView(LoginView):
    template_name = "ric/login.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        nombre = request.POST.get("username", "").strip()
        if bloqueado(nombre):
            registrar_accion("bloqueo_login", detalle={"usuario": nombre}, exitoso=False)
            form = self.get_form()
            return self.render_to_response(self.get_context_data(form=form, bloqueado=True, minutos=MINUTOS_BLOQUEO, intentos=INTENTOS_MAXIMOS))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        # Si recordó su contraseña, la solicitud de restablecimiento ya no hace falta.
        from .models import SolicitudRestablecimiento

        SolicitudRestablecimiento.atender(form.get_user(), SolicitudRestablecimiento.Via.INGRESO)
        return super().form_valid(form)


def invitacion(request, uidb64, token):
    """M11: la persona invitada crea su propia contraseña con el enlace de un
    solo uso. Un enlace vencido, ya usado o alterado se dice con claridad."""
    from django.contrib import messages
    from django.contrib.auth.password_validation import password_validators_help_texts, validate_password
    from django.core.exceptions import ValidationError
    from django.shortcuts import redirect, render

    from . import invitaciones
    from .auditoria_acciones import cerrar_sesiones_de

    usuario = invitaciones.usuario_de(uidb64, token)
    if usuario is None:
        return render(request, "ric/invitacion.html", {"invalido": True}, status=400)
    errores = []
    if request.method == "POST":
        clave, confirmar = request.POST.get("password", ""), request.POST.get("password_confirmar", "")
        if clave != confirmar:
            errores.append("La contraseña y su confirmación no coinciden.")
        else:
            try:
                validate_password(clave, user=usuario)
            except ValidationError as e:
                errores.extend(e.messages)
        if not errores:
            usuario.set_password(clave)
            usuario.save(update_fields=["password"])
            cerrar_sesiones_de(usuario, motivo="contraseña creada con invitación")
            from .models import SolicitudRestablecimiento

            SolicitudRestablecimiento.atender(usuario, SolicitudRestablecimiento.Via.CONTRASENA_CREADA)
            registrar_accion("modificar", usuario=usuario, objeto=usuario, detalle={"invitacion": "contraseña creada por la persona"})
            messages.success(request, "Su contraseña quedó creada. Ya puede ingresar.")
            return redirect("ric_login")
    return render(request, "ric/invitacion.html", {
        "usuario": usuario, "errores": errores, "ayudas": password_validators_help_texts(),
    })


SOLICITUDES_POR_HORA = 5  # por dirección IP: frena el abuso sin estorbar a quien de verdad lo necesita


def olvido_contrasena(request):
    """M11: «¿Olvidó su contraseña?» desde el ingreso. La respuesta es la
    misma exista o no la cuenta, para no revelar qué usuarios hay. Con correo
    en el servidor el enlace llega solo; sin correo, la solicitud queda
    pendiente para el administrador."""
    from datetime import timedelta

    from django.conf import settings
    from django.contrib.auth.models import User
    from django.db.models import Q
    from django.shortcuts import render
    from django.utils import timezone

    from . import invitaciones
    from .auditoria_acciones import _ip
    from .models import SolicitudRestablecimiento

    contexto = {"correo_configurado": bool(settings.EMAIL_HOST), "dias": invitaciones.dias_vigencia()}
    if request.method != "POST":
        return render(request, "ric/olvido.html", contexto)

    identidad = request.POST.get("identidad", "").strip()[:254]
    ip = _ip(request)
    recientes = SolicitudRestablecimiento.objects.filter(ip=ip, fecha__gte=timezone.now() - timedelta(hours=1)).count() if ip else 0
    usuario = None
    if identidad and recientes < SOLICITUDES_POR_HORA:
        usuario = User.objects.filter(Q(username__iexact=identidad) | Q(email__iexact=identidad), is_active=True).order_by("pk").first()
    if usuario is not None:
        pendiente = SolicitudRestablecimiento.objects.filter(usuario=usuario, atendida=False).exists()
        if settings.EMAIL_HOST:
            enviada, mensaje, _url = invitaciones.enviar(request, usuario, motivo="restablecer")
            SolicitudRestablecimiento.objects.create(usuario=usuario, ip=ip)
            if enviada:
                SolicitudRestablecimiento.atender(usuario, SolicitudRestablecimiento.Via.CORREO)
        elif not pendiente:
            SolicitudRestablecimiento.objects.create(usuario=usuario, ip=ip)
            mensaje = "pendiente del administrador (sin correo en el servidor)"
        else:
            mensaje = "ya había una solicitud pendiente"
        registrar_accion("solicitar_restablecimiento", usuario=usuario, objeto=usuario, detalle={"resultado": mensaje})
    else:
        # sin cuenta, o con demasiadas solicitudes desde esta dirección: se registra, la respuesta no cambia
        registrar_accion("solicitar_restablecimiento", exitoso=False,
                         detalle={"identidad": identidad, "motivo": "límite por hora" if recientes >= SOLICITUDES_POR_HORA else "sin cuenta activa"})
    return render(request, "ric/olvido.html", {**contexto, "enviada": True})
