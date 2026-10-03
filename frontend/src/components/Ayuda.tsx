import { useEffect, useRef, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { guiaPara } from "@/lib/ayuda";

// Ambulancia de ayuda: el mismo ícono de la plataforma anterior. Abre una
// tarjeta con los pasos de la pantalla en la que está la persona.
function Ambulancia() {
  return (
    <svg viewBox="0 0 32 24" aria-hidden="true">
      <rect x="9" y="1" width="4" height="2.4" rx="1" fill="#e74c3c" />
      <path d="M2.5 6.5a3 3 0 0 1 3-3H20v14H2.5z" fill="#fff" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M20 8h5.4l4.1 5v4.5H20z" fill="#fff" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M21.8 9.6h3l2.5 3h-5.5z" fill="#9ec9e6" />
      <path d="M9.6 6.8h2.8v2.9h2.9v2.8h-2.9v2.9H9.6v-2.9H6.7V9.7h2.9z" fill="#e74c3c" />
      <path d="M2.5 14.5H29.5" stroke="#e74c3c" strokeWidth="1.4" />
      <circle cx="8" cy="19" r="2.8" fill="#fff" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="24" cy="19" r="2.8" fill="#fff" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function Ayuda() {
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const guia = guiaPara(pathname, params.get("vista"));
  const [abierta, setAbierta] = useState(false);
  const [paso, setPaso] = useState(0);
  const boton = useRef<HTMLButtonElement>(null);
  const clave = `${pathname}?${params.get("vista") ?? ""}`;

  // Al cambiar de pantalla, la guía vuelve al primer paso.
  useEffect(() => setPaso(0), [clave]);

  useEffect(() => {
    if (!abierta) return;
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setAbierta(false);
        boton.current?.focus();
      }
    };
    document.addEventListener("keydown", tecla);
    return () => document.removeEventListener("keydown", tecla);
  }, [abierta]);

  if (!guia) return null;
  const total = guia.pasos.length;
  const actual = guia.pasos[Math.min(paso, total - 1)];
  const ultimo = paso >= total - 1;

  return (
    <>
      {abierta && (
        <div className="ayuda-tarjeta" role="dialog" aria-label={`Ayuda: ${guia.titulo}`}>
          <button type="button" className="ayuda-cerrar" aria-label="Cerrar la ayuda" onClick={() => setAbierta(false)}>×</button>
          <div className="ayuda-modulo">{guia.titulo}</div>
          <h3>{actual.titulo}</h3>
          <p>{actual.texto}</p>
          <div className="ayuda-pie">
            <span>Paso {paso + 1} de {total}</span>
            <div>
              <button type="button" className="boton chico" aria-label="Paso anterior" disabled={paso === 0} onClick={() => setPaso(paso - 1)}>←</button>
              <button
                type="button"
                className="boton chico primario"
                onClick={() => (ultimo ? (setAbierta(false), setPaso(0)) : setPaso(paso + 1))}
              >
                {ultimo ? "Entendido" : "Siguiente →"}
              </button>
            </div>
          </div>
        </div>
      )}
      <button
        ref={boton}
        type="button"
        className="ambulancia"
        aria-haspopup="dialog"
        aria-expanded={abierta}
        aria-label="Ayuda: qué hacer en esta pantalla"
        title="Ayuda: qué hacer en esta pantalla"
        onClick={() => setAbierta(!abierta)}
      >
        <Ambulancia />
      </button>
    </>
  );
}
