import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, pedir, puede, type Modulo } from "@/lib/api";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";
import { Encabezado, Indicadores } from "@/components/Encabezado";

const I_DOC = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></svg>;
const I_OK = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.6 2.6L16 9.6" /></svg>;
const I_BARRAS = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M5 20V12M10 20V6M15 20v-9M20 20V4" /></svg>;
const I_CARPETA = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"><path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h4l2 2.2h7A2.5 2.5 0 0 1 21 9.7v7.8a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z" /></svg>;
interface Productividad { total_fondo: number; archivos_listos: number; archivos_descritos: number }

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
  const [cifras, setCifras] = useState<Productividad | null>(null);

  useEffect(() => {
    if (!fondo) return;
    setAvance(null);
    pedir<Avance>(`/api/fondos/${fondo.id}/avance`).then(setAvance)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar el avance del fondo."));
    if (puede(usuario, "descripcion")) {
      pedir<Productividad>(`/api/descripcion/productividad?fondo_id=${fondo.id}`).then(setCifras).catch(() => setCifras(null));
    }
  }, [fondo, usuario]);

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
      <Encabezado titulo={`${saludo()}, ${nombre}`} ceja={null}
                  descripcion="Gestione el archivo histórico y continúe con su recorrido archivístico." />
      {cifras && (
        <Indicadores etiqueta="Estado del fondo" items={[
          { etiqueta: "Por describir", valor: Math.max(0, cifras.archivos_listos - cifras.archivos_descritos).toLocaleString("es-CO"), icono: I_DOC },
          { etiqueta: "Descripciones publicadas", valor: cifras.total_fondo.toLocaleString("es-CO"), icono: I_OK, tono: "bien" },
          { etiqueta: "Archivos descritos", icono: I_BARRAS,
            valor: cifras.archivos_listos ? `${Math.round((cifras.archivos_descritos / cifras.archivos_listos) * 100)} %` : "—",
            nota: `${cifras.archivos_descritos.toLocaleString("es-CO")} de ${cifras.archivos_listos.toLocaleString("es-CO")}` },
        ]} />
      )}
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!avance && !error && <div className="cargando">Cargando…</div>}
      {avance && (
        <>
          {siguiente && puedeIr(siguiente) && (
            <div className="tarjeta siguiente-paso">
              <span className="icono-siguiente" aria-hidden="true">{I_CARPETA}</span>
              <div style={{ flex: 1 }}>
                <span className="etiqueta-siguiente">Siguiente paso recomendado</span>
                <h2>{siguiente.titulo}</h2>
                <p>{siguiente.resumen}</p>
              </div>
              <Link className="boton primario" to={siguiente.ruta!}>{siguiente.accion} →</Link>
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
                  {puedeIr(p) && p.accion && <Link className={`boton chico${p.clave === avance.siguiente ? " primario" : ""}`} to={p.ruta!}>{p.accion}</Link>}
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
