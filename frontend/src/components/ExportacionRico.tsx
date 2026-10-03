import { useState } from "react";
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

export function ExportacionRico({ fondo }: { fondo: { id: string; titulo: string } }) {
  const { usuario } = useSesion();
  const esAdmin = !!usuario?.es_administrador;
  const conReservado = tienePermiso(usuario, "catalogo", "escribir");
  const [reporte, setReporte] = useState<Reporte | null>(null);
  const [incluir, setIncluir] = useState(false);
  const [ocupado, setOcupado] = useState("");
  const [error, setError] = useState("");

  async function bajar(formato: "turtle" | "jsonld") {
    setOcupado(formato);
    setError("");
    try {
      await descargar(`/api/exportacion/rdf?fondo_id=${fondo.id}&formato=${formato}&incluir_restringidos=${incluir}`);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo exportar.");
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
