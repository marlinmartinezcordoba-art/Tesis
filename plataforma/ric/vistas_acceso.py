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
