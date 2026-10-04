import { Fragment, useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ErrorAPI, pedir } from "@/lib/api";
import {
  MODULO_NOMBRE, MOTIVO_CIERRE, duracion, valor, type Cambio, type Consolidado, type Desglose, type Evento,
  type PropiedadRico, type Revision,
} from "@/lib/auditoria";
import { Hallazgos } from "@/components/Hallazgos";
import { useSesion } from "@/lib/sesion";
import { AvisoReciente, ExportarExcel } from "@/components/HistorialReciente";
import { fecha } from "@/lib/formato";
import { useVista } from "@/components/Marco";

const hora = new Intl.DateTimeFormat("es-CO", { timeZone: "America/Bogota", weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const soloHora = new Intl.DateTimeFormat("es-CO", { timeZone: "America/Bogota", hour: "numeric", minute: "2-digit" });
const diaLargo = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

// La propiedad de RiC-O: verificada en monoespaciada; lo que no tiene
// propiedad confirmada, atenuado y en cursiva (prompt de auditoría v7, §10).
export function Rico({ p }: { p?: PropiedadRico | null }) {
  if (!p) return null;
  if (p.nombre) {
    return <code className="rico" title={p.codigo_cm ? `RiC-CM ${p.codigo_cm}` : "Verificada contra RiC-O 1.1"}>{p.nombre}</code>;
  }
  return (
    <em className="meta" title={p.estado === "sin_propiedad" ? "RiC-O no tiene propiedad para este dato; no se exporta."
      : "Texto libre sin propiedad de RiC-O verificada."}>
      {p.estado === "sin_propiedad" ? "sin propiedad en RiC-O" : "literal pendiente de confirmación"}
    </em>
  );
}

function Cambios({ cambios }: { cambios: Cambio[] }) {
  if (!cambios.length) return null;
  return (
    <div className="cambios">
      {cambios.map((c) => (
        <div key={c.campo} className="cambio">
          <span className="campo-cambio">{c.campo.replace(/_/g, " ")}{c.propiedad_rico && <> · <Rico p={c.propiedad_rico} /></>}</span>
          <del>{valor(c.antes)}</del>
          <span aria-hidden="true">→</span>
          <ins>{valor(c.despues)}</ins>
        </div>
      ))}
    </div>
  );
}

// --- Mi trazabilidad -----------------------------------------------------------------------------

// Cuántos registros se ven sin desplazarse; el resto se exporta.
const RECIENTES_TRAZABILIDAD = 15;
const RECIENTES_DECISIONES = 25;

function MiTrazabilidad() {
  const [acciones, setAcciones] = useState<{ accion: string; modulo: string; etiqueta: string }[]>([]);
  const [filtro, setFiltro] = useState({ accion: "", desde: "", hasta: "" });
  const [eventos, setEventos] = useState<Evento[] | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    pedir<typeof acciones>("/api/auditoria/acciones").then(setAcciones).catch(() => undefined);
  }, []);

  const consulta = useCallback(() => {
    const p = new URLSearchParams();
    Object.entries(filtro).forEach(([k, v]) => v && p.set(k, v));
    return p;
  }, [filtro]);

  const cargar = useCallback(async () => {
    const p = consulta();
    p.set("limite", String(RECIENTES_TRAZABILIDAD));
    try {
      const r = await pedir<{ eventos: Evento[]; total: number }>(`/api/auditoria/mi-trazabilidad?${p}`);
      setEventos(r.eventos);
      setTotal(r.total);
      setError("");
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar la trazabilidad.");
    }
  }, [consulta]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <>
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
        <ExportarExcel ruta={`/api/auditoria/trazabilidad/exportar?${consulta()}`} deshabilitado={!total} />
      </div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <AvisoReciente visibles={RECIENTES_TRAZABILIDAD} total={total} unidad="registros" />
      <div className="tarjeta">
        <div className="tarjeta-cab">{eventos === null ? "Cargando…" : `${total} acción(es) con estos filtros`}</div>
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

function RevisionSemana({ lunes, revisiones, alCambiar }: {
  lunes: string; revisiones: Revision[]; alCambiar: (r: Revision[]) => void;
}) {
  const [nota, setNota] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [cadena, setCadena] = useState<{ integra: boolean; eventos: number; roto_en: number | null;
                                         sello: { orden: number | null; huella: string | null } } | null>(null);
  useEffect(() => { pedir<typeof cadena>("/api/auditoria/cadena").then(setCadena).catch(() => undefined); }, [revisiones]);
  async function marcar() {
    setOcupado(true);
    try {
      const r = await pedir<{ revisiones: Revision[] }>("/api/auditoria/consolidado/revisado", {
        method: "POST", body: JSON.stringify({ semana: lunes, nota: nota.trim() || null }),
      });
      alCambiar(r.revisiones);
      setNota("");
    } finally { setOcupado(false); }
  }
  return (
    <div className="aviso proceso" role="status">
      {revisiones.length === 0
        ? "Nadie ha dejado constancia de revisar el registro de esta semana. "
        : `Revisada por ${revisiones.map((r) => `${r.por || "—"} (${new Date(r.fecha).toLocaleDateString("es-CO")})`).join(", ")}. `}
      La revisión periódica del registro es el nivel 4 de Control en NDSA.
      {cadena && (cadena.integra ? (
        <div style={{ marginTop: 6 }}>
          <span className="insignia bien">Cadena íntegra</span> {cadena.eventos} eventos encadenados. Sello actual:
          {" "}<code title="Anótelo o expórtelo fuera del sistema: si alguien rehace el registro, ya no coincidirá">
            n.º {cadena.sello.orden} · {cadena.sello.huella?.slice(0, 16)}…</code>
        </div>
      ) : (
        <div className="aviso error" role="alert" style={{ marginTop: 6 }}>
          La cadena de huellas del registro se rompe en el evento n.º {cadena.roto_en}: alguien alteró o quitó eventos
          por fuera del sistema. Conserve el respaldo y avise a la administración.
        </div>
      ))}
      <div className="filtros" style={{ marginTop: 8 }}>
        <input type="text" placeholder="Nota (opcional): qué se revisó o qué se encontró" value={nota} maxLength={1000}
               onChange={(e) => setNota(e.target.value)} aria-label="Nota de la revisión" style={{ flex: 1 }} />
        <button type="button" className="boton chico" disabled={ocupado} onClick={marcar}>Dejar constancia de revisión</button>
      </div>
    </div>
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
      <p className="sub">Por persona y por semana: días trabajados, horas conectada y cantidad de acciones. Son datos
        objetivos, no una calificación ni un ranking. Horario de {datos?.semana.zona_horaria || "Bogotá"}.</p>
      <div className="filtros" style={{ alignItems: "center" }}>
        <button type="button" className="boton chico" disabled={!datos} onClick={() => datos && setSemana(datos.semana.anterior)}>‹ Semana anterior</button>
        <strong>{datos ? `${diaLargo.format(new Date(datos.semana.lunes))} – ${diaLargo.format(new Date(datos.semana.domingo))}` : "…"}</strong>
        <button type="button" className="boton chico" disabled={!datos?.semana.siguiente}
                onClick={() => datos?.semana.siguiente && setSemana(datos.semana.siguiente)}>Semana siguiente ›</button>
        <label className="pastilla">Ir a <input type="date" aria-label="Semana" onChange={(e) => e.target.value && setSemana(e.target.value)} /></label>
        <ExportarExcel ruta={`/api/auditoria/panel-consolidado/exportar${datos ? `?semana=${datos.semana.lunes}` : ""}`} deshabilitado={!datos} />
      </div>
      {error && <div className="aviso error">{error}</div>}
      {datos && <RevisionSemana lunes={datos.semana.lunes} revisiones={datos.revisiones}
                                alCambiar={(revisiones) => setDatos({ ...datos, revisiones })} />}
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

// --- Decisiones de IA (solo administrador): fuente del capítulo de evaluación --------------------

interface Conteo {
  aceptada: number; corregida: number; rechazada: number; agregada: number; propuestas: number;
  pct_aceptadas: number | null; pct_corregidas: number | null; pct_rechazadas: number | null; pct_cobertura: number | null;
}
interface FilaDecision {
  id: number; fecha: string; documento: { id: string; titulo: string | null }; tipo: string; tipo_nombre: string;
  decision: "aceptada" | "corregida" | "rechazada" | "agregada"; propuesto: string | null; final: string | null;
  confianza: number | null; modelo: string | null; version_prompt: string | null; por: string | null;
  clase_rico: string | null; propiedad_rico: PropiedadRico | null; version_etiqueta: string | null;
}
interface DatosDecisiones {
  resumen: Conteo; por_tipo: (Conteo & { tipo_nombre: string })[]; modelos: string[]; versiones_prompt: string[];
  total: number; filas: FilaDecision[];
}

const DECISION: Record<FilaDecision["decision"], { texto: string; clase: string }> = {
  aceptada: { texto: "Aceptada", clase: "bien" },
  corregida: { texto: "Corregida", clase: "alerta" },
  rechazada: { texto: "Rechazada", clase: "error" },
  agregada: { texto: "Agregada por la archivista", clase: "proceso" },
};
const TIPOS_DECISION: [string, string][] = [["agente", "Agente"], ["lugar", "Lugar"], ["fecha", "Fecha"],
  ["forma_documental", "Forma documental"], ["actividad", "Actividad"], ["tipo_actividad", "Tipo de actividad"],
  ["mandato", "Mandato o norma"], ["titulo", "Título"], ["alcance", "Alcance y contenido"], ["idioma", "Idioma"]];

function hoyMenos(dias: number): string {
  const d = new Date();
  d.setDate(d.getDate() - dias);
  return d.toISOString().slice(0, 10);
}

function DecisionesIA() {
  const [tipo, setTipo] = useState("");
  const [decision, setDecision] = useState("");
  const [periodo, setPeriodo] = useState("todo");
  const [datos, setDatos] = useState<DatosDecisiones | null>(null);
  const [error, setError] = useState("");

  const consulta = useCallback(() => {
    const p = new URLSearchParams();
    if (tipo) p.set("tipo", tipo);
    if (decision) p.set("decision", decision);
    if (periodo !== "todo") p.set("desde", hoyMenos(Number(periodo)));
    return p.toString();
  }, [tipo, decision, periodo]);

  useEffect(() => {
    setError("");
    pedir<DatosDecisiones>(`/api/auditoria/decisiones-ia?${consulta()}&limite=${RECIENTES_DECISIONES}`).then(setDatos)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudieron cargar las decisiones."));
  }, [consulta]);

  const r = datos?.resumen;
  const pct = (x: number | null) => (x === null ? "—" : `${x} %`);
  return (
    <>
      <h1>Decisiones de validación asistida por inteligencia artificial</h1>
      <p className="sub">
        Visible solo para la administración. Cada propuesta del motor frente a lo que finalmente quedó confirmado, clasificada
        sola al publicar. Es la fuente de datos del capítulo de evaluación de la tesis.
      </p>
      <div className="filtros" style={{ alignItems: "center" }}>
        <select className="selector" aria-label="Tipo de entidad" value={tipo} onChange={(e) => setTipo(e.target.value)}>
          <option value="">Todos los tipos de entidad</option>
          {TIPOS_DECISION.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="selector" aria-label="Decisión" value={decision} onChange={(e) => setDecision(e.target.value)}>
          <option value="">Todas las decisiones</option>
          {Object.entries(DECISION).map(([k, v]) => <option key={k} value={k}>{v.texto}</option>)}
        </select>
        <select className="selector" aria-label="Periodo" value={periodo} onChange={(e) => setPeriodo(e.target.value)}>
          <option value="7">Últimos 7 días</option>
          <option value="30">Últimos 30 días</option>
          <option value="todo">Todo el registro</option>
        </select>
        <ExportarExcel ruta={`/api/auditoria/decisiones-ia/exportar?${consulta()}`} deshabilitado={!datos?.total} />
        {datos?.modelos.length ? <span className="insignia proceso">Motor de IA · {datos.modelos.join(", ")}</span> : null}
      </div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!datos || !r ? <div className="cargando">Cargando…</div> : (
        <>
          <div className="resumen-preservacion">
            <div className="cifra bien"><strong>{r.aceptada}</strong><span>Aceptadas · {pct(r.pct_aceptadas)}</span></div>
            <div className="cifra alerta"><strong>{r.corregida}</strong><span>Corregidas · {pct(r.pct_corregidas)}</span></div>
            <div className="cifra error"><strong>{r.rechazada}</strong><span>Rechazadas · {pct(r.pct_rechazadas)}</span></div>
            <div className="cifra"><strong>{r.propuestas}</strong><span>Propuestas evaluadas</span></div>
            <div className="cifra"><strong>{r.agregada}</strong><span>Agregadas por la archivista (el motor no las propuso)</span></div>
          </div>
          {datos.por_tipo.length > 1 && (
            <div className="tarjeta">
              <div className="tarjeta-cab">Por tipo de entidad</div>
              <div className="tabla-desplazable">
                <table className="tabla-permisos">
                  <thead><tr><th>Tipo</th><th>Propuestas</th><th>Aceptadas</th><th>Corregidas</th><th>Rechazadas</th>
                    <th>Agregadas</th><th title="De todo lo publicado, cuánto propuso el motor">Cobertura del motor</th></tr></thead>
                  <tbody>
                    {datos.por_tipo.map((t) => (
                      <tr key={t.tipo_nombre}>
                        <td>{t.tipo_nombre}</td><td>{t.propuestas}</td><td>{t.aceptada} ({pct(t.pct_aceptadas)})</td>
                        <td>{t.corregida} ({pct(t.pct_corregidas)})</td><td>{t.rechazada} ({pct(t.pct_rechazadas)})</td>
                        <td>{t.agregada}</td><td>{pct(t.pct_cobertura)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          <AvisoReciente visibles={datos.filas.length} total={datos.total} unidad="registros" />
          <div className="tarjeta">
            <div className="tarjeta-cab">Decisiones · {datos.total}</div>
            {datos.filas.length === 0 ? <div className="vacio">Todavía no hay decisiones registradas con estos filtros.</div> : (
              <div className="tabla-desplazable">
                <table className="tabla-permisos">
                  <thead><tr><th>Fecha</th><th>Documento</th><th>Entidad</th><th>Propuesto por el motor</th><th>Valor final</th>
                    <th>Decisión</th><th>Propiedad RiC-O</th><th>Versión de la instrucción</th></tr></thead>
                  <tbody>
                    {datos.filas.map((f) => (
                      <tr key={f.id}>
                        <td>{hora.format(new Date(f.fecha))}</td>
                        <td><Link to={`/descripcion/registro/${f.documento.id}`}>{f.documento.titulo || "Documento"}</Link></td>
                        <td>{f.tipo_nombre}{f.clase_rico && <div><code className="rico">{f.clase_rico}</code></div>}</td>
                        <td>{f.propuesto || <span className="meta">—</span>}</td>
                        <td>{f.final || <span className="meta">—</span>}</td>
                        <td><span className={`insignia ${DECISION[f.decision].clase}`}>{DECISION[f.decision].texto}</span></td>
                        <td><Rico p={f.propiedad_rico} /></td>
                        <td>{f.version_prompt ? <><code>{f.version_prompt}</code>{f.version_etiqueta && <span className="meta"> · {f.version_etiqueta}</span>}</> : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <VersionesInstruccion />
          <p className="meta">
            «Cobertura del motor» es la parte de lo publicado que el motor había propuesto. Estas cifras miden la aceptación de la
            archivista, que ve la propuesta antes de decidir; la evaluación frente a descripciones hechas sin ver la IA es otro
            procedimiento.
          </p>
        </>
      )}
    </>
  );
}

// Trazabilidad: una sola entrada con dos modos. «Mis acciones» es el
// registro de cada acción propia; «Equipo por semana» resume, por persona,
// días, horas y cantidad de acciones (solo para quien ve toda la auditoría).
function Trazabilidad() {
  const { usuario } = useSesion();
  const veTodo = !!usuario && (usuario.es_administrador || usuario.permisos?.auditoria === "todo");
  const [parametros] = useSearchParams();
  const equipo = veTodo && parametros.get("vista") === "consolidado";
  return (
    <>
      <div className="cabecera-nivel" style={{ marginBottom: 6 }}>
        <h1>Trazabilidad</h1>
        {veTodo && (
          <div className="segmentado" role="radiogroup" aria-label="Qué trazabilidad ver">
            <Link to="/auditoria" role="radio" aria-checked={!equipo} className={equipo ? "" : "elegido"}>Mis acciones</Link>
            <Link to="/auditoria?vista=consolidado" role="radio" aria-checked={equipo} className={equipo ? "elegido" : ""}>Equipo por semana</Link>
          </div>
        )}
      </div>
      {equipo ? <PanelConsolidado /> : <MiTrazabilidad />}
    </>
  );
}

export function Auditoria() {
  const pestana = useVista<"propia" | "decisiones" | "hallazgos">("/auditoria");
  return pestana === "propia" ? <Trazabilidad /> : pestana === "hallazgos" ? <Hallazgos /> : <DecisionesIA />;
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
          <thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Propiedad RiC-O</th><th>Antes → después</th></tr></thead>
          <tbody>
            {!datos && !error && <tr><td colSpan={5} className="meta">Cargando…</td></tr>}
            {datos?.eventos.length === 0 && <tr><td colSpan={5} className="meta">Sin eventos registrados.</td></tr>}
            {datos?.eventos.map((e) => (
              <Fragment key={e.id}>
                <tr>
                  <td style={{ whiteSpace: "nowrap" }}>{fecha(e.fecha)}</td>
                  <td>{e.usuario}</td>
                  <td>{e.etiqueta}{e.detalle && <div className="meta">{e.detalle}</div>}</td>
                  <td>{e.propiedad_rico ? <Rico p={e.propiedad_rico} /> : e.cambios.some((c) => c.propiedad_rico)
                    ? <span className="meta">por campo →</span> : <span className="meta">—</span>}</td>
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

// --- Versiones de la instrucción del motor ---------------------------------------------------------

interface Version { version: string; decisiones: number; primera: string | null; ultima: string | null; etiqueta: string | null; vigente: boolean }

function VersionesInstruccion() {
  const [versiones, setVersiones] = useState<Version[] | null>(null);
  const [editando, setEditando] = useState<string | null>(null);
  const [texto, setTexto] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    pedir<Version[]>("/api/auditoria/versiones-prompt").then(setVersiones).catch(() => setVersiones([]));
  }, []);

  async function guardar(version: string) {
    setError("");
    try {
      setVersiones(await pedir<Version[]>(`/api/auditoria/versiones-prompt/${version}`,
        { method: "PUT", body: JSON.stringify({ etiqueta: texto }) }));
      setEditando(null);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo guardar.");
    }
  }

  if (!versiones?.length) return null;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Versiones de la instrucción del motor</div>
      <div className="tarjeta-cuerpo">
        <p className="meta">
          El identificador se calcula solo a partir del texto de la instrucción (SHA-256): si la instrucción cambia en un solo
          carácter, cambia. La etiqueta es opcional y solo sirve para nombrarla; no reemplaza el identificador.
        </p>
        {error && <div className="aviso error">{error}</div>}
        <table className="tabla-permisos">
          <thead><tr><th>Identificador</th><th>Etiqueta</th><th>Decisiones</th><th>Usada</th><th /></tr></thead>
          <tbody>
            {versiones.map((v) => (
              <tr key={v.version}>
                <td><code>{v.version}</code>{v.vigente && <span className="insignia bien" style={{ marginLeft: 6 }}>vigente</span>}</td>
                <td>{editando === v.version ? (
                  <input className="campo" value={texto} maxLength={40} aria-label="Etiqueta" autoFocus
                         onChange={(e) => setTexto(e.target.value)} onKeyDown={(e) => e.key === "Enter" && guardar(v.version)} />
                ) : v.etiqueta || <span className="meta">—</span>}</td>
                <td>{v.decisiones}</td>
                <td className="meta">{v.primera ? `${fecha(v.primera)} – ${fecha(v.ultima as string)}` : "todavía no"}</td>
                <td>{editando === v.version
                  ? <><button type="button" className="boton chico primario" onClick={() => guardar(v.version)}>Guardar</button>{" "}
                    <button type="button" className="boton chico" onClick={() => setEditando(null)}>Cancelar</button></>
                  : <button type="button" className="boton chico" onClick={() => { setEditando(v.version); setTexto(v.etiqueta || ""); }}>
                    {v.etiqueta ? "Cambiar etiqueta" : "Ponerle etiqueta"}</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
