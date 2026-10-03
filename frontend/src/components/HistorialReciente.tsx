import { useState } from "react";
import { ErrorAPI, descargar } from "@/lib/api";

// Patrón «historial reciente con exportación completa»: la vista muestra
// solo los registros más recientes, nunca pagina, y ofrece llevarse en Excel
// la totalidad de lo que cumple los filtros activos (no solo lo visible).
export function ExportarExcel({ ruta, deshabilitado = false }: { ruta: string; deshabilitado?: boolean }) {
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  return (
    <>
      <button type="button" className="boton chico" disabled={deshabilitado || ocupado}
              aria-label="Exportar a Excel todo el historial que cumple los filtros activos"
              onClick={() => {
                setOcupado(true);
                setError("");
                descargar(ruta).catch((e) => setError(e instanceof ErrorAPI ? e.message : "No se pudo exportar."))
                  .finally(() => setOcupado(false));
              }}>
        <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8"
             strokeLinecap="round" strokeLinejoin="round"><path d="M12 4v10m0 0l-3.5-3.5M12 14l3.5-3.5M5 16v2a2 2 0 002 2h10a2 2 0 002-2v-2" /></svg>
        {ocupado ? "Preparando…" : "Exportar todo a Excel"}
      </button>
      {error && <span className="meta" role="alert" style={{ color: "var(--danger)" }}>{error}</span>}
    </>
  );
}

export function AvisoReciente({ visibles, total, unidad }: { visibles: number; total: number | null; unidad: string }) {
  if (total === null || total <= visibles) return null;
  return (
    <div className="aviso-reciente" role="status">
      Se muestran los {visibles} {unidad} más recientes de {total.toLocaleString("es-CO")}. El resto está en la exportación a Excel.
    </div>
  );
}
