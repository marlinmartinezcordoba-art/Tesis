import { pedirTexto } from "@/lib/dialogos";
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
import { VentanaVisor } from "@/components/VisorDocumento";
import { Encabezado, IconoDocumento, Indicadores, MenuAcciones, type Accion } from "@/components/Encabezado";
import { NivelRiC } from "@/components/NivelRiC";

// «Descritas» muestra las más recientes; el resto, en la exportación.
const RECIENTES_DESCRITAS = 15;

// Cifras medidas del fondo para los indicadores (el mismo dato que cuenta el panel de auditoría).
interface Productividad { hoy_por_mi: number; total_fondo: number; archivos_listos: number; archivos_descritos: number }

function useProductividad(fondoId: string | undefined, version: number) {
  const [p, setP] = useState<Productividad | null>(null);
  useEffect(() => {
    if (!fondoId) return;
    pedir<Productividad>(`/api/descripcion/productividad?fondo_id=${fondoId}`).then(setP).catch(() => setP(null));
  }, [fondoId, version]);
  return p;
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
  trabajo_propio_id?: string | null;  // lo tiene abierto quien mira: puede continuar
  trabajo_id?: string | null;  // solo para la administración: puede liberarlo
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
  return p.length > 1 ? p.pop()!.slice(0, 4).toUpperCase() : "";
}

const FILTROS: [string, string][] = [["todos", "Todos"], ["libres", "Sin abrir"], ["edicion", "En edición"],
  ["ocr", "OCR con confianza baja"], ["sin_texto", "Sin texto"]];

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
  const [abriendo, setAbriendo] = useState<{ cantidad: number; nombre: string } | null>(null);
  const [error, setError] = useState("");
  const [busqueda, setBusqueda] = useState("");
  const [filtro, setFiltro] = useState("todos");
  const [viendo, setViendo] = useState<PorDescribir | null>(null);
  const [version, setVersion] = useState(0);
  const productividad = useProductividad(fondo?.id, version);
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
      setVersion((v) => v + 1);
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

  // Solo la administración elimina un documento cargado por error, y solo si nunca
  // se describió: el archivo se borra y queda constancia (quién, cuándo, por qué, huella).
  async function eliminar(d: PorDescribir) {
    const motivo = await pedirTexto(`«${d.nombre}» se borra de forma definitiva por haberse cargado por error. En la `
      + "auditoría quedan su nombre, su huella SHA-256, quién lo eliminó y por qué.",
    { titulo: "Eliminar un documento cargado por error", aceptar: "Eliminar definitivamente", minimo: 5 });
    if (!motivo || motivo.trim().length < 5) return;
    setError("");
    try {
      await pedir(`/api/ingesta/${d.id}/eliminar`, { method: "POST", body: JSON.stringify({ motivo: motivo.trim() }) });
      await cargar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo eliminar.");
    }
  }

  // La administración libera un documento que otra persona dejó abierto; su avance se conserva.
  async function liberar(d: PorDescribir) {
    const motivo = await pedirTexto(`«${d.nombre}» lo tiene abierto ${d.en_edicion_por}. Al liberarlo, otra persona puede `
      + "continuar la descripción desde donde iba (su avance se conserva), o retomarla quien la empezó. Queda constancia "
      + "en la auditoría.",
    { titulo: "Liberar un documento en edición", aceptar: "Liberar", minimo: 10 });
    if (!motivo) return;
    setError("");
    try {
      await pedir(`/api/descripcion/trabajos/${d.trabajo_id}/liberar`, { method: "POST", body: JSON.stringify({ motivo }) });
      await cargar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo liberar.");
    }
  }

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

      {pestana === "cola" ? (() => {
        const texto = busqueda.trim().toLowerCase();
        const visibles = (cola || []).filter((d) =>
          (!texto || d.nombre.toLowerCase().includes(texto) || (d.expediente || "").toLowerCase().includes(texto))
          && (filtro === "todos" || (filtro === "libres" && !d.en_edicion_por && !d.trabajo_propio_id)
            || (filtro === "edicion" && (!!d.en_edicion_por || !!d.trabajo_propio_id))
            || (filtro === "ocr" && d.ocr_baja_confianza) || (filtro === "sin_texto" && d.origen_texto === "sin_texto")));
        const siguiente = (cola || []).find((d) => !d.en_edicion_por && !d.trabajo_propio_id);
        const p = productividad;
        const avance = p && p.archivos_listos ? p.archivos_descritos / p.archivos_listos : null;
        const dudosos = (cola || []).filter((d) => d.ocr_baja_confianza).length;
        return (
          <>
            <Encabezado titulo="Descripción documental"
                        descripcion="Describa los documentos listos del fondo. El motor de análisis propone; usted valida, corrige o descarta cada dato." />
            <Indicadores etiqueta="Indicadores de la descripción" items={[
              { etiqueta: "Por describir", valor: cola === null ? "—" : cola.length.toLocaleString("es-CO"),
                nota: "Archivos listos, sin descripción" },
              { etiqueta: "Descripciones publicadas", valor: p ? p.total_fondo.toLocaleString("es-CO") : "—",
                nota: p ? `${p.hoy_por_mi} validadas hoy por usted` : undefined, tono: "bien" },
              { etiqueta: "Avance del fondo", valor: avance === null ? "—" : `${Math.round(avance * 100)} %`, avance,
                nota: p ? `${p.archivos_descritos.toLocaleString("es-CO")} de ${p.archivos_listos.toLocaleString("es-CO")} archivos descritos` : undefined },
              { etiqueta: "OCR con confianza baja", valor: cola === null ? "—" : dudosos.toLocaleString("es-CO"),
                nota: "Lea su texto con cuidado", tono: dudosos ? "alerta" : undefined },
            ]} />
            <div className="tarjeta">
              <div className="lista-titulo">
                <h2>Documentos pendientes</h2>
                {puede && siguiente && (
                  <button type="button" className="boton primario" disabled={!!abriendo} onClick={() => describir([siguiente.id])}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
                    Describir el siguiente</button>
                )}
              </div>
              <div className="herramientas">
                <label className="buscador">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
                  <input className="entrada" type="search" placeholder="Buscar por nombre o expediente…" aria-label="Buscar documentos pendientes"
                         value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />
                </label>
                <select className="selector" aria-label="Filtrar" value={filtro} onChange={(e) => setFiltro(e.target.value)}>
                  {FILTROS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
                </select>
              </div>
              {cola === null && <div className="vacio">Cargando…</div>}
              {cola !== null && cola.length === 0 && (
                <EstadoVacio icono="bien" titulo="No hay documentos por describir"
                             texto="Los que termina de procesar la ingesta aparecen aquí solos."
                             accion={tienePermiso(usuario, "ingesta", "escribir") ? { texto: "Cargar documentos", alHacer: () => navegar("/ingesta") } : undefined} />
              )}
              {cola !== null && cola.length > 0 && visibles.length === 0 && <div className="vacio">Ningún documento coincide con la búsqueda.</div>}
              {visibles.map((d) => {
                const secundarias: Accion[] = [{ texto: "Previsualizar", alHacer: () => setViendo(d) }];
                if (usuario?.es_administrador && d.en_edicion_por && d.trabajo_id) {
                  secundarias.push({ texto: "Liberar para otra persona", alHacer: () => liberar(d),
                    ayuda: "Si la persona no va a volver pronto. Su avance se conserva." });
                }
                if (usuario?.es_administrador && !d.en_edicion_por) {
                  secundarias.push({ texto: "Eliminar (cargado por error)", alHacer: () => eliminar(d), peligro: true,
                    ayuda: "Solo si se cargó por error y nunca se describió" });
                }
                const formato = extension(d.nombre);
                return (
                  <div className={`fila${resaltado === d.id ? " resaltada" : ""}`} key={d.id}>
                    {puede && (
                      <input type="checkbox" aria-label={`Seleccionar ${d.nombre}`} disabled={!!d.en_edicion_por}
                             checked={seleccion.includes(d.id)} onChange={() => alternar(d.id)} />
                    )}
                    <span className="icono-archivo" aria-hidden="true"><IconoDocumento /></span>
                    <div className="fila-principal">
                      <div className="nombre">{d.nombre}</div>
                      <div className="meta">
                        {d.expediente ? `Expediente ${d.expediente}` : "Sin expediente"}{formato && ` · ${formato}`} · {peso(d.tamano_bytes)}
                        {d.origen_texto && ` · ${TEXTO[d.origen_texto] || d.origen_texto}`}
                        {d.confianza_ocr !== null && ` ${confianzaTexto(d.confianza_ocr)}`} · cargado {fecha(d.cargado_en)}
                      </div>
                    </div>
                    {d.ocr_baja_confianza && <span className="insignia alerta" title="La transcripción automática es dudosa: léala con cuidado">OCR dudoso</span>}
                    {d.trabajo_propio_id ? <span className="insignia acento">En curso por usted</span>
                      : d.en_edicion_por ? <span className="insignia proceso">En edición por {d.en_edicion_por}</span>
                        : <span className="insignia pendiente">Pendiente</span>}
                    {d.trabajo_propio_id ? (
                      <button type="button" className="boton chico primario" title="Abre su trabajo con el avance guardado"
                              onClick={() => navegar(`/descripcion/trabajo/${d.trabajo_propio_id}`)}>Continuar</button>
                    ) : !d.en_edicion_por && puede && (
                      <button type="button" className="boton chico" disabled={!!abriendo} onClick={() => describir([d.id])}>Describir</button>
                    )}
                    <MenuAcciones etiqueta={`Más acciones para ${d.nombre}`} acciones={secundarias} />
                  </div>
                );
              })}
              {puede && seleccion.length > 1 && (
                <div className="confirmar">
                  <span>{seleccion.length} documentos seleccionados</span>
                  <div className="acciones" style={{ alignItems: "center" }}>
                    <span className="pista" style={{ margin: 0 }}>Se describen como un expediente de su serie (las series
                      salen de la TRD)</span>
                    <button type="button" className="boton primario" disabled={!!abriendo} onClick={() => describir(seleccion, "expediente")}>
                      {abriendo ? "Abriendo…" : "Describir como expediente"}
                    </button>
                  </div>
                </div>
              )}
            </div>
            {viendo && <VentanaVisor base={`/api/descripcion/${viendo.id}/previsualizar`} titulo={viendo.nombre} cerrar={() => setViendo(null)} />}
          </>
        );
      })() : (
        <>
          <Encabezado titulo="Descripciones publicadas"
                      descripcion="Las más recientes primero. Se pueden reabrir para corregirlas; cada cambio queda en la auditoría." />
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
                    {NIVEL_NOMBRE[p.nivel] || p.nivel} <NivelRiC nivel={p.nivel} /> · {p.documentos} documento{p.documentos === 1 ? "" : "s"} · publicada {fecha(p.publicado_en)}
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
