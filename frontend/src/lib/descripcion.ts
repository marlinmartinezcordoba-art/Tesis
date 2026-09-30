import { pedir } from "./api";

export type TipoEntidad = "agente" | "lugar" | "fecha" | "actividad" | "forma_documental";

export const TIPO_NOMBRE: Record<TipoEntidad, string> = {
  agente: "Agente",
  lugar: "Lugar",
  fecha: "Fecha",
  actividad: "Actividad",
  forma_documental: "Forma documental",
};

export const TIPO_CLASE: Record<TipoEntidad, string> = {
  agente: "agente",
  lugar: "alerta",
  fecha: "proceso",
  actividad: "acento",
  forma_documental: "bien",
};

export const SUBTIPO_NOMBRE: Record<string, string> = {
  persona: "Persona",
  entidad_corporativa: "Entidad corporativa",
  cargo: "Cargo",
  familia: "Familia",
};

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

export const EN_VOCABULARIO: TipoEntidad[] = ["agente", "lugar", "forma_documental"];

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
