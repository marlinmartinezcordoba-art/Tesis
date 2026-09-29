"""M11 (Administración y seguridad, RF-M11-01 / RF-M11-03): tres roles —
archivista (ingesta, analiza, modela relaciones y también puede aprobar),
revisor (revisa y aprueba, no ingesta) y consulta (solo catálogo,
exportación y panel). La cuenta superusuario administra usuarios y
proveedores de IA.

Se apoya en lo que Django ya trae: `is_staff` marca al archivista (es lo
que además le abre el panel técnico) y un grupo "revisor" marca al
revisor; quien no tiene ninguna de las dos es de consulta."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.shortcuts import redirect

SUPERUSUARIO = "superusuario"
ADMINISTRADOR = SUPERUSUARIO  # el cuarto rol de los documentos: administra usuarios, proveedores y parámetros
ARCHIVISTA = "archivista"
REVISOR = "revisor"
CONSULTA = "consulta"

ROLES_ASIGNABLES = (ARCHIVISTA, REVISOR, CONSULTA)
ETIQUETAS = {
    SUPERUSUARIO: "Administrador",
    ARCHIVISTA: "Archivista",
    REVISOR: "Revisor",
    CONSULTA: "Consulta",
}
_GRUPO_REVISOR = "revisor"


def rol_de(usuario):
    if not usuario or not usuario.is_authenticated:
        return None
    if usuario.is_superuser:
        return SUPERUSUARIO
    if usuario.is_staff:
        return ARCHIVISTA
    if usuario.groups.filter(name=_GRUPO_REVISOR).exists():
        return REVISOR
    return CONSULTA


def asignar_rol(usuario, rol):
    if rol not in ROLES_ASIGNABLES:
        raise ValueError(f"Rol desconocido: {rol!r}")
    from .auditoria_acciones import registrar_accion

    rol_anterior = rol_de(usuario)
    grupo, _ = Group.objects.get_or_create(name=_GRUPO_REVISOR)
    usuario.is_staff = rol == ARCHIVISTA
    usuario.save(update_fields=["is_staff"])
    if rol == REVISOR:
        usuario.groups.add(grupo)
    else:
        usuario.groups.remove(grupo)
    if rol_anterior != rol:
        registrar_accion("modificar", objeto=usuario, antes={"rol": rol_anterior}, despues={"rol": rol})


def puede(usuario, *roles):
    """El superusuario puede todo; los demás, solo si su rol está en `roles`."""
    rol = rol_de(usuario)
    return rol == SUPERUSUARIO or rol in roles


def contexto_roles(request):
    """Context processor: el rol y los permisos gruesos, para que el menú
    lateral muestre solo los módulos que la persona puede usar."""
    usuario = getattr(request, "user", None)
    rol = rol_de(usuario)
    return {
        "rol": rol,
        "rol_etiqueta": ETIQUETAS.get(rol, ""),
        "puede_ingestar": puede(usuario, ARCHIVISTA),
        "puede_revisar": puede(usuario, ARCHIVISTA, REVISOR),
        "puede_administrar": bool(usuario and usuario.is_superuser),
    }


def requiere_rol(*roles, mensaje=None):
    """RF-M11-03: cada acción del sistema restringida según el rol."""

    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(request, *args, **kwargs):
            if not puede(request.user, *roles):
                from .auditoria_acciones import registrar_accion

                registrar_accion(
                    "acceso_denegado", usuario=request.user, exitoso=False,
                    detalle={"ruta": request.path, "rol": rol_de(request.user), "requiere": list(roles) or ["administrador"]},
                )
                permitidos = " o ".join(ETIQUETAS[r].lower() for r in roles)
                messages.error(
                    request,
                    mensaje or f"Esta acción requiere el rol {permitidos}; tu cuenta es de {ETIQUETAS[rol_de(request.user)].lower()}.",
                )
                return redirect("panel")
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


def requiere_rol_api(*roles):
    """Igual que `requiere_rol`, para puntos que responden JSON a la propia
    pantalla: 401 sin sesión, 403 sin el rol (y queda en la auditoría)."""

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            from django.http import JsonResponse

            if not request.user.is_authenticated:
                return JsonResponse({"ok": False, "error": "La sesión expiró. Vuelva a iniciar sesión."}, status=401)
            if not puede(request.user, *roles):
                from .auditoria_acciones import registrar_accion

                registrar_accion("acceso_denegado", usuario=request.user, exitoso=False,
                                 detalle={"ruta": request.path, "rol": rol_de(request.user), "requiere": list(roles)})
                return JsonResponse({"ok": False, "error": "Esta acción requiere el rol " + " o ".join(ETIQUETAS[r].lower() for r in roles) + "."}, status=403)
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
