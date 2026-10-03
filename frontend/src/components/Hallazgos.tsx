import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ErrorAPI, descargar, pedir } from "@/lib/api";
import { fecha } from "@/lib/formato";

// Hallazgos de conformidad con RiC (prompt de auditoría v7, §5bis): un
// registro que lleva una persona, no un analizador automático. Del
// hallazgo creado solo cambian el estado, la fecha de cierre y la acción.

type Estado = "abierto" | "en_correccion" | "cerrado";
interface Hallazgo {
  id: string; numero: number; titulo: string; descripcion: string; componentes: string[]; estado: Estado;
  estado_nombre: string; abierto_en: string; cerrado_en: string | null; accion: string | null;
}
interface Datos { hallazgos: Hallazgo[]; conteo: Record<Estado, number>; conteo_filtrado: Record<Estado, number> }

const ESTADO: Record<Estado, { texto: string; clase: string }> = {
  abierto: { texto: "Abierto", clase: "error" },
  en_correccion: { texto: "En corrección", clase: "alerta" },
  cerrado: { texto: "Cerrado", clase: "bien" },
};
const COMPONENTES: [string, string][] = [["autenticacion", "Autenticación"], ["ingesta", "Ingesta"],
  ["descripcion", "Descripción"], ["vocabularios", "Vocabularios"], ["instrumentos", "Instrumentos"],
  ["preservacion", "Preservación"], ["auditoria", "Auditoría"]];
const NOMBRE_COMPONENTE = Object.fromEntries(COMPONENTES);
const dia = (iso: string) => fecha(`${iso}T12:00:00`).split(",")[0];

export function Hallazgos() {
  const [estado, setEstado] = useState("");
  const [componente, setComponente] = useState("");
  const [datos, setDatos] = useState<Datos | null>(null);
  const [nuevo, setNuevo] = useState(false);
  const [error, setError] = useState("");

  const consulta = useCallback(() => {
    const p = new URLSearchParams();
    if (estado) p.set("estado", estado);
    if (componente) p.set("componente", componente);
    return p.toString();
  }, [estado, componente]);

  const cargar = useCallback(() => {
    pedir<Datos>(`/api/auditoria/hallazgos?${consulta()}`).then(setDatos)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudieron cargar los hallazgos."));
  }, [consulta]);
  useEffect(cargar, [cargar]);

  return (
    <>
      <h1>Hallazgos de conformidad</h1>
      <p className="sub">
        Brechas frente a Records in Contexts detectadas durante el desarrollo, y cómo se fueron cerrando. Lo lleva el equipo a
        mano: ningún proceso automático las detecta. Cada cambio queda en la auditoría.
      </p>
      <div className="filtros" style={{ alignItems: "center" }}>
        <select className="selector" aria-label="Estado" value={estado} onChange={(e) => setEstado(e.target.value)}>
          <option value="">Todos los estados</option>
          {Object.entries(ESTADO).map(([k, v]) => <option key={k} value={k}>{v.texto}</option>)}
        </select>
        <select className="selector" aria-label="Componente" value={componente} onChange={(e) => setComponente(e.target.value)}>
          <option value="">Todos los componentes</option>
          {COMPONENTES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <button type="button" className="boton chico" onClick={() => descargar(`/api/auditoria/hallazgos/hoja-de-calculo?${consulta()}`)
          .catch(() => undefined)}>Descargar hoja de cálculo</button>
        <button type="button" className="boton chico primario" onClick={() => setNuevo(true)}>Registrar hallazgo</button>
      </div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {datos && (
        <div className="resumen-preservacion">
          <div className="cifra error"><strong>{datos.conteo_filtrado.abierto}</strong><span>Abiertos</span></div>
          <div className="cifra alerta"><strong>{datos.conteo_filtrado.en_correccion}</strong><span>En corrección</span></div>
          <div className="cifra bien"><strong>{datos.conteo_filtrado.cerrado}</strong><span>Cerrados</span></div>
          <div className="cifra"><strong>{datos.hallazgos.length}</strong><span>Con estos filtros</span></div>
        </div>
      )}
      {nuevo && <NuevoHallazgo cerrar={() => setNuevo(false)} creado={() => { setNuevo(false); cargar(); }} />}
      {!datos ? <div className="cargando">Cargando…</div> : datos.hallazgos.length === 0
        ? <div className="vacio">Ningún hallazgo con estos filtros.</div>
        : datos.hallazgos.map((h) => <Tarjeta key={h.id} h={h} cambiado={cargar} />)}
    </>
  );
}

function Tarjeta({ h, cambiado }: { h: Hallazgo; cambiado: () => void }) {
  const [editando, setEditando] = useState(false);
  const [estado, setEstado] = useState<Estado>(h.estado);
  const [accion, setAccion] = useState(h.accion || "");
  const [error, setError] = useState("");

  async function guardar(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await pedir(`/api/auditoria/hallazgos/${h.id}`, { method: "PATCH", body: JSON.stringify({ estado, accion }) });
      setEditando(false);
      cambiado();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo guardar.");
    }
  }

  return (
    <div className="tarjeta">
      <div className="tarjeta-cab" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <span>Hallazgo {h.numero}</span>
        <span className={`insignia ${ESTADO[h.estado].clase}`}>{ESTADO[h.estado].texto}</span>
      </div>
      <div className="tarjeta-cuerpo">
        <h3 style={{ marginTop: 0 }}>{h.titulo}</h3>
        <p className="meta">
          {h.componentes.map((c) => NOMBRE_COMPONENTE[c] || c).join(" · ")} · abierto el {dia(h.abierto_en)}
          {h.cerrado_en && ` · cerrado el ${dia(h.cerrado_en)}`}
        </p>
        <p>{h.descripcion}</p>
        {editando ? (
          <form onSubmit={guardar}>
            <label className="meta" htmlFor={`estado-${h.id}`}>Estado</label>
            <select id={`estado-${h.id}`} className="selector" value={estado} onChange={(e) => setEstado(e.target.value as Estado)}>
              {Object.entries(ESTADO).map(([k, v]) => <option key={k} value={k}>{v.texto}</option>)}
            </select>
            <label className="meta" htmlFor={`accion-${h.id}`} style={{ display: "block", marginTop: 8 }}>Acción tomada o pendiente</label>
            <textarea id={`accion-${h.id}`} className="campo" rows={5} style={{ width: "100%" }} value={accion}
                      onChange={(e) => setAccion(e.target.value)} />
            {error && <div className="aviso error">{error}</div>}
            <div className="acciones">
              <button type="submit" className="boton chico primario">Guardar</button>
              <button type="button" className="boton chico" onClick={() => setEditando(false)}>Cancelar</button>
            </div>
          </form>
        ) : (
          <>
            <h4>Acción tomada o pendiente</h4>
            <p style={{ whiteSpace: "pre-wrap" }}>{h.accion || <span className="meta">Sin registrar.</span>}</p>
            <button type="button" className="boton chico" onClick={() => setEditando(true)}>Cambiar estado o acción</button>
          </>
        )}
      </div>
    </div>
  );
}

function NuevoHallazgo({ cerrar, creado }: { cerrar: () => void; creado: () => void }) {
  const [titulo, setTitulo] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [componentes, setComponentes] = useState<string[]>([]);
  const [accion, setAccion] = useState("");
  const [error, setError] = useState("");

  async function crear(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await pedir("/api/auditoria/hallazgos", { method: "POST", body: JSON.stringify({ titulo, descripcion, componentes,
        accion: accion || null }) });
      creado();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo registrar.");
    }
  }

  return (
    <form className="tarjeta" onSubmit={crear}>
      <div className="tarjeta-cab">Registrar hallazgo</div>
      <div className="tarjeta-cuerpo">
        <p className="meta">El título y la descripción no se pueden cambiar después: escríbalos como quedará en la historia.</p>
        <label className="meta" htmlFor="h-titulo">Título breve</label>
        <input id="h-titulo" className="campo" style={{ width: "100%" }} maxLength={300} required value={titulo}
               onChange={(e) => setTitulo(e.target.value)} />
        <label className="meta" htmlFor="h-desc" style={{ display: "block", marginTop: 8 }}>En qué consiste la brecha</label>
        <textarea id="h-desc" className="campo" rows={4} style={{ width: "100%" }} required value={descripcion}
                  onChange={(e) => setDescripcion(e.target.value)} />
        <fieldset style={{ border: 0, padding: 0, margin: "8px 0" }}>
          <legend className="meta">Componentes que afecta</legend>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
            {COMPONENTES.map(([k, v]) => (
              <label key={k} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input type="checkbox" checked={componentes.includes(k)}
                       onChange={(e) => setComponentes(e.target.checked ? [...componentes, k] : componentes.filter((c) => c !== k))} />
                {v}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="meta" htmlFor="h-accion">Acción prevista (opcional)</label>
        <textarea id="h-accion" className="campo" rows={3} style={{ width: "100%" }} value={accion}
                  onChange={(e) => setAccion(e.target.value)} />
        {error && <div className="aviso error">{error}</div>}
        <div className="acciones">
          <button type="submit" className="boton chico primario" disabled={!componentes.length}>Registrar</button>
          <button type="button" className="boton chico" onClick={cerrar}>Cancelar</button>
        </div>
      </div>
    </form>
  );
}
