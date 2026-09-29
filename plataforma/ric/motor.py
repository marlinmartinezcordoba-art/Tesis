"""M3 (Motor de análisis RiC): la entrega de un documento al proveedor de
IA activo. Es el único lugar desde donde las pantallas piden propuestas —
al terminar el preprocesamiento (M2), al aceptar una página de calidad
baja, o cuando la persona pide "generar propuesta" / "nueva propuesta"
tras un rechazo en la revisión (M6)."""

from . import proveedores


def enviar_al_motor(record, usuario, proveedor=None):
    """Devuelve un dict con lo que pasó, para mostrarlo en pantalla:
    {"propuestas": n, "rechazadas_por_reglas": n} si se analizó,
    {"sin_proveedor": True} si no hay proveedor de IA activo (M11), o
    {"error": mensaje} si el servicio falló."""
    proveedor = proveedor or proveedores.proveedor_activo()
    if proveedor is None:
        return {"propuestas": 0, "sin_proveedor": True}
    try:
        creadas = proveedores.generar_propuestas(record, proveedor)
    except proveedores.ErrorProveedorIA as e:
        return {"propuestas": 0, "error": str(e)}
    rechazadas = sum(1 for p in creadas if p.estado == p.Estado.RECHAZADA)
    return {"propuestas": len(creadas) - rechazadas, "rechazadas_por_reglas": rechazadas, "proveedor": proveedor.nombre}
