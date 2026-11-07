import { useEffect, useState } from "react";
import { ErrorAPI, pedir, subir } from "@/lib/api";

// Avance de la carga de una TRD, un CCD o una TVD que puede venir en varios archivos:
// cuántos se eligieron, la barra de subida, el tiempo de lectura en el servidor y,
// al terminar, el resultado de cada archivo (leído, sin tabla o sin texto) con su motivo.

export interface ArchivoLeido {
  archivo: string; estado: "leido" | "leido_ia" | "sin_leer" | "sin_tabla"; filas: number; con_problemas: number; motivo: string | null;
}
interface Progreso { hechos: number; total: number; actual: string | null }
interface Estado {
  nombres: string[]; bytes: number; fase: "subiendo" | "leyendo" | "listo" | "error"; avance: number; inicio: number;
  archivos?: ArchivoLeido[]; error?: string; progreso?: Progreso;
}

// Avance que informa el servidor mientras lee en segundo plano.
interface Lectura extends Progreso {
  id: string; estado: "leyendo" | "listo" | "error"; faltan: number; archivos: ArchivoLeido[]; error: string | null;
  codigo: number | null; resultado: unknown;
}

type Carga = ReturnType<typeof useCarga>;

/** Sube el archivo (uno, o varios en un .zip) y lo lee en segundo plano, informando cada pocos
 * segundos cuántos archivos van y cuántos faltan. Devuelve la vista previa al terminar. */
export async function leerConAvance<T>(archivo: File, carga: Carga): Promise<T> {
  const datos = new FormData();
  datos.append("archivo", archivo, archivo.name);
  let l = await subir<Lectura>("/api/cuadro/lecturas", datos, carga.avanzar);
  let fallos = 0;
  for (;;) {
    if (l.estado === "listo") return l.resultado as T;
    if (l.estado === "error") throw new ErrorAPI(l.codigo || 422, l.error || "No se pudo leer el archivo.");
    carga.progresar(l);
    await new Promise((r) => window.setTimeout(r, 2000));
    try {
      l = await pedir<Lectura>(`/api/cuadro/lecturas/${l.id}`);
      fallos = 0;
    } catch (err) {
      // Un corte pasajero (el servidor ocupado) no detiene la lectura: se vuelve a preguntar.
      if (err instanceof ErrorAPI && err.status === 404) throw err;
      if (++fallos > 15) throw err;
    }
  }
}

export function useCarga() {
  const [estado, setEstado] = useState<Estado | null>(null);
  return {
    estado,
    empezar: (lista: File[]) => setEstado({ nombres: lista.map((f) => f.name), bytes: lista.reduce((n, f) => n + f.size, 0),
      fase: "subiendo", avance: 0, inicio: Date.now() }),
    avanzar: (f: number) => setEstado((e) => e && e.fase === "subiendo"
      ? { ...e, avance: f, fase: f >= 0.999 ? "leyendo" : "subiendo" } : e),
    terminar: (archivos?: ArchivoLeido[]) => setEstado((e) => e && { ...e, fase: "listo", avance: 1, archivos }),
    progresar: (p: { hechos: number; total: number; actual: string | null; archivos?: ArchivoLeido[] }) =>
      setEstado((e) => e && { ...e, fase: "leyendo", avance: 1, progreso: { hechos: p.hechos, total: p.total, actual: p.actual },
        archivos: p.archivos }),
    fallar: (error: string) => setEstado((e) => e && { ...e, fase: "error", error }),
    reiniciar: () => setEstado(null),
  };
}

const reloj = (s: number) => (s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`);

const MB = (b: number) => `${(b / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;

export function PanelCarga({ estado }: { estado: Estado | null }) {
  const [ahora, setAhora] = useState(Date.now());
  const activo = estado?.fase === "subiendo" || estado?.fase === "leyendo";
  useEffect(() => {
    if (!activo) return;
    const t = window.setInterval(() => setAhora(Date.now()), 500);
    return () => window.clearInterval(t);
  }, [activo]);
  if (!estado) return null;
  const n = estado.nombres.length;
  const segundos = Math.max(0, Math.round((ahora - estado.inicio) / 1000));
  const leidos = (estado.archivos || []).filter((a) => a.estado === "leido" || a.estado === "leido_ia");
  const fallidos = (estado.archivos || []).filter((a) => a.estado !== "leido" && a.estado !== "leido_ia");
  const conIa = (estado.archivos || []).filter((a) => a.estado === "leido_ia").length;
  const p = estado.fase === "leyendo" && estado.progreso && estado.progreso.total > 1 ? estado.progreso : null;
  // Tiempo que falta, por el ritmo de los archivos ya leídos (solo desde el segundo archivo).
  const estimado = p && p.hechos >= 2 ? Math.round((segundos / p.hechos) * (p.total - p.hechos)) : null;
  const avanceBarra = p ? p.hechos / p.total : estado.avance;
  const indeterminada = estado.fase === "leyendo" && !p;
  return (
    <div className="panel-carga" aria-live="polite">
      <div className="panel-carga-cab">
        <strong>{n} archivo{n === 1 ? "" : "s"} · {MB(estado.bytes)}</strong>
        {estado.fase === "subiendo" && <span>Subiendo… {Math.round(estado.avance * 100)} %</span>}
        {estado.fase === "leyendo" && !p && <span>Leyendo {n === 1 ? "el archivo" : `los ${n} archivos`} en el servidor… {reloj(segundos)}</span>}
        {estado.fase === "leyendo" && p && (
          <span><b>{p.hechos} de {p.total}</b> leídos · faltan {p.total - p.hechos}
            {fallidos.length > 0 && <> · <b className="texto-error">{fallidos.length} con error</b></>}
            {estimado !== null && <> · quedan unos {reloj(estimado)}</>} · {reloj(segundos)}</span>
        )}
        {estado.fase === "listo" && (
          <span>{leidos.length} de {estado.archivos?.length ?? n} leído{leidos.length === 1 ? "" : "s"}
            {conIa > 0 && <> · {conIa} con IA</>}
            {fallidos.length > 0 && <> · <b className="texto-error">{fallidos.length} con error</b></>}</span>
        )}
        {estado.fase === "error" && <span className="texto-error">No se pudo leer</span>}
      </div>
      <div className={`barra-carga${indeterminada ? " indeterminada" : ""}${estado.fase === "error" ? " con-error" : ""}`}
           role="progressbar" aria-label="Avance de la carga" aria-valuemin={0} aria-valuemax={100}
           aria-valuenow={indeterminada ? undefined : Math.round(avanceBarra * 100)}>
        <i style={{ width: indeterminada ? undefined : `${Math.round(avanceBarra * 100)}%` }} />
      </div>
      {p?.actual && <p className="meta" style={{ margin: "6px 0 0" }}>Leyendo ahora: <b>{p.actual}</b></p>}
      {estado.fase === "leyendo" && (n > 1 || p) && (
        <p className="meta" style={{ margin: "6px 0 0" }}>Un PDF de muchas páginas puede tardar, y más si el formato es antiguo y
          lo lee la IA; no cierre esta pantalla.</p>
      )}
      {estado.fase === "error" && estado.error && <p className="texto-error" style={{ margin: "6px 0 0" }}>{estado.error}</p>}
      {(estado.fase === "listo" || p) && estado.archivos && estado.archivos.length > 0 && (
        <div className="tabla-desplazable" style={{ marginTop: 8 }}>
          <table className="tabla-datos tabla-carga">
            <thead><tr><th>Archivo</th><th>Resultado</th><th className="num">Filas</th><th className="num">Con problemas</th></tr></thead>
            <tbody>
              {estado.archivos.map((a) => (
                <tr key={a.archivo}>
                  <td>{a.archivo}{a.motivo && <span className="secundario">{a.motivo}</span>}</td>
                  <td>{a.estado === "leido" ? <span className="insignia bien">✓ Leído</span>
                    : a.estado === "leido_ia" ? <span className="insignia agente" title="El formato no era reconocible: lo leyó el motor de análisis. Revise cada fila.">✓ Leído con IA · revise</span>
                    : a.estado === "sin_tabla" ? <span className="insignia alerta">Sin tabla reconocible</span>
                    : <span className="insignia error">No se pudo leer</span>}</td>
                  <td className="num">{a.filas}</td>
                  <td className="num">{a.con_problemas}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
