import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { ErrorAPI, pedir } from "@/lib/api";
import { useSesion } from "@/lib/sesion";
import { Ventana } from "@/components/Ventana";

// Disposición final: el calendario de retención (qué cumplió y qué manda la TRD) y el
// registro de lo ejecutado como rico:Activity. Nada se borra: lo eliminado sigue descrito.

interface Elemento {
  id: string; nivel: string; titulo: string; codigo: string | null; serie: string | null; fechas: string | null;
  regla: string | null; disposicion: string | null; disposicion_nombre: string | null; vence: string | null;
  cumplida: boolean; motivo: string | null;
  ejecutada: { actividad: { nombre: string }; tipo_nombre: string; fecha: string | null } | null;
}
interface Actividad { id: string; nombre: string; tipo_nombre: string; fecha: string | null; ejecutor: string | null;
  elementos: number; observaciones: string | null }

type Filtro = "cumplida" | "pendiente" | "ejecutada" | "todos";

function mensaje(err: unknown, por: string) {
  return err instanceof ErrorAPI ? err.message : por;
}

export function DisposicionFinal({ fondoId }: { fondoId: string }) {
  const esAdmin = !!useSesion().usuario?.es_administrador;
  const [elementos, setElementos] = useState<Elemento[] | null>(null);
  const [historial, setHistorial] = useState<Actividad[] | null>(null);
  const [filtro, setFiltro] = useState<Filtro>("cumplida");
  const [elegidos, setElegidos] = useState<Set<string>>(new Set());
  const [form, setForm] = useState(false);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");

  const cargar = useCallback(() => {
    pedir<Elemento[]>(`/api/disposicion/calendario?fondo_id=${fondoId}`).then(setElementos)
      .catch((err) => setError(mensaje(err, "No se pudo cargar.")));
    pedir<Actividad[]>(`/api/disposicion/historial?fondo_id=${fondoId}`).then(setHistorial).catch(() => setHistorial([]));
  }, [fondoId]);
  useEffect(cargar, [cargar]);

  const visibles = useMemo(() => (elementos || []).filter((e) => filtro === "todos"
    || (filtro === "cumplida" && e.cumplida) || (filtro === "ejecutada" && e.ejecutada)
    || (filtro === "pendiente" && !e.cumplida && !e.ejecutada)), [elementos, filtro]);
  const seleccion = (elementos || []).filter((e) => elegidos.has(e.id));
  const disposicion = seleccion[0]?.disposicion || null;
  const mezcla = new Set(seleccion.map((e) => e.disposicion)).size > 1;

  function alternar(e: Elemento) {
    const n = new Set(elegidos);
    if (n.has(e.id)) n.delete(e.id); else n.add(e.id);
    setElegidos(n);
  }

  const conteo = (f: Filtro) => (elementos || []).filter((e) => f === "todos" || (f === "cumplida" && e.cumplida)
    || (f === "ejecutada" && e.ejecutada) || (f === "pendiente" && !e.cumplida && !e.ejecutada)).length;

  return (
    <>
      <h1>Disposición final</h1>
      <p className="sub">
        El calendario de retención del fondo: cuándo cumple cada expediente su tiempo en archivo de gestión y central, y
        qué manda la TRD. Lo que se ejecuta queda registrado con su acta como una actividad de RiC (rico:Activity), con
        quién la ejecutó, la regla que la mandó y lo que afectó. Nada se borra: un expediente eliminado sigue descrito.
      </p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {aviso && <div className="aviso bien" role="status">{aviso}</div>}
      <div className="acciones" role="group" aria-label="Filtrar">
        {(["cumplida", "pendiente", "ejecutada", "todos"] as Filtro[]).map((f) => (
          <button key={f} type="button" className={`boton chico${filtro === f ? " primario" : ""}`} onClick={() => setFiltro(f)}>
            {{ cumplida: "Cumplieron su retención", pendiente: "En retención", ejecutada: "Ya dispuestos", todos: "Todos" }[f]}
            {" "}({conteo(f)})</button>
        ))}
        {esAdmin && (
          <button type="button" className="boton primario" disabled={!seleccion.length || mezcla || !disposicion}
                  title={mezcla ? "Elija expedientes con la misma disposición" : undefined} onClick={() => setForm(true)}>
            Registrar la disposición ({seleccion.length})</button>
        )}
      </div>
      {mezcla && <div className="aviso alerta">La selección mezcla disposiciones distintas: cada acta registra una.</div>}
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Calendario de retención</div>
        {!elementos ? <div className="cargando">Cargando…</div> : visibles.length === 0 ? (
          <p className="meta" style={{ padding: "0 18px" }}>Nada en este grupo.</p>
        ) : (
          <table className="tabla-permisos">
            <thead><tr>{esAdmin && <th />}<th>Expediente</th><th>Serie</th><th>Fechas</th><th>Retención (TRD)</th>
              <th>Cumple</th><th>Disposición</th></tr></thead>
            <tbody>
              {visibles.map((e) => (
                <tr key={e.id}>
                  {esAdmin && <td><input type="checkbox" aria-label={`Elegir ${e.titulo}`} disabled={!e.cumplida}
                                         checked={elegidos.has(e.id)} onChange={() => alternar(e)} /></td>}
                  <td>{e.codigo && <strong>{e.codigo} </strong>}{e.titulo}</td>
                  <td>{e.serie || "—"}</td>
                  <td>{e.fechas || <span className="meta">sin fechas</span>}</td>
                  <td className="meta">{e.regla || e.motivo || "Sin regla de retención"}</td>
                  <td>{e.vence || "—"}</td>
                  <td>{e.ejecutada
                    ? <span className="insignia acento" title={e.ejecutada.actividad.nombre}>{e.ejecutada.tipo_nombre} · {e.ejecutada.fecha}</span>
                    : e.disposicion_nombre || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Disposiciones ejecutadas</div>
        {!historial ? <div className="cargando">Cargando…</div> : historial.length === 0 ? (
          <p className="meta" style={{ padding: "0 18px" }}>Todavía no hay disposiciones registradas.</p>
        ) : (
          <table className="tabla-permisos">
            <thead><tr><th>Actividad (rico:Activity)</th><th>Fecha</th><th>Ejecutó</th><th>Elementos</th></tr></thead>
            <tbody>{historial.map((h) => (
              <tr key={h.id}><td>{h.nombre}{h.observaciones && <div className="meta">{h.observaciones}</div>}</td>
                <td>{h.fecha}</td><td>{h.ejecutor || "—"}</td><td>{h.elementos}</td></tr>
            ))}</tbody>
          </table>
        )}
      </div>
      {form && disposicion && (
        <Ventana titulo={`Registrar la disposición: ${seleccion[0].disposicion_nombre}`} alCerrar={() => setForm(false)}>
          <FormDisposicion fondoId={fondoId} disposicion={disposicion} recursos={seleccion.map((e) => e.id)}
                           alTerminar={(t) => { setForm(false); setElegidos(new Set()); setAviso(t); cargar(); }} />
        </Ventana>
      )}
    </>
  );
}

function FormDisposicion({ fondoId, disposicion, recursos, alTerminar }: { fondoId: string; disposicion: string;
  recursos: string[]; alTerminar: (texto: string) => void }) {
  const [d, setD] = useState({ acta_numero: "", acta_fecha: "", ejecutor: "", observaciones: "" });
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const poner = (k: keyof typeof d) => (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value });

  async function guardar(e: FormEvent) {
    e.preventDefault();
    setError("");
    setOcupado(true);
    try {
      const a = await pedir<Actividad>("/api/disposicion/ejecutar", { method: "POST", body: JSON.stringify({
        fondo_id: fondoId, recursos, disposicion, ...d, observaciones: d.observaciones.trim() || null }) });
      alTerminar(`Registrada: ${a.nombre} (${a.elementos} elemento(s)).`);
    } catch (err) {
      setError(mensaje(err, "No se pudo registrar."));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <form onSubmit={guardar}>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <p className="meta" style={{ marginTop: 0 }}>{recursos.length} elemento(s). Se registra como hecho: la descripción
        no se borra.</p>
      <div className="rejilla">
        <div className="campo">
          <label htmlFor="d-acta">Número del acta</label>
          <input id="d-acta" className="entrada" required value={d.acta_numero} onChange={poner("acta_numero")} />
        </div>
        <div className="campo">
          <label htmlFor="d-fecha">Fecha del acta</label>
          <input id="d-fecha" type="date" className="entrada" required value={d.acta_fecha} onChange={poner("acta_fecha")} />
        </div>
      </div>
      <div className="campo">
        <label htmlFor="d-ejecutor">Quién la ejecuta</label>
        <input id="d-ejecutor" className="entrada" required placeholder="Comité Institucional de Gestión y Desempeño"
               value={d.ejecutor} onChange={poner("ejecutor")} />
      </div>
      <div className="campo">
        <label htmlFor="d-obs">Observaciones</label>
        <textarea id="d-obs" className="entrada" rows={3} value={d.observaciones} onChange={poner("observaciones")} />
      </div>
      <div className="acciones"><button type="submit" className="boton primario" disabled={ocupado}>
        {ocupado ? "Registrando…" : "Registrar"}</button></div>
    </form>
  );
}
