import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, descargar, pedir } from "@/lib/api";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";
import { Encabezado } from "@/components/Encabezado";
import { confirmar } from "@/lib/dialogos";
import { Ventana } from "@/components/Ventana";

// Evaluación del rendimiento del motor con la medida F1 (objetivo 3).
// La referencia es la descripción que la archivista valida en Descripción: al publicar, cada
// propuesta aceptada cuenta como acierto, cada rechazada como dato inventado, cada agregada como
// dato omitido y cada corregida como las dos cosas. Aquí se preparan los conjuntos de desarrollo y
// prueba, se fijan los umbrales, se congela la versión y se leen los resultados.

type Estado = "preparacion" | "en_curso" | "cerrada";
interface Criterio { f1: number; precision: number; exhaustividad: number; acuerdo: number }
interface EvaluacionBreve {
  id: string; nombre: string; protocolo: string | null; estado: Estado; documentos: number; desarrollo: number;
  prueba: number; semilla: number | null; sorteada_en: string | null; criterio: Criterio;
  version_congelada: Record<string, string | null> | null;
}
interface Documento { instanciacion_id: string; nombre: string; anio: string; conjunto: "desarrollo" | "prueba" | null; publicado: boolean }
interface Intervalo { inferior: number | null; superior: number | null }
interface Dictamen { umbral: number | null; valor: number | null; limite_inferior: number | null; cumple: boolean | null }
interface PorTipo {
  tipo: string; texto_libre: boolean; aceptada: number; corregida: number; rechazada: number; agregada: number;
  precision: number | null; exhaustividad: number | null; f1: number | null;
}
interface Resultados {
  metricas: {
    conteo: { vp: number; fp: number; fn: number; aceptada: number; corregida: number; rechazada: number; agregada: number };
    f1: number | null; precision: number | null; exhaustividad: number | null; f1_macro: number | null;
    intervalos: Record<"f1" | "precision" | "exhaustividad", Intervalo>; por_tipo: PorTipo[]; documentos: number;
  };
  dictamen: Record<"f1" | "precision" | "exhaustividad", Dictamen> & { hipotesis: string | null };
  acuerdo: { pares: number; iguales: number; documentos: number; porcentaje: number | null; umbral: number; cumple: boolean | null };
  causas: { causa: string; nombre: string; cantidad: number }[];
  avisos: string[]; decisiones: number;
}
interface ErrorMotor {
  evento_id: number; documento: string | null; tipo: string; tipo_nombre: string;
  decision: "corregida" | "rechazada" | "agregada"; propuesto: string | null; final: string | null; causa: string | null; nota: string | null;
}
interface PropuestaControl { evento_id: number; tipo: string; tipo_nombre: string; propuesto: string | null; confianza: number | null; mi_decision: string | null }

const ESTADO: Record<Estado, { texto: string; clase: string }> = {
  preparacion: { texto: "En preparación", clase: "proceso" },
  en_curso: { texto: "En curso", clase: "alerta" },
  cerrada: { texto: "Cerrada", clase: "bien" },
};
const MEDIDAS: [keyof Criterio & ("f1" | "precision" | "exhaustividad"), string, string][] = [
  ["f1", "Medida F1", "Rendimiento global, de 0 a 1"],
  ["precision", "Precisión", "De lo que propuso el motor, cuánto estaba bien"],
  ["exhaustividad", "Exhaustividad", "De lo que tiene el documento, cuánto encontró el motor"],
];
const CAUSAS: [string, string][] = [["lectura", "Lectura del texto"], ["ambiguedad", "Ambigüedad del documento"],
  ["regla", "Regla mal aplicada"], ["invencion", "Invención del motor"]];
const DECISION: Record<string, { texto: string; clase: string }> = {
  aceptada: { texto: "Aceptada", clase: "bien" }, corregida: { texto: "Corregida", clase: "alerta" },
  rechazada: { texto: "Rechazada", clase: "error" }, agregada: { texto: "Agregada por la archivista", clase: "proceso" },
};

const TIPO: Record<string, string> = { agente: "Agente", lugar: "Lugar", fecha: "Fecha", actividad: "Actividad",
  tipo_actividad: "Tipo de actividad", mandato: "Mandato o norma", forma_documental: "Tipo documental", titulo: "Título",
  alcance: "Alcance y contenido", idioma: "Idioma", documento_citado: "Documento relacionado" };
const num = (x: number | null | undefined, d = 3) => (x === null || x === undefined ? "—" : x.toFixed(d).replace(".", ","));
const pct = (x: number | null | undefined) => (x === null || x === undefined ? "—" : `${Math.round(x * 100)} %`);
function mensaje(err: unknown, porDefecto: string) {
  return err instanceof ErrorAPI ? err.message : porDefecto;
}

export function Evaluacion() {
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const esAdmin = !!usuario?.es_administrador;
  const [lista, setLista] = useState<EvaluacionBreve[] | null>(null);
  const [abierta, setAbierta] = useState<string | null>(null);
  const [creando, setCreando] = useState(false);
  const [error, setError] = useState("");

  const cargar = useCallback(() => {
    if (!fondo) return;
    pedir<EvaluacionBreve[]>(`/api/evaluacion?fondo_id=${fondo.id}`).then(setLista)
      .catch((err) => setError(mensaje(err, "No se pudieron cargar las evaluaciones.")));
  }, [fondo]);
  useEffect(cargar, [cargar]);

  if (!fondo) return <div className="vacio">Primero debe existir un fondo.</div>;
  const actual = lista?.find((e) => e.id === abierta);
  return (
    <>
      {!actual && (
        <Encabezado titulo="Evaluación"
                    acciones={esAdmin ? <button type="button" className="boton primario" onClick={() => setCreando(true)}>Nueva evaluación</button> : undefined} />
      )}
      {creando && (
        <Ventana titulo="Nueva evaluación" alCerrar={() => setCreando(false)}>
          <NuevaEvaluacion fondoId={fondo.id} creada={() => { setCreando(false); cargar(); }} />
        </Ventana>
      )}
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!actual && <EvaluacionAutomatica fondoId={fondo.id} />}
      {!actual && <h2 style={{ marginTop: 18 }}>Evaluaciones con protocolo (sorteo y versión congelada)</h2>}
      {actual ? <Detalle ev={actual} esAdmin={esAdmin} volver={() => { setAbierta(null); cargar(); }} cambio={cargar} />
        : !lista ? <div className="cargando">Cargando…</div> : lista.length === 0 ? <ComoFunciona esAdmin={esAdmin} /> : (
          <div className="tarjeta">
            <div className="cabecera-tabla"><span>{lista.length} evaluaci{lista.length === 1 ? "ón" : "ones"}</span></div>
            <div className="tabla-desplazable">
              <table className="tabla-datos">
                <thead><tr><th>Evaluación</th><th className="num">Documentos</th><th className="num">Desarrollo</th>
                  <th className="num">Prueba</th><th>Estado</th><th className="acciones-celda"><span className="sr-only">Abrir</span></th></tr></thead>
                <tbody>
                  {lista.map((e) => (
                    <tr key={e.id}>
                      <td><strong>{e.nombre}</strong></td><td className="num">{e.documentos}</td>
                      <td className="num">{e.desarrollo}</td><td className="num">{e.prueba}</td>
                      <td><span className={`insignia ${ESTADO[e.estado].clase}`}>{ESTADO[e.estado].texto}</span></td>
                      <td className="acciones-celda" style={{ width: 90 }}>
                        <button type="button" className="boton chico" onClick={() => setAbierta(e.id)}>Abrir</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
    </>
  );
}

interface MetricasAuto {
  conteo: Resultados["metricas"]["conteo"]; f1: number | null; precision: number | null; exhaustividad: number | null;
  f1_macro: number | null; intervalos: Record<"f1" | "precision" | "exhaustividad", Intervalo>;
  por_tipo: PorTipo[]; documentos: number;
}
interface Automatica {
  revisadas_una_a_una: { metricas: MetricasAuto; dictamen: Resultados["dictamen"] };
  todas: { metricas: MetricasAuto };
  criterio: Criterio; decisiones: number; avisos: string[];
  versiones: { version: string; decisiones: number }[];
  documentos: { recurso_id: string; titulo: string | null; decisiones: number; revisada_una_a_una: boolean }[];
}

// La evaluación que se hace sola: cada descripción publicada deja sus decisiones y aquí se cuentan.
function EvaluacionAutomatica({ fondoId }: { fondoId: string }) {
  const [a, setA] = useState<Automatica | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    pedir<Automatica>(`/api/evaluacion/automatica?fondo_id=${fondoId}`).then(setA)
      .catch((err) => setError(mensaje(err, "No se pudo calcular la evaluación automática.")));
  }, [fondoId]);
  if (error) return <div className="aviso error" role="alert">{error}</div>;
  if (!a) return <div className="cargando">Calculando la evaluación automática…</div>;
  const limpia = a.revisadas_una_a_una.metricas, todas = a.todas.metricas, d = a.revisadas_una_a_una.dictamen;
  const estado = (c: boolean | null) => c === null ? <span className="meta">—</span>
    : <span className={`insignia ${c ? "bien" : "error"}`}>{c ? "Cumple" : "No cumple"}</span>;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Evaluación automática <span className="meta">(se actualiza con cada descripción publicada;
        no hay que crear nada)</span></div>
      <div className="tarjeta-cuerpo">
        {a.avisos.map((x) => <div key={x} className="aviso" role="status">{x}</div>)}
        <p className="meta">Cada propuesta de la IA aceptada cuenta como acierto, la rechazada como dato inventado, la
          agregada por la archivista como dato omitido y la corregida como las dos cosas. Solo cuenta la primera
          publicación de cada documento. El dictamen usa solo las descripciones revisadas una a una.</p>
        <div className="tabla-desplazable">
          <table className="tabla-datos">
            <thead><tr><th>Medida</th><th className="num">Revisadas una a una</th><th className="num">Intervalo 95 %</th>
              <th className="num">Umbral</th><th>Dictamen</th><th className="num">Todas las descripciones</th></tr></thead>
            <tbody>
              {MEDIDAS.map(([k, n, ayuda]) => (
                <tr key={k}>
                  <td title={ayuda}><strong>{n}</strong></td><td className="num">{num(limpia[k])}</td>
                  <td className="num">{num(limpia.intervalos[k].inferior)} a {num(limpia.intervalos[k].superior)}</td>
                  <td className="num">{num(d[k].umbral, 2)}</td><td>{estado(d[k].cumple)}</td><td className="num">{num(todas[k])}</td>
                </tr>
              ))}
              <tr><td>Documentos</td><td className="num">{limpia.documentos}</td><td colSpan={3} /><td className="num">{todas.documentos}</td></tr>
            </tbody>
          </table>
        </div>
        <div className="resumen-preservacion">
          <div className="cifra bien"><strong>{todas.conteo.aceptada}</strong><span>Aceptadas (aciertos)</span></div>
          <div className="cifra alerta"><strong>{todas.conteo.corregida}</strong><span>Corregidas</span></div>
          <div className="cifra error"><strong>{todas.conteo.rechazada}</strong><span>Rechazadas (inventadas)</span></div>
          <div className="cifra"><strong>{todas.conteo.agregada}</strong><span>Agregadas (omitidas)</span></div>
        </div>
        {a.versiones.length > 0 && <div className="meta">Versiones de la instrucción del motor: {a.versiones.map((v) =>
          `${v.version} (${v.decisiones} decisiones)`).join(" · ")}</div>}
        {todas.por_tipo.length > 0 && (
          <details style={{ marginTop: 8 }}>
            <summary>Por tipo de dato (todas las descripciones)</summary>
            <div className="tabla-desplazable">
              <table className="tabla-datos">
                <thead><tr><th>Tipo</th><th className="num">Aceptadas</th><th className="num">Corregidas</th><th className="num">Rechazadas</th>
                  <th className="num">Agregadas</th><th className="num">Precisión</th><th className="num">Exhaustividad</th><th className="num">F1</th></tr></thead>
                <tbody>
                  {todas.por_tipo.map((t) => (
                    <tr key={t.tipo}>
                      <td>{TIPO[t.tipo] || t.tipo}{t.texto_libre && <span className="meta"> · texto libre, fuera de la F1 global</span>}</td>
                      <td className="num">{t.aceptada}</td><td className="num">{t.corregida}</td><td className="num">{t.rechazada}</td>
                      <td className="num">{t.agregada}</td><td className="num">{num(t.precision)}</td><td className="num">{num(t.exhaustividad)}</td>
                      <td className="num">{num(t.f1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

function ComoFunciona({ esAdmin }: { esAdmin: boolean }) {
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Así se evalúa el motor con la medida F1</div>
      <ol className="pasos-inicio">
        <li><strong>Preparación.</strong> Se agregan los documentos del caso, se sortean con una semilla en un conjunto de
          desarrollo y uno de prueba y se fijan los umbrales de aceptación.</li>
        <li><strong>Ajuste.</strong> Con los documentos de desarrollo se ajusta la instrucción del motor. Al iniciar, la versión
          queda congelada.</li>
        <li><strong>Validación.</strong> Los documentos de prueba se describen en Descripción, una sola vez. Cada propuesta que
          la archivista acepta, corrige, rechaza o agrega queda registrada al publicar.</li>
        <li><strong>Resultados.</strong> El sistema calcula la precisión, la exhaustividad y la medida F1 con intervalos de
          confianza del 95 %, y las compara con los umbrales.</li>
      </ol>
      {esAdmin && <p className="pista" style={{ padding: "0 18px 14px", margin: 0 }}>Para empezar, pulse «Nueva evaluación».</p>}
    </div>
  );
}

function NuevaEvaluacion({ fondoId, creada }: { fondoId: string; creada: () => void }) {
  const [nombre, setNombre] = useState("");
  const [protocolo, setProtocolo] = useState("");
  const [error, setError] = useState("");
  async function crear(e: FormEvent) {
    e.preventDefault();
    try {
      await pedir("/api/evaluacion", { method: "POST", body: JSON.stringify({ fondo_id: fondoId, nombre, protocolo }) });
      creada();
    } catch (err) {
      setError(mensaje(err, "No se pudo crear."));
    }
  }
  return (
    <form onSubmit={crear}>
      <div className="campo"><label htmlFor="ev-nombre">Nombre</label>
        <input id="ev-nombre" className="entrada" required minLength={3} value={nombre}
               placeholder="Rendimiento de RICORA · resoluciones de sustracción" onChange={(e) => setNombre(e.target.value)} /></div>
      <div className="campo"><label htmlFor="ev-protocolo">Protocolo (quién valida, instrucciones, versión del motor)</label>
        <textarea id="ev-protocolo" className="entrada" rows={4} value={protocolo} onChange={(e) => setProtocolo(e.target.value)} /></div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="acciones"><button type="submit" className="boton primario">Crear la evaluación</button></div>
    </form>
  );
}

type Pestana = "preparacion" | "documentos" | "resultados" | "errores";

function Detalle({ ev, esAdmin, volver, cambio }: { ev: EvaluacionBreve; esAdmin: boolean; volver: () => void; cambio: () => void }) {
  const [pestana, setPestana] = useState<Pestana>(ev.estado === "preparacion" && esAdmin ? "preparacion" : "documentos");
  const [docs, setDocs] = useState<Documento[] | null>(null);
  const [control, setControl] = useState<Documento | null>(null);
  const cargarDocs = useCallback(() => {
    pedir<Documento[]>(`/api/evaluacion/${ev.id}/documentos`).then(setDocs).catch(() => setDocs([]));
  }, [ev.id]);
  useEffect(cargarDocs, [cargarDocs, ev]);
  const pestanas: [Pestana, string][] = [
    ...(esAdmin ? [["preparacion", "Preparación"] as [Pestana, string]] : []),
    ["documentos", "Documentos"],
    ...(esAdmin ? [["resultados", "Resultados"] as [Pestana, string]] : []),
    ["errores", "Causas de error"],
  ];
  return (
    <>
      <div className="filtros" style={{ alignItems: "center" }}>
        <button type="button" className="boton chico" onClick={volver}>← Evaluaciones</button>
        <strong>{ev.nombre}</strong>
        <span className={`insignia ${ESTADO[ev.estado].clase}`}>{ESTADO[ev.estado].texto}</span>
        {ev.version_congelada && <span className="meta">Versión congelada · {ev.version_congelada.motor || "sin motor"} ·
          instrucción {ev.version_congelada.version_instruccion} · sistema {ev.version_congelada.sistema}</span>}
      </div>
      <div className="pestanas" role="tablist">
        {pestanas.map(([k, v]) => (
          <button key={k} type="button" role="tab" aria-selected={pestana === k} className={`pestana${pestana === k ? " activa" : ""}`}
                  onClick={() => setPestana(k)}>{v}</button>
        ))}
      </div>
      {pestana === "preparacion" && <Preparacion ev={ev} docs={docs} cambio={() => { cambio(); cargarDocs(); }} />}
      {pestana === "documentos" && <ListaDocumentos ev={ev} docs={docs} controlar={setControl} />}
      {pestana === "resultados" && <VerResultados ev={ev} />}
      {pestana === "errores" && <Errores ev={ev} />}
      {control && (
        <Ventana titulo={`Validación de control · ${control.nombre}`} alCerrar={() => setControl(null)}>
          <Control ev={ev} doc={control} />
        </Ventana>
      )}
    </>
  );
}

function Preparacion({ ev, docs, cambio }: { ev: EvaluacionBreve; docs: Documento[] | null; cambio: () => void }) {
  const { fondo } = useFondo();
  const [cola, setCola] = useState<{ id: string; nombre: string }[]>([]);
  const [elegidos, setElegidos] = useState<string[]>([]);
  const [semilla, setSemilla] = useState(ev.semilla ?? new Date().getFullYear());
  const [desarrollo, setDesarrollo] = useState(15);
  const [criterio, setCriterio] = useState<Criterio>(ev.criterio);
  const [aviso, setAviso] = useState("");
  const enPreparacion = ev.estado === "preparacion";

  useEffect(() => {
    if (enPreparacion && fondo && !ev.sorteada_en) {
      pedir<{ id: string; nombre: string }[]>(`/api/descripcion/cola?fondo_id=${fondo.id}`).then(setCola).catch(() => setCola([]));
    }
  }, [enPreparacion, fondo, ev.sorteada_en, docs]);

  async function hacer(ruta: string, metodo: string, cuerpo?: object, exito?: string) {
    setAviso("");
    try {
      await pedir(`/api/evaluacion/${ev.id}/${ruta}`, { method: metodo, body: cuerpo ? JSON.stringify(cuerpo) : undefined });
      if (exito) setAviso(exito);
      setElegidos([]);
      cambio();
    } catch (err) {
      setAviso(mensaje(err, "No se pudo."));
    }
  }
  const yaEstan = new Set((docs || []).map((d) => d.instanciacion_id));
  const disponibles = cola.filter((c) => !yaEstan.has(c.id));

  return (
    <div className="tarjeta">
      <div className="tarjeta-cuerpo">
        {aviso && <div className="aviso" role="status">{aviso}</div>}
        {!enPreparacion && <p className="pista">La evaluación ya se inició: el sorteo, los umbrales y la versión quedaron congelados.</p>}

        <h3>1. Documentos · {ev.documentos}</h3>
        {enPreparacion && !ev.sorteada_en ? (
          disponibles.length === 0 ? <p className="meta">No hay más documentos listos y sin describir en este fondo.</p> : (
            <>
              <div className="tabla-desplazable" style={{ maxHeight: 220 }}>
                <table className="tabla-datos"><tbody>
                  {disponibles.map((c) => (
                    <tr key={c.id}><td style={{ width: 36 }}>
                      <input type="checkbox" aria-label={`Elegir ${c.nombre}`} checked={elegidos.includes(c.id)}
                             onChange={(e) => setElegidos(e.target.checked ? [...elegidos, c.id] : elegidos.filter((x) => x !== c.id))} /></td>
                      <td>{c.nombre}</td></tr>
                  ))}
                </tbody></table>
              </div>
              <div className="acciones">
                <button type="button" className="boton chico" onClick={() => setElegidos(disponibles.map((d) => d.id))}>Elegir todos</button>
                <button type="button" className="boton primario" disabled={!elegidos.length}
                        onClick={() => hacer("documentos", "POST", { instanciacion_ids: elegidos }, `${elegidos.length} documento(s) agregados.`)}>
                  Agregar {elegidos.length || ""}</button>
              </div>
            </>
          )
        ) : <p className="meta">{ev.sorteada_en ? "Tras el sorteo no se agregan ni se quitan documentos." : ""}</p>}

        <h3>2. Sorteo de los conjuntos</h3>
        {ev.sorteada_en ? (
          <p>Semilla <strong>{ev.semilla}</strong> · {ev.desarrollo} de desarrollo · {ev.prueba} de prueba</p>
        ) : enPreparacion && (
          <div className="filtros" style={{ alignItems: "flex-end" }}>
            <div className="campo"><label htmlFor="ev-semilla">Semilla</label>
              <input id="ev-semilla" className="entrada" type="number" min={0} value={semilla} style={{ maxWidth: 140 }}
                     onChange={(e) => setSemilla(Number(e.target.value))} /></div>
            <div className="campo"><label htmlFor="ev-desarrollo">Documentos de desarrollo</label>
              <input id="ev-desarrollo" className="entrada" type="number" min={1} value={desarrollo} style={{ maxWidth: 140 }}
                     onChange={(e) => setDesarrollo(Number(e.target.value))} /></div>
            <button type="button" className="boton primario" disabled={ev.documentos < 3}
                    onClick={async () => {
                      if (await confirmar(`Se sortearán ${desarrollo} documentos de desarrollo y ${ev.documentos - desarrollo} de prueba con la semilla ${semilla}. Después no se agregan ni se quitan documentos. ¿Continuar?`))
                        hacer("sorteo", "POST", { semilla, desarrollo }, "Sorteo realizado.");
                    }}>Sortear</button>
          </div>
        )}
        <p className="meta">El sorteo es estratificado por el año que aparece en el nombre del archivo. Con la misma semilla
          se obtiene siempre el mismo resultado.</p>

        <h3>3. Umbrales de aceptación</h3>
        <div className="filtros" style={{ alignItems: "flex-end" }}>
          {([...MEDIDAS.map(([k, n]) => [k, n] as [keyof Criterio, string]), ["acuerdo", "Acuerdo entre validadoras"]] as [keyof Criterio, string][]).map(([k, n]) => (
            <div className="campo" key={k}><label htmlFor={`um-${k}`}>{n}</label>
              <input id={`um-${k}`} className="entrada" type="number" min={0.01} max={1} step={0.01} style={{ maxWidth: 120 }}
                     disabled={!enPreparacion} value={criterio[k]}
                     onChange={(e) => setCriterio({ ...criterio, [k]: Number(e.target.value) })} /></div>
          ))}
          {enPreparacion && <button type="button" className="boton" onClick={() => hacer("criterio", "PUT", criterio, "Umbrales guardados.")}>Guardar umbrales</button>}
        </div>

        <h3>4. Iniciar</h3>
        {enPreparacion ? (
          <>
            <p className="meta">Al iniciar se congelan los umbrales y la versión del sistema, del motor y de la instrucción. Ajuste
              antes la instrucción con los documentos de desarrollo.</p>
            <button type="button" className="boton primario" disabled={!ev.sorteada_en}
                    onClick={async () => { if (await confirmar("¿Iniciar la evaluación y congelar la versión?")) hacer("estado", "POST", { estado: "en_curso" }); }}>
              Iniciar la evaluación</button>
          </>
        ) : ev.estado === "en_curso" ? (
          <button type="button" className="boton"
                  onClick={async () => { if (await confirmar("¿Cerrar la evaluación?")) hacer("estado", "POST", { estado: "cerrada" }); }}>
            Cerrar la evaluación</button>
        ) : <p>Evaluación cerrada.</p>}
      </div>
    </div>
  );
}

function ListaDocumentos({ ev, docs, controlar }: { ev: EvaluacionBreve; docs: Documento[] | null; controlar: (d: Documento) => void }) {
  if (!docs) return <div className="cargando">Cargando…</div>;
  if (!docs.length) return <div className="vacio">La evaluación todavía no tiene documentos.</div>;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Documentos · {docs.length}</div>
      <p className="pista" style={{ padding: "0 18px" }}>Los documentos se validan en Descripción, como siempre. Los de prueba se procesan
        una sola vez, con la versión congelada. La validación de control la hace una persona distinta de quien validó.</p>
      <div className="tabla-desplazable">
        <table className="tabla-datos">
          <thead><tr><th>Documento</th><th>Año</th><th>Conjunto</th><th>Estado</th><th className="acciones-celda"><span className="sr-only">Acciones</span></th></tr></thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.instanciacion_id}>
                <td>{d.nombre}</td><td>{d.anio}</td>
                <td>{d.conjunto ? <span className={`insignia ${d.conjunto === "prueba" ? "alerta" : "proceso"}`}>
                  {d.conjunto === "prueba" ? "Prueba" : "Desarrollo"}</span> : <span className="meta">Sin sortear</span>}</td>
                <td>{d.publicado ? <span className="insignia bien">Validado y publicado</span> : <span className="meta">Pendiente</span>}</td>
                <td className="acciones-celda" style={{ width: 230 }}>
                  {!d.publicado && ev.estado !== "preparacion" && <Link className="boton chico" to="/descripcion">Ir a Descripción</Link>}
                  {d.publicado && d.conjunto === "prueba" && ev.estado === "en_curso" &&
                    <button type="button" className="boton chico" onClick={() => controlar(d)}>Validación de control</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Control({ ev, doc }: { ev: EvaluacionBreve; doc: Documento }) {
  const [datos, setDatos] = useState<{ documento: { texto: string | null }; propuestas: PropuestaControl[] } | null>(null);
  const [error, setError] = useState("");
  const cargar = useCallback(() => {
    pedir<{ documento: { texto: string | null }; propuestas: PropuestaControl[] }>(`/api/evaluacion/${ev.id}/control/${doc.instanciacion_id}`)
      .then(setDatos).catch((err) => setError(mensaje(err, "No se pudo abrir la validación de control.")));
  }, [ev.id, doc.instanciacion_id]);
  useEffect(cargar, [cargar]);
  async function decidir(p: PropuestaControl, decision: string) {
    try {
      await pedir(`/api/evaluacion/${ev.id}/control/decisiones/${p.evento_id}`, { method: "PUT", body: JSON.stringify({ decision }) });
      cargar();
    } catch (err) {
      setError(mensaje(err, "No se pudo registrar."));
    }
  }
  if (error) return <div className="aviso error" role="alert">{error}</div>;
  if (!datos) return <div className="cargando">Cargando…</div>;
  return (
    <>
      <p className="pista">Decida sobre cada propuesta original del motor leyendo el documento, sin ver lo que decidió la primera
        validadora. Su decisión no cambia la descripción publicada.</p>
      <div className="tarjeta" style={{ maxHeight: 220, overflow: "auto", whiteSpace: "pre-wrap", padding: 12 }}>{datos.documento.texto}</div>
      <table className="tabla-datos">
        <thead><tr><th>Tipo</th><th>Propuesta del motor</th><th className="num">Certeza</th><th>Su decisión</th></tr></thead>
        <tbody>
          {datos.propuestas.map((p) => (
            <tr key={p.evento_id}>
              <td>{p.tipo_nombre}</td><td>{p.propuesto || "—"}</td><td className="num">{num(p.confianza, 2)}</td>
              <td>
                <select className="selector" aria-label={`Decisión sobre ${p.propuesto}`} value={p.mi_decision || ""}
                        onChange={(e) => decidir(p, e.target.value)}>
                  <option value="" disabled>Elegir…</option>
                  <option value="aceptada">Aceptar</option>
                  <option value="corregida">Corregir</option>
                  <option value="rechazada">Rechazar</option>
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="meta">{datos.propuestas.filter((p) => p.mi_decision).length} de {datos.propuestas.length} decididas.</p>
    </>
  );
}

function VerResultados({ ev }: { ev: EvaluacionBreve }) {
  const [r, setR] = useState<Resultados | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    pedir<Resultados>(`/api/evaluacion/${ev.id}/resultados`).then(setR).catch((err) => setError(mensaje(err, "No se pudieron calcular los resultados.")));
  }, [ev.id]);
  if (error) return <div className="aviso error" role="alert">{error}</div>;
  if (!r) return <div className="cargando">Calculando…</div>;
  const m = r.metricas;
  const lectura: Record<string, string> = {
    f1: m.f1 === null ? "" : `Rendimiento global de ${num(m.f1, 2)} sobre 1`,
    precision: m.precision === null ? "" : `De cada 100 datos que propuso el motor, ${Math.round(m.precision * 100)} eran correctos`,
    exhaustividad: m.exhaustividad === null ? "" : `De cada 100 datos de la descripción validada, el motor encontró ${Math.round(m.exhaustividad * 100)}`,
  };
  const estado = (c: boolean | null) => c === null ? <span className="meta">—</span>
    : <span className={`insignia ${c ? "bien" : "error"}`}>{c ? "Cumple" : "No cumple"}</span>;
  return (
    <>
      {r.avisos.map((a) => <div key={a} className="aviso" role="status">{a}</div>)}
      <div className="filtros" style={{ alignItems: "center" }}>
        <button type="button" className="boton" onClick={() => descargar(`/api/evaluacion/${ev.id}/resultados/hoja-de-calculo`)}>
          Descargar en Excel (para el Anexo D)</button>
        <span className="meta">{m.documentos} documento(s) de prueba · {r.decisiones} decisiones</span>
        {r.dictamen.hipotesis && <span className={`insignia ${r.dictamen.hipotesis === "se sostiene" ? "bien" : "error"}`}>
          La hipótesis {r.dictamen.hipotesis}</span>}
      </div>
      <div className="tarjeta">
        <div className="tarjeta-cab">Medidas y dictamen</div>
        <div className="tabla-desplazable">
          <table className="tabla-datos">
            <thead><tr><th>Medida</th><th className="num">Valor</th><th className="num">Intervalo 95 %</th><th className="num">Umbral</th>
              <th>Dictamen (límite inferior)</th><th>Cómo se lee</th></tr></thead>
            <tbody>
              {MEDIDAS.map(([k, n, ayuda]) => (
                <tr key={k}>
                  <td title={ayuda}><strong>{n}</strong></td><td className="num">{num(m[k])}</td>
                  <td className="num">{num(m.intervalos[k].inferior)} a {num(m.intervalos[k].superior)}</td>
                  <td className="num">{num(r.dictamen[k].umbral, 2)}</td><td>{estado(r.dictamen[k].cumple)}</td><td>{lectura[k]}</td>
                </tr>
              ))}
              <tr><td>Medida F1 macro</td><td className="num">{num(m.f1_macro)}</td><td colSpan={4} className="meta">Promedio entre tipos de entidad</td></tr>
              <tr><td>Acuerdo entre validadoras</td><td className="num">{pct(r.acuerdo.porcentaje)}</td>
                <td className="num meta">{r.acuerdo.iguales} de {r.acuerdo.pares}</td><td className="num">{pct(r.acuerdo.umbral)}</td>
                <td>{estado(r.acuerdo.cumple)}</td><td className="meta">{r.acuerdo.documentos} documento(s) con validación de control</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <div className="resumen-preservacion">
        <div className="cifra bien"><strong>{m.conteo.aceptada}</strong><span>Aceptadas (aciertos)</span></div>
        <div className="cifra alerta"><strong>{m.conteo.corregida}</strong><span>Corregidas</span></div>
        <div className="cifra error"><strong>{m.conteo.rechazada}</strong><span>Rechazadas (inventadas)</span></div>
        <div className="cifra"><strong>{m.conteo.agregada}</strong><span>Agregadas (omitidas)</span></div>
      </div>
      <div className="tarjeta">
        <div className="tarjeta-cab">Por tipo de dato</div>
        <div className="tabla-desplazable">
          <table className="tabla-datos">
            <thead><tr><th>Tipo</th><th className="num">Aceptadas</th><th className="num">Corregidas</th><th className="num">Rechazadas</th>
              <th className="num">Agregadas</th><th className="num">Precisión</th><th className="num">Exhaustividad</th><th className="num">F1</th></tr></thead>
            <tbody>
              {m.por_tipo.map((t) => (
                <tr key={t.tipo}>
                  <td>{TIPO[t.tipo] || t.tipo}{t.texto_libre && <span className="meta"> · texto libre, fuera de la F1 global</span>}</td>
                  <td className="num">{t.aceptada}</td><td className="num">{t.corregida}</td><td className="num">{t.rechazada}</td>
                  <td className="num">{t.agregada}</td><td className="num">{num(t.precision)}</td><td className="num">{num(t.exhaustividad)}</td>
                  <td className="num">{num(t.f1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {r.causas.length > 0 && (
        <div className="tarjeta">
          <div className="tarjeta-cab">Causas de error</div>
          <ul className="lista-simple" style={{ padding: "6px 36px 12px" }}>{r.causas.map((c) => <li key={c.causa}>{c.nombre} · {c.cantidad}</li>)}</ul>
        </div>
      )}
    </>
  );
}

function Errores({ ev }: { ev: EvaluacionBreve }) {
  const [lista, setLista] = useState<ErrorMotor[] | null>(null);
  const [error, setError] = useState("");
  const cargar = useCallback(() => {
    pedir<ErrorMotor[]>(`/api/evaluacion/${ev.id}/errores`).then(setLista).catch((err) => setError(mensaje(err, "No se pudieron cargar.")));
  }, [ev.id]);
  useEffect(cargar, [cargar]);
  async function clasificar(e: ErrorMotor, causa: string) {
    try {
      await pedir(`/api/evaluacion/${ev.id}/errores/${e.evento_id}`, { method: "PUT", body: JSON.stringify({ causa, nota: e.nota }) });
      cargar();
    } catch (err) {
      setError(mensaje(err, "No se pudo registrar la causa."));
    }
  }
  if (error) return <div className="aviso error" role="alert">{error}</div>;
  if (!lista) return <div className="cargando">Cargando…</div>;
  if (!lista.length) return <div className="vacio">No hay errores del motor en los documentos de prueba validados.</div>;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Errores del motor · {lista.length} · {lista.filter((e) => e.causa).length} con causa</div>
      <div className="tabla-desplazable">
        <table className="tabla-datos">
          <thead><tr><th>Documento</th><th>Tipo</th><th>Decisión</th><th>Propuesto</th><th>Valor final</th><th>Causa</th></tr></thead>
          <tbody>
            {lista.map((e) => (
              <tr key={e.evento_id}>
                <td>{e.documento}</td><td>{e.tipo_nombre}</td>
                <td><span className={`insignia ${DECISION[e.decision].clase}`}>{DECISION[e.decision].texto}</span></td>
                <td>{e.propuesto || "—"}</td><td>{e.final || "—"}</td>
                <td>
                  <select className="selector" aria-label="Causa del error" value={e.causa || ""} onChange={(x) => clasificar(e, x.target.value)}>
                    <option value="" disabled>Elegir…</option>
                    {CAUSAS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
