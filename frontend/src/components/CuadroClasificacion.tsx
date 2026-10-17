import { useCallback, useEffect, useState } from "react";
import { ErrorAPI, descargar, pedir, subir } from "@/lib/api";
import { useSesion } from "@/lib/sesion";

// Cuadro de clasificación (CCD) y tabla de retención (TRD) del fondo.
// Se cargan desde la plantilla Excel del sistema o desde la TRD en el
// formato del AGN (Excel o PDF), siempre con vista previa antes de crear.

interface Regla { gestion_anios: number | null; central_anios: number | null; disposicion_nombre: string | null;
  resumen: string; heredada_de: { titulo: string } | null }
interface NodoCuadro { id: string; nivel: string; codigo: string | null; titulo: string; regla: Regla | null;
  expedientes: number; hijos: NodoCuadro[] }
interface NodoLeido { codigo: string | null; nombre: string }
interface FilaLeida {
  fila: number; seccion: NodoLeido | null; subseccion: NodoLeido | null; serie: NodoLeido | null; subserie: NodoLeido | null;
  tipos: string[]; gestion: number | null; central: number | null; disposicion: string | null; otras_disposiciones: string[];
  procedimiento: string | null; funcion: string | null; problemas: string[];
  codigos: { seccion: string | null; subseccion: string | null; serie: string | null; subserie: string | null };
}
interface Vista { origen: string; filas: FilaLeida[]; resumen: Record<string, number> }
interface Informe { creados: Record<string, number>; reutilizados: number; reglas: number; tipos_documentales: number;
  funciones: number; avisos: string[] }

const NIVEL: Record<string, string> = { seccion: "Sección", subseccion: "Subsección", serie: "Serie", subserie: "Subserie" };
const DISP: Record<string, string> = { ct: "CT", e: "E", s: "S", m: "M" };

function mensaje(err: unknown, porDefecto: string) {
  return err instanceof ErrorAPI ? err.message : porDefecto;
}

function Rama({ n, profundidad }: { n: NodoCuadro; profundidad: number }) {
  return (
    <>
      <tr>
        <td style={{ paddingLeft: 8 + profundidad * 18 }}>
          <span className="meta">{NIVEL[n.nivel]}</span> {n.codigo && <strong>{n.codigo}</strong>} {n.titulo}
        </td>
        <td>{n.regla && !n.regla.heredada_de ? `${n.regla.gestion_anios ?? "—"} / ${n.regla.central_anios ?? "—"}` : ""}</td>
        <td>{n.regla && !n.regla.heredada_de ? n.regla.disposicion_nombre : ""}</td>
        <td>{n.nivel === "serie" || n.nivel === "subserie" ? n.expedientes : ""}</td>
      </tr>
      {n.hijos.map((h) => <Rama key={h.id} n={h} profundidad={profundidad + 1} />)}
    </>
  );
}

export function CuadroClasificacion({ fondoId }: { fondoId: string }) {
  const { usuario } = useSesion();
  const esAdmin = !!usuario?.es_administrador;
  const [arbol, setArbol] = useState<NodoCuadro[] | null>(null);
  const [vista, setVista] = useState<Vista | null>(null);
  const [incluir, setIncluir] = useState<Set<number>>(new Set());
  const [informe, setInforme] = useState<Informe | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");

  const cargar = useCallback(() => {
    pedir<NodoCuadro[]>(`/api/cuadro?fondo_id=${fondoId}`).then(setArbol).catch((err) => setError(mensaje(err, "No se pudo cargar.")));
  }, [fondoId]);
  useEffect(cargar, [cargar]);

  async function leer(archivo: File) {
    setError("");
    setInforme(null);
    const datos = new FormData();
    datos.append("archivo", archivo, archivo.name);
    setOcupado(true);
    try {
      const v = await subir<Vista>("/api/cuadro/vista-previa", datos, () => undefined);
      setVista(v);
      setIncluir(new Set(v.filas.filter((f) => !f.problemas.length).map((f) => f.fila)));
    } catch (err) {
      setError(mensaje(err, "No se pudo leer el archivo."));
    } finally {
      setOcupado(false);
    }
  }

  async function aplicar() {
    if (!vista) return;
    setError("");
    setOcupado(true);
    try {
      const r = await pedir<Informe>("/api/cuadro/aplicar", { method: "POST", body: JSON.stringify({
        fondo_id: fondoId, filas: vista.filas.filter((f) => incluir.has(f.fila)) }) });
      setInforme(r);
      setVista(null);
      cargar();
    } catch (err) {
      setError(mensaje(err, "No se pudo crear."));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <>
      <h1>Cuadro de clasificación y tabla de retención</h1>
      <p className="sub">
        El cuadro (CCD) organiza el fondo en secciones, subsecciones, series y subseries con su código; la tabla de
        retención (TRD) dice cuánto tiempo se guarda cada serie y qué pasa después. Con ellos el sistema sabe a qué serie,
        sección y fondo pertenece cada documento, y la retención la heredan sus expedientes.
      </p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {informe && (
        <div className="aviso bien" role="status">
          Listo: {Object.entries(informe.creados).map(([k, v]) => `${v} ${NIVEL[k]?.toLowerCase() || k}(s)`).join(", ") || "nada nuevo"};
          {" "}{informe.reglas} regla(s) de retención; {informe.tipos_documentales} tipo(s) documental(es) nuevos;
          {" "}{informe.reutilizados} nivel(es) que ya existían.
          {informe.avisos.length > 0 && <ul>{informe.avisos.map((a) => <li key={a}>{a}</li>)}</ul>}
        </div>
      )}
      {esAdmin && (
        <div className="tarjeta">
          <div className="tarjeta-cab">Cargar el cuadro y la TRD</div>
          <div className="tarjeta-cuerpo">
            <p className="meta">
              Use la plantilla Excel del sistema, o la TRD en el formato del AGN (columnas D, S, Sb; series, subseries y tipos
              documentales; AG, AC; CT, E, M, S; procedimiento), en Excel o en PDF. Primero verá lo que el sistema entendió;
              nada se crea hasta que lo confirme. Si un código ya existe, se reutiliza.
            </p>
            <div className="acciones">
              <button type="button" className="boton chico"
                      onClick={() => descargar("/api/cuadro/plantilla").catch(() => undefined)}>Descargar la plantilla Excel</button>
              <label className="boton chico primario">
                {ocupado ? "Leyendo…" : "Leer un archivo (Excel o PDF)"}
                <input type="file" accept=".xlsx,.xlsm,.pdf" hidden disabled={ocupado}
                       onChange={(e) => e.target.files?.[0] && leer(e.target.files[0])} />
              </label>
            </div>
          </div>
        </div>
      )}
      {vista && (
        <div className="tarjeta tabla-desplazable">
          <div className="tarjeta-cab">Vista previa · {vista.origen} · {vista.resumen.filas} fila(s), {vista.resumen.con_problemas} con problemas</div>
          <table className="tabla-permisos">
            <thead><tr><th>Crear</th><th>Sección</th><th>Serie / subserie</th><th>Tipos documentales</th><th>AG / AC</th>
              <th>Disposición</th><th>Problemas</th></tr></thead>
            <tbody>
              {vista.filas.map((f) => (
                <tr key={f.fila} className={f.problemas.length ? "fila-problema" : undefined}>
                  <td><input type="checkbox" aria-label={`Crear la fila ${f.fila}`} disabled={!!f.problemas.length}
                             checked={incluir.has(f.fila)}
                             onChange={(e) => setIncluir((s) => { const n = new Set(s); if (e.target.checked) n.add(f.fila); else n.delete(f.fila); return n; })} /></td>
                  <td>{f.codigos.seccion} {f.seccion?.nombre}{f.subseccion ? ` › ${f.codigos.subseccion || ""} ${f.subseccion.nombre}` : ""}</td>
                  <td><strong>{f.codigos.serie}</strong> {f.serie?.nombre}
                    {f.subserie && <div>› <strong>{f.codigos.subserie}</strong> {f.subserie.nombre}</div>}</td>
                  <td>{f.tipos.join("; ")}</td>
                  <td>{f.gestion ?? "—"} / {f.central ?? "—"}</td>
                  <td>{f.disposicion ? [f.disposicion, ...f.otras_disposiciones].map((d) => DISP[d]).join(" + ") : "—"}</td>
                  <td>{f.problemas.join(" ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="acciones" style={{ padding: "0 18px 14px" }}>
            <button type="button" className="boton chico primario" disabled={ocupado || !incluir.size} onClick={aplicar}>
              Crear {incluir.size} fila(s)</button>
            <button type="button" className="boton chico" onClick={() => setVista(null)}>Descartar la lectura</button>
          </div>
        </div>
      )}
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Cuadro del fondo</div>
        {!arbol ? <div className="cargando">Cargando…</div> : arbol.length === 0 ? (
          <p className="meta" style={{ padding: "0 18px" }}>Todavía no hay cuadro de clasificación en este fondo.</p>
        ) : (
          <table className="tabla-permisos">
            <thead><tr><th>Nivel</th><th>Retención AG / AC (años)</th><th>Disposición final</th><th>Expedientes</th></tr></thead>
            <tbody>{arbol.map((n) => <Rama key={n.id} n={n} profundidad={0} />)}</tbody>
          </table>
        )}
      </div>
    </>
  );
}
