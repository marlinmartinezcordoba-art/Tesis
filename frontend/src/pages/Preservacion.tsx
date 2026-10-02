import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, pedir } from "@/lib/api";
import { NIVEL_NOMBRE } from "@/lib/descripcion";
import { useFondo } from "@/lib/fondo";
import { dia, peso } from "@/lib/formato";
import { FRECUENCIAS, TIPO_ATENCION, type Configuracion, type Panel } from "@/lib/preservacion";
import { useSesion } from "@/lib/sesion";

function extension(nombre: string) {
  const p = nombre.split(".");
  return p.length > 1 ? p.pop()!.slice(0, 4) : "·";
}

export function contextoTexto(contexto: { nivel: string; titulo: string }[]): string {
  const util = contexto.filter((c) => c.nivel !== "fondo");
  return util.length ? util.map((c) => `${NIVEL_NOMBRE[c.nivel]}: ${c.titulo}`).join(" › ") : "Sin describir todavía";
}

// --- Panel -------------------------------------------------------------------------------------

export function PanelPreservacion() {
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const [panel, setPanel] = useState<Panel | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(async () => {
    if (!fondo) return;
    try {
      setPanel(await pedir<Panel>(`/api/preservacion/panel?fondo_id=${fondo.id}`));
      window.dispatchEvent(new Event("ricora:alertas"));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar el panel.");
    }
  }, [fondo]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  if (!fondo) return <div className="vacio">Primero debe existir un fondo (se registra en Ingesta).</div>;
  const frecuencia = FRECUENCIAS.find((f) => f.dias === panel?.frecuencia_dias)?.nombre.split(" (")[0].toLowerCase();

  return (
    <>
      <div className="cabecera-nivel">
        <div>
          <h1>Preservación digital</h1>
          <p className="sub" style={{ marginBottom: 0 }}>
            Estado técnico de los archivos de «{fondo.titulo}». La integridad se verifica sola
            {panel && ` (${frecuencia || `cada ${panel.frecuencia_dias} días`}; última: ${panel.ultima_verificacion ? dia(panel.ultima_verificacion) : "todavía no"})`}.
            Nada se migra sin su aprobación.
          </p>
        </div>
        {usuario?.es_administrador && <Link className="boton chico" to="/preservacion/configuracion">Configuración</Link>}
      </div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!panel ? <div className="cargando">Cargando…</div> : (
        <>
          <div className="resumen-preservacion">
            <div className="cifra bien"><strong>{panel.resumen.buen_estado}</strong><span>En buen estado</span></div>
            <div className="cifra error"><strong>{panel.resumen.alerta_integridad}</strong><span>Alerta de integridad</span></div>
            <div className="cifra error"><strong>{panel.resumen.alerta_segunda_copia}</strong><span>Alerta de segunda copia</span></div>
            <div className="cifra alerta"><strong>{panel.resumen.riesgo_obsolescencia}</strong><span>Riesgo de obsolescencia</span></div>
            <div className="cifra"><strong>{panel.resumen.total}</strong><span>Total de archivos</span></div>
          </div>
          {panel.sin_segunda_copia > 0 && (
            <div className="aviso proceso" role="status">
              {panel.sin_segunda_copia} archivo(s) todavía sin segunda copia en el lugar configurado: el sistema las crea solo,
              de a poco, en segundo plano.
            </div>
          )}
          <div className="tarjeta">
            <div className="tarjeta-cab">Requieren atención · {panel.atencion.length}</div>
            {panel.atencion.length === 0 && (
              <div className="vacio">
                {panel.resumen.total === 0 ? "Todavía no hay archivos ingresados en este fondo." : "Ningún archivo requiere atención."}
              </div>
            )}
            {panel.atencion.map((a) => (
              <Link key={a.alerta_id} to={`/preservacion/instanciacion/${a.instanciacion.id}`} className="fila fila-enlace">
                <span className="icono-archivo" aria-hidden="true">{extension(a.instanciacion.nombre)}</span>
                <div className="fila-principal">
                  <div className="nombre">{a.instanciacion.nombre}</div>
                  <div className="meta">
                    {contextoTexto(a.contexto)} · {a.instanciacion.formato || "formato sin identificar"}
                    {a.instanciacion.puid && ` (${a.instanciacion.puid})`}
                  </div>
                </div>
                <span className={`insignia ${TIPO_ATENCION[a.tipo].clase}`}>{TIPO_ATENCION[a.tipo].texto}</span>
              </Link>
            ))}
          </div>
        </>
      )}
    </>
  );
}

// --- Configuración (solo administrador) --------------------------------------------------------

export function ConfiguracionPreservacion() {
  const [conf, setConf] = useState<Configuracion | null>(null);
  const [frecuencia, setFrecuencia] = useState(30);
  const [formatos, setFormatos] = useState<Configuracion["formatos"]>([]);
  const [nueva, setNueva] = useState({ origen: "", mimes: "", conversor: "" });
  const [agregando, setAgregando] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: "bien" | "error"; texto: string } | null>(null);
  const [ubicacion, setUbicacion] = useState("");

  function aplicar(c: Configuracion) {
    setConf(c);
    setUbicacion(c.segunda_copia.actual || "");
    setFrecuencia(c.frecuencia_dias);
    setFormatos(c.formatos);
    setNueva({ origen: "", mimes: "", conversor: c.conversores[0]?.clave || "" });
  }

  useEffect(() => {
    pedir<Configuracion>("/api/preservacion/configuracion").then(aplicar)
      .catch((err) => setMensaje({ tipo: "error", texto: err instanceof ErrorAPI ? err.message : "No se pudo cargar." }));
  }, []);

  async function guardar(lista = formatos, segunda: string | null = null) {
    setMensaje(null);
    try {
      aplicar(await pedir<Configuracion>("/api/preservacion/configuracion", {
        method: "PUT", body: JSON.stringify({ frecuencia_dias: frecuencia, formatos: lista, segunda_ubicacion: segunda }),
      }));
      setAgregando(false);
      setMensaje({ tipo: "bien", texto: "Configuración guardada. Queda en auditoría con el valor anterior y el nuevo." });
    } catch (err) {
      setMensaje({ tipo: "error", texto: err instanceof ErrorAPI ? err.message : "No se pudo guardar." });
    }
  }

  function agregar() {
    const conversor = conf?.conversores.find((c) => c.clave === nueva.conversor);
    if (!conversor) return;
    const fila = {
      id: `f${Date.now()}`, origen: nueva.origen.trim(), destino: conversor.destino, conversor: conversor.clave, activo: true,
      origen_mime: nueva.mimes.split(",").map((m) => m.trim().toLowerCase()).filter(Boolean),
    };
    guardar([...formatos, fila]);
  }

  if (!conf) return mensaje ? <div className={`aviso ${mensaje.tipo}`}>{mensaje.texto}</div> : <div className="cargando">Cargando…</div>;
  const nombreDestino = (clave: string) => conf.destinos.find((d) => d.clave === clave)?.nombre || clave;
  const nombreConversor = (clave: string) => conf.conversores.find((c) => c.clave === clave)?.nombre || clave;

  return (
    <>
      <Link className="enlace" to="/preservacion">← Volver a Preservación</Link>
      <h1 style={{ marginTop: 10 }}>Configuración de preservación</h1>
      <p className="sub">Solo la administración ve esta pantalla. Cada cambio queda en auditoría.</p>
      {mensaje && <div className={`aviso ${mensaje.tipo}`} role="status">{mensaje.texto}</div>}
      {!conf.herramientas.ghostscript && (
        <div className="aviso alerta">Ghostscript no está instalado en este servidor: la conversión a PDF/A no funcionará.</div>
      )}

      <div className="tarjeta">
        <div className="tarjeta-cab">Frecuencia de la verificación de integridad</div>
        <div className="tarjeta-cuerpo">
          <div className="opciones" role="radiogroup" aria-label="Frecuencia">
            {FRECUENCIAS.map((f) => (
              <label key={f.dias} className={frecuencia === f.dias ? "elegida" : ""}>
                <input type="radio" name="frecuencia" checked={frecuencia === f.dias} onChange={() => setFrecuencia(f.dias)} />
                {f.nombre}
              </label>
            ))}
          </div>
          <div className="acciones" style={{ marginTop: 12 }}>
            <button type="button" className="boton chico primario" disabled={frecuencia === conf.frecuencia_dias}
                    onClick={() => guardar()}>Guardar frecuencia</button>
          </div>
        </div>
      </div>

      <div className="tarjeta">
        <div className="tarjeta-cab">
          <span>Formatos soportados para migración automática</span>
          {!agregando && <button type="button" className="boton chico" onClick={() => setAgregando(true)}>Agregar formato</button>}
        </div>
        <div className="tabla-desplazable">
          <table className="tabla-permisos">
            <thead><tr><th>Origen</th><th>Tipos MIME</th><th>Destino</th><th>Herramienta</th><th>Estado</th></tr></thead>
            <tbody>
              {formatos.map((f, i) => (
                <tr key={f.id}>
                  <td>{f.origen}</td>
                  <td className="meta">{f.origen_mime.join(", ")}</td>
                  <td>{nombreDestino(f.destino)}</td>
                  <td className="meta">{nombreConversor(f.conversor)}</td>
                  <td>
                    <button type="button" className={`insignia ${f.activo ? "bien" : "proceso"} boton-insignia`}
                            title={f.activo ? "Desactivar" : "Activar"}
                            onClick={() => guardar(formatos.map((x, j) => (j === i ? { ...x, activo: !x.activo } : x)))}>
                      {f.activo ? "Activo" : "Inactivo"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {agregando && (
          <div className="tarjeta-cuerpo form-entidad">
            <div className="rejilla">
              <div className="campo"><label htmlFor="n-origen">Nombre del origen</label>
                <input id="n-origen" className="entrada" value={nueva.origen} placeholder="p. ej. Mapas de bits"
                       onChange={(e) => setNueva({ ...nueva, origen: e.target.value })} /></div>
              <div className="campo"><label htmlFor="n-mimes">Tipos MIME (separados por coma)</label>
                <input id="n-mimes" className="entrada" value={nueva.mimes} placeholder="image/bmp, image/gif"
                       onChange={(e) => setNueva({ ...nueva, mimes: e.target.value })} /></div>
              <div className="campo"><label htmlFor="n-conv">Convertir con</label>
                <select id="n-conv" className="selector" value={nueva.conversor} onChange={(e) => setNueva({ ...nueva, conversor: e.target.value })}>
                  {conf.conversores.map((c) => <option key={c.clave} value={c.clave}>{c.nombre} → {nombreDestino(c.destino)}</option>)}
                </select></div>
            </div>
            <p className="meta">Las herramientas disponibles son las que el sistema sabe ejecutar. Para otro destino, la migración
              se hace por fuera y se carga el archivo convertido.</p>
            <div className="acciones">
              <button type="button" className="boton chico" onClick={() => setAgregando(false)}>Cancelar</button>
              <button type="button" className="boton chico primario" disabled={!nueva.origen.trim() || !nueva.mimes.trim()}
                      onClick={agregar}>Agregar</button>
            </div>
          </div>
        )}
      </div>

      <div className="tarjeta">
        <div className="tarjeta-cab">Segundo lugar de almacenamiento (segunda copia)</div>
        <div className="tarjeta-cuerpo">
          <p className="meta" style={{ marginTop: 0 }}>
            Cada archivo tiene una segunda copia, creada sola al ingresar o al migrar, y verificada junto con la primaria. La
            copia primaria vive en <code>{conf.segunda_copia.primaria}</code>. Los lugares que se pueden elegir los declara quien
            opera el servidor (variable RICORA_SEGUNDA_COPIA); desde aquí no se escriben rutas nuevas.
          </p>
          <div className="opciones opciones-columna" role="radiogroup" aria-label="Lugar de la segunda copia">
            {conf.segunda_copia.ubicaciones.map((u) => (
              <label key={u.ruta} className={ubicacion === u.ruta ? "elegida" : ""}>
                <input type="radio" name="ubicacion" checked={ubicacion === u.ruta} disabled={!u.escribible}
                       onChange={() => setUbicacion(u.ruta)} />
                <span>
                  <code>{u.ruta}</code>
                  {u.ruta === conf.segunda_copia.actual && <span className="insignia bien" style={{ marginLeft: 8 }}>En uso</span>}
                  <span className="meta" style={{ display: "block" }}>
                    {!u.existe ? "No existe en el servidor" : !u.escribible ? "No se puede escribir" :
                      `${u.libre_bytes !== null ? `${peso(u.libre_bytes)} libres` : ""}${u.mismo_disco_que_primaria
                        ? " · mismo disco que la primaria: protege de borrados y daños de archivos, no de la falla del disco"
                        : " · disco distinto de la primaria"}`}
                  </span>
                </span>
              </label>
            ))}
          </div>
          {conf.segunda_copia.ubicaciones.length === 0 && (
            <div className="aviso error">No hay ningún lugar declarado para la segunda copia.</div>
          )}
          {conf.segunda_copia.pendientes > 0 && (
            <p className="meta">{conf.segunda_copia.pendientes} archivo(s) esperan su segunda copia en el lugar en uso; el sistema
              las crea en segundo plano.</p>
          )}
          <div className="acciones" style={{ marginTop: 12 }}>
            <button type="button" className="boton chico primario" disabled={!ubicacion || ubicacion === conf.segunda_copia.actual}
                    onClick={() => guardar(formatos, ubicacion)}>Cambiar el lugar</button>
          </div>
          <p className="meta" style={{ marginBottom: 0 }}>Al cambiarlo, las copias nuevas se crean en el lugar elegido y las del
            lugar anterior se conservan (nada se borra).</p>
        </div>
      </div>
    </>
  );
}
