import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { guiaPara } from "@/lib/ayuda";
import { puede } from "@/lib/api";
import { useSesion } from "@/lib/sesion";

// Asistente RICORA: un panel flotante que acompaña la descripción, la clasificación y la validación.
// No es un modelo de lenguaje: lleva a la pantalla o acción que la persona busca (con el mismo buscador
// de Ctrl K), muestra la guía de la pantalla en la que está y reúne las acciones rápidas.
// Así no inventa respuestas: todo lo que ofrece existe en el sistema.

export const I_CHISPA = (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9z" />
    <path d="M19 14l.9 2.6 2.6.9-2.6.9L19 21l-.9-2.6-2.6-.9 2.6-.9z" opacity=".75" />
  </svg>
);

const trazo = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
export const ACCIONES_RAPIDAS = [
  { texto: "Nueva carga", ruta: "/ingesta?vista=cargar", modulo: "ingesta" as const,
    icono: <svg viewBox="0 0 24 24" {...trazo}><path d="M12 16V4M7 9l5-5 5 5M4 20h16" /></svg> },
  { texto: "Describir", ruta: "/descripcion", modulo: "descripcion" as const,
    icono: <svg viewBox="0 0 24 24" {...trazo}><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="M13 7l4 4" /></svg> },
  { texto: "Consultar", ruta: "/instrumentos?vista=catalogo", modulo: "catalogo" as const,
    icono: <svg viewBox="0 0 24 24" {...trazo}><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2" /></svg> },
  { texto: "Exportar RiC-O", ruta: "/instrumentos?vista=rico", modulo: "catalogo" as const,
    icono: <svg viewBox="0 0 24 24" {...trazo}><path d="M12 4v12M7 11l5 5 5-5M4 20h16" /></svg> },
  { texto: "Auditoría", ruta: "/auditoria", modulo: "auditoria" as const,
    icono: <svg viewBox="0 0 24 24" {...trazo}><path d="M5 20V12M10 20V6M15 20v-9M20 20V4" /></svg> },
];

export function abrirBuscador(q?: string) {
  window.dispatchEvent(new CustomEvent("ricora:lanzador", { detail: { q } }));
}

/** Contenido del asistente: se usa en el panel flotante y en la tarjeta de Inicio. */
export function PanelAsistente({ alCerrar, compacto }: { alCerrar?: () => void; compacto?: boolean }) {
  const { usuario } = useSesion();
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const guia = compacto ? null : guiaPara(pathname, params.get("vista"));
  const [texto, setTexto] = useState("");
  const [abierto, setAbierto] = useState<number | null>(null);
  const acciones = ACCIONES_RAPIDAS.filter((a) => puede(usuario, a.modulo));

  function enviar(e: FormEvent) {
    e.preventDefault();
    alCerrar?.();
    abrirBuscador(texto.trim() || undefined);
  }

  return (
    <div className="asistente">
      <div className="asistente-cab">
        <span className="asistente-icono">{I_CHISPA}</span>
        <div>
          <strong>Asistente RICORA</strong>
          <p>Le ayuda a describir, normalizar y validar conforme a RiC-O y la normativa del AGN.</p>
        </div>
        {alCerrar && <button type="button" className="asistente-cerrar" aria-label="Cerrar el asistente" onClick={alCerrar}>×</button>}
      </div>
      <form className="asistente-pregunta" onSubmit={enviar}>
        <input aria-label="¿Qué necesita hoy?" placeholder="¿Qué necesita hoy? (p. ej. «cargar TRD», «inventario»)" value={texto}
               onChange={(e) => setTexto(e.target.value)} />
        <button type="submit" aria-label="Buscar">
          <svg viewBox="0 0 24 24" {...trazo}><path d="M4 12h15M13 6l6 6-6 6" /></svg>
        </button>
      </form>
      {acciones.length > 0 && (
        <div className="asistente-acciones">
          {acciones.map((a) => (
            <Link key={a.texto} to={a.ruta} onClick={alCerrar}>{a.icono}<span>{a.texto}</span></Link>
          ))}
        </div>
      )}
      {guia && (
        <div className="asistente-guia">
          <span className="asistente-seccion">En esta pantalla · {guia.titulo}</span>
          <ol>
            {guia.pasos.map((p, i) => (
              <li key={p.titulo}>
                <button type="button" aria-expanded={abierto === i} onClick={() => setAbierto(abierto === i ? null : i)}>
                  <b>{i + 1}</b>{p.titulo}</button>
                {abierto === i && <p>{p.texto}</p>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

/** Botón de la barra superior que abre el asistente como panel flotante. */
export function BotonAsistente() {
  const [abierto, setAbierto] = useState(false);
  const caja = useRef<HTMLDivElement>(null);
  const { pathname } = useLocation();
  useEffect(() => setAbierto(false), [pathname]);
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
  return (
    <div className="asistente-ancla" ref={caja}>
      <button type="button" className="boton-asistente" aria-expanded={abierto} aria-label="Asistente RICORA" title="Asistente RICORA"
              onClick={() => setAbierto(!abierto)}>{I_CHISPA}</button>
      {abierto && <div className="asistente-flotante" role="dialog" aria-label="Asistente RICORA"><PanelAsistente alCerrar={() => setAbierto(false)} /></div>}
    </div>
  );
}
