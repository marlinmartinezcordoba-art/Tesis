import { Fragment, useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ErrorAPI, pedir, puede as tienePermiso } from "@/lib/api";
import { SUBTIPO_NOMBRE } from "@/lib/descripcion";
import { useFondo } from "@/lib/fondo";
import { fecha } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";
import { useVista } from "@/components/Marco";
import { EstadoVacio } from "@/components/EstadoVacio";
import { Tesauros } from "@/components/Tesauros";
import { ImportarEac } from "@/components/ImportarEac";
import { NIVEL_FICHA } from "@/components/FichaAutoridad";
import { Encabezado, MenuAcciones, Paginacion } from "@/components/Encabezado";

const POR_PAGINA = 25;
const TRAZO = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
// Ícono por clase: el tipo se reconoce por la forma y por la insignia con su nombre, no solo por el color.
const ICONO_CLASE: Record<string, JSX.Element> = {
  agente: <svg viewBox="0 0 24 24" {...TRAZO}><circle cx="12" cy="8" r="3.4" /><path d="M5 20c1.2-4 4.4-6 7-6s5.8 2 7 6" /></svg>,
  lugar: <svg viewBox="0 0 24 24" {...TRAZO}><path d="M12 21s-6.5-6.2-6.5-11.2a6.5 6.5 0 0 1 13 0C18.5 14.8 12 21 12 21z" /><circle cx="12" cy="9.8" r="2.3" /></svg>,
  forma_documental: <svg viewBox="0 0 24 24" {...TRAZO}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></svg>,
  actividad: <svg viewBox="0 0 24 24" {...TRAZO}><path d="M12 3l9 5-9 5-9-5z" /><path d="M3 13l9 5 9-5" /></svg>,
  tipo_actividad: <svg viewBox="0 0 24 24" {...TRAZO}><path d="M12 3l9 5-9 5-9-5z" /><path d="M3 13l9 5 9-5M3 17.5l9 5 9-5" /></svg>,
  mandato: <svg viewBox="0 0 24 24" {...TRAZO}><path d="M5 21h14M7 21V10M17 21V10M12 21V10M4 10l8-6 8 6z" /></svg>,
  materia: <svg viewBox="0 0 24 24" {...TRAZO}><path d="M20 12l-8 8-9-9V3h8z" /><circle cx="7.5" cy="7.5" r="1.4" /></svg>,
};
const ICONO_GENERICO = <svg viewBox="0 0 24 24" {...TRAZO}><circle cx="12" cy="12" r="8" /></svg>;
import {
  CLASES, CLASE_INSIGNIA, CLASE_NOMBRE, CLASE_NOMBRE_PLURAL, accionesTexto, claseRicDe, conexionesTexto, esMecanismo,
  type ClaseVocabulario, type EntidadVocabulario, type ParametrosFusion, type Sugerencia,
} from "@/lib/vocabulario";

type Orden = "conexiones_desc" | "conexiones_asc" | "nombre";

interface NodoFuncion {
  id: string;
  nombre: string;
  series: { id: string; titulo: string; nivel: string }[];
  especificos: NodoFuncion[];
}

// Árbol de funciones: los tipos de actividad del fondo unidos por
// skos:broader / skos:narrower, con tantos niveles como haya, y la serie
// que produce cada función (vínculo de la TRD).
function ArbolFunciones({ fondoId }: { fondoId: string }) {
  const [arbol, setArbol] = useState<NodoFuncion[] | null>(null);
  useEffect(() => {
    pedir<NodoFuncion[]>(`/api/vocabulario/funciones/arbol?fondo_id=${fondoId}`).then(setArbol).catch(() => setArbol([]));
  }, [fondoId]);
  const rama = (n: NodoFuncion) => (
    <li key={n.id}>
      <Link to={`/vocabularios/${n.id}`}>{n.nombre}</Link>
      {n.series.map((s) => <span key={s.id} className="insignia acento" style={{ marginLeft: 8 }}>Serie: {s.titulo}</span>)}
      {n.especificos.length > 0 && <ul>{n.especificos.map(rama)}</ul>}
    </li>
  );
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">
        <span>Árbol de funciones</span>
        <span className="meta">skos:broader / skos:narrower — complemento de RiC-O para la jerarquía de la TRD</span>
      </div>
      <div className="tarjeta-cuerpo">
        {arbol === null ? "Cargando…" : arbol.length === 0
          ? <div className="vacio">Todavía no hay tipos de actividad en el fondo.</div>
          : <ul className="arbol-funciones">{arbol.map(rama)}</ul>}
      </div>
    </div>
  );
}

// Una sugerencia: las dos entidades lado a lado, y el archivista decide.
// El sistema propone como definitiva la que tiene más conexiones, pero
// la elección es de la persona.
function TarjetaSugerencia({ s, puede, alResolver }: { s: Sugerencia; puede: boolean; alResolver: (aviso: string) => void }) {
  const [a, b] = s.entidades;
  const [definitiva, setDefinitiva] = useState(a.conexiones >= b.conexiones ? a.id : b.id);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  const absorbida = definitiva === a.id ? b : a;
  const queda = definitiva === a.id ? a : b;

  async function decidir(accion: "aprobar" | "descartar") {
    setOcupado(true);
    setError("");
    try {
      await pedir(`/api/vocabulario/sugerencias-fusion/${s.id}/${accion}`, {
        method: "POST",
        body: accion === "aprobar" ? JSON.stringify({ definitiva_id: definitiva }) : undefined,
      });
      alResolver(accion === "aprobar"
        ? `«${absorbida.nombre}» se fusionó en «${queda.nombre}». Sus documentos ahora apuntan a la definitiva.`
        : `Se marcaron como distintas «${a.nombre}» y «${b.nombre}». No se volverán a sugerir.`);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo registrar la decisión.");
      setOcupado(false);
    }
  }

  return (
    <div className="tarjeta sugerencia">
      <div className="tarjeta-cab">
        <span><span className={`insignia ${CLASE_INSIGNIA[s.clase]}`}>{CLASE_NOMBRE[s.clase]}</span></span>
        <span className="meta">Detectada {fecha(s.creada_en)}</span>
      </div>
      <div className="par-fusion con-centro">
        {s.entidades.map((e, i) => (
          <Fragment key={e.id}>
            {i === 1 && (
              <div className="similitud" aria-label={`Similitud ${Math.round(s.similitud * 100)} %`}>
                <strong>{Math.round(s.similitud * 100)} %</strong>
                <span>{s.motivo === "identificador" ? "mismo identificador externo"
                  : s.motivo === "otra_forma" ? "similitud (otra forma del nombre)" : "similitud"}</span>
              </div>
            )}
            <label className={`candidata${definitiva === e.id ? " elegida" : ""}`}>
              {puede && (
                <input type="radio" name={`def-${s.id}`} checked={definitiva === e.id} onChange={() => setDefinitiva(e.id)} />
              )}
              <span>
                <span className="nombre">{e.nombre}</span>
                <span className="meta">
                  {e.subtipo ? `${SUBTIPO_NOMBRE[e.subtipo] || e.subtipo} · ` : ""}{conexionesTexto(e.conexiones)} ·{" "}
                  {e.fondo_registro && <>registrada en «{e.fondo_registro.titulo}» · </>}
                  <Link to={`/vocabularios/${e.id}`}>ver documentos</Link>
                </span>
                {puede && definitiva === e.id && <span className="insignia bien" style={{ marginTop: 6 }}>Queda como definitiva</span>}
              </span>
            </label>
          </Fragment>
        ))}
      </div>
      {error && <div className="aviso error" role="alert" style={{ margin: "0 16px 12px" }}>{error}</div>}
      {puede && (
        <div className="confirmar">
          <span className="meta">
            Si aprueba, {absorbida.conexiones === 1 ? "el documento" : `los ${conexionesTexto(absorbida.conexiones)}`} de «{absorbida.nombre}»{" "}
            {absorbida.conexiones === 1 ? "pasa" : "pasan"} a «{queda.nombre}».
          </span>
          <div className="acciones">
            <button type="button" className="boton chico" disabled={ocupado} onClick={() => decidir("descartar")}>Son distintas</button>
            <button type="button" className="boton chico primario" disabled={ocupado} onClick={() => decidir("aprobar")}>Aprobar fusión</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Parametros({ esAdmin }: { esAdmin: boolean }) {
  const [p, setP] = useState<ParametrosFusion | null>(null);
  const [editando, setEditando] = useState<ParametrosFusion | null>(null);
  const [mensaje, setMensaje] = useState<{ tipo: "bien" | "error"; texto: string } | null>(null);

  useEffect(() => {
    pedir<ParametrosFusion>("/api/vocabulario/parametros").then(setP).catch(() => undefined);
  }, []);

  async function guardar() {
    if (!editando) return;
    try {
      setP(await pedir<ParametrosFusion>("/api/vocabulario/parametros", { method: "PUT", body: JSON.stringify(editando) }));
      setEditando(null);
      setMensaje({ tipo: "bien", texto: "Criterios guardados. Se aplican en la próxima búsqueda." });
    } catch (err) {
      setMensaje({ tipo: "error", texto: err instanceof ErrorAPI ? err.message : "No se pudieron guardar." });
    }
  }

  if (!p) return null;
  const campo = (clave: keyof ParametrosFusion, etiqueta: string, pista: string) => (
    <div className="campo">
      <label htmlFor={`p-${clave}`}>{etiqueta}</label>
      <input id={`p-${clave}`} className="entrada" type="number" value={editando![clave]}
             onChange={(e) => setEditando({ ...editando!, [clave]: Number(e.target.value) })} />
      <div className="pista">{pista}</div>
    </div>
  );

  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">
        <span>Criterios de detección</span>
        {esAdmin && !editando && <button type="button" className="boton chico" onClick={() => setEditando(p)}>Cambiar</button>}
      </div>
      <div className="tarjeta-cuerpo">
        {mensaje && <div className={`aviso ${mensaje.tipo}`} role="status">{mensaje.texto}</div>}
        {editando ? (
          <>
            <div className="rejilla">
              {campo("similitud_pct", "Similitud mínima (%)", "Entre 30 y 100. Más alto: menos sugerencias, más seguras.")}
              {campo("max_conexiones", "Conexiones máximas", "Solo se sugieren entidades con pocos documentos.")}
              {campo("horas_deteccion", "Cada cuántas horas", "Frecuencia de la búsqueda automática (1 a 720).")}
            </div>
            <div className="acciones">
              <button type="button" className="boton chico" onClick={() => setEditando(null)}>Cancelar</button>
              <button type="button" className="boton chico primario" onClick={guardar}>Guardar</button>
            </div>
          </>
        ) : (
          <p className="meta" style={{ margin: 0 }}>
            Se sugieren pares del mismo tipo con similitud de nombre de {p.similitud_pct} % o más, cuando cada entidad tiene
            {" "}{p.max_conexiones} documentos o menos. La búsqueda corre sola cada {p.horas_deteccion} h.
            {!esAdmin && " Solo la administración puede cambiar estos criterios."}
          </p>
        )}
      </div>
    </div>
  );
}

export function Vocabularios() {
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const ubicacion = useLocation();
  const puede = tienePermiso(usuario, "vocabularios", "escribir");
  const pestana = useVista<"vocabulario" | "sugerencias" | "tesauros">("/vocabularios");
  const [clase, setClase] = useState<ClaseVocabulario | "">("");
  // Los mecanismos (software, RiC-E13) no son autoridades ISAAR: van en su propio filtro.
  const [mecanismos, setMecanismos] = useState(false);
  const [q, setQ] = useState("");
  const [orden, setOrden] = useState<Orden>("conexiones_desc");
  const [fusionadas, setFusionadas] = useState(false);
  // Las autoridades son de la institución: también las de otros fondos que este todavía no cita.
  const [institucion, setInstitucion] = useState(false);
  const [nivel, setNivel] = useState<"" | "minimo" | "parcial" | "completo">("");
  const [vistaArbol, setVistaArbol] = useState(false);
  const [entidades, setEntidades] = useState<EntidadVocabulario[] | null>(null);
  const [sugerencias, setSugerencias] = useState<Sugerencia[] | null>(null);
  const [aviso, setAviso] = useState((ubicacion.state as { aviso?: string } | null)?.aviso || "");
  const [error, setError] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [pagina, setPagina] = useState(1);
  const [masFiltros, setMasFiltros] = useState(false);
  const [importando, setImportando] = useState(false);
  const navegar = useNavigate();
  const filtrosActivos = !!(q || clase || nivel || fusionadas || mecanismos || institucion);
  const limpiarFiltros = () => {
    setQ(""); setClase(""); setNivel(""); setFusionadas(false); setMecanismos(false); setInstitucion(false); setPagina(1);
  };

  const cargarEntidades = useCallback(async () => {
    if (!fondo) return;
    const params = new URLSearchParams({ fondo_id: fondo.id, orden, estado: fusionadas ? "fusionada" : "activa" });
    if (mecanismos) {
      params.set("clase", "agente");
      params.set("mecanismos", "solo");
    } else if (clase) params.set("clase", clase);
    if (!mecanismos && clase === "agente" && nivel) params.set("nivel_detalle", nivel);
    if (q.trim()) params.set("q", q.trim());
    if (institucion) params.set("alcance", "institucion");
    try {
      setEntidades(await pedir<EntidadVocabulario[]>(`/api/vocabulario?${params}`));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar el vocabulario.");
    }
  }, [fondo, clase, q, orden, fusionadas, nivel, mecanismos, institucion]);

  const cargarSugerencias = useCallback(async () => {
    if (!fondo) return;
    try {
      setSugerencias(await pedir<Sugerencia[]>(`/api/vocabulario/sugerencias-fusion?fondo_id=${fondo.id}`));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudieron cargar las sugerencias.");
    }
  }, [fondo]);

  useEffect(() => {
    const t = setTimeout(cargarEntidades, 250);
    return () => clearTimeout(t);
  }, [cargarEntidades]);

  useEffect(() => {
    cargarSugerencias();
  }, [cargarSugerencias]);

  async function detectarAhora() {
    if (!fondo) return;
    setBuscando(true);
    setError("");
    try {
      const r = await pedir<{ nuevas: number }>(`/api/vocabulario/detectar?fondo_id=${fondo.id}`, { method: "POST" });
      setAviso(r.nuevas ? `Se encontraron ${r.nuevas} sugerencia(s) nuevas.` : "No se encontraron pares nuevos para revisar.");
      await cargarSugerencias();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo buscar.");
    } finally {
      setBuscando(false);
    }
  }

  if (!fondo) return <div className="vacio">Primero debe existir un fondo (se registra en Ingesta).</div>;


  return (
    <>
      {aviso && <div className="aviso bien" role="status">{aviso}</div>}
      {error && <div className="aviso error" role="alert">{error}</div>}

      {pestana === "tesauros" ? <Tesauros /> : pestana === "vocabulario" ? (
        <>
          <Encabezado titulo="Autoridades y términos"
                      descripcion="El vocabulario del fondo: agentes, lugares, formas documentales, actividades y demás términos normalizados. Cada entidad se crea una sola vez al describir y se reutiliza en todos los documentos."
                      acciones={usuario?.es_administrador ? (
                        <button type="button" className="boton" onClick={() => setImportando(!importando)}>
                          {importando ? "Cerrar la importación" : "Importar autoridades (EAC-CPF)"}</button>) : undefined} />
          {importando && usuario?.es_administrador && (
            <div className="tarjeta"><div className="tarjeta-cuerpo"><ImportarEac fondoId={fondo.id} alTerminar={cargarEntidades} /></div></div>
          )}
          <div className="barra-filtros" role="group" aria-label="Filtros">
            <label className="filtro">
              <span>Tipo de autoridad</span>
              <select className="selector" value={mecanismos ? "mecanismos" : clase} onChange={(e) => {
                const v = e.target.value;
                if (v === "mecanismos") { setMecanismos(true); setNivel(""); } else { setMecanismos(false); setClase(v as ClaseVocabulario | ""); }
                setPagina(1);
              }}>
                <option value="">Todas</option>
                {CLASES.map((c) => <option key={c} value={c}>{CLASE_NOMBRE_PLURAL[c]}</option>)}
                <option value="mecanismos">Mecanismos (software)</option>
              </select>
            </label>
            <label className="filtro ancho">
              <span>Buscar</span>
              <span className="buscador">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
                <input className="entrada" type="search" placeholder="Buscar por nombre…" value={q} onChange={(e) => { setQ(e.target.value); setPagina(1); }} />
              </span>
            </label>
            <label className="filtro">
              <span>Ordenar por</span>
              <select className="selector" value={orden} onChange={(e) => setOrden(e.target.value as Orden)}>
                <option value="conexiones_desc">Más conectadas</option>
                <option value="conexiones_asc">Menos conectadas</option>
                <option value="nombre">Nombre</option>
              </select>
            </label>
            {clase === "agente" && !mecanismos && (
              <label className="filtro">
                <span>Nivel de la ficha</span>
                <select className="selector" value={nivel} onChange={(e) => { setNivel(e.target.value as typeof nivel); setPagina(1); }}>
                  <option value="">Cualquiera</option>
                  <option value="minimo">Mínima (por enriquecer)</option>
                  <option value="parcial">Parcial</option>
                  <option value="completo">Completa</option>
                </select>
              </label>
            )}
            <button type="button" className={`boton${masFiltros ? " con-filtros" : ""}`} aria-expanded={masFiltros}
                    onClick={() => setMasFiltros(!masFiltros)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden="true"><path d="M4 5h16l-6 7.5V19l-4 2v-8.5z" /></svg>
              Filtros{(fusionadas ? 1 : 0) + (institucion ? 1 : 0) ? ` (${(fusionadas ? 1 : 0) + (institucion ? 1 : 0)})` : ""}
            </button>
            <button type="button" className="enlace-limpiar" disabled={!filtrosActivos} onClick={limpiarFiltros}>Limpiar filtros</button>
          </div>
          {masFiltros && (
            <div className="casillas" style={{ margin: "-6px 0 16px", flexDirection: "row", gap: 18 }}>
              <label><input type="checkbox" checked={fusionadas} onChange={(e) => { setFusionadas(e.target.checked); setPagina(1); }} />
                Ver las fusionadas</label>
              <label title="Personas, familias, entidades, cargos, lugares, materias y mandatos son de toda la institución">
                <input type="checkbox" checked={institucion} onChange={(e) => { setInstitucion(e.target.checked); setPagina(1); }} />
                Incluir las autoridades de toda la institución</label>
              {clase === "tipo_actividad" && !fusionadas && (
                <label><input type="checkbox" checked={vistaArbol} onChange={(e) => setVistaArbol(e.target.checked)} />
                  Ver como árbol de funciones</label>
              )}
            </div>
          )}
          {clase === "regla" && !fusionadas && (
            <p className="meta">Las reglas de retención se crean al aplicar la TRD (Instrumentos › TRD y CCD).</p>
          )}
          {clase === "tipo_actividad" && vistaArbol && !fusionadas ? <ArbolFunciones fondoId={fondo.id} /> : (
          <div className="tarjeta">
            <div className="cabecera-tabla">
              <span>{entidades === null ? "Cargando…" : `${entidades.length.toLocaleString("es-CO")} registro${entidades.length === 1 ? "" : "s"}${fusionadas ? " fusionados" : ""}`}</span>
            </div>
            {entidades !== null && entidades.length === 0 && (
              filtrosActivos ? (
                <EstadoVacio icono="filtro" titulo="Ninguna entidad cumple el filtro activo"
                             texto={fusionadas && !q && !clase && !nivel ? "No hay entidades fusionadas en este fondo." : "La lista no está vacía por un error: el filtro no deja pasar nada."}
                             accion={{ texto: "Limpiar filtros", alHacer: limpiarFiltros }} />
              ) : (
                <EstadoVacio icono="lista" titulo="El vocabulario del fondo está vacío"
                             texto="Se llena solo, a medida que se publican descripciones: cada agente, lugar o forma documental confirmado queda aquí una sola vez." />
              )
            )}
            {mecanismos && (
              <div className="pista" style={{ padding: "10px 18px" }}>
                Programas que actuaron sobre los archivos del fondo, cada uno con su versión exacta. En RiC son agentes
                (rico:Mechanism); aquí son de solo consulta porque los registra el sistema, no una persona.
              </div>
            )}
            {entidades !== null && entidades.length > 0 && (
              <div className="tabla-desplazable">
                <table className="tabla-datos">
                  <thead><tr><th>Nombre</th><th>Tipo</th><th className="num">{mecanismos ? "Archivos" : "Documentos vinculados"}</th>
                    {!mecanismos && <th>Ficha</th>}<th className="acciones-celda"><span className="sr-only">Acciones</span></th></tr></thead>
                  <tbody>
                    {entidades.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA).map((e) => (
                      <tr key={e.id}>
                        <td>
                          <Link to={`/vocabularios/${e.id}`} className="celda-nombre">
                            {ICONO_CLASE[e.clase] || ICONO_GENERICO}
                            <span>{e.nombre}
                              <span className="secundario">
                                {e.subtipo ? `${SUBTIPO_NOMBRE[e.subtipo] || e.subtipo} · ` : ""}
                                {e.version ? `versión ${e.version} · ` : esMecanismo(e) ? "sin versión · " : ""}{claseRicDe(e)}
                                {e.fusionada_en && ` · fusionada en «${e.fusionada_en.nombre}»`}
                                {e.fondo_registro && ` · registrada en «${e.fondo_registro.titulo}»`}
                                {esMecanismo(e) && <> · {accionesTexto(e.acciones)}</>}
                              </span>
                            </span>
                          </Link>
                        </td>
                        <td><span className={`insignia ${CLASE_INSIGNIA[e.clase]}`}>{CLASE_NOMBRE[e.clase]}</span></td>
                        <td className="num">{(esMecanismo(e) ? e.archivos ?? 0 : e.conexiones).toLocaleString("es-CO")}</td>
                        {!mecanismos && (
                          <td>{e.nivel_detalle && !esMecanismo(e) ? (
                            <span className={`insignia ${e.nivel_detalle === "completo" ? "bien" : "neutra"}`}>{NIVEL_FICHA[e.nivel_detalle] || e.nivel_detalle}</span>
                          ) : <span className="meta">—</span>}</td>
                        )}
                        <td className="acciones-celda">
                          <MenuAcciones etiqueta={`Acciones para ${e.nombre}`} acciones={[
                            { texto: "Ver y editar la ficha", alHacer: () => navegar(`/vocabularios/${e.id}`) },
                            { texto: "Ver su historial de auditoría", alHacer: () => navegar(`/auditoria/entidad/entidad_vocabulario/${e.id}`) },
                          ]} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {entidades !== null && (
              <Paginacion pagina={pagina} paginas={Math.max(1, Math.ceil(entidades.length / POR_PAGINA))} total={entidades.length}
                          porPagina={POR_PAGINA} alCambiar={setPagina} />
            )}
          </div>
          )}
        </>
      ) : (
        <>
          <h1>Sugerencias de fusión</h1>
          <p className="sub">
            Pares que el sistema cree que son la misma entidad escrita de dos formas. Nada se fusiona solo: usted decide cuál
            queda como definitiva o si son distintas. Toda fusión queda en la auditoría y se puede rastrear.
          </p>
          {puede && (
            <div className="acciones" style={{ marginBottom: 14 }}>
              <button type="button" className="boton chico" disabled={buscando} onClick={detectarAhora}>
                {buscando ? "Buscando…" : "Buscar candidatos ahora"}
              </button>
            </div>
          )}
          {sugerencias === null && <div className="cargando">Cargando…</div>}
          {sugerencias !== null && sugerencias.length === 0 && (
            <div className="tarjeta">
              <EstadoVacio icono="fusion" titulo="No hay sugerencias pendientes"
                           texto={<>Una sugerencia aparece cuando dos entidades del mismo tipo tienen nombres muy parecidos y
                             pocas conexiones cada una (los criterios están abajo): por ejemplo, «Alcaldía Municipal» y «Alcaldía
                             Mpal.». Que esta lista esté vacía no es un error: significa que la última búsqueda no encontró pares
                             así. También puede buscar ahora con el botón de arriba.</>} />
            </div>
          )}
          {sugerencias?.map((s) => (
            <TarjetaSugerencia key={s.id} s={s} puede={puede} alResolver={(texto) => {
              setAviso(texto);
              cargarSugerencias();
              cargarEntidades();
            }} />
          ))}
          <Parametros esAdmin={!!usuario?.es_administrador} />
        </>
      )}
    </>
  );
}


