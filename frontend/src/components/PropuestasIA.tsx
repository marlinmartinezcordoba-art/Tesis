// Evidencia de la IA (brecha RF-AI-002): las propuestas del motor que
// llevaron a una descripción, como registro propio e inalterable. Muestra con
// qué modelo, versión e instrucción se generó cada una, cuándo, cuánto tardó,
// cómo terminó y si su huella sigue íntegra; permite guardar el registro
// completo (lo que recibió el motor y lo que respondió tal cual).
import { useState } from "react";
import { ErrorAPI, pedir } from "@/lib/api";
import { fecha } from "@/lib/formato";

export interface PropuestaRegistrada {
  id: string;
  motor: string | null;
  version_modelo: string | null;
  version_prompt: string | null;
  generada_en: string;
  duracion_ms: number | null;
  estado: string;
  estado_nombre: string;
  entidades: number;
  confianza_media: number | null;
  huella: string;
  integra: boolean;
}

function segundos(ms: number | null) {
  if (ms === null) return "—";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toLocaleString("es-CO", { maximumFractionDigits: 1 })} s`;
}

export function PropuestasIA({ propuestas, puede }: { propuestas: PropuestaRegistrada[]; puede: boolean }) {
  const [error, setError] = useState("");
  if (!propuestas.length) return null;

  async function guardar(p: PropuestaRegistrada) {
    setError("");
    try {
      const completa = await pedir<object>(`/api/descripcion/propuestas/${p.id}`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(completa, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `propuesta-motor-${p.id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo obtener la propuesta.");
    }
  }

  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Propuesta del motor (evidencia)</div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {propuestas.map((p) => (
        <div className="fila" key={p.id}>
          <div className="fila-principal">
            <div className="nombre">
              {p.motor}{p.version_modelo && p.version_modelo !== p.motor ? ` (versión ${p.version_modelo})` : ""}
              {p.version_prompt && <> · instrucción <code>{p.version_prompt}</code></>}
            </div>
            <div className="meta">
              Generada el {fecha(p.generada_en)} en {segundos(p.duracion_ms)} · {p.entidades} entidad{p.entidades === 1 ? "" : "es"}
              {p.confianza_media !== null && ` · confianza media ${Math.round(p.confianza_media * 100)} %`} · {p.estado_nombre}
            </div>
            <div className="meta">
              Huella SHA-256 <code title={p.huella}>{p.huella.slice(0, 16)}…</code>
            </div>
          </div>
          <span className={`insignia ${p.integra ? "bien" : "error"}`}>
            {p.integra ? "Íntegra: nadie la ha alterado" : "¡Alterada! La huella no coincide"}
          </span>
          {puede && <button type="button" className="boton chico" onClick={() => guardar(p)}>Guardar el registro completo</button>}
        </div>
      ))}
      <p className="pista" style={{ padding: "0 16px 12px" }}>
        Lo que propuso el motor no se puede cambiar ni borrar: es la base para comparar con lo que decidió la persona.
      </p>
    </div>
  );
}
