import { useEffect, useState } from "react";
import { ErrorAPI, descargar, pedir, puede as tienePermiso } from "@/lib/api";
import { useSesion } from "@/lib/sesion";

// Exportación del fondo en RiC-O 1.1 (RDF) y su reporte de conformidad.
// El backend arma el grafo con el mapeo único verificado contra el OWL
// oficial; aquí solo se descarga y se muestra lo que dijo la validación.

interface ResultadoShacl { foco: string | null; ruta: string | null; mensaje: string | null; severidad: string | null; forma: string | null; valor: string | null }
interface Reporte {
  conforme: boolean;
  ontologia: string;
  owl: { conforme: boolean; problemas: string[] };
  shacl: { conforme: boolean; resultados: ResultadoShacl[]; perfil: string; formas: number };
  mapeo: { problemas: string[] };
  sin_propiedad: Record<string, string>;
  tripletas: number;
  por_clase: Record<string, number>;
  omitidas: Record<string, number>;
  fondo: { id: string; titulo: string };
  uri_fondo: string;
  uris_publicas: boolean;
}

interface GrafoGuardado { fondo_id: string; alcance: string; nombre: string; al_dia: boolean; tripletas: number | null;
  sincronizado_en: string | null; conforme: boolean | null; huella: string | null; error: string | null }
interface EstadoGrafo { almacen: { ok: boolean; motor?: string | null; tripletas?: number | null; motivo?: string | null };
  grafos: GrafoGuardado[] }

interface Diferencia { tabla: string; id: string; columna: string | null; problema: string }

const ALCANCE: Record<string, string> = { publico: "Público (sin lo clasificado ni lo reservado)", completo: "Completo" };

// El grafo RiC-O del fondo vive guardado en un almacén de tripletas
// (Oxigraph); de ahí salen el SPARQL, las URI y las descargas.
function GrafoPersistente({ fondoId }: { fondoId: string }) {
  const { usuario } = useSesion();
  const [estado, setEstado] = useState<EstadoGrafo | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  const [coherencia, setCoherencia] = useState<{ coinciden: boolean; diferencias: Diferencia[] } | null>(null);
  const [rehecho, setRehecho] = useState("");
  const cargar = () => pedir<EstadoGrafo>("/api/exportacion/grafo").then(setEstado).catch(() => setEstado(null));

  async function comparar() {
    setOcupado(true);
    setError("");
    setRehecho("");
    try {
      setCoherencia(await pedir(`/api/exportacion/grafo/coherencia?fondo_id=${fondoId}`));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo comparar.");
    } finally {
      setOcupado(false);
    }
  }

  async function reconstruir() {
    if (!window.confirm("Las tablas del fondo se rehacen con lo que dice el grafo RiC-O guardado (la fuente de verdad). ¿Continuar?")) return;
    setOcupado(true);
    setError("");
    try {
      const r = await pedir<{ corregidas: number; diferencias_despues: Diferencia[] }>(
        `/api/exportacion/grafo/reconstruir?fondo_id=${fondoId}`, { method: "POST" });
      setRehecho(`Listo: ${r.corregidas} dato(s) corregidos desde el grafo; ${r.diferencias_despues.length} diferencia(s) después.`);
      setCoherencia(null);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo reconstruir.");
    } finally {
      setOcupado(false);
    }
  }
  useEffect(() => { cargar(); }, [fondoId]);

  async function rearmar() {
    setOcupado(true);
    setError("");
    try {
      setEstado(await pedir<EstadoGrafo>(`/api/exportacion/grafo/sincronizar?fondo_id=${fondoId}`, { method: "POST" }));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo rearmar.");
    } finally {
      setOcupado(false);
    }
  }

  if (!estado) return null;
  const propios = estado.grafos.filter((g) => g.fondo_id === fondoId);
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Grafo RiC-O guardado</div>
      <div className="tarjeta-cuerpo">
        <p className="meta">
          La descripción publicada vive como grafo RDF en un almacén de tripletas y es la fuente de verdad: publicar es
          escribir en él, validado antes contra RiC-O 1.1 (OWL y SHACL); el SPARQL, las URI y las descargas leen de aquí,
          y las tablas del sistema se pueden rehacer desde él. Lo que RiC-O no puede expresar (procedencia del dato,
          años de retención, archivo de cada instanciación) va en un grafo de control interno, que nunca se publica.
          {estado.almacen.ok && estado.almacen.motor && <> Motor: {estado.almacen.motor}.</>}
        </p>
        {error && <div className="aviso error" role="alert">{error}</div>}
        {!estado.almacen.ok && <div className="aviso error" role="alert">{estado.almacen.motivo}</div>}
        <table className="tabla-permisos">
          <thead><tr><th>Grafo</th><th>Estado</th><th>Tripletas</th><th>RiC-O 1.1</th><th>Actualizado</th></tr></thead>
          <tbody>
            {propios.map((g) => (
              <tr key={g.alcance}>
                <td>{ALCANCE[g.alcance] || g.alcance}<div className="meta"><code>{g.nombre}</code></div></td>
                <td>{g.error ? <span className="insignia alerta" title={g.error}>Con error</span>
                  : g.al_dia ? <span className="insignia bien">Al día</span> : <span className="insignia proceso">Actualizándose</span>}</td>
                <td>{g.tripletas ?? "—"}</td>
                <td>{g.conforme == null ? "—" : g.conforme ? "Conforme" : "No conforme"}</td>
                <td className="meta">{g.sincronizado_en ? new Date(g.sincronizado_en).toLocaleString("es-CO") : "—"}
                  {g.huella && <div title={`SHA-256 del grafo guardado: ${g.huella}`}>huella {g.huella.slice(0, 12)}…</div>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {coherencia && (
          <div className={`aviso ${coherencia.coinciden ? "bien" : "error"}`} role="status">
            {coherencia.coinciden ? "Las tablas coinciden con el grafo guardado." : (
              <>Las tablas no coinciden con el grafo en {coherencia.diferencias.length} dato(s); el grafo es la fuente de verdad.
                <ul>{coherencia.diferencias.slice(0, 8).map((d) => (
                  <li key={`${d.id}-${d.columna}`}>{d.tabla}{d.columna ? ` · ${d.columna}` : ""}: {d.problema}</li>))}</ul></>
            )}
          </div>
        )}
        {rehecho && <div className="aviso bien" role="status">{rehecho}</div>}
        <div className="acciones" style={{ marginTop: 10 }}>
          <button type="button" className="boton chico" disabled={ocupado} onClick={comparar}>Comparar tablas con el grafo</button>
          {usuario?.es_administrador && (
            <>
              <button type="button" className="boton chico" disabled={ocupado} onClick={rearmar}>
                {ocupado ? "Trabajando…" : "Rearmar el grafo"}</button>
              {coherencia && !coherencia.coinciden && (
                <button type="button" className="boton chico peligro" disabled={ocupado} onClick={reconstruir}>
                  Rehacer las tablas desde el grafo</button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function ExportacionRico({ fondo }: { fondo: { id: string; titulo: string } }) {
  const { usuario } = useSesion();
  const esAdmin = !!usuario?.es_administrador;
  const conReservado = tienePermiso(usuario, "catalogo", "escribir");
  const [reporte, setReporte] = useState<Reporte | null>(null);
  const [incluir, setIncluir] = useState(false);
  const [ocupado, setOcupado] = useState("");
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");

  async function bajar(formato: "turtle" | "jsonld") {
    setOcupado(formato);
    setError("");
    setAviso("");
    try {
      const cabeceras = await descargar(`/api/exportacion/rdf?fondo_id=${fondo.id}&formato=${formato}&incluir_restringidos=${incluir}`);
      // Cada descarga se valida en el servidor (OWL y SHACL); si no pasó, se avisa aquí.
      if (cabeceras.get("X-RICORA-Conformidad") === "no-conforme")
        setAviso("El archivo se descargó, pero no pasó la validación RiC-O. Quedó una alerta para la administración; use «Validar conformidad» para ver el detalle.");
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo exportar.");
    } finally {
      setOcupado("");
    }
  }

  async function otro(ruta: string, clave: string) {
    setOcupado(clave);
    setError("");
    try {
      await descargar(ruta);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo descargar.");
    } finally {
      setOcupado("");
    }
  }

  async function validar() {
    setOcupado("validar");
    setError("");
    try {
      setReporte(await pedir<Reporte>(`/api/exportacion/conformidad?fondo_id=${fondo.id}&incluir_restringidos=${incluir}`));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo validar.");
    } finally {
      setOcupado("");
    }
  }

  async function cambiarPublicas(publicas: boolean) {
    setOcupado("uris");
    try {
      await pedir("/api/exportacion/uris-publicas", { method: "PUT", body: JSON.stringify({ publicas }) });
      if (reporte) setReporte({ ...reporte, uris_publicas: publicas });
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cambiar.");
    } finally {
      setOcupado("");
    }
  }

  return (
    <>
      <h1>RiC-O</h1>
      <p className="sub">
        El fondo como datos enlazados, en la ontología oficial del Consejo Internacional de Archivos (RiC-O 1.1).
        Cada descripción publicada, su contexto y sus instanciaciones, con una URI propia.
      </p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {aviso && <div className="aviso" role="status">{aviso}</div>}
      <GrafoPersistente fondoId={fondo.id} />

      <div className="tarjeta">
        <div className="tarjeta-cab">Exportar</div>
        <div className="tarjeta-cuerpo">
          <p className="meta">
            Nunca salen el origen ni la confianza de un dato (motor o persona), los borradores ni los programas que
            actúan en el sistema. Por defecto tampoco lo clasificado o reservado (Ley 1712 de 2014).
          </p>
          {conReservado && (
            <label className="meta" style={{ display: "flex", gap: 8, alignItems: "center", margin: "8px 0" }}>
              <input type="checkbox" checked={incluir} onChange={(e) => setIncluir(e.target.checked)} />
              Incluir lo clasificado o reservado (queda en la auditoría)
            </label>
          )}
          <div className="acciones">
            <button type="button" className="boton primario" disabled={!!ocupado} onClick={() => bajar("turtle")}>
              {ocupado === "turtle" ? "Exportando…" : "Descargar Turtle (.ttl)"}
            </button>
            <button type="button" className="boton" disabled={!!ocupado} onClick={() => bajar("jsonld")}>
              {ocupado === "jsonld" ? "Exportando…" : "Descargar JSON-LD"}
            </button>
            <button type="button" className="boton" disabled={!!ocupado} onClick={validar}>
              {ocupado === "validar" ? "Validando…" : "Validar conformidad"}
            </button>
          </div>
        </div>
      </div>

      <div className="tarjeta">
        <div className="tarjeta-cab">Otros formatos y datos abiertos</div>
        <div className="tarjeta-cuerpo">
          <p className="meta">
            Solo lo público (sin lo clasificado ni lo reservado). EAD3 y EAC-CPF se validan contra el esquema oficial
            de la SAA antes de descargarse.
          </p>
          <div className="acciones">
            <button type="button" className="boton" disabled={!!ocupado}
                    onClick={() => otro(`/api/publico/ead3?fondo_id=${fondo.id}`, "ead3")}>
              {ocupado === "ead3" ? "Exportando…" : "Descargar EAD3 (.xml)"}</button>
            <button type="button" className="boton" disabled={!!ocupado}
                    onClick={() => otro(`/api/publico/ley1712?fondo_id=${fondo.id}&formato=xlsx`, "ley1712")}>
              {ocupado === "ley1712" ? "Exportando…" : "Índice de información clasificada y reservada (Ley 1712)"}</button>
          </div>
          <p className="meta" style={{ marginBottom: 0 }}>
            Consulta SPARQL de solo lectura: <code>/api/publico/sparql?fondo_id={fondo.id}&amp;query=…</code>. La ficha
            de cada agente se descarga en EAC-CPF desde Vocabularios, y cada descripción pública tiene su manifiesto IIIF
            en <code>/api/publico/iiif/&lt;id&gt;/manifest</code>.
          </p>
        </div>
      </div>

      {reporte && <ReporteConformidad r={reporte} />}

      {reporte && (
        <div className="tarjeta">
          <div className="tarjeta-cab">URI de los nodos</div>
          <div className="tarjeta-cuerpo">
            <p>URI del fondo: <code>{reporte.uri_fondo}</code></p>
            <p className="meta">
              Cada URI devuelve la descripción RDF del nodo (Turtle, o JSON-LD con <code>Accept: application/ld+json</code>
              {" "}o la extensión <code>.jsonld</code>). Lo clasificado o reservado no se resuelve nunca por esta vía.
            </p>
            <p>
              Resolución sin iniciar sesión:{" "}
              <span className={`insignia ${reporte.uris_publicas ? "alerta" : "neutra-borde"}`}>
                {reporte.uris_publicas ? "encendida" : "apagada"}
              </span>
            </p>
            {esAdmin && (
              <>
                {!reporte.uris_publicas && (
                  <div className="aviso">
                    Encenderla publica en internet todo lo descrito con acceso público. Hágalo solo con el servidor en
                    HTTPS y después de revisar los derechos de acceso del fondo.
                  </div>
                )}
                <button type="button" className="boton" disabled={!!ocupado}
                        onClick={() => cambiarPublicas(!reporte.uris_publicas)}>
                  {reporte.uris_publicas ? "Apagar la resolución pública" : "Encender la resolución pública"}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function ReporteConformidad({ r }: { r: Reporte }) {
  const omitidas = Object.entries(r.omitidas).filter(([, n]) => n > 0);
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">
        Conformidad con {r.ontologia}{" "}
        <span className={`insignia ${r.conforme ? "bien" : "error"}`}>{r.conforme ? "conforme" : "no conforme"}</span>
      </div>
      <div className="tarjeta-cuerpo">
        <dl className="par-dato">
          <dt>Ontología oficial (OWL)</dt>
          <dd>{r.owl.conforme ? "Cada clase y propiedad existe, con su dominio y su rango" : `${r.owl.problemas.length} problema(s)`}</dd>
          <dt>Perfil SHACL del sistema</dt>
          <dd>{r.shacl.conforme ? `Cumple las ${r.shacl.formas} formas` : `${r.shacl.resultados.length} incumplimiento(s)`}</dd>
          <dt>Mapeo único contra el OWL</dt>
          <dd>{r.mapeo.problemas.length === 0 ? "Sin problemas" : `${r.mapeo.problemas.length} problema(s)`}</dd>
          <dt>Tripletas</dt><dd>{r.tripletas.toLocaleString("es-CO")}</dd>
        </dl>
        {r.owl.problemas.length > 0 && (
          <ul>{r.owl.problemas.map((p) => <li key={p}>{p}</li>)}</ul>
        )}
        {r.shacl.resultados.length > 0 && (
          <table className="tabla">
            <thead><tr><th>Nodo</th><th>Propiedad</th><th>Qué falla</th></tr></thead>
            <tbody>
              {r.shacl.resultados.slice(0, 50).map((x, i) => (
                <tr key={i}><td><code>{x.foco?.split("/id/")[1] || x.foco}</code></td><td>{x.ruta || x.forma}</td><td>{x.mensaje}</td></tr>
              ))}
            </tbody>
          </table>
        )}
        <h4>Por clase de RiC-O</h4>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {Object.entries(r.por_clase).map(([c, n]) => <span key={c} className="insignia neutra-borde"><code>rico:{c}</code> {n}</span>)}
        </div>
        {omitidas.length > 0 && (
          <>
            <h4>No exportado, y por qué</h4>
            <ul>{omitidas.map(([m, n]) => <li key={m}>{m}: {n}</li>)}</ul>
          </>
        )}
        <details>
          <summary>Datos que el sistema guarda y RiC-O no puede expresar</summary>
          <ul>{Object.entries(r.sin_propiedad).map(([k, v]) => <li key={k}><b>{k}</b>: {v}</li>)}</ul>
        </details>
      </div>
    </div>
  );
}
