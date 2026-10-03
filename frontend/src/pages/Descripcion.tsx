import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ErrorAPI, pedir, puede as tienePermiso } from "@/lib/api";
import { NIVEL_NOMBRE } from "@/lib/descripcion";
import { useFondo } from "@/lib/fondo";
import { confianzaTexto, fecha, peso } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";
import { useVista } from "@/components/Marco";
import { EstadoVacio } from "@/components/EstadoVacio";
import { AvisoReciente, ExportarExcel } from "@/components/HistorialReciente";
import { BotonPrevisualizar } from "@/components/VisorDocumento";

// «Descritas» muestra las más recientes; el resto, en la exportación.
const RECIENTES_DESCRITAS = 15;

// Bajo una cola corta: lo descrito hoy y el total del fondo, el mismo dato
// que cuenta el panel consolidado de auditoría (no un cálculo aparte).
function Productividad({ fondoId }: { fondoId: string }) {
  const [p, setP] = useState<{ hoy_por_mi: number; total_fondo: number } | null>(null);
  useEffect(() => {
    pedir<{ hoy_por_mi: number; total_fondo: number }>(`/api/descripcion/productividad?fondo_id=${fondoId}`).then(setP).catch(() => setP(null));
  }, [fondoId]);
  if (!p) return null;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Su trabajo reciente</div>
      <div className="resumen-preservacion compacto">
        <div className="cifra"><strong>{p.hoy_por_mi}</strong><span>Descripciones que usted validó hoy (publicadas, corregidas o recortadas)</span></div>
        <div className="cifra bien"><strong>{p.total_fondo}</strong><span>Descripciones publicadas en el fondo</span></div>
      </div>
    </div>
  );
}

interface PorDescribir {
  id: string;
  nombre: string;
  tamano_bytes: number;
  formato: string | null;
  expediente: string | null;
  origen_texto: string | null;
  confianza_ocr: number | null;
  ocr_baja_confianza: boolean;
  cargado_en: string;
  en_edicion_por: string | null;
}

interface Publicada {
  id: string;
  titulo: string;
  nivel: string;
  documentos: number;
  publicado_en: string | null;
  actualizado_en: string | null;
  en_edicion_por: string | null;
}

const TEXTO: Record<string, string> = { capa_de_texto: "con texto", ocr: "texto por OCR", sin_texto: "sin texto" };

function extension(nombre: string) {
  const p = nombre.split(".");
  return p.length > 1 ? p.pop()!.slice(0, 4) : "·";
}

// Mientras el motor de análisis lee el documento (puede tardar hasta 90 s, el
// límite del servidor): qué está pasando y cuánto lleva, en lugar de una
// pantalla quieta. Los pasos son los del servidor, en su orden; la petición
// es una sola, así que el paso se deduce del tiempo y se dice así.
const LIMITE_MOTOR_S = 90;

function EsperaMotor({ cantidad, nombre }: { cantidad: number; nombre: string }) {
  const [segundos, setSegundos] = useState(0);
  useEffect(() => {
    const inicio = Date.now();
    const t = setInterval(() => setSegundos(Math.floor((Date.now() - inicio) / 1000)), 500);
    return () => clearInterval(t);
  }, []);
  const pasos = [
    "Reservar el documento para usted (nadie más puede editarlo mientras tanto)",
    "Buscar en el vocabulario del fondo las entidades que ya existen",
    "El motor de análisis lee el texto y propone agentes, fechas, lugares, actividades y relaciones",
  ];
  const actual = segundos < 1 ? 0 : segundos < 2 ? 1 : 2;
  return (
    <div className="espera-fondo" role="dialog" aria-modal="true" aria-labelledby="espera-titulo">
      <div className="espera-tarjeta" role="status" aria-live="polite">
        <h2 id="espera-titulo">Preparando la descripción</h2>
        <p className="meta">{cantidad > 1 ? `${cantidad} documentos` : `«${nombre}»`}</p>
        <div className="barra-indeterminada" aria-hidden="true"><i /></div>
        <ol className="espera-pasos">
          {pasos.map((p, i) => (
            <li key={p} className={i < actual ? "hecho" : i === actual ? "actual" : ""}>{p}</li>
          ))}
        </ol>
        <p className="meta">Lleva {segundos} s. El motor suele tardar entre 10 y 40 segundos.</p>
        {segundos >= 45 && (
          <p className="pista">Está tardando más de lo normal. Si llega a {LIMITE_MOTOR_S} s sin respuesta, el documento se
            abre igual, sin propuesta, para describirlo a mano.</p>
        )}
      </div>
    </div>
  );
}

export function Descripcion() {
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const navegar = useNavigate();
  const ubicacion = useLocation();
  const puede = tienePermiso(usuario, "descripcion", "escribir");
  const pestana = useVista<"cola" | "publicadas">("/descripcion");
  const [cola, setCola] = useState<PorDescribir[] | null>(null);
  const [publicadas, setPublicadas] = useState<Publicada[] | null>(null);
  const [seleccion, setSeleccion] = useState<string[]>([]);
  const [nivel, setNivel] = useState("expediente");
  const [abriendo, setAbriendo] = useState<{ cantidad: number; nombre: string } | null>(null);
  const [error, setError] = useState("");
  const aviso = (ubicacion.state as { aviso?: string } | null)?.aviso;
  // Desde el panel de alertas se llega con ?documento=<id>: esa fila se resalta.
  const resaltado = new URLSearchParams(ubicacion.search).get("documento");

  const cargar = useCallback(async () => {
    if (!fondo) return;
    try {
      const [c, p] = await Promise.all([
        pedir<PorDescribir[]>(`/api/descripcion/cola?fondo_id=${fondo.id}`),
        pedir<Publicada[]>(`/api/descripcion/publicadas?fondo_id=${fondo.id}`),
      ]);
      setCola(c);
      setPublicadas(p);
      setSeleccion((s) => s.filter((id) => c.some((x) => x.id === id && !x.en_edicion_por)));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar la cola.");
    }
  }, [fondo]);

  useEffect(() => {
    cargar();
    const t = setInterval(cargar, 30000);
    return () => clearInterval(t);
  }, [cargar]);

  async function describir(ids: string[], nivelConjunto?: string) {
    setError("");
    setAbriendo({ cantidad: ids.length, nombre: cola?.find((d) => d.id === ids[0])?.nombre || "" });
    try {
      const espacio = await pedir<{ trabajo_id: string }>("/api/descripcion/iniciar", {
        method: "POST",
        body: JSON.stringify({ instanciacion_ids: ids, ...(nivelConjunto ? { nivel: nivelConjunto } : {}) }),
      });
      navegar(`/descripcion/trabajo/${espacio.trabajo_id}`, { state: { espacio } });
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo abrir la descripción.");
      setAbriendo(null);
      cargar();
    }
  }

  if (!fondo) return <div className="vacio">Primero debe existir un fondo (se registra en Ingesta).</div>;

  const alternar = (id: string) => setSeleccion((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <>
      {abriendo && <EsperaMotor cantidad={abriendo.cantidad} nombre={abriendo.nombre} />}
      {aviso && <div className="aviso bien" role="status">{aviso}</div>}
      {error && <div className="aviso error" role="alert">{error}</div>}

      {pestana === "cola" ? (
        <>
          <h1>Por describir</h1>
          <p className="sub">
            Documentos que ya salieron de ingesta y están listos. Abra uno para describirlo solo, o seleccione varios para
            describirlos como conjunto a nivel de expediente, subserie o serie.
          </p>
          <div className="tarjeta">
            <div className="tarjeta-cab">
              {cola === null ? "Cargando…" : `${cola.length} documento${cola.length === 1 ? "" : "s"} listo${cola.length === 1 ? "" : "s"}`}
            </div>
            {cola !== null && cola.length === 0 && (
              <EstadoVacio icono="bien" titulo="No hay documentos por describir"
                           texto="Los que termina de procesar la ingesta aparecen aquí solos."
                           accion={tienePermiso(usuario, "ingesta", "escribir") ? { texto: "Cargar documentos", alHacer: () => navegar("/ingesta") } : undefined} />
            )}
            {cola?.map((d) => (
              <div className={`fila${resaltado === d.id ? " resaltada" : ""}`} key={d.id}>
                {puede && (
                  <input type="checkbox" aria-label={`Seleccionar ${d.nombre}`} disabled={!!d.en_edicion_por}
                         checked={seleccion.includes(d.id)} onChange={() => alternar(d.id)} />
                )}
                <span className="icono-archivo" aria-hidden="true">{extension(d.nombre)}</span>
                <div className="fila-principal">
                  <div className="nombre">{d.nombre}</div>
                  <div className="meta">
                    {d.expediente ? `Expediente: ${d.expediente}` : "Sin expediente asignado"} · {peso(d.tamano_bytes)}
                    {d.origen_texto && ` · ${TEXTO[d.origen_texto] || d.origen_texto}`}
                    {d.confianza_ocr !== null && ` (confianza ${confianzaTexto(d.confianza_ocr)})`} · cargado {fecha(d.cargado_en)}
                  </div>
                </div>
                {d.ocr_baja_confianza && <span className="insignia alerta" title="La transcripción automática es dudosa: léala con cuidado">OCR con confianza baja</span>}
                <BotonPrevisualizar base={`/api/descripcion/${d.id}/previsualizar`} nombre={d.nombre} />
                {d.en_edicion_por ? (
                  <span className="insignia proceso">En edición por {d.en_edicion_por}</span>
                ) : puede && (
                  <button type="button" className="boton chico" disabled={!!abriendo} onClick={() => describir([d.id])}>Describir</button>
                )}
              </div>
            ))}
            {puede && seleccion.length > 1 && (
              <div className="confirmar">
                <span>{seleccion.length} documentos seleccionados</span>
                <div className="acciones" style={{ alignItems: "center" }}>
                  <label className="pista" style={{ margin: 0 }} htmlFor="nivel-conjunto">Son un</label>
                  <select id="nivel-conjunto" className="selector" style={{ width: "auto" }} value={nivel} onChange={(e) => setNivel(e.target.value)}>
                    <option value="expediente">Expediente</option>
                    <option value="subserie">Subserie</option>
                    <option value="serie">Serie</option>
                  </select>
                  <button type="button" className="boton primario" disabled={!!abriendo} onClick={() => describir(seleccion, nivel)}>
                    {abriendo ? "Abriendo…" : "Describir como conjunto"}
                  </button>
                </div>
              </div>
            )}
          </div>
          {fondo && cola !== null && cola.length < 5 && <Productividad fondoId={fondo.id} />}
        </>
      ) : (
        <>
          <h1>Descritas</h1>
          <p className="sub">Descripciones ya publicadas en el fondo, las más recientes primero. Se pueden reabrir para corregirlas;
            cada cambio queda en auditoría.</p>
          {fondo && publicadas && publicadas.length > RECIENTES_DESCRITAS && (
            <div className="filtros"><ExportarExcel ruta={`/api/descripcion/publicadas/exportar?fondo_id=${fondo.id}`} /></div>
          )}
          <AvisoReciente visibles={RECIENTES_DESCRITAS} total={publicadas?.length ?? null} unidad="descripciones" />
          <div className="tarjeta">
            {publicadas === null ? <div className="vacio">Cargando…</div> : publicadas.length === 0 ? (
              <EstadoVacio icono="documento" titulo="Todavía no se ha publicado ninguna descripción"
                           texto="Cuando publique la primera desde «Por describir», aparecerá aquí."
                           accion={{ texto: "Ir a Por describir", alHacer: () => navegar("/descripcion") }} />
            ) : publicadas.slice(0, RECIENTES_DESCRITAS).map((p) => (
              <div className="fila" key={p.id}>
                <div className="fila-principal">
                  <div className="nombre">{p.titulo}</div>
                  <div className="meta">
                    {NIVEL_NOMBRE[p.nivel] || p.nivel} · {p.documentos} documento{p.documentos === 1 ? "" : "s"} · publicada {fecha(p.publicado_en)}
                    {p.actualizado_en && ` · corregida ${fecha(p.actualizado_en)}`}
                  </div>
                </div>
                {p.en_edicion_por && <span className="insignia proceso">En edición por {p.en_edicion_por}</span>}
                <button type="button" className="boton chico" onClick={() => navegar(`/descripcion/registro/${p.id}`)}>
                  {puede ? "Ver y corregir" : "Ver"}
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
