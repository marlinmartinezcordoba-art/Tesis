// La explicación de una pantalla, plegada: el menú dice dónde se está (los títulos de módulo no se muestran),
// y quien no sabe para qué sirve la abre con un clic.
import type { ReactNode } from "react";

export function ParaQueSirve({ children }: { children: ReactNode }) {
  return (
    <details className="para-que-sirve">
      <summary>¿Para qué sirve esta pantalla?</summary>
      <div>{children}</div>
    </details>
  );
}
