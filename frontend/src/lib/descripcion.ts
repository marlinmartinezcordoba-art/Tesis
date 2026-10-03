import { pedir } from "./api";

export type TipoEntidad = "agente" | "lugar" | "fecha" | "actividad" | "tipo_actividad" | "mandato" | "forma_documental";

export const TIPO_NOMBRE: Record<TipoEntidad, string> = {
  agente: "Agente",
  lugar: "Lugar",
  fecha: "Fecha",
  actividad: "Actividad",
  tipo_actividad: "Tipo de actividad",
  mandato: "Mandato o norma",
  forma_documental: "Forma documental",
};

// Actividad, tipo de actividad y mandato comparten color: son una sola
// familia, la del contexto institucional; los distingue su insignia.
export const TIPO_CLASE: Record<TipoEntidad, string> = {
  agente: "agente",
  lugar: "alerta",
  fecha: "proceso",
  actividad: "contexto",
  tipo_actividad: "contexto",
  mandato: "contexto",
  forma_documental: "bien",
};

export const SUBTIPO_AGENTE: Record<string, string> = {
  persona: "Persona",
  entidad_corporativa: "Entidad corporativa",
  grupo: "Grupo (comité, junta)",
  cargo: "Cargo",
  familia: "Familia",
  mecanismo: "Mecanismo (software)",
};

export const SUBTIPO_MANDATO: Record<string, string> = {
  ley: "Ley",
  decreto: "Decreto",
  ordenanza: "Ordenanza",
  acuerdo: "Acuerdo",
  resolucion: "Resolución",
  otro: "Otro instrumento",
};

export const SUBTIPO_NOMBRE: Record<string, string> = { ...SUBTIPO_AGENTE, ...SUBTIPO_MANDATO };

export const ROL_NOMBRE: Record<string, string> = {
  productor: "Productor",
  remitente: "Remitente",
  destinatario: "Destinatario",
  mencionado: "Mencionado",
};

export const NIVEL_NOMBRE: Record<string, string> = {
  fondo: "Fondo",
  seccion: "Sección",
  serie: "Serie",
  subserie: "Subserie",
  expediente: "Expediente",
  unidad_documental: "Unidad documental",
};

export const ORIGEN_NOMBRE: Record<string, string> = {
  motor: "Propuesto por el motor",
  motor_editado: "Propuesto por el motor y corregido",
  persona: "Escrito por una persona",
};

export const EN_VOCABULARIO: TipoEntidad[] = ["agente", "lugar", "forma_documental", "actividad", "tipo_actividad", "mandato"];

export interface Coincidencia {
  id: string;
  nombre: string;
  subtipo: string | null;
  similitud: number;
  conexiones: number;
}

export function verificarVocabulario(fondoId: string, tipo: TipoEntidad, valor: string): Promise<Coincidencia[]> {
  return pedir<Coincidencia[]>("/api/descripcion/verificar-vocabulario", {
    method: "POST",
    body: JSON.stringify({ fondo_id: fondoId, tipo, valor }),
  });
}

export interface NivelSuperior {
  id: string;
  titulo: string;
  nivel: string;
}

export function nivelesSuperiores(fondoId: string, nivel: string): Promise<NivelSuperior[]> {
  return pedir<NivelSuperior[]>(`/api/descripcion/niveles-superiores?fondo_id=${fondoId}&nivel=${nivel}`);
}

// Estado de la verificación de vocabulario de una entidad en pantalla.
export interface Verificacion {
  estado: "no_aplica" | "sin_verificar" | "verificando" | "pregunta" | "resuelta";
  coincidencias: Coincidencia[];
  reutilizarId?: string;
  reutilizarNombre?: string;
  crearNueva?: boolean;
}

export function verificacionInicial(tipo: TipoEntidad): Verificacion {
  return { estado: EN_VOCABULARIO.includes(tipo) ? "sin_verificar" : "no_aplica", coincidencias: [] };
}
