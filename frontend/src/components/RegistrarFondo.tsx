import { useEffect, useRef, useState } from "react";
import { unoOVarios } from "@/lib/zip";
import { PanelCarga, leerConAvance, useCarga, type ArchivoLeido } from "@/components/CargaArchivos";
import { ErrorAPI, descargar, pedir, subir } from "@/lib/api";
import { useFondo, type Fondo } from "@/lib/fondo";
import { ResultadoValidacion, TablaVistaPrevia, type Informe, type Validacion, type Vista } from "@/components/CuadroClasificacion";

// Solo el administrador registra fondos. Todo en una pantalla: 1) suba la TRD y el CCD (uno o
// varios archivos, o arrástrelos); 2) el sistema los lee y propone el nombre de la entidad;
// 3) revise las filas marcadas y cree el fondo. Al crear se valida en RiC-O 1.1: si no es
// conforme no se crea nada y se muestra por qué. La retención es opcional (fondo histórico).

export interface Respuesta { creado: boolean; fondo: Fondo | null; informe: Informe; validacion: Validacion;
  parametrizacion: Record<string, number> | null; version: { nombre: string; estado: string } | null }

type VistaLeida = Vista & { archivos?: ArchivoLeido[]; entidad?: string | null };

// Lo leído se guarda en este navegador como borrador hasta crear el fondo: si la persona cambia de
// módulo o recarga, no pierde la lectura. Se borra al crear el fondo o con «Empezar de nuevo».
const BORRADOR = "ricora.borrador-fondo";
interface Borrador { vista: VistaLeida; incluir: number[]; titulo: string; fechas: string; acto: string;
  fechaActo: string; desde: string }

function leerBorrador(): Borrador | null {
  try {
    const b = JSON.parse(localStorage.getItem(BORRADOR) || "null") as Borrador | null;
    return b && b.vista && Array.isArray(b.vista.filas) ? b : null;
  } catch {
    return null;
  }
}

function borrarBorrador() {
  try { localStorage.removeItem(BORRADOR); } catch { /* sin almacenamiento: no hay nada que borrar */ }
}

// Une la lectura guardada con la de los archivos nuevos (sin los archivos ya subidos a mano tras recargar).
function unir(antes: VistaLeida, nueva: VistaLeida): VistaLeida {
  // Se numeran de corrido para que cada fila se marque por separado.
  const filas = [...antes.filas, ...nueva.filas].map((f, i) => ({ ...f, fila: i + 1 }));
  const nombres = new Set((nueva.archivos || []).map((a) => a.archivo));
  return { ...nueva, filas, origen: `${antes.origen} + ${nueva.origen}`, entidad: antes.entidad || nueva.entidad,
    archivos: [...(antes.archivos || []).filter((a) => !nombres.has(a.archivo)), ...(nueva.archivos || [])],
    resumen: { ...nueva.resumen, filas: filas.length, con_problemas: filas.filter((f) => f.problemas.length).length,
      secciones: new Set(filas.map((f) => f.seccion?.nombre).filter(Boolean)).size,
      series: new Set(filas.map((f) => `${f.seccion?.nombre}|${f.serie?.codigo || f.serie?.nombre}`).filter((x) => !x.endsWith("|"))).size,
      subseries: filas.filter((f) => f.subserie).length } };
}

export function RegistrarFondo({ alTerminar, alCrear }: { alTerminar: () => void; alCrear?: (r: Respuesta) => void }) {
  const { recargar, elegir } = useFondo();
  const [guardado] = useState(leerBorrador);
  const [titulo, setTitulo] = useState(guardado?.titulo || "");
  const [fechas, setFechas] = useState(guardado?.fechas || "");
  // La TRD aprobada: con el acto, su fecha y la vigencia, el fondo nace con la versión 1 vigente.
  const [acto, setActo] = useState(guardado?.acto || "");
  const [fechaActo, setFechaActo] = useState(guardado?.fechaActo || "");
  const [desde, setDesde] = useState(guardado?.desde || "");
  const [vista, setVista] = useState<VistaLeida | null>(guardado?.vista || null);
  const [incluir, setIncluir] = useState<Set<number>>(new Set(guardado?.incluir || []));
  const [rechazo, setRechazo] = useState<Respuesta | null>(null);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [encima, setEncima] = useState(false);
  // Los archivos ya subidos: «Agregar» suma a estos (el del mismo nombre se reemplaza) y se leen todos juntos.
  const [subidos, setSubidos] = useState<File[]>([]);
  const carga = useCarga();
  const entrada = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!vista) return;
    try {
      localStorage.setItem(BORRADOR, JSON.stringify({ vista, incluir: [...incluir], titulo, fechas, acto, fechaActo, desde }));
    } catch { /* sin almacenamiento (ventana privada o lleno): la lectura sigue en pantalla */ }
  }, [vista, incluir, titulo, fechas, acto, fechaActo, desde]);

  function empezarDeNuevo() {
    borrarBorrador();
    setSubidos([]); setVista(null); setIncluir(new Set()); setTitulo(""); setFechas(""); setActo(""); setFechaActo("");
    setDesde(""); setRechazo(null); setError(""); carga.reiniciar();
  }

  const mensaje = (err: unknown, por: string) => (err instanceof ErrorAPI ? err.message : por);
  const conProblemas = vista ? vista.filas.filter((f) => f.problemas.length).length : 0;
  const faltaActo = !!acto.trim() && (!fechaActo || !desde);

  async function recibir(nuevos: File[], reemplazar = false) {
    if (!nuevos.length || ocupado) return;
    setError("");
    setRechazo(null);
    const nombres = new Set(nuevos.map((f) => f.name));
    const lista = reemplazar ? nuevos : [...subidos.filter((f) => !nombres.has(f.name)), ...nuevos];
    carga.empezar(lista);
    const archivo = await unoOVarios(lista, "TRD.zip");
    if (!archivo) return;
    setOcupado(true);
    try {
      const v = await leerConAvance<VistaLeida>(archivo, carga);
      // Tras volver al módulo, la lectura guardada no tiene sus archivos: lo nuevo se le suma.
      const final = !reemplazar && vista && !subidos.length ? unir(vista, v) : v;
      carga.terminar(final.archivos);
      setSubidos(lista);
      setVista(final);
      setIncluir(new Set(final.filas.filter((f) => !f.problemas.length).map((f) => f.fila)));
      if (!titulo.trim() && v.entidad) setTitulo(v.entidad);
    } catch (err) {
      carga.fallar(mensaje(err, "No se pudo leer el archivo."));
      setError(mensaje(err, "No se pudo leer el archivo."));
    } finally {
      setOcupado(false);
    }
  }

  async function crear() {
    setError("");
    setRechazo(null);
    setOcupado(true);
    try {
      const r = await pedir<Respuesta>("/api/fondos/configurar", { method: "POST", body: JSON.stringify({
        fondo: { titulo: titulo.trim(), fechas_extremas: fechas || null },
        filas: vista?.filas.filter((f) => incluir.has(f.fila)) || [], crear: true,
        version: acto.trim() ? { acto_aprobacion: acto.trim(), fecha_aprobacion: fechaActo || null, vigente_desde: desde || null } : null }) });
      if (!r.creado || !r.fondo) {
        setRechazo(r);
        setError("No se creó nada: el cuadro no es conforme con RiC-O. Abajo está el motivo.");
        return;
      }
      borrarBorrador();
      await recargar();
      elegir(r.fondo.id);
      if (alCrear) alCrear(r);
      else alTerminar();
    } catch (err) {
      setError(mensaje(err, "No se pudo crear el fondo."));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="formulario-nuevo registro-rapido">
      {error && <div className="aviso error" role="alert">{error}</div>}

      <label className={`zona-soltar${encima ? " encima" : ""}${ocupado ? " ocupada" : ""}`}
             tabIndex={0} role="button"
             onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); entrada.current?.click(); } }}
             onDragOver={(e) => { e.preventDefault(); setEncima(true); }}
             onDragLeave={() => setEncima(false)}
             onDrop={(e) => { e.preventDefault(); setEncima(false); void recibir(Array.from(e.dataTransfer.files)); }}>
        <input ref={entrada} type="file" multiple accept=".xlsx,.xlsm,.pdf,.docx,.csv,.zip" hidden disabled={ocupado}
               onChange={(e) => { const l = Array.from(e.target.files || []); e.target.value = ""; void recibir(l); }} />
        <strong>{ocupado ? "Leyendo…" : vista ? `Agregar más archivos (${vista.archivos?.length || subidos.length} leídos)` : "Suba la TRD y el CCD"}</strong>
        <span className="meta">Arrástrelos aquí o haga clic. Uno o varios: Excel, PDF con texto, Word, CSV o .zip, tal como
          los tiene la entidad.</span>
      </label>
      <PanelCarga estado={carga.estado} />
      {vista && !subidos.length && guardado && (
        <div className="aviso" role="note">Recuperé la lectura que dejó sin terminar ({vista.filas.length} filas). El fondo
          todavía <b>no se ha creado</b>: revise y pulse «Crear el fondo».</div>
      )}
      {vista && (
        <p className="meta">Los archivos nuevos se suman a los ya leídos. Lo leído queda guardado en este navegador hasta
          crear el fondo.{" "}
          <button type="button" className="enlace" disabled={ocupado} onClick={empezarDeNuevo}>Empezar de nuevo</button></p>
      )}
      {!vista && (
        <p className="meta">¿No tiene el archivo en un formato legible?{" "}
          <button type="button" className="enlace" onClick={() => descargar("/api/cuadro/plantilla").catch(() => undefined)}>
            Descargue la plantilla Excel</button>.</p>
      )}

      {vista && (
        <>
          <div className="resumen-lectura">
            <span><b>{vista.resumen.secciones ?? 0}</b> secciones</span>
            <span><b>{vista.resumen.series ?? 0}</b> series</span>
            <span><b>{vista.resumen.subseries ?? 0}</b> subseries</span>
            <span><b>{incluir.size}</b> filas para crear</span>
            {conProblemas > 0 && <span className="texto-error"><b>{conProblemas}</b> por revisar</span>}
          </div>

          <div className="rejilla">
            <div className="campo">
              <label htmlFor="f-titulo">Nombre del fondo</label>
              <input id="f-titulo" className="entrada" required minLength={3} value={titulo}
                     placeholder="Nombre completo de la entidad productora" onChange={(e) => setTitulo(e.target.value)} />
              {vista.entidad && titulo === vista.entidad && <span className="meta">Tomado del encabezado del archivo. Corríjalo si hace falta.</span>}
            </div>
            <div className="campo">
              <label htmlFor="f-fechas">Fechas extremas (opcional)</label>
              <input id="f-fechas" className="entrada" value={fechas} placeholder="1930–1955"
                     onChange={(e) => setFechas(e.target.value)} />
            </div>
          </div>

          <details className="plegable" open={conProblemas > 0}>
            <summary>{conProblemas > 0 ? `Revise las filas (${conProblemas} con problemas no se crearán si no las marca)`
              : "Ver las filas leídas"}</summary>
            <div className="tabla-desplazable">
              <div className="meta">{vista.origen}</div>
              <TablaVistaPrevia vista={vista} incluir={incluir} setIncluir={setIncluir} />
            </div>
          </details>

          <details className="plegable">
            <summary>La TRD ya está aprobada (opcional)</summary>
            <p className="meta">Con el acto, el fondo nace con la versión 1 vigente. Sin él, queda en borrador.</p>
            <div className="rejilla">
              <div className="campo">
                <label htmlFor="f-acto">Acto que la aprueba</label>
                <input id="f-acto" className="entrada" value={acto} placeholder="Resolución 045"
                       onChange={(e) => setActo(e.target.value)} />
              </div>
              <div className="campo">
                <label htmlFor="f-fecha-acto">Fecha de aprobación</label>
                <input id="f-fecha-acto" className="entrada" type="date" value={fechaActo}
                       onChange={(e) => setFechaActo(e.target.value)} />
              </div>
              <div className="campo">
                <label htmlFor="f-desde">Rige desde</label>
                <input id="f-desde" className="entrada" type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
              </div>
            </div>
          </details>

          {rechazo && <ResultadoValidacion v={rechazo.validacion} />}

          <div className="acciones">
            <button type="button" className="boton primario"
                    disabled={ocupado || !incluir.size || titulo.trim().length < 3 || faltaActo} onClick={crear}>
              {ocupado ? "Creando…" : `Crear el fondo con ${incluir.size} fila(s)`}</button>
            {!alCrear && <button className="boton" type="button" onClick={alTerminar}>Cancelar</button>}
          </div>
          {titulo.trim().length < 3 && <p className="meta">Escriba el nombre del fondo para poder crearlo.</p>}
          {faltaActo && <p className="meta">Si registra el acto, ponga también su fecha y desde cuándo rige.</p>}
          <p className="meta">Antes de crear, el sistema valida todo en RiC-O 1.1; si algo no cumple, no se crea nada.</p>
        </>
      )}
    </div>
  );
}
