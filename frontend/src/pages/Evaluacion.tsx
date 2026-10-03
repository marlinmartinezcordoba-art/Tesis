import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ErrorAPI, descargar, pedir } from "@/lib/api";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";

// Evaluación ciega del motor frente a archivistas (objetivo 3 de la tesis).
// La archivista describe a ciegas (sin ver nunca la propuesta del motor),
// después con la propuesta delante (asistida) y por último la califica.
// El servidor impide describir a ciegas lo que ya se vio.

interface EvaluacionBreve {
  id: string; nombre: string; protocolo: string | null; estado: "preparacion" | "en_curso" | "cerrada";
  umbral_similitud: number; documentos: number; con_propuesta: number;
}
interface EstadoAnotacion { id: string; estado: "en_curso" | "enviada" | "anulada" }
interface Tarea {
  instanciacion_id: string; nombre: string; ciega: EstadoAnotacion | null; asistida: EstadoAnotacion | null;
  puede_ciega: boolean; calificado: boolean;
}
interface Entidad { tipo: string; valor: string; rol: string | null; edtf: string | null }
interface Datos { titulo?: string | null; alcance?: string | null; entidades: Entidad[] }
interface AnotacionAbierta {
  id: string; condicion: "ciega" | "asistida"; estado: string; datos: Datos;
  documento: { id: string; nombre: string; texto: string | null };
}

const ESTADO_EV: Record<EvaluacionBreve["estado"], { texto: string; clase: string }> = {
  preparacion: { texto: "En preparación", clase: "proceso" },
  en_curso: { texto: "En curso", clase: "alerta" },
  cerrada: { texto: "Cerrada", clase: "bien" },
};
const TIPOS: [string, string][] = [["agente", "Agente"], ["lugar", "Lugar"], ["fecha", "Fecha"], ["actividad", "Actividad"],
  ["tipo_actividad", "Tipo de actividad (función)"], ["mandato", "Mandato o norma"], ["forma_documental", "Forma documental"]];
const ROLES: [string, string][] = [["productor", "Productor"], ["remitente", "Remitente"], ["destinatario", "Destinatario"],
  ["mencionado", "Mencionado"], ["custodio", "Custodio"]];
const CRITERIOS: [string, string, string][] = [
  ["exactitud", "Exactitud", "Lo propuesto es cierto según el documento."],
  ["completitud", "Completitud", "No le falta nada importante."],
  ["pertinencia", "Pertinencia", "El contexto (agentes, funciones, fechas) es el que un archivista registraría."],
];

function mensaje(err: unknown, porDefecto: string) {
  return err instanceof ErrorAPI ? err.message : porDefecto;
}

export function EvaluacionCiega() {
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const esAdmin = !!usuario?.es_administrador;
  const [evaluaciones, setEvaluaciones] = useState<EvaluacionBreve[] | null>(null);
  const [abierta, setAbierta] = useState<string | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(() => {
    if (!fondo) return;
    pedir<EvaluacionBreve[]>(`/api/evaluacion?fondo_id=${fondo.id}`).then(setEvaluaciones)
      .catch((err) => setError(mensaje(err, "No se pudieron cargar las evaluaciones.")));
  }, [fondo]);
  useEffect(cargar, [cargar]);

  if (!fondo) return <div className="vacio">Primero debe existir un fondo.</div>;
  const actual = evaluaciones?.find((e) => e.id === abierta);
  return (
    <>
      <h1>Evaluación ciega</h1>
      <p className="sub">
        Mide la calidad del motor de análisis frente a archivistas: cada documento se describe primero a ciegas, sin ver
        nunca la propuesta del motor; después con ella delante; y al final se califica la propuesta. Es la evidencia del
        objetivo 3 de la tesis.
      </p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {actual ? (
        <DetalleEvaluacion ev={actual} esAdmin={esAdmin} volver={() => { setAbierta(null); cargar(); }} cambio={cargar} />
      ) : (
        <>
          {esAdmin && <NuevaEvaluacion fondoId={fondo.id} creada={cargar} />}
          {!evaluaciones ? <div className="cargando">Cargando…</div> : evaluaciones.length === 0 ? (
            <div className="tarjeta">
              <div className="tarjeta-cab">{esAdmin ? "Todavía no hay evaluaciones: así funciona el protocolo" : "No hay evaluaciones en curso: así funciona el protocolo"}</div>
              <ol className="pasos-inicio">
                <li><strong>Descripción a ciegas.</strong> La archivista describe cada documento sin ver nunca la propuesta del
                  motor: esa es la referencia humana independiente.</li>
                <li><strong>Descripción asistida.</strong> Después, el mismo documento con la propuesta del motor delante.</li>
                <li><strong>Calificación.</strong> Se ve la propuesta y se califica de 1 a 5 en exactitud, completitud y
                  pertinencia. Al cerrar, el sistema calcula precisión, exhaustividad y F1 frente a la descripción a ciegas, y
                  el acuerdo entre archivistas.</li>
              </ol>
              {esAdmin && <p className="pista" style={{ padding: "0 18px 14px", margin: 0 }}>Para empezar, cree una evaluación con el formulario de arriba y agregue los documentos.</p>}
            </div>
          ) : evaluaciones.map((e) => (
            <div key={e.id} className="fila">
              <div className="fila-principal">
                <div className="nombre">{e.nombre}</div>
                <div className="meta">{e.documentos} documento(s) · umbral de similitud {e.umbral_similitud}</div>
              </div>
              <span className={`insignia ${ESTADO_EV[e.estado].clase}`}>{ESTADO_EV[e.estado].texto}</span>
              <button type="button" className="boton chico" onClick={() => setAbierta(e.id)}>Abrir</button>
            </div>
          ))}
        </>
      )}
    </>
  );
}

function NuevaEvaluacion({ fondoId, creada }: { fondoId: string; creada: () => void }) {
  const [nombre, setNombre] = useState("");
  const [protocolo, setProtocolo] = useState("");
  const [umbral, setUmbral] = useState(0.85);
  const [error, setError] = useState("");
  async function crear(e: FormEvent) {
    e.preventDefault();
    try {
      await pedir("/api/evaluacion", { method: "POST", body: JSON.stringify({ fondo_id: fondoId, nombre, protocolo,
        umbral_similitud: umbral }) });
      setNombre("");
      setProtocolo("");
      creada();
    } catch (err) {
      setError(mensaje(err, "No se pudo crear."));
    }
  }
  return (
    <form className="tarjeta" onSubmit={crear}>
      <div className="tarjeta-cab">Nueva evaluación</div>
      <div className="tarjeta-cuerpo">
        <label className="meta" htmlFor="ev-nombre">Nombre</label>
        <input id="ev-nombre" className="campo" style={{ width: "100%" }} required minLength={3} value={nombre}
               onChange={(e) => setNombre(e.target.value)} />
        <label className="meta" htmlFor="ev-protocolo" style={{ display: "block", marginTop: 8 }}>
          Protocolo (quiénes describen, instrucciones, criterios)</label>
        <textarea id="ev-protocolo" className="campo" rows={3} style={{ width: "100%" }} value={protocolo}
                  onChange={(e) => setProtocolo(e.target.value)} />
        <label className="meta" htmlFor="ev-umbral" style={{ display: "block", marginTop: 8 }}>
          Umbral de similitud para la medida flexible (1 = solo valores iguales)</label>
        <input id="ev-umbral" className="campo" type="number" min={0.5} max={1} step={0.05} value={umbral}
               onChange={(e) => setUmbral(Number(e.target.value))} />
        {error && <div className="aviso error">{error}</div>}
        <div className="acciones"><button type="submit" className="boton chico primario">Crear</button></div>
      </div>
    </form>
  );
}

function DetalleEvaluacion({ ev, esAdmin, volver, cambio }: { ev: EvaluacionBreve; esAdmin: boolean; volver: () => void;
  cambio: () => void }) {
  const [tareas, setTareas] = useState<Tarea[] | null>(null);
  const [anotacion, setAnotacion] = useState<AnotacionAbierta | null>(null);
  const [calificando, setCalificando] = useState<string | null>(null);
  const [verResultados, setVerResultados] = useState(false);
  const [error, setError] = useState("");

  const cargar = useCallback(() => {
    pedir<{ tareas: Tarea[] }>(`/api/evaluacion/${ev.id}/tareas`).then((r) => setTareas(r.tareas))
      .catch((err) => setError(mensaje(err, "No se pudieron cargar las tareas.")));
  }, [ev.id]);
  useEffect(cargar, [cargar]);

  async function abrir(inst: string, condicion: "ciega" | "asistida") {
    setError("");
    try {
      setAnotacion(await pedir<AnotacionAbierta>(`/api/evaluacion/${ev.id}/documentos/${inst}/anotar`,
        { method: "POST", body: JSON.stringify({ condicion }) }));
    } catch (err) {
      setError(mensaje(err, "No se pudo abrir."));
    }
  }

  if (anotacion) {
    return <FormularioAnotacion a={anotacion} cerrar={() => { setAnotacion(null); cargar(); }} />;
  }
  if (calificando) {
    return <Rubrica evId={ev.id} inst={calificando} cerrar={() => { setCalificando(null); cargar(); }} />;
  }
  if (verResultados) {
    return <Resultados evId={ev.id} volver={() => setVerResultados(false)} />;
  }
  return (
    <>
      <button type="button" className="boton chico" onClick={volver}>← Evaluaciones</button>
      <h2>{ev.nombre} <span className={`insignia ${ESTADO_EV[ev.estado].clase}`}>{ESTADO_EV[ev.estado].texto}</span></h2>
      {ev.protocolo && <p className="meta" style={{ whiteSpace: "pre-wrap" }}>{ev.protocolo}</p>}
      {error && <div className="aviso error" role="alert">{error}</div>}
      {esAdmin && <Administracion ev={ev} cambio={() => { cambio(); cargar(); }} resultados={() => setVerResultados(true)} />}
      {ev.estado === "en_curso" && (
        <div className="tarjeta">
          <div className="tarjeta-cab">Mis tareas</div>
          <div className="tarjeta-cuerpo">
            <p className="meta">
              El orden importa: primero a ciegas, luego asistida, luego calificar. Una vez vista la propuesta del motor, ese
              documento ya no se puede describir a ciegas.
            </p>
            {!tareas ? <div className="cargando">Cargando…</div> : tareas.map((t) => (
              <div key={t.instanciacion_id} className="fila" style={{ flexWrap: "wrap", gap: 8 }}>
                <div className="fila-principal"><div className="nombre">{t.nombre}</div></div>
                <button type="button" className="boton chico" disabled={!t.puede_ciega || t.ciega?.estado === "enviada"}
                        title={!t.puede_ciega ? "Ya vio la propuesta de este documento" : undefined}
                        onClick={() => abrir(t.instanciacion_id, "ciega")}>
                  {t.ciega?.estado === "enviada" ? "A ciegas ✓" : !t.puede_ciega ? "A ciegas (no disponible)" : "Describir a ciegas"}
                </button>
                <button type="button" className="boton chico" disabled={t.asistida?.estado === "enviada" || t.ciega?.estado === "en_curso"}
                        onClick={() => abrir(t.instanciacion_id, "asistida")}>
                  {t.asistida?.estado === "enviada" ? "Asistida ✓" : "Describir con la propuesta"}
                </button>
                <button type="button" className="boton chico" disabled={t.ciega?.estado === "en_curso"}
                        onClick={() => setCalificando(t.instanciacion_id)}>
                  {t.calificado ? "Calificada ✓ (cambiar)" : "Calificar la propuesta"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function Administracion({ ev, cambio, resultados }: { ev: EvaluacionBreve; cambio: () => void; resultados: () => void }) {
  const { fondo } = useFondo();
  const [cola, setCola] = useState<{ id: string; nombre: string }[]>([]);
  const [elegidos, setElegidos] = useState<string[]>([]);
  const [aviso, setAviso] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    if (ev.estado === "preparacion" && fondo) {
      pedir<{ id: string; nombre: string }[]>(`/api/descripcion/cola?fondo_id=${fondo.id}`).then(setCola).catch(() => setCola([]));
    }
  }, [ev.estado, fondo]);

  async function accion(ruta: string, cuerpo?: object) {
    setOcupado(true);
    setAviso("");
    try {
      const r = await pedir<{ generadas?: number; avisos?: string[] }>(`/api/evaluacion/${ev.id}/${ruta}`,
        { method: "POST", body: cuerpo ? JSON.stringify(cuerpo) : undefined });
      if (r.generadas !== undefined) {
        setAviso(`${r.generadas} propuesta(s) generadas, sin mostrarlas.${r.avisos?.length ? ` ${r.avisos.join(" · ")}` : ""}`);
      }
      setElegidos([]);
      cambio();
    } catch (err) {
      setAviso(mensaje(err, "No se pudo."));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Administración</div>
      <div className="tarjeta-cuerpo">
        <p>{ev.documentos} documento(s) · {ev.con_propuesta} con propuesta del motor</p>
        {aviso && <div className="aviso">{aviso}</div>}
        {ev.estado === "preparacion" && (
          <>
            <p className="meta">Solo documentos aún sin describir: si ya lo estuvieran, el vocabulario del fondo le daría la
              respuesta al motor.</p>
            <div style={{ maxHeight: 220, overflow: "auto" }}>
              {cola.map((d) => (
                <label key={d.id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input type="checkbox" checked={elegidos.includes(d.id)}
                         onChange={(e) => setElegidos(e.target.checked ? [...elegidos, d.id] : elegidos.filter((x) => x !== d.id))} />
                  {d.nombre}
                </label>
              ))}
              {cola.length === 0 && <div className="meta">No hay documentos listos sin describir.</div>}
            </div>
            <div className="acciones">
              <button type="button" className="boton chico" disabled={!elegidos.length || ocupado}
                      onClick={() => accion("documentos", { instanciacion_ids: elegidos })}>Agregar {elegidos.length || ""}</button>
              <button type="button" className="boton chico" disabled={!ev.documentos || ocupado}
                      onClick={() => accion("propuestas")}>{ocupado ? "Trabajando…" : "Generar las propuestas del motor"}</button>
              <button type="button" className="boton chico primario" disabled={!ev.documentos || ev.con_propuesta < ev.documentos || ocupado}
                      onClick={() => accion("estado", { estado: "en_curso" })}>Iniciar la evaluación</button>
            </div>
          </>
        )}
        {ev.estado !== "preparacion" && (
          <div className="acciones">
            {ev.estado === "en_curso" && (
              <button type="button" className="boton chico" disabled={ocupado}
                      onClick={() => accion("estado", { estado: "cerrada" })}>Cerrar la evaluación</button>
            )}
            <button type="button" className="boton chico primario" onClick={resultados}>Ver resultados</button>
          </div>
        )}
        <p className="meta">Ver los resultados muestra las propuestas: desde ahí, usted no puede describir a ciegas estos documentos.</p>
      </div>
    </div>
  );
}

function FormularioAnotacion({ a, cerrar }: { a: AnotacionAbierta; cerrar: () => void }) {
  const [datos, setDatos] = useState<Datos>({ titulo: a.datos.titulo || "", alcance: a.datos.alcance || "",
    entidades: a.datos.entidades || [] });
  const [error, setError] = useState("");
  const soloLectura = a.estado !== "en_curso";

  function cambiar(i: number, campo: keyof Entidad, valor: string) {
    setDatos({ ...datos, entidades: datos.entidades.map((e, j) => (j === i ? { ...e, [campo]: valor || null } : e)) });
  }

  async function guardar(enviar: boolean) {
    setError("");
    try {
      await pedir(`/api/evaluacion/anotaciones/${a.id}`, { method: "PUT", body: JSON.stringify({ ...datos, enviar }) });
      cerrar();
    } catch (err) {
      setError(mensaje(err, "No se pudo guardar."));
    }
  }

  return (
    <>
      <button type="button" className="boton chico" onClick={cerrar}>← Volver sin guardar</button>
      <h2>{a.documento.nombre} · {a.condicion === "ciega" ? "a ciegas" : "con la propuesta del motor"}</h2>
      {a.condicion === "ciega" && (
        <div className="aviso">Describa solo a partir del documento. El tiempo se mide desde que lo abrió hasta que lo envía.</div>
      )}
      <div className="evaluacion-columnas">
        <div className="tarjeta"><div className="tarjeta-cab">Documento</div>
          <div className="tarjeta-cuerpo" style={{ whiteSpace: "pre-wrap", maxHeight: 520, overflow: "auto" }}>
            {a.documento.texto || <span className="meta">Sin texto extraído.</span>}</div></div>
        <div className="tarjeta"><div className="tarjeta-cab">Descripción</div>
          <div className="tarjeta-cuerpo">
            <label className="meta" htmlFor="an-titulo">Título</label>
            <input id="an-titulo" className="campo" style={{ width: "100%" }} disabled={soloLectura} value={datos.titulo || ""}
                   onChange={(e) => setDatos({ ...datos, titulo: e.target.value })} />
            <label className="meta" htmlFor="an-alcance" style={{ display: "block", marginTop: 8 }}>Alcance y contenido</label>
            <textarea id="an-alcance" className="campo" rows={3} style={{ width: "100%" }} disabled={soloLectura}
                      value={datos.alcance || ""} onChange={(e) => setDatos({ ...datos, alcance: e.target.value })} />
            <h4>Entidades</h4>
            {datos.entidades.map((e, i) => (
              <div key={i} style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 6 }}>
                <select className="selector" aria-label="Tipo" disabled={soloLectura} value={e.tipo}
                        onChange={(x) => cambiar(i, "tipo", x.target.value)}>
                  {TIPOS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <input className="campo" aria-label="Valor" placeholder="Valor" disabled={soloLectura} value={e.valor}
                       onChange={(x) => cambiar(i, "valor", x.target.value)} style={{ flex: "1 1 160px" }} />
                {e.tipo === "agente" && (
                  <select className="selector" aria-label="Rol" disabled={soloLectura} value={e.rol || ""}
                          onChange={(x) => cambiar(i, "rol", x.target.value)}>
                    <option value="">Rol…</option>
                    {ROLES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                )}
                {e.tipo === "fecha" && (
                  <input className="campo" aria-label="EDTF" placeholder="EDTF (1948-03, 1948~…)" disabled={soloLectura}
                         value={e.edtf || ""} onChange={(x) => cambiar(i, "edtf", x.target.value)} style={{ width: 150 }} />
                )}
                {!soloLectura && (
                  <button type="button" className="boton chico" aria-label="Quitar"
                          onClick={() => setDatos({ ...datos, entidades: datos.entidades.filter((_, j) => j !== i) })}>×</button>
                )}
              </div>
            ))}
            {!soloLectura && (
              <button type="button" className="boton chico" onClick={() => setDatos({ ...datos,
                entidades: [...datos.entidades, { tipo: "agente", valor: "", rol: null, edtf: null }] })}>+ Entidad</button>
            )}
            {error && <div className="aviso error">{error}</div>}
            {!soloLectura && (
              <div className="acciones">
                <button type="button" className="boton chico" onClick={() => guardar(false)}>Guardar borrador</button>
                <button type="button" className="boton chico primario" onClick={() => guardar(true)}>Enviar</button>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function Rubrica({ evId, inst, cerrar }: { evId: string; inst: string; cerrar: () => void }) {
  const [propuesta, setPropuesta] = useState<Datos | null>(null);
  const [notas, setNotas] = useState<Record<string, number>>({});
  const [error, setError] = useState("");
  const [confirmado, setConfirmado] = useState(false);

  async function ver() {
    try {
      setPropuesta(await pedir<Datos>(`/api/evaluacion/${evId}/documentos/${inst}/propuesta`, { method: "POST" }));
    } catch (err) {
      setError(mensaje(err, "No se pudo abrir la propuesta."));
    }
  }

  async function guardar() {
    try {
      await pedir(`/api/evaluacion/${evId}/documentos/${inst}/calificacion`, { method: "PUT", body: JSON.stringify(notas) });
      cerrar();
    } catch (err) {
      setError(mensaje(err, "No se pudo guardar."));
    }
  }

  return (
    <>
      <button type="button" className="boton chico" onClick={cerrar}>← Volver</button>
      <h2>Calificar la propuesta del motor</h2>
      {error && <div className="aviso error">{error}</div>}
      {!propuesta ? (
        <div className="tarjeta"><div className="tarjeta-cuerpo">
          <p>Para calificarla hay que verla. <strong>Después, este documento ya no se puede describir a ciegas.</strong></p>
          <label style={{ display: "flex", gap: 8 }}>
            <input type="checkbox" checked={confirmado} onChange={(e) => setConfirmado(e.target.checked)} />
            Entiendo; ya describí este documento a ciegas o no lo voy a hacer.
          </label>
          <div className="acciones"><button type="button" className="boton chico primario" disabled={!confirmado} onClick={ver}>
            Ver la propuesta</button></div>
        </div></div>
      ) : (
        <div className="tarjeta"><div className="tarjeta-cuerpo">
          <p><strong>{propuesta.titulo}</strong></p>
          {propuesta.alcance && <p>{propuesta.alcance}</p>}
          <ul>{propuesta.entidades.map((e, i) => <li key={i}>{TIPOS.find(([k]) => k === e.tipo)?.[1]}: {e.valor}
            {e.rol && ` · ${e.rol}`}{e.edtf && ` · ${e.edtf}`}</li>)}</ul>
          {CRITERIOS.map(([k, nombre, pista]) => (
            <fieldset key={k} style={{ border: 0, padding: 0, margin: "10px 0" }}>
              <legend><strong>{nombre}</strong> <span className="meta">{pista}</span></legend>
              <div style={{ display: "flex", gap: 12 }}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <label key={n} style={{ display: "flex", gap: 4 }}>
                    <input type="radio" name={k} checked={notas[k] === n} onChange={() => setNotas({ ...notas, [k]: n })} />{n}
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
          <div className="acciones"><button type="button" className="boton chico primario" disabled={Object.keys(notas).length < 3}
                                            onClick={guardar}>Guardar calificación</button></div>
        </div></div>
      )}
    </>
  );
}

interface Medida { vp: number; fp: number; fn: number; precision: number | null; exhaustividad: number | null; f1: number | null }
interface Resultado {
  umbral: number; motores: { motor: string; version_prompt: string }[];
  estricto: { por_tipo: Record<string, Medida>; micro: Medida; macro_f1: number | null };
  flexible: { por_tipo: Record<string, Medida>; micro: Medida; macro_f1: number | null };
  acuerdo_entre_archivistas: Medida | null;
  tiempos: Record<string, { n: number; mediana_minutos: number | null; media_minutos: number | null }>;
  rubrica: Record<string, { n: number; media: number | null; pares: number; kappa_ponderado: number | null }>;
  documentos: { instanciacion_id: string; nombre: string; entidades_motor: number; referencias_ciegas: number;
    f1_flexible: number | null; descrito_durante_la_evaluacion: boolean }[];
  anotaciones: { ciegas: number; asistidas: number; evaluadores: number };
}

const num = (x: number | null | undefined, d = 2) => (x === null || x === undefined ? "—" : x.toLocaleString("es-CO", { maximumFractionDigits: d }));

function Resultados({ evId, volver }: { evId: string; volver: () => void }) {
  const [r, setR] = useState<Resultado | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    pedir<Resultado>(`/api/evaluacion/${evId}/resultados`).then(setR).catch((err) => setError(mensaje(err, "No se pudieron calcular.")));
  }, [evId]);
  if (error) return <><button type="button" className="boton chico" onClick={volver}>← Volver</button><div className="aviso error">{error}</div></>;
  if (!r) return <div className="cargando">Calculando…</div>;
  const tipos = Array.from(new Set([...Object.keys(r.estricto.por_tipo), ...Object.keys(r.flexible.por_tipo)]));
  return (
    <>
      <button type="button" className="boton chico" onClick={volver}>← Volver</button>
      <h2>Resultados</h2>
      <p className="meta">
        {r.anotaciones.ciegas} descripción(es) ciega(s) y {r.anotaciones.asistidas} asistida(s) de {r.anotaciones.evaluadores} persona(s).
        Motor: {r.motores.map((m) => `${m.motor} · instrucción ${m.version_prompt}`).join("; ") || "—"}.
      </p>
      <div className="acciones">
        <button type="button" className="boton chico" onClick={() => descargar(`/api/evaluacion/${evId}/resultados/hoja-de-calculo`).catch(() => undefined)}>
          Descargar hoja de cálculo</button>
      </div>
      <div className="resumen-preservacion">
        <div className="cifra"><strong>{num(r.estricto.micro.f1)}</strong><span>F1 estricto (micro)</span></div>
        <div className="cifra"><strong>{num(r.flexible.micro.f1)}</strong><span>F1 flexible (umbral {r.umbral})</span></div>
        <div className="cifra"><strong>{num(r.acuerdo_entre_archivistas?.f1)}</strong><span>Acuerdo entre archivistas (F1)</span></div>
        <div className="cifra"><strong>{num(r.tiempos.ciega?.mediana_minutos, 1)} / {num(r.tiempos.asistida?.mediana_minutos, 1)}</strong>
          <span>Minutos por documento: a ciegas / asistida (mediana)</span></div>
      </div>
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Entidades del motor frente a las descripciones ciegas</div>
        <table className="tabla-permisos">
          <thead><tr><th>Tipo</th><th>P estricta</th><th>E estricta</th><th>F1 estricto</th><th>P flexible</th><th>E flexible</th>
            <th>F1 flexible</th><th>VP / FP / FN (flexible)</th></tr></thead>
          <tbody>
            {tipos.map((t) => {
              const e = r.estricto.por_tipo[t];
              const f = r.flexible.por_tipo[t];
              return (
                <tr key={t}><td>{TIPOS.find(([k]) => k === t)?.[1] || t}</td>
                  <td>{num(e?.precision)}</td><td>{num(e?.exhaustividad)}</td><td>{num(e?.f1)}</td>
                  <td>{num(f?.precision)}</td><td>{num(f?.exhaustividad)}</td><td>{num(f?.f1)}</td>
                  <td>{f ? `${f.vp} / ${f.fp} / ${f.fn}` : "—"}</td></tr>
              );
            })}
            <tr><td><strong>Total (micro)</strong></td><td>{num(r.estricto.micro.precision)}</td><td>{num(r.estricto.micro.exhaustividad)}</td>
              <td>{num(r.estricto.micro.f1)}</td><td>{num(r.flexible.micro.precision)}</td><td>{num(r.flexible.micro.exhaustividad)}</td>
              <td>{num(r.flexible.micro.f1)}</td><td>{r.flexible.micro.vp} / {r.flexible.micro.fp} / {r.flexible.micro.fn}</td></tr>
          </tbody>
        </table>
      </div>
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Rúbrica (1 a 5)</div>
        <table className="tabla-permisos">
          <thead><tr><th>Criterio</th><th>Media</th><th>Calificaciones</th><th>Kappa ponderado (pares)</th></tr></thead>
          <tbody>
            {CRITERIOS.map(([k, nombre]) => (
              <tr key={k}><td>{nombre}</td><td>{num(r.rubrica[k]?.media)}</td><td>{r.rubrica[k]?.n ?? 0}</td>
                <td>{num(r.rubrica[k]?.kappa_ponderado)} ({r.rubrica[k]?.pares ?? 0})</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Por documento</div>
        <table className="tabla-permisos">
          <thead><tr><th>Documento</th><th>Entidades del motor</th><th>Descripciones ciegas</th><th>F1 flexible</th><th /></tr></thead>
          <tbody>
            {r.documentos.map((d) => (
              <tr key={d.instanciacion_id}><td>{d.nombre}</td><td>{d.entidades_motor}</td><td>{d.referencias_ciegas}</td>
                <td>{num(d.f1_flexible)}</td>
                <td>{d.descrito_durante_la_evaluacion && <span className="insignia alerta">Se describió en el sistema durante la evaluación</span>}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="meta">
        Estricta: mismo valor tras quitar tildes, mayúsculas y signos; las fechas, por su EDTF. Flexible: similitud de texto
        desde el umbral. Cada entidad cuenta una sola vez (emparejamiento uno a uno, dentro del mismo tipo y, en los agentes,
        del mismo rol). Cada descripción ciega es una referencia. El acuerdo entre archivistas se mide con F1, porque en la
        extracción de entidades no hay negativos y el kappa no está definido; la rúbrica usa kappa ponderado cuadrático.
      </p>
    </>
  );
}
