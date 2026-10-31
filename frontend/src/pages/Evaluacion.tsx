import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ErrorAPI, descargar, pedir } from "@/lib/api";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";

// Evaluación ciega del motor frente a archivistas (objetivo 3 de la tesis).
// La archivista describe a ciegas (sin ver nunca la propuesta del motor),
// después con la propuesta delante (asistida) y por último la califica.
// El servidor impide describir a ciegas lo que ya se vio.
// La descripción se hace en RiC: entidades (con su clase de RiC-O) y
// relaciones (con su propiedad de RiC-O) entre el documento y esas entidades
// o entre ellas. El servidor revisa la conformidad con RiC-O 1.1.

interface Criterio { margen_f: number; minimo_casos: number; rubrica_minima: number; conformidad_asistida: number }
interface EvaluacionBreve {
  id: string; nombre: string; protocolo: string | null; estado: "preparacion" | "en_curso" | "cerrada";
  umbral_similitud: number; documentos: number; con_propuesta: number; criterio: Criterio;
}
interface EstadoAnotacion { id: string; estado: "en_curso" | "enviada" | "anulada" }
interface Tarea {
  instanciacion_id: string; nombre: string; ciega: EstadoAnotacion | null; asistida: EstadoAnotacion | null;
  puede_ciega: boolean; calificado: boolean;
}
interface Entidad { clave: string; tipo: string; valor: string; subtipo: string | null; edtf: string | null }
interface Relacion { origen: string; propiedad: string; destino: string }
interface Datos { titulo?: string | null; alcance?: string | null; entidades: Entidad[]; relaciones: Relacion[] }
interface Conformidad { conforme: boolean; relaciones: number; relaciones_validas: number; problemas: string[] }
interface AnotacionAbierta {
  id: string; condicion: "ciega" | "asistida"; estado: string; datos: Datos; conformidad: Conformidad | null;
  documento: { id: string; nombre: string; texto: string | null };
}
interface PropiedadRic { codigo: string; rico: string; papel: string; etiqueta: string; codigo_cm: string | null; origen: string[]; destino: string[] }

const ESTADO_EV: Record<EvaluacionBreve["estado"], { texto: string; clase: string }> = {
  preparacion: { texto: "En preparación", clase: "proceso" },
  en_curso: { texto: "En curso", clase: "alerta" },
  cerrada: { texto: "Cerrada", clase: "bien" },
};
const TIPOS: [string, string][] = [["agente", "Agente"], ["lugar", "Lugar"], ["fecha", "Fecha"], ["actividad", "Actividad"],
  ["tipo_actividad", "Tipo de actividad (función)"], ["mandato", "Mandato o norma"], ["forma_documental", "Forma documental"]];
const SUBTIPOS: [string, string][] = [["persona", "Persona"], ["entidad_corporativa", "Entidad corporativa"],
  ["cargo", "Cargo"], ["grupo", "Grupo"], ["familia", "Familia"], ["mecanismo", "Mecanismo"]];
const DOCUMENTO = "documento";

// Qué tipo de extremo es, en los términos del catálogo de propiedades del servidor.
function extremo(clave: string, entidades: Entidad[]): string {
  if (clave === DOCUMENTO) return "documento";
  const e = entidades.find((x) => x.clave === clave);
  if (!e) return "";
  return e.tipo === "agente" ? (e.subtipo ? `agente:${e.subtipo}` : "agente") : e.tipo;
}

function nombreExtremo(clave: string, entidades: Entidad[]): string {
  if (clave === DOCUMENTO) return "Este documento";
  const e = entidades.find((x) => x.clave === clave);
  return e ? `${e.valor || "(sin nombre)"} · ${TIPOS.find(([k]) => k === e.tipo)?.[1] ?? e.tipo}` : "(quitada)";
}

function nombrePropiedad(codigo: string, catalogo: PropiedadRic[]): string {
  const p = catalogo.find((x) => x.codigo === codigo);
  return p ? `${p.papel} — ${p.etiqueta} (${p.rico}${p.codigo_cm ? ` · ${p.codigo_cm}` : ""})` : codigo;
}

function useCatalogo(): PropiedadRic[] {
  const [catalogo, setCatalogo] = useState<PropiedadRic[]>([]);
  useEffect(() => {
    pedir<PropiedadRic[]>("/api/evaluacion/propiedades").then(setCatalogo).catch(() => setCatalogo([]));
  }, []);
  return catalogo;
}

function ListaRelaciones({ datos, catalogo }: { datos: Datos; catalogo: PropiedadRic[] }) {
  if (!datos.relaciones?.length) return <p className="meta">Sin relaciones.</p>;
  return (
    <ul className="lista-relaciones">
      {datos.relaciones.map((r, i) => (
        <li key={i}>{nombreExtremo(r.origen, datos.entidades)} — <strong>{nombrePropiedad(r.propiedad, catalogo)}</strong> →{" "}
          {nombreExtremo(r.destino, datos.entidades)}</li>
      ))}
    </ul>
  );
}

function AvisoConformidad({ c }: { c: Conformidad | null }) {
  if (!c) return null;
  if (c.conforme) {
    return <div className="aviso bien" role="status">Conforme con RiC-O 1.1: {c.relaciones} relación(es) válidas.</div>;
  }
  return (
    <div className="aviso alerta" role="status">
      <strong>Todavía no es RiC válida</strong> ({c.relaciones_validas} de {c.relaciones} relaciones válidas):
      <ul>{c.problemas.map((p) => <li key={p}>{p}</li>)}</ul>
    </div>
  );
}
const CRITERIOS: [string, string, string][] = [
  ["exactitud", "Exactitud", "Lo propuesto es cierto según el documento."],
  ["completitud", "Completitud", "No le falta nada importante."],
  ["pertinencia", "Pertinencia", "El contexto (agentes, funciones, fechas) es el que un archivista registraría."],
];
// Descriptores de cada nivel (tabla de la rúbrica en el capítulo III de la tesis), del 1 al 5.
const DESCRIPTORES: Record<string, string[]> = {
  exactitud: ["La mayor parte de lo propuesto es incorrecto",
    "Error en el productor, la fecha principal o el tipo documental",
    "Errores que exigen corrección, sin afectar al productor ni a la fecha principal",
    "Un error menor que no altera el sentido",
    "Todas las entidades y relaciones propuestas son correctas"],
  completitud: ["Omite la mayor parte de lo esencial", "Omite un elemento principal", "Omite varios elementos secundarios",
    "Omite un elemento secundario", "Propone todo lo que una archivista registraría"],
  pertinencia: ["La propuesta no sirve para describir el documento", "Predominan los elementos irrelevantes",
    "Varios elementos sin valor descriptivo", "Un elemento de poco valor descriptivo",
    "Todo lo propuesto es relevante para describir el documento"],
};
const NOMBRE_TIPO = (t: string) => TIPOS.find(([k]) => k === t)?.[1] || t;

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
                  pertinencia. Al cerrar, el sistema calcula precisión, exhaustividad y F1 de entidades y de relaciones RiC
                  frente a la descripción a ciegas, la conformidad con RiC-O 1.1 y el acuerdo entre archivistas.</li>
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
        <CriterioComparabilidad ev={ev} cambio={cambio} />
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

// Criterio de comparabilidad: se fija antes de iniciar y queda congelado (objetivo 3 de la tesis).
function CriterioComparabilidad({ ev, cambio }: { ev: EvaluacionBreve; cambio: () => void }) {
  const [c, setC] = useState<Criterio>(ev.criterio);
  const [aviso, setAviso] = useState("");
  useEffect(() => setC(ev.criterio), [ev.criterio]);
  const editable = ev.estado === "preparacion";

  async function guardar(e: FormEvent) {
    e.preventDefault();
    setAviso("");
    try {
      await pedir(`/api/evaluacion/${ev.id}/criterio`, { method: "PUT", body: JSON.stringify(c) });
      setAviso("Criterio guardado. Quedará fijo al iniciar la evaluación.");
      cambio();
    } catch (err) {
      setAviso(mensaje(err, "No se pudo guardar el criterio."));
    }
  }

  const campo = (k: keyof Criterio, texto: string, paso: number, min: number, max: number) => (
    <label className="meta" style={{ display: "grid", gap: 2 }}>{texto}
      <input className="campo" type="number" step={paso} min={min} max={max} value={c[k]} disabled={!editable}
             onChange={(e) => setC({ ...c, [k]: Number(e.target.value) })} />
    </label>
  );
  return (
    <form onSubmit={guardar} style={{ margin: "8px 0 12px" }}>
      <strong>Criterio de comparabilidad</strong>{" "}
      <span className="meta">{editable ? "Se fija antes de iniciar; después no cambia." : "Fijado al iniciar la evaluación."}</span>
      <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", marginTop: 6 }}>
        {campo("margen_f", "Margen frente al acuerdo entre archivistas (F)", 0.01, 0, 0.5)}
        {campo("minimo_casos", "Mínimo de entidades de referencia por tipo", 1, 1, 1000)}
        {campo("rubrica_minima", "Media mínima de la rúbrica", 0.5, 1, 5)}
        {campo("conformidad_asistida", "Conformidad mínima de las asistidas (0 a 1)", 0.05, 0, 1)}
      </div>
      {aviso && <div className="aviso" role="status">{aviso}</div>}
      {editable && <div className="acciones"><button type="submit" className="boton chico">Guardar el criterio</button></div>}
    </form>
  );
}

function FormularioAnotacion({ a, cerrar }: { a: AnotacionAbierta; cerrar: () => void }) {
  const catalogo = useCatalogo();
  const [datos, setDatos] = useState<Datos>({ titulo: a.datos.titulo || "", alcance: a.datos.alcance || "",
    entidades: a.datos.entidades || [], relaciones: a.datos.relaciones || [] });
  const [conformidad, setConformidad] = useState<Conformidad | null>(a.conformidad);
  const [error, setError] = useState("");
  const soloLectura = a.estado !== "en_curso";

  function cambiar(i: number, campo: keyof Entidad, valor: string) {
    setDatos({ ...datos, entidades: datos.entidades.map((e, j) => (j === i ? { ...e, [campo]: valor || null } : e)) });
  }
  function nuevaEntidad() {
    const usadas = new Set(datos.entidades.map((e) => e.clave));
    let n = datos.entidades.length + 1;
    while (usadas.has(`e${n}`)) n += 1;
    setDatos({ ...datos, entidades: [...datos.entidades, { clave: `e${n}`, tipo: "agente", valor: "", subtipo: null, edtf: null }] });
  }
  function quitarEntidad(clave: string) {
    setDatos({ ...datos, entidades: datos.entidades.filter((e) => e.clave !== clave),
      relaciones: datos.relaciones.filter((r) => r.origen !== clave && r.destino !== clave) });
  }
  // Las propiedades que admiten esos dos extremos (las demás no se ofrecen).
  function validas(origen: string, destino: string): PropiedadRic[] {
    const o = extremo(origen, datos.entidades);
    const d = extremo(destino, datos.entidades);
    return catalogo.filter((p) => p.origen.includes(o) && p.destino.includes(d));
  }
  function cambiarRelacion(i: number, campo: keyof Relacion, valor: string) {
    setDatos({ ...datos, relaciones: datos.relaciones.map((r, j) => {
      if (j !== i) return r;
      const nueva = { ...r, [campo]: valor };
      // Al cambiar un extremo, la relación se vuelve a elegir: una propiedad que quedó puesta sola
      // (válida para los extremos anteriores) no debe colarse como si la archivista la hubiera elegido.
      if (campo !== "propiedad") nueva.propiedad = validas(nueva.origen, nueva.destino)[0]?.codigo || "";
      return nueva;
    }) });
  }
  function nuevaRelacion() {
    const destino = datos.entidades[0]?.clave || "";
    setDatos({ ...datos, relaciones: [...datos.relaciones, { origen: DOCUMENTO, destino,
      propiedad: validas(DOCUMENTO, destino)[0]?.codigo || "" }] });
  }

  async function guardar(enviar: boolean) {
    setError("");
    try {
      const r = await pedir<AnotacionAbierta>(`/api/evaluacion/anotaciones/${a.id}`, { method: "PUT",
        body: JSON.stringify({ ...datos, relaciones: datos.relaciones.filter((x) => x.propiedad), enviar }) });
      setConformidad(r.conformidad);
      if (enviar) cerrar();
    } catch (err) {
      setError(mensaje(err, "No se pudo guardar."));
    }
  }

  const extremos = [DOCUMENTO, ...datos.entidades.map((e) => e.clave)];
  return (
    <>
      <button type="button" className="boton chico" onClick={cerrar}>← Volver</button>
      <h2>{a.documento.nombre} · {a.condicion === "ciega" ? "a ciegas" : "con la propuesta del motor"}</h2>
      {a.condicion === "ciega" && (
        <div className="aviso">Describa solo a partir del documento. El tiempo se mide desde que lo abrió hasta que lo envía.</div>
      )}
      <div className="evaluacion-columnas">
        <div className="tarjeta"><div className="tarjeta-cab">Documento</div>
          <div className="tarjeta-cuerpo" style={{ whiteSpace: "pre-wrap", maxHeight: 520, overflow: "auto" }}>
            {a.documento.texto || <span className="meta">Sin texto extraído.</span>}</div></div>
        <div className="tarjeta"><div className="tarjeta-cab">Descripción en RiC</div>
          <div className="tarjeta-cuerpo">
            <label className="meta" htmlFor="an-titulo">Título (rico:title)</label>
            <input id="an-titulo" className="campo" style={{ width: "100%" }} disabled={soloLectura} value={datos.titulo || ""}
                   onChange={(e) => setDatos({ ...datos, titulo: e.target.value })} />
            <label className="meta" htmlFor="an-alcance" style={{ display: "block", marginTop: 8 }}>
              Alcance y contenido (rico:scopeAndContent)</label>
            <textarea id="an-alcance" className="campo" rows={3} style={{ width: "100%" }} disabled={soloLectura}
                      value={datos.alcance || ""} onChange={(e) => setDatos({ ...datos, alcance: e.target.value })} />

            <h4>1. Entidades</h4>
            <p className="meta">Quién, dónde, cuándo, qué actividad y qué norma aparecen en el documento. El papel de cada una
              (productor, destinatario…) no va aquí: es una relación.</p>
            {datos.entidades.map((e, i) => (
              <div key={e.clave} className="fila-entidad" style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 6 }}>
                <select className="selector" aria-label="Tipo" disabled={soloLectura} value={e.tipo}
                        onChange={(x) => cambiar(i, "tipo", x.target.value)}>
                  {TIPOS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                {e.tipo === "agente" && (
                  <select className="selector" aria-label="Clase de agente" disabled={soloLectura} value={e.subtipo || ""}
                          onChange={(x) => cambiar(i, "subtipo", x.target.value)}>
                    <option value="">Clase de agente…</option>
                    {SUBTIPOS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                )}
                <input className="campo" aria-label="Nombre o valor" placeholder="Nombre o valor" disabled={soloLectura}
                       value={e.valor} onChange={(x) => cambiar(i, "valor", x.target.value)} style={{ flex: "1 1 160px" }} />
                {e.tipo === "fecha" && (
                  <input className="campo" aria-label="EDTF" placeholder="EDTF (1948-03, 1948~…)" disabled={soloLectura}
                         value={e.edtf || ""} onChange={(x) => cambiar(i, "edtf", x.target.value)} style={{ width: 150 }} />
                )}
                {!soloLectura && (
                  <button type="button" className="boton chico" aria-label={`Quitar ${e.valor || "entidad"}`}
                          onClick={() => quitarEntidad(e.clave)}>×</button>
                )}
              </div>
            ))}
            {!soloLectura && <button type="button" className="boton chico" onClick={nuevaEntidad}>+ Entidad</button>}

            <h4>2. Relaciones (RiC-O)</h4>
            <p className="meta">Cómo se conectan el documento y las entidades. Solo se ofrecen las relaciones que RiC-O admite
              entre esos dos extremos.</p>
            {datos.relaciones.map((r, i) => {
              const opciones = validas(r.origen, r.destino);
              return (
                <div key={i} className="fila-relacion" style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 6 }}>
                  <select className="selector" aria-label="Origen" disabled={soloLectura} value={r.origen}
                          onChange={(x) => cambiarRelacion(i, "origen", x.target.value)}>
                    {extremos.map((k) => <option key={k} value={k}>{nombreExtremo(k, datos.entidades)}</option>)}
                  </select>
                  <select className="selector" aria-label="Relación" disabled={soloLectura} value={r.propiedad}
                          onChange={(x) => cambiarRelacion(i, "propiedad", x.target.value)} style={{ flex: "1 1 200px" }}>
                    {!opciones.some((p) => p.codigo === r.propiedad) && (
                      <option value={r.propiedad}>{r.propiedad ? `${nombrePropiedad(r.propiedad, catalogo)} — no admitida` : "Ninguna relación de RiC-O une estos extremos"}</option>
                    )}
                    {opciones.map((p) => <option key={p.codigo} value={p.codigo}>{nombrePropiedad(p.codigo, catalogo)}</option>)}
                  </select>
                  <select className="selector" aria-label="Destino" disabled={soloLectura} value={r.destino}
                          onChange={(x) => cambiarRelacion(i, "destino", x.target.value)}>
                    {extremos.map((k) => <option key={k} value={k}>{nombreExtremo(k, datos.entidades)}</option>)}
                  </select>
                  {!soloLectura && (
                    <button type="button" className="boton chico" aria-label="Quitar relación"
                            onClick={() => setDatos({ ...datos, relaciones: datos.relaciones.filter((_, j) => j !== i) })}>×</button>
                  )}
                </div>
              );
            })}
            {!soloLectura && (
              <button type="button" className="boton chico" disabled={!datos.entidades.length} onClick={nuevaRelacion}>
                + Relación</button>
            )}
            <AvisoConformidad c={conformidad} />
            {error && <div className="aviso error" role="alert">{error}</div>}
            {!soloLectura && (
              <div className="acciones">
                <button type="button" className="boton chico" onClick={() => guardar(false)}>Guardar y revisar conformidad</button>
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
  const catalogo = useCatalogo();
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
          <h4>Entidades</h4>
          <ul>{propuesta.entidades.map((e) => <li key={e.clave}>{TIPOS.find(([k]) => k === e.tipo)?.[1]}: {e.valor}
            {e.subtipo && ` · ${SUBTIPOS.find(([k]) => k === e.subtipo)?.[1] ?? e.subtipo}`}{e.edtf && ` · ${e.edtf}`}</li>)}</ul>
          <h4>Relaciones (RiC-O)</h4>
          <ListaRelaciones datos={propuesta} catalogo={catalogo} />
          {CRITERIOS.map(([k, nombre, pista]) => (
            <fieldset key={k} style={{ border: 0, padding: 0, margin: "10px 0" }}>
              <legend><strong>{nombre}</strong> <span className="meta">{pista}</span></legend>
              <div style={{ display: "grid", gap: 4 }}>
                {[5, 4, 3, 2, 1].map((n) => (
                  <label key={n} style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
                    <input type="radio" name={k} checked={notas[k] === n} onChange={() => setNotas({ ...notas, [k]: n })} />
                    <span><strong>{n}</strong> · {DESCRIPTORES[k][n - 1]}</span>
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
  relaciones: {
    estricto: { por_tipo: Record<string, Medida>; micro: Medida; macro_f1: number | null };
    flexible: { por_tipo: Record<string, Medida>; micro: Medida; macro_f1: number | null };
    acuerdo_entre_archivistas: Medida | null;
    confusiones: { motor: string; archivista: string; veces: number }[];
    propiedades: Record<string, string>;
  };
  conformidad: Record<string, { descripciones: number; conformes: number; relaciones: number; relaciones_validas: number;
    tasa_relaciones_validas: number | null; problemas: { problema: string; veces: number }[] }>;
  acuerdo_entre_archivistas: Medida | null;
  tiempos: Record<string, { n: number; mediana_minutos: number | null; media_minutos: number | null }>;
  rubrica: Record<string, { n: number; media: number | null; pares: number; kappa_ponderado: number | null }>;
  documentos: { instanciacion_id: string; nombre: string; entidades_motor: number; relaciones_motor: number;
    referencias_ciegas: number; f1_flexible: number | null; f1_relaciones_flexible: number | null; motor_conforme: boolean;
    descrito_durante_la_evaluacion: boolean }[];
  anotaciones: { ciegas: number; asistidas: number; evaluadores: number };
  comparabilidad: {
    criterio: Criterio;
    condiciones: Record<string, { valor: number | Record<string, number | null> | null; exigido: number; cumple: boolean }>;
    tipos: { tipo: string; casos: number; f_motor: number | null; techo: number | null; diferencia: number | null;
      estado: "comparable" | "no_comparable" | "datos_insuficientes" | "sin_techo"; motivos: string[] }[];
    comparables: string[]; no_comparables: string[]; sin_decidir: string[];
  };
  intervalos: Record<string, { documentos: number; remuestreos: number; inferior: number | null; superior: number | null }>;
  prueba_tiempos: { n: number; z: number | null; p: number | null; nota: string | null };
  supervision: { por_tipo: Record<string, Record<string, number>>; total: Record<string, number>; propuestas: number;
    pct_aceptadas: number | null; pct_corregidas: number | null; pct_rechazadas: number | null; pct_agregadas: number | null };
  errores: { desacuerdos: number; clasificados: number; pendientes_consenso: number; sin_clasificar: number;
    clasificadoras: number; pares: number; kappa: number | null; por_clase: Record<string, number>;
    distribucion: { tipo_error: string; nombre: string; veces: number; porcentaje: number | null }[] };
}
const ESTADO_TIPO: Record<string, { texto: string; clase: string }> = {
  comparable: { texto: "Comparable", clase: "bien" },
  no_comparable: { texto: "No comparable", clase: "error" },
  datos_insuficientes: { texto: "Datos insuficientes", clase: "alerta" },
  sin_techo: { texto: "Sin techo (falta una segunda archivista)", clase: "alerta" },
};

const num = (x: number | null | undefined, d = 2) => (x === null || x === undefined ? "—" : x.toLocaleString("es-CO", { maximumFractionDigits: d }));

function Resultados({ evId, volver }: { evId: string; volver: () => void }) {
  const [r, setR] = useState<Resultado | null>(null);
  const [error, setError] = useState("");
  const [clasificando, setClasificando] = useState(false);
  const cargar = useCallback(() => {
    pedir<Resultado>(`/api/evaluacion/${evId}/resultados`).then(setR).catch((err) => setError(mensaje(err, "No se pudieron calcular.")));
  }, [evId]);
  useEffect(cargar, [cargar]);
  if (clasificando) return <Desacuerdos evId={evId} volver={() => { setClasificando(false); cargar(); }} />;
  if (error) return <><button type="button" className="boton chico" onClick={volver}>← Volver</button><div className="aviso error">{error}</div></>;
  if (!r) return <div className="cargando">Calculando…</div>;
  const tipos = Array.from(new Set([...Object.keys(r.estricto.por_tipo), ...Object.keys(r.flexible.por_tipo)]));
  const props = Array.from(new Set([...Object.keys(r.relaciones.estricto.por_tipo), ...Object.keys(r.relaciones.flexible.por_tipo)]));
  const rico = (c: string) => r.relaciones.propiedades[c] || c;
  const QUIEN: Record<string, string> = { motor: "Motor", ciega: "Archivistas a ciegas", asistida: "Archivistas asistidas" };
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
        <div className="cifra"><strong>{num(r.relaciones.flexible.micro.f1)}</strong><span>F1 de relaciones RiC (flexible)</span></div>
        <div className="cifra"><strong>{r.conformidad.motor?.conformes ?? 0} / {r.conformidad.motor?.descripciones ?? 0}</strong>
          <span>Propuestas del motor conformes con RiC-O</span></div>
        <div className="cifra"><strong>{num(r.acuerdo_entre_archivistas?.f1)}</strong><span>Acuerdo entre archivistas (F1)</span></div>
        <div className="cifra"><strong>{num(r.tiempos.ciega?.mediana_minutos, 1)} / {num(r.tiempos.asistida?.mediana_minutos, 1)}</strong>
          <span>Minutos por documento: a ciegas / asistida (mediana)</span></div>
      </div>
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Respuesta a la pregunta: ¿son comparables con las de las archivistas?</div>
        <p className="meta" style={{ padding: "0 18px" }}>
          Criterio fijado antes de iniciar: la F flexible del motor no queda más de {num(r.comparabilidad.criterio.margen_f)} por
          debajo del acuerdo entre archivistas (techo), con al menos {r.comparabilidad.criterio.minimo_casos} entidades de
          referencia; descripciones asistidas conformes ≥ {num(r.comparabilidad.criterio.conformidad_asistida * 100, 0)} %
          ({r.comparabilidad.condiciones.conformidad_asistida?.cumple ? "cumple" : "no cumple"}); rúbrica media
          ≥ {num(r.comparabilidad.criterio.rubrica_minima, 1)} en los tres criterios
          ({r.comparabilidad.condiciones.rubrica?.cumple ? "cumple" : "no cumple"}).
        </p>
        <table className="tabla-permisos">
          <thead><tr><th>Tipo</th><th>Casos</th><th>F del motor</th><th>Acuerdo entre archivistas</th><th>Diferencia</th>
            <th>Resultado</th><th>Por qué</th></tr></thead>
          <tbody>
            {r.comparabilidad.tipos.length === 0 && <tr><td colSpan={7} className="meta">Todavía no hay descripciones ciegas.</td></tr>}
            {r.comparabilidad.tipos.map((t) => (
              <tr key={t.tipo}><td>{NOMBRE_TIPO(t.tipo)}</td><td>{t.casos}</td><td>{num(t.f_motor)}</td><td>{num(t.techo)}</td>
                <td>{num(t.diferencia)}</td>
                <td><span className={`insignia ${ESTADO_TIPO[t.estado].clase}`}>{ESTADO_TIPO[t.estado].texto}</span></td>
                <td className="meta">{t.motivos.join("; ") || "—"}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Supervisión en la condición asistida</div>
        <table className="tabla-permisos">
          <thead><tr><th>Tipo</th><th>Aceptadas</th><th>Corregidas</th><th>Rechazadas</th><th>Agregadas por la archivista</th></tr></thead>
          <tbody>
            {Object.entries(r.supervision.por_tipo).map(([t, x]) => (
              <tr key={t}><td>{NOMBRE_TIPO(t)}</td><td>{x.aceptada}</td><td>{x.corregida}</td><td>{x.rechazada}</td><td>{x.agregada}</td></tr>
            ))}
            <tr><td><strong>Total</strong></td><td>{r.supervision.total.aceptada ?? 0} ({num(r.supervision.pct_aceptadas, 1)} %)</td>
              <td>{r.supervision.total.corregida ?? 0} ({num(r.supervision.pct_corregidas, 1)} %)</td>
              <td>{r.supervision.total.rechazada ?? 0} ({num(r.supervision.pct_rechazadas, 1)} %)</td>
              <td>{r.supervision.total.agregada ?? 0} ({num(r.supervision.pct_agregadas, 1)} %)</td></tr>
          </tbody>
        </table>
        <p className="meta" style={{ padding: "0 18px" }}>
          F1 de entidades (flexible), intervalo del 95 %: {num(r.intervalos.entidades_flexible?.inferior)} a{" "}
          {num(r.intervalos.entidades_flexible?.superior)} · de relaciones: {num(r.intervalos.relaciones_flexible?.inferior)} a{" "}
          {num(r.intervalos.relaciones_flexible?.superior)} ({r.intervalos.entidades_flexible?.documentos ?? 0} documento(s),
          remuestreo por documento). Tiempos ciega frente a asistida, Wilcoxon: n = {r.prueba_tiempos.n}
          {r.prueba_tiempos.p !== null ? `, z = ${num(r.prueba_tiempos.z)}, p = ${num(r.prueba_tiempos.p, 4)}` : ` (${r.prueba_tiempos.nota ?? "sin datos"})`}.
        </p>
      </div>
      <div className="tarjeta">
        <div className="tarjeta-cab">Análisis de errores</div>
        <div className="tarjeta-cuerpo">
          <p>{r.errores.desacuerdos} desacuerdo(s) entre el motor y las referencias ciegas · {r.errores.clasificados} clasificados ·{" "}
            {r.errores.pendientes_consenso} pendientes de consenso · {r.errores.sin_clasificar} sin clasificar. Kappa entre
            clasificadoras: {num(r.errores.kappa)} ({r.errores.pares} pares).</p>
          {r.errores.distribucion.length > 0 && (
            <ul>{r.errores.distribucion.map((x) => <li key={x.tipo_error}>{x.nombre}: {x.veces} ({num(x.porcentaje, 1)} %)</li>)}</ul>
          )}
          <div className="acciones"><button type="button" className="boton chico primario" onClick={() => setClasificando(true)}>
            Clasificar los desacuerdos</button></div>
        </div>
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
        <div className="tarjeta-cab">Relaciones RiC del motor frente a las descripciones ciegas</div>
        <table className="tabla-permisos">
          <thead><tr><th>Propiedad RiC-O</th><th>P estricta</th><th>E estricta</th><th>F1 estricto</th><th>P flexible</th>
            <th>E flexible</th><th>F1 flexible</th><th>VP / FP / FN (flexible)</th></tr></thead>
          <tbody>
            {props.length === 0 && <tr><td colSpan={8} className="meta">Todavía no hay relaciones que comparar.</td></tr>}
            {props.map((c) => {
              const e = r.relaciones.estricto.por_tipo[c];
              const f = r.relaciones.flexible.por_tipo[c];
              return (
                <tr key={c}><td>{rico(c)}</td>
                  <td>{num(e?.precision)}</td><td>{num(e?.exhaustividad)}</td><td>{num(e?.f1)}</td>
                  <td>{num(f?.precision)}</td><td>{num(f?.exhaustividad)}</td><td>{num(f?.f1)}</td>
                  <td>{f ? `${f.vp} / ${f.fp} / ${f.fn}` : "—"}</td></tr>
              );
            })}
            <tr><td><strong>Total (micro)</strong></td><td>{num(r.relaciones.estricto.micro.precision)}</td>
              <td>{num(r.relaciones.estricto.micro.exhaustividad)}</td><td>{num(r.relaciones.estricto.micro.f1)}</td>
              <td>{num(r.relaciones.flexible.micro.precision)}</td><td>{num(r.relaciones.flexible.micro.exhaustividad)}</td>
              <td>{num(r.relaciones.flexible.micro.f1)}</td>
              <td>{r.relaciones.flexible.micro.vp} / {r.relaciones.flexible.micro.fp} / {r.relaciones.flexible.micro.fn}</td></tr>
          </tbody>
        </table>
        <p className="meta" style={{ padding: "0 18px" }}>Acuerdo entre archivistas en relaciones (F1):{" "}
          {num(r.relaciones.acuerdo_entre_archivistas?.f1)}</p>
      </div>
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Confusión de propiedades: la misma entidad, otra relación</div>
        <table className="tabla-permisos">
          <thead><tr><th>El motor dijo</th><th>La archivista dijo</th><th>Veces</th></tr></thead>
          <tbody>
            {r.relaciones.confusiones.length === 0 && <tr><td colSpan={3} className="meta">Ninguna.</td></tr>}
            {r.relaciones.confusiones.map((c) => (
              <tr key={`${c.motor}-${c.archivista}`}><td>{rico(c.motor)}</td><td>{rico(c.archivista)}</td><td>{c.veces}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Conformidad con RiC-O 1.1</div>
        <table className="tabla-permisos">
          <thead><tr><th>Quién describe</th><th>Descripciones conformes</th><th>Relaciones válidas</th><th>Problemas más frecuentes</th></tr></thead>
          <tbody>
            {Object.entries(r.conformidad).map(([k, c]) => (
              <tr key={k}><td>{QUIEN[k] || k}</td><td>{c.conformes} / {c.descripciones}</td>
                <td>{c.relaciones_validas} / {c.relaciones} ({num(c.tasa_relaciones_validas)})</td>
                <td>{c.problemas.length === 0 ? "—" : <ul>{c.problemas.slice(0, 5).map((x) => <li key={x.problema}>{x.problema} ({x.veces})</li>)}</ul>}</td></tr>
            ))}
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
          <thead><tr><th>Documento</th><th>Entidades / relaciones del motor</th><th>Descripciones ciegas</th>
            <th>F1 entidades</th><th>F1 relaciones</th><th>Motor conforme</th><th /></tr></thead>
          <tbody>
            {r.documentos.map((d) => (
              <tr key={d.instanciacion_id}><td>{d.nombre}</td><td>{d.entidades_motor} / {d.relaciones_motor}</td>
                <td>{d.referencias_ciegas}</td><td>{num(d.f1_flexible)}</td><td>{num(d.f1_relaciones_flexible)}</td>
                <td>{d.motor_conforme ? "Sí" : "No"}</td>
                <td>{d.descrito_durante_la_evaluacion && <span className="insignia alerta">Se describió en el sistema durante la evaluación</span>}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="meta">
        Estricta: mismo valor tras quitar tildes, mayúsculas y signos; las fechas, por su EDTF. Flexible: similitud de texto
        desde el umbral. Cada entidad cuenta una sola vez (emparejamiento uno a uno, dentro del mismo tipo). Una relación
        acierta si tiene la misma propiedad de RiC-O y sus dos extremos coinciden; si los extremos coinciden con otra
        propiedad, es una confusión (por ejemplo, destinatario en lugar de productor). La conformidad revisa cada relación
        contra el mapeo verificado y contra el OWL oficial de RiC-O 1.1. Cada descripción ciega es una referencia. El acuerdo entre archivistas se mide con F1, porque en la
        extracción de entidades no hay negativos y el kappa no está definido; la rúbrica usa kappa ponderado cuadrático.
      </p>
    </>
  );
}

interface DesacuerdoFila {
  clave: string; documento: string | null; clase: string; clase_nombre: string; tipo: string; propiedad: string | null;
  propiedad_archivista: string | null; motor: string | null; archivista: string | null; mia: string | null; otra: string | null;
  otra_clasifico: boolean; consenso: string | null; requiere_consenso: boolean;
}
interface DesacuerdosRespuesta {
  estado: string; tipos_error: Record<string, string>; clases: Record<string, string>;
  resumen: { desacuerdos: number; clasificados: number; pendientes_consenso: number; sin_clasificar: number; kappa: number | null; pares: number };
  desacuerdos: DesacuerdoFila[];
}

// Clasificación de cada desacuerdo con la taxonomía de errores de la tesis. Cada investigadora
// clasifica por su cuenta; ve la clasificación de la otra solo después de dar la suya, y si
// difieren, registran el consenso.
function Desacuerdos({ evId, volver }: { evId: string; volver: () => void }) {
  const [d, setD] = useState<DesacuerdosRespuesta | null>(null);
  const [error, setError] = useState("");
  const [filtro, setFiltro] = useState<"todos" | "pendientes" | "consenso">("pendientes");
  const cargar = useCallback(() => {
    pedir<DesacuerdosRespuesta>(`/api/evaluacion/${evId}/desacuerdos`).then(setD)
      .catch((err) => setError(mensaje(err, "No se pudieron cargar los desacuerdos.")));
  }, [evId]);
  useEffect(cargar, [cargar]);

  async function clasificar(clave: string, tipo_error: string, ronda: "individual" | "consenso") {
    setError("");
    try {
      await pedir(`/api/evaluacion/${evId}/desacuerdos/${clave}`, { method: "PUT", body: JSON.stringify({ tipo_error, ronda }) });
      cargar();
    } catch (err) {
      setError(mensaje(err, "No se pudo clasificar."));
    }
  }

  if (!d) return <>{error ? <div className="aviso error">{error}</div> : <div className="cargando">Cargando…</div>}</>;
  const filas = d.desacuerdos.filter((x) => filtro === "todos" || (filtro === "pendientes" ? !x.mia : x.requiere_consenso));
  const opciones = Object.entries(d.tipos_error);
  return (
    <>
      <button type="button" className="boton chico" onClick={volver}>← Resultados</button>
      <h2>Clasificar los desacuerdos</h2>
      {d.estado !== "cerrada" && <div className="aviso alerta">Se clasifican con la evaluación cerrada, cuando ya no cambian.</div>}
      {error && <div className="aviso error" role="alert">{error}</div>}
      <p className="meta">{d.resumen.clasificados} de {d.resumen.desacuerdos} clasificados · {d.resumen.pendientes_consenso} por
        consenso · kappa entre clasificadoras {num(d.resumen.kappa)}. Usted ve la clasificación de la otra investigadora solo
        después de dar la suya.</p>
      <div className="acciones">
        {(["pendientes", "consenso", "todos"] as const).map((f) => (
          <button key={f} type="button" className={`boton chico${filtro === f ? " primario" : ""}`} onClick={() => setFiltro(f)}>
            {f === "pendientes" ? "Sin mi clasificación" : f === "consenso" ? "Requieren consenso" : "Todos"}</button>
        ))}
      </div>
      <div className="tarjeta tabla-desplazable">
        <table className="tabla-permisos">
          <thead><tr><th>Documento</th><th>Desacuerdo</th><th>Motor</th><th>Archivista</th><th>Mi clasificación</th><th>Otra / consenso</th></tr></thead>
          <tbody>
            {filas.length === 0 && <tr><td colSpan={6} className="meta">Nada en esta vista.</td></tr>}
            {filas.map((x) => (
              <tr key={x.clave}>
                <td>{x.documento}</td>
                <td>{x.clase_nombre}{x.tipo !== "relacion" ? ` · ${NOMBRE_TIPO(x.tipo)}` : ""}
                  {x.propiedad && <div className="meta">{x.propiedad}{x.propiedad_archivista ? ` / ${x.propiedad_archivista}` : ""}</div>}</td>
                <td>{x.motor ?? "—"}</td><td>{x.archivista ?? "—"}</td>
                <td>
                  <select className="campo" value={x.mia ?? ""} disabled={d.estado !== "cerrada"}
                          aria-label="Mi clasificación" onChange={(e) => e.target.value && clasificar(x.clave, e.target.value, "individual")}>
                    <option value="">Elegir…</option>
                    {opciones.map(([k, nombre]) => <option key={k} value={k}>{nombre}</option>)}
                  </select>
                </td>
                <td>
                  {x.consenso ? <span className="insignia bien">Consenso: {d.tipos_error[x.consenso]}</span>
                    : x.otra ? d.tipos_error[x.otra] : x.otra_clasifico ? <span className="meta">Ya clasificó (oculta)</span> : "—"}
                  {x.requiere_consenso && (
                    <select className="campo" value="" aria-label="Consenso"
                            onChange={(e) => e.target.value && clasificar(x.clave, e.target.value, "consenso")}>
                      <option value="">Registrar consenso…</option>
                      {opciones.map(([k, nombre]) => <option key={k} value={k}>{nombre}</option>)}
                    </select>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
