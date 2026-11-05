import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { guiaPara } from "@/lib/ayuda";
import { ErrorAPI, pedir, puede } from "@/lib/api";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";

// Asistente RICORA con IA: un panel lateral de conversación. Responde preguntas de archivística
// y de uso del sistema con el motor de análisis (Gemini). No lee documentos ni cambia nada.
// Sin motor configurado queda en modo guiado: búsqueda, acciones rápidas y la guía de la pantalla.

export const I_CHISPA = (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9z" />
    <path d="M19 14l.9 2.6 2.6.9-2.6.9L19 21l-.9-2.6-2.6-.9 2.6-.9z" opacity=".75" />
  </svg>
);
const trazo = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
const I_ENVIAR = <svg viewBox="0 0 24 24" {...trazo}><path d="M4 12h15M13 6l6 6-6 6" /></svg>;


// Preguntas que suelen surgir en cada pantalla.
const GENERALES = [
  "¿Qué diferencia hay entre la TRD y la TVD?",
  "¿Cómo describo un agente productor en RiC-O?",
  "¿Qué campos lleva el FUID?",
  "¿Qué documentos tienen reserva por la Ley 1712?",
];
const PREGUNTAS: [string, string[]][] = [
  ["/fondos", ["¿Qué diferencia hay entre el CCD y la TRD?", "¿Cuándo se elabora una TVD y no una TRD?",
    "¿Qué significa conservación total, selección y eliminación?", "¿Quién aprueba la TRD y qué acto la adopta?"]],
  ["/ingesta", ["¿Qué formatos se recomiendan para preservar un documento digital?", "¿Para qué sirve la huella SHA-256?",
    "¿Qué hago si el OCR sale con confianza baja?", "¿Cómo asigno los documentos a un expediente?"]],
  ["/descripcion", ["¿Qué va en «Alcance y contenido» según ISAD(G)?", "¿Cómo escribo el título de una unidad documental?",
    "¿Cómo registro una fecha aproximada o incierta?", "¿Qué diferencia hay entre productor y destinatario en RiC-O?"]],
  ["/vocabularios", ["¿Cómo se escribe la forma autorizada de un nombre?", "¿Cuándo dos autoridades son la misma y se fusionan?",
    "¿Qué diferencia hay entre función, actividad y mandato?", "¿Qué es una ficha ISAAR(CPF)?"]],
  ["/instrumentos", ["¿Qué diferencia hay entre inventario, guía e índice?", "¿Qué campos lleva el FUID?",
    "¿Qué es RiC-O y para qué sirve publicarlo?", "¿Cómo consulto el grafo con SPARQL?"]],
  ["/auditoria", ["¿Qué debe quedar registrado en la trazabilidad de un archivo?", "¿Por cuánto tiempo se conservan los registros de auditoría?",
    "¿Qué significa que la cadena de huellas está íntegra?", "¿Cómo exporto el registro de actividad?"]],
  ["/evaluacion", ["¿Por qué se describe primero a ciegas?", "¿Qué miden la precisión, la exhaustividad y F1?",
    "¿Qué es el acuerdo entre expertas?", "¿Cómo califico exactitud, completitud y pertinencia?"]],
  ["/usuarios", ["¿Qué permisos debe tener una archivista que describe?", "¿Qué hace el rol de revisor?",
    "¿Qué borra la puesta en marcha y qué conserva?", "¿Cómo protejo los datos personales de las cuentas?"]],
];
function preguntasPara(ruta: string): string[] {
  return PREGUNTAS.find(([prefijo]) => ruta.startsWith(prefijo))?.[1] ?? GENERALES;
}

interface Mensaje { rol: "persona" | "asistente"; texto: string; error?: boolean }
interface Estado { disponible: boolean; modelo: string | null; aviso: string }

/** Abre el panel del asistente, opcionalmente con una pregunta ya escrita. */
export function abrirAsistente(q?: string) {
  window.dispatchEvent(new CustomEvent("ricora:asistente", { detail: { q } }));
}

// Texto de la respuesta: párrafos y listas con «- ».
function Texto({ texto }: { texto: string }) {
  const bloques: { lista: boolean; lineas: string[] }[] = [];
  for (const linea of texto.split("\n").map((l) => l.trim()).filter(Boolean)) {
    const lista = /^[-•]\s+/.test(linea);
    const limpia = linea.replace(/^[-•]\s+/, "");
    const ultimo = bloques[bloques.length - 1];
    if (ultimo && ultimo.lista && lista) ultimo.lineas.push(limpia);
    else bloques.push({ lista, lineas: [limpia] });
  }
  return <>{bloques.map((b, i) => b.lista
    ? <ul key={i}>{b.lineas.map((l, j) => <li key={j}>{l}</li>)}</ul>
    : <p key={i}>{b.lineas[0]}</p>)}</>;
}

function Conversacion({ alCerrar, inicial }: { alCerrar: () => void; inicial?: string }) {
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const guia = guiaPara(pathname, params.get("vista"));
  const [estado, setEstado] = useState<Estado | null>(null);
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [texto, setTexto] = useState(inicial || "");
  const [pensando, setPensando] = useState(false);
  const fin = useRef<HTMLDivElement>(null);
  const entrada = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { pedir<Estado>("/api/asistente/estado").then(setEstado).catch(() => setEstado({ disponible: false, modelo: null, aviso: "" })); }, []);
  useEffect(() => { fin.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [mensajes, pensando]);
  useEffect(() => { entrada.current?.focus(); }, []);
  // Una pregunta escrita en el Inicio se envía sola en cuanto se sabe que hay IA.
  const enviada = useRef(false);
  useEffect(() => {
    if (inicial && estado?.disponible && !enviada.current) { enviada.current = true; preguntar(inicial); }
  }, [estado]); // eslint-disable-line react-hooks/exhaustive-deps

  async function preguntar(pregunta: string) {
    const limpia = pregunta.trim();
    if (!limpia || pensando) return;
    if (!estado?.disponible) {
      setMensajes([...mensajes, { rol: "persona", texto: limpia }, { rol: "asistente", error: true, texto:
        "El asistente con IA todavía no está disponible en este servidor. Mientras tanto, use Ctrl + K para ir a cualquier pantalla." }]);
      setTexto("");
      return;
    }
    const nuevos: Mensaje[] = [...mensajes, { rol: "persona", texto: limpia }];
    setMensajes(nuevos);
    setTexto("");
    setPensando(true);
    try {
      const r = await pedir<{ respuesta: string }>("/api/asistente/preguntar", { method: "POST", body: JSON.stringify({
        mensajes: nuevos.filter((m) => !m.error).map(({ rol, texto: t }) => ({ rol, texto: t })),
        pantalla: guia ? { titulo: guia.titulo, pasos: guia.pasos.map((p) => `${p.titulo} ${p.texto}`) } : null,
        fondo: fondo?.titulo ?? null }) });
      setMensajes([...nuevos, { rol: "asistente", texto: r.respuesta }]);
    } catch (err) {
      setMensajes([...nuevos, { rol: "asistente", error: true,
        texto: err instanceof ErrorAPI ? err.message : "No se pudo consultar al asistente. Intente de nuevo." }]);
    } finally {
      setPensando(false);
    }
  }
  function enviar(e: FormEvent) { e.preventDefault(); preguntar(texto); }

  const nombre = usuario?.nombre.split(" ")[0] || "";
  return (
    <div className="chat">
      <header className="chat-cab">
        <span className="chat-icono">{I_CHISPA}</span>
        <div>
          <strong>Asistente RICORA <span className="chat-ia">IA</span></strong>
          <span className="chat-estado">{estado === null ? "Conectando…" : estado.disponible
            ? <><i className="punto-vivo" />En línea · orienta en archivística y en RICORA</>
            : "Modo guiado: el servidor no tiene el motor de IA configurado"}</span>
        </div>
        <button type="button" className="chat-cerrar" aria-label="Cerrar el asistente" onClick={alCerrar}>×</button>
      </header>

      <div className="chat-cuerpo" aria-live="polite">
        {mensajes.length === 0 && (
          <div className="chat-bienvenida">
            <h3>Hola{nombre ? `, ${nombre}` : ""}. ¿En qué le ayudo?</h3>
            <p>Pregunte por normas archivísticas, RiC-O, la TRD o cómo hacer algo en RICORA. Oriento; las decisiones
              son suyas.</p>
            <span className="chat-seccion">Preguntas frecuentes</span>
            <div className="chat-sugerencias">
              {preguntasPara(pathname).map((q) => <button type="button" key={q} onClick={() => preguntar(q)}>{q}</button>)}
            </div>
          </div>
        )}
        {mensajes.map((m, i) => (
          <div key={i} className={`burbuja de-${m.rol}${m.error ? " error" : ""}`}>
            {m.rol === "asistente" && <span className="burbuja-icono">{I_CHISPA}</span>}
            <div className="burbuja-texto">{m.rol === "asistente" ? <Texto texto={m.texto} /> : m.texto}</div>
          </div>
        ))}
        {pensando && (
          <div className="burbuja de-asistente"><span className="burbuja-icono">{I_CHISPA}</span>
            <div className="burbuja-texto escribiendo" aria-label="El asistente está escribiendo"><i /><i /><i /></div></div>
        )}
        <div ref={fin} />
      </div>

      <form className="chat-pie" onSubmit={enviar}>
        <div className="chat-entrada">
          <textarea ref={entrada} rows={1} aria-label="Escriba su pregunta" value={texto}
                    placeholder="Escriba su pregunta…"
                    onChange={(e) => setTexto(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); preguntar(texto); } }} />
          <button type="submit" disabled={!texto.trim() || pensando} aria-label="Enviar">{I_ENVIAR}</button>
        </div>
        <p className="chat-aviso">{estado?.aviso || "Oriento con base en normas y en el uso del sistema."} Puede equivocarse: verifique lo importante.</p>
      </form>
    </div>
  );
}

/** Tarjeta del Inicio: escribe y abre el panel del asistente. */
export function PanelAsistente() {
  const [texto, setTexto] = useState("");
  return (
    <div className="asistente-inicio">
      <div className="asistente-cab">
        <span className="asistente-icono">{I_CHISPA}</span>
        <div>
          <strong>Asistente RICORA <span className="chat-ia">IA</span></strong>
          <p>Le ayuda a describir, normalizar y validar conforme a RiC-O y la normativa del AGN.</p>
        </div>
      </div>
      <form className="asistente-pregunta" onSubmit={(e) => { e.preventDefault(); abrirAsistente(texto.trim() || undefined); setTexto(""); }}>
        <input aria-label="¿Qué necesita hoy?" placeholder="¿Qué necesita hoy?" value={texto} onChange={(e) => setTexto(e.target.value)} />
        <button type="submit" aria-label="Preguntar">{I_ENVIAR}</button>
      </form>
    </div>
  );
}

/** Botón de la barra superior y panel lateral del asistente. */
export function BotonAsistente() {
  const [abierto, setAbierto] = useState(false);
  const [inicial, setInicial] = useState<string | undefined>();
  const [clave, setClave] = useState(0);
  useEffect(() => {
    const abrir = (e: Event) => {
      setInicial((e as CustomEvent<{ q?: string }>).detail?.q);
      setClave((k) => k + 1);
      setAbierto(true);
    };
    window.addEventListener("ricora:asistente", abrir);
    return () => window.removeEventListener("ricora:asistente", abrir);
  }, []);
  useEffect(() => {
    if (!abierto) return;
    const tecla = (e: KeyboardEvent) => { if (e.key === "Escape") setAbierto(false); };
    document.addEventListener("keydown", tecla);
    return () => document.removeEventListener("keydown", tecla);
  }, [abierto]);
  return (
    <>
      <button type="button" className="boton-asistente" aria-expanded={abierto} aria-label="Asistente RICORA" title="Asistente RICORA (IA)"
              onClick={() => { setInicial(undefined); setAbierto(!abierto); }}>{I_CHISPA}</button>
      {abierto && (
        <>
          <div className="chat-velo" onClick={() => setAbierto(false)} aria-hidden="true" />
          <aside className="chat-panel" role="dialog" aria-label="Asistente RICORA">
            <Conversacion key={clave} inicial={inicial} alCerrar={() => setAbierto(false)} />
          </aside>
        </>
      )}
    </>
  );
}
