import { useCallback, useEffect, useState } from "react";
import { ErrorAPI, pedir, subir } from "@/lib/api";
import { confirmar } from "@/lib/dialogos";

// Biblioteca del Asistente RICORA (RAG): las leyes, acuerdos del AGN, manuales y procedimientos con
// los que responde el asistente en «Documentos de la entidad». La administración los carga; el texto
// se extrae en segundo plano (con OCR y la imagen limpia si vienen escaneados). Nada se borra: se anula.

interface Doc {
  id: string; titulo: string; clase: string; clase_nombre: string; archivo: string; huella: string;
  tamano_bytes: number; estado: "procesando" | "listo" | "error" | "anulado"; error: string | null;
  paginas: number | null; origen_texto: string | null; caracteres: number; cargado_en: string;
}
const CLASES: [string, string][] = [["ley", "Ley"], ["decreto", "Decreto"], ["acuerdo_agn", "Acuerdo del AGN"],
  ["manual", "Manual"], ["procedimiento", "Procedimiento"], ["otro", "Otro"]];
const ESTADO: Record<Doc["estado"], [string, string]> = { procesando: ["Leyendo el texto…", "proceso"],
  listo: ["Listo", "bien"], error: ["No se pudo leer", "error"], anulado: ["Anulado", "proceso"] };

export function BibliotecaAsistente() {
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [clase, setClase] = useState("ley");
  const [titulo, setTitulo] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  const [mensaje, setMensaje] = useState("");

  const cargar = useCallback(() => {
    pedir<Doc[]>("/api/asistente/biblioteca").then(setDocs).catch(() => setDocs([]));
  }, []);
  useEffect(cargar, [cargar]);
  // Mientras haya documentos leyéndose, la lista se actualiza sola.
  useEffect(() => {
    if (!docs?.some((d) => d.estado === "procesando")) return;
    const t = setInterval(cargar, 4000);
    return () => clearInterval(t);
  }, [docs, cargar]);

  async function subirArchivos(lista: File[]) {
    setError(""); setMensaje(""); setOcupado(true);
    let hechos = 0;
    try {
      for (const archivo of lista) {
        const datos = new FormData();
        datos.append("archivo", archivo, archivo.name);
        datos.append("clase", clase);
        if (lista.length === 1 && titulo.trim()) datos.append("titulo", titulo.trim());
        try {
          await subir("/api/asistente/biblioteca", datos, () => undefined);
          hechos += 1;
        } catch (err) {
          setError(`${archivo.name}: ${err instanceof ErrorAPI ? err.message : "no se pudo cargar."}`);
        }
      }
      if (hechos) setMensaje(`${hechos} documento(s) cargado(s). RICORA está leyendo su texto; en unos minutos el asistente ya responde con ellos.`);
      setTitulo("");
      cargar();
    } finally {
      setOcupado(false);
    }
  }

  async function anular(d: Doc) {
    if (!await confirmar(`¿Anular «${d.titulo}»? El asistente deja de consultarlo. No se borra: queda registrado.`)) return;
    try {
      await pedir(`/api/asistente/biblioteca/${d.id}/anular`, { method: "POST", body: JSON.stringify({ motivo: null }) });
      cargar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo anular.");
    }
  }

  return (
    <>
      <div className="tarjeta"><div className="tarjeta-cuerpo">
        <p style={{ marginTop: 0 }}>Cargue aquí las leyes, decretos, acuerdos del AGN, manuales y procedimientos de la
          entidad. En el asistente, con <strong>«Documentos de la entidad»</strong>, RICORA busca en ellos (y en lo publicado
          del fondo) los pasajes que tratan la pregunta y responde solo con esos pasajes, citándolos. Si no los encuentra,
          lo dice en vez de inventar.</p>
        <div className="filtros">
          <select className="selector" aria-label="Clase de documento" value={clase} onChange={(e) => setClase(e.target.value)}>
            {CLASES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
          </select>
          <input className="entrada" aria-label="Título (opcional)" placeholder="Título (opcional; si no, el nombre del archivo)"
                 value={titulo} onChange={(e) => setTitulo(e.target.value)} style={{ minWidth: 260 }} />
          <label className="boton primario">
            {ocupado ? "Cargando…" : "Elegir archivos"}
            <input type="file" multiple hidden disabled={ocupado}
                   accept=".pdf,.docx,.doc,.odt,.txt,.md,.html,.htm,.rtf,.png,.jpg,.jpeg,.tif,.tiff"
                   onChange={(e) => { const l = Array.from(e.target.files || []); e.target.value = ""; if (l.length) void subirArchivos(l); }} />
          </label>
        </div>
        <p className="meta">PDF con texto o escaneado, Word, texto o imagen. No cargue documentos con reserva legal: los
          pasajes que use el asistente salen hacia Gemini (sin datos personales).</p>
        {mensaje && <div className="aviso bien" role="status">{mensaje}</div>}
        {error && <div className="aviso error" role="alert" data-fijo>{error}</div>}
      </div></div>

      <div className="tarjeta">
        <div className="tarjeta-cab">En la biblioteca ({docs?.length ?? "…"})</div>
        {docs && !docs.length ? <p className="meta" style={{ padding: "0 16px 12px" }}>Todavía no hay documentos.</p> : (
          <div className="tabla-desplazable">
            <table className="tabla-datos">
              <thead><tr><th>Documento</th><th>Clase</th><th>Estado</th><th>Texto</th><th /></tr></thead>
              <tbody>
                {(docs || []).map((d) => (
                  <tr key={d.id}>
                    <td><strong>{d.titulo}</strong><div className="meta">{d.archivo} · huella <code title={d.huella}>
                      {d.huella.slice(0, 10)}…</code></div></td>
                    <td>{d.clase_nombre}</td>
                    <td><span className={`insignia ${ESTADO[d.estado][1]}`}>{ESTADO[d.estado][0]}</span>
                      {d.error && <div className="meta">{d.error}</div>}</td>
                    <td className="meta">{d.estado === "listo" ? `${d.caracteres.toLocaleString("es-CO")} caracteres`
                      + (d.paginas ? ` · ${d.paginas} pág.` : "") + (d.origen_texto === "ocr" ? " · con OCR" : "") : "—"}</td>
                    <td><button type="button" className="boton chico" onClick={() => anular(d)}>Anular</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
