// A dónde lleva cada alerta del panel (hallazgo ING-07). Las dos alertas de
// la ingesta que no bloquean (formato no identificado y OCR con confianza
// baja) llegan cuando el documento ya está listo para describir: las dos
// llevan al espacio de descripción de ese documento.

export interface AlertaEnlazable {
  tipo: string;
  entidad_tipo: string;
  entidad_id: string;
}

const A_DESCRIPCION = new Set(["formato_no_identificado", "ocr_baja_confianza"]);

export function enlaceDeAlerta(a: AlertaEnlazable): { ruta: string; texto: string } | null {
  if (A_DESCRIPCION.has(a.tipo) && a.entidad_tipo === "instanciacion")
    return { ruta: `/descripcion?documento=${encodeURIComponent(a.entidad_id)}`, texto: "Ir a describir" };
  return null;
}

export const TIPO_ALERTA: Record<string, string> = {
  formato_no_identificado: "Formato no identificado",
  ocr_baja_confianza: "OCR con confianza baja",
  inventario_campos_pendientes: "Campos pendientes del inventario",
  integridad_alterada: "Alerta de integridad",
  riesgo_obsolescencia: "Riesgo de obsolescencia",
  segunda_copia_alterada: "Segunda copia alterada",
  respaldo_fallido: "Respaldo fallido",
  respaldo_atrasado: "Respaldo atrasado",
  respaldo_sin_copia_externa: "Respaldo sin copia fuera del servidor",
  verificacion_atrasada: "Verificación de integridad atrasada",
  huella_referencia_alterada: "Huella de referencia alterada",
  exportacion_no_conforme: "Exportación RiC-O no conforme",
  mecanismo_sin_version: "Mecanismo sin versión",
};
