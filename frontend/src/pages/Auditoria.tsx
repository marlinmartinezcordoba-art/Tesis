import { Fragment, useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ErrorAPI, pedir } from "@/lib/api";
import {
  MODULO_NOMBRE, MOTIVO_CIERRE, duracion, valor, type Cambio, type Consolidado, type Desglose, type Evento,
} from "@/lib/auditoria";
import { fecha } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";

const hora = new Intl.DateTimeFormat("es-CO", { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const soloHora = new Intl.DateTimeFormat("es-CO", { hour: "numeric", minute: "2-digit" });
const diaLargo = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

function Cambios({ cambios }: { cambios: Cambio[] }) {
  if (!cambios.length) return null;
  return (
    <div className="cambios">
      {cambios.map((c) => (
        <div key={c.campo} className="cambio">
          <span className="campo-cambio">{c.campo.replace(/_/g, " ")}</span>
          <del>{valor(c.antes)}</del>
          <span aria-hidden="true">→</span>
          <ins>{valor(c.despues)}</ins>
        </div>
      ))}
    </div>
  );
}

// --- Mi trazabilidad -----------------------------------------------------------------------------

function MiTrazabilidad() {
  const [acciones, setAcciones] = useState<{ accion: string; modulo: string; etiqueta: string }[]>([]);
  const [filtro, setFiltro] = useState({ accion: "", desde: "", hasta: "" });
  const [eventos, setEventos] = useState<Evento[] | null>(null);
  const [siguiente, setSiguiente] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    pedir<typeof acciones>("/api/auditoria/acciones").then(setAcciones).catch(() => undefined);
  }, []);

  const cargar = useCallback(async (antes?: number) => {
    const p = new URLSearchParams();
    Object.entries(filtro).forEach(([k, v]) => v && p.set(k, v));
    if (antes) p.set("antes_de", String(antes));
    try {
      const r = await pedir<{ eventos: Evento[]; siguiente: number | null }>(`/api/auditoria/mi-trazabilidad?${p}`);
      setEventos((prev) => (antes && prev ? [...prev, ...r.eventos] : r.eventos));
      setSiguiente(r.siguiente);
      setError("");
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar la trazabilidad.");
    }
  }, [filtro]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <>
      <h1>Mi trazabilidad</h1>
      <p className="sub">Todo lo que usted hizo en el sistema, en orden cronológico. Cada acción quedó registrada de forma
        permanente: nadie, ni la administración, puede modificarla ni borrarla.</p>
      <div className="filtros">
        <select className="selector" aria-label="Tipo de acción" value={filtro.accion}
                onChange={(e) => setFiltro({ ...filtro, accion: e.target.value })}>
          <option value="">Todas las acciones</option>
          {acciones.map((a) => <option key={`${a.modulo}-${a.accion}`} value={a.accion}>{MODULO_NOMBRE[a.modulo] || a.modulo} · {a.etiqueta}</option>)}
        </select>
        <label className="pastilla">Desde <input type="date" value={filtro.desde} onChange={(e) => setFiltro({ ...filtro, desde: e.target.value })} /></label>
        <label className="pastilla">Hasta <input type="date" value={filtro.hasta} onChange={(e) => setFiltro({ ...filtro, hasta: e.target.value })} /></label>
      </div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="tarjeta">
        <div className="tarjeta-cab">{eventos === null ? "Cargando…" : `${eventos.length}${siguiente ? "+" : ""} acción(es)`}</div>
        {eventos?.length === 0 && <div className="vacio">No hay acciones con esos filtros.</div>}
        {eventos?.map((e) => (
          <div className="fila" key={e.id} style={{ alignItems: "flex-start" }}>
            <span className={`punto-modulo m-${e.modulo}`} aria-hidden="true" />
            <div className="fila-principal">
              <div className="nombre">{e.etiqueta}</div>
              {e.detalle && <div className="meta">{e.detalle}</div>}
              <Cambios cambios={e.cambios} />
            </div>
            <div className="lado-derecho">
              <span className="insignia proceso">{MODULO_NOMBRE[e.modulo] || e.modulo}</span>
              <span className="meta">{fecha(e.fecha)}</span>
            </div>
          </div>
        ))}
        {siguiente && <div className="tarjeta-cuerpo"><button type="button" className="boton chico" onClick={() => cargar(siguiente)}>Ver más</button></div>}
      </div>
    </>
  );
}

// --- Panel consolidado --------------------------------------------------------------------------

function FilaPersona({ f, semana }: { f: Consolidado["filas"][number]; semana: string }) {
  const [abierta, setAbierta] = useState(false);
  const [desglose, setDesglose] = useState<Desglose | null>(null);

  async function alternar() {
    setAbierta(!abierta);
    if (!desglose) setDesglose(await pedir<Desglose>(`/api/auditoria/consolidado/${f.usuario_id}?semana=${semana}`).catch(() => null));
  }

  return (
    <>
      <tr className="fila-persona" onClick={alternar} aria-expanded={abierta}>
        <td>
          <button type="button" className="enlace" aria-label={`Ver sesiones de ${f.nombre}`}>{abierta ? "▾" : "▸"}</button>{" "}
          <strong>{f.nombre}</strong> <span className="insignia proceso">{f.rol_nombre}</span>
          {!f.activo && <span className="insignia alerta">Inactivo</span>}
        </td>
        <td className="numero">
          {f.dias_habiles_trabajados} de {f.dias_habiles}
          {f.dias_fin_de_semana > 0 && <span className="meta"> +{f.dias_fin_de_semana} fin de semana</span>}
        </td>
        <td className="numero">{duracion(f.segundos_conectado)}{f.en_curso && <span className="meta"> (en curso)</span>}</td>
        <td>
          <div className="insignias">
            {Object.entries(f.acciones).map(([g, n]) => <span key={g} className="insignia acento">{g} · {n}</span>)}
            {!Object.keys(f.acciones).length && <span className="meta">—</span>}
          </div>
        </td>
      </tr>
      {abierta && (
        <tr className="detalle-persona">
          <td colSpan={4}>
            {!desglose ? <span className="meta">Cargando…</span> : desglose.sesiones.length === 0 ? (
              <span className="meta">Sin sesiones esta semana.</span>
            ) : (
              <table className="tabla-permisos">
                <thead><tr><th>Inicio</th><th>Fin</th><th className="numero">Duración</th><th>Cierre</th><th>Acciones</th></tr></thead>
                <tbody>
                  {desglose.sesiones.map((s) => (
                    <tr key={s.sesion_id}>
                      <td>{hora.format(new Date(s.inicio))}</td>
                      <td>{s.en_curso ? "en curso" : soloHora.format(new Date(s.fin))}</td>
                      <td className="numero">{duracion(s.segundos)}</td>
                      <td className="meta">{s.motivo ? MOTIVO_CIERRE[s.motivo] || s.motivo : "—"}</td>
                      <td className="meta">{Object.entries(s.acciones).map(([g, n]) => `${g}: ${n}`).join(" · ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function PanelConsolidado() {
  const [semana, setSemana] = useState("");
  const [datos, setDatos] = useState<Consolidado | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setDatos(null);
    pedir<Consolidado>(`/api/auditoria/consolidado${semana ? `?semana=${semana}` : ""}`).then(setDatos)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar el panel."));
  }, [semana]);

  return (
    <>
      <h1>Panel consolidado semanal</h1>
      <p className="sub">Datos objetivos de conexión y de acciones registradas, por persona. No es una calificación ni un
        ranking. Horario de {datos?.semana.zona_horaria || "Bogotá"}.</p>
      <div className="filtros" style={{ alignItems: "center" }}>
        <button type="button" className="boton chico" disabled={!datos} onClick={() => datos && setSemana(datos.semana.anterior)}>‹ Semana anterior</button>
        <strong>{datos ? `${diaLargo.format(new Date(datos.semana.lunes))} – ${diaLargo.format(new Date(datos.semana.domingo))}` : "…"}</strong>
        <button type="button" className="boton chico" disabled={!datos?.semana.siguiente}
                onClick={() => datos?.semana.siguiente && setSemana(datos.semana.siguiente)}>Semana siguiente ›</button>
        <label className="pastilla">Ir a <input type="date" aria-label="Semana" onChange={(e) => e.target.value && setSemana(e.target.value)} /></label>
      </div>
      {error && <div className="aviso error">{error}</div>}
      <div className="tarjeta tabla-desplazable">
        <table className="tabla-permisos tabla-consolidado">
          <thead><tr><th>Persona</th><th className="numero">Días hábiles</th><th className="numero">Horas conectada</th><th>Acciones</th></tr></thead>
          <tbody>
            {!datos && <tr><td colSpan={4} className="meta">Cargando…</td></tr>}
            {datos?.filas.map((f) => <FilaPersona key={`${datos.semana.lunes}-${f.usuario_id}`} f={f} semana={datos.semana.lunes} />)}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function Auditoria() {
  const { usuario } = useSesion();
  const veTodo = !!usuario && (usuario.es_administrador || usuario.permisos?.auditoria === "todo");
  const [parametros, setParametros] = useSearchParams();
  const pestana = veTodo && parametros.get("vista") === "consolidado" ? "consolidado" : "propia";
  return (
    <>
      {veTodo && (
        <div className="pestanas" role="tablist">
          <button type="button" role="tab" aria-selected={pestana === "propia"} className={`pestana${pestana === "propia" ? " activa" : ""}`}
                  onClick={() => setParametros({})}>Mi trazabilidad</button>
          <button type="button" role="tab" aria-selected={pestana === "consolidado"}
                  className={`pestana${pestana === "consolidado" ? " activa" : ""}`}
                  onClick={() => setParametros({ vista: "consolidado" })}>Panel consolidado</button>
        </div>
      )}
      {pestana === "propia" ? <MiTrazabilidad /> : <PanelConsolidado />}
    </>
  );
}

// --- Trazabilidad por entidad -------------------------------------------------------------------

export function TrazabilidadEntidad() {
  const { tipo = "", id = "" } = useParams();
  const [parametros] = useSearchParams();
  const nombre = parametros.get("nombre") || id;
  const volver = parametros.get("volver");
  const [datos, setDatos] = useState<{ solo_propias: boolean; eventos: Evento[] } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    pedir<{ solo_propias: boolean; eventos: Evento[] }>(`/api/auditoria/entidad/${encodeURIComponent(id)}?tipo=${tipo}`)
      .then(setDatos).catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar la historia."));
  }, [tipo, id]);

  return (
    <>
      <nav className="migas" aria-label="Ubicación">
        {volver && volver.startsWith("/") ? <Link className="enlace" to={volver}>{nombre}</Link> : <span>{nombre}</span>}
        <span> › </span><strong>Historial de auditoría</strong>
      </nav>
      <h1>Historial de auditoría</h1>
      <p className="sub">{nombre}{datos?.solo_propias && " · Usted ve solo sus propias acciones sobre esta entidad."}</p>
      {error && <div className="aviso error">{error}</div>}
      <div className="tarjeta tabla-desplazable">
        <table className="tabla-permisos">
          <thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Antes → después</th></tr></thead>
          <tbody>
            {!datos && !error && <tr><td colSpan={4} className="meta">Cargando…</td></tr>}
            {datos?.eventos.length === 0 && <tr><td colSpan={4} className="meta">Sin eventos registrados.</td></tr>}
            {datos?.eventos.map((e) => (
              <Fragment key={e.id}>
                <tr>
                  <td style={{ whiteSpace: "nowrap" }}>{fecha(e.fecha)}</td>
                  <td>{e.usuario}</td>
                  <td>{e.etiqueta}{e.detalle && <div className="meta">{e.detalle}</div>}</td>
                  <td><Cambios cambios={e.cambios} />{!e.cambios.length && <span className="meta">—</span>}</td>
                </tr>
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
