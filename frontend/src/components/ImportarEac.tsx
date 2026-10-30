import { useState } from "react";
import { ErrorAPI, subir } from "@/lib/api";

// Autoridades en EAC-CPF (2.0 o 2010), una o varias en un .zip, a la ficha ISAAR del
// fondo. La vista previa dice qué se crea y qué se completa; lo que la ficha ya tenía
// no se pisa (queda como aviso), y lo que EAC-CPF trae y aquí no entra se cuenta.

interface Autoridad {
  archivo: string; error?: string; nombre?: string; subtipo?: string; accion?: "crear" | "completar";
  campos?: Record<string, unknown>; otras_formas?: { nombre: string }[]; identificadores?: { esquema: string; valor: string }[];
  omitidas?: Record<string, number>; fondo_registro?: string;
}
interface Previa { autoridades: Autoridad[]; resumen: { crear: number; completar: number; con_error: number } }
interface Hecho { creadas: number; completadas: number; avisos: string[]; omitidas: Record<string, number> }

const SUBTIPO: Record<string, string> = { persona: "Persona", entidad_corporativa: "Entidad", familia: "Familia" };

export function ImportarEac({ fondoId, alTerminar }: { fondoId: string; alTerminar: () => void }) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [hecho, setHecho] = useState<Hecho | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");

  function datos(a: File) {
    const f = new FormData();
    f.append("archivo", a, a.name);
    f.append("fondo_id", fondoId);
    return f;
  }

  async function leer(a: File) {
    setArchivo(a);
    setError("");
    setHecho(null);
    setOcupado(true);
    try {
      setPrevia(await subir<Previa>("/api/vocabulario/eac/vista-previa", datos(a), () => undefined));
    } catch (err) {
      setPrevia(null);
      setError(err instanceof ErrorAPI ? err.message : "No se pudo leer el archivo.");
    } finally {
      setOcupado(false);
    }
  }

  async function importar() {
    if (!archivo) return;
    setOcupado(true);
    setError("");
    try {
      setHecho(await subir<Hecho>("/api/vocabulario/eac", datos(archivo), () => undefined));
      setPrevia(null);
      alTerminar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo importar.");
    } finally {
      setOcupado(false);
    }
  }

  const omitidas = (o: Record<string, number>) => Object.entries(o).map(([k, n]) => `${n} ${k}`).join("; ");
  return (
    <div>
      <p className="meta" style={{ marginTop: 0 }}>
        La ficha de una persona, familia o entidad en EAC-CPF (2.0 o 2010), como la exportan AtoM, ArchivesSpace o el
        mismo RICORA. Puede subir un .xml o un .zip con varias. Si el agente ya existe en el fondo, se completa su ficha
        sin cambiar lo que ya tiene.
      </p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <label className="boton chico primario">
        {ocupado && !previa ? "Leyendo…" : previa ? "Leer otro archivo" : "Leer el EAC-CPF (.xml o .zip)"}
        <input type="file" accept=".xml,.zip" hidden disabled={ocupado}
               onChange={(e) => e.target.files?.[0] && leer(e.target.files[0])} />
      </label>
      {previa && (
        <>
          <p className="meta">Se crearían {previa.resumen.crear} y se completarían {previa.resumen.completar}
            {previa.resumen.con_error ? ` · ${previa.resumen.con_error} archivo(s) con error` : ""}.</p>
          <div className="tabla-desplazable">
            <table className="tabla-permisos">
              <thead><tr><th>Autoridad</th><th>Tipo</th><th>Qué se hace</th><th>Trae</th><th>No entra por aquí</th></tr></thead>
              <tbody>
                {previa.autoridades.map((a) => (
                  <tr key={a.archivo} className={a.error ? "fila-problema" : undefined}>
                    <td><strong>{a.nombre || a.archivo}</strong>{a.error && <div className="meta">{a.error}</div>}</td>
                    <td>{a.subtipo ? SUBTIPO[a.subtipo] : "—"}</td>
                    <td>{a.accion === "crear" ? "Crear" : a.accion === "completar" ? "Completar la ficha existente" : "—"}
                      {a.fondo_registro && <div className="meta">Autoridad registrada en «{a.fondo_registro}»</div>}</td>
                    <td className="meta">{[...Object.keys(a.campos || {}),
                      a.otras_formas?.length ? `${a.otras_formas.length} otra(s) forma(s) del nombre` : "",
                      a.identificadores?.length ? `${a.identificadores.length} identificador(es)` : ""].filter(Boolean).join(", ")}</td>
                    <td className="meta">{a.omitidas ? omitidas(a.omitidas) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="acciones">
            <button type="button" className="boton primario" disabled={ocupado || !!previa.resumen.con_error
              || !(previa.resumen.crear + previa.resumen.completar)} onClick={importar}>
              {ocupado ? "Importando…" : "Importar las autoridades"}</button>
          </div>
        </>
      )}
      {hecho && (
        <div className="aviso bien" role="status">
          Se crearon {hecho.creadas} y se completaron {hecho.completadas} autoridad(es).
          {hecho.avisos.length > 0 && <ul>{hecho.avisos.map((x) => <li key={x}>{x}</li>)}</ul>}
          {Object.keys(hecho.omitidas).length > 0 && <div className="meta">No entraron por aquí: {omitidas(hecho.omitidas)}.</div>}
        </div>
      )}
    </div>
  );
}
