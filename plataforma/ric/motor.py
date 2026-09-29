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
    elegido = proveedor is not None
    proveedor = proveedor or proveedores.proveedor_activo()
    if proveedor is None:
        proveedor = proveedores.proveedor_respaldo()
        if proveedor is None:
            return {"propuestas": 0, "sin_proveedor": True}
    aviso = ""
    try:
        creadas = proveedores.generar_propuestas(record, proveedor)
    except proveedores.ErrorProveedorIA as e:
        # Si el principal falla (saturado, sin conexión, límite de uso) y hay
        # un respaldo configurado (p. ej. la IA local), se usa ese — y se dice.
        respaldo = None if elegido else proveedores.proveedor_respaldo(excepto=proveedor)
        if respaldo is None:
            return {"propuestas": 0, "error": str(e)}
        aviso = f"{proveedor.nombre} no respondió ({e}); se usó el respaldo {respaldo.nombre} {respaldo.version}."
        proveedor = respaldo
        try:
            creadas = proveedores.generar_propuestas(record, proveedor)
        except proveedores.ErrorProveedorIA as e2:
            return {"propuestas": 0, "error": f"{aviso.split(';')[0]}; el respaldo tampoco: {e2}"}
    rechazadas = sum(1 for p in creadas if p.estado == p.Estado.RECHAZADA)
    resultado = {"propuestas": len(creadas) - rechazadas, "rechazadas_por_reglas": rechazadas, "proveedor": proveedor.nombre}
    if aviso:
        resultado["aviso_respaldo"] = aviso
    return resultado
