import { useEffect, useState } from "react";
import { pedir } from "@/lib/api";

// Guía de cada campo y de cada tipo de entidad: qué es, por qué importa,
// con qué se relaciona, y sus normas (ISAD(G), RiC-O, Esquema del AGN).
// El texto viene del servidor (servicios/guia_metadatos.py): una sola fuente.

interface FilaAgn { id: string; elemento: string; obligatoriedad: string; codigo_agn: string }
interface GuiaAtributo {
  clave: string; etiqueta: string; isad: string | null; rico: string | null; cardinalidad: string; obligatorio: boolean;
  que_es: string; por_que: string; se_relaciona: string; ejemplo: string | null; agn: FilaAgn[];
}
interface GuiaEntidad { tipo: string; rico: string; que_es: string; por_que: string; se_relaciona: string; ejemplo: string | null }
interface Guia { atributos: GuiaAtributo[]; entidades: GuiaEntidad[] }

let cache: Promise<Guia> | null = null;

function useGuia(): Guia | null {
  const [guia, setGuia] = useState<Guia | null>(null);
  useEffect(() => {
    if (!cache) cache = pedir<Guia>("/api/descripcion/guia").catch((e) => { cache = null; throw e; });
    let vivo = true;
    cache.then((g) => vivo && setGuia(g)).catch(() => undefined);
    return () => { vivo = false; };
  }, []);
  return guia;
}

function Cuerpo({ que_es, por_que, se_relaciona, ejemplo, normas }: {
  que_es: string; por_que: string; se_relaciona: string; ejemplo: string | null; normas: string[];
}) {
  return (
    <div className="guia-cuerpo">
      <p><strong>Qué es.</strong> {que_es}</p>
      <p><strong>Por qué importa.</strong> {por_que}</p>
      <p><strong>Con qué se relaciona.</strong> {se_relaciona}</p>
      {ejemplo && <p><strong>Ejemplo.</strong> {ejemplo}</p>}
      {normas.length > 0 && <p className="meta">{normas.join(" · ")}</p>}
    </div>
  );
}

export function GuiaCampo({ clave }: { clave: string }) {
  const guia = useGuia();
  const a = guia?.atributos.find((x) => x.clave === clave);
  if (!a) return null;
  const normas = [
    a.isad ? `ISAD(G) ${a.isad}` : null, a.rico, `Cardinalidad ${a.cardinalidad}${a.obligatorio ? " (obligatorio)" : ""}`,
    ...a.agn.map((f) => `AGN ${f.id}: ${f.elemento}${f.obligatoriedad !== "—" ? ` (${f.obligatoriedad.toLowerCase()})` : ""}`),
  ].filter(Boolean) as string[];
  return (
    <details className="guia-campo">
      <summary aria-label={`Qué es «${a.etiqueta}» y por qué importa`} title="Qué es, por qué importa y con qué se relaciona">ⓘ</summary>
      <Cuerpo {...a} normas={normas} />
    </details>
  );
}

export function GuiaTipoEntidad({ tipo }: { tipo: string }) {
  const guia = useGuia();
  const e = guia?.entidades.find((x) => x.tipo === tipo);
  if (!e) return null;
  return (
    <details className="guia-campo">
      <summary aria-label="Qué es este tipo de entidad y por qué importa" title="Qué es y por qué importa">ⓘ</summary>
      <Cuerpo {...e} normas={[e.rico]} />
    </details>
  );
}
