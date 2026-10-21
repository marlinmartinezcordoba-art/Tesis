import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

// Ventana flotante centrada para los formularios (decisión de la autora): la
// página de atrás no se mueve y queda oscurecida. Se cierra con la X, con Esc
// o con un clic afuera; el foco queda dentro mientras está abierta y vuelve
// adonde estaba al cerrarla.
export function Ventana({ titulo, alCerrar, children, ancha = false }: {
  titulo: string; alCerrar: () => void; children: ReactNode; ancha?: boolean;
}) {
  const caja = useRef<HTMLDivElement>(null);
  const idTitulo = useId();
  // La función de cerrar cambia en cada render del padre: se guarda aparte para que
  // el foco no salte al primer campo cada vez que se escribe.
  const cerrar = useRef(alCerrar);
  cerrar.current = alCerrar;

  useEffect(() => {
    const antes = document.activeElement as HTMLElement | null;
    const primero = caja.current?.querySelector<HTMLElement>("input, select, textarea, button:not(.ventana-cerrar)");
    (primero || caja.current)?.focus();
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") cerrar.current();
      if (e.key !== "Tab" || !caja.current) return;
      const enfocables = [...caja.current.querySelectorAll<HTMLElement>(
        "a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select, textarea, [tabindex]:not([tabindex='-1'])")];
      if (!enfocables.length) return;
      const [a, z] = [enfocables[0], enfocables[enfocables.length - 1]];
      if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); }
      else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
    };
    document.addEventListener("keydown", tecla);
    const desplazamiento = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", tecla);
      document.body.style.overflow = desplazamiento;
      antes?.focus?.();
    };
  }, []);

  return createPortal(
    <div className="ventana-fondo" onMouseDown={(e) => e.target === e.currentTarget && alCerrar()}>
      <div ref={caja} className={`ventana${ancha ? " ancha" : ""}`} role="dialog" aria-modal="true"
           aria-labelledby={idTitulo} tabIndex={-1}>
        <div className="ventana-cab">
          <h2 id={idTitulo}>{titulo}</h2>
          <button type="button" className="ventana-cerrar" aria-label="Cerrar" onClick={alCerrar}>×</button>
        </div>
        <div className="ventana-cuerpo">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
