import { useEffect, useMemo, useRef, useState, type PointerEvent as EventoPuntero, type ReactNode } from "react";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, type SimulationNodeDatum } from "d3-force";

export type Familia =
  | "RecordSet" | "Record" | "RecordPart" | "Agent" | "Place" | "Activity" | "Date" | "Instantiation"
  | "DocumentaryFormType" | "ActivityType" | "Mandate" | "Event";

export interface NodoGrafo {
  clave: string;
  id: string;
  tipo: string;
  clase: string;
  familia: Familia;
  etiqueta: string;
  subtitulo: string | null;
  estado: string | null;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  salto: number;
  documentos?: number;
}

export interface AristaGrafo {
  desde: string;
  hacia: string;
  codigo_ric: string;
  uri_rico: string | null;
  etiqueta: string;
  dirigida: boolean;
}

export interface DatosGrafo {
  fondo: { id: string; titulo: string };
  centro: string;
  saltos: number;
  nodos: NodoGrafo[];
  aristas: AristaGrafo[];
  truncado: boolean;
  maximo_nodos: number;
  filtros_activos: number;
}

const trazo = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

// Iconos de trazo delgado, del mismo estilo que los de la barra lateral.
// El color nunca es la única señal: icono y etiqueta de texto dicen lo mismo.
export const ICONO_FAMILIA: Record<Familia, ReactNode> = {
  RecordSet: <g {...trazo}><path d="M8 4h8l3 3v10H8z" /><path d="M5 7v13h11" /></g>,
  Record: <g {...trazo}><path d="M6 3h12v18H6z" /><path d="M9 8h6M9 12h6M9 16h4" /></g>,
  RecordPart: <g {...trazo}><path d="M6 3h12v18H6z" /><path d="M9 13h6v5H9z" /></g>,
  Agent: <g {...trazo}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="10" r="3" /><path d="M6.6 18.4c1.3-2.3 3.2-3.4 5.4-3.4s4.1 1.1 5.4 3.4" /></g>,
  Place: <g {...trazo}><path d="M12 21s-6-5.8-6-11a6 6 0 0 1 12 0c0 5.2-6 11-6 11z" /><circle cx="12" cy="10" r="2.2" /></g>,
  Activity: <g {...trazo}><circle cx="12" cy="12" r="3" /><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" /></g>,
  Date: <g {...trazo}><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M8 3v4M16 3v4" /></g>,
  Instantiation: <g {...trazo}><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4" /></g>,
  DocumentaryFormType: <g {...trazo}><path d="M3.5 12.5l9-9H20v7.5l-9 9z" /><circle cx="16" cy="8" r="1.4" /></g>,
  ActivityType: <g {...trazo}><path d="M5 4h6v6H5zM13 14h6v6h-6z" /><path d="M8 10v7h5" /></g>,
  Event: <g {...trazo}><path d="M12 3l2.6 5.5 6 .8-4.4 4.2 1.1 6L12 16.6 6.7 19.5l1.1-6L3.4 9.3l6-.8z" /></g>,
  Mandate: <g {...trazo}><path d="M12 4v16M8 20h8M5 7h14" /><path d="M5 7l-2.5 6h5zM19 7l-2.5 6h5z" /></g>,
};

// Los siete tipos de la leyenda principal y los demás tipos RiC que el
// sistema ya modela (aparecen en la leyenda solo si están en pantalla).
export const FAMILIAS: { clave: Familia; nombre: string; ric: string; principal: boolean }[] = [
  { clave: "RecordSet", nombre: "Agrupación documental", ric: "Record Set", principal: true },
  { clave: "Record", nombre: "Documento", ric: "Record", principal: true },
  { clave: "Agent", nombre: "Agente", ric: "Agent", principal: true },
  { clave: "Place", nombre: "Lugar", ric: "Place", principal: true },
  { clave: "Activity", nombre: "Actividad", ric: "Activity", principal: true },
  { clave: "Date", nombre: "Fecha", ric: "Date", principal: true },
  { clave: "Instantiation", nombre: "Archivo", ric: "Instantiation", principal: true },
  { clave: "RecordPart", nombre: "Parte documental", ric: "Record Part", principal: false },
  { clave: "DocumentaryFormType", nombre: "Forma documental", ric: "Documentary Form Type", principal: false },
  { clave: "ActivityType", nombre: "Tipo de actividad", ric: "Activity Type", principal: false },
  { clave: "Mandate", nombre: "Mandato o norma", ric: "Mandate", principal: false },
  { clave: "Event", nombre: "Hito institucional", ric: "Event", principal: false },
];
export const NOMBRE_FAMILIA = Object.fromEntries(FAMILIAS.map((f) => [f.clave, f.nombre])) as Record<Familia, string>;

export function MuestraFamilia({ familia, tamano = 18 }: { familia: Familia; tamano?: number }) {
  return (
    <svg className={`muestra-familia f-${familia}`} width={tamano} height={tamano} viewBox="-12 -12 24 24" aria-hidden="true">
      <circle r="12" />
      <g transform="translate(-7.2 -7.2) scale(.6)" className="icono-nodo">{ICONO_FAMILIA[familia]}</g>
    </svg>
  );
}

function radio(n: NodoGrafo, raiz: boolean): number {
  if (raiz) return 27;
  switch (n.familia) {
    case "RecordSet": return n.clase === "fondo" ? 22 : 18;
    case "Record": return 15;
    case "RecordPart": return 12;
    case "Date": return 12;
    case "Instantiation": return 13;
    default: return 13 + Math.min(8, Math.sqrt(n.documentos || 1) * 2);
  }
}

function corto(texto: string, n = 26): string {
  return texto.length > n ? `${texto.slice(0, n - 1)}…` : texto;
}

type Punto = SimulationNodeDatum & { clave: string };

export function LienzoGrafo({ datos: completo, seleccion, alSeleccionar, enfoque, alArrastrar }: {
  datos: DatosGrafo;
  seleccion: string | null;
  alSeleccionar: (clave: string | null) => void;
  // Avisa cuando se arrastra el lienzo, para que la pantalla aparte barras y paneles.
  alArrastrar?: (activo: boolean) => void;
  // Nodo que la búsqueda pide centrar (el número cambia en cada búsqueda).
  enfoque: { clave: string; vez: number } | null;
}) {
  const lienzo = useRef<SVGSVGElement>(null);
  // Leyenda interactiva: cada tipo de entidad se muestra u oculta con un toque.
  // Lo oculto desaparece del dibujo con sus relaciones; la raíz nunca se oculta.
  const [ocultas, setOcultas] = useState<Set<Familia>>(new Set());
  const datos = useMemo<DatosGrafo>(() => {
    if (!ocultas.size) return completo;
    const nodos = completo.nodos.filter((n) => !ocultas.has(n.familia) || n.clave === completo.centro);
    const quedan = new Set(nodos.map((n) => n.clave));
    return { ...completo, nodos, aristas: completo.aristas.filter((a) => quedan.has(a.desde) && quedan.has(a.hacia)) };
  }, [completo, ocultas]);
  const alternarFamilia = (f: Familia) => setOcultas((o) => {
    const n = new Set(o);
    if (n.has(f)) n.delete(f);
    else n.add(f);
    return n;
  });
  const [posiciones, setPosiciones] = useState<Record<string, { x: number; y: number }>>({});
  const [vista, setVista] = useState({ x: 0, y: 0, k: 1 });
  const [encima, setEncima] = useState<string | null>(null);
  const [paneando, setPaneando] = useState(false);
  const [tamano, setTamano] = useState({ ancho: 800, alto: 560 });
  const puntos = useRef<Map<string, Punto>>(new Map());
  const simulacion = useRef<ReturnType<typeof forceSimulation<Punto>> | null>(null);
  const arrastre = useRef<{ tipo: "fondo" | "nodo"; clave?: string; x: number; y: number; movido: boolean } | null>(null);
  const tamanoRef = useRef({ ancho: 800, alto: 560 });

  function encuadrar() {
    const lista = [...puntos.current.values()];
    if (!lista.length) return;
    const xs = lista.map((p) => p.x || 0);
    const ys = lista.map((p) => p.y || 0);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const { ancho, alto } = tamanoRef.current;
    const k = Math.min(1.4, Math.max(0.2, Math.min(ancho / (x1 - x0 + 180), alto / (y1 - y0 + 140))));
    setVista({ k, x: -((x0 + x1) / 2) * k, y: -((y0 + y1) / 2) * k });
  }

  const porClave = useMemo(() => new Map(datos.nodos.map((n) => [n.clave, n])), [datos]);

  // Disposición por fuerzas: los nodos se repelen y las relaciones actúan
  // como resortes. Los nodos que ya estaban conservan su lugar, así un
  // cambio de filtro o de saltos es una transición y no un parpadeo.
  useEffect(() => {
    const anteriores = puntos.current;
    const nodos: Punto[] = datos.nodos.map((n) => {
      const p = anteriores.get(n.clave);
      return { clave: n.clave, x: p?.x ?? (Math.random() - 0.5) * 240, y: p?.y ?? (Math.random() - 0.5) * 240 };
    });
    const centro = nodos.find((n) => n.clave === datos.centro);
    if (centro) {
      centro.fx = 0;
      centro.fy = 0;
    }
    puntos.current = new Map(nodos.map((n) => [n.clave, n]));
    const grado = new Map<string, number>();
    for (const a of datos.aristas) for (const c of [a.desde, a.hacia]) grado.set(c, (grado.get(c) || 0) + 1);
    // Cuanto más relaciones comparten los extremos, más corto el resorte: los
    // grupos muy relacionados quedan juntos sin acomodarlos a mano.
    const enlaces = datos.aristas.map((a) => ({
      source: a.desde, target: a.hacia,
      largo: 100 + 60 / Math.sqrt(Math.min(grado.get(a.desde) || 1, grado.get(a.hacia) || 1)),
    }));
    let cuadro = 0;
    const sim = forceSimulation<Punto>(nodos)
      .force("enlaces", forceLink<Punto, { source: string; target: string; largo: number }>(enlaces).id((n) => n.clave)
        .distance((l) => l.largo))
      .force("carga", forceManyBody().strength(-380))
      .force("choque", forceCollide<Punto>().radius((n) => radio(porClave.get(n.clave)!, n.clave === datos.centro) + 24))
      .force("centro", forceCenter(0, 0).strength(0.04))
      .alpha(anteriores.size ? 0.6 : 1)
      .on("end", () => encuadrar())
      .on("tick", () => {
        if (cuadro) return;
        cuadro = requestAnimationFrame(() => {
          cuadro = 0;
          setPosiciones(Object.fromEntries(nodos.map((n) => [n.clave, { x: n.x || 0, y: n.y || 0 }])));
        });
      });
    simulacion.current = sim;
    if (!anteriores.size) setVista({ x: 0, y: 0, k: datos.nodos.length > 40 ? 0.6 : 1 });
    const primerEncuadre = window.setTimeout(encuadrar, 900);
    return () => {
      sim.stop();
      window.clearTimeout(primerEncuadre);
      cancelAnimationFrame(cuadro);
    };
  }, [datos, porClave]);

  // La búsqueda centra el nodo encontrado sin tocar los filtros.
  useEffect(() => {
    if (!enfoque) return;
    const p = puntos.current.get(enfoque.clave);
    if (!p) return;
    setVista((v) => {
      const k = Math.max(v.k, 1);
      return { k, x: -(p.x || 0) * k, y: -(p.y || 0) * k };
    });
  }, [enfoque]);

  useEffect(() => {
    const el = lienzo.current;
    if (!el) return;
    const medir = () => {
      tamanoRef.current = { ancho: el.clientWidth || 800, alto: el.clientHeight || 560 };
      setTamano(tamanoRef.current);
    };
    medir();
    const obs = new ResizeObserver(medir);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  function aLienzo(e: { clientX: number; clientY: number }) {
    const caja = lienzo.current!.getBoundingClientRect();
    return { x: (e.clientX - caja.left - caja.width / 2 - vista.x) / vista.k, y: (e.clientY - caja.top - caja.height / 2 - vista.y) / vista.k };
  }

  function bajar(e: EventoPuntero<SVGElement>, clave?: string) {
    e.stopPropagation();
    if (e.button !== 0) return; // solo el botón principal arrastra
    try {
      // La captura va al lienzo entero: el arrastre sigue aunque el puntero salga de él.
      lienzo.current?.setPointerCapture?.(e.pointerId);
    } catch {
      /* puntero sintético o ya liberado: el arrastre funciona igual */
    }
    arrastre.current = { tipo: clave ? "nodo" : "fondo", clave, x: e.clientX, y: e.clientY, movido: false };
    if (clave) simulacion.current?.alphaTarget(0.25).restart();
  }

  function mover(e: EventoPuntero<SVGSVGElement>) {
    const a = arrastre.current;
    if (!a) return;
    if (!a.movido && Math.abs(e.clientX - a.x) + Math.abs(e.clientY - a.y) > 3) {
      a.movido = true;
      if (a.tipo === "fondo") {
        setPaneando(true);
        alArrastrar?.(true);
      }
    }
    if (a.tipo === "fondo") {
      if (!a.movido) return;
      // El desplazamiento se calcula ya: el actualizador de estado corre después y a.x habrá cambiado.
      const dx = e.clientX - a.x, dy = e.clientY - a.y;
      setVista((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
      a.x = e.clientX;
      a.y = e.clientY;
    } else if (a.clave) {
      const p = puntos.current.get(a.clave);
      const q = aLienzo(e);
      if (p) {
        p.fx = q.x;
        p.fy = q.y;
      }
    }
  }

  function soltar() {
    const a = arrastre.current;
    arrastre.current = null;
    if (a?.tipo === "fondo" && a.movido) {
      setPaneando(false);
      alArrastrar?.(false);
    }
    if (a?.tipo === "nodo" && a.clave) {
      simulacion.current?.alphaTarget(0);
      if (!a.movido) alSeleccionar(a.clave);
    } else if (a?.tipo === "fondo" && !a.movido) {
      alSeleccionar(null); // tocar el lienzo vacío cierra el panel
    }
  }


  const mover1 = (dx: number, dy: number) => setVista((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
  // Teclado: flechas para desplazarse, + y − para acercar.
  function teclas(e: React.KeyboardEvent<SVGSVGElement>) {
    const pasos: Record<string, [number, number]> = { ArrowUp: [0, 80], ArrowDown: [0, -80], ArrowLeft: [80, 0], ArrowRight: [-80, 0] };
    if (pasos[e.key]) { e.preventDefault(); mover1(...pasos[e.key]); }
    else if (e.key === "+" || e.key === "=") zoom(1.2);
    else if (e.key === "-") zoom(1 / 1.2);
  }

  // Rueda del ratón: sube y baja por el grafo (Mayús + rueda, a los lados);
  // Ctrl + rueda o el gesto de pellizco acercan y alejan. Escucha nativa,
  // no pasiva, para que la página no se desplace a la vez.
  useEffect(() => {
    const el = lienzo.current;
    if (!el) return;
    const rueda = (e: globalThis.WheelEvent) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        const factor = Math.exp(-e.deltaY * 0.0025);
        setVista((v) => ({ ...v, k: Math.min(3, Math.max(0.2, v.k * factor)) }));
      } else if (e.shiftKey) {
        setVista((v) => ({ ...v, x: v.x - (e.deltaY || e.deltaX) }));
      } else {
        setVista((v) => ({ ...v, x: v.x - e.deltaX, y: v.y - e.deltaY }));
      }
    };
    el.addEventListener("wheel", rueda, { passive: false });
    return () => el.removeEventListener("wheel", rueda);
  }, []);

  const zoom = (factor: number) => setVista((v) => ({ ...v, k: Math.min(3, Math.max(0.2, v.k * factor)) }));
  const activo = encima || seleccion;
  const atenuar = encima;
  // Etiquetas de las relaciones: siempre, mientras se puedan leer; en un
  // grafo muy denso o muy alejado, solo las del nodo señalado.
  const etiquetasLegibles = datos.aristas.length <= 60 && vista.k >= 0.7;
  const familiasPresentes = new Set(completo.nodos.map((n) => n.familia));
  // Varias relaciones entre los mismos dos nodos: cada etiqueta a una distancia distinta de la línea.
  const desplazamiento = useMemo(() => {
    const vistos = new Map<string, number>();
    return new Map(datos.aristas.map((a) => {
      const par = [a.desde, a.hacia].sort().join("|");
      const n = vistos.get(par) || 0;
      vistos.set(par, n + 1);
      return [`${a.desde}-${a.hacia}-${a.codigo_ric}`, (n % 2 ? -1 : 1) * (9 + Math.floor(n / 2) * 13)];
    }));
  }, [datos]);

  return (
    <div className={`lienzo-grafo${paneando ? " paneando" : ""}`}>
      <div className="leyenda-grafo" role="group" aria-label="Leyenda: toque un tipo para mostrarlo u ocultarlo">
        {FAMILIAS.filter((f) => f.principal || familiasPresentes.has(f.clave)).map((f) => {
          const cuantos = completo.nodos.filter((n) => n.familia === f.clave).length;
          return (
            <button key={f.clave} type="button" className={`item-leyenda${ocultas.has(f.clave) ? " oculta" : ""}`}
                    aria-pressed={!ocultas.has(f.clave)} disabled={!cuantos}
                    title={cuantos ? `${ocultas.has(f.clave) ? "Mostrar" : "Ocultar"} ${f.nombre.toLowerCase()} · rico:${f.ric.replace(/ /g, "")}` : "No hay en este grafo"}
                    onClick={() => alternarFamilia(f.clave)}>
              <MuestraFamilia familia={f.clave} />
              <span>{f.nombre}</span>
              <span className="cuenta-leyenda">{cuantos}</span>
            </button>
          );
        })}
        {ocultas.size > 0 && (
          <button type="button" className="enlace mostrar-todos" onClick={() => setOcultas(new Set())}>Mostrar todos</button>
        )}
      </div>
      <div className="controles-grafo" role="group" aria-label="Acercamiento y desplazamiento del grafo">
        <button type="button" className="boton chico" onClick={() => zoom(1.25)} aria-label="Acercar" title="Acercar">+</button>
        <input type="range" className="deslizador-zoom" min={20} max={300} step={5} value={Math.round(vista.k * 100)}
               aria-label={`Acercamiento: ${Math.round(vista.k * 100)} %`} title={`${Math.round(vista.k * 100)} %`}
               onChange={(e) => setVista((v) => ({ ...v, k: Number(e.target.value) / 100 }))} />
        <button type="button" className="boton chico" onClick={() => zoom(0.8)} aria-label="Alejar" title="Alejar">−</button>
        <button type="button" className="boton chico" onClick={encuadrar} aria-label="Ajustar a la ventana" title="Ajustar a la ventana">
          <svg viewBox="0 0 24 24" width="14" height="14" {...trazo}><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>
        </button>
      </div>
      <svg ref={lienzo} className="svg-grafo" role="img"
           viewBox={`${-tamano.ancho / 2} ${-tamano.alto / 2} ${tamano.ancho} ${tamano.alto}`}
           aria-label={`Grafo con ${datos.nodos.length} entidades y ${datos.aristas.length} relaciones`}
           tabIndex={0} onKeyDown={teclas}
           onPointerDown={(e) => bajar(e)} onPointerMove={mover} onPointerUp={soltar} onPointerCancel={soltar}
           onLostPointerCapture={soltar}>
        <defs>
          {/* Cuadrícula de puntos que se desplaza con el dibujo: da la sensación de lienzo libre. */}
          <pattern id="puntos-grafo" width="24" height="24" patternUnits="userSpaceOnUse"
                   patternTransform={`translate(${vista.x} ${vista.y}) scale(${vista.k})`}>
            <circle cx="12" cy="12" r="1.1" className="punto-lienzo" />
          </pattern>
          <marker id="flecha" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" className="punta" />
          </marker>
        </defs>
        <rect className="fondo-lienzo" x={-tamano.ancho / 2} y={-tamano.alto / 2} width={tamano.ancho} height={tamano.alto} fill="url(#puntos-grafo)" />
        <g transform={`translate(${vista.x} ${vista.y}) scale(${vista.k})`}>
          <g>
            {datos.aristas.map((a) => {
              const p = posiciones[a.desde];
              const q = posiciones[a.hacia];
              const nq = porClave.get(a.hacia);
              if (!p || !q || !nq) return null;
              const dx = q.x - p.x;
              const dy = q.y - p.y;
              const largo = Math.hypot(dx, dy) || 1;
              const r = radio(nq, a.hacia === datos.centro) + 3;
              const fin = { x: q.x - (dx / largo) * r, y: q.y - (dy / largo) * r };
              const resaltada = activo === a.desde || activo === a.hacia;
              const ver = etiquetasLegibles || resaltada;
              // La etiqueta va al lado de la línea (no encima), girada con ella si es legible.
              const nx = -dy / largo, ny = dx / largo;
              const d = desplazamiento.get(`${a.desde}-${a.hacia}-${a.codigo_ric}`) || 9;
              const mx = (p.x + q.x) / 2 + nx * d, my = (p.y + q.y) / 2 + ny * d;
              let angulo = (Math.atan2(dy, dx) * 180) / Math.PI;
              if (angulo > 90 || angulo < -90) angulo += 180;
              return (
                <g key={`${a.desde}-${a.hacia}-${a.codigo_ric}`} className={`arista${resaltada ? " resaltada" : ""}${atenuar && atenuar !== a.desde && atenuar !== a.hacia ? " tenue" : ""}`}>
                  <line x1={p.x} y1={p.y} x2={fin.x} y2={fin.y} markerEnd={a.dirigida ? "url(#flecha)" : undefined} />
                  {ver && (
                    <text x={mx} y={my} textAnchor="middle" dominantBaseline="middle" transform={`rotate(${angulo} ${mx} ${my})`}>
                      <title>{a.uri_rico ? `${a.etiqueta} · ${a.uri_rico}` : a.etiqueta}</title>
                      {a.etiqueta}
                    </text>
                  )}
                </g>
              );
            })}
            {datos.nodos.map((n) => {
              const p = posiciones[n.clave];
              if (!p) return null;
              const raiz = n.clave === datos.centro;
              const r = radio(n, raiz);
              const conectado = !atenuar || atenuar === n.clave || datos.aristas.some(
                (a) => (a.desde === atenuar && a.hacia === n.clave) || (a.hacia === atenuar && a.desde === n.clave));
              const escala = (r * 1.15) / 24;
              return (
                <g key={n.clave} transform={`translate(${p.x} ${p.y})`}
                   className={`nodo f-${n.familia}${seleccion === n.clave ? " elegido" : ""}${raiz ? " central" : ""}${conectado ? "" : " tenue"}`}
                   tabIndex={0} role="button"
                   aria-label={`${NOMBRE_FAMILIA[n.familia]}: ${n.etiqueta}${raiz ? " (entidad raíz)" : ""}`}
                   onPointerDown={(e) => bajar(e, n.clave)} onPointerEnter={() => setEncima(n.clave)} onPointerLeave={() => setEncima(null)}
                   onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && alSeleccionar(n.clave)}>
                  <circle r={r} />
                  <g className="icono-nodo" transform={`translate(${-12 * escala} ${-12 * escala}) scale(${escala})`}>{ICONO_FAMILIA[n.familia]}</g>
                  <text y={r + 13} textAnchor="middle">{corto(n.etiqueta)}</text>
                  {n.subtitulo === "Versión de conservación" && (
                    <text y={r + 26} textAnchor="middle" className="subtitulo-nodo">versión de conservación</text>
                  )}
                </g>
              );
            })}
          </g>
        </g>
      </svg>
    </div>
  );
}
