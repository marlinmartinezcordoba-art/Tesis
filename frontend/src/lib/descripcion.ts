import { pedir } from "./api";
import { RELACION_DEL_ROL, termino } from "./terminos";

export type TipoEntidad = "agente" | "lugar" | "fecha" | "actividad" | "tipo_actividad" | "mandato" | "forma_documental"
  | "materia";

export const TIPO_NOMBRE: Record<TipoEntidad, string> = {
  agente: "Agente",
  lugar: "Lugar",
  fecha: "Fecha",
  actividad: "Actividad",
  tipo_actividad: "Tipo de actividad",
  mandato: "Mandato o norma",
  forma_documental: "Forma documental",
  materia: "Materia (tema)",
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
  materia: "bien",
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

// El papel del agente se nombra con el vocabulario único de relaciones (lib/terminos.ts, generado).
const nombreDelRol = (rol: string) => termino(RELACION_DEL_ROL[rol], rol)?.nombre ?? rol;

export const ROL_NOMBRE: Record<string, string> = {
  productor: nombreDelRol("productor"),
  autor: `${nombreDelRol("autor")} (persona, grupo o cargo)`,
  remitente: nombreDelRol("remitente"),
  destinatario: nombreDelRol("destinatario"),
  acumulador: nombreDelRol("acumulador"),
  mencionado: nombreDelRol("mencionado"),
  custodio: `${nombreDelRol("custodio")} (distinto del productor)`,
  // Cobertura total de RiC-CM (R029, R030, R037, R038, R040, R020).
  receptor: nombreDelRol("receptor"),
  coleccionista: `${nombreDelRol("coleccionista")} (colección facticia)`,
  tema_principal: nombreDelRol("tema_principal"),
  propietario: `${nombreDelRol("propietario")} (persona, grupo o cargo)`,
  gestor: nombreDelRol("gestor"),
  titular_derechos: `${nombreDelRol("titular_derechos")} (Ley 23 de 1982)`,
};

// El papel de una fecha en la descripción: de creación (RiC-R080) o de modificación (RiC-R073).
export const ROL_FECHA_NOMBRE: Record<string, string> = {
  "": "Fecha de creación",
  modificacion: "Fecha de modificación (reforma o adición posterior)",
};

// El papel de un lugar en la descripción, con los mismos términos.
export const ROL_LUGAR_NOMBRE: Record<string, string> = {
  "": termino("has_or_had_subject", "lugar")?.nombre ?? "",
  expedicion: termino("is_or_was_location_of", "expedicion")?.nombre ?? "",
};

export const NIVEL_NOMBRE: Record<string, string> = {
  fondo: "Fondo",
  coleccion: "Colección",
  seccion: "Sección",
  subseccion: "Subsección",
  serie: "Serie",
  subserie: "Subserie",
  expediente: "Expediente",
  unidad_documental: "Unidad documental",
  parte_documental: "Parte documental",
};

export const ORIGEN_NOMBRE: Record<string, string> = {
  motor: "Propuesto por el motor",
  motor_editado: "Propuesto por el motor y corregido",
  persona: "Escrito por una persona",
};

export const EN_VOCABULARIO: TipoEntidad[] = ["agente", "lugar", "forma_documental", "actividad", "tipo_actividad", "mandato",
  "materia"];

export interface Coincidencia {
  id: string;
  nombre: string;
  subtipo: string | null;
  similitud: number;
  conexiones: number;
  aviso?: string | null;
}

export function verificarVocabulario(fondoId: string, tipo: TipoEntidad | "tipo_parte", valor: string): Promise<Coincidencia[]> {
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

export function nivelesSuperiores(fondoId: string, nivel: string, adicional = false): Promise<NivelSuperior[]> {
  return pedir<NivelSuperior[]>(`/api/descripcion/niveles-superiores?fondo_id=${fondoId}&nivel=${nivel}${adicional ? "&adicional=true" : ""}`);
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
