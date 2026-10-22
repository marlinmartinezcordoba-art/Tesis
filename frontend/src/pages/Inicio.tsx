import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, pedir, puede, type Modulo } from "@/lib/api";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";

// Inicio guiado: dónde va el fondo activo en el recorrido archivístico y qué
// sigue. Cada paso dice su estado y lleva a la pantalla donde se hace.

interface Paso {
  clave: string; titulo: string; estado: "hecho" | "en_curso" | "pendiente"; resumen: string;
  accion: string | null; ruta: string | null; modulo: string;
}
interface Avance { fondo: { id: string; titulo: string }; pasos: Paso[]; siguiente: string | null; hechos: number; total: number }

const ESTADO: Record<Paso["estado"], { texto: string; clase: string }> = {
  hecho: { texto: "Hecho", clase: "hecho" },
  en_curso: { texto: "En curso", clase: "en-curso" },
  pendiente: { texto: "Pendiente", clase: "pendiente" },
};

function saludo(): string {
  const h = new Date().getHours();
  return h < 12 ? "Buenos días" : h < 19 ? "Buenas tardes" : "Buenas noches";
}

export function Inicio() {
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const [avance, setAvance] = useState<Avance | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!fondo) return;
    setAvance(null);
    pedir<Avance>(`/api/fondos/${fondo.id}/avance`).then(setAvance)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar el avance del fondo."));
  }, [fondo]);

  const nombre = usuario?.nombre.split(" ")[0] || "";
  const puedeIr = (p: Paso) => !!p.ruta && puede(usuario, p.modulo as Modulo);

  if (!fondo) {
    return (
      <div className="inicio">
        <h1>{saludo()}, {nombre}</h1>
        <div className="tarjeta inicio-bienvenida">
          <h2>Empecemos por el fondo</h2>
          <p>En RICORA todo nace de los instrumentos archivísticos: cargue el cuadro de clasificación (CCD) y la tabla de
            retención (TRD) y el sistema arma el fondo, sus dependencias, series y subseries.</p>
          {usuario?.es_administrador
            ? <Link className="boton primario" to="/fondos?vista=cargar">Cargar el CCD y la TRD</Link>
            : <p className="meta">Pídale a la administración que registre el primer fondo.</p>}
        </div>
      </div>
    );
  }

  const siguiente = avance?.pasos.find((p) => p.clave === avance.siguiente);
  return (
    <div className="inicio">
      <h1>{saludo()}, {nombre}</h1>
      <p className="sub">Fondo activo: <strong>{fondo.titulo}</strong>. Así va su recorrido archivístico.</p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!avance && !error && <div className="cargando">Cargando…</div>}
      {avance && (
        <>
          {siguiente && puedeIr(siguiente) && (
            <div className="tarjeta siguiente-paso">
              <div>
                <span className="etiqueta-siguiente">Siguiente paso recomendado</span>
                <h2>{siguiente.titulo}</h2>
                <p>{siguiente.resumen}</p>
              </div>
              <Link className="boton primario" to={siguiente.ruta!}>{siguiente.accion}</Link>
            </div>
          )}
          <div className="tarjeta">
            <div className="tarjeta-cab">
              <span>Recorrido del fondo</span>
              <span className="meta">{avance.hechos} de {avance.total} pasos al día</span>
            </div>
            <div className="barra-avance" role="progressbar" aria-valuemin={0} aria-valuemax={avance.total}
                 aria-valuenow={avance.hechos} aria-label="Pasos al día">
              <span style={{ width: `${(avance.hechos / avance.total) * 100}%` }} />
            </div>
            <ol className="recorrido">
              {avance.pasos.map((p, i) => (
                <li key={p.clave} className={`paso-recorrido ${ESTADO[p.estado].clase}${p.clave === avance.siguiente ? " es-siguiente" : ""}`}>
                  <span className="marca-paso" aria-hidden="true">{p.estado === "hecho" ? "✓" : i + 1}</span>
                  <div className="cuerpo-paso">
                    <div className="titulo-paso">{p.titulo} <span className={`insignia estado-${ESTADO[p.estado].clase}`}>{ESTADO[p.estado].texto}</span></div>
                    <div className="meta">{p.resumen}</div>
                  </div>
                  {puedeIr(p) && p.accion && <Link className="boton chico" to={p.ruta!}>{p.accion}</Link>}
                </li>
              ))}
            </ol>
          </div>
          <p className="meta consejo">Consejo: pulse <kbd>Ctrl</kbd> + <kbd>K</kbd> en cualquier pantalla para ir directo a
            lo que necesita.</p>
        </>
      )}
    </div>
  );
}
