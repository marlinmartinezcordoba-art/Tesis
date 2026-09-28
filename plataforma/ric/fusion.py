"""F08 (validación archivista): fusionar dos entidades que resultaron ser
la misma cosa. `PropuestaRiC.validar()` ya deja "vincular a una entidad
existente" para EVITAR el duplicado al momento de aceptar una propuesta,
pero eso no ayuda si el duplicado ya se creó antes (dos propuestas con el
nombre escrito ligeramente distinto, por ejemplo) — para eso es esto.

No es F10 (Desambiguación, sin construir): ahí la IA detectaría sola que
dos menciones podrían ser la misma entidad y lo sugeriría; aquí el
archivista ya sabe que lo son y pide fusionarlas a mano. F10 seguirá
haciendo falta para que RICORA lo sugiera sola.

Alcance deliberado: solo entidades sin ninguna referencia directa (no
genérica) de otro modelo — es decir, ni RecordSet (referenciado por
`padre`/`RecordSet` y por `Record.record_set`) ni RecordPart (por
`RecordPart.record_padre`). Fusionar esas arrastraría además decisiones de
jerarquía documental que no son parte de esto; se dejan fuera a propósito
en vez de intentar adivinar qué hacer con sus hijos.
"""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

_MODELOS_NO_FUSIONABLES = {"RecordSet", "RecordPart", "Record", "RecordResource"}


class ErrorDeFusion(Exception):
    """Error que se muestra a la persona archivista en lenguaje claro."""


def fusionar_entidades(duplicada, superviviente, usuario):
    """Mueve todas las relaciones (RelacionRiC) y propuestas pendientes
    (PropuestaRiC) que apuntaban a `duplicada` para que apunten a
    `superviviente`, guarda una fotografía de `duplicada` en VersionRiC
    (mismo mecanismo de F07, para no perder su historia) y la borra.

    Devuelve {"relaciones_movidas": int, "propuestas_movidas": int}.
    """
    from .models import EventoRiC, PropuestaRiC, RelacionRiC, _registrar_version, registrar_evento

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
        _registrar_version(duplicada)
        duplicada.delete()

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
