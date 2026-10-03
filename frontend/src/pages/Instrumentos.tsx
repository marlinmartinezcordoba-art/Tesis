import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ErrorAPI, descargar, pedir, puede as tienePermiso } from "@/lib/api";
import { NIVEL_NOMBRE, SUBTIPO_NOMBRE } from "@/lib/descripcion";
import { useFondo } from "@/lib/fondo";
import {
  ESTADO_PRESERVACION, etiquetaRelacion, type Ficha, type Indice as DatosIndice, type Inventario as DatosInventario, type Miga, type NivelCatalogo,
} from "@/lib/instrumentos";
import { useSesion } from "@/lib/sesion";
import { PestanaGrafo } from "@/pages/GrafoFondo";
import { CadenaActividad } from "@/components/ContextoActividad";
import { IDIOMAS } from "@/components/DescripcionV3";
import { CLASE_NOMBRE_PLURAL } from "@/lib/vocabulario";
import { ExportacionRico } from "@/components/ExportacionRico";
import { useVista } from "@/components/Marco";
import { BotonPrevisualizar } from "@/components/VisorDocumento";

type Pestana = "catalogo" | "grafo" | "inventario" | "guia" | "indice" | "rico";
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

function PanelFicha({ id, cerrar, ir, verGrafo }: {
  id: string; cerrar: () => void; ir: (id: string | null) => void; verGrafo: (centro: string) => void;
}) {
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

  const vePreservacion = tienePermiso(usuario, "preservacion");
  // La insignia muestra el estado más delicado entre los archivos de la descripción.
  const preservacion = ficha?.instanciaciones.map((i) => i.preservacion)
    .sort((a, b) => ESTADO_PRESERVACION[a.estado].orden - ESTADO_PRESERVACION[b.estado].orden)[0];
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
              {preservacion && (
                <span className={`insignia ${ESTADO_PRESERVACION[preservacion.estado].clase}`} title="Estado de preservación (módulo 5)">
                  ● {ESTADO_PRESERVACION[preservacion.estado].texto}
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
                  {e.contexto && <CadenaActividad contexto={e.contexto} enlazar={false} />}
                </FilaEntidad>
              ))}
              <dt>Alcance y contenido</dt><dd>{ficha.alcance_contenido || "—"}</dd>
              {ficha.parte_de && (
                <><dt>Parte documental de</dt><dd>{ficha.parte_de.titulo}{ficha.tipo_parte && <span className="meta"> ({ficha.tipo_parte})</span>}</dd></>
              )}
              {ficha.idiomas.length > 0 && (
                <><dt>Idioma</dt><dd>{ficha.idiomas.map((c) => IDIOMAS[c] || c).join(", ")}</dd></>
              )}
              {ficha.condiciones_acceso && <><dt>Condiciones de acceso</dt><dd>{ficha.condiciones_acceso}</dd></>}
              {ficha.condiciones_uso && <><dt>Condiciones de uso</dt><dd>{ficha.condiciones_uso}</dd></>}
              {ficha.secuencia.map((x) => (
                <FilaEntidad key={x.id} etiqueta={x.posicion === "precede_a" ? "Precede a" : "Sigue a"}>{x.titulo}</FilaEntidad>
              ))}
              {ficha.partes.length > 0 && (
                <>
                  <dt>Partes documentales</dt>
                  <dd>{ficha.partes.map((p) => (
                    <div key={p.id}>{p.titulo}{p.tipo_parte && <span className="meta"> ({p.tipo_parte})</span>}
                      {p.alcance_contenido && <span className="meta"> · {p.alcance_contenido}</span>}</div>
                  ))}</dd>
                </>
              )}
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
                        <BotonPrevisualizar base={`/api/instrumentos/previsualizar/${i.id}`} nombre={i.nombre} etiqueta="Ver" />{" "}
                        {vePreservacion ? <Link to={`/preservacion/instanciacion/${i.id}`}>{i.nombre}</Link> : i.nombre}
                        {i.preservacion.derivada_de && " (versión de conservación)"}
                        {" · "}{i.preservacion.formato || "formato sin identificar"}{i.preservacion.puid && ` (${i.preservacion.puid})`}
                        {" · "}{ESTADO_PRESERVACION[i.preservacion.estado].texto.toLowerCase()}
                      </div>
                    ))}
                  </dd>
                </>
              )}
            </dl>
            <div className="acciones" style={{ marginTop: 16 }}>
              <button type="button" className="boton chico primario" onClick={() => verGrafo(`recurso_documental:${ficha.id}`)}>
                Ver en grafo
              </button>
              {ficha.hijos > 0 && (
                <button type="button" className="boton chico" onClick={() => { cerrar(); ir(ficha.id); }}>
                  Ver lo que contiene ({ficha.hijos})
                </button>
              )}
            </div>
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

// Exportación del paquete de preservación (AIP) de un expediente completo:
// la hace el módulo de preservación, con su permiso, desde aquí.
function ExportarPaqueteExpediente({ id }: { id: string }) {
  const [estado, setEstado] = useState<{ tipo: "bien" | "error"; texto: string } | null>(null);
  const [ocupado, setOcupado] = useState(false);

  async function exportar() {
    setOcupado(true);
    setEstado(null);
    try {
      await descargar(`/api/preservacion/expediente/${id}/exportar-paquete`, { method: "POST" });
      setEstado({ tipo: "bien", texto: "Paquete exportado con todas las instanciaciones del expediente." });
    } catch (err) {
      setEstado({ tipo: "error", texto: err instanceof ErrorAPI ? err.message : "No se pudo exportar el paquete." });
    } finally {
      setOcupado(false);
    }
  }

  return (
    <>
      <button type="button" className="boton chico" disabled={ocupado} onClick={exportar}
              title="Paquete de información de archivo (OAIS): BagIt con cada archivo, PREMIS y la PDI">
        {ocupado ? "Armando el paquete…" : "Exportar paquete de preservación"}
      </button>
      {estado && <div className={`aviso ${estado.tipo}`} role="status" style={{ marginTop: 8 }}>{estado.texto}</div>}
    </>
  );
}

function Catalogo({ nivel, ir, abrir }: { nivel: NivelCatalogo; ir: (id: string | null) => void; abrir: (id: string) => void }) {
  const a = nivel.actual;
  const { usuario } = useSesion();
  const preserva = tienePermiso(usuario, "preservacion", "escribir");
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
        <div className="acciones" style={{ marginTop: 0 }}>
          {a.nivel === "expediente" && preserva && <ExportarPaqueteExpediente id={a.id} />}
          {a.nivel !== "fondo" && <button type="button" className="boton chico" onClick={() => abrir(a.id)}>Ver ficha</button>}
        </div>
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
      {datos?.grupos.filter((g) => g.total > 0 || ["agente", "lugar", "forma_documental"].includes(g.clase)).map((g) => (
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

// --- Contenido de apoyo: accesos a las otras vistas y propósito de cada instrumento -------------------

const trazoAtajo = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
const ATAJOS: { vista: Pestana; nombre: string; frase: string; icono: JSX.Element }[] = [
  { vista: "grafo", nombre: "Grafo", frase: "El fondo como red de entidades y relaciones RiC, para recorrer su contexto.",
    icono: <svg viewBox="0 0 24 24" {...trazoAtajo}><circle cx="12" cy="6" r="2.2" /><circle cx="6" cy="17" r="2.2" /><circle cx="18" cy="17" r="2.2" /><path d="M10.5 7.5L7.5 15M13.5 7.5l3 7.5M8.2 17h7.6" /></svg> },
  { vista: "inventario", nombre: "Inventario", frase: "El inventario documental (FUID) para el control interno.",
    icono: <svg viewBox="0 0 24 24" {...trazoAtajo}><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M4 10h16M4 15h16M10 4v16" /></svg> },
  { vista: "guia", nombre: "Guía", frase: "Una presentación del fondo en prosa, para un lector externo.",
    icono: <svg viewBox="0 0 24 24" {...trazoAtajo}><path d="M5 5h6a2 2 0 012 2v12a2 2 0 00-2-2H5zM19 5h-6a2 2 0 00-2 2v12a2 2 0 012-2h6z" /></svg> },
  { vista: "indice", nombre: "Índice", frase: "Agentes, lugares y formas documentales en orden alfabético.",
    icono: <svg viewBox="0 0 24 24" {...trazoAtajo}><path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" /></svg> },
  { vista: "rico", nombre: "RiC-O", frase: "El fondo en datos enlazados (Turtle o JSON-LD), validado contra la ontología.",
    icono: <svg viewBox="0 0 24 24" {...trazoAtajo}><path d="M9 7l-5 5 5 5M15 7l5 5-5 5" /></svg> },
];

function AtajosInstrumentos() {
  return (
    <nav className="tarjetas-atajo" aria-label="Otras vistas de Instrumentos">
      {ATAJOS.map((a) => (
        <Link key={a.vista} to={`/instrumentos?vista=${a.vista}`} className="tarjeta-atajo">
          {a.icono}
          <div><strong>{a.nombre}</strong><span>{a.frase}</span></div>
        </Link>
      ))}
    </nav>
  );
}

// Para qué sirve cada instrumento y para quién: la vista enseña su
// propósito aunque el fondo todavía tenga poco contenido.
const PROPOSITO: Partial<Record<Pestana, [string, string]>> = {
  inventario: ["Para control interno.", "El inventario documental (FUID) dice qué hay, dónde está físicamente (caja, carpeta, folios) y en qué soporte: es la herramienta de quien custodia el fondo."],
  guia: ["Para un lector externo.", "La guía presenta el fondo en prosa a quien no lo conoce: su productor, su contenido y cómo se organiza, sin detalle unidad por unidad."],
  indice: ["Para buscar rápido por nombre.", "El índice reúne los agentes, lugares y formas documentales del vocabulario del fondo, en orden alfabético, con cuántos documentos los citan."],
  rico: ["Para verificar la correspondencia con la ontología.", "La vista RiC-O entrega el fondo como datos enlazados y comprueba que cada clase y propiedad exista en RiC-O 1.1: es la evidencia técnica de conformidad."],
};

function Proposito({ vista }: { vista: Pestana }) {
  const p = PROPOSITO[vista];
  if (!p) return null;
  return <aside className="proposito"><strong>{p[0]}</strong>{p[1]}</aside>;
}

export function Instrumentos() {
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const [parametros, setParametros] = useSearchParams();
  const pestana = useVista<Pestana>("/instrumentos");
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
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!nivel ? <div className="cargando">Cargando…</div> : (
        <>
          {pestana === "catalogo" && (
            <>
              <Catalogo nivel={nivel} ir={(id) => cambiar({ nodo: id })} abrir={(id) => cambiar({ ficha: id })} />
              {nivel.hijos.length < 6 && <AtajosInstrumentos />}
            </>
          )}
          {pestana === "inventario" && <Inventario nivel={nivel} puede={puede} />}
          {pestana === "guia" && <Guia fondo={nivel.fondo} puede={puede} />}
          {pestana === "indice" && <Indice fondo={nivel.fondo} />}
          {pestana === "rico" && <ExportacionRico fondo={nivel.fondo} />}
          <Proposito vista={pestana} />
          {pestana === "grafo" && (
            <PestanaGrafo fondo={nivel.fondo} centro={parametros.get("centro")}
                          centrar={(c) => cambiar({ centro: c })} abrirFicha={(id) => cambiar({ ficha: id })} />
          )}
        </>
      )}
      {fichaAbierta && (
        <PanelFicha id={fichaAbierta} cerrar={() => cambiar({ ficha: null })}
                    ir={(id) => cambiar({ nodo: id, vista: null })}
                    verGrafo={(centro) => cambiar({ vista: "grafo", centro, ficha: null })} />
      )}
    </>
  );
}
