"""F04 (Segmentación): detecta cuando un único archivo ingerido contiene,
además de su documento principal, otro documento distinto — por ejemplo
varios oficios o actas escaneados juntos en un solo PDF — y propone dónde
empieza cada uno para que la persona archivista lo valide.

La señal es la reaparición de un componente tipo "titulo" (F03): cada
título después del primero marca, con alta probabilidad, el comienzo de
un documento nuevo dentro del mismo archivo. No es un modelo de IA, es
una consecuencia directa de la detección de estructura — por eso hereda
su misma honestidad: si el archivo no repite ningún título reconocido, no
se propone ninguna segmentación (no se inventa una división que no hay).

Aceptar una propuesta (`PropuestaSegmentacion.validar`) no corta el
archivo físico: crea un Record y una Instantiation nuevos que apuntan al
mismo objeto digital (mismo hash: es un recorte lógico, no una copia
distinta), con solo las páginas de ese rango, y los relaciona con el
Record contenedor mediante RiC-R002 'has or had part'.
"""

from django.db.models import Max


def detectar_segmentos(instanciacion):
    """Lista de segmentos propuestos (dicts listos para
    `PropuestaSegmentacion`), a partir de los títulos (F03) ya detectados
    en `instanciacion`. Vacía si hay menos de dos títulos: un solo título
    es el documento completo, no una segmentación."""
    titulos = list(instanciacion.componentes.filter(tipo="titulo").order_by("pagina", "orden"))
    if len(titulos) < 2:
        return []

    ultima_pagina = (
        instanciacion.paginas.aggregate(m=Max("numero"))["m"] or titulos[-1].pagina
    )
    propuestas = []
    for i in range(1, len(titulos)):
        titulo = titulos[i]
        siguiente = titulos[i + 1] if i + 1 < len(titulos) else None
        pagina_fin = (siguiente.pagina - 1) if siguiente else ultima_pagina
        propuestas.append({
            "pagina_inicio": titulo.pagina, "pagina_fin": pagina_fin,
            "titulo_detectado": titulo.texto, "confianza": titulo.confianza,
            "regla": "titulo_repetido",
        })
    return propuestas


def guardar_propuestas(instanciacion, propuestas):
    """Crea las propuestas nuevas que no existan ya (mismo rango de
    páginas) — a diferencia de F02/F03, esto SÍ guarda decisiones humanas
    (`estado`), así que reprocesar nunca borra ni reemplaza una propuesta
    existente, solo agrega las que falten."""
    from .models import PropuestaSegmentacion

    existentes = set(
        instanciacion.propuestas_segmentacion.values_list("pagina_inicio", "pagina_fin")
    )
    nuevas = [
        PropuestaSegmentacion(instanciacion=instanciacion, **p)
        for p in propuestas
        if (p["pagina_inicio"], p["pagina_fin"]) not in existentes
    ]
    PropuestaSegmentacion.objects.bulk_create(nuevas)
    return nuevas


def detectar_y_proponer_segmentos(instanciacion):
    return guardar_propuestas(instanciacion, detectar_segmentos(instanciacion))


def materializar_segmento(propuesta):
    """Crea el Record + Instantiation del segmento aceptado: copia sus
    páginas de texto (renumeradas desde 1, con sus coordenadas de OCR si
    las tenían) y vuelve a detectar su estructura (F03). Registra la
    relación RiC-R002 'has or had part' entre el Record contenedor
    original y el nuevo Record segmentado."""
    from .estructura import detectar_y_guardar_estructura
    from .models import Instantiation, PaginaTexto, Record, RelacionRiC

    instanciacion = propuesta.instanciacion
    contenedor = instanciacion.record_resource

    nombre = propuesta.titulo_detectado or f"Segmento p.{propuesta.pagina_inicio}-{propuesta.pagina_fin}"
    nuevo_record = Record.objects.create(nombre=nombre)

    nueva_instanciacion = Instantiation(
        nombre=f"{instanciacion.nombre} (segmento: {nombre})",
        record_resource=nuevo_record,
        archivo=instanciacion.archivo.name,  # mismo objeto digital: mismo hash al guardar
    )
    nueva_instanciacion.save()

    paginas_originales = instanciacion.paginas.filter(
        numero__gte=propuesta.pagina_inicio, numero__lte=propuesta.pagina_fin
    ).order_by("numero")
    PaginaTexto.objects.bulk_create([
        PaginaTexto(
            instanciacion=nueva_instanciacion, numero=i,
            texto=p.texto, uso_ocr=p.uso_ocr, confianza_ocr=p.confianza_ocr, cajas_ocr=p.cajas_ocr,
        )
        for i, p in enumerate(paginas_originales, start=1)
    ])

    detectar_y_guardar_estructura(nueva_instanciacion)

    relacion = RelacionRiC(
        relacion_id="R002", origen=contenedor, destino=nuevo_record,
        estado=RelacionRiC.Estado.ACEPTADA,
        descripcion_relacion=(
            f"F04: segmentación de {instanciacion.nombre} "
            f"(p.{propuesta.pagina_inicio}-{propuesta.pagina_fin})."
        ),
    )
    relacion.save()

    return nuevo_record, nueva_instanciacion
