import { useState } from "react";
import { ErrorAPI, subir } from "@/lib/api";
import { useFondo } from "@/lib/fondo";
import { ResultadoValidacion, TablaVistaPrevia, type Validacion, type Vista } from "@/components/CuadroClasificacion";

// Importar un fondo descrito en RiC-O 1.1 por otro sistema. El cuadro sale de la
// parametrización (filas del CCD y la TRD deducidas del árbol de rico:RecordSet);
// el resto del grafo va al vocabulario, los expedientes, los documentos y las relaciones.

interface Previa {
  fondo: string | null; niveles: Record<string, number>; entidades: Record<string, number>; filas_cuadro: number;
  filas_con_problemas: number; series_sin_seccion: number; productor_sugerido: string | null;
  omitidas: Record<string, number>; problemas: string[]; filas: Vista["filas"];
  trd: { nombre: string | null; acto_aprobacion: string | null; fecha_aprobacion: string | null;
    vigente_desde: string | null } | null;
}
export interface Importado {
  creado: boolean; fondo: { id: string; titulo: string } | null; validacion: Validacion;
  parametrizacion: Record<string, number> | null; contenido: Record<string, number>;
  omitidas: Record<string, number>; version: { nombre: string; estado: string } | null;
}

const NIVEL: Record<string, string> = { fondo: "fondo", seccion: "sección(es)", subseccion: "subsección(es)",
  serie: "serie(s)", subserie: "subserie(s)", expediente: "expediente(s)", unidad_documental: "documento(s)",
  coleccion: "colección(es)" };
const CLASE: Record<string, string> = { agente: "agente(s)", lugar: "lugar(es)", forma_documental: "forma(s) documental(es)",
  actividad: "actividad(es)", tipo_actividad: "función(es)", mandato: "mandato(s)", materia: "materia(s)" };

export function ImportarRico({ alImportar }: { alImportar: (r: Importado) => void }) {
  const { recargar, elegir } = useFondo();
  const [archivo, setArchivo] = useState<File | null>(null);
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [titulo, setTitulo] = useState("");
  const [seccion, setSeccion] = useState({ nombre: "", codigo: "" });
  const [acto, setActo] = useState({ acto_aprobacion: "", fecha_aprobacion: "", vigente_desde: "" });
  const [prueba, setPrueba] = useState<Importado | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");

  function datos(extra: Record<string, string> = {}) {
    const f = new FormData();
    if (archivo) f.append("archivo", archivo, archivo.name);
    const campos: Record<string, string> = { titulo, seccion_nombre: seccion.nombre, seccion_codigo: seccion.codigo,
      ...acto, ...extra };
    Object.entries(campos).forEach(([k, v]) => v && f.append(k, v));
    return f;
  }

  async function leer(a: File) {
    setArchivo(a);
    setError("");
    setPrueba(null);
    setOcupado(true);
    try {
      const f = new FormData();
      f.append("archivo", a, a.name);
      const p = await subir<Previa>("/api/importacion/rico/vista-previa", f, () => undefined);
      setPrevia(p);
      setTitulo(p.fondo || "");
      setSeccion({ nombre: p.productor_sugerido || "", codigo: "" });
      // Si el archivo trae la TRD vigente con su acto, sus datos llenan la versión 1.
      setActo({ acto_aprobacion: p.trd?.acto_aprobacion || "", fecha_aprobacion: p.trd?.fecha_aprobacion || "",
        vigente_desde: p.trd?.vigente_desde || "" });
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo leer el archivo.");
    } finally {
      setOcupado(false);
    }
  }

  async function enviar(crear: boolean) {
    setError("");
    setOcupado(true);
    try {
      const r = await subir<Importado>("/api/importacion/rico", datos(crear ? { crear: "1" } : {}), () => undefined);
      setPrueba(r);
      if (crear && r.creado && r.fondo) {
        await recargar();
        elegir(r.fondo.id);
        alImportar(r);
      }
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo importar.");
    } finally {
      setOcupado(false);
    }
  }

  const lista = (o: Record<string, number>, nombres: Record<string, string>) =>
    Object.entries(o).map(([k, n]) => `${n} ${nombres[k] || k}`).join(", ") || "—";

  return (
    <>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <p className="meta" style={{ marginTop: 0 }}>
        Un fondo descrito en RiC-O 1.1 por otro sistema (Turtle, RDF/XML, JSON-LD o N-Triples). Las secciones, series y
        subseries se convierten en el CCD y la TRD del fondo, y entran por la parametrización como cualquier otro; los
        agentes, lugares, expedientes, documentos y relaciones se llevan a sus tablas. Antes de crear se valida en RiC-O.
      </p>
      <label className="boton chico primario">
        {ocupado && !previa ? "Leyendo…" : previa ? "Leer otro archivo" : "Leer el archivo RiC-O"}
        <input type="file" accept=".ttl,.rdf,.xml,.owl,.jsonld,.json,.nt" hidden disabled={ocupado}
               onChange={(e) => e.target.files?.[0] && leer(e.target.files[0])} />
      </label>
      {previa && (
        <>
          <div className="tarjeta" style={{ marginTop: 12 }}>
            <div className="tarjeta-cab">Lo que trae el archivo</div>
            <div className="tarjeta-cuerpo">
              <ul>
                <li><strong>Niveles:</strong> {lista(previa.niveles, NIVEL)}</li>
                <li><strong>Vocabulario:</strong> {lista(previa.entidades, CLASE)}</li>
                <li><strong>Cuadro:</strong> {previa.filas_cuadro} serie(s) o subserie(s) para la TRD
                  {previa.filas_con_problemas ? `, ${previa.filas_con_problemas} con problemas` : ""}</li>
              </ul>
              {previa.problemas.map((p) => <div key={p} className="aviso error">{p}</div>)}
              {Object.keys(previa.omitidas).length > 0 && (
                <details><summary className="meta">Lo que no se importa ({Object.values(previa.omitidas).reduce((a, b) => a + b, 0)})</summary>
                  <ul className="meta">{Object.entries(previa.omitidas).map(([k, n]) => <li key={k}>{n} · {k}</li>)}</ul>
                </details>
              )}
              {previa.filas.length > 0 && (
                <details><summary className="meta">Filas del CCD y la TRD deducidas</summary>
                  <div className="tabla-desplazable">
                    <TablaVistaPrevia vista={{ origen: "RiC-O", filas: previa.filas, resumen: {} }}
                                      incluir={new Set(previa.filas.map((f) => f.fila))} setIncluir={() => undefined} />
                  </div>
                </details>
              )}
            </div>
          </div>
          <div className="rejilla">
            <div className="campo">
              <label htmlFor="i-titulo">Nombre del fondo</label>
              <input id="i-titulo" className="entrada" value={titulo} onChange={(e) => setTitulo(e.target.value)} />
            </div>
          </div>
          {previa.series_sin_seccion > 0 && (
            <>
              <div className="aviso alerta">{previa.series_sin_seccion} serie(s) cuelgan directo del fondo, sin sección. En
                el CCD toda serie tiene su dependencia productora: indíquela{previa.productor_sugerido
                  ? " (se sugiere el productor del fondo)" : ""}.</div>
              <div className="rejilla">
                <div className="campo">
                  <label htmlFor="i-sec-cod">Código de la dependencia</label>
                  <input id="i-sec-cod" className="entrada" value={seccion.codigo}
                         onChange={(e) => setSeccion({ ...seccion, codigo: e.target.value })} />
                </div>
                <div className="campo">
                  <label htmlFor="i-sec-nom">Dependencia productora</label>
                  <input id="i-sec-nom" className="entrada" value={seccion.nombre}
                         onChange={(e) => setSeccion({ ...seccion, nombre: e.target.value })} />
                </div>
              </div>
            </>
          )}
          <p className="meta">{previa.trd?.acto_aprobacion
            ? `El archivo trae la TRD vigente (${previa.trd.nombre || "TRD"}) con su acto: revise los datos.`
            : "Si la TRD está aprobada, registre su acto: el fondo nace con la versión 1 vigente."}</p>
          <div className="rejilla">
            <div className="campo">
              <label htmlFor="i-acto">Acto que aprueba la TRD (opcional)</label>
              <input id="i-acto" className="entrada" value={acto.acto_aprobacion}
                     onChange={(e) => setActo({ ...acto, acto_aprobacion: e.target.value })} />
            </div>
            <div className="campo">
              <label htmlFor="i-fecha">Fecha de aprobación</label>
              <input id="i-fecha" type="date" className="entrada" value={acto.fecha_aprobacion}
                     onChange={(e) => setActo({ ...acto, fecha_aprobacion: e.target.value })} />
            </div>
            <div className="campo">
              <label htmlFor="i-desde">Rige desde</label>
              <input id="i-desde" type="date" className="entrada" value={acto.vigente_desde}
                     onChange={(e) => setActo({ ...acto, vigente_desde: e.target.value })} />
            </div>
          </div>
          {prueba && !prueba.creado && <ResultadoValidacion v={prueba.validacion} />}
          <div className="acciones">
            <button type="button" className="boton" disabled={ocupado || previa.problemas.length > 0}
                    onClick={() => enviar(false)}>{ocupado ? "Validando…" : "Validar en RiC-O"}</button>
            <button type="button" className="boton primario" disabled={ocupado || !prueba?.validacion.conforme}
                    title={prueba?.validacion.conforme ? undefined : "Primero valide en RiC-O"} onClick={() => enviar(true)}>
              Importar el fondo</button>
          </div>
        </>
      )}
    </>
  );
}
