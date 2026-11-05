import { useEffect, useRef, useState } from "react";

// Avisos flotantes: las confirmaciones y los errores salen abajo a la derecha sin mover la pantalla.
//
// Las pantallas siguen escribiendo sus mensajes como siempre (<div className="aviso bien|error">);
// este componente los detecta apenas aparecen dentro del contenido, los muestra flotando y oculta la
// copia en la página. Así el cambio vale para todas las pantallas a la vez sin tocar su lógica.
//
// - Confirmación (aviso bien, o aviso informativo con role="status"): se va sola a los 5 segundos.
// - Error (aviso error): se queda hasta que la persona lo cierra.
// - Tampoco los avisos con botones o enlaces dentro.
// - No se tocan las notas de guía (role="note", avisos «alerta» fijos) ni lo que está dentro de una
//   ventana, del asistente o de la ayuda: ahí el mensaje debe quedar junto al formulario.

type Tipo = "bien" | "error" | "info";
interface Aviso { id: number; tipo: Tipo; texto: string }

const SELECTOR = ".aviso.bien, .aviso.error, .aviso[role='status']:not(.alerta)";
const EXCLUIR = ".ventana, .ventana-fondo, .chat-panel, .ayuda-tarjeta, [role='dialog'], [data-fijo]";
const SEGUNDOS = 5;

let siguiente = 1;
const oyentes = new Set<(a: Aviso) => void>();
/** Muestra un aviso flotante desde cualquier parte del código. */
export function avisar(texto: string, tipo: Tipo = "bien") {
  const a = { id: siguiente++, tipo, texto };
  oyentes.forEach((f) => f(a));
}

function tipoDe(el: Element): Tipo {
  return el.classList.contains("error") ? "error" : el.classList.contains("bien") ? "bien" : "info";
}

export function AvisosFlotantes() {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const vistos = useRef(new WeakMap<Element, string>());

  useEffect(() => {
    const agregar = (a: Aviso) => {
      setAvisos((lista) => (lista.some((x) => x.texto === a.texto && x.tipo === a.tipo) ? lista : [...lista.slice(-3), a]));
      if (a.tipo !== "error") window.setTimeout(() => setAvisos((l) => l.filter((x) => x.id !== a.id)), SEGUNDOS * 1000);
    };
    oyentes.add(agregar);

    const revisar = (el: Element) => {
      // Un aviso con botones o enlaces (p. ej. «Descargar el respaldo») se queda en la página: es parte del trabajo.
      if (!el.matches(SELECTOR) || el.closest(EXCLUIR) || el.querySelector("button, a, input, select, textarea")) return;
      const texto = (el.textContent || "").replace(/\s+/g, " ").replace(/^×\s*/, "").trim();
      (el as HTMLElement).classList.add("aviso-en-flotante");
      if (!texto || vistos.current.get(el) === texto) return;
      vistos.current.set(el, texto);
      agregar({ id: siguiente++, tipo: tipoDe(el), texto });
    };
    const raiz = document.querySelector(".contenido") || document.body;
    raiz.querySelectorAll(SELECTOR).forEach(revisar);
    const observador = new MutationObserver((cambios) => {
      for (const c of cambios) {
        if (c.type === "childList") {
          c.addedNodes.forEach((n) => {
            if (!(n instanceof Element)) {
              const padre = n.parentElement?.closest(SELECTOR);
              if (padre) revisar(padre);
              return;
            }
            revisar(n);
            n.querySelectorAll(SELECTOR).forEach(revisar);
            const padre = n.parentElement?.closest(SELECTOR);
            if (padre) revisar(padre);
          });
        } else if (c.type === "characterData") {
          const padre = c.target.parentElement?.closest(SELECTOR);
          if (padre) revisar(padre);
        }
      }
    });
    observador.observe(raiz, { childList: true, subtree: true, characterData: true });
    return () => { observador.disconnect(); oyentes.delete(agregar); };
  }, []);

  const cerrar = (id: number) => setAvisos((l) => l.filter((x) => x.id !== id));
  return (
    <div className="avisos-flotantes" aria-live="polite">
      {avisos.map((a) => (
        <div key={a.id} className={`aviso-flotante ${a.tipo}`} role={a.tipo === "error" ? "alert" : "status"}>
          <span className="aviso-flotante-icono" aria-hidden="true">{a.tipo === "error" ? "!" : a.tipo === "bien" ? "✓" : "i"}</span>
          <p>{a.texto}</p>
          <button type="button" aria-label="Cerrar el aviso" onClick={() => cerrar(a.id)}>×</button>
          {a.tipo !== "error" && <i className="aviso-flotante-tiempo" style={{ animationDuration: `${SEGUNDOS}s` }} />}
        </div>
      ))}
    </div>
  );
}
