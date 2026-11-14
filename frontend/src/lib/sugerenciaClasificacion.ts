// Sugerencia de clasificación (Ley 1712 de 2014) y de datos personales (Ley 1581 de 2012) a partir de
// lo que el detector de reglas encontró en el texto del documento. Es una sugerencia: la decisión es
// de la persona (la clasificación la decide la institución, no el motor). No usa IA: se puede explicar.

export interface HallazgoResumen {
  tipo_nombre: string; categoria: "personal" | "sensible" | "menores"; categoria_final: "personal" | "sensible" | "menores" | null;
  estado: "pendiente" | "confirmado" | "corregido" | "descartado"; veces: number; paginas: number[];
}
export interface RevisionResumen {
  documentos: { hallazgos: HallazgoResumen[] }[]; pendientes: number; sin_texto: string[];
}
export interface Sugerencia {
  acceso: "hereda" | "publico" | "clasificado";
  fundamento: string;
  reproduccion: "permitida" | "condicionada" | "no_permitida";
  datosPersonales: "no_contiene" | "personales" | "sensibles" | "menores";
  motivos: string[];
  pendientes: number;
}

const ORDEN = { personal: 1, sensible: 2, menores: 3 } as const;
const NIVEL = { personal: "personales", sensible: "sensibles", menores: "menores" } as const;
const FUNDAMENTO_INTIMIDAD = "Ley 1712 de 2014, art. 18, literal a (intimidad); Ley 1581 de 2012, arts. 5 a 7";

export function sugerirClasificacion(revision: RevisionResumen | null | undefined,
                                     heredada?: { acceso: string } | null): Sugerencia | null {
  if (!revision) return null;
  const hallazgos = revision.documentos.flatMap((d) => d.hallazgos).filter((h) => h.estado !== "descartado");
  // Sin texto no hay de dónde sugerir: la persona revisa el documento.
  if (!hallazgos.length && revision.sin_texto.length) return null;
  const categoria = (h: HallazgoResumen) => h.categoria_final || h.categoria;
  const mayor = hallazgos.reduce<HallazgoResumen["categoria"] | null>(
    (m, h) => (!m || ORDEN[categoria(h)] > ORDEN[m] ? categoria(h) : m), null);

  const porTipo = new Map<string, { veces: number; paginas: Set<number> }>();
  for (const h of hallazgos) {
    const x = porTipo.get(h.tipo_nombre) || { veces: 0, paginas: new Set<number>() };
    x.veces += h.veces;
    h.paginas.forEach((p) => x.paginas.add(p));
    porTipo.set(h.tipo_nombre, x);
  }
  const motivos = [...porTipo].map(([tipo, x]) => {
    const pags = [...x.paginas].sort((a, b) => a - b);
    return `${tipo}: ${x.veces} ${x.veces === 1 ? "vez" : "veces"}${pags.length ? ` (pág. ${pags.slice(0, 6).join(", ")}${pags.length > 6 ? "…" : ""})` : ""}`;
  });
  const restringidaArriba = heredada && (heredada.acceso === "clasificado" || heredada.acceso === "reservado");

  if (mayor === "sensible" || mayor === "menores") {
    return { acceso: restringidaArriba ? "hereda" : "clasificado", fundamento: restringidaArriba ? "" : FUNDAMENTO_INTIMIDAD,
      reproduccion: "no_permitida", datosPersonales: NIVEL[mayor], pendientes: revision.pendientes,
      motivos: [`Hay datos ${mayor === "menores" ? "de niños, niñas o adolescentes" : "sensibles"}: publicarla sin restricción `
        + "expondría la intimidad de personas identificables.", ...motivos] };
  }
  return {
    acceso: restringidaArriba ? "hereda" : "publico", fundamento: "", reproduccion: "permitida",
    datosPersonales: mayor ? "personales" : "no_contiene", pendientes: revision.pendientes,
    motivos: [restringidaArriba ? "El nivel superior ya está restringido: se conserva lo heredado."
      : "Máxima publicidad (Ley 1712, art. 2): no aparece información de las excepciones de los arts. 18 y 19.",
      ...(mayor ? ["Tiene datos personales: queda pública, pero la consulta los anonimiza.", ...motivos]
        : ["El detector no encontró identificadores personales en el texto."])],
  };
}
