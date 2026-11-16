// Descripción por componentes RiC: el estado de cada parte de la descripción
// (no las áreas de ISAD(G)), el contexto funcional (función → actividad →
// recurso) y las manifestaciones física y digital del recurso.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { pedir } from "@/lib/api";

type Estado = "completo" | "parcial" | "por_completar";
interface Componente { clave: string; nombre: string; ric: string; estado: Estado; tiene: string[]; falta: string[] }
interface Componentes { componentes: Componente[]; completos: number; total: number }

const ESTADO: Record<Estado, { texto: string; clase: string }> = {
  completo: { texto: "Completo", clase: "bien" },
  parcial: { texto: "Parcial", clase: "alerta" },
  por_completar: { texto: "Por completar", clase: "" },
};
const ICONO: Record<string, string> = {
  recurso: "▤", agentes: "◍", funciones: "⚙", relaciones: "⇄", tiempo_lugar: "⌖", custodia: "▣", fuentes: "✓",
};

export interface ActividadDescrita {
  valor: string;
  contexto?: { tipo_actividad?: { nombre: string } | null; ejercida_por?: { nombre: string }[] };
}
export interface InstanciacionDescrita {
  id: string; nombre: string; fisica?: boolean; soporte?: string | null; ubicacion?: string | null; signatura?: string | null;
}

export function ComponentesRic({ recursoId, titulo, identificador, actualizado, actividades, instanciaciones }: {
  recursoId: string; titulo: string; identificador: string | null; actualizado: string | null;
  actividades: ActividadDescrita[]; instanciaciones: InstanciacionDescrita[];
}) {
  const [datos, setDatos] = useState<Componentes | null>(null);
  const [abierto, setAbierto] = useState<string | null>(null);
  useEffect(() => {
    pedir<Componentes>(`/api/descripcion/registros/${recursoId}/componentes-ric`).then(setDatos).catch(() => setDatos(null));
  }, [recursoId, actualizado]);
  if (!datos) return null;
  const completa = datos.completos === datos.total;
  const fisicas = instanciaciones.filter((i) => i.fisica);
  const digitales = instanciaciones.filter((i) => !i.fisica);

  return (
    <div className="tarjeta componentes-ric">
      <div className="tarjeta-cab">
        <div>
          <div>Descripción archivística RiC · {titulo}</div>
          <div className="meta">Identificador: {identificador || "sin asignar"}</div>
        </div>
        <span className={`insignia ${completa ? "bien" : "alerta"}`}>
          {completa ? "Completa" : `En construcción · ${datos.completos} de ${datos.total}`}</span>
      </div>
      <ol className="componentes-lista">
        {datos.componentes.map((c, n) => {
          const e = ESTADO[c.estado];
          return (
            <li key={c.clave}>
              <button type="button" className="componente-fila" aria-expanded={abierto === c.clave}
                      onClick={() => setAbierto(abierto === c.clave ? null : c.clave)}>
                <span className="componente-icono" aria-hidden="true">{ICONO[c.clave] || "•"}</span>
                <span className="componente-nombre">{String(n + 1).padStart(2, "0")}. {c.nombre}</span>
                <span className={`insignia ${e.clase}`}>{e.texto}</span>
              </button>
              {abierto === c.clave && (
                <div className="componente-detalle">
                  <div className="meta"><code className="rico">{c.ric}</code></div>
                  {c.tiene.length > 0 && <ul>{c.tiene.map((t) => <li key={t}>{t}</li>)}</ul>}
                  {c.falta.length > 0 && <p className="pista">Falta: {c.falta.join("; ")}.</p>}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {actividades.length > 0 && (
        <div className="tarjeta-cuerpo">
          <div className="componente-subtitulo">Contexto funcional</div>
          {actividades.map((a) => (
            <div className="cadena-funcional" key={a.valor}>
              <div className="eslabon funcion"><span className="meta">Función (tipo de actividad)</span>
                {a.contexto?.tipo_actividad?.nombre || <span className="meta">Sin registrar</span>}</div>
              <div className="conector">↓ <span className="meta">se desarrolla mediante</span></div>
              <div className="eslabon actividad"><span className="meta">Actividad</span>{a.valor}
                {a.contexto?.ejercida_por?.length ? <span className="meta"> · ejercida por {a.contexto.ejercida_por.map((x) => x.nombre).join(", ")}</span> : null}</div>
              <div className="conector">↓ <span className="meta">se documenta en (RiC-R033)</span></div>
              <div className="eslabon recurso"><span className="meta">Recurso documental</span>{titulo}</div>
            </div>
          ))}
        </div>
      )}

      {instanciaciones.length > 0 && (
        <div className="tarjeta-cuerpo">
          <div className="componente-subtitulo">Manifestaciones del recurso</div>
          <div className="manifestaciones">
            {fisicas.map((i) => (
              <div className="manifestacion" key={i.id}>
                <span className="componente-icono" aria-hidden="true">▤</span>
                <strong>Manifestación física</strong>
                <span className="meta">{i.soporte || "Original"}{i.ubicacion ? ` · ${i.ubicacion}` : ""}{i.signatura ? ` · ${i.signatura}` : ""}</span>
              </div>
            ))}
            {digitales.map((i) => (
              <div className="manifestacion" key={i.id}>
                <span className="componente-icono digital" aria-hidden="true">▧</span>
                <strong>Manifestación digital</strong>
                <span className="meta">{i.nombre}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="tarjeta-cuerpo componente-pie">
        <Link to={`/instrumentos?vista=grafo&centro=recurso_documental:${recursoId}`}>Visualizar en el grafo</Link>
      </div>
    </div>
  );
}
