export type NivelRiesgo = "bajo" | "medio" | "alto";

export interface InstBreve {
  id: string;
  nombre: string;
  formato: string | null;
  puid: string | null;
}

export interface Miga {
  id: string;
  nivel: string;
  titulo: string;
}

export interface Panel {
  resumen: { total: number; alerta_integridad: number; riesgo_obsolescencia: number; buen_estado: number };
  atencion: {
    alerta_id: string;
    tipo: "integridad_alterada" | "riesgo_obsolescencia" | "formato_no_identificado";
    severidad: "alta" | "media" | "baja";
    mensaje: string;
    instanciacion: InstBreve;
    contexto: Miga[];
  }[];
  frecuencia_dias: number;
  ultima_verificacion: string | null;
}

export interface Riesgo {
  nivel: NivelRiesgo;
  razon: string;
  recomendacion: string | null;
  destino_sugerido: string | null;
  mitigado_por: { id: string; nombre: string } | null;
}

export interface MigracionHist {
  id: string;
  destino: string;
  destino_nombre: string;
  modo: "automatica" | "manual";
  estado: "en_curso" | "completada" | "fallida" | "esperando_archivo";
  herramienta: string | null;
  mensaje: string | null;
  aprobada_por: string | null;
  aprobada_en: string;
  terminada_en: string | null;
  resultado: InstBreve | null;
}

export interface Detalle {
  id: string;
  nombre: string;
  fondo_id: string;
  formato: { puid: string | null; nombre: string | null; version: string | null; mime: string | null; identificado: boolean;
    herramienta: string | null; base: string | null };
  tamano_bytes: number;
  paginas: number | null;
  huella: string | null;
  algoritmo_huella: string;
  cargado_en: string;
  estado_integridad: "sin_verificar" | "integra" | "alterada" | "ausente";
  ultima_verificacion_en: string | null;
  riesgo: Riesgo;
  contexto: Miga[];
  derivada_de: InstBreve | null;
  migrada_desde: { herramienta: string | null; modo: string } | null;
  verificaciones: { fecha: string; resultado: "integra" | "alterada" | "ausente"; origen: "periodica" | "manual"; por: string | null }[];
  migraciones: MigracionHist[];
  destinos: { clave: string; nombre: string; automatica: boolean; conversor: string | null }[];
}

export interface Configuracion {
  frecuencia_dias: number;
  formatos: { id: string; origen: string; origen_mime: string[]; destino: string; conversor: string; activo: boolean }[];
  conversores: { clave: string; nombre: string; destino: string }[];
  destinos: { clave: string; nombre: string }[];
  herramientas: { ghostscript: boolean };
}

export const INTEGRIDAD: Record<Detalle["estado_integridad"], { texto: string; clase: string }> = {
  sin_verificar: { texto: "Sin verificar todavía", clase: "proceso" },
  integra: { texto: "Íntegra", clase: "bien" },
  alterada: { texto: "Alterada", clase: "error" },
  ausente: { texto: "Archivo ausente", clase: "error" },
};

export const RIESGO: Record<NivelRiesgo, { texto: string; clase: string }> = {
  bajo: { texto: "Riesgo bajo", clase: "bien" },
  medio: { texto: "Riesgo medio", clase: "alerta" },
  alto: { texto: "Riesgo alto", clase: "error" },
};

export const TIPO_ATENCION: Record<Panel["atencion"][number]["tipo"], { texto: string; clase: string }> = {
  integridad_alterada: { texto: "Alerta de integridad", clase: "error" },
  riesgo_obsolescencia: { texto: "Riesgo de obsolescencia", clase: "alerta" },
  formato_no_identificado: { texto: "Formato no identificado", clase: "alerta" },
};

export const FRECUENCIAS = [
  { dias: 7, nombre: "Semanal" },
  { dias: 15, nombre: "Quincenal" },
  { dias: 30, nombre: "Mensual (recomendado para un fondo histórico)" },
  { dias: 90, nombre: "Trimestral" },
  { dias: 180, nombre: "Semestral" },
  { dias: 365, nombre: "Anual" },
];
