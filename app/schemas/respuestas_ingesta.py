"""
Esquemas de respuesta del módulo de ingesta, solo para documentar la API.

No se usan como `response_model`: describen en OpenAPI lo que ya devuelven
las rutas, sin filtrar ni validar la salida. `extra="allow"` deja pasar
cualquier dato adicional.
"""

from pydantic import BaseModel, ConfigDict


class VistaPreviaDocumento(BaseModel):
    """Datos del visor de un documento: páginas que se pueden mostrar y texto extraído."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    formato: str | None
    puid: str | None
    admite: bool
    total: int
    texto: str | None
    origen_texto: str | None


class CargaReciente(BaseModel):
    """Un archivo cargado hace poco al fondo, con su destino."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    tamano_bytes: int | None
    formato: str | None
    estado: str
    cargado_en: str
    expediente: str | None
    descrito_en: str | None


class ResumenIngesta(BaseModel):
    """Estado general de la ingesta del fondo: documentos listos, con texto y en riesgo."""

    model_config = ConfigDict(extra="allow")

    documentos: int | None
    con_texto: int | None
    en_riesgo: int
    riesgo_integridad: int
    riesgo_obsolescencia: int


class EntidadNombrada(BaseModel):
    """Referencia breve a una entidad del vocabulario (remitente o dependencia)."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str | None


class ArchivoLote(BaseModel):
    """Un archivo que llegó en el lote de transferencia."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    estado: str
    huella: str | None


class PaqueteSip(BaseModel):
    """Paquete de envío BagIt del lote confirmado: huella, archivos y tamaño."""

    model_config = ConfigDict(extra="allow")

    huella: str
    archivos: int | None
    bytes: int | None


class LoteResumen(BaseModel):
    """Un lote de transferencia con su acta, sus archivos y su paquete de envío."""

    model_config = ConfigDict(extra="allow")

    id: str
    numero: str
    estado: str
    forma_ingreso: str
    forma_ingreso_nombre: str
    remitente: EntidadNombrada | None
    dependencia_origen: EntidadNombrada | None
    acta_numero: str | None
    acta_fecha_edtf: str | None
    acta_fecha_legible: str | None
    acta_instanciacion_id: str | None
    observaciones: str | None
    creado_en: str
    confirmado_en: str | None
    motivo_anulacion: str | None
    archivos: list[ArchivoLote]
    listos: int
    sip: PaqueteSip | None


class ArchivoAcuse(BaseModel):
    """Un archivo recibido, con su huella SHA-256 y su formato."""

    model_config = ConfigDict(extra="allow")

    nombre: str
    sha256: str | None
    formato: str | None


class AcuseRecibo(BaseModel):
    """Acuse de recibo del lote: qué se recibió, con qué huellas, cuándo y bajo qué acta."""

    model_config = ConfigDict(extra="allow")

    sistema: str
    fondo: str
    lote: str
    forma_ingreso: str
    acta: str | None
    fecha_acta: str | None
    dependencia_origen: str | None
    remitente: str | None
    recibido_en: str | None
    paquete_bagit_sha256: str | None
    total_archivos: int | None
    total_bytes: int | None
    archivos: list[ArchivoAcuse]


class LoteConfirmado(BaseModel):
    """Lote recién confirmado junto con su acuse de recibo."""

    model_config = ConfigDict(extra="allow")

    lote: LoteResumen
    acuse: AcuseRecibo

