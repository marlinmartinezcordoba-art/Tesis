// Propiedad de RiC-O de un cambio o de una relación, del mapeo único del
// sistema: verificada contra el OWL, sin propiedad en RiC-O, o texto
// libre cuya propiedad no está confirmada (nunca se inventa un nombre).
export interface PropiedadRico {
  nombre: string | null;
  estado: "verificada" | "general" | "sin_propiedad" | "literal_pendiente";
  codigo_cm?: string | null;
}

export interface Cambio {
  campo: string;
  antes: unknown;
  despues: unknown;
  propiedad_rico?: PropiedadRico | null;
}

export interface Evento {
  id: number;
  fecha: string;
  usuario_id: string | null;
  usuario: string | null;
  modulo: string;
  accion: string;
  etiqueta: string;
  entidad_tipo: string | null;
  entidad_id: string | null;
  detalle: string | null;
  propiedad_rico?: PropiedadRico | null;
  cambios: Cambio[];
}

export interface FilaConsolidado {
  usuario_id: string;
  nombre: string;
  rol: string;
  rol_nombre: string;
  activo: boolean;
  dias_trabajados: number;
  dias_habiles_trabajados: number;
  dias_fin_de_semana: number;
  dias_habiles: number;
  segundos_conectado: number;
  sesiones: number;
  en_curso: boolean;
  acciones: Record<string, number>;
}

export interface Consolidado {
  semana: { lunes: string; domingo: string; anterior: string; siguiente: string | null; zona_horaria: string };
  filas: FilaConsolidado[];
}

export interface Desglose {
  usuario: { id: string; nombre: string };
  semana: string;
  sesiones: { sesion_id: string; inicio: string; fin: string; en_curso: boolean; motivo: string | null; segundos: number;
    acciones: Record<string, number> }[];
  segundos_conectado: number;
}

export const MODULO_NOMBRE: Record<string, string> = {
  autenticacion: "Autenticación", ingesta: "Ingesta", descripcion: "Descripción", vocabularios: "Vocabularios",
  instrumentos: "Instrumentos", preservacion: "Preservación", auditoria: "Auditoría", sistema: "Sistema",
  evaluacion: "Evaluación",
};

export const MOTIVO_CIERRE: Record<string, string> = {
  cierre_voluntario: "cerró sesión", expiracion: "venció por inactividad o tiempo máximo",
  cambio_contrasena: "cambio de contraseña", cuenta_desactivada: "cuenta desactivada",
  revocada_administrador: "cerrada por la administración", reutilizacion_token: "cerrada por seguridad (enlace de sesión reutilizado)",
};

export function duracion(segundos: number): string {
  const h = Math.floor(segundos / 3600);
  const m = Math.round((segundos % 3600) / 60);
  if (h === 0) return `${m} min`;
  return m ? `${h} h ${m} min` : `${h} h`;
}

export function valor(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    return typeof o.nombre === "string" ? o.nombre : JSON.stringify(v);
  }
  return String(v);
}

// Enlace a la historia de auditoría de una entidad, desde cualquier pantalla.
export function enlaceHistoria(tipo: string, id: string, nombre: string, volver: string): string {
  const p = new URLSearchParams({ nombre, volver });
  return `/auditoria/entidad/${tipo}/${id}?${p}`;
}
