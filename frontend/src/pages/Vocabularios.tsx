import { Fragment, useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ErrorAPI, pedir, puede as tienePermiso } from "@/lib/api";
import { SUBTIPO_NOMBRE } from "@/lib/descripcion";
import { useFondo } from "@/lib/fondo";
import { fecha } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";
import { useVista } from "@/components/Marco";
import { EstadoVacio } from "@/components/EstadoVacio";
import {
  CLASES, CLASE_INSIGNIA, CLASE_NOMBRE, CLASE_NOMBRE_PLURAL, claseRicDe, conexionesTexto,
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
                <strong>{Math.round(s.similitud * 100)} %</strong><span>similitud</span>
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
  const pestana = useVista<"vocabulario" | "sugerencias">("/vocabularios");
  const [clase, setClase] = useState<ClaseVocabulario | "">("");
  const [q, setQ] = useState("");
  const [orden, setOrden] = useState<Orden>("conexiones_desc");
  const [fusionadas, setFusionadas] = useState(false);
  const [nivel, setNivel] = useState<"" | "minimo" | "completo">("");
  const [vistaArbol, setVistaArbol] = useState(false);
  const [entidades, setEntidades] = useState<EntidadVocabulario[] | null>(null);
  const [sugerencias, setSugerencias] = useState<Sugerencia[] | null>(null);
  const [aviso, setAviso] = useState((ubicacion.state as { aviso?: string } | null)?.aviso || "");
  const [error, setError] = useState("");
  const [buscando, setBuscando] = useState(false);

  const cargarEntidades = useCallback(async () => {
    if (!fondo) return;
    const params = new URLSearchParams({ fondo_id: fondo.id, orden, estado: fusionadas ? "fusionada" : "activa" });
    if (clase) params.set("clase", clase);
    if (clase === "agente" && nivel) params.set("nivel_detalle", nivel);
    if (q.trim()) params.set("q", q.trim());
    try {
      setEntidades(await pedir<EntidadVocabulario[]>(`/api/vocabulario?${params}`));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar el vocabulario.");
    }
  }, [fondo, clase, q, orden, fusionadas, nivel]);

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

      {pestana === "vocabulario" ? (
        <>
          <h1>Vocabulario del fondo</h1>
          <p className="sub">
            Registro único de agentes, lugares, formas documentales, actividades, tipos de actividad y mandatos de
            «{fondo.titulo}». Cada entidad se crea una sola vez al describir, se reutiliza en todos los documentos que la
            mencionan y se enriquece aquí: la ficha de autoridad de un agente, la ficha ampliada de un lugar, el árbol de
            funciones.
          </p>
          <div className="opciones" role="radiogroup" aria-label="Tipo" style={{ marginBottom: 10 }}>
            {(["", ...CLASES] as (ClaseVocabulario | "")[]).map((c) => (
              <label key={c || "todos"} className={clase === c ? "elegida" : ""}>
                <input type="radio" name="clase" checked={clase === c} onChange={() => setClase(c)} />
                {c ? CLASE_NOMBRE_PLURAL[c] : "Todos"}
              </label>
            ))}
          </div>
          <div className="filtros">
            <input className="entrada" type="search" placeholder="Buscar por nombre…" aria-label="Buscar por nombre"
                   value={q} onChange={(e) => setQ(e.target.value)} />
            <select className="selector" aria-label="Orden" value={orden} onChange={(e) => setOrden(e.target.value as Orden)}>
              <option value="conexiones_desc">Más conectadas primero</option>
              <option value="conexiones_asc">Menos conectadas primero</option>
              <option value="nombre">Por nombre</option>
            </select>
            <label className="pastilla">
              <input type="checkbox" checked={fusionadas} onChange={(e) => setFusionadas(e.target.checked)} /> Ver fusionadas
            </label>
            {clase === "agente" && (
              <select className="selector" aria-label="Nivel de detalle" value={nivel}
                      onChange={(e) => setNivel(e.target.value as typeof nivel)}>
                <option value="">Cualquier nivel de detalle</option>
                <option value="minimo">Ficha mínima (por enriquecer)</option>
                <option value="completo">Ficha completa</option>
              </select>
            )}
            {clase === "tipo_actividad" && !fusionadas && (
              <div className="opciones" role="radiogroup" aria-label="Vista">
                <label className={!vistaArbol ? "elegida" : ""}>
                  <input type="radio" checked={!vistaArbol} onChange={() => setVistaArbol(false)} /> Lista
                </label>
                <label className={vistaArbol ? "elegida" : ""}>
                  <input type="radio" checked={vistaArbol} onChange={() => setVistaArbol(true)} /> Árbol de funciones
                </label>
              </div>
            )}
          </div>
          {clase === "regla" && !fusionadas && <NuevaRegla fondoId={fondo.id} />}
          {clase === "tipo_actividad" && vistaArbol && !fusionadas ? <ArbolFunciones fondoId={fondo.id} /> : (
          <div className="tarjeta">
            <div className="tarjeta-cab">
              {entidades === null ? "Cargando…" : `${entidades.length} entidad${entidades.length === 1 ? "" : "es"}${fusionadas ? " fusionadas" : ""}`}
            </div>
            {entidades !== null && entidades.length === 0 && (
              q || clase || nivel || fusionadas ? (
                <EstadoVacio icono="filtro" titulo="Ninguna entidad cumple el filtro activo"
                             texto={fusionadas && !q && !clase && !nivel ? "No hay entidades fusionadas en este fondo." : "La lista no está vacía por un error: el filtro no deja pasar nada."}
                             accion={{ texto: "Limpiar filtro", alHacer: () => { setQ(""); setClase(""); setNivel(""); setFusionadas(false); } }} />
              ) : (
                <EstadoVacio icono="lista" titulo="El vocabulario del fondo está vacío"
                             texto="Se llena solo, a medida que se publican descripciones: cada agente, lugar o forma documental confirmado queda aquí una sola vez." />
              )
            )}
            {entidades?.map((e) => (
              <Link to={`/vocabularios/${e.id}`} className="fila fila-enlace" key={e.id}>
                <span className={`insignia ${CLASE_INSIGNIA[e.clase]}`}>{CLASE_NOMBRE[e.clase]}</span>
                <div className="fila-principal">
                  <div className="nombre">{e.nombre}</div>
                  <div className="meta">
                    {e.subtipo ? `${SUBTIPO_NOMBRE[e.subtipo] || e.subtipo} · ` : ""}
                    {e.version ? `versión ${e.version} · ` : ""}{claseRicDe(e)}
                    {e.fusionada_en && ` · fusionada en «${e.fusionada_en.nombre}»`}
                  </div>
                </div>
                {e.nivel_detalle && (
                  <span className={`insignia ${e.nivel_detalle === "completo" ? "bien" : "proceso"}`}>
                    {e.nivel_detalle === "completo" ? "Ficha completa" : "Ficha mínima"}
                  </span>
                )}
                <span className="meta">{conexionesTexto(e.conexiones)}</span>
              </Link>
            ))}
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


// Una regla de retención de la TRD (rico:Rule) se crea aquí y luego, desde su
// ficha, se une a la serie o subserie que regula (hallazgos CM-18 y DES-09).
function NuevaRegla({ fondoId }: { fondoId: string }) {
  const navegar = useNavigate();
  const [abierta, setAbierta] = useState(false);
  const [datos, setDatos] = useState({ nombre: "", gestion: "", central: "", disposicion: "" });
  const [error, setError] = useState("");
  async function crear(ev: React.FormEvent) {
    ev.preventDefault();
    setError("");
    const numero = (v: string) => (v.trim() === "" ? null : Number(v));
    try {
      const r = await pedir<{ entidad: { id: string } }>("/api/vocabulario/reglas", {
        method: "POST", body: JSON.stringify({
          fondo_id: fondoId, nombre: datos.nombre, retencion_gestion_anios: numero(datos.gestion),
          retencion_central_anios: numero(datos.central), disposicion_final: datos.disposicion || null,
        }),
      });
      navegar(`/vocabularios/${r.entidad.id}`);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo crear la regla.");
    }
  }
  if (!abierta) {
    return <button type="button" className="boton chico" style={{ marginBottom: 12 }} onClick={() => setAbierta(true)}>Nueva regla de retención</button>;
  }
  return (
    <form className="tarjeta" onSubmit={crear} style={{ padding: 14, marginBottom: 12 }}>
      <div className="rejilla">
        <input className="entrada" required placeholder="Nombre (p. ej. «TRD Actas, 110.2»)" aria-label="Nombre de la regla"
               value={datos.nombre} onChange={(e) => setDatos({ ...datos, nombre: e.target.value })} />
        <input className="entrada" type="number" min={0} max={100} placeholder="Años en gestión" aria-label="Años en el archivo de gestión"
               value={datos.gestion} onChange={(e) => setDatos({ ...datos, gestion: e.target.value })} />
        <input className="entrada" type="number" min={0} max={100} placeholder="Años en central" aria-label="Años en el archivo central"
               value={datos.central} onChange={(e) => setDatos({ ...datos, central: e.target.value })} />
        <select className="selector" aria-label="Disposición final" value={datos.disposicion}
                onChange={(e) => setDatos({ ...datos, disposicion: e.target.value })}>
          <option value="">Disposición final…</option>
          <option value="conservacion_total">Conservación total</option>
          <option value="eliminacion">Eliminación</option>
          <option value="seleccion">Selección</option>
          <option value="medio_tecnico">Reproducción por medio técnico</option>
        </select>
      </div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="acciones" style={{ marginTop: 10 }}>
        <button type="submit" className="boton chico primario">Crear regla</button>
        <button type="button" className="boton chico" onClick={() => setAbierta(false)}>Cancelar</button>
      </div>
    </form>
  );
}
