import { Link } from "react-router-dom";
import { SUBTIPO_MANDATO } from "@/lib/descripcion";

export interface FechaPublica {
  fecha_subtipo: string;
  edtf: string | null;
  fecha_legible: string | null;
}

export interface ContextoActividad {
  tipo_actividad: { id: string; nombre: string } | null;
  ejercida_por: { id: string; nombre: string }[];
  regulada_por: { id: string; nombre: string; subtipo: string | null; expedicion: FechaPublica | null }[];
  periodo: FechaPublica | null;
}

// La cadena actividad → tipo de actividad → mandato, con el agente que la
// ejerce (RiC-R033, hasActivityType, R060, R063, R067), leída del grafo.
export function CadenaActividad({ contexto, enlazar }: { contexto: ContextoActividad; enlazar: boolean }) {
  const vinculo = (id: string, nombre: string) => (enlazar ? <Link to={`/vocabularios/${id}`}>{nombre}</Link> : nombre);
  const partes = [];
  if (contexto.tipo_actividad) partes.push(<span key="t">tipo: {vinculo(contexto.tipo_actividad.id, contexto.tipo_actividad.nombre)}</span>);
  if (contexto.ejercida_por.length) {
    partes.push(<span key="a">ejercida por {contexto.ejercida_por.map((a, i) => <span key={a.id}>{i ? ", " : ""}{vinculo(a.id, a.nombre)}</span>)}</span>);
  }
  for (const m of contexto.regulada_por) {
    partes.push(
      <span key={m.id}>
        regulada por {vinculo(m.id, m.nombre)}
        {m.subtipo && m.subtipo !== "otro" ? ` (${SUBTIPO_MANDATO[m.subtipo].toLowerCase()}` : m.expedicion ? " (" : ""}
        {m.expedicion?.fecha_legible ? `${m.subtipo && m.subtipo !== "otro" ? ", " : ""}${m.expedicion.fecha_legible}` : ""}
        {(m.subtipo && m.subtipo !== "otro") || m.expedicion ? ")" : ""}
      </span>,
    );
  }
  if (contexto.periodo?.fecha_legible) partes.push(<span key="p">{contexto.periodo.fecha_legible}</span>);
  if (!partes.length) return null;
  return <div className="linea-contexto">{partes.map((p, i) => <span key={i}>{i ? " · " : ""}{p}</span>)}</div>;
}
