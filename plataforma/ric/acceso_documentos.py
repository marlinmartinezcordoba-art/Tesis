"""Quién puede ver qué (RF-M8-04, Ley 1712 de 2014). Una sola regla para el
catálogo, el visor, el grafo, el RDF, SPARQL y la entrega del archivo
original: archivista y revisor ven todo; el rol consulta ve

- documentos publicados cuyos archivos son todos de acceso abierto;
- las entidades (personas, instituciones, fechas, lugares...) que aparecen
  en al menos uno de esos documentos, más las de los instrumentos
  archivísticos (organigrama, TRD), que son información pública;
- fondos, secciones y series; y los expedientes solo si contienen al menos
  un documento visible (su nombre puede llevar datos de una persona).

Nada que solo aparezca en un documento reservado, restringido o sin
publicar se deja ver, ni siquiera como sugerencia de búsqueda."""

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


FUENTE_INSTRUMENTO = "Instrumento archivístico precargado (M5)"


class Visibilidad:
    """Lo que un usuario de consulta puede ver, calculado una vez por
    petición. Para archivista y revisor, `todo` es True y no filtra nada."""

    def __init__(self, usuario):
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import Q

        from .models import RecordSet, RelacionRiC

        self.todo = not solo_publicados(usuario)
        self.usuario = usuario
        if self.todo:
            return
        self.records = set(documentos_visibles(usuario).values_list("pk", flat=True))
        ct_record = ContentType.objects.get_for_model(Record)
        self.ct_record, self.ct_conjunto = ct_record.pk, ContentType.objects.get_for_model(RecordSet).pk
        self.entidades = set()  # {(content_type_id, pk)}
        validadas = RelacionRiC.objects.filter(estado__in=("aceptada", "modificada"))
        for o_ct, o_id, d_ct, d_id in validadas.filter(
            Q(origen_content_type=ct_record, origen_object_id__in=self.records)
            | Q(destino_content_type=ct_record, destino_object_id__in=self.records)
        ).values_list("origen_content_type", "origen_object_id", "destino_content_type", "destino_object_id"):
            self.entidades.update({(o_ct, o_id), (d_ct, d_id)})
        for o_ct, o_id, d_ct, d_id in validadas.filter(fuente_relacion=FUENTE_INSTRUMENTO).values_list(
            "origen_content_type", "origen_object_id", "destino_content_type", "destino_object_id"
        ):
            self.entidades.update({(o_ct, o_id), (d_ct, d_id)})
        self.expedientes = set(
            RecordSet.objects.filter(tipo_conjunto=RecordSet.Tipo.EXPEDIENTE, records__pk__in=self.records).values_list("pk", flat=True)
        )

    def puede(self, entidad):
        if self.todo or entidad is None:
            return True
        from django.contrib.contenttypes.models import ContentType

        from .models import RecordSet

        if isinstance(entidad, Instantiation):
            return puede_ver_instanciacion(self.usuario, entidad)
        if isinstance(entidad, Record):
            return entidad.pk in self.records
        if isinstance(entidad, RecordSet):
            return entidad.tipo_conjunto != RecordSet.Tipo.EXPEDIENTE or entidad.pk in self.expedientes
        ct = ContentType.objects.get_for_model(type(entidad)).pk
        return (ct, entidad.pk) in self.entidades

    def relacion(self, relacion):
        """Una relación se ve solo si se ven sus dos extremos."""
        return self.todo or (self.puede(relacion.origen) and self.puede(relacion.destino))

    def filtrar(self, entidades):
        return [e for e in entidades if self.puede(e)]
