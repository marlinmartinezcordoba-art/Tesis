import { useCallback, useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ICONOS, useVista } from "@/components/Marco";
import { LotesDelFondo, NuevoLote, type Lote } from "@/components/Lotes";
import { RegistrarFondo } from "@/components/RegistrarFondo";
import { BotonPrevisualizar } from "@/components/VisorDocumento";
import { ErrorAPI, pedir, puede, subir } from "@/lib/api";
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
  const esAdmin = !!usuario?.es_administrador;
  const [limite, setLimite] = useState<number | null>(null);
  const [expedientes, setExpedientes] = useState<{ id: string; titulo: string }[]>([]);
  const [expediente, setExpediente] = useState("");
  const [lotes, setLotes] = useState<Lote[]>([]);
  const [lote, setLote] = useState("");
  const [abriendoLote, setAbriendoLote] = useState(false);
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
    setLote("");
    pedir<Lote[]>(`/api/ingesta/lotes?fondo_id=${fondo.id}`).then((l) => setLotes(l.filter((x) => x.estado === "abierto")))
      .catch(() => setLotes([]));
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
      if (lote) datos.append("lote_id", lote);
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
        <div className="campo">
          <label htmlFor="lote">Lote de transferencia <span className="meta">(procedencia · ISAD-G 3.2.4)</span></label>
          <select id="lote" className="selector" value={lote} disabled={subiendo} onChange={(e) => setLote(e.target.value)}>
            <option value="">Sin lote</option>
            {lotes.map((l) => <option key={l.id} value={l.id}>{l.numero} · {l.dependencia_origen?.nombre || l.forma_ingreso_nombre}
              {l.acta_numero ? ` · acta ${l.acta_numero}` : ""}</option>)}
          </select>
          {!abriendoLote && (
            <button type="button" className="enlace" onClick={() => setAbriendoLote(true)}>+ Abrir un lote de transferencia</button>
          )}
        </div>
        {esAdmin && !cambiandoLimite && (
          <p className="pista" style={{ margin: 0 }}>
            Límite por archivo: <b>{textoLimite}</b>.{" "}
            <button type="button" className="enlace" onClick={() => { setNuevoLimite(String(Math.round((limite || 0) / 1048576))); setCambiandoLimite(true); }}>
              Cambiar
            </button>
          </p>
        )}
        {esAdmin && <UmbralOcr />}
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

      {abriendoLote && (
        <div className="tarjeta">
          <div className="tarjeta-cab">Nuevo lote de transferencia</div>
          <NuevoLote fondoId={fondo.id} alCancelar={() => setAbriendoLote(false)}
                     alCrear={(l) => { setLotes((x) => [l, ...x]); setLote(l.id); setAbriendoLote(false); alTerminar(); }} />
        </div>
      )}

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
        <div className="acciones">
          <BotonPrevisualizar base={`/api/ingesta/${e.id}/previsualizar`} nombre={e.nombre} />
          {e.duplicado_de && <BotonPrevisualizar base={`/api/ingesta/${e.duplicado_de.id}/previsualizar`} nombre={e.duplicado_de.nombre} etiqueta="Ver el que ya existe" />}
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
      <div className="acciones"><BotonPrevisualizar base={`/api/ingesta/${e.id}/previsualizar`} nombre={e.nombre} /></div>
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

// --- Contenido de apoyo: actividad reciente y resumen del fondo ----------------------------------------

interface Reciente {
  id: string; nombre: string; tamano_bytes: number; formato: string | null; estado: string; cargado_en: string;
  expediente: string | null; descrito_en: string | null;
}

// Debajo del área de carga: los últimos cinco archivos y dónde quedaron.
// Si el fondo aún no tiene nada, una guía de tres pasos para empezar.
function ActividadReciente({ fondo, version }: { fondo: Fondo; version: number }) {
  const [filas, setFilas] = useState<Reciente[] | null>(null);
  useEffect(() => {
    pedir<Reciente[]>(`/api/ingesta/recientes?fondo_id=${fondo.id}`).then(setFilas).catch(() => setFilas([]));
  }, [fondo.id, version]);
  if (filas === null) return null;
  if (filas.length === 0) {
    return (
      <div className="tarjeta">
        <div className="tarjeta-cab">Cómo empezar</div>
        <ol className="pasos-inicio">
          <li><strong>Arrastre o seleccione los archivos.</strong> Cualquier formato: el sistema calcula su huella digital y reconoce el formato.</li>
          <li><strong>Si ya lo sabe, elija el expediente de destino.</strong> Es opcional: también se decide al describir.</li>
          <li><strong>Revise el resultado en la cola de ingesta.</strong> Allí aparece lo que necesita su decisión (duplicados, errores).</li>
        </ol>
      </div>
    );
  }
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab" style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <span>Actividad reciente de ingesta</span>
        <Link to="/ingesta?vista=cola" className="enlace">Ver la cola de ingesta</Link>
      </div>
      {filas.map((f) => (
        <div className="fila" key={f.id}>
          <IconoArchivo nombre={f.nombre} />
          <div className="fila-principal">
            <div className="nombre">{f.nombre}</div>
            <div className="meta">{peso(f.tamano_bytes)}{f.formato && ` · ${f.formato}`} · cargado {fecha(f.cargado_en)}</div>
          </div>
          <span title={f.descrito_en || f.expediente || undefined} className={`insignia recortada ${f.descrito_en ? "bien" : f.estado === "listo_para_descripcion" ? (f.expediente ? "proceso" : "neutra-borde") : f.estado === "error" ? "error" : "alerta"}`}>
            {f.descrito_en ? `Descrito en «${f.descrito_en}»` : f.estado === "listo_para_descripcion"
              ? (f.expediente ? `Asignado a «${f.expediente}»` : "Pendiente de asignar")
              : ESTADO_CORTO[f.estado] || f.estado}
          </span>
          <BotonPrevisualizar base={`/api/ingesta/${f.id}/previsualizar`} nombre={f.nombre} />
        </div>
      ))}
    </div>
  );
}
const ESTADO_CORTO: Record<string, string> = { procesando: "En proceso", duplicado_pendiente: "Posible duplicado", error: "Con error" };

// Debajo de una cola corta: el estado general del fondo, con los mismos
// datos del panel de preservación (no un cálculo propio de esta pantalla).
function ResumenIngesta({ fondo }: { fondo: Fondo }) {
  const [r, setR] = useState<{ documentos: number; con_texto: number; en_riesgo: number; riesgo_integridad: number; riesgo_obsolescencia: number } | null>(null);
  useEffect(() => {
    pedir<typeof r>(`/api/ingesta/resumen?fondo_id=${fondo.id}`).then(setR).catch(() => setR(null));
  }, [fondo.id]);
  if (!r) return null;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Estado general de la ingesta del fondo</div>
      <div className="resumen-preservacion compacto">
        <div className="cifra"><strong>{r.documentos}</strong><span>Documentos ingresados</span></div>
        <div className="cifra bien"><strong>{r.con_texto}</strong><span>Con texto reconocido</span></div>
        <div className={`cifra${r.en_riesgo ? " alerta" : ""}`}><strong>{r.en_riesgo}</strong>
          <span>En riesgo · {r.riesgo_integridad} de integridad, {r.riesgo_obsolescencia} de obsolescencia (<Link to="/preservacion">ver en Preservación</Link>)</span></div>
      </div>
    </div>
  );
}

// --- Pantalla -----------------------------------------------------------------------

export function Ingesta() {
  const { usuario } = useSesion();
  const { fondos, fondo } = useFondo();
  const puedeCargar = puede(usuario, "ingesta", "escribir");
  const pestana = useVista<"cargar" | "cola">("/ingesta");
  const [cola, setCola] = useState<Cola | null>(null);
  const [mensaje, setMensaje] = useState("");
  const [registrando, setRegistrando] = useState(false);
  const [version, setVersion] = useState(0);
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
          {usuario?.es_administrador ? (
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

  return (
    <>
      {usuario?.es_administrador && (
        <div className="acciones-vista">
          <button type="button" className="enlace" onClick={() => setRegistrando(!registrando)}>+ Registrar otro fondo</button>
        </div>
      )}
      {registrando && (
        <div className="tarjeta"><RegistrarFondo alTerminar={() => setRegistrando(false)} /></div>
      )}
      {mensaje && <div className="aviso bien" role="status">{mensaje}</div>}
      {pestana === "cargar" && puedeCargar ? (
        <>
          <Cargar fondo={fondo} alTerminar={() => { cargarCola(); setVersion((v) => v + 1); }} />
          <LotesDelFondo fondoId={fondo.id} version={version} puedeEscribir={puedeCargar} />
          <ActividadReciente fondo={fondo} version={version} />
        </>
      ) : (
        <>
          <VistaCola cola={cola} puedeDecidir={puedeCargar}
                     alCambiar={(m) => { setMensaje(m); cargarCola(); }} />
          {cola && cola.procesando.length + cola.duplicados.length + cola.errores.length < 5 && <ResumenIngesta fondo={fondo} />}
        </>
      )}
    </>
  );
}

// Confianza mínima del OCR: por debajo, el documento se marca para leerlo con
// cuidado (aparece en el panel de alertas y en el espacio de descripción).
function UmbralOcr() {
  const [umbral, setUmbral] = useState<number | null>(null);
  const [editando, setEditando] = useState(false);
  const [valor, setValor] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    pedir<{ umbral: number }>("/api/ingesta/umbral-ocr").then((r) => setUmbral(r.umbral)).catch(() => undefined);
  }, []);

  async function guardar(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const r = await pedir<{ umbral: number }>("/api/ingesta/umbral-ocr", {
        method: "PUT", body: JSON.stringify({ umbral: Number(valor) }),
      });
      setUmbral(r.umbral);
      setEditando(false);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cambiar el umbral.");
    }
  }

  if (umbral === null) return null;
  return editando ? (
    <form className="acciones" onSubmit={guardar} style={{ alignItems: "center" }}>
      <label className="pista" style={{ margin: 0 }} htmlFor="umbral-ocr">Confianza mínima del OCR</label>
      <input id="umbral-ocr" className="entrada" style={{ width: 80 }} type="number" min={0} max={100} required
             value={valor} onChange={(e) => setValor(e.target.value)} />
      <span className="pista" style={{ margin: 0 }}>/ 100</span>
      <button className="boton chico primario" type="submit">Guardar</button>
      <button className="boton chico" type="button" onClick={() => setEditando(false)}>Cancelar</button>
      {error && <span className="pista" style={{ color: "var(--danger)", margin: 0 }}>{error}</span>}
    </form>
  ) : (
    <p className="pista" style={{ margin: 0 }}>
      Confianza mínima del OCR: <b>{umbral} / 100</b>.{" "}
      <button type="button" className="enlace" onClick={() => { setValor(String(umbral)); setEditando(true); }}>Cambiar</button>
    </p>
  );
}
