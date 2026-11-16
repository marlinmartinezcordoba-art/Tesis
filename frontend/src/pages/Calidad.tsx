// Validación semántica y calidad del fondo: cada hallazgo con la descripción o entidad afectada,
// el problema, la regla incumplida y la acción que lo corrige.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, pedir } from "@/lib/api";
import { useFondo } from "@/lib/fondo";

interface Afectado { tipo: string; id: string; titulo: string; nivel: string; enlace: string }
interface Hallazgo {
  tipo: string; gravedad: "error" | "aviso"; afectado: Afectado | null; problema: string; regla: string; accion: string;
  enlace: string | null;
}
interface Calidad {
  resumen: { tipo: string; nombre: string; gravedad: string; total: number }[];
  errores: number; avisos: number; hallazgos: Hallazgo[]; descripciones_revisadas: number; relaciones_revisadas: number;
}

export function Calidad() {
  const { fondo } = useFondo();
  const [datos, setDatos] = useState<Calidad | null>(null);
  const [error, setError] = useState("");
  const [tipo, setTipo] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  function revisar() {
    if (!fondo) return;
    setCargando(true);
    setError("");
    pedir<Calidad>(`/api/fondos/${fondo.id}/calidad`).then(setDatos)
      .catch((e) => setError(e instanceof ErrorAPI ? e.message : "No se pudo revisar la calidad."))
      .finally(() => setCargando(false));
  }
  useEffect(revisar, [fondo]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!fondo) return <div className="aviso">Elija un fondo para revisar su calidad.</div>;
  const lista = (datos?.hallazgos || []).filter((h) => !tipo || h.tipo === tipo);

  return (
    <>
      <div className="cabecera-nivel">
        <h1 style={{ margin: 0 }}>Calidad</h1>
        <button type="button" className="boton chico" onClick={revisar} disabled={cargando}>
          {cargando ? "Revisando…" : "Revisar de nuevo"}</button>
      </div>
      <p className="sub">Validación semántica del fondo: entidades duplicadas, identificadores repetidos, fechas
        contradictorias, descripciones incompletas, relaciones sin evidencia, relaciones y propiedades fuera de RiC-O,
        el perfil SHACL y la coherencia entre el CCD y la TRD vigente.</p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!datos && !error && <div className="cargando">Revisando…</div>}
      {datos && (
        <>
          <p className="meta">{datos.descripciones_revisadas} descripción(es) y {datos.relaciones_revisadas} relación(es)
            revisadas · <span className="insignia error">{datos.errores} error(es)</span>{" "}
            <span className="insignia alerta">{datos.avisos} aviso(s)</span></p>
          <div className="calidad-resumen" role="group" aria-label="Filtrar por tipo de hallazgo">
            <button type="button" className={`calidad-chip${!tipo ? " activo" : ""}`} onClick={() => setTipo(null)}>
              Todos <b>{datos.hallazgos.length}</b></button>
            {datos.resumen.map((r) => (
              <button type="button" key={r.tipo} className={`calidad-chip${tipo === r.tipo ? " activo" : ""}${r.total ? ` ${r.gravedad}` : " cero"}`}
                      onClick={() => setTipo(tipo === r.tipo ? null : r.tipo)} aria-pressed={tipo === r.tipo}>
                {r.nombre} <b>{r.total}</b></button>
            ))}
          </div>
          {lista.length === 0 ? (
            <div className="tarjeta"><div className="vacio">{datos.hallazgos.length ? "Ningún hallazgo de este tipo."
              : "Sin hallazgos: el conocimiento del fondo cumple todas las reglas revisadas."}</div></div>
          ) : (
            <div className="tarjeta tabla-desplazable">
              <table className="tabla-permisos tabla-calidad">
                <thead><tr><th>Gravedad</th><th>Afecta a</th><th>Problema</th><th>Regla incumplida</th><th>Acción correctiva</th></tr></thead>
                <tbody>
                  {lista.map((h, i) => (
                    <tr key={i}>
                      <td><span className={`insignia ${h.gravedad === "error" ? "error" : "alerta"}`}>{h.gravedad === "error" ? "Error" : "Aviso"}</span></td>
                      <td>{h.afectado ? <Link to={h.afectado.enlace}>{h.afectado.titulo}</Link> : <span className="meta">Fondo</span>}</td>
                      <td>{h.problema}</td>
                      <td className="meta">{h.regla}</td>
                      <td>{h.accion}{h.enlace && (!h.afectado || h.enlace !== h.afectado.enlace) && <> <Link to={h.enlace}>Ir</Link></>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}
