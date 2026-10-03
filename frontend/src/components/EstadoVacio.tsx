import type { ReactNode } from "react";

const trazo = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
const ICONOS: Record<string, ReactNode> = {
  filtro: <path d="M4 5h16l-6 7.5V19l-4-2v-4.5z" />,
  grafo: <><circle cx="12" cy="6" r="2.2" /><circle cx="6" cy="17" r="2.2" /><circle cx="18" cy="17" r="2.2" /><path d="M10.5 7.5L7.5 15M13.5 7.5l3 7.5" /></>,
  documento: <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4M9 12h6M9 16h4" /></>,
  lista: <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />,
  fusion: <><circle cx="6" cy="6" r="2.5" /><circle cx="6" cy="18" r="2.5" /><circle cx="18" cy="12" r="2.5" /><path d="M8.5 6.5c4 .5 5 3 7 5M8.5 17.5c4-.5 5-3 7-5" /></>,
  carga: <path d="M12 4v10m0 0l-3.5-3.5M12 14l3.5-3.5M5 16v2a2 2 0 002 2h10a2 2 0 002-2v-2" />,
  bien: <><circle cx="12" cy="12" r="8.5" /><path d="M8.5 12.5l2.3 2.3 4.7-4.8" /></>,
};

// Estado vacío con mensaje y acción: ninguna pantalla queda en blanco sin
// explicar por qué ni qué hacer a continuación.
export function EstadoVacio({ icono = "lista", titulo, texto, accion, children }: {
  icono?: keyof typeof ICONOS | string;
  titulo: string;
  texto?: ReactNode;
  accion?: { texto: string; alHacer: () => void };
  children?: ReactNode;
}) {
  return (
    <div className="estado-vacio" role="status">
      <svg viewBox="0 0 24 24" width="34" height="34" aria-hidden="true" {...trazo}>{ICONOS[icono] || ICONOS.lista}</svg>
      <strong>{titulo}</strong>
      {texto && <p>{texto}</p>}
      {children}
      {accion && <button type="button" className="boton chico primario" onClick={accion.alHacer}>{accion.texto}</button>}
    </div>
  );
}
