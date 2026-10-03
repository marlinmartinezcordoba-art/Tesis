export type ClaseVocabulario = "agente" | "lugar" | "forma_documental" | "actividad" | "tipo_actividad" | "mandato";

export interface EntidadVocabulario {
  id: string;
  clase: ClaseVocabulario;
  subtipo: string | null;
  nombre: string;
  estado: "activa" | "fusionada";
  conexiones: number;
  fusionada_en: { id: string; nombre: string } | null;
}

export interface Sugerencia {
  id: string;
  clase: ClaseVocabulario;
  similitud: number;
  creada_en: string;
  entidades: [EntidadVocabulario, EntidadVocabulario];
}

export interface ParametrosFusion {
  similitud_pct: number;
  max_conexiones: number;
  horas_deteccion: number;
}

export const CLASES: ClaseVocabulario[] = ["agente", "lugar", "forma_documental", "actividad", "tipo_actividad", "mandato"];

export const CLASE_NOMBRE: Record<ClaseVocabulario, string> = {
  agente: "Agente",
  lugar: "Lugar",
  forma_documental: "Forma documental",
  actividad: "Actividad",
  tipo_actividad: "Tipo de actividad",
  mandato: "Mandato o norma",
};

export const CLASE_NOMBRE_PLURAL: Record<ClaseVocabulario, string> = {
  agente: "Agentes",
  lugar: "Lugares",
  forma_documental: "Formas documentales",
  actividad: "Actividades",
  tipo_actividad: "Tipos de actividad",
  mandato: "Mandatos y normas",
};

// Referencia RiC-CM de cada clase, para que el archivista sepa qué es.
export const CLASE_RIC: Record<ClaseVocabulario, string> = {
  agente: "RiC-E07 Agent",
  lugar: "RiC-E22 Place",
  forma_documental: "RiC-A17 Documentary form type",
  actividad: "RiC-E15 Activity",
  tipo_actividad: "rico:ActivityType (vocabulario controlado)",
  mandato: "RiC-E17 Mandate",
};

export const CLASE_INSIGNIA: Record<ClaseVocabulario, string> = {
  agente: "agente",
  lugar: "alerta",
  forma_documental: "bien",
  actividad: "contexto",
  tipo_actividad: "contexto",
  mandato: "contexto",
};

export function conexionesTexto(n: number): string {
  return `${n} documento${n === 1 ? "" : "s"}`;
}
