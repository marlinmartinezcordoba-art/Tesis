import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CLASES_NODO, LienzoGrafo, claseVisual, type DatosGrafo } from "@/components/Grafo";
import { ErrorAPI, pedir, puede } from "@/lib/api";
import { NIVEL_NOMBRE, SUBTIPO_NOMBRE } from "@/lib/descripcion";
import { useSesion } from "@/lib/sesion";

const TIPO_NODO: Record<string, string> = {
  recurso_documental: "Documento", entidad_vocabulario: "Entidad del vocabulario", fecha: "Fecha",
  actividad: "Actividad", instanciacion: "Archivo (instanciación)",
};
const CLASE_NOMBRE: Record<string, string> = {
  agente: "Agente", lugar: "Lugar", forma_documental: "Forma documental",
};

// Pestaña «Grafo» de Instrumentos: el grafo RiC del fondo dibujado, en solo
// lectura. Se navega cambiando de nodo central; nada se edita aquí.
export function PestanaGrafo({ fondo, centro, centrar, abrirFicha }: {
  fondo: { id: string; titulo: string };
  centro: string | null;
  centrar: (clave: string) => void;
  abrirFicha: (id: string) => void;
}) {
  const { usuario } = useSesion();
  const [profundidad, setProfundidad] = useState(centro ? 1 : 3);
  const [datos, setDatos] = useState<DatosGrafo | null>(null);
  const [seleccion, setSeleccion] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    const p = new URLSearchParams({ fondo_id: fondo.id, profundidad: String(profundidad) });
    if (centro) p.set("centro", centro);
    pedir<DatosGrafo>(`/api/instrumentos/grafo?${p}`)
      .then((d) => {
        setDatos(d);
        setSeleccion(d.centro);
      })
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar el grafo."));
  }, [fondo.id, centro, profundidad]);

  const nodo = datos?.nodos.find((n) => n.clave === seleccion) || null;
  const relaciones = nodo ? datos!.aristas.filter((a) => a.desde === nodo.clave || a.hacia === nodo.clave) : [];
  const nombreDe = (clave: string) => datos?.nodos.find((n) => n.clave === clave)?.etiqueta || "";
  const centroNodo = datos?.nodos.find((n) => n.clave === datos.centro);

  return (
    <>
      <div className="cabecera-nivel">
        <div>
          <h1>Grafo del fondo</h1>
          <p className="sub" style={{ marginBottom: 0 }}>
            Las entidades y relaciones Records in Contexts que guardó la descripción, dibujadas. Arrastre los nodos o el fondo,
            use la rueda o los botones para el zoom, y haga clic en un nodo para ver sus relaciones.
          </p>
        </div>
        <div className="opciones" role="radiogroup" aria-label="Alcance">
          {[1, 2, 3].map((n) => (
            <label key={n} className={profundidad === n ? "elegida" : ""}>
              <input type="radio" name="profundidad" checked={profundidad === n} onChange={() => setProfundidad(n)} />
              {n === 1 ? "Relaciones directas" : `${n} saltos`}
            </label>
          ))}
        </div>
      </div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {datos?.truncado && (
        <div className="aviso alerta">El grafo es grande: se muestran los primeros {datos.nodos.length} nodos. Elija un nodo y
          «Centrar aquí» para explorar desde él.</div>
      )}
      {!datos ? <div className="cargando">Cargando…</div> : (
        <div className="grafo-y-panel">
          <div>
            <div className="migas" style={{ marginBottom: 8 }}>
              Centro: <strong>{centroNodo?.etiqueta}</strong>
              {centro && <> · <button type="button" className="enlace" onClick={() => centrar("")}>volver al fondo</button></>}
            </div>
            <LienzoGrafo datos={datos} seleccion={seleccion} alSeleccionar={setSeleccion} />
            <div className="leyenda-grafo" aria-label="Leyenda">
              {CLASES_NODO.map((c) => (
                <span key={c.clase}><i className={`muestra n-${c.clase}`} />{c.nombre} <em>({c.ric})</em></span>
              ))}
            </div>
          </div>
          <aside className="tarjeta panel-nodo" aria-live="polite">
            {!nodo ? <div className="vacio">Haga clic en un nodo.</div> : (
              <div className="tarjeta-cuerpo">
                <span className={`insignia muestra-insignia n-${claseVisual(nodo)}`}>
                  {nodo.tipo === "recurso_documental" ? NIVEL_NOMBRE[nodo.clase] : CLASE_NOMBRE[nodo.clase] || TIPO_NODO[nodo.tipo]}
                </span>
                <h2 className="titulo-nodo">{nodo.etiqueta}</h2>
                <p className="meta">
                  {nodo.subtitulo && nodo.tipo !== "recurso_documental" ? `${SUBTIPO_NOMBRE[nodo.subtitulo] || nodo.subtitulo} · ` : ""}
                  {nodo.documentos !== undefined && `${nodo.documentos} documento(s) del fondo · `}
                  {relaciones.length} relación(es) visibles
                </p>
                <div className="acciones">
                  {nodo.clave !== datos.centro && (
                    <button type="button" className="boton chico primario" onClick={() => centrar(nodo.clave)}>Centrar aquí</button>
                  )}
                  {nodo.tipo === "recurso_documental" && nodo.clase !== "fondo" && (
                    <button type="button" className="boton chico" onClick={() => abrirFicha(nodo.id)}>Abrir ficha</button>
                  )}
                  {nodo.tipo === "entidad_vocabulario" && puede(usuario, "vocabularios") && (
                    <Link className="boton chico" to={`/vocabularios/${nodo.id}`}>Ver en vocabulario</Link>
                  )}
                  {nodo.tipo === "instanciacion" && puede(usuario, "preservacion") && (
                    <Link className="boton chico" to={`/preservacion/instanciacion/${nodo.id}`}>Ver en preservación</Link>
                  )}
                </div>
                <ul className="lista-relaciones">
                  {relaciones.map((a) => (
                    <li key={`${a.desde}-${a.hacia}-${a.codigo_ric}`}>
                      {a.desde === nodo.clave ? (
                        <>{a.etiqueta} → <button type="button" className="enlace" onClick={() => setSeleccion(a.hacia)}>{nombreDe(a.hacia)}</button></>
                      ) : (
                        <><button type="button" className="enlace" onClick={() => setSeleccion(a.desde)}>{nombreDe(a.desde)}</button> → {a.etiqueta}</>
                      )}
                      {a.uri_rico && <span className="meta"> · {a.uri_rico}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </aside>
        </div>
      )}
    </>
  );
}
