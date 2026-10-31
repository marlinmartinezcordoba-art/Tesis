"""Todos los modelos, importados aquí para que Alembic los conozca."""

from app.db.base import Base  # noqa: F401
from app.models.alerta import Alerta  # noqa: F401
from app.models.auditoria import RegistroAuditoria  # noqa: F401
from app.models.dato_personal import DatoPersonalDetectado  # noqa: F401
from app.models.digitalizacion import Digitalizacion, VerificacionDigitalizacion  # noqa: F401
from app.models.evidencia_ia import PaginaTexto, PropuestaIA  # noqa: F401
from app.models.evaluacion import Anotacion, Calificacion, Evaluacion, EvaluacionDocumento, Exposicion  # noqa: F401
from app.models.grafo_rdf import GrafoRdf  # noqa: F401
from app.models.hallazgo import EtiquetaVersionPrompt, HallazgoConformidad  # noqa: F401
from app.models.descripcion import (  # noqa: F401
    Actividad, EntidadVocabulario, Fecha, Relacion, SugerenciaFusion, TrabajoDescripcion, TrabajoInstanciacion,
)
from app.models.instanciacion import Instanciacion  # noqa: F401
from app.models.instrumento_aprobado import InstrumentoAprobado  # noqa: F401
from app.models.lote import LoteIngesta  # noqa: F401
from app.models.parametro import Parametro  # noqa: F401
from app.models.preservacion import (  # noqa: F401
    ComprobacionTecnica, DeclaracionDerechos, Migracion, PaqueteRecuperacion, RespaldoBaseDatos, Restauracion, SegundaCopia,
    VerificacionIntegridad,
)
from app.models.recurso_documental import RecursoDocumental  # noqa: F401
from app.models.rol import Rol  # noqa: F401
from app.models.sesion import Sesion  # noqa: F401
from app.models.tesauro import ConceptoTesauro, EtiquetaConcepto, Tesauro  # noqa: F401
from app.models.token_acceso import TokenUnUso  # noqa: F401
from app.models.trd import CargaInstrumento, DependenciaTrd, FilaTrd, TerminoBanco, VersionTrd  # noqa: F401
from app.models.usuario import Usuario  # noqa: F401
from app.models.version_descripcion import VersionDescripcion  # noqa: F401

# El grafo RiC-O persistente escucha los cambios de estos modelos (marca su fondo).
from app.servicios import grafo_rdf  # noqa: E402,F401
