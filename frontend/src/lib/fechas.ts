// Fechas en EDTF (subconjunto del módulo de descripción). La archivista
// nunca escribe la expresión: la arman estos controles. La forma legible
// replica la del servidor (app/servicios/fechas.py), que es la que vale.

export type SubtipoFecha = "simple" | "rango" | "conjunto";
export type Precision = "exacto" | "decada" | "siglo" | "desconocido";
export type Calificador = "" | "~" | "?" | "%";

export interface PuntoFecha {
  vacio: boolean; // extremo desconocido de un rango
  precision: Precision;
  anio: string;
  mes: string; // "" o "01".."12"
  dia: string; // "" o "1".."31"
  calificador: Calificador;
}

export interface ControlFecha {
  subtipo: SubtipoFecha;
  puntos: PuntoFecha[];
}

export const SUBTIPO_FECHA_NOMBRE: Record<SubtipoFecha, string> = {
  simple: "Fecha simple",
  rango: "Rango de fechas",
  conjunto: "Conjunto de fechas",
};

export const CALIFICADOR_NOMBRE: Record<Calificador, string> = {
  "": "Exacta",
  "~": "Aproximada (c.)",
  "?": "Incierta",
  "%": "Aproximada e incierta",
};

export const PRECISION_NOMBRE: Record<Precision, string> = {
  exacto: "Año",
  decada: "Década",
  siglo: "Siglo",
  desconocido: "Año desconocido",
};

export const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
  "octubre", "noviembre", "diciembre"];

export function puntoVacio(): PuntoFecha {
  return { vacio: false, precision: "exacto", anio: "", mes: "", dia: "", calificador: "" };
}

export function controlInicial(subtipo: SubtipoFecha = "simple"): ControlFecha {
  return { subtipo, puntos: subtipo === "simple" ? [puntoVacio()] : [puntoVacio(), puntoVacio()] };
}

function token(p: PuntoFecha): string | null {
  if (p.precision === "desconocido") return "XXXX";
  if (!/^\d{4}$/.test(p.anio)) return null;
  if (p.precision === "decada") return `${p.anio.slice(0, 3)}X`;
  if (p.precision === "siglo") return `${p.anio.slice(0, 2)}XX`;
  if (!p.mes) return p.anio;
  if (!p.dia) return `${p.anio}-${p.mes}`;
  const dia = p.dia.padStart(2, "0");
  const d = new Date(`${p.anio}-${p.mes}-${dia}T00:00:00Z`);
  if (Number.isNaN(d.getTime()) || d.getUTCDate() !== Number(dia)) return null;
  return `${p.anio}-${p.mes}-${dia}`;
}

// Expresión EDTF de los controles, o null si falta algo.
export function construir(c: ControlFecha): string | null {
  if (c.subtipo === "simple") {
    const t = token(c.puntos[0]);
    return t ? t + c.puntos[0].calificador : null;
  }
  if (c.subtipo === "rango") {
    const [a, b] = c.puntos;
    if (a.vacio && b.vacio) return null;
    const ta = a.vacio ? "" : token(a);
    const tb = b.vacio ? "" : token(b);
    if (ta === null || tb === null) return null;
    return `${ta}${ta ? a.calificador : ""}/${tb}${tb ? b.calificador : ""}`;
  }
  const tokens = c.puntos.map(token);
  if (tokens.length < 2 || tokens.some((t) => !t)) return null;
  return `{${tokens.join(",")}}`;
}

function desarmarToken(t: string, calificador: Calificador = ""): PuntoFecha {
  const [anio, mes = "", dia = ""] = t.split("-");
  if (anio === "XXXX") return { ...puntoVacio(), precision: "desconocido", calificador };
  if (anio.endsWith("XX")) return { ...puntoVacio(), precision: "siglo", anio: `${anio.slice(0, 2)}00`, calificador };
  if (anio.endsWith("X")) return { ...puntoVacio(), precision: "decada", anio: `${anio.slice(0, 3)}0`, calificador };
  return {
    ...puntoVacio(), anio, mes: mes === "XX" ? "" : mes, dia: dia === "XX" || !dia ? "" : String(Number(dia)), calificador,
  };
}

function separarCalificador(t: string): [string, Calificador] {
  const ultimo = t.slice(-1);
  return ["~", "?", "%"].includes(ultimo) ? [t.slice(0, -1), ultimo as Calificador] : [t, ""];
}

// Controles a partir de una expresión (para mostrar lo que propuso el motor).
export function desarmar(edtf: string | null | undefined, subtipo?: SubtipoFecha | null): ControlFecha {
  if (!edtf) return controlInicial(subtipo || "simple");
  if (edtf.startsWith("{")) {
    return { subtipo: "conjunto", puntos: edtf.slice(1, -1).split(",").map((t) => desarmarToken(t)) };
  }
  if (edtf.includes("/")) {
    const [a, b] = edtf.split("/");
    const punto = (x: string) => (x ? desarmarToken(...separarCalificador(x)) : { ...puntoVacio(), vacio: true });
    return { subtipo: "rango", puntos: [punto(a), punto(b)] };
  }
  return { subtipo: "simple", puntos: [desarmarToken(...separarCalificador(edtf))] };
}

function romano(n: number): string {
  const v: [number, string][] = [[10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]];
  let s = "";
  for (const [valor, letra] of v) while (n >= valor) { s += letra; n -= valor; }
  return s;
}

function legibleToken(t: string): string {
  const [anio, mes, dia] = t.split("-");
  let a = anio;
  if (anio === "XXXX") a = "año desconocido";
  else if (anio.endsWith("XX")) a = `siglo ${romano(Number(anio.slice(0, 2)) + 1)} (${anio.slice(0, 2)}00–${anio.slice(0, 2)}99)`;
  else if (anio.endsWith("X")) a = `década de ${anio.slice(0, 3)}0`;
  if (!mes) return a;
  if (mes === "XX") return `${a} (mes sin precisar)`;
  const m = MESES[Number(mes) - 1];
  if (!dia) return `${m} de ${a}`;
  if (dia === "XX") return `${m} de ${a} (día sin precisar)`;
  return `${Number(dia)} de ${m} de ${a}`;
}

function conCalificador(texto: string, c: string): string {
  if (c === "~") return `c. ${texto}`;
  if (c === "?") return `${texto} (incierta)`;
  if (c === "%") return `c. ${texto} (incierta)`;
  return texto;
}

export function legible(edtf: string | null | undefined): string {
  if (!edtf) return "";
  if (edtf.startsWith("{")) {
    const textos = edtf.slice(1, -1).split(",").map(legibleToken);
    return `${textos.slice(0, -1).join(", ")} y ${textos[textos.length - 1]}`;
  }
  if (edtf.includes("/")) {
    const [a, b] = edtf.split("/").map((x) => (x ? conCalificador(legibleToken(separarCalificador(x)[0]), separarCalificador(x)[1]) : ""));
    if (a && b) return `de ${a} a ${b}`;
    return b ? `hasta ${b} (inicio desconocido)` : `desde ${a} (fin desconocido)`;
  }
  const [t, c] = separarCalificador(edtf);
  return conCalificador(legibleToken(t), c);
}
