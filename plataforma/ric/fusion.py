"""F08 (validación archivista): fusionar dos entidades que resultaron ser
la misma cosa. `PropuestaRiC.validar()` ya deja "vincular a una entidad
existente" para EVITAR el duplicado al momento de aceptar una propuesta,
pero eso no ayuda si el duplicado ya se creó antes (dos propuestas con el
nombre escrito ligeramente distinto, por ejemplo) — para eso es esto.

No es F10 (Desambiguación, ver `ric.desambiguacion`): ahí la IA detecta
sola que dos menciones podrían ser la misma entidad y lo sugiere; aquí el
archivista ya sabe que lo son y pide fusionarlas a mano — F10 solo
sugiere, esto es lo que de verdad ejecuta la fusión.

Alcance deliberado: solo entidades sin ninguna referencia directa (no
genérica) de otro modelo — es decir, ni RecordSet (referenciado por
`padre`/`RecordSet` y por `Record.record_set`) ni RecordPart (por
`RecordPart.record_padre`). Fusionar esas arrastraría además decisiones de
jerarquía documental que no son parte de esto; se dejan fuera a propósito
en vez de intentar adivinar qué hacer con sus hijos.
"""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

_MODELOS_NO_FUSIONABLES = {"RecordSet", "RecordPart", "Record", "RecordResource", "Agent", "Instantiation"}

# Nombres de modelo (RIC_ID_A_MODELO_NOMBRE) que sí se pueden fusionar: los
# tipos "hoja" que de verdad se instancian (nunca la categoría abstracta
# Agent/Event/Rule sola) más Event y Rule, que sí son tablas propias con
# fila real (a diferencia de RecordResource/Agent, que nunca se registran
# solas en el admin). Lista explícita, no derivada por exclusión: así no
# se cuela por accidente un modelo con referencias directas fuera de
# RelacionRiC (como Instantiation, referenciada por Evidencia/PaginaTexto).
NOMBRES_MODELOS_FUSIONABLES = [
    "Person", "Group", "Family", "CorporateBody", "Position", "Mechanism",
    "Event", "Activity", "Rule", "Mandate", "Date", "Place",
]


def modelos_fusionables():
    """`NOMBRES_MODELOS_FUSIONABLES` como clases reales, para que el admin
    y las vistas no dupliquen el inventario a mano."""
    from django.apps import apps

    return [apps.get_model("ric", nombre) for nombre in NOMBRES_MODELOS_FUSIONABLES]


class ErrorDeFusion(Exception):
    """Error que se muestra a la persona archivista en lenguaje claro."""


def fusionar_entidades(duplicada, superviviente, usuario):
    """Mueve todas las relaciones (RelacionRiC) y propuestas pendientes
    (PropuestaRiC) que apuntaban a `duplicada` para que apunten a
    `superviviente`, guarda una fotografía de `duplicada` en VersionRiC
    (mismo mecanismo de F07, para no perder su historia) y la marca como
    eliminada (borrado lógico; `eliminar()` toma la fotografía al guardar).

    Devuelve {"relaciones_movidas": int, "propuestas_movidas": int}.
    """
    from .models import EventoRiC, PropuestaRiC, RelacionRiC, registrar_evento

    nombre_modelo = type(duplicada).__name__
    if nombre_modelo in _MODELOS_NO_FUSIONABLES:
        raise ErrorDeFusion(
            f"{nombre_modelo} no se puede fusionar aquí: tiene otras entidades que dependen "
            f"directamente de él (jerarquía documental), no solo relaciones RiC."
        )
    if type(duplicada) is not type(superviviente):
        raise ErrorDeFusion(
            f"Solo se puede fusionar entidades del mismo tipo "
            f"({nombre_modelo} y {type(superviviente).__name__} no lo son)."
        )
    if duplicada.pk is None or superviviente.pk is None:
        raise ErrorDeFusion("Ambas entidades deben existir ya guardadas.")
    if duplicada.pk == superviviente.pk:
        raise ErrorDeFusion("No se puede fusionar una entidad consigo misma.")

    content_type = ContentType.objects.get_for_model(type(duplicada))
    relaciones_movidas = 0

    with transaction.atomic():
        for rel in RelacionRiC.objects.filter(origen_content_type=content_type, origen_object_id=duplicada.pk):
            rel.origen = superviviente
            rel.save()
            relaciones_movidas += 1
        for rel in RelacionRiC.objects.filter(destino_content_type=content_type, destino_object_id=duplicada.pk):
            rel.destino = superviviente
            rel.save()
            relaciones_movidas += 1

        propuestas_movidas = PropuestaRiC.objects.filter(
            origen_content_type=content_type, origen_object_id=duplicada.pk
        ).update(origen_object_id=superviviente.pk)

        descripcion_duplicada = str(duplicada)
        # Regla del proyecto: nada se elimina de forma irreversible. La
        # duplicada queda marcada como eliminada (borrado lógico) con el
        # motivo de la fusión y puede restaurarse desde Administración.
        duplicada.eliminar(usuario, motivo=f"Fusionada en «{superviviente}» (id {superviviente.pk})")

        registrar_evento(
            None, EventoRiC.Tipo.FUSION, agente=usuario,
            detalle={
                "tipo_entidad": content_type.model,
                "duplicada": descripcion_duplicada,
                "superviviente_id": superviviente.pk,
                "superviviente": str(superviviente),
                "relaciones_movidas": relaciones_movidas,
                "propuestas_movidas": propuestas_movidas,
            },
        )

    return {"relaciones_movidas": relaciones_movidas, "propuestas_movidas": propuestas_movidas}


def fusionar_formas(duplicada, superviviente, usuario):
    """La forma documental no es una entidad RiC con RelacionRiC: lo que
    la referencia son los documentos (Record.forma_documental) y las
    series de la TRD (Activity.formas_documentales). Ambas cosas pasan a la
    superviviente y la duplicada se retira; queda el evento de fusión
    (CC-08) con su nombre para poder reconstruir qué se unió."""
    from .models import EventoRiC, FormaDocumental, registrar_evento

    if not isinstance(duplicada, FormaDocumental) or not isinstance(superviviente, FormaDocumental):
        raise ErrorDeFusion("Solo se pueden fusionar dos formas documentales entre sí.")
    if duplicada.pk == superviviente.pk:
        raise ErrorDeFusion("No se puede fusionar una forma documental consigo misma.")

    with transaction.atomic():
        documentos_movidos = duplicada.records.update(forma_documental=superviviente)
        series_movidas = 0
        for actividad in duplicada.actividades.all():
            actividad.formas_documentales.add(superviviente)
            series_movidas += 1
        if not superviviente.definicion and duplicada.definicion:
            superviviente.definicion = duplicada.definicion
        if not superviviente.serie_trd and duplicada.serie_trd:
            superviviente.serie_trd = duplicada.serie_trd
        superviviente.modificado_por = usuario
        superviviente.save()
        nombre_duplicada = duplicada.nombre
        duplicada.eliminar(usuario, motivo=f"Fusionada en «{superviviente.nombre}» (id {superviviente.pk})")
        registrar_evento(
            None, EventoRiC.Tipo.FUSION, agente=usuario,
            detalle={
                "tipo_entidad": "formadocumental", "duplicada": nombre_duplicada,
                "superviviente_id": superviviente.pk, "superviviente": superviviente.nombre,
                "documentos_movidos": documentos_movidos, "series_movidas": series_movidas,
            },
        )
    return {"documentos_movidos": documentos_movidos, "series_movidas": series_movidas}
