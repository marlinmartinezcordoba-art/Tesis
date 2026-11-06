import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, pedir, puede, type Modulo } from "@/lib/api";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";
import { Indicadores } from "@/components/Encabezado";
import { PanelAsistente } from "@/components/Asistente";
import { fecha as fechaHora } from "@/lib/formato";
import type { Evento } from "@/lib/auditoria";

const I_DOC = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></svg>;
const I_OK = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.6 2.6L16 9.6" /></svg>;
const I_BARRAS = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M5 20V12M10 20V6M15 20v-9M20 20V4" /></svg>;
const I_CAPAS = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"><path d="M12 3l9 5-9 5-9-5z" /><path d="M3 13l9 5 9-5" /></svg>;
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
      <div className="inicio inicio-sin-fondo">
        <section className="inicio-hero">
          <div className="hero-texto">
            <span className="hero-saludo">{saludo()},</span>
            <h1 className="titulo-entidad">{nombre || "bienvenida"}</h1>
            <p>Empecemos por el fondo. Elija el instrumento con el que la institución organizó sus documentos.</p>
          </div>
          <Paisaje />
        </section>
        <div className="opciones-inicio">
          <div className="tarjeta opcion-inicio">
            <span className="opcion-icono electrico" aria-hidden="true">{I_CARPETA}</span>
            <h2>Con tabla de retención (TRD)</h2>
            <p>Para los documentos producidos con TRD. Cargue el cuadro de clasificación (CCD) y la TRD: el sistema arma el
              fondo, sus dependencias, series y subseries, con su retención y su disposición final.</p>
            {usuario?.es_administrador
              ? <Link className="boton primario" to="/fondos?vista=cargar">Cargar el CCD y la TRD</Link>
              : <p className="meta">Pídale a la administración que registre el primer fondo.</p>}
          </div>
          <div className="tarjeta opcion-inicio">
            <span className="opcion-icono violeta" aria-hidden="true">{I_CAPAS}</span>
            <h2>Fondo acumulado (TVD)</h2>
            <p>Para los documentos producidos sin TRD. Registre el fondo con su cuadro de clasificación y después cargue la
              tabla de valoración (TVD) de cada periodo institucional en Instrumentos → TVD.</p>
            {usuario?.es_administrador
              ? <Link className="boton" to="/fondos?vista=cargar">Registrar el fondo acumulado</Link>
              : <p className="meta">Pídale a la administración que registre el primer fondo.</p>}
          </div>
        </div>
      </div>
    );
  }

  const siguiente = avance?.pasos.find((p) => p.clave === avance.siguiente);
  const pendientes = cifras ? Math.max(0, cifras.archivos_listos - cifras.archivos_descritos) : 0;
  const proporcion = cifras?.archivos_listos ? cifras.archivos_descritos / cifras.archivos_listos : 0;
  const hoy = new Date().toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });
  return (
    <div className="inicio inicio-tablero">
      <section className="inicio-hero">
        <div className="hero-texto">
          <span className="hero-saludo">{saludo()},</span>
          <h1 className="titulo-entidad">{nombre || "bienvenida"}</h1>
          <p>Gestione el archivo histórico, los instrumentos archivísticos y la descripción documental de forma integral.</p>
          <span className="hero-fecha">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M9 3v4M15 3v4" /></svg>
            {hoy}</span>
        </div>
        <Paisaje />
      </section>

      <div className="inicio-rejilla">
        <div className="inicio-principal">
          {cifras && (
            <Indicadores etiqueta="Estado del fondo" items={[
              { etiqueta: "Por describir", valor: pendientes.toLocaleString("es-CO"), icono: I_DOC },
              { etiqueta: "Descripciones publicadas", valor: cifras.total_fondo.toLocaleString("es-CO"), icono: I_OK },
              { etiqueta: "Avance de descripción", icono: I_BARRAS, avance: proporcion,
                valor: cifras.archivos_listos ? `${Math.round(proporcion * 100)} %` : "—",
                nota: `${cifras.archivos_descritos.toLocaleString("es-CO")} de ${cifras.archivos_listos.toLocaleString("es-CO")}` },
              { etiqueta: "Documentos cargados", valor: cifras.archivos_listos.toLocaleString("es-CO"), icono: I_CAPAS },
            ]} />
          )}
          {error && <div className="aviso error" role="alert">{error}</div>}
          {!avance && !error && <div className="cargando">Cargando…</div>}
          {avance && siguiente && puedeIr(siguiente) && (
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
          {avance && (
            <div className="tarjeta">
              <div className="tarjeta-cab">
                <span>Recorrido del fondo</span>
                <span className="meta">{avance.hechos} de {avance.total} pasos al día</span>
              </div>
              <ol className="recorrido-horizontal">
                {avance.pasos.map((p, i) => (
                  <li key={p.clave} className={`${ESTADO[p.estado].clase}${p.clave === avance.siguiente ? " es-siguiente" : ""}`}>
                    <span className="marca-paso" aria-hidden="true">{p.estado === "hecho" ? "✓" : i + 1}</span>
                    <strong>{p.titulo}</strong>
                    <span className={`insignia estado-${ESTADO[p.estado].clase}`}>{ESTADO[p.estado].texto}</span>
                    <span className="meta">{p.resumen}</span>
                    {puedeIr(p) && p.accion && <Link className={`boton chico${p.clave === avance.siguiente ? " primario" : ""}`} to={p.ruta!}>{p.accion}</Link>}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>

        <aside className="inicio-lateral">
          <div className="tarjeta tarjeta-asistente"><PanelAsistente /></div>
          {cifras && cifras.archivos_listos > 0 && (
            <div className="tarjeta">
              <div className="tarjeta-cab"><span>Avance general del fondo</span></div>
              <div className="tarjeta-cuerpo avance-general">
                <Dona proporcion={proporcion} />
                <ul>
                  <li><i className="punto descritos" />Descritos <b>{cifras.archivos_descritos.toLocaleString("es-CO")}</b></li>
                  <li><i className="punto pendientes" />Pendientes <b>{pendientes.toLocaleString("es-CO")}</b></li>
                  <li><i className="punto total" />Total de archivos <b>{cifras.archivos_listos.toLocaleString("es-CO")}</b></li>
                </ul>
              </div>
            </div>
          )}
          <ActividadReciente />
        </aside>
      </div>
    </div>
  );
}

/** Dibujo de la portada: montañas y ondas en la paleta de RICORA (SVG propio, sin imágenes externas). */
function Paisaje() {
  return (
    <svg className="hero-paisaje" viewBox="0 0 600 260" preserveAspectRatio="xMaxYMid slice" aria-hidden="true">
      <defs>
        <linearGradient id="cielo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#16c6c1" stopOpacity=".35" /><stop offset="1" stopColor="#8555e8" stopOpacity=".55" />
        </linearGradient>
        <linearGradient id="monte1" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#147dce" stopOpacity=".9" /><stop offset="1" stopColor="#091b43" stopOpacity=".2" />
        </linearGradient>
        <linearGradient id="monte2" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#16c6c1" stopOpacity=".85" /><stop offset="1" stopColor="#147dce" stopOpacity=".1" />
        </linearGradient>
      </defs>
      <circle cx="470" cy="70" r="120" fill="url(#cielo)" />
      <circle cx="455" cy="62" r="26" fill="#ffffff" opacity=".85" />
      <path d="M120 260 L260 120 L330 180 L420 80 L520 170 L600 110 L600 260 Z" fill="url(#monte1)" />
      <path d="M200 260 L330 170 L400 210 L500 140 L600 200 L600 260 Z" fill="url(#monte2)" />
      <path d="M0 230 C120 200 220 250 330 222 S520 190 600 215 L600 260 L0 260 Z" fill="#ffffff" opacity=".12" />
      <path d="M0 246 C140 220 260 262 380 238 S540 214 600 232" fill="none" stroke="#16c6c1" strokeWidth="2" opacity=".7" />
      <path d="M352 96 q8 -8 16 0 q8 -8 16 0" fill="none" stroke="#ffffff" strokeWidth="2.2" strokeLinecap="round" opacity=".9" />
      <path d="M392 120 q6 -6 12 0 q6 -6 12 0" fill="none" stroke="#ffffff" strokeWidth="1.8" strokeLinecap="round" opacity=".7" />
    </svg>
  );
}

function Dona({ proporcion }: { proporcion: number }) {
  const r = 52, c = 2 * Math.PI * r;
  return (
    <div className="dona" role="img" aria-label={`Avance ${Math.round(proporcion * 100)} %`}>
      <svg viewBox="0 0 130 130">
        <defs><linearGradient id="anillo" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#147dce" /><stop offset="1" stopColor="#8555e8" /></linearGradient></defs>
        <circle cx="65" cy="65" r={r} fill="none" stroke="var(--hielo)" strokeWidth="14" />
        <circle cx="65" cy="65" r={r} fill="none" stroke="url(#anillo)" strokeWidth="14" strokeLinecap="round"
                strokeDasharray={`${c * Math.max(0, Math.min(1, proporcion))} ${c}`} transform="rotate(-90 65 65)" />
      </svg>
      <span><b>{Math.round(proporcion * 100)} %</b>Avance</span>
    </div>
  );
}

function ActividadReciente() {
  const { usuario } = useSesion();
  const [eventos, setEventos] = useState<Evento[] | null>(null);
  const todos = !!usuario?.es_administrador;
  useEffect(() => {
    if (!puede(usuario, "auditoria")) return;
    const pedido = todos
      ? pedir<{ eventos: Evento[] }>("/api/auditoria/registro?por_pagina=5")
      : pedir<{ eventos: Evento[] }>("/api/auditoria/mi-trazabilidad?limite=5");
    pedido.then((r) => setEventos(r.eventos.slice(0, 5))).catch(() => setEventos(null));
  }, [usuario, todos]);
  if (!eventos || eventos.length === 0) return null;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab"><span>Actividad reciente</span><Link to="/auditoria" className="meta">Ver todas →</Link></div>
      <ul className="actividad-reciente">
        {eventos.map((e) => (
          <li key={e.id}>
            <span className="punto-actividad" aria-hidden="true" />
            <div><strong>{e.etiqueta}</strong><span className="meta">{e.usuario || "Sistema"} · {fechaHora(e.fecha)}</span></div>
          </li>
        ))}
      </ul>
    </div>
  );
}
