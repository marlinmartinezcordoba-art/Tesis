import { useCallback, useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { ICONOS } from "@/components/Marco";
import { RegistrarFondo } from "@/components/RegistrarFondo";
import { ErrorAPI, pedir, subir } from "@/lib/api";
import { useFondo, type Fondo } from "@/lib/fondo";
import { dia, fecha, peso } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";

interface ElementoCola {
  id: string;
  nombre: string;
  tamano_bytes: number;
  estado: string;
  paso: string;
  progreso: number;
  detalle_paso: string | null;
  mensaje_error: string | null;
  cargado_en: string;
  cargado_por: string | null;
  expediente: string | null;
  duplicado_de: { id: string; nombre: string; cargado_en: string; estado: string } | null;
}

interface Cola {
  procesando: ElementoCola[];
  duplicados: ElementoCola[];
  errores: ElementoCola[];
  listos_hoy: number;
}

interface ResultadoCarga {
  nombre: string;
  aceptado: boolean;
  id: string | null;
  motivo: string | null;
}

type EstadoArchivo = "listo" | "excede" | "subiendo" | "subido" | "rechazado" | "fallo";

interface ArchivoLocal {
  clave: string;
  archivo: File;
  estado: EstadoArchivo;
  avance: number;
  mensaje?: string;
}

function extension(nombre: string): string {
  const partes = nombre.split(".");
  return partes.length > 1 ? partes.pop()!.slice(0, 4) : "·";
}

function IconoArchivo({ nombre, clase = "" }: { nombre: string; clase?: string }) {
  return <span className={`icono-archivo ${clase}`} aria-hidden="true">{extension(nombre)}</span>;
}

// --- Cargar documentos -------------------------------------------------------------

function Cargar({ fondo, alTerminar }: { fondo: Fondo; alTerminar: () => void }) {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "administrador";
  const [limite, setLimite] = useState<number | null>(null);
  const [expedientes, setExpedientes] = useState<{ id: string; titulo: string }[]>([]);
  const [expediente, setExpediente] = useState("");
  const [archivos, setArchivos] = useState<ArchivoLocal[]>([]);
  const [encima, setEncima] = useState(false);
  const [subiendo, setSubiendo] = useState(false);
  const [resumen, setResumen] = useState("");
  const [cambiandoLimite, setCambiandoLimite] = useState(false);
  const [nuevoLimite, setNuevoLimite] = useState("");
  const [error, setError] = useState("");
  const selector = useRef<HTMLInputElement>(null);

  useEffect(() => {
    pedir<{ limite_bytes: number; limite_mb: number }>("/api/ingesta/limite").then((l) => setLimite(l.limite_bytes)).catch(() => undefined);
  }, []);
  useEffect(() => {
    setExpediente("");
    pedir<{ id: string; titulo: string }[]>(`/api/fondos/${fondo.id}/expedientes`).then(setExpedientes).catch(() => setExpedientes([]));
  }, [fondo.id]);

  // Si cambia el límite, se recalcula qué archivos lo exceden.
  useEffect(() => {
    if (limite === null) return;
    setArchivos((lista) => lista.map((a) =>
      a.estado === "listo" || a.estado === "excede" ? { ...a, estado: a.archivo.size > limite ? "excede" : "listo" } : a));
  }, [limite]);

  function agregar(lista: FileList | null) {
    if (!lista) return;
    setResumen("");
    const nuevos: ArchivoLocal[] = Array.from(lista).map((archivo, i) => ({
      clave: `${Date.now()}-${i}-${archivo.name}`,
      archivo,
      estado: limite !== null && archivo.size > limite ? "excede" : "listo",
      avance: 0,
    }));
    setArchivos((actuales) => [...actuales.filter((a) => a.estado !== "subido"), ...nuevos]);
  }

  function soltar(e: DragEvent) {
    e.preventDefault();
    setEncima(false);
    if (!subiendo) agregar(e.dataTransfer.files);
  }

  const actualizar = (clave: string, cambio: Partial<ArchivoLocal>) =>
    setArchivos((lista) => lista.map((a) => (a.clave === clave ? { ...a, ...cambio } : a)));

  async function cargarTodos() {
    setSubiendo(true);
    setResumen("");
    let aceptados = 0;
    let rechazados = 0;
    for (const a of archivos.filter((x) => x.estado === "listo" || x.estado === "fallo")) {
      actualizar(a.clave, { estado: "subiendo", avance: 0, mensaje: undefined });
      const datos = new FormData();
      datos.append("fondo_id", fondo.id);
      if (expediente) datos.append("expediente_id", expediente);
      datos.append("archivos", a.archivo, a.archivo.name);
      try {
        const r = await subir<{ resultados: ResultadoCarga[] }>("/api/ingesta/cargar", datos, (f) => actualizar(a.clave, { avance: f }));
        const [res] = r.resultados;
        if (res?.aceptado) {
          aceptados++;
          actualizar(a.clave, { estado: "subido", avance: 1 });
        } else {
          rechazados++;
          actualizar(a.clave, { estado: "rechazado", mensaje: res?.motivo || "El servidor no aceptó el archivo." });
        }
      } catch (err) {
        rechazados++;
        actualizar(a.clave, { estado: "fallo", mensaje: err instanceof ErrorAPI ? err.message : "No se pudo subir." });
        if (err instanceof ErrorAPI && err.status === 401) break;
      }
    }
    setSubiendo(false);
    if (aceptados) {
      setResumen(`${aceptados} archivo${aceptados === 1 ? "" : "s"} cargado${aceptados === 1 ? "" : "s"}. El sistema ya los está procesando.`);
      alTerminar();
    } else if (rechazados) {
      setResumen("");
    }
  }

  async function guardarLimite(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const l = await pedir<{ limite_bytes: number }>("/api/ingesta/limite", {
        method: "PUT",
        body: JSON.stringify({ limite_mb: Number(nuevoLimite) }),
      });
      setLimite(l.limite_bytes);
      setCambiandoLimite(false);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cambiar el límite.");
    }
  }

  const listos = archivos.filter((a) => a.estado === "listo" || a.estado === "fallo").length;
  const textoLimite = limite !== null ? peso(limite).replace(",0 ", " ") : "…";

  return (
    <>
      <h1>Cargar documentos</h1>
      <p className="sub">
        Cualquier formato, sin restricción. El sistema calcula la huella digital y reconoce el formato de cada archivo
        apenas termina de subir.
      </p>
      {error && <div className="aviso error" role="alert">{error}</div>}

      <div className="linea-campo">
        <div className="campo">
          <label htmlFor="expediente">Expediente de destino (opcional)</label>
          <select id="expediente" className="selector" value={expediente} disabled={subiendo}
                  onChange={(e) => setExpediente(e.target.value)}>
            <option value="">Sin asignar, decidir en descripción</option>
            {expedientes.map((x) => <option key={x.id} value={x.id}>{x.titulo}</option>)}
          </select>
        </div>
        {esAdmin && !cambiandoLimite && (
          <p className="pista" style={{ margin: 0 }}>
            Límite por archivo: <b>{textoLimite}</b>.{" "}
            <button type="button" className="enlace" onClick={() => { setNuevoLimite(String(Math.round((limite || 0) / 1048576))); setCambiandoLimite(true); }}>
              Cambiar
            </button>
          </p>
        )}
        {esAdmin && cambiandoLimite && (
          <form className="acciones" onSubmit={guardarLimite} style={{ alignItems: "center" }}>
            <input className="entrada" style={{ width: 110 }} type="number" min={1} max={20000} required
                   aria-label="Límite en megabytes" value={nuevoLimite} onChange={(e) => setNuevoLimite(e.target.value)} />
            <span className="pista" style={{ margin: 0 }}>MB</span>
            <button className="boton chico primario" type="submit">Guardar</button>
            <button className="boton chico" type="button" onClick={() => setCambiandoLimite(false)}>Cancelar</button>
          </form>
        )}
      </div>

      <div
        className={`zona${encima ? " encima" : ""}`}
        role="button"
        tabIndex={0}
        onClick={() => !subiendo && selector.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !subiendo && selector.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setEncima(true); }}
        onDragLeave={() => setEncima(false)}
        onDrop={soltar}
      >
        {ICONOS.ingesta}
        <div className="zona-titulo">Arrastre archivos aquí o haga clic para seleccionar</div>
        <div className="zona-sub">Cualquier formato · hasta {textoLimite} por archivo · se puede cargar en lote</div>
        <input ref={selector} type="file" multiple hidden onChange={(e) => { agregar(e.target.files); e.target.value = ""; }} />
      </div>

      {resumen && <div className="aviso bien" role="status">{resumen}</div>}

      {archivos.length > 0 && (
        <div className="tarjeta">
          <div className="tarjeta-cab">
            <span>{subiendo ? "Subiendo" : "Listos para subir"} · {archivos.length} archivo{archivos.length === 1 ? "" : "s"}</span>
            {!subiendo && (
              <button type="button" className="boton chico" onClick={() => { setArchivos([]); setResumen(""); }}>Vaciar lista</button>
            )}
          </div>
          {archivos.map((a) => (
            <div className="fila" key={a.clave}>
              <IconoArchivo nombre={a.archivo.name} clase={a.estado === "excede" || a.estado === "rechazado" || a.estado === "fallo" ? "error" : ""} />
              <div className="fila-principal">
                <div className="nombre">{a.archivo.name}</div>
                <div className="meta" style={a.estado === "excede" || a.mensaje ? { color: "var(--danger)" } : undefined}>
                  {peso(a.archivo.size)}
                  {a.estado === "excede" && ` · excede el límite de ${textoLimite}`}
                  {a.mensaje && ` · ${a.mensaje}`}
                </div>
              </div>
              {a.estado === "subiendo" && (
                <div className="barra subiendo" role="progressbar" aria-valuenow={Math.round(a.avance * 100)}>
                  <i style={{ width: `${Math.round(a.avance * 100)}%` }} />
                </div>
              )}
              {a.estado === "excede" && <span className="insignia error">Demasiado pesado</span>}
              {a.estado === "rechazado" && <span className="insignia error">Rechazado</span>}
              {a.estado === "fallo" && <span className="insignia error">No se subió</span>}
              {a.estado === "subido" && <span className="insignia bien">Cargado</span>}
              {!subiendo && a.estado !== "subido" && (
                <button type="button" className="boton chico" aria-label={`Quitar ${a.archivo.name}`}
                        onClick={() => setArchivos((l) => l.filter((x) => x.clave !== a.clave))}>
                  Quitar
                </button>
              )}
            </div>
          ))}
          <div className="confirmar">
            <span>{listos} de {archivos.length} archivo{archivos.length === 1 ? "" : "s"} listo{listos === 1 ? "" : "s"} para cargar</span>
            <button type="button" className="boton primario" disabled={!listos || subiendo} onClick={cargarTodos}>
              {subiendo ? "Subiendo…" : `Cargar ${listos} archivo${listos === 1 ? "" : "s"}`}
            </button>
          </div>
        </div>
      )}
    </>
  );
}

// --- Cola de ingesta ----------------------------------------------------------------

function FilaCola({ e, puedeDecidir, alCambiar }: { e: ElementoCola; puedeDecidir: boolean; alCambiar: (m: string) => void }) {
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");

  async function accion(metodo: string, ruta: string, mensaje: string) {
    setError("");
    setOcupado(true);
    try {
      await pedir(ruta, { method: metodo });
      alCambiar(mensaje);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo completar la acción.");
      setOcupado(false);
    }
  }

  const meta = [peso(e.tamano_bytes), e.expediente && `Expediente: ${e.expediente}`, e.cargado_por && `Cargó: ${e.cargado_por}`]
    .filter(Boolean).join(" · ");

  if (e.estado === "procesando") {
    return (
      <div className="fila">
        <IconoArchivo nombre={e.nombre} />
        <div className="fila-principal">
          <div className="nombre">{e.nombre}</div>
          <div className="meta">{e.detalle_paso || "En espera de procesamiento"}…</div>
        </div>
        <div className="barra" role="progressbar" aria-valuenow={e.progreso} aria-label={`Avance de ${e.nombre}`}>
          <i style={{ width: `${Math.max(e.progreso, 3)}%` }} />
        </div>
        <span className="insignia proceso">En proceso</span>
      </div>
    );
  }

  if (e.estado === "duplicado_pendiente") {
    return (
      <div className="fila">
        <IconoArchivo nombre={e.nombre} clase="alerta" />
        <div className="fila-principal">
          <div className="nombre">{e.nombre}</div>
          <div className="meta">
            {e.duplicado_de
              ? <>La misma huella digital ya existe en el fondo: «{e.duplicado_de.nombre}», cargado el {dia(e.duplicado_de.cargado_en)}.</>
              : "La misma huella digital ya existe en el fondo."}
            {" "}{meta}
          </div>
          {error && <div className="aviso error" style={{ margin: "8px 0 0" }}>{error}</div>}
        </div>
        {puedeDecidir && (
          <div className="acciones">
            <button type="button" className="boton chico" disabled={ocupado}
                    onClick={() => window.confirm(`¿Cancelar la carga de «${e.nombre}»? El archivo se elimina porque ya existe en el fondo.`)
                      && accion("DELETE", `/api/ingesta/${e.id}`, `Se canceló la carga de «${e.nombre}».`)}>
              Cancelar carga
            </button>
            <button type="button" className="boton chico primario" disabled={ocupado}
                    onClick={() => accion("POST", `/api/ingesta/${e.id}/confirmar-duplicado`, `«${e.nombre}» sigue su procesamiento.`)}>
              Es distinto, continuar
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="fila">
      <IconoArchivo nombre={e.nombre} clase="error" />
      <div className="fila-principal">
        <div className="nombre">{e.nombre}</div>
        <div className="meta" style={{ color: "var(--danger)" }}>{e.mensaje_error}</div>
        <div className="meta">{meta} · cargado {fecha(e.cargado_en)}</div>
        {error && <div className="aviso error" style={{ margin: "8px 0 0" }}>{error}</div>}
      </div>
      {puedeDecidir && (
        <div className="acciones">
          <button type="button" className="boton chico" disabled={ocupado}
                  onClick={() => window.confirm(`¿Descartar «${e.nombre}»? El archivo se elimina.`)
                    && accion("DELETE", `/api/ingesta/${e.id}`, `Se descartó «${e.nombre}».`)}>
            Descartar
          </button>
          <button type="button" className="boton chico primario" disabled={ocupado}
                  onClick={() => accion("POST", `/api/ingesta/${e.id}/reintentar`, `«${e.nombre}» se volverá a procesar.`)}>
            Reintentar
          </button>
        </div>
      )}
    </div>
  );
}

function VistaCola({ cola, puedeDecidir, alCambiar }: { cola: Cola | null; puedeDecidir: boolean; alCambiar: (m: string) => void }) {
  if (!cola) return <div className="vacio">Cargando…</div>;
  const vacia = !cola.procesando.length && !cola.duplicados.length && !cola.errores.length;
  return (
    <>
      <h1>Cola de ingesta</h1>
      <p className="sub">
        Solo se muestra aquí lo que todavía necesita algo de usted. Lo que ya quedó listo pasó de forma automática al
        módulo de descripción.
      </p>
      {vacia && (
        <div className="tarjeta">
          <div className="vacio-grande">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.5 2.5L16 9.5" /></svg>
            <h2>No hay nada pendiente en la ingesta</h2>
            <p className="sub" style={{ margin: "0 auto" }}>
              Todo lo cargado ya pasó a descripción.
              {cola.listos_hoy > 0 && ` En las últimas 24 horas quedaron listos ${cola.listos_hoy} documento${cola.listos_hoy === 1 ? "" : "s"}.`}
            </p>
          </div>
        </div>
      )}
      {cola.procesando.length > 0 && (
        <div className="tarjeta">
          <div className="tarjeta-cab">Procesando · {cola.procesando.length}</div>
          {cola.procesando.map((e) => <FilaCola key={e.id} e={e} puedeDecidir={puedeDecidir} alCambiar={alCambiar} />)}
        </div>
      )}
      {cola.duplicados.length > 0 && (
        <div className="tarjeta">
          <div className="tarjeta-cab">Posible duplicado · requiere su decisión</div>
          {cola.duplicados.map((e) => <FilaCola key={e.id} e={e} puedeDecidir={puedeDecidir} alCambiar={alCambiar} />)}
        </div>
      )}
      {cola.errores.length > 0 && (
        <div className="tarjeta">
          <div className="tarjeta-cab">Con error</div>
          {cola.errores.map((e) => <FilaCola key={e.id} e={e} puedeDecidir={puedeDecidir} alCambiar={alCambiar} />)}
        </div>
      )}
    </>
  );
}

// --- Pantalla -----------------------------------------------------------------------

export function Ingesta() {
  const { usuario } = useSesion();
  const { fondos, fondo } = useFondo();
  const puedeCargar = usuario?.rol === "administrador" || usuario?.rol === "archivista";
  const [pestana, setPestana] = useState<"cargar" | "cola">(puedeCargar ? "cargar" : "cola");
  const [cola, setCola] = useState<Cola | null>(null);
  const [mensaje, setMensaje] = useState("");
  const [registrando, setRegistrando] = useState(false);
  const procesandoAntes = useRef(0);

  const cargarCola = useCallback(async () => {
    if (!fondo) return;
    try {
      const c = await pedir<Cola>(`/api/ingesta/cola?fondo_id=${fondo.id}`);
      setCola(c);
      // Si terminó de procesarse algo, el panel de alertas puede cambiar.
      if (c.procesando.length < procesandoAntes.current) window.dispatchEvent(new Event("ricora:alertas"));
      procesandoAntes.current = c.procesando.length;
    } catch {
      /* el siguiente ciclo lo reintenta */
    }
  }, [fondo]);

  useEffect(() => {
    setCola(null);
    cargarCola();
  }, [cargarCola]);

  // Mientras algo se procesa se actualiza cada 3 segundos; si no, cada 20.
  const hayProceso = (cola?.procesando.length || 0) > 0;
  useEffect(() => {
    const t = setInterval(cargarCola, hayProceso ? 3000 : 20000);
    return () => clearInterval(t);
  }, [cargarCola, hayProceso]);

  if (fondos === null) return <div className="cargando">Cargando…</div>;

  if (!fondo) {
    return (
      <>
        <h1>Ingesta</h1>
        <div className="tarjeta">
          <div className="tarjeta-cab">Todavía no hay ningún fondo registrado</div>
          {usuario?.rol === "administrador" ? (
            <>
              <div className="tarjeta-cuerpo" style={{ paddingBottom: 0 }}>
                <p className="sub" style={{ margin: 0 }}>
                  Registre el fondo histórico con el que va a trabajar. Todo lo que se cargue quedará dentro de él.
                </p>
              </div>
              <RegistrarFondo alTerminar={() => undefined} />
            </>
          ) : (
            <div className="vacio">Pida al administrador que registre el fondo histórico con el que se va a trabajar.</div>
          )}
        </div>
      </>
    );
  }

  const pendientes = cola ? cola.procesando.length + cola.duplicados.length + cola.errores.length : 0;

  return (
    <>
      <div className="pestanas" role="tablist">
        {puedeCargar && (
          <button type="button" role="tab" aria-selected={pestana === "cargar"} className={`pestana${pestana === "cargar" ? " activa" : ""}`}
                  onClick={() => setPestana("cargar")}>
            Cargar documentos
          </button>
        )}
        <button type="button" role="tab" aria-selected={pestana === "cola"} className={`pestana${pestana === "cola" ? " activa" : ""}`}
                onClick={() => setPestana("cola")}>
          Cola de ingesta {pendientes > 0 && <span className="contador">{pendientes}</span>}
        </button>
        {usuario?.rol === "administrador" && (
          <button type="button" className="pestana" style={{ marginLeft: "auto", marginRight: 0 }} onClick={() => setRegistrando(!registrando)}>
            + Registrar otro fondo
          </button>
        )}
      </div>
      {registrando && (
        <div className="tarjeta"><RegistrarFondo alTerminar={() => setRegistrando(false)} /></div>
      )}
      {mensaje && <div className="aviso bien" role="status">{mensaje}</div>}
      {pestana === "cargar" && puedeCargar ? (
        <Cargar fondo={fondo} alTerminar={cargarCola} />
      ) : (
        <VistaCola cola={cola} puedeDecidir={puedeCargar}
                   alCambiar={(m) => { setMensaje(m); cargarCola(); }} />
      )}
    </>
  );
}
