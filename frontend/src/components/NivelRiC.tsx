import { NIVEL_RIC } from "@/lib/terminos";

// El término RiC-O junto al término archivístico de un nivel (ISAD(G) y cuadro
// de clasificación): la clase y el tipo de agrupación con que se guarda en el
// grafo RiC-O. «≈» cuando el nivel no tiene tipo propio en RiC-O.
export function textoRiC(nivel: string): string {
  const r = NIVEL_RIC[nivel];
  if (!r) return "";
  return r.tipo ? `${r.clase} · ${r.tipo}` : r.cercano ? `${r.clase} · ≈ ${r.cercano}` : r.clase;
}

export function NivelRiC({ nivel }: { nivel: string }) {
  const texto = textoRiC(nivel);
  if (!texto) return null;
  const r = NIVEL_RIC[nivel];
  const ayuda = r.tipo ? "Clase y tipo de agrupación en RiC-O 1.1"
    : r.cercano ? "Clase en RiC-O 1.1; este nivel no tiene tipo oficial y se une al más cercano (skos:broadMatch)"
      : "Clase en RiC-O 1.1";
  return <span className="nivel-ric" title={ayuda}>{texto}</span>;
}
