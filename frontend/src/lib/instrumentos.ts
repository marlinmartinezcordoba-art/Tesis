export interface NodoArbol {
  id: string;
  nivel: string;
  titulo: string;
  codigo_referencia: string | null;
  fechas_extremas: string | null;
  hijos: number;
  unidades_documentales: number;
}

export interface Miga {
  id: string;
  nivel: string;
  titulo: string;
}

export interface NivelCatalogo {
  fondo: { id: string; titulo: string };
  migas: Miga[];
  actual: NodoArbol;
  hijos: NodoArbol[];
}

export interface EntidadFicha {
  entidad_id: string;
  tipo: string;
  valor: string;
  subtipo: string | null;
  rol: string | null;
  codigo_ric: string;
  uri_rico: string | null;
  fecha_normalizada?: string | null;
  fecha_legible?: string | null;
  contexto?: import("@/components/ContextoActividad").ContextoActividad;
  en_vocabulario: boolean;
  documentos: number | null;
}

export interface Preservacion {
  estado: "buen_estado" | "alerta_integridad" | "riesgo_obsolescencia" | "sin_verificar" | "sin_evaluar";
  integridad?: string;
  riesgo?: string;
  derivada_de?: string | null;
  formato?: string | null;
  puid?: string | null;
  algoritmo_huella?: string;
  huella?: string | null;
}

export interface Ficha {
  id: string;
  nivel: string;
  titulo: string;
  alcance_contenido: string | null;
  incluido_en: Miga | null;
  forma_documental: { id: string; nombre: string; documentos: number } | null;
  entidades: EntidadFicha[];
  instanciaciones: { id: string; nombre: string; preservacion: Preservacion }[];
  migas: Miga[];
  fechas_extremas: string | null;
  control: { codigo_referencia: string | null; caja: string | null; carpeta: string | null; folios: number | null; soporte: string | null };
  hijos: number;
  publicado_en: string | null;
  // Versión 3 de la descripción
  idiomas: string[];
  condiciones_acceso: string | null;
  condiciones_uso: string | null;
  tipo_parte: string | null;
  partes: { id: string; titulo: string; tipo_parte: string | null; alcance_contenido: string | null; instanciaciones: { id: string; nombre: string }[] }[];
  parte_de: Miga | null;
  secuencia: { id: string; titulo: string; posicion: "precede_a" | "sigue_a"; uri_rico: string }[];
}

export interface Inventario {
  nivel: Miga;
  fondo: { id: string; titulo: string };
  columnas: { clave: string; nombre: string; obligatoria: boolean }[];
  filas: { id: string; nivel: string; valores: Record<string, string | number | null>; pendientes: string[] }[];
  pendientes: number;
  pendientes_por_campo: Record<string, number>;
  alerta: { id: string; mensaje: string } | null;
}

export interface Indice {
  fondo: { id: string; titulo: string };
  grupos: {
    clase: string;
    total: number;
    letras: { letra: string; entidades: {
      id: string; nombre: string; subtipo: string | null; documentos: number;
      descripciones: { id: string; titulo: string; nivel: string }[];
    }[] }[];
  }[];
}

// Cómo se lee cada relación en la ficha, en lenguaje archivístico.
export function etiquetaRelacion(e: EntidadFicha): string {
  if (e.tipo === "fecha") return "Fecha";
  if (e.tipo === "lugar") return "Lugar";
  if (e.tipo === "actividad") return "Actividad documentada";
  if (e.codigo_ric === "has_or_had_subject") return "Trata de";
  if (e.rol === "productor" || e.codigo_ric === "has_creator") return "Producido por";
  if (e.rol === "remitente") return "Remitido por";
  if (e.rol === "destinatario") return "Dirigido a";
  if (e.rol === "mencionado") return "Menciona a";
  return "Agente";
}

export const ESTADO_PRESERVACION: Record<Preservacion["estado"], { texto: string; clase: string; orden: number }> = {
  alerta_integridad: { texto: "Alerta de integridad", clase: "error", orden: 0 },
  riesgo_obsolescencia: { texto: "Riesgo de obsolescencia", clase: "alerta", orden: 1 },
  sin_verificar: { texto: "Sin verificar todavía", clase: "proceso", orden: 2 },
  sin_evaluar: { texto: "Sin evaluar", clase: "proceso", orden: 3 },
  buen_estado: { texto: "Buen estado", clase: "bien", orden: 4 },
};
