// Tabla de Control de Acceso (TCA): la condición de acceso de cada serie y subserie, con su fundamento,
// vigencia, condiciones de consulta y quién autoriza. Se hereda a los expedientes y documentos de la serie.
import { FormEvent, useEffect, useState } from "react";
import { ErrorAPI, pedir } from "@/lib/api";
import { useSesion } from "@/lib/sesion";

interface Condicion {
  acceso: string; acceso_nombre: string; fundamento: string; reproduccion: string; vigente_hasta: string | null;
  condiciones: string | null; responsable: string | null; declarada_en: string | null;
}
interface Fila { id: string; nivel: string; codigo: string | null; titulo: string; propia: Condicion | null; heredada: Condicion | null; documentos: number }
interface Tabla { series: Fila[]; totales: { series: number; con_condicion: number; restringidas: number } }

const CLASE: Record<string, string> = { publico: "bien", clasificado: "alerta", reservado: "error" };
const fecha = (x: string | null) => (x ? new Date(`${x.slice(0, 10)}T00:00:00`).toLocaleDateString("es-CO") : "—");

function Formulario({ fila, fondoId, alGuardar, alCancelar }: { fila: Fila; fondoId: string; alGuardar: (t: Tabla) => void; alCancelar: () => void }) {
  const c = fila.propia;
  const [acceso, setAcceso] = useState(c?.acceso || "publico");
  const [fundamento, setFundamento] = useState(c?.fundamento || "Ley 1712 de 2014");
  const [hasta, setHasta] = useState(c?.vigente_hasta || "");
  const [reproduccion, setReproduccion] = useState(c?.reproduccion || "permitida");
  const [condiciones, setCondiciones] = useState(c?.condiciones || "");
  const [responsable, setResponsable] = useState(c?.responsable || "");
  const [error, setError] = useState("");
  async function guardar(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      alGuardar(await pedir<Tabla>(`/api/fondos/${fondoId}/tca/${fila.id}`, { method: "PUT", body: JSON.stringify({
        acceso, fundamento, reproduccion, vigente_hasta: acceso === "publico" ? null : hasta || null,
        condiciones: condiciones || null, responsable: responsable || null }) }));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo guardar.");
    }
  }
  return (
    <form onSubmit={guardar} className="tca-form">
      <div className="campo"><label htmlFor="tca-acceso">Categoría de acceso</label>
        <select id="tca-acceso" className="selector" value={acceso} onChange={(e) => setAcceso(e.target.value)}>
          <option value="publico">Pública</option><option value="clasificado">Clasificada (art. 18)</option>
          <option value="reservado">Reservada (art. 19)</option>
        </select></div>
      <div className="campo"><label htmlFor="tca-fund">Fundamento legal</label>
        <input id="tca-fund" className="entrada" required minLength={5} maxLength={500} value={fundamento} onChange={(e) => setFundamento(e.target.value)} /></div>
      {acceso !== "publico" && (
        <div className="campo"><label htmlFor="tca-hasta">Rige hasta <span className="meta">(obligatorio · máximo 15 años)</span></label>
          <input id="tca-hasta" type="date" className="entrada" required value={hasta} onChange={(e) => setHasta(e.target.value)} /></div>
      )}
      <div className="campo"><label htmlFor="tca-rep">Reproducción</label>
        <select id="tca-rep" className="selector" value={reproduccion} onChange={(e) => setReproduccion(e.target.value)}>
          <option value="permitida">Permitida</option><option value="condicionada">Condicionada</option><option value="no_permitida">No permitida</option>
        </select></div>
      <div className="campo"><label htmlFor="tca-cond">Condiciones de consulta</label>
        <input id="tca-cond" className="entrada" maxLength={500} value={condiciones} onChange={(e) => setCondiciones(e.target.value)}
               placeholder="Ej.: solo con autorización escrita, en sala" /></div>
      <div className="campo"><label htmlFor="tca-resp">Responsable de autorizar</label>
        <input id="tca-resp" className="entrada" maxLength={200} value={responsable} onChange={(e) => setResponsable(e.target.value)}
               placeholder="Cargo o dependencia" /></div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="acciones">
        <button type="submit" className="boton primario chico">Guardar</button>
        <button type="button" className="boton chico" onClick={alCancelar}>Cancelar</button>
      </div>
    </form>
  );
}

export function TablaControlAcceso({ fondoId }: { fondoId: string }) {
  const { usuario } = useSesion();
  const [tabla, setTabla] = useState<Tabla | null>(null);
  const [error, setError] = useState("");
  const [editando, setEditando] = useState<string | null>(null);
  useEffect(() => {
    pedir<Tabla>(`/api/fondos/${fondoId}/tca`).then(setTabla)
      .catch((e) => setError(e instanceof ErrorAPI ? e.message : "No se pudo cargar la TCA."));
  }, [fondoId]);

  return (
    <>
      <h1>Tabla de Control de Acceso (TCA)</h1>
      <p className="sub">La condición de acceso de cada serie y subserie. En RiC es una regla que rige la agrupación y se
        hereda a sus expedientes y documentos: el catálogo, el buscador, el grafo y los datos abiertos la aplican al rol de
        consulta. Cada cambio reemplaza a la condición anterior, que queda en el historial.</p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!tabla && !error && <div className="cargando">Cargando…</div>}
      {tabla && (
        <>
          <p className="meta">{tabla.totales.series} serie(s) y subserie(s) · {tabla.totales.con_condicion} con condición propia ·{" "}
            {tabla.totales.restringidas} restringida(s)</p>
          <div className="tarjeta tabla-desplazable">
            <table className="tabla-permisos">
              <thead><tr><th>Código</th><th>Serie o subserie</th><th>Acceso</th><th>Fundamento</th><th>Rige hasta</th>
                <th>Condiciones y responsable</th><th>Documentos</th>{usuario?.es_administrador && <th />}</tr></thead>
              <tbody>
                {tabla.series.map((f) => {
                  const c = f.propia || f.heredada;
                  return [
                    <tr key={f.id}>
                      <td>{f.codigo || "—"}</td>
                      <td>{f.titulo}</td>
                      <td>{c ? <span className={`insignia ${CLASE[c.acceso] || ""}`}>{c.acceso_nombre}</span> : <span className="meta">Sin declarar (pública)</span>}
                        {!f.propia && f.heredada && <div className="meta">heredada</div>}</td>
                      <td className="meta">{c?.fundamento || "—"}</td>
                      <td>{fecha(c?.vigente_hasta || null)}</td>
                      <td className="meta">{[c?.condiciones, c?.responsable && `Autoriza: ${c.responsable}`].filter(Boolean).join(" · ") || "—"}</td>
                      <td>{f.documentos}</td>
                      {usuario?.es_administrador && <td><button type="button" className="boton chico" onClick={() => setEditando(editando === f.id ? null : f.id)}>
                        {f.propia ? "Cambiar" : "Declarar"}</button></td>}
                    </tr>,
                    editando === f.id && (
                      <tr key={`${f.id}-form`}><td colSpan={8}>
                        <Formulario fila={f} fondoId={fondoId} alGuardar={(t) => { setTabla(t); setEditando(null); }} alCancelar={() => setEditando(null)} />
                      </td></tr>
                    ),
                  ];
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
