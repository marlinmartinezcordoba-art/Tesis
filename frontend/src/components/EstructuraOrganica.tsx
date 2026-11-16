// Estructura orgánica: cada dependencia del cuadro como agente RiC (rico:CorporateBody) que produce su
// agrupación (hasCreator), subordinado a la dependencia superior (hasOrHadSubordinate) y con su vigencia.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, pedir } from "@/lib/api";
import { useSesion } from "@/lib/sesion";
import { ParaQueSirve } from "@/components/ParaQueSirve";

interface Dep {
  id: string; nivel: string; codigo: string | null; titulo: string; superior_en_cuadro: string | null; provisional: boolean;
  agente: { id: string; nombre: string; vigencia: string | null; vigencia_legible: string | null } | null;
  subordinada_a: { id: string; nombre: string } | null;
}
interface Datos {
  entidad: { id: string; nombre: string } | null; dependencias: Dep[];
  totales: { dependencias: number; con_agente: number; subordinadas: number; con_vigencia: number; provisionales: number };
  resultado?: { creados: number; unidos: number; subordinados: number; omitidos: string[] };
}

function Vigencia({ fondoId, dep, alGuardar }: { fondoId: string; dep: Dep; alGuardar: (d: Datos) => void }) {
  const [valor, setValor] = useState(dep.agente?.vigencia || "");
  const [error, setError] = useState("");
  return (
    <form className="acciones" style={{ alignItems: "center" }} onSubmit={async (e) => {
      e.preventDefault();
      setError("");
      try {
        alGuardar(await pedir<Datos>(`/api/fondos/${fondoId}/estructura-organica/${dep.agente!.id}/vigencia`,
          { method: "PUT", body: JSON.stringify({ vigencia: valor }) }));
      } catch (err) { setError(err instanceof ErrorAPI ? err.message : "No se pudo guardar."); }
    }}>
      <input className="entrada" style={{ width: 130 }} value={valor} onChange={(e) => setValor(e.target.value)}
             placeholder="1950/1998" aria-label={`Vigencia de ${dep.titulo}`} />
      <button type="submit" className="boton chico">Guardar</button>
      {error && <span className="meta" role="alert" style={{ color: "var(--danger)" }}>{error}</span>}
    </form>
  );
}

export function EstructuraOrganica({ fondoId }: { fondoId: string }) {
  const { usuario } = useSesion();
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState("");
  const [trabajando, setTrabajando] = useState(false);
  useEffect(() => {
    pedir<Datos>(`/api/fondos/${fondoId}/estructura-organica`).then(setDatos)
      .catch((e) => setError(e instanceof ErrorAPI ? e.message : "No se pudo cargar."));
  }, [fondoId]);

  async function derivar() {
    setTrabajando(true);
    setError("");
    try {
      setDatos(await pedir<Datos>(`/api/fondos/${fondoId}/estructura-organica/derivar`, { method: "POST" }));
    } catch (e) {
      setError(e instanceof ErrorAPI ? e.message : "No se pudo derivar.");
    } finally {
      setTrabajando(false);
    }
  }

  const t = datos?.totales;
  return (
    <>
      <h1>Estructura orgánica</h1>
      <ParaQueSirve><p>Cada dependencia es un agente (rico:CorporateBody) que produce su agrupación del cuadro
        (rico:hasCreator) y está subordinado a la dependencia superior (rico:hasOrHadSubordinate), con su vigencia. Si una
        dependencia cambió de nombre, no se renombra: se registra en su ficha el nombre nuevo con su periodo o su sucesora.</p></ParaQueSirve>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!datos && !error && <div className="cargando">Cargando…</div>}
      {datos && t && (
        <>
          <p className="meta">{t.dependencias} dependencia(s) · {t.con_agente} con agente · {t.subordinadas} subordinada(s) ·
            {" "}{t.con_vigencia} con vigencia{t.provisionales ? ` · ${t.provisionales} con nombre provisional` : ""}
            {datos.entidad && <> · entidad: <Link to={`/vocabularios/${datos.entidad.id}`}>{datos.entidad.nombre}</Link></>}</p>
          {usuario?.es_administrador && (t.con_agente < t.dependencias - t.provisionales || t.subordinadas < t.con_agente) && (
            <div className="aviso" role="note">Faltan agentes o subordinaciones. RICORA los completa desde el cuadro sin inventar
              nombres (las de nombre provisional quedan para después).{" "}
              <button type="button" className="boton chico primario" disabled={trabajando} onClick={derivar}>
                {trabajando ? "Completando…" : "Completar la estructura desde el cuadro"}</button></div>
          )}
          {datos.resultado && (
            <div className="aviso bien" role="status">{datos.resultado.creados} agente(s) creados, {datos.resultado.unidos} unidos a
              su agrupación y {datos.resultado.subordinados} subordinación(es) registradas.
              {datos.resultado.omitidos.length > 0 && ` Sin agente por nombre provisional: ${datos.resultado.omitidos.join(", ")}.`}</div>
          )}
          <div className="tarjeta tabla-desplazable">
            <table className="tabla-permisos">
              <thead><tr><th>Código</th><th>Dependencia (agrupación)</th><th>Agente</th><th>Subordinada a</th><th>Vigencia</th></tr></thead>
              <tbody>
                {datos.dependencias.map((d) => (
                  <tr key={d.id}>
                    <td>{d.codigo || "—"}</td>
                    <td style={{ paddingLeft: d.nivel === "subseccion" ? 24 : undefined }}>{d.titulo}
                      {d.provisional && <span className="insignia alerta" style={{ marginLeft: 6 }}>Nombre provisional</span>}</td>
                    <td>{d.agente ? <Link to={`/vocabularios/${d.agente.id}`}>{d.agente.nombre}</Link> : <span className="meta">Sin agente</span>}</td>
                    <td>{d.subordinada_a?.nombre || <span className="meta">—</span>}</td>
                    <td>{d.agente && usuario?.es_administrador ? <Vigencia fondoId={fondoId} dep={d} alGuardar={setDatos} />
                      : d.agente?.vigencia_legible || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
