"""Quién puede ver qué documento y qué archivo (RF-M8-04, Ley 1712 de 2014).
Una sola regla para el catálogo, el visor y la entrega del archivo original:
archivista y revisor ven todo; el rol consulta solo documentos publicados y
solo instanciaciones de acceso abierto."""

from . import roles
from .models import Instantiation, Record


def solo_publicados(usuario):
    return not roles.puede(usuario, roles.ARCHIVISTA, roles.REVISOR)


def documentos_visibles(usuario):
    qs = Record.objects.all()
    if solo_publicados(usuario):
        qs = qs.filter(publicado=True).exclude(
            instanciaciones__condicion_acceso__in=(
                Instantiation.CondicionAcceso.RESTRINGIDO, Instantiation.CondicionAcceso.RESERVADO,
            )
        )
    return qs.distinct()


def puede_ver_instanciacion(usuario, instanciacion):
    if not solo_publicados(usuario):
        return True
    if instanciacion.condicion_acceso != Instantiation.CondicionAcceso.ABIERTO:
        return False
    return documentos_visibles(usuario).filter(pk=instanciacion.record_resource_id).exists()
