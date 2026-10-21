import { useState } from "react";
import { ErrorAPI, descargar, pedir, subir } from "@/lib/api";
import { useFondo, type Fondo } from "@/lib/fondo";
import { ResultadoValidacion, TablaVistaPrevia, type Informe, type Validacion, type Vista } from "@/components/CuadroClasificacion";

// Solo el administrador registra fondos. Un fondo se configura desde su cuadro de
// clasificación (CCD) y su tabla de retención (TRD): 1) datos del fondo, 2) el
// cuadro leído del archivo, 3) validación en RiC-O 1.1, 4) creación (todo o nada).
// La retención es opcional: un fondo histórico puede no tener TRD.

const NOMBRE: Record<string, string> = { seccion: "sección(es)", subseccion: "subsección(es)", serie: "serie(s)",
  subserie: "subserie(s)" };

const PASOS = ["Datos del fondo", "Cuadro de clasificación y TRD", "Validación RiC-O", "Crear"];

export interface Respuesta { creado: boolean; fondo: Fondo | null; informe: Informe; validacion: Validacion;
  parametrizacion: Record<string, number> | null; version: { nombre: string; estado: string } | null }

export function RegistrarFondo({ alTerminar, alCrear }: { alTerminar: () => void; alCrear?: (r: Respuesta) => void }) {
  const { recargar, elegir } = useFondo();
  const [paso, setPaso] = useState(0);
  const [titulo, setTitulo] = useState("");
  const [fechas, setFechas] = useState("");
  // La TRD aprobada: con el acto, su fecha y la vigencia, el fondo nace con la versión 1 vigente.
  const [acto, setActo] = useState("");
  const [fechaActo, setFechaActo] = useState("");
  const [desde, setDesde] = useState("");
  const [vista, setVista] = useState<Vista | null>(null);
  const [incluir, setIncluir] = useState<Set<number>>(new Set());
  const [prueba, setPrueba] = useState<Respuesta | null>(null);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const mensaje = (err: unknown, por: string) => (err instanceof ErrorAPI ? err.message : por);
  const cuerpo = (crear: boolean) => JSON.stringify({
    fondo: { titulo, fechas_extremas: fechas || null }, filas: vista?.filas.filter((f) => incluir.has(f.fila)) || [], crear,
    version: acto.trim() ? { acto_aprobacion: acto.trim(), fecha_aprobacion: fechaActo || null, vigente_desde: desde || null } : null });

  async function leer(archivo: File) {
    setError("");
    const datos = new FormData();
    datos.append("archivo", archivo, archivo.name);
    setOcupado(true);
    try {
      const v = await subir<Vista>("/api/cuadro/vista-previa", datos, () => undefined);
      setVista(v);
      setPrueba(null);
      setIncluir(new Set(v.filas.filter((f) => !f.problemas.length).map((f) => f.fila)));
    } catch (err) {
      setError(mensaje(err, "No se pudo leer el archivo."));
    } finally {
      setOcupado(false);
    }
  }

  async function validar() {
    setError("");
    setOcupado(true);
    try {
      setPrueba(await pedir<Respuesta>("/api/fondos/configurar", { method: "POST", body: cuerpo(false) }));
      setPaso(2);
    } catch (err) {
      setError(mensaje(err, "No se pudo validar."));
    } finally {
      setOcupado(false);
    }
  }

  async function crear() {
    setError("");
    setOcupado(true);
    try {
      const r = await pedir<Respuesta>("/api/fondos/configurar", { method: "POST", body: cuerpo(true) });
      if (!r.creado || !r.fondo) {
        setPrueba(r);
        setError("No se creó: el cuadro no es conforme con RiC-O. Revise el detalle.");
        return;
      }
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
    <div className="formulario-nuevo">
      <ol className="pasos-asistente">
        {PASOS.map((p, i) => <li key={p} className={i === paso ? "activo" : i < paso ? "hecho" : undefined}>{i + 1}. {p}</li>)}
      </ol>
      {error && <div className="aviso error" role="alert">{error}</div>}

      {paso === 0 && (
        <form onSubmit={(e) => { e.preventDefault(); setPaso(1); }}>
          <div className="rejilla">
            <div className="campo">
              <label htmlFor="f-titulo">Nombre del fondo</label>
              <input id="f-titulo" className="entrada" required minLength={3} value={titulo}
                     placeholder="Correspondencia municipal" onChange={(e) => setTitulo(e.target.value)} />
            </div>
            <div className="campo">
              <label htmlFor="f-fechas">Fechas extremas (opcional)</label>
              <input id="f-fechas" className="entrada" value={fechas} placeholder="1930–1955"
                     onChange={(e) => setFechas(e.target.value)} />
            </div>
          </div>
          <p className="meta">Si la TRD ya está aprobada, registre su acto: el fondo nace con la versión 1 vigente. Si no,
            queda en borrador y se completa en Fondos › Versiones de la TRD.</p>
          <div className="rejilla">
            <div className="campo">
              <label htmlFor="f-acto">Acto que aprueba la TRD (opcional)</label>
              <input id="f-acto" className="entrada" value={acto} placeholder="Resolución 045"
                     onChange={(e) => setActo(e.target.value)} />
            </div>
            <div className="campo">
              <label htmlFor="f-fecha-acto">Fecha de aprobación</label>
              <input id="f-fecha-acto" className="entrada" type="date" value={fechaActo} required={!!acto.trim()}
                     onChange={(e) => setFechaActo(e.target.value)} />
            </div>
            <div className="campo">
              <label htmlFor="f-desde">Rige desde</label>
              <input id="f-desde" className="entrada" type="date" value={desde} required={!!acto.trim()}
                     onChange={(e) => setDesde(e.target.value)} />
            </div>
          </div>
          <div className="acciones">
            <button className="boton primario" type="submit">Siguiente: el cuadro de clasificación</button>
            {!alCrear && <button className="boton" type="button" onClick={alTerminar}>Cancelar</button>}
          </div>
        </form>
      )}

      {paso === 1 && (
        <>
          <p className="meta">
            El fondo se organiza desde su cuadro de clasificación: secciones (dependencias productoras), series,
            subseries y tipos documentales, y, si los hay, los tiempos de retención y la disposición final de la TRD. Use
            la plantilla Excel del sistema o la TRD en el formato del AGN, en Excel o PDF. Si el fondo es histórico y no
            tiene TRD, deje vacías las columnas de retención.
          </p>
          <div className="acciones">
            <button type="button" className="boton chico" onClick={() => descargar("/api/cuadro/plantilla").catch(() => undefined)}>
              Descargar la plantilla Excel</button>
            <label className="boton chico primario">
              {ocupado ? "Leyendo…" : vista ? "Leer otro archivo" : "Leer el cuadro (Excel o PDF)"}
              <input type="file" accept=".xlsx,.xlsm,.pdf" hidden disabled={ocupado}
                     onChange={(e) => e.target.files?.[0] && leer(e.target.files[0])} />
            </label>
          </div>
          {vista && (
            <div className="tabla-desplazable" style={{ marginTop: 10 }}>
              <div className="meta">Vista previa · {vista.origen} · {vista.resumen.filas} fila(s), {vista.resumen.con_problemas} con problemas</div>
              <TablaVistaPrevia vista={vista} incluir={incluir} setIncluir={setIncluir} />
            </div>
          )}
          <div className="acciones">
            <button type="button" className="boton primario" disabled={ocupado || !incluir.size} onClick={validar}>
              {ocupado ? "Validando…" : "Siguiente: validar en RiC-O"}</button>
            <button type="button" className="boton" onClick={() => setPaso(0)}>Atrás</button>
          </div>
        </>
      )}

      {paso >= 2 && prueba && (
        <>
          <p className="meta">
            Así quedaría «{titulo}» en RiC-O 1.1: {Object.entries(prueba.informe.creados).map(([k, v]) => `${v} ${NOMBRE[k] || k}`).join(", ")};
            {" "}{prueba.informe.reglas} regla(s) de retención; {prueba.informe.tipos_documentales} tipo(s) documental(es).
            Todavía no se ha creado nada.
          </p>
          <ResultadoValidacion v={prueba.validacion} />
          <div className="acciones">
            <button type="button" className="boton primario" disabled={ocupado || !prueba.validacion.conforme} onClick={crear}>
              {ocupado ? "Creando…" : "Crear el fondo con su cuadro"}</button>
            <button type="button" className="boton" onClick={() => setPaso(1)}>Atrás</button>
          </div>
        </>
      )}
    </div>
  );
}
