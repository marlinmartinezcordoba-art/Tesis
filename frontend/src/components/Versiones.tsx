// Versiones de una descripción (RF-RIC-001) y atributos con su fuente
// (RF-RIC-002). Cada corrección deja una versión numerada que no se borra;
// restaurar una anterior crea una versión nueva.
import { useCallback, useEffect, useState } from "react";
import { ErrorAPI, pedir } from "@/lib/api";
import { fecha } from "@/lib/formato";

interface Cambio {
  campo: string;
  etiqueta: string;
  antes?: unknown;
  despues?: unknown;
  fuente_antes?: string | null;
  fuente_despues?: string | null;
  agregados?: string[];
  quitados?: string[];
}

interface Version {
  numero: number;
  motivo: string;
  motivo_nombre: string;
  restaurada_de: number | null;
  autor: string | null;
  creada_en: string;
  integra: boolean;
  con_contexto: boolean;
  cambios: Cambio[];
}

export interface AtributoConFuente {
  clave: string;
  etiqueta: string;
  valor: unknown;
  fuente: string;
  confianza: number | null;
  cardinalidad: string;
  rico: string | null;
  isad: string | null;
}

const FUENTE: Record<string, string> = { motor: "Motor", motor_editado: "Motor, corregido", persona: "Persona" };

function texto(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "—";
  const s = String(v);
  return s.length > 160 ? `${s.slice(0, 160)}…` : s;
}

export function VersionesDescripcion({ recursoId, puede, editando, alRestaurar, marca }: {
  recursoId: string; puede: boolean; editando: boolean; alRestaurar: (r: unknown) => void; marca: unknown;
}) {
  const [versiones, setVersiones] = useState<Version[] | null>(null);
  const [abierta, setAbierta] = useState<number | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(() => {
    pedir<Version[]>(`/api/descripcion/registros/${recursoId}/versiones`).then(setVersiones)
      .catch((e) => setError(e instanceof ErrorAPI ? e.message : "No se pudieron cargar las versiones."));
  }, [recursoId]);
  useEffect(cargar, [cargar, marca]);

  async function restaurar(n: number) {
    if (!window.confirm(`¿Volver a los datos de la versión ${n}? Se crea una versión nueva; ninguna se pierde.`)) return;
    setError("");
    try {
      alRestaurar(await pedir(`/api/descripcion/registros/${recursoId}/versiones/${n}/restaurar`, { method: "POST" }));
    } catch (e) {
      setError(e instanceof ErrorAPI ? e.message : "No se pudo restaurar.");
    }
  }

  if (!versiones) return null;
  const vigente = versiones[0]?.numero;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Versiones ({versiones.length})</div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {versiones.map((v) => (
        <div key={v.numero} className="fila version-fila">
          <div className="fila-principal">
            <div className="nombre">
              Versión {v.numero} · {v.motivo_nombre}{v.restaurada_de ? ` de la versión ${v.restaurada_de}` : ""}
              {v.numero === vigente && <span className="insignia bien" style={{ marginLeft: 8 }}>Vigente</span>}
              {!v.integra && <span className="insignia error" style={{ marginLeft: 8 }}>¡Alterada!</span>}
            </div>
            <div className="meta">
              {fecha(v.creada_en)}{v.autor ? ` · ${v.autor}` : ""}
              {v.cambios.length > 0 && <> · {v.cambios.length} cambio{v.cambios.length === 1 ? "" : "s"}{" "}
                <button type="button" className="enlace" onClick={() => setAbierta(abierta === v.numero ? null : v.numero)}>
                  {abierta === v.numero ? "ocultar" : "ver"}
                </button></>}
              {!v.con_contexto && " · sin el contexto anterior al versionado"}
            </div>
            {abierta === v.numero && (
              <ul className="version-cambios">
                {v.cambios.map((c) => (
                  <li key={c.campo}>
                    <b>{c.etiqueta}:</b>{" "}
                    {c.agregados || c.quitados ? (
                      <>{c.agregados?.length ? <span className="agregado">+ {c.agregados.join(" · ")}</span> : null}
                        {c.quitados?.length ? <span className="quitado"> − {c.quitados.join(" · ")}</span> : null}</>
                    ) : (
                      <><span className="quitado">{texto(c.antes)}</span> → <span className="agregado">{texto(c.despues)}</span>
                        {c.fuente_antes !== c.fuente_despues && c.fuente_despues && (
                          <span className="meta"> ({FUENTE[c.fuente_antes || ""] || "—"} → {FUENTE[c.fuente_despues] || c.fuente_despues})</span>
                        )}</>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          {puede && !editando && v.numero !== vigente && (
            <button type="button" className="boton chico" onClick={() => restaurar(v.numero)}>Restaurar</button>
          )}
        </div>
      ))}
      <p className="pista" style={{ padding: "0 16px 12px" }}>
        Restaurar devuelve los atributos (título, alcance, notas, datos de control…) con su procedencia. Las entidades y
        relaciones tienen su propia historia: se corrigen desde «Corregir».
      </p>
    </div>
  );
}

export function AtributosConFuente({ atributos }: { atributos: AtributoConFuente[] }) {
  if (!atributos.length) return null;
  return (
    <details className="tarjeta atributos-fuente">
      <summary className="tarjeta-cab">Atributos, fuente y cardinalidad ({atributos.length})</summary>
      <table className="tabla-permisos">
        <thead><tr><th>Atributo</th><th>Valor</th><th>Fuente</th><th>Cardinalidad</th><th>RiC-O</th></tr></thead>
        <tbody>
          {atributos.map((a) => (
            <tr key={a.clave}>
              <td>{a.etiqueta}{a.isad && <span className="meta"> · {a.isad}</span>}</td>
              <td>{texto(a.valor)}</td>
              <td>{FUENTE[a.fuente] || a.fuente}{a.confianza !== null && ` (${Math.round(a.confianza * 100)} %)`}</td>
              <td><code>{a.cardinalidad}</code></td>
              <td>{a.rico ? <code>{a.rico}</code> : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
