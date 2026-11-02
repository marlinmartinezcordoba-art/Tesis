import { useEffect, useRef, useState, type ReactNode } from "react";
import { useFondo } from "@/lib/fondo";

// Piezas del rediseño: encabezado de pantalla, indicadores medidos y menú de acciones secundarias.

/** Ceja (el fondo activo), título, descripción y la acción principal de la pantalla. */
export function Encabezado({ titulo, descripcion, acciones, ceja }: {
  titulo: string; descripcion?: ReactNode; acciones?: ReactNode; ceja?: string | null;
}) {
  const { fondo } = useFondo();
  const textoCeja = ceja === undefined ? fondo?.titulo : ceja;
  return (
    <header className="encabezado">
      <div>
        {textoCeja && <p className="ceja">{textoCeja}</p>}
        <h1>{titulo}</h1>
        {descripcion && <p className="sub">{descripcion}</p>}
      </div>
      {acciones && <div className="encabezado-acciones">{acciones}</div>}
    </header>
  );
}

export interface Indicador {
  etiqueta: string;
  valor: ReactNode;
  nota?: string;
  /** Proporción 0–1: dibuja una barra de avance. */
  avance?: number | null;
  tono?: "bien" | "alerta";
  icono?: ReactNode;
}

/** Cifras medidas del módulo. Nunca ilustrativas: cada una viene de la base. */
export function Indicadores({ items, etiqueta }: { items: Indicador[]; etiqueta: string }) {
  return (
    <section className="indicadores" aria-label={etiqueta}>
      {items.map((i) => (
        <div className={`indicador${i.tono ? ` ${i.tono}` : ""}${i.icono ? " con-icono" : ""}`} key={i.etiqueta}>
          {i.icono && <span className={`icono-indicador${i.tono === "bien" ? " bien" : ""}`} aria-hidden="true">{i.icono}</span>}
          <div style={{ flex: 1, minWidth: 0 }}>
          {i.icono ? <><strong>{i.valor}</strong><span className="etiqueta">{i.etiqueta}</span></>
            : <><span className="etiqueta">{i.etiqueta}</span><strong>{i.valor}</strong></>}
          {i.nota && <span className="nota" style={{ display: "block" }}>{i.nota}</span>}
          {i.avance != null && (
            <div className="barra" role="progressbar" aria-valuemin={0} aria-valuemax={100}
                 aria-valuenow={Math.round(i.avance * 100)} aria-label={i.etiqueta}>
              <i style={{ width: `${Math.max(0, Math.min(1, i.avance)) * 100}%` }} />
            </div>
          )}
          </div>
        </div>
      ))}
    </section>
  );
}

export interface Accion {
  texto: string;
  alHacer: () => void;
  peligro?: boolean;
  deshabilitada?: boolean;
  ayuda?: string;
}

/** Las acciones secundarias de una fila, en un menú (⋯): la principal queda a la vista. */
export function MenuAcciones({ acciones, etiqueta }: { acciones: Accion[]; etiqueta: string }) {
  const [abierto, setAbierto] = useState(false);
  const caja = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!abierto) return;
    const cerrar = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !caja.current?.contains(e.target as Node)) setAbierto(false);
    };
    document.addEventListener("mousedown", cerrar);
    document.addEventListener("keydown", cerrar);
    return () => {
      document.removeEventListener("mousedown", cerrar);
      document.removeEventListener("keydown", cerrar);
    };
  }, [abierto]);
  if (!acciones.length) return null;
  return (
    <div className="menu-acciones" ref={caja}>
      <button type="button" className="boton-icono" aria-haspopup="menu" aria-expanded={abierto} aria-label={etiqueta}
              title={etiqueta} onClick={() => setAbierto(!abierto)}>
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" />
        </svg>
      </button>
      {abierto && (
        <div className="menu" role="menu">
          {acciones.map((a) => (
            <button type="button" role="menuitem" key={a.texto} className={a.peligro ? "peligro" : undefined}
                    disabled={a.deshabilitada} title={a.ayuda}
                    onClick={() => { setAbierto(false); a.alHacer(); }}>{a.texto}</button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Ícono de documento para las filas. */
export function IconoDocumento() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
         aria-hidden="true">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" />
      <path d="M9 13h6M9 17h4" />
    </svg>
  );
}

/** Paginación de una tabla: «Mostrando 1–25 de 89» y los números de página. */
export function Paginacion({ pagina, paginas, total, porPagina, alCambiar, unidad = "registros" }: {
  pagina: number; paginas: number; total: number; porPagina: number; alCambiar: (p: number) => void; unidad?: string;
}) {
  if (total === 0) return null;
  const desde = (pagina - 1) * porPagina + 1;
  const hasta = Math.min(total, pagina * porPagina);
  const numeros: (number | "…")[] = [];
  for (let p = 1; p <= paginas; p++) {
    if (p === 1 || p === paginas || Math.abs(p - pagina) <= 1) numeros.push(p);
    else if (numeros[numeros.length - 1] !== "…") numeros.push("…");
  }
  return (
    <div className="paginacion">
      <span>Mostrando {desde.toLocaleString("es-CO")}–{hasta.toLocaleString("es-CO")} de {total.toLocaleString("es-CO")} {unidad}</span>
      {paginas > 1 && (
        <nav aria-label="Páginas">
          <button type="button" disabled={pagina <= 1} onClick={() => alCambiar(pagina - 1)} aria-label="Página anterior">‹</button>
          {numeros.map((n, i) => n === "…" ? <span className="salto" key={`s${i}`}>…</span> : (
            <button type="button" key={n} aria-current={n === pagina ? "page" : undefined} onClick={() => alCambiar(n)}
                    aria-label={`Página ${n}`}>{n}</button>
          ))}
          <button type="button" disabled={pagina >= paginas} onClick={() => alCambiar(pagina + 1)} aria-label="Página siguiente">›</button>
        </nav>
      )}
    </div>
  );
}
