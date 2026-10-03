import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FAMILIAS, LienzoGrafo, MuestraFamilia, NOMBRE_FAMILIA, type DatosGrafo, type Familia } from "@/components/Grafo";
import { EstadoVacio } from "@/components/EstadoVacio";
import { ErrorAPI, descargar, pedir, puede } from "@/lib/api";
import { useSesion } from "@/lib/sesion";

interface Opcion { clave: string; nombre: string; uri_rico?: string | null }
interface Raiz { clave: string; etiqueta: string; subtitulo: string; familia: Familia }
interface Opciones { familias: Opcion[]; relaciones: Opcion[]; estados: Opcion[]; raices: Raiz[]; saltos_maximos: number }
interface Campo { campo: string; valor: string; icono: string }
interface RelacionFicha {
  codigo_ric: string; etiqueta: string; uri_rico: string | null; sentido: "sale" | "entra";
  otro: { clave: string; etiqueta: string; familia: Familia }; registrada: string | null;
}
interface FichaEntidad {
  clave: string; id: string; tipo: string; clase: string; familia: Familia; familia_nombre: string; etiqueta: string;
  resumen: Campo[]; atributos: Campo[]; relaciones_total: number; relaciones: RelacionFicha[];
}
interface Filtros { familias: string[]; relaciones: string[]; desde: string; hasta: string; estados: string[] }
const SIN_FILTROS: Filtros = { familias: [], relaciones: [], desde: "", hasta: "", estados: [] };

const trazo = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
const ICONO_CAMPO: Record<string, JSX.Element> = {
  identificador: <path d="M5 9h14M5 15h14M10 4l-2 16M16 4l-2 16" />,
  titulo: <path d="M5 6h14M12 6v13" />,
  nivel: <path d="M4 7h16M7 12h10M10 17h4" />,
  texto: <path d="M5 6h14M5 10h14M5 14h10M5 18h7" />,
  fecha: <><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M8 3v4M16 3v4" /></>,
  estado: <><circle cx="12" cy="12" r="8" /><path d="M8.5 12.5l2.3 2.3 4.7-4.8" /></>,
  forma: <path d="M3.5 12.5l9-9H20v7.5l-9 9z" />,
  idioma: <><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17M12 3.5c2.5 2.5 2.5 14.5 0 17M12 3.5c-2.5 2.5-2.5 14.5 0 17" /></>,
  acceso: <><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>,
  ubicacion: <><path d="M12 21s-6-5.8-6-11a6 6 0 0 1 12 0c0 5.2-6 11-6 11z" /><circle cx="12" cy="10" r="2.2" /></>,
  extension: <path d="M6 3h12v18H6zM9 8h6M9 12h6" />,
};

function consulta(f: Filtros, saltos: number, fondoId: string): URLSearchParams {
  const p = new URLSearchParams({ fondo_id: fondoId, saltos: String(saltos) });
  f.familias.forEach((x) => p.append("tipo_entidad", x));
  f.relaciones.forEach((x) => p.append("tipo_relacion", x));
  f.estados.forEach((x) => p.append("estado", x));
  if (f.desde) p.set("fecha_desde", f.desde);
  if (f.hasta) p.set("fecha_hasta", f.hasta);
  return p;
}

function activos(f: Filtros): number {
  return [f.familias.length, f.relaciones.length, f.desde || f.hasta, f.estados.length].filter(Boolean).length;
}

function alternar(lista: string[], valor: string): string[] {
  return lista.includes(valor) ? lista.filter((x) => x !== valor) : [...lista, valor];
}

function rutaEntidad(tipo: string, id: string) {
  return `/api/grafo/${tipo}/${id}`;
}

// --- Panel de filtros -----------------------------------------------------------------------------

function PanelFiltros({ opciones, filtros, cambiar, cerrar }: {
  opciones: Opciones; filtros: Filtros; cambiar: (f: Filtros) => void; cerrar: () => void;
}) {
  const caja = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const fuera = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !caja.current?.contains(e.target as Node)) cerrar();
    };
    document.addEventListener("mousedown", fuera);
    document.addEventListener("keydown", fuera);
    return () => {
      document.removeEventListener("mousedown", fuera);
      document.removeEventListener("keydown", fuera);
    };
  }, [cerrar]);
  return (
    <div className="panel-filtros-grafo" ref={caja} role="dialog" aria-label="Filtros del grafo">
      <fieldset>
        <legend>Tipo de entidad</legend>
        <div className="casillas">
          {FAMILIAS.map((f) => (
            <label key={f.clave}>
              <input type="checkbox" checked={filtros.familias.includes(f.clave)}
                     onChange={() => cambiar({ ...filtros, familias: alternar(filtros.familias, f.clave) })} />
              <MuestraFamilia familia={f.clave} tamano={16} /> {f.nombre}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>Tipo de relación</legend>
        <div className="casillas desplazable">
          {opciones.relaciones.map((r) => (
            <label key={r.clave} title={r.uri_rico || undefined}>
              <input type="checkbox" checked={filtros.relaciones.includes(r.clave)}
                     onChange={() => cambiar({ ...filtros, relaciones: alternar(filtros.relaciones, r.clave) })} />
              {r.nombre}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>Rango de fechas</legend>
        <div className="fila-fechas">
          <label>Desde <input type="date" value={filtros.desde} onChange={(e) => cambiar({ ...filtros, desde: e.target.value })} /></label>
          <label>Hasta <input type="date" value={filtros.hasta} onChange={(e) => cambiar({ ...filtros, hasta: e.target.value })} /></label>
        </div>
        <p className="pista">Lo que no tiene fecha no se excluye: no hay evidencia de que caiga fuera.</p>
      </fieldset>
      <fieldset>
        <legend>Estado de la descripción</legend>
        <div className="casillas">
          {opciones.estados.map((e) => (
            <label key={e.clave}>
              <input type="checkbox" checked={filtros.estados.includes(e.clave)}
                     onChange={() => cambiar({ ...filtros, estados: alternar(filtros.estados, e.clave) })} />
              {e.nombre}
            </label>
          ))}
        </div>
        <p className="pista">Los borradores nunca se dibujan: solo lo que una persona validó y publicó.</p>
      </fieldset>
      <div className="acciones">
        <button type="button" className="boton chico" disabled={!activos(filtros)} onClick={() => cambiar(SIN_FILTROS)}>Limpiar filtros</button>
        <button type="button" className="boton chico primario" onClick={cerrar}>Listo</button>
      </div>
    </div>
  );
}

// --- Panel de detalle de la entidad seleccionada --------------------------------------------------

function PanelDetalle({ clave, fondoId, cerrar, recentrar, abrirFicha, exportar }: {
  clave: string; fondoId: string; cerrar: () => void; recentrar: (clave: string) => void;
  abrirFicha: (id: string) => void; exportar: (formato: "turtle" | "jsonld") => void;
}) {
  const { usuario } = useSesion();
  const navegar = useNavigate();
  const [ficha, setFicha] = useState<FichaEntidad | null>(null);
  const [error, setError] = useState("");
  const [pestana, setPestana] = useState<"resumen" | "atributos" | "relaciones">("resumen");
  const [tipo, id] = clave.split(":");

  useEffect(() => {
    setFicha(null);
    setError("");
    pedir<FichaEntidad>(`${rutaEntidad(tipo, id)}/ficha?fondo_id=${fondoId}`).then(setFicha)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo abrir la entidad."));
  }, [tipo, id, fondoId]);

  // Abrir entidad: su ficha completa en el módulo que la administra.
  let abrir: (() => void) | null = null;
  let porque = "";
  if (ficha) {
    if (tipo === "recurso_documental" && ficha.clase !== "fondo") abrir = () => abrirFicha(id);
    else if (tipo === "recurso_documental") abrir = () => navegar("/instrumentos");
    else if (tipo === "entidad_vocabulario" && puede(usuario, "vocabularios")) abrir = () => navegar(`/vocabularios/${id}`);
    else if (tipo === "instanciacion" && puede(usuario, "preservacion")) abrir = () => navegar(`/preservacion/instanciacion/${id}`);
    else porque = tipo === "fecha" ? "Una fecha no tiene ficha propia: se edita en la descripción que la cita." : "Su rol no tiene acceso a ese módulo.";
  }

  return (
    <aside className="detalle-grafo" aria-label="Entidad seleccionada" aria-live="polite">
      <div className="detalle-cab">
        <span>Entidad seleccionada</span>
        <button type="button" className="ayuda-cerrar" aria-label="Cerrar el detalle" onClick={cerrar}>×</button>
      </div>
      {error && <div className="aviso error">{error}</div>}
      {!ficha && !error && <div className="cargando">Cargando…</div>}
      {ficha && (
        <>
          <span className={`insignia insignia-familia f-${ficha.familia}`}>
            <MuestraFamilia familia={ficha.familia} tamano={16} /> {ficha.familia_nombre}
          </span>
          <h2 className="titulo-nodo">{ficha.etiqueta}</h2>
          <div className="pestanas compactas" role="tablist">
            {([["resumen", "Resumen"], ["atributos", `Atributos (${ficha.atributos.length})`],
               ["relaciones", `Relaciones (${ficha.relaciones_total})`]] as const).map(([k, nombre]) => (
              <button key={k} type="button" role="tab" aria-selected={pestana === k}
                      className={`pestana${pestana === k ? " activa" : ""}`} onClick={() => setPestana(k)}>{nombre}</button>
            ))}
          </div>
          <div className="detalle-cuerpo">
            {pestana !== "relaciones" && (
              (pestana === "resumen" ? ficha.resumen : ficha.atributos).length === 0
                ? <p className="pista">Esta entidad no tiene más datos registrados.</p>
                : (
                  <dl className="campos-icono">
                    {(pestana === "resumen" ? ficha.resumen : ficha.atributos).map((c) => (
                      <div key={c.campo}>
                        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" {...trazo}>{ICONO_CAMPO[c.icono]}</svg>
                        <dt>{c.campo}</dt>
                        <dd>{c.valor}</dd>
                      </div>
                    ))}
                  </dl>
                )
            )}
            {pestana === "relaciones" && (
              <>
                <ul className="lista-relaciones">
                  {ficha.relaciones.map((r) => (
                    <li key={`${r.codigo_ric}-${r.otro.clave}-${r.sentido}`}>
                      {r.sentido === "entra" && (
                        <>
                          <MuestraFamilia familia={r.otro.familia} tamano={14} />{" "}
                          <button type="button" className="enlace" onClick={() => recentrar(r.otro.clave)}
                                  title="Recentrar el grafo en esa entidad, con los mismos filtros">{r.otro.etiqueta}</button>
                          {" → "}
                        </>
                      )}
                      <span title={r.uri_rico || undefined}>{r.etiqueta}</span>
                      {r.sentido === "entra" ? <span className="meta"> → esta entidad</span> : (
                        <>
                          {" → "}
                          <MuestraFamilia familia={r.otro.familia} tamano={14} />{" "}
                          <button type="button" className="enlace" onClick={() => recentrar(r.otro.clave)}
                                  title="Recentrar el grafo en esa entidad, con los mismos filtros">{r.otro.etiqueta}</button>
                        </>
                      )}
                      <span className="meta"> · {NOMBRE_FAMILIA[r.otro.familia]}</span>
                    </li>
                  ))}
                </ul>
                {ficha.relaciones_total > ficha.relaciones.length && (
                  <p className="pista">
                    Se muestran las {ficha.relaciones.length} más recientes de {ficha.relaciones_total}.{" "}
                    <button type="button" className="enlace"
                            onClick={() => descargar(`${rutaEntidad(tipo, id)}/relaciones/exportar?fondo_id=${fondoId}`)}>
                      Exportar todas a Excel
                    </button>
                  </p>
                )}
              </>
            )}
          </div>
          <div className="detalle-pie">
            <button type="button" className="boton primario ancho" disabled={!abrir} onClick={() => abrir?.()}
                    title={porque || undefined}>Abrir entidad</button>
            {porque && <p className="pista">{porque}</p>}
            <div className="dos-botones">
              <button type="button" className="boton chico" onClick={() => recentrar(clave)}>Ver en contexto</button>
              <details className="menu-exportar">
                <summary className="boton chico">Exportar</summary>
                <div>
                  <button type="button" className="enlace" onClick={() => exportar("turtle")}>Turtle (.ttl)</button>
                  <button type="button" className="enlace" onClick={() => exportar("jsonld")}>JSON-LD (.jsonld)</button>
                </div>
              </details>
            </div>
          </div>
        </>
      )}
    </aside>
  );
}

// --- Pantalla -------------------------------------------------------------------------------------

export function PestanaGrafo({ fondo, centro, centrar, abrirFicha }: {
  fondo: { id: string; titulo: string };
  centro: string | null;
  centrar: (clave: string) => void;
  abrirFicha: (id: string) => void;
}) {
  const raizClave = centro || `recurso_documental:${fondo.id}`;
  const [saltos, setSaltos] = useState(1);
  const [filtros, setFiltros] = useState<Filtros>(SIN_FILTROS);
  const [opciones, setOpciones] = useState<Opciones | null>(null);
  const [datos, setDatos] = useState<DatosGrafo | null>(null);
  const [cargando, setCargando] = useState(false);
  const [seleccion, setSeleccion] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [verFiltros, setVerFiltros] = useState(false);
  const [completa, setCompleta] = useState(false);
  const [busqueda, setBusqueda] = useState("");
  const [enfoque, setEnfoque] = useState<{ clave: string; vez: number } | null>(null);
  const selector = useRef<HTMLSelectElement>(null);

  useEffect(() => {
    pedir<Opciones>(`/api/grafo/opciones?fondo_id=${fondo.id}`).then(setOpciones).catch(() => setOpciones(null));
  }, [fondo.id]);

  // Cada cambio de raíz, saltos o filtros pide al servidor el subgrafo acotado.
  useEffect(() => {
    const [tipo, id] = raizClave.split(":");
    setError("");
    setCargando(true);
    const vivo = { si: true };
    pedir<DatosGrafo>(`${rutaEntidad(tipo, id)}?${consulta(filtros, saltos, fondo.id)}`)
      .then((d) => vivo.si && setDatos(d))
      .catch((err) => vivo.si && setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar el grafo."))
      .finally(() => vivo.si && setCargando(false));
    return () => { vivo.si = false; };
  }, [raizClave, saltos, filtros, fondo.id]);

  useEffect(() => setSeleccion(null), [raizClave]);
  // Si un filtro saca del dibujo la entidad seleccionada, su panel se cierra.
  useEffect(() => {
    if (seleccion && datos && !datos.nodos.some((n) => n.clave === seleccion)) setSeleccion(null);
  }, [datos, seleccion]);

  useEffect(() => {
    if (!completa) return;
    const tecla = (e: KeyboardEvent) => e.key === "Escape" && setCompleta(false);
    document.addEventListener("keydown", tecla);
    document.body.classList.add("grafo-completo");
    return () => {
      document.removeEventListener("keydown", tecla);
      document.body.classList.remove("grafo-completo");
    };
  }, [completa]);

  const raiz = useMemo(() => opciones?.raices.find((r) => r.clave === raizClave)
    || datos?.nodos.find((n) => n.clave === raizClave), [opciones, datos, raizClave]);
  const numFiltros = activos(filtros);

  function buscar(texto: string) {
    setBusqueda(texto);
    const t = texto.trim().toLowerCase();
    if (!t || !datos) return;
    const hallado = datos.nodos.find((n) => n.etiqueta.toLowerCase().includes(t));
    if (hallado) {
      setEnfoque({ clave: hallado.clave, vez: Date.now() });
      setSeleccion(hallado.clave);
    }
  }

  function exportar(formato: "turtle" | "jsonld") {
    const [tipo, id] = raizClave.split(":");
    const p = consulta(filtros, saltos, fondo.id);
    p.set("formato", formato);
    descargar(`${rutaEntidad(tipo, id)}/exportar?${p}`)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo exportar."));
  }

  // El lienzo nunca queda en blanco sin explicación.
  const vacio = datos && datos.aristas.length === 0;
  const hallazgo = busqueda.trim() && datos && !datos.nodos.some((n) => n.etiqueta.toLowerCase().includes(busqueda.trim().toLowerCase()));

  return (
    <div className={`vista-grafo${completa ? " completa" : ""}`}>
      <div className="cabecera-nivel">
        <div>
          <h1>Grafo del fondo</h1>
          <label className="selector-raiz">
            <span className="sr-only">Entidad raíz del grafo</span>
            {raiz && "familia" in raiz && <MuestraFamilia familia={raiz.familia} tamano={18} />}
            <select ref={selector} value={raizClave} onChange={(e) => centrar(e.target.value === `recurso_documental:${fondo.id}` ? "" : e.target.value)}>
              {!opciones?.raices.some((r) => r.clave === raizClave) && raiz && <option value={raizClave}>{raiz.etiqueta}</option>}
              {opciones && FAMILIAS.map((f) => {
                const de = opciones.raices.filter((r) => r.familia === f.clave);
                return de.length ? (
                  <optgroup key={f.clave} label={f.nombre}>
                    {de.map((r) => <option key={r.clave} value={r.clave}>{r.etiqueta}{r.subtitulo && f.clave === "RecordSet" ? ` · ${r.subtitulo}` : ""}</option>)}
                  </optgroup>
                ) : null;
              })}
            </select>
          </label>
        </div>
      </div>

      <div className="barra-grafo">
        <label className="buscar-grafo">
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" {...trazo}><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2" /></svg>
          <input type="search" placeholder="Buscar en el grafo…" aria-label="Buscar una entidad en el grafo"
                 value={busqueda} onChange={(e) => buscar(e.target.value)} />
        </label>
        <div className="envoltura-filtros">
          <button type="button" className={`boton${numFiltros ? " con-filtros" : ""}`} aria-haspopup="dialog" aria-expanded={verFiltros}
                  onClick={() => setVerFiltros(!verFiltros)}>
            <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" {...trazo}><path d="M4 5h16l-6 7.5V19l-4-2v-4.5z" /></svg>
            Filtros {numFiltros > 0 && <span className="contador" aria-label={`${numFiltros} activos`}>{numFiltros}</span>}
          </button>
          {verFiltros && opciones && (
            <PanelFiltros opciones={opciones} filtros={filtros} cambiar={setFiltros} cerrar={() => setVerFiltros(false)} />
          )}
        </div>
        <div className="segmentado" role="radiogroup" aria-label="Profundidad del recorrido">
          {[1, 2, 3].map((n) => (
            <button key={n} type="button" role="radio" aria-checked={saltos === n} className={saltos === n ? "elegido" : ""}
                    onClick={() => setSaltos(n)}>{n === 1 ? "Relaciones directas" : `${n} saltos`}</button>
          ))}
        </div>
        <button type="button" className="boton" onClick={() => setCompleta(!completa)} aria-pressed={completa}>
          <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" {...trazo}>
            {completa ? <path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" /> : <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />}
          </svg>
          {completa ? "Salir de pantalla completa" : "Pantalla completa"}
        </button>
      </div>

      {error && <div className="aviso error" role="alert">{error}</div>}
      {hallazgo && <div className="aviso" role="status">Ninguna entidad visible se llama así. La búsqueda no cambia los filtros.</div>}
      {datos?.truncado && (
        <div className="aviso alerta" role="status">
          El grafo se truncó en {datos.maximo_nodos} entidades para seguir siendo legible. Reduzca los saltos, aplique un
          filtro o elija una entidad raíz más específica.
        </div>
      )}
      {!datos ? <div className="cargando">Cargando…</div> : (
        <div className={`grafo-y-detalle${seleccion && !completa ? " con-detalle" : ""}${cargando ? " recargando" : ""}`}>
          <div className="contenedor-lienzo">
            <LienzoGrafo datos={datos} seleccion={seleccion} alSeleccionar={setSeleccion} enfoque={enfoque} />
            {vacio && (
              <div className="vacio-lienzo">
                {numFiltros ? (
                  <EstadoVacio icono="filtro" titulo="Ningún nodo pasa los filtros activos"
                               texto={`Con ${numFiltros} filtro${numFiltros === 1 ? "" : "s"} y ${saltos} salto${saltos === 1 ? "" : "s"}, no queda ninguna entidad relacionada con «${raiz?.etiqueta}». El recorrido no pasa por lo filtrado: para llegar más lejos, incluya también los tipos intermedios (agrupaciones, documentos).`}
                               accion={{ texto: "Limpiar filtros", alHacer: () => setFiltros(SIN_FILTROS) }} />
                ) : (
                  <EstadoVacio icono="grafo" titulo="Esta entidad todavía no tiene relaciones registradas"
                               texto="Las relaciones aparecen cuando se publica una descripción que la cita. Mientras tanto, explore desde otra entidad."
                               accion={{ texto: "Elegir otra entidad raíz", alHacer: () => selector.current?.focus() }} />
                )}
              </div>
            )}
          </div>
          {seleccion && !completa && (
            <PanelDetalle key={seleccion} clave={seleccion} fondoId={fondo.id} cerrar={() => setSeleccion(null)}
                          recentrar={(c) => centrar(c === `recurso_documental:${fondo.id}` ? "" : c)}
                          abrirFicha={abrirFicha} exportar={exportar} />
          )}
        </div>
      )}
    </div>
  );
}
