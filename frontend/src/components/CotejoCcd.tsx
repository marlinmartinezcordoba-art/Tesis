import { useEffect, useState } from "react";
import { ErrorAPI, pedir, subir } from "@/lib/api";

// Cotejo del cuadro de clasificación (CCD) con la versión de la TRD (fase C). Se compara por
// código: series del CCD sin retención en la TRD (lo más grave), series de la TRD que el CCD no
// tiene, el mismo código con otro nombre, otra dependencia. No corrige nada: decide la persona.

interface Item { codigo: string; nivel: string; nombre: string; dependencia?: string; fila?: number; parte?: string | null;
  en_ccd?: string; en_trd?: string }
export interface Cotejo {
  version: { nombre: string }; diferencias: number; coinciden: number;
  sin_retencion: Item[]; solo_en_trd: Item[]; nombre_distinto: Item[]; otra_dependencia: Item[];
  dependencias: { solo_en_ccd: { codigo: string; nombre: string }[]; solo_en_trd: { codigo: string; nombre: string }[];
    nombre_distinto: { codigo: string; en_ccd: string; en_trd: string }[] };
  totales: { series_ccd: number; subseries_ccd: number; series_trd: number; subseries_trd: number };
  archivo: { archivo: string; huella: string } | null; cotejado_en?: string;
}

function Lista({ titulo, items, texto }: { titulo: string; items: Item[]; texto: (i: Item) => string }) {
  if (!items.length) return null;
  return (
    <details open={items.length <= 8}>
      <summary><strong>{titulo}</strong> <span className="meta">({items.length})</span></summary>
      <ul className="meta">{items.map((i) => <li key={`${i.nivel}-${i.codigo}`}>{texto(i)}</li>)}</ul>
    </details>
  );
}

export function ResultadoCotejo({ c }: { c: Cotejo }) {
  const d = c.dependencias;
  return (
    <div className={`aviso ${c.diferencias ? (c.sin_retencion.length ? "error" : "alerta") : "bien"}`} role="status">
      <strong>{c.diferencias ? `El CCD y la ${c.version.nombre} no coinciden en ${c.diferencias} punto(s)`
        : `El CCD y la ${c.version.nombre} coinciden`}</strong>
      <span className="meta"> · {c.coinciden} serie(s) y subserie(s) en los dos{c.archivo && ` · CCD «${c.archivo.archivo}»`}</span>
      <Lista titulo="Del CCD, sin retención en la TRD" items={c.sin_retencion}
             texto={(i) => `${i.codigo} ${i.nombre} (${i.nivel}) · ${i.dependencia}${i.fila ? ` · fila ${i.fila}${i.parte ? ` de ${i.parte}` : ""}` : ""}`} />
      <Lista titulo="De la TRD, que no están en el CCD" items={c.solo_en_trd}
             texto={(i) => `${i.codigo} ${i.nombre} (${i.nivel}) · ${i.dependencia}`} />
      <Lista titulo="El mismo código con otro nombre" items={c.nombre_distinto}
             texto={(i) => `${i.codigo}: en el CCD «${i.en_ccd}», en la TRD «${i.en_trd}»`} />
      <Lista titulo="La misma serie en otra dependencia" items={c.otra_dependencia}
             texto={(i) => `${i.codigo} ${i.nombre}: en el CCD «${i.en_ccd}», en la TRD «${i.en_trd}»`} />
      {(d.solo_en_ccd.length > 0 || d.solo_en_trd.length > 0 || d.nombre_distinto.length > 0) && (
        <p className="meta" style={{ marginBottom: 0 }}>
          {d.solo_en_ccd.length > 0 && <>Dependencias solo en el CCD: {d.solo_en_ccd.map((x) => `${x.codigo} ${x.nombre}`).join(", ")}. </>}
          {d.solo_en_trd.length > 0 && <>Solo en la TRD: {d.solo_en_trd.map((x) => `${x.codigo} ${x.nombre}`).join(", ")}. </>}
          {d.nombre_distinto.length > 0 && <>Con otro nombre: {d.nombre_distinto.map((x) => `${x.codigo} («${x.en_ccd}» / «${x.en_trd}»)`).join(", ")}.</>}
        </p>
      )}
      {c.diferencias > 0 && <p className="meta" style={{ marginBottom: 0 }}>Corrija la TRD en el paso 3 o pida a la
        entidad el CCD que corresponde, y vuelva a cotejar.</p>}
    </div>
  );
}

export function CotejoCcd({ versionId }: { versionId: string }) {
  const [c, setC] = useState<Cotejo | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { pedir<Cotejo | null>(`/api/trd/versiones/${versionId}/cotejo`).then(setC).catch(() => setC(null)); }, [versionId]);

  async function cotejar(archivo: File) {
    setError("");
    setOcupado(true);
    try {
      const datos = new FormData();
      datos.append("archivo", archivo, archivo.name);
      const vista = await subir<{ filas: unknown[]; origen: string; original?: { huella: string; archivo: string } }>(
        "/api/cuadro/vista-previa", datos, () => undefined);
      setC(await pedir<Cotejo>(`/api/trd/versiones/${versionId}/cotejo`, { method: "POST", body: JSON.stringify({
        filas: vista.filas, original: vista.original ? { ...vista.original, origen: vista.origen } : null }) }));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cotejar.");
    } finally {
      setOcupado(false);
    }
  }

  async function repetir() {
    setOcupado(true);
    setError("");
    try {
      setC(await pedir<Cotejo>(`/api/trd/versiones/${versionId}/cotejo/repetir`, { method: "POST" }));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cotejar.");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="tarjeta" style={{ marginTop: 10 }}>
      <div className="tarjeta-cab">Cotejar con el cuadro de clasificación (CCD)</div>
      <div className="tarjeta-cuerpo">
        {!c && <p className="meta" style={{ marginTop: 0 }}>Si la entidad entregó el CCD aparte, súbalo: el sistema revisa que
          toda serie del cuadro tenga su retención en la TRD y que la TRD no tenga series que el cuadro no trae.</p>}
        {error && <div className="aviso error" role="alert">{error}</div>}
        {c && <ResultadoCotejo c={c} />}
        <div className="acciones">
          <label className="boton chico">{ocupado ? "Cotejando…" : c ? "Cotejar con otro CCD" : "Subir el CCD"}
            <input type="file" accept=".xlsx,.xlsm,.pdf,.docx,.csv,.zip" hidden disabled={ocupado}
                   onChange={(e) => e.target.files?.[0] && cotejar(e.target.files[0])} /></label>
          {c && <button type="button" className="boton chico" disabled={ocupado} onClick={repetir}>Volver a cotejar</button>}
        </div>
      </div>
    </div>
  );
}
