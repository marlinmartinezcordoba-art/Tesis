import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ErrorAPI, descargar, pedir, puede as tienePermiso } from "@/lib/api";
import { NIVEL_NOMBRE, SUBTIPO_NOMBRE } from "@/lib/descripcion";
import { useFondo } from "@/lib/fondo";
import {
  etiquetaRelacion, type Ficha, type Indice as DatosIndice, type Inventario as DatosInventario, type Miga, type NivelCatalogo,
} from "@/lib/instrumentos";
import { useSesion } from "@/lib/sesion";
import { CLASE_NOMBRE_PLURAL } from "@/lib/vocabulario";

type Pestana = "catalogo" | "inventario" | "guia" | "indice";
const PESTANAS: { clave: Pestana; nombre: string }[] = [
  { clave: "catalogo", nombre: "Catálogo" },
  { clave: "inventario", nombre: "Inventario" },
  { clave: "guia", nombre: "Guía" },
  { clave: "indice", nombre: "Índice" },
];
const AGRUPACIONES = ["fondo", "seccion", "serie", "subserie", "expediente"];

function Migas({ fondo, migas, actual, ir }: { fondo: string; migas: Miga[]; actual?: Miga; ir: (id: string | null) => void }) {
  return (
    <nav className="migas" aria-label="Ubicación en el fondo">
      {migas.map((m, i) => (
        <span key={m.id}>
          <button type="button" className="enlace" onClick={() => ir(i === 0 ? null : m.id)}>{i === 0 ? `Fondo · ${fondo}` : m.titulo}</button>
          <span aria-hidden="true"> › </span>
        </span>
      ))}
      {actual && <strong>{actual.nivel === "fondo" ? `Fondo · ${actual.titulo}` : actual.titulo}</strong>}
    </nav>
  );
}

// --- Ficha (panel superpuesto) ------------------------------------------------------------------

function PanelFicha({ id, cerrar, ir }: { id: string; cerrar: () => void; ir: (id: string | null) => void }) {
  const { usuario } = useSesion();
  const veVocabulario = tienePermiso(usuario, "vocabularios");
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setFicha(null);
    pedir<Ficha>(`/api/instrumentos/catalogo/${id}`).then(setFicha)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo abrir la ficha."));
  }, [id]);

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => e.key === "Escape" && cerrar();
    document.addEventListener("keydown", tecla);
    return () => document.removeEventListener("keydown", tecla);
  }, [cerrar]);

  const entidad = (nombre: string, entidadId: string, documentos: number | null) => (
    <>
      {veVocabulario ? <Link to={`/vocabularios/${entidadId}`}>{nombre}</Link> : nombre}
      {documentos !== null && <span className="meta"> · {documentos} documento{documentos === 1 ? "" : "s"} de esta entidad</span>}
    </>
  );

  const preservacion = ficha?.instanciaciones[0]?.preservacion;
  return (
    <div className="velo" onMouseDown={(e) => e.target === e.currentTarget && cerrar()}>
      <aside className="panel-ficha" role="dialog" aria-modal="true" aria-label="Ficha de la descripción">
        <div className="panel-cab">
          {ficha ? <Migas fondo={ficha.migas[0]?.titulo || ""} migas={ficha.migas} actual={ficha}
                          ir={(n) => { cerrar(); ir(n); }} /> : <span />}
          <button type="button" className="enlace" onClick={cerrar}>Cerrar</button>
        </div>
        {error && <div className="aviso error">{error}</div>}
        {!ficha && !error && <div className="cargando">Cargando…</div>}
        {ficha && (
          <div className="panel-cuerpo">
            <div className="ficha-titulo">
              <div>
                <span className="insignia acento">{NIVEL_NOMBRE[ficha.nivel]}</span>
                <h2>{ficha.titulo}</h2>
              </div>
              {ficha.instanciaciones.length > 0 && (
                <span className="insignia proceso" title="El módulo 5 (preservación) aún no evalúa este archivo">
                  ● Preservación: sin evaluar
                </span>
              )}
            </div>
            <dl className="pares">
              {ficha.control.codigo_referencia && <><dt>Código</dt><dd>{ficha.control.codigo_referencia}</dd></>}
              {ficha.forma_documental && (
                <><dt>Forma documental</dt><dd>{entidad(ficha.forma_documental.nombre, ficha.forma_documental.id, ficha.forma_documental.documentos)}</dd></>
              )}
              {ficha.fechas_extremas && <><dt>{ficha.nivel === "unidad_documental" ? "Fecha" : "Fechas extremas"}</dt><dd>{ficha.fechas_extremas}</dd></>}
              {ficha.entidades.filter((e) => e.tipo !== "fecha").map((e) => (
                <FilaEntidad key={`${e.entidad_id}-${e.codigo_ric}-${e.rol}`} etiqueta={etiquetaRelacion(e)}>
                  {e.en_vocabulario ? entidad(e.valor, e.entidad_id, e.documentos) : e.valor}
                  {e.subtipo && <span className="meta"> ({SUBTIPO_NOMBRE[e.subtipo] || e.subtipo})</span>}
                </FilaEntidad>
              ))}
              <dt>Alcance y contenido</dt><dd>{ficha.alcance_contenido || "—"}</dd>
              {(ficha.control.caja || ficha.control.carpeta || ficha.control.folios !== null || ficha.control.soporte) && (
                <>
                  <dt>Ubicación y volumen</dt>
                  <dd>{[ficha.control.caja && `Caja ${ficha.control.caja}`, ficha.control.carpeta && `Carpeta ${ficha.control.carpeta}`,
                    ficha.control.folios !== null && `${ficha.control.folios} folio(s)`, ficha.control.soporte].filter(Boolean).join(" · ")}</dd>
                </>
              )}
              {ficha.instanciaciones.length > 0 && (
                <>
                  <dt>Preservación</dt>
                  <dd>
                    {ficha.instanciaciones.map((i) => (
                      <div key={i.id} className="meta">
                        {i.nombre} · {i.preservacion.formato || "formato sin identificar"}{i.preservacion.puid && ` (${i.preservacion.puid})`}
                        {i.preservacion.huella && ` · ${i.preservacion.algoritmo_huella} ${i.preservacion.huella.slice(0, 12)}…`}
                      </div>
                    ))}
                    {preservacion && <div className="meta">Estado: sin evaluar todavía (lo mantendrá el módulo de preservación digital).</div>}
                  </dd>
                </>
              )}
            </dl>
            {ficha.hijos > 0 && (
              <button type="button" className="boton chico" style={{ marginTop: 16 }} onClick={() => { cerrar(); ir(ficha.id); }}>
                Ver lo que contiene ({ficha.hijos})
              </button>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}

function FilaEntidad({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return <><dt>{etiqueta}</dt><dd>{children}</dd></>;
}

// --- Catálogo -----------------------------------------------------------------------------------

function Catalogo({ nivel, ir, abrir }: { nivel: NivelCatalogo; ir: (id: string | null) => void; abrir: (id: string) => void }) {
  const a = nivel.actual;
  return (
    <>
      <Migas fondo={nivel.fondo.titulo} migas={nivel.migas}
             actual={a} ir={ir} />
      <div className="cabecera-nivel">
        <div>
          <h1>{a.titulo}</h1>
          <p className="sub" style={{ marginBottom: 0 }}>
            {NIVEL_NOMBRE[a.nivel]}{a.codigo_referencia && ` · ${a.codigo_referencia}`}{a.fechas_extremas && ` · ${a.fechas_extremas}`}
            {" · "}{a.unidades_documentales} unidad{a.unidades_documentales === 1 ? "" : "es"} documental{a.unidades_documentales === 1 ? "" : "es"}
          </p>
        </div>
        {a.nivel !== "fondo" && <button type="button" className="boton chico" onClick={() => abrir(a.id)}>Ver ficha</button>}
      </div>
      <div className="tarjeta">
        <div className="tarjeta-cab">{nivel.hijos.length ? "Contiene" : "Sin niveles inferiores descritos"}</div>
        {nivel.hijos.length === 0 && (
          <div className="vacio">
            {a.nivel === "fondo" ? "Todavía no hay descripciones publicadas en este fondo." : "Este nivel no tiene descripciones publicadas por debajo."}
          </div>
        )}
        {nivel.hijos.map((h) => {
          const entra = AGRUPACIONES.includes(h.nivel) && h.hijos > 0;
          return (
            <button type="button" key={h.id} className="fila fila-enlace fila-boton" onClick={() => (entra ? ir(h.id) : abrir(h.id))}>
              <span className="insignia acento">{NIVEL_NOMBRE[h.nivel]}</span>
              <div className="fila-principal">
                <div className="nombre">{h.titulo}</div>
                <div className="meta">
                  {[h.codigo_referencia, h.fechas_extremas,
                    entra && `${h.unidades_documentales} unidad(es) documental(es)`].filter(Boolean).join(" · ") || "Sin fecha"}
                </div>
              </div>
              <span className="meta">{entra ? "Abrir ›" : "Ver ficha"}</span>
            </button>
          );
        })}
      </div>
    </>
  );
}

// --- Inventario ---------------------------------------------------------------------------------

function Inventario({ nivel, puede }: { nivel: NivelCatalogo; puede: boolean }) {
  const [datos, setDatos] = useState<DatosInventario | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  const a = nivel.actual;

  useEffect(() => setDatos(null), [a.id]);

  async function generar() {
    setOcupado(true);
    setError("");
    try {
      setDatos(await pedir<DatosInventario>("/api/instrumentos/inventario/vista-previa", {
        method: "POST", body: JSON.stringify({ recurso_id: a.id }),
      }));
      window.dispatchEvent(new Event("ricora:alertas"));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo generar el inventario.");
    } finally {
      setOcupado(false);
    }
  }

  async function exportar() {
    setOcupado(true);
    setError("");
    try {
      await descargar("/api/instrumentos/inventario", { method: "POST", body: JSON.stringify({ recurso_id: a.id }) });
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo exportar.");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <>
      <h1>Generar inventario</h1>
      <p className="sub">
        {NIVEL_NOMBRE[a.nivel]} · {a.titulo} · estructurado sobre el Formato Único de Inventario Documental (AGN). Para
        generarlo desde otro nivel, navegue hasta él en el Catálogo.
      </p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!puede ? (
        <div className="aviso">Su rol puede consultar el catálogo, pero no generar instrumentos.</div>
      ) : !datos ? (
        <button type="button" className="boton primario" disabled={ocupado} onClick={generar}>
          {ocupado ? "Armando…" : `Armar inventario de «${a.titulo}»`}
        </button>
      ) : (
        <>
          <div className="tarjeta tabla-desplazable">
            <table className="tabla-fuid">
              <thead>
                <tr>{datos.columnas.map((c) => <th key={c.clave}>{c.nombre}</th>)}</tr>
              </thead>
              <tbody>
                {datos.filas.length === 0 && (
                  <tr><td colSpan={datos.columnas.length} className="vacio">No hay unidades documentales ni expedientes publicados en este nivel.</td></tr>
                )}
                {datos.filas.map((f) => (
                  <tr key={f.id}>
                    {datos.columnas.map((c) => (
                      f.pendientes.includes(c.clave) ? (
                        <td key={c.clave} className="pendiente">pendiente <span className="insignia alerta">falta dato</span></td>
                      ) : (
                        <td key={c.clave}>{c.clave === "nombre" ? (
                          <Link to={`/descripcion/registro/${f.id}`} title="Abrir la descripción para completarla">{f.valores[c.clave]}</Link>
                        ) : f.valores[c.clave] ?? ""}</td>
                      )
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="barra-publicar">
            <span>
              {datos.filas.length} renglón(es) ·{" "}
              {datos.pendientes === 0 ? "sin campos pendientes"
                : <><strong className="texto-alerta">{datos.pendientes} campo{datos.pendientes === 1 ? "" : "s"} pendiente{datos.pendientes === 1 ? "" : "s"}</strong>
                  {datos.alerta && <> · se generó una alerta en el <Link to="/alertas">panel central</Link></>}</>}
            </span>
            <div className="acciones">
              <button type="button" className="boton chico" disabled={ocupado} onClick={generar}>Volver a armar</button>
              <button type="button" className="boton chico primario" disabled={ocupado} onClick={exportar}>Exportar a Excel</button>
            </div>
          </div>
          {datos.pendientes > 0 && (
            <p className="meta">Los pendientes se completan en la descripción de cada unidad (Descripción › Corregir › Datos de control).
              El archivo se exporta igual, con esas celdas marcadas.</p>
          )}
        </>
      )}
    </>
  );
}

// --- Guía ---------------------------------------------------------------------------------------

function Guia({ fondo, puede }: { fondo: { id: string; titulo: string }; puede: boolean }) {
  const [texto, setTexto] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");

  async function redactar() {
    setOcupado(true);
    setError("");
    try {
      const r = await pedir<{ texto: string; aviso: string | null }>("/api/instrumentos/guia", {
        method: "POST", body: JSON.stringify({ fondo_id: fondo.id }),
      });
      setTexto(r.texto);
      setAviso(r.aviso);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo redactar el borrador.");
    } finally {
      setOcupado(false);
    }
  }

  async function exportar() {
    setOcupado(true);
    setError("");
    try {
      await descargar("/api/instrumentos/guia/exportar", { method: "POST", body: JSON.stringify({ fondo_id: fondo.id, texto }) });
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo exportar.");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <>
      <div className="cabecera-nivel">
        <div>
          <h1>Generar guía</h1>
          <p className="sub" style={{ marginBottom: 0 }}>Fondo · {fondo.titulo}</p>
        </div>
        {puede && texto !== null && (
          <button type="button" className="boton primario" disabled={ocupado || !texto.trim()} onClick={exportar}>Exportar a Word</button>
        )}
      </div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!puede ? (
        <div className="aviso">Su rol puede consultar el catálogo, pero no generar instrumentos.</div>
      ) : texto === null ? (
        <>
          <p className="meta">El motor redacta una nota de presentación solo con datos ya validados (niveles superiores publicados,
            fechas y vocabulario). Usted la corrige libremente; se exporta exactamente lo que deje escrito.</p>
          <button type="button" className="boton primario" disabled={ocupado} onClick={redactar}>
            {ocupado ? "Redactando…" : "Redactar borrador"}
          </button>
        </>
      ) : (
        <div className="tarjeta">
          <div className="tarjeta-cab">
            <span>Nota de presentación</span>
            <span className="meta">Editable antes de exportar</span>
          </div>
          <div className="tarjeta-cuerpo">
            {aviso && <div className="aviso alerta">{aviso}</div>}
            <textarea className="entrada texto-guia" aria-label="Nota de presentación" value={texto}
                      onChange={(e) => setTexto(e.target.value)} rows={16} />
            <div className="acciones" style={{ marginTop: 10 }}>
              <button type="button" className="boton chico" disabled={ocupado}
                      onClick={() => window.confirm("¿Reemplazar su texto por un borrador nuevo?") && redactar()}>
                Redactar de nuevo
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// --- Índice -------------------------------------------------------------------------------------

function Indice({ fondo }: { fondo: { id: string; titulo: string } }) {
  const { usuario } = useSesion();
  const veVocabulario = tienePermiso(usuario, "vocabularios");
  const [datos, setDatos] = useState<DatosIndice | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    pedir<DatosIndice>(`/api/instrumentos/indice?fondo_id=${fondo.id}`).then(setDatos)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar el índice."));
  }, [fondo.id]);

  return (
    <>
      <h1>Índice</h1>
      <p className="sub">Vista de consulta, generada desde el vocabulario ya consolidado del fondo.</p>
      {error && <div className="aviso error">{error}</div>}
      {!datos && !error && <div className="cargando">Cargando…</div>}
      {datos?.grupos.map((g) => (
        <div className="tarjeta" key={g.clase}>
          <div className="tarjeta-cab">{CLASE_NOMBRE_PLURAL[g.clase]} · {g.total}</div>
          {g.total === 0 && <div className="vacio">Sin entradas.</div>}
          {g.letras.map((l) => (
            <div key={l.letra} className="grupo-letra">
              <div className="letra">{l.letra}</div>
              <div>
                {l.entidades.map((e) => (
                  <div className="fila" key={e.id}>
                    <div className="fila-principal">
                      <div className="nombre">
                        {veVocabulario ? <Link to={`/vocabularios/${e.id}`}>{e.nombre}</Link> : e.nombre}
                        {e.subtipo && <span className="meta"> · {SUBTIPO_NOMBRE[e.subtipo] || e.subtipo}</span>}
                      </div>
                    </div>
                    <span className="meta">{e.documentos} documento{e.documentos === 1 ? "" : "s"}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}
    </>
  );
}

// --- Página -------------------------------------------------------------------------------------

export function Instrumentos() {
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const [parametros, setParametros] = useSearchParams();
  const pestana = (parametros.get("vista") as Pestana) || "catalogo";
  const nodo = parametros.get("nodo");
  const fichaAbierta = parametros.get("ficha");
  const puede = tienePermiso(usuario, "instrumentos", "escribir");
  const [nivel, setNivel] = useState<NivelCatalogo | null>(null);
  const [error, setError] = useState("");

  const cambiar = useCallback((cambios: Record<string, string | null>) => {
    setParametros((p) => {
      const n = new URLSearchParams(p);
      for (const [k, v] of Object.entries(cambios)) {
        if (v) n.set(k, v);
        else n.delete(k);
      }
      return n;
    });
  }, [setParametros]);

  useEffect(() => {
    if (!fondo) return;
    setError("");
    pedir<NivelCatalogo>(`/api/instrumentos/catalogo?fondo_id=${fondo.id}${nodo ? `&nodo_id=${nodo}` : ""}`)
      .then(setNivel)
      .catch((err) => {
        setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar el catálogo.");
        if (nodo) cambiar({ nodo: null });
      });
  }, [fondo, nodo, cambiar]);

  if (!fondo) return <div className="vacio">Primero debe existir un fondo (se registra en Ingesta).</div>;

  return (
    <>
      <div className="pestanas" role="tablist">
        {PESTANAS.map((p) => (
          <button key={p.clave} type="button" role="tab" aria-selected={pestana === p.clave}
                  className={`pestana${pestana === p.clave ? " activa" : ""}`}
                  onClick={() => cambiar({ vista: p.clave === "catalogo" ? null : p.clave })}>
            {p.nombre}
          </button>
        ))}
      </div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!nivel ? <div className="cargando">Cargando…</div> : (
        <>
          {pestana === "catalogo" && (
            <Catalogo nivel={nivel} ir={(id) => cambiar({ nodo: id })} abrir={(id) => cambiar({ ficha: id })} />
          )}
          {pestana === "inventario" && <Inventario nivel={nivel} puede={puede} />}
          {pestana === "guia" && <Guia fondo={nivel.fondo} puede={puede} />}
          {pestana === "indice" && <Indice fondo={nivel.fondo} />}
        </>
      )}
      {fichaAbierta && (
        <PanelFicha id={fichaAbierta} cerrar={() => cambiar({ ficha: null })}
                    ir={(id) => cambiar({ nodo: id, vista: null })} />
      )}
    </>
  );
}
