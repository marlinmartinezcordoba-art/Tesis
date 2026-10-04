import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, descargar, pedir } from "@/lib/api";
import { NIVEL_NOMBRE } from "@/lib/descripcion";
import { useFondo } from "@/lib/fondo";
import { dia, peso } from "@/lib/formato";
import { FRECUENCIAS, TIPO_ATENCION, type Configuracion, type Panel } from "@/lib/preservacion";

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
          <LineaTiempo fondoId={fondo.id} />
          <NivelesNdsa />
        </>
      )}
    </>
  );
}

// --- Niveles NDSA 2.0, calculados (PRE-13) ----------------------------------------------------------

interface RequisitoNdsa { requisito: string; cumple: boolean; evidencia: string }
interface AreaNdsa { area: string; nivel: number; requisitos: RequisitoNdsa[][]; falta_para_el_siguiente: string[] }

function NivelesNdsa() {
  const [areas, setAreas] = useState<AreaNdsa[] | null>(null);
  useEffect(() => {
    pedir<{ areas: AreaNdsa[] }>("/api/preservacion/ndsa").then((d) => setAreas(d.areas)).catch(() => setAreas(null));
  }, []);
  if (!areas) return null;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Niveles NDSA 2.0 · calculados del estado real del sistema</div>
      <p className="sub" style={{ margin: "0 16px 8px" }}>
        Un nivel cuenta solo si se cumplen todos sus requisitos y los de los niveles inferiores.
      </p>
      {areas.map((a) => (
        <details key={a.area} className="fila" style={{ display: "block" }}>
          <summary>
            <strong>{a.area}</strong> · nivel {a.nivel} de 4
            {a.falta_para_el_siguiente.length > 0 && <span className="meta"> · falta: {a.falta_para_el_siguiente.join("; ")}</span>}
          </summary>
          {a.requisitos.map((nivel, i) => (
            <ul key={i} style={{ margin: "4px 0 4px 16px" }}>
              {nivel.map((r) => (
                <li key={r.requisito}>
                  <span className={`insignia ${r.cumple ? "bien" : "alerta"}`}>{r.cumple ? "Cumple" : "No cumple"}</span>{" "}
                  Nivel {i + 1}: {r.requisito} <span className="meta">({r.evidencia})</span>
                </li>
              ))}
            </ul>
          ))}
        </details>
      ))}
    </div>
  );
}

// --- Línea de tiempo de los últimos eventos de preservación -----------------------------------------

interface Eventos {
  verificacion: { fecha: string; resultados: Record<string, number> } | null;
  migracion: { fecha: string; estado: string; destino: string; archivo: string } | null;
  restauracion: { fecha: string; estado_previo: string; archivo: string } | null;
  simulacro_base_de_datos: { fecha: string; estado: "correcto" | "fallido"; respaldo_en: string;
    tablas: Record<string, number> | null; descargado_en: string | null } | null;
}

const ICONO_EVENTO = {
  bien: <path d="M5 12.5l4.5 4.5L19 7.5" />, alerta: <path d="M12 6v7M12 17.5v.01" />, error: <path d="M7 7l10 10M17 7L7 17" />,
  neutro: <circle cx="12" cy="12" r="3" />,
};

function Evento({ estado, titulo, children }: { estado: keyof typeof ICONO_EVENTO; titulo: string; children: React.ReactNode }) {
  return (
    <li>
      <span className={`marca-evento ${estado === "neutro" ? "" : estado}`} aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">{ICONO_EVENTO[estado]}</svg>
      </span>
      <div><strong>{titulo}</strong><div className="meta">{children}</div></div>
    </li>
  );
}

function LineaTiempo({ fondoId }: { fondoId: string }) {
  const [e, setE] = useState<Eventos | null>(null);
  useEffect(() => {
    pedir<Eventos>(`/api/preservacion/eventos-recientes?fondo_id=${fondoId}`).then(setE).catch(() => setE(null));
  }, [fondoId]);
  if (!e) return null;
  const v = e.verificacion;
  const fallas = v ? (v.resultados.alterada || 0) + (v.resultados.ausente || 0) : 0;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Últimos eventos de preservación</div>
      <ol className="cronologia">
        <Evento estado={!v ? "neutro" : fallas ? "error" : "bien"} titulo="Última verificación de integridad">
          {v ? <>{dia(v.fecha)} · {v.resultados.integra || 0} íntegro(s){fallas ? `, ${fallas} con problema` : ""}</> : "Todavía no se ha verificado ningún archivo."}
        </Evento>
        <Evento estado={!e.migracion ? "neutro" : e.migracion.estado === "completada" ? "bien" : e.migracion.estado === "fallida" ? "error" : "alerta"}
                titulo="Última migración de formato">
          {e.migracion ? <>{dia(e.migracion.fecha)} · «{e.migracion.archivo}» a {e.migracion.destino} · {ESTADO_MIGRACION[e.migracion.estado] || e.migracion.estado}</>
            : "Ninguna migración todavía."}
        </Evento>
        <Evento estado={e.restauracion ? "alerta" : "neutro"} titulo="Última restauración desde la segunda copia">
          {e.restauracion ? <>{dia(e.restauracion.fecha)} · «{e.restauracion.archivo}» estaba {e.restauracion.estado_previo}</> : "Nunca hizo falta restaurar un archivo."}
        </Evento>
        <Evento estado={!e.simulacro_base_de_datos ? "alerta" : e.simulacro_base_de_datos.estado === "correcto" ? "bien" : "error"}
                titulo="Último simulacro de restauración de la base de datos">
          {e.simulacro_base_de_datos
            ? <>{dia(e.simulacro_base_de_datos.fecha)} · {e.simulacro_base_de_datos.estado === "correcto"
                ? `restaurado entero (${e.simulacro_base_de_datos.tablas?.recursos_documentales ?? 0} descripciones, ${e.simulacro_base_de_datos.tablas?.instanciaciones ?? 0} archivos)`
                : "falló: revise Configuración › Respaldos"}
                {" · "}{e.simulacro_base_de_datos.descargado_en ? `copia fuera del servidor el ${dia(e.simulacro_base_de_datos.descargado_en)}` : "aún sin copia fuera del servidor"}</>
            : "Todavía no hay respaldo: el sistema lo hace solo en las próximas horas."}
        </Evento>
      </ol>
    </div>
  );
}
// --- Respaldos de la base de datos (solo administrador) ------------------------------------------

interface Respaldo {
  id: string; iniciado_en: string; origen: string; estado: "en_curso" | "correcto" | "fallido";
  archivo: string | null; tamano_bytes: number | null; huella: string | null; error: string | null;
  simulacro_estado: "correcto" | "fallido" | null; simulacro_error: string | null;
  descargado_en: string | null; depurado_en: string | null; destino: string;
}

function Respaldos() {
  const [datos, setDatos] = useState<{ respaldos: Respaldo[]; frecuencia_horas: number; dias_copia_externa: number } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "bien" | "error"; texto: string } | null>(null);
  const cargar = useCallback(() => {
    pedir<typeof datos>("/api/preservacion/respaldos").then(setDatos).catch(() => setDatos(null));
  }, []);
  useEffect(cargar, [cargar]);

  async function ahora() {
    setOcupado(true); setAviso(null);
    try {
      const r = await pedir<Respaldo>("/api/preservacion/respaldos", { method: "POST" });
      setAviso(r.simulacro_estado === "correcto"
        ? { tipo: "bien", texto: "Respaldo hecho y restaurado de prueba sin diferencias." }
        : { tipo: "error", texto: `El respaldo o su simulacro falló: ${r.error || r.simulacro_error || "revise el registro"}` });
      cargar();
    } catch (err) {
      setAviso({ tipo: "error", texto: err instanceof ErrorAPI ? err.message : "No se pudo respaldar." });
    } finally { setOcupado(false); }
  }

  async function bajar(r: Respaldo) {
    try {
      const h = await descargar(`/api/preservacion/respaldos/${r.id}/descargar`);
      setAviso({ tipo: "bien", texto: `Descargado. Guárdelo fuera del servidor; su huella SHA-256 es ${h.get("X-Huella-SHA256")}.` });
      cargar();
    } catch (err) {
      setAviso({ tipo: "error", texto: err instanceof ErrorAPI ? err.message : "No se pudo descargar." });
    }
  }

  if (!datos) return null;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">
        <span>Respaldos de la base de datos</span>
        <button type="button" className="boton chico" disabled={ocupado} onClick={ahora}>{ocupado ? "Respaldando…" : "Respaldar ahora"}</button>
      </div>
      <div className="tarjeta-cuerpo">
        <p className="sub" style={{ marginTop: 0 }}>
          Cada {datos.frecuencia_horas} h el sistema vuelca la base y la restaura de prueba en una base aparte para comprobar
          que el respaldo sirve. El volcado queda en el mismo servidor: descárguelo a otro equipo al menos cada{" "}
          {datos.dias_copia_externa} días, o el sistema le avisará.
        </p>
        {aviso && <div className={`aviso ${aviso.tipo}`} role="status">{aviso.texto}</div>}
        {datos.respaldos.length === 0 ? <div className="vacio">Todavía no hay respaldos.</div> : (
          <div className="tabla-desplazable">
            <table className="tabla">
              <thead><tr><th>Fecha</th><th>Respaldo</th><th>Simulacro</th><th>Tamaño</th><th>Fuera del servidor</th><th /></tr></thead>
              <tbody>
                {datos.respaldos.slice(0, 10).map((r) => (
                  <tr key={r.id}>
                    <td>{dia(r.iniciado_en)}</td>
                    <td><span className={`insignia ${r.estado === "correcto" ? "bien" : r.estado === "fallido" ? "error" : ""}`}>{r.estado}</span></td>
                    <td>{r.simulacro_estado ? <span className={`insignia ${r.simulacro_estado === "correcto" ? "bien" : "error"}`}>{r.simulacro_estado}</span> : "—"}</td>
                    <td>{r.tamano_bytes ? peso(r.tamano_bytes) : "—"}</td>
                    <td>{r.descargado_en ? dia(r.descargado_en) : "—"}</td>
                    <td>{r.estado === "correcto" && !r.depurado_en && (
                      <button type="button" className="boton chico" onClick={() => bajar(r)}>Descargar</button>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// --- Recuperación ante desastres (solo administrador; NFR-04 y NFR-07) ----------------------------

interface Paquete {
  id: string; creado_en: string; estado: "en_curso" | "correcto" | "fallido"; tamano_bytes: number | null;
  huella: string | null; archivos: number | null; error: string | null; simulacro_estado: "correcto" | "fallido" | null;
  simulacro_segundos: number | null; archivos_verificados: number | null; simulacro_error: string | null;
  descargado_en: string | null; depurado_en: string | null; ausentes: string[];
}
interface EstadoRecuperacion {
  objetivos: { rpo_horas: number; rto_horas: number; aprovisionar_horas: number };
  escenarios: { clave: string; escenario: string; mecanismo: string; rpo: string; rto: string;
                rpo_actual_horas: number | null; rto_medido_horas: number | null; cumple: boolean }[];
  ultimo_paquete: Paquete | null; paquetes: Paquete[]; frecuencia_dias: number;
}

function horasTexto(h: number | null) {
  if (h === null) return "sin medir";
  if (h === 0) return "ninguna";
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  return h < 48 ? `${Math.round(h * 10) / 10} h` : `${Math.round(h / 24)} días`;
}

function Recuperacion() {
  const [datos, setDatos] = useState<EstadoRecuperacion | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "bien" | "error"; texto: string } | null>(null);
  const [objetivos, setObjetivos] = useState({ rpo_horas: 168, rto_horas: 8, frecuencia_dias: 7 });
  const cargar = useCallback(() => {
    pedir<EstadoRecuperacion>("/api/preservacion/recuperacion").then((d) => {
      setDatos(d);
      setObjetivos({ rpo_horas: d.objetivos.rpo_horas, rto_horas: d.objetivos.rto_horas, frecuencia_dias: d.frecuencia_dias });
    }).catch(() => setDatos(null));
  }, []);
  useEffect(cargar, [cargar]);

  async function generar() {
    setOcupado(true); setAviso(null);
    try {
      const p = await pedir<Paquete>("/api/preservacion/recuperacion", { method: "POST" });
      setAviso(p.simulacro_estado === "correcto"
        ? { tipo: p.ausentes.length ? "error" : "bien",
            texto: `Paquete listo y restaurado de prueba completo en ${p.simulacro_segundos} s: ${p.archivos_verificados} archivos con su huella.`
              + (p.ausentes.length ? ` Faltan en el disco y no entraron: ${p.ausentes.join(", ")}. Repóngalos desde la segunda copia.` : "") }
        : { tipo: "error", texto: `El paquete o su restauración de prueba falló: ${p.error || p.simulacro_error || "revise el registro"}` });
      cargar();
    } catch (err) {
      setAviso({ tipo: "error", texto: err instanceof ErrorAPI ? err.message : "No se pudo armar el paquete." });
    } finally { setOcupado(false); }
  }

  async function bajar(p: Paquete) {
    try {
      const h = await descargar(`/api/preservacion/recuperacion/${p.id}/descargar`);
      setAviso({ tipo: "bien", texto: `Descargado. Guárdelo en un disco fuera del servidor y fuera de línea; su huella SHA-256 es ${h.get("X-Huella-SHA256")}.` });
      cargar();
    } catch (err) {
      setAviso({ tipo: "error", texto: err instanceof ErrorAPI ? err.message : "No se pudo descargar." });
    }
  }

  async function guardar(e: FormEvent) {
    e.preventDefault();
    try {
      setDatos(await pedir<EstadoRecuperacion>("/api/preservacion/recuperacion/objetivos",
                                               { method: "PUT", body: JSON.stringify(objetivos) }));
      setAviso({ tipo: "bien", texto: "Objetivos de recuperación guardados." });
    } catch (err) {
      setAviso({ tipo: "error", texto: err instanceof ErrorAPI ? err.message : "No se pudieron guardar." });
    }
  }

  if (!datos) return null;
  const vivo = datos.paquetes.find((p) => p.estado === "correcto" && !p.depurado_en);
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">
        <span>Recuperación ante desastres</span>
        <button type="button" className="boton chico" disabled={ocupado} onClick={generar}>
          {ocupado ? "Armando y probando…" : "Armar paquete y probar"}
        </button>
      </div>
      <div className="tarjeta-cuerpo">
        <p className="sub" style={{ marginTop: 0 }}>
          El paquete de recuperación lleva la base, todos los documentos digitales y su manifiesto de huellas: con él se
          levanta RICORA en un servidor nuevo. {datos.frecuencia_dias ? `Cada ${datos.frecuencia_dias} días` : "Cuando usted lo pida"} el
          sistema lo arma y lo restaura de prueba completo en una base y una carpeta aparte, y mide cuánto tarda. Descárguelo a un
          disco fuera del servidor: es la única copia que sobrevive a perder el servidor.
        </p>
        {aviso && <div className={`aviso ${aviso.tipo}`} role="status">{aviso.texto}</div>}
        <div className="tabla-desplazable">
          <table className="tabla">
            <thead><tr><th>Escenario</th><th>Cómo se recupera</th><th>Pérdida posible (RPO)</th><th>Tiempo de vuelta (RTO)</th><th /></tr></thead>
            <tbody>
              {datos.escenarios.map((e) => (
                <tr key={e.clave}>
                  <td>{e.escenario}</td>
                  <td className="meta">{e.mecanismo}</td>
                  <td>{horasTexto(e.rpo_actual_horas)} <span className="meta">· objetivo {horasTexto(datos.objetivos.rpo_horas)}</span></td>
                  <td>{horasTexto(e.rto_medido_horas)} <span className="meta">· objetivo {horasTexto(datos.objetivos.rto_horas)}</span></td>
                  <td><span className={`insignia ${e.cumple ? "bien" : "alerta"}`}>{e.cumple ? "Cumple" : "No cumple"}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="pista">El tiempo de vuelta tras perder el servidor suma la restauración medida y {datos.objetivos.aprovisionar_horas} h
          estimadas para instalar un servidor nuevo. La pérdida posible es el tiempo desde la última descarga del paquete.</p>
        {datos.ultimo_paquete ? (
          <p>
            Último paquete probado: {dia(datos.ultimo_paquete.creado_en)} · {datos.ultimo_paquete.archivos} archivos ·{" "}
            {datos.ultimo_paquete.tamano_bytes ? peso(datos.ultimo_paquete.tamano_bytes) : "—"} · restaurado en{" "}
            {datos.ultimo_paquete.simulacro_segundos} s · {datos.ultimo_paquete.descargado_en
              ? `descargado el ${dia(datos.ultimo_paquete.descargado_en)}` : <span className="texto-alerta">nunca descargado</span>}
          </p>
        ) : <div className="vacio">Todavía no hay un paquete de recuperación probado.</div>}
        {vivo && <button type="button" className="boton chico primario" onClick={() => bajar(vivo)}>Descargar el último paquete</button>}
        <form onSubmit={guardar} className="rejilla" style={{ marginTop: 14, alignItems: "end" }}>
          <div className="campo" style={{ margin: 0 }}>
            <label htmlFor="rpo">Pérdida máxima aceptable (horas)</label>
            <input id="rpo" type="number" min={1} max={8760} className="entrada" value={objetivos.rpo_horas}
                   onChange={(e) => setObjetivos({ ...objetivos, rpo_horas: Number(e.target.value) })} />
          </div>
          <div className="campo" style={{ margin: 0 }}>
            <label htmlFor="rto">Tiempo máximo para volver (horas)</label>
            <input id="rto" type="number" min={1} max={720} className="entrada" value={objetivos.rto_horas}
                   onChange={(e) => setObjetivos({ ...objetivos, rto_horas: Number(e.target.value) })} />
          </div>
          <div className="campo" style={{ margin: 0 }}>
            <label htmlFor="frec">Armar y probar cada (días; 0 = a mano)</label>
            <input id="frec" type="number" min={0} max={365} className="entrada" value={objetivos.frecuencia_dias}
                   onChange={(e) => setObjetivos({ ...objetivos, frecuencia_dias: Number(e.target.value) })} />
          </div>
          <button type="submit" className="boton chico">Guardar objetivos</button>
        </form>
      </div>
    </div>
  );
}

const ESTADO_MIGRACION: Record<string, string> = { completada: "completada", fallida: "fallida", en_curso: "en curso", esperando_archivo: "esperando el archivo convertido" };

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

      <Respaldos />
      <Recuperacion />

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
