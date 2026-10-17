import { pedir } from "./api";

// Tesauros para normalizar las materias (temas) de la descripción.

export interface Tesauro {
  id: string; nombre: string; fuente: string | null; licencia: string | null; idioma: string; formato: string;
  archivo: string | null; uri_esquema: string | null; conceptos: number; estado: "vigente" | "anulado"; importado_en: string;
}

export interface Concepto {
  id: string; preferente: string; uri: string | null; notacion: string | null; nota_alcance: string | null;
  no_preferentes: string[]; ruta: string[]; tesauro: { id: string; nombre: string; licencia: string | null };
  etiqueta_coincidente?: string | null; similitud?: number | null;
}

export interface Normalizacion {
  termino: string; exacto: Concepto | null; via: "preferente" | "no_preferente" | null; parecidos: Concepto[];
}

export function normalizar(texto: string): Promise<Normalizacion> {
  return pedir<Normalizacion>(`/api/tesauros/normalizar?texto=${encodeURIComponent(texto)}`);
}
