"""
Puesta en marcha: dejar RICORA en blanco para empezar a usarlo de verdad.

Borra todo lo cargado y lo descrito (documentos, descripciones, autoridades,
relaciones, CCD y TRD, evaluaciones, grafos RiC-O) y conserva lo que hace
funcionar el sistema: usuarios, roles, parámetros, datos de la institución,
respaldos y el registro de auditoría.

Es la única excepción a «nada se borra, se anula», y por eso:

- Solo la ejecuta un administrador, con su contraseña y escribiendo la frase
  de confirmación.
- Antes de borrar se hace un respaldo completo de la base. Si el respaldo
  falla, no se borra nada. El contenido sigue recuperable desde ese respaldo.
- Los archivos no se eliminan: se apartan dentro del almacenamiento, en
  «_retirado/<fecha>», donde quien opera el servidor decide qué hacer con ellos.
- El registro de auditoría no se toca (la base de datos lo impide) y recibe
  un evento «sistema_reiniciado» con lo que se borró y el respaldo que lo guarda.

Las tablas están clasificadas una por una (BORRAR, CONSERVAR, TESAUROS). Una
tabla nueva que no esté en ninguna lista hace fallar la prueba
test_reinicio::test_toda_tabla_esta_clasificada: nunca se borra por omisión.
"""

import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.seguridad import verificar_contrasena
from app.db.base import ahora
from app.models.grafo_rdf import GrafoRdf
from app.models.parametro import Parametro
from app.models.usuario import Usuario
from app.servicios.auditoria import registrar

log = logging.getLogger("ricora.reinicio")

FRASE = "BORRAR TODO EL CONTENIDO"

# Lo que hace funcionar el sistema: se conserva siempre.
CONSERVAR = ("alembic_version", "usuarios", "roles", "sesiones", "tokens_un_uso", "parametros", "registro_auditoria",
             "etiquetas_version_prompt", "respaldos_bd", "paquetes_recuperacion")
# Vocabularios controlados cargados por la institución: se conservan salvo que se pida borrarlos.
TESAUROS = ("tesauros", "conceptos_tesauro", "etiquetas_concepto")
# Todo lo cargado y lo descrito.
BORRAR = ("actividades", "alertas", "cargas_instrumento", "comprobaciones_tecnicas", "datos_personales_detectados",
          "declaraciones_derechos", "digitalizaciones", "entidades_vocabulario", "evaluacion_anotaciones",
          "evaluacion_calificaciones", "evaluacion_documentos", "evaluacion_errores", "evaluacion_exposiciones",
          "evaluacion_participantes", "evaluaciones", "fechas", "grafos_rdf", "hallazgos_conformidad", "hitos",
          "identificadores_entidad", "instanciaciones", "instrumentos_aprobados", "lotes_ingesta", "migraciones",
          "nombres_entidad", "paginas_texto", "propuestas_ia", "recursos_documentales", "relaciones", "restauraciones",
          "segundas_copias", "sugerencias_fusion", "trabajo_instanciaciones", "trabajos_descripcion", "trd_banco",
          "trd_dependencias", "trd_filas", "trd_versiones", "verificaciones_digitalizacion",
          "verificaciones_integridad", "versiones_descripcion")
# Parámetros que guardan identificadores o fechas del contenido borrado.
PARAMETROS_DE_CONTENIDO = ("mecanismos_motor", "fusion_ultima_deteccion", "preservacion_ultima_verificacion")

# Lo que se muestra antes de confirmar: qué se va a borrar, en palabras de archivo.
RESUMEN = (
    ("Fondos y unidades de descripción", "SELECT count(*) FROM recursos_documentales"),
    ("Archivos cargados", "SELECT count(*) FROM instanciaciones"),
    ("Autoridades y términos", "SELECT count(*) FROM entidades_vocabulario"),
    ("Relaciones", "SELECT count(*) FROM relaciones"),
    ("Versiones de la TRD", "SELECT count(*) FROM trd_versiones"),
    ("Evaluaciones", "SELECT count(*) FROM evaluaciones"),
    ("Propuestas del motor", "SELECT count(*) FROM propuestas_ia"),
)


class ReinicioRechazado(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


def _existentes(db: Session) -> set[str]:
    return set(db.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).all())


def sin_clasificar(db: Session) -> set[str]:
    return _existentes(db) - set(CONSERVAR) - set(TESAUROS) - set(BORRAR)


def inventario(db: Session) -> dict:
    """Lo que hay hoy y lo que se borraría. No cambia nada."""
    return {
        "frase": FRASE,
        "se_borra": [{"que": que, "cantidad": int(db.scalar(text(sql)) or 0)} for que, sql in RESUMEN],
        "tesauros": int(db.scalar(text("SELECT count(*) FROM conceptos_tesauro")) or 0),
        "se_conserva": ["Usuarios y roles", "Parámetros y datos de la institución", "Respaldos de la base de datos",
                        "Registro de auditoría (no se puede borrar)"],
        "sin_clasificar": sorted(sin_clasificar(db)),
    }


def _apartar_archivos(marca: str) -> dict:
    """Mueve el contenido del almacenamiento a «_retirado/<marca>»: nada se elimina del disco."""
    raiz: Path = settings.directorio_almacenamiento
    if not raiz.exists():
        return {"movidos": 0, "destino": None}
    destino = raiz / "_retirado" / marca
    respaldo = settings.directorio_respaldo.resolve()
    movidos = 0
    for hijo in list(raiz.iterdir()):
        if hijo.name == "_retirado" or hijo.resolve() == respaldo or respaldo.is_relative_to(hijo.resolve()):
            continue
        destino.mkdir(parents=True, exist_ok=True)
        shutil.move(str(hijo), str(destino / hijo.name))
        movidos += 1
    return {"movidos": movidos, "destino": str(destino) if movidos else None}


def _vaciar_grafos(nombres: list[str]) -> str | None:
    """Vacía en el almacén RDF los grafos de los fondos borrados. Si falla, no quedan visibles:
    la consulta del acervo solo usa los grafos que la base registra."""
    if not nombres:
        return None
    from app.servicios import grafo_rdf

    try:
        grafo_rdf.almacen().reemplazar_varios({n: b"" for n in nombres})
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudieron vaciar los grafos RiC-O: %s", exc)
        return str(exc)[:300]


def reiniciar(db: Session, usuario: Usuario, contrasena: str, frase: str, incluir_tesauros: bool = False,
              respaldar=None) -> dict:
    if not verificar_contrasena(contrasena or "", usuario.contrasena_hash):
        raise ReinicioRechazado("La contraseña no es correcta.", 403)
    if " ".join((frase or "").split()).upper() != FRASE:
        raise ReinicioRechazado(f"Escriba exactamente «{FRASE}» para confirmar.")
    faltan = sin_clasificar(db)
    if faltan:  # una tabla nueva que nadie clasificó: no se borra a ciegas
        raise ReinicioRechazado("Hay tablas sin clasificar: " + ", ".join(sorted(faltan)) + ". No se borró nada.", 500)

    antes = inventario(db)["se_borra"]
    # 1. Respaldo completo antes de borrar. Sin respaldo correcto, no se borra.
    if respaldar is None:
        from app.servicios import respaldo as servicio_respaldo

        respaldar = servicio_respaldo.respaldar
    r = respaldar(db, origen="reinicio", usuario_id=usuario.id)
    db.commit()
    if r.estado != "correcto":
        raise ReinicioRechazado(f"El respaldo previo falló ({r.error or 'sin detalle'}). No se borró nada.", 500)

    # 2. Vaciar las tablas en una sola orden, sin CASCADE: si alguna tabla que se conserva
    #    dependiera de una que se borra, PostgreSQL rechaza la orden y no se borra nada.
    from app.servicios.grafo_rdf import nombre as nombre_grafo

    nombres_grafos = [nombre_grafo(f, a) for f, a in db.execute(select(GrafoRdf.fondo_id, GrafoRdf.alcance)).all()]
    tablas = list(BORRAR) + (list(TESAUROS) if incluir_tesauros else [])
    db.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tablas) + " RESTART IDENTITY"))
    db.query(Parametro).filter(Parametro.clave.in_(PARAMETROS_DE_CONTENIDO)).delete(synchronize_session=False)
    marca = f"{ahora():%Y%m%dT%H%M%S}-{str(uuid.uuid4())[:8]}"
    registrar(db, modulo="sistema", accion="sistema_reiniciado", usuario_id=usuario.id, entidad_tipo="sistema",
              entidad_id=marca, detalle="Puesta en marcha: se borró todo lo cargado y lo descrito",
              nuevo={"borrado": antes, "tesauros_borrados": incluir_tesauros, "respaldo_id": str(r.id),
                     "respaldo_archivo": Path(r.archivo).name if r.archivo else None, "respaldo_huella": r.huella})
    db.commit()

    # 3. Después de confirmar en la base: grafos y archivos (no se pueden deshacer con la transacción).
    error_grafos = _vaciar_grafos(nombres_grafos)
    archivos = _apartar_archivos(marca)
    return {"borrado": antes, "respaldo": {"id": str(r.id), "archivo": Path(r.archivo).name if r.archivo else None,
                                           "huella": r.huella},
            "archivos_apartados": archivos, "aviso_grafos": error_grafos, "tesauros_borrados": incluir_tesauros}
