// Buscador unificado (RF-SEARCH-001/002). El servidor marca lo que coincide
// con ⟦ y ⟧; aquí se parte el texto para resaltarlo sin interpretar HTML.
export const ABRE = "⟦";
export const CIERRA = "⟧";

export interface Parte { texto: string; resaltado: boolean }

export function partesResaltadas(fragmento: string): Parte[] {
  const partes: Parte[] = [];
  let resto = fragmento;
  while (resto) {
    const i = resto.indexOf(ABRE);
    const j = i < 0 ? -1 : resto.indexOf(CIERRA, i + 1);
    if (i < 0 || j < 0) {
      partes.push({ texto: resto.split(ABRE).join("").split(CIERRA).join(""), resaltado: false });
      break;
    }
    if (i > 0) partes.push({ texto: resto.slice(0, i), resaltado: false });
    partes.push({ texto: resto.slice(i + 1, j), resaltado: true });
    resto = resto.slice(j + 1);
  }
  return partes;
}

export type Alcance = "todo" | "descripcion" | "texto" | "autoridades";

export const ALCANCE_NOMBRE: Record<Alcance, string> = {
  todo: "Todo",
  descripcion: "Descripción",
  texto: "Texto de los documentos",
  autoridades: "Autoridades",
};

export interface DocumentoHallado {
  id: string;
  titulo: string;
  nivel: string;
  codigo_referencia: string | null;
  fechas: string | null;
  fondo: { id: string; titulo: string };
  ruta: string[];
  motivos: string[];
  fragmento: string | null;
  borrador: boolean;
}

export interface AutoridadHallada {
  id: string;
  nombre: string;
  clase: string;
  subtipo: string | null;
  fondo_id: string;
  motivo: string;
  documentos: number;
  ejemplos: { id: string; titulo: string; nivel: string }[];
}

export interface ResultadoBusqueda {
  q: string;
  total: number;
  pagina: number;
  por_pagina: number;
  documentos: DocumentoHallado[];
  autoridades: AutoridadHallada[];
  archivos_sin_describir: { id: string; nombre: string; fondo_id: string; fondo: string }[];
  facetas: {
    niveles: Record<string, number>;
    fondos: { id: string; titulo: string; total: number }[];
    agentes: { id: string; nombre: string; documentos: number }[];
    anios: [number, number] | null;
  };
  alcance_reserva: "completo" | "publico";
}
