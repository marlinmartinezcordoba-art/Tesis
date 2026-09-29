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
            registrar_accion("modificar", usuario=usuario, objeto=usuario, detalle={"invitacion": "contraseña creada por la persona"})
            messages.success(request, "Su contraseña quedó creada. Ya puede ingresar.")
            return redirect("ric_login")
    return render(request, "ric/invitacion.html", {
        "usuario": usuario, "errores": errores, "ayudas": password_validators_help_texts(),
    })
