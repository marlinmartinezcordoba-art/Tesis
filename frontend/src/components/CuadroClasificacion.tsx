import { useCallback, useEffect, useState } from "react";
import { ErrorAPI, pedir } from "@/lib/api";
import { NivelRiC } from "@/components/NivelRiC";

// Cuadro de clasificación (CCD) del fondo y piezas compartidas con la carga de
// la TRD desde un archivo (plantilla del sistema o formato del AGN, en Excel o
// PDF): la vista previa y el resultado de la validación RiC-O.

interface Regla { gestion_anios: number | null; central_anios: number | null; disposicion_nombre: string | null;
  resumen: string; heredada_de: { titulo: string } | null; vigencia_legible: string | null; versiones: number }
interface NodoCuadro { id: string; nivel: string; codigo: string | null; titulo: string; regla: Regla | null;
  expedientes: number; hijos: NodoCuadro[] }
export interface NodoLeido { codigo: string | null; nombre: string }
export interface FilaLeida {
  fila: number; seccion: NodoLeido | null; intermedias?: NodoLeido[]; subseccion: NodoLeido | null; serie: NodoLeido | null; subserie: NodoLeido | null;
  tipos: string[]; gestion: number | null; central: number | null; disposicion: string | null; otras_disposiciones: string[];
  procedimiento: string | null; funcion: string | null; problemas: string[];
  codigos: { seccion: string | null; subseccion: string | null; serie: string | null; subserie: string | null };
}
export interface Vista { origen: string; filas: FilaLeida[]; resumen: Record<string, number> }
export interface Informe { creados: Record<string, number>; reutilizados: number; reglas: number; tipos_documentales: number;
  funciones: number; avisos: string[] }

export interface Validacion { conforme: boolean; ontologia: string; tripletas: number; por_clase: Record<string, number>;
  problemas_owl: string[]; resultados_shacl: { mensaje?: string | null; foco?: string | null; forma?: string | null }[] }

const NIVEL: Record<string, string> = { seccion: "Sección", subseccion: "Subsección", serie: "Serie", subserie: "Subserie" };
const DISP: Record<string, string> = { ct: "CT", e: "E", s: "S", m: "M" };

function mensaje(err: unknown, porDefecto: string) {
  return err instanceof ErrorAPI ? err.message : porDefecto;
}

// Lo que el sistema entendió del archivo, fila por fila: se marcan las que se crean.
export function TablaVistaPrevia({ vista, incluir, setIncluir }: { vista: Vista; incluir: Set<number>;
  setIncluir: (f: (s: Set<number>) => Set<number>) => void }) {
  return (
    <table className="tabla-permisos">
      <thead><tr><th>Crear</th><th>Sección</th><th>Serie / subserie</th><th>Tipos documentales</th><th>AG / AC</th>
        <th>Disposición</th><th>Problemas</th></tr></thead>
      <tbody>
        {vista.filas.map((f) => (
          <tr key={f.fila} className={f.problemas.length ? "fila-problema" : undefined}>
            <td><input type="checkbox" aria-label={`Crear la fila ${f.fila}`} disabled={!!f.problemas.length}
                       checked={incluir.has(f.fila)}
                       onChange={(e) => setIncluir((s) => { const n = new Set(s); if (e.target.checked) n.add(f.fila); else n.delete(f.fila); return n; })} /></td>
            <td>{f.codigos.seccion} {f.seccion?.nombre}
              {(f.intermedias || []).map((n, i) => <span key={i}> › {n.codigo || ""} {n.nombre}</span>)}
              {f.subseccion ? ` › ${f.codigos.subseccion || ""} ${f.subseccion.nombre}` : ""}</td>
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
  );
}

// El resultado de validar en RiC-O 1.1 (OWL y SHACL) lo que se va a crear.
export function ResultadoValidacion({ v }: { v: Validacion }) {
  const clases = Object.entries(v.por_clase).map(([c, n]) => `${n} rico:${c}`).join(", ");
  return (
    <div className={`aviso ${v.conforme ? "bien" : "error"}`} role="status">
      <strong>{v.conforme ? "Conforme con " : "No conforme con "}{v.ontologia}</strong> (ontología oficial y perfil SHACL):
      {" "}{v.tripletas} tripletas · {clases}.
      {!v.conforme && (
        <ul>
          {v.problemas_owl.map((p) => <li key={p}>{p}</li>)}
          {v.resultados_shacl.map((r, i) => <li key={i}>{r.mensaje || r.forma}{r.foco && <span className="meta"> · {r.foco}</span>}</li>)}
        </ul>
      )}
    </div>
  );
}

function Rama({ n, profundidad }: { n: NodoCuadro; profundidad: number }) {
  return (
    <>
      <tr>
        <td style={{ paddingLeft: 8 + profundidad * 18 }}>
          <span className="meta">{NIVEL[n.nivel]}</span> {n.codigo && <strong>{n.codigo}</strong>} {n.titulo}
          {" "}<NivelRiC nivel={n.nivel} />
        </td>
        <td>{n.regla && !n.regla.heredada_de ? `${n.regla.gestion_anios ?? "—"} / ${n.regla.central_anios ?? "—"}` : ""}</td>
        <td>{n.regla && !n.regla.heredada_de ? n.regla.disposicion_nombre : ""}</td>
        <td className="meta">{n.regla && !n.regla.heredada_de ? (n.regla.vigencia_legible || "—")
          + (n.regla.versiones > 1 ? ` (${n.regla.versiones} versiones)` : "") : ""}</td>
        <td>{n.nivel === "serie" || n.nivel === "subserie" ? n.expedientes : ""}</td>
      </tr>
      {n.hijos.map((h) => <Rama key={h.id} n={h} profundidad={profundidad + 1} />)}
    </>
  );
}

// El cuadro de clasificación que resulta de aplicar la TRD: solo consulta. Se
// parametriza en Versiones de la TRD, Dependencias, Series y Matriz.
export function CuadroClasificacion({ fondoId }: { fondoId: string }) {
  const [arbol, setArbol] = useState<NodoCuadro[] | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(() => {
    pedir<NodoCuadro[]>(`/api/cuadro?fondo_id=${fondoId}`).then(setArbol).catch((err) => setError(mensaje(err, "No se pudo cargar.")));
  }, [fondoId]);
  useEffect(cargar, [cargar]);

  return (
    <>
      <h1>Cuadro de clasificación</h1>
      <p className="sub">
        El cuadro (CCD) del fondo tal como quedó al aplicar la TRD vigente: secciones, subsecciones, series y subseries con
        su código y su retención. Con él el sistema sabe a qué serie, sección y fondo pertenece cada documento, y sus
        expedientes heredan la retención. Para cambiarlo, abra una versión nueva de la TRD.
      </p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Cuadro del fondo</div>
        {!arbol ? <div className="cargando">Cargando…</div> : arbol.length === 0 ? (
          <p className="meta" style={{ padding: "0 18px" }}>Todavía no hay cuadro de clasificación en este fondo: parametrice
            y aplique una versión de la TRD.</p>
        ) : (
          <table className="tabla-permisos">
            <thead><tr><th>Nivel</th><th>Retención AG / AC (años)</th><th>Disposición final</th><th>Vigencia de la regla</th>
              <th>Expedientes</th></tr></thead>
            <tbody>{arbol.map((n) => <Rama key={n.id} n={n} profundidad={0} />)}</tbody>
          </table>
        )}
      </div>
    </>
  );
}
