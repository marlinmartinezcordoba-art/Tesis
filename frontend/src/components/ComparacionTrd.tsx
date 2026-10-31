import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, pedir } from "@/lib/api";

// Qué cambia entre dos versiones de la TRD y a qué registros afecta (fase B, requisito 7).
// Las series se comparan por su código compuesto; cada expediente se rige por la TRD vigente
// en su fecha final: los cerrados antes conservan la anterior, los abiertos pasan a la nueva.

interface Breve { codigo: string; nombre: string; dependencia: string }
interface Diferencia { campo: string; etiqueta: string; antes?: string | number; despues?: string | number;
  quitados?: string[]; agregados?: string[] }
interface Afectados {
  total: number; pasan_a_la_nueva: number; conservan_la_anterior: number; desde: string | null;
  series: { codigo: string; nombre: string; motivo: "cambia" | "se_retira"; total: number; pasan_a_la_nueva: number;
    conservan_la_anterior: number;
    registros: { id: string; titulo: string; nivel: string; fecha_final: string | null; rige: "nueva" | "anterior" }[] }[];
}
export interface Comparacion {
  comparable: boolean; explicacion?: string;
  anterior?: { id: string; nombre: string }; nueva?: { id: string; nombre: string };
  agregadas?: Breve[]; retiradas?: Breve[]; cambiadas?: (Breve & { diferencias: Diferencia[] })[]; sin_cambio?: number;
  dependencias_nuevas?: { codigo: string; nombre: string }[]; dependencias_retiradas?: { codigo: string; nombre: string }[];
  afectados?: Afectados;
}

export function ComparacionTrd({ versionId, con, abierta = false }: { versionId: string; con?: string | null; abierta?: boolean }) {
  const [c, setC] = useState<Comparacion | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setC(null);
    setError("");
    pedir<Comparacion>(`/api/trd/versiones/${versionId}/comparar${con ? `?con=${con}` : ""}`).then(setC)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo comparar."));
  }, [versionId, con]);

  if (error) return <div className="aviso error" role="alert">{error}</div>;
  if (!c) return <div className="meta">Comparando…</div>;
  if (!c.comparable) return <div className="meta">{c.explicacion}</div>;
  const af = c.afectados!;
  const nada = !c.agregadas!.length && !c.retiradas!.length && !c.cambiadas!.length;
  return (
    <details className="tarjeta comparacion-trd" open={abierta}>
      <summary>
        <strong>Qué cambia de la {c.anterior!.nombre} a la {c.nueva!.nombre}</strong>{" "}
        <span className="meta">
          {nada ? "Ninguna serie cambia." : [c.agregadas!.length && `${c.agregadas!.length} serie(s) nueva(s)`,
            c.retiradas!.length && `${c.retiradas!.length} retirada(s)`, c.cambiadas!.length && `${c.cambiadas!.length} cambiada(s)`,
            `${c.sin_cambio} igual(es)`].filter(Boolean).join(" · ")}
          {af.total > 0 && ` · ${af.total} registro(s) afectado(s)`}
        </span>
      </summary>
      <div className="tarjeta-cuerpo">
        {c.cambiadas!.length > 0 && (
          <>
            <h4>Series que cambian</h4>
            {c.cambiadas!.map((s) => (
              <div key={s.codigo} className="fila" style={{ display: "block", padding: "6px 0" }}>
                <div className="nombre">{s.codigo} {s.nombre} <span className="meta">· {s.dependencia}</span></div>
                <ul className="meta" style={{ margin: "2px 0 0" }}>
                  {s.diferencias.map((d) => (
                    <li key={d.campo}>{d.etiqueta}: {d.quitados || d.agregados
                      ? [d.agregados?.length && `se agrega ${d.agregados.join(", ")}`, d.quitados?.length && `se quita ${d.quitados.join(", ")}`]
                        .filter(Boolean).join("; ")
                      : <><s>{String(d.antes)}</s> → <strong>{String(d.despues)}</strong></>}</li>
                  ))}
                </ul>
              </div>
            ))}
          </>
        )}
        {c.agregadas!.length > 0 && (
          <><h4>Series nuevas</h4>
            <ul className="meta">{c.agregadas!.map((s) => <li key={s.codigo}>{s.codigo} {s.nombre} · {s.dependencia}</li>)}</ul></>
        )}
        {c.retiradas!.length > 0 && (
          <><h4>Series que se retiran</h4>
            <ul className="meta">{c.retiradas!.map((s) => <li key={s.codigo}>{s.codigo} {s.nombre} · {s.dependencia}</li>)}</ul></>
        )}
        {(c.dependencias_nuevas!.length > 0 || c.dependencias_retiradas!.length > 0) && (
          <p className="meta">
            {c.dependencias_nuevas!.length > 0 && <>Dependencias nuevas: {c.dependencias_nuevas!.map((d) => `${d.codigo} ${d.nombre}`).join(", ")}. </>}
            {c.dependencias_retiradas!.length > 0 && <>Dependencias que ya no aparecen: {c.dependencias_retiradas!.map((d) => `${d.codigo} ${d.nombre}`).join(", ")}.</>}
          </p>
        )}
        <h4>Registros afectados</h4>
        {af.total === 0 ? (
          <p className="meta">Ningún expediente ni documento descrito está en las series que cambian o se retiran.</p>
        ) : (
          <>
            <p className="meta">
              {af.total} registro(s) en series que cambian o se retiran. Cada uno se valora con la TRD vigente en su fecha
              final: <strong>{af.conservan_la_anterior}</strong> conservan la {c.anterior!.nombre} (cerrados antes
              {af.desde ? ` del ${af.desde}` : " de que rija la nueva"}) y <strong>{af.pasan_a_la_nueva}</strong> pasan a la
              {" "}{c.nueva!.nombre} (abiertos o cerrados después).
            </p>
            {af.series.map((s) => (
              <details key={s.codigo}>
                <summary>{s.codigo} {s.nombre} <span className="meta">· {s.motivo === "se_retira" ? "se retira" : "cambia"} ·
                  {" "}{s.total} registro(s): {s.pasan_a_la_nueva} pasan a la nueva, {s.conservan_la_anterior} conservan la anterior</span></summary>
                <ul className="meta">
                  {s.registros.map((r) => (
                    <li key={r.id}><Link to={`/descripcion/registro/${r.id}`}>{r.titulo}</Link>
                      {r.fecha_final ? ` · cerrado ${r.fecha_final}` : " · abierto"} · {r.rige === "nueva" ? "pasa a la nueva" : "conserva la anterior"}
                      {s.motivo === "se_retira" && r.rige === "nueva" && " · revise dónde se clasifica: su serie se retira"}</li>
                  ))}
                  {s.total > s.registros.length && <li>… y {s.total - s.registros.length} más.</li>}
                </ul>
              </details>
            ))}
          </>
        )}
      </div>
    </details>
  );
}
