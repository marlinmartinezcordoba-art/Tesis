import { useEffect, useState } from "react";
import { ErrorAPI, pedir, pedirArchivo } from "@/lib/api";

interface InfoVisor {
  id: string; nombre: string; formato: string | null; puid: string | null;
  admite: boolean; total: number; texto: string | null; origen_texto: string | null;
}

/** Zona de un fragmento citado (RF-OCR-001): página y cajas en fracciones de la página. */
export interface Zona {
  pagina: number;
  cajas: { x: number; y: number; ancho: number; alto: number }[];
}

// Visor de documentos sin descarga: muestra las páginas como imagen
// (PDF e imágenes) generadas por el servidor, nunca el archivo original, y
// respeta el nivel de acceso del documento. `base` es la ruta del módulo:
// /api/ingesta/<id>/previsualizar o /api/descripcion/<id>/previsualizar.
// Con `resaltado`, va a la página del fragmento y marca su zona.
export function VisorDocumento({ base, alto = 520, resaltado = null }: { base: string; alto?: number; resaltado?: Zona | null }) {
  const [info, setInfo] = useState<InfoVisor | null>(null);
  const [error, setError] = useState("");
  const [pagina, setPagina] = useState(1);
  const [url, setUrl] = useState<string | null>(null);
  const [verTexto, setVerTexto] = useState(false);

  useEffect(() => {
    if (!resaltado) return;
    setPagina(resaltado.pagina);
    setVerTexto(false);
  }, [resaltado]);

  useEffect(() => {
    setInfo(null);
    setError("");
    setPagina(1);
    pedir<InfoVisor>(base).then((i) => { setInfo(i); setVerTexto(!i.admite); })
      .catch((e) => setError(e instanceof ErrorAPI ? e.message : "No se pudo abrir el documento."));
  }, [base]);

  useEffect(() => {
    if (!info?.admite || verTexto) return;
    let vivo = true;
    let actual: string | null = null;
    setUrl(null);
    pedirArchivo(`${base}/${pagina}`).then((b) => {
      if (!vivo) return;
      actual = URL.createObjectURL(b);
      setUrl(actual);
    }).catch((e) => vivo && setError(e instanceof ErrorAPI ? e.message : "No se pudo mostrar la página."));
    return () => { vivo = false; if (actual) URL.revokeObjectURL(actual); };
  }, [info, pagina, base, verTexto]);

  if (error) return <div className="aviso error" role="alert">{error}</div>;
  if (!info) return <div className="cargando" style={{ padding: 30 }}>Abriendo…</div>;
  return (
    <div className="visor">
      <div className="visor-barra">
        <span className="meta visor-nombre" title={info.nombre}>{info.nombre}{info.formato && ` · ${info.formato}`}</span>
        {info.admite && !verTexto && (
          <span className="visor-paginas">
            <button type="button" className="boton chico" disabled={pagina <= 1} aria-label="Página anterior"
                    onClick={() => setPagina(pagina - 1)}>‹</button>
            <span>{pagina} de {info.total}</span>
            <button type="button" className="boton chico" disabled={pagina >= info.total} aria-label="Página siguiente"
                    onClick={() => setPagina(pagina + 1)}>›</button>
          </span>
        )}
        {info.admite && info.texto && (
          <button type="button" className="enlace" onClick={() => setVerTexto(!verTexto)}>
            {verTexto ? "Ver la imagen" : "Ver el texto extraído"}
          </button>
        )}
      </div>
      <div className="visor-lienzo" style={{ height: alto }}>
        {verTexto ? (
          info.texto ? <pre className="visor-texto">{info.texto}</pre>
            : <p className="pista">Este formato no se puede mostrar como imagen y no tiene texto extraído.</p>
        ) : url ? (
          <div className="visor-hoja">
            <img src={url} alt={`Página ${pagina} de ${info.nombre}`} draggable={false} />
            {resaltado && resaltado.pagina === pagina && resaltado.cajas.map((c, i) => (
              <span key={i} className="visor-zona" aria-hidden="true" style={{
                left: `${c.x * 100}%`, top: `${c.y * 100}%`, width: `${c.ancho * 100}%`, height: `${c.alto * 100}%` }} />
            ))}
          </div>
        ) : <div className="cargando">Cargando la página…</div>}
      </div>
      {resaltado && resaltado.pagina === pagina && !verTexto && (
        <p className="pista visor-nota">Resaltado: de dónde salió la entidad elegida (página {resaltado.pagina}).</p>
      )}
      <p className="pista visor-nota">Vista de consulta: el visor no entrega el archivo original.</p>
    </div>
  );
}

export function VentanaVisor({ base, titulo, cerrar }: { base: string; titulo: string; cerrar: () => void }) {
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => e.key === "Escape" && cerrar();
    document.addEventListener("keydown", tecla);
    return () => document.removeEventListener("keydown", tecla);
  }, [cerrar]);
  return (
    <div className="velo" onMouseDown={(e) => e.target === e.currentTarget && cerrar()}>
      <aside className="panel-ficha panel-visor" role="dialog" aria-modal="true" aria-label={`Previsualizar ${titulo}`}>
        <div className="panel-cab">
          <strong>Previsualizar</strong>
          <button type="button" className="enlace" onClick={cerrar}>Cerrar</button>
        </div>
        <div className="panel-cuerpo"><VisorDocumento base={base} alto={Math.max(360, window.innerHeight - 190)} /></div>
      </aside>
    </div>
  );
}

export function BotonPrevisualizar({ base, nombre, etiqueta = "Previsualizar" }: { base: string; nombre: string; etiqueta?: string }) {
  const [abierto, setAbierto] = useState(false);
  return (
    <>
      <button type="button" className="boton chico" onClick={() => setAbierto(true)} aria-label={`Previsualizar ${nombre}`}>
        <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8"
             strokeLinecap="round" strokeLinejoin="round"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" /><circle cx="12" cy="12" r="2.8" /></svg>
        {etiqueta}
      </button>
      {abierto && <VentanaVisor base={base} titulo={nombre} cerrar={() => setAbierto(false)} />}
    </>
  );
}
