import { useEffect, useMemo, useRef, useState, type PointerEvent as EventoPuntero, type WheelEvent } from "react";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, type SimulationNodeDatum } from "d3-force";

export interface NodoGrafo {
  clave: string;
  id: string;
  tipo: string;
  clase: string;
  etiqueta: string;
  subtitulo: string | null;
  documentos?: number;
}

export interface AristaGrafo {
  desde: string;
  hacia: string;
  codigo_ric: string;
  uri_rico: string | null;
  etiqueta: string;
}

export interface DatosGrafo {
  fondo: { id: string; titulo: string };
  centro: string;
  nodos: NodoGrafo[];
  aristas: AristaGrafo[];
  truncado: boolean;
}

// Cómo se dibuja cada clase de nodo (color por CSS y nombre para la leyenda).
export const CLASES_NODO: { clase: string; nombre: string; ric: string }[] = [
  { clase: "documento", nombre: "Documento o agrupación", ric: "Record / Record Set" },
  { clase: "agente", nombre: "Agente", ric: "Agent" },
  { clase: "lugar", nombre: "Lugar", ric: "Place" },
  { clase: "forma_documental", nombre: "Forma documental", ric: "Documentary form type" },
  { clase: "fecha", nombre: "Fecha", ric: "Date" },
  { clase: "actividad", nombre: "Actividad", ric: "Activity" },
  { clase: "instanciacion", nombre: "Archivo (instanciación)", ric: "Instantiation" },
];

export function claseVisual(n: NodoGrafo): string {
  return n.tipo === "recurso_documental" ? "documento" : n.clase;
}

function radio(n: NodoGrafo): number {
  if (n.tipo === "recurso_documental") return n.clase === "fondo" ? 22 : n.clase === "unidad_documental" ? 14 : 18;
  if (n.tipo === "entidad_vocabulario") return 10 + Math.min(10, Math.sqrt(n.documentos || 1) * 2.5);
  return 9;
}

function corto(texto: string, n = 26): string {
  return texto.length > n ? `${texto.slice(0, n - 1)}…` : texto;
}

type Punto = SimulationNodeDatum & { clave: string };

export function LienzoGrafo({ datos, seleccion, alSeleccionar }: {
  datos: DatosGrafo;
  seleccion: string | null;
  alSeleccionar: (clave: string) => void;
}) {
  const lienzo = useRef<SVGSVGElement>(null);
  const [posiciones, setPosiciones] = useState<Record<string, { x: number; y: number }>>({});
  const [vista, setVista] = useState({ x: 0, y: 0, k: 1 });
  const [encima, setEncima] = useState<string | null>(null);
  const [tamano, setTamano] = useState({ ancho: 800, alto: 560 });
  const puntos = useRef<Map<string, Punto>>(new Map());
  const simulacion = useRef<ReturnType<typeof forceSimulation<Punto>> | null>(null);
  const arrastre = useRef<{ tipo: "fondo" | "nodo"; clave?: string; x: number; y: number; movido: boolean } | null>(null);

  const tamanoRef = useRef({ ancho: 800, alto: 560 });

  // Ajusta el zoom para que todo el grafo quepa en el recuadro.
  function encuadrar() {
    const lista = [...puntos.current.values()];
    if (!lista.length) return;
    const xs = lista.map((p) => p.x || 0);
    const ys = lista.map((p) => p.y || 0);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const { ancho, alto } = tamanoRef.current;
    const k = Math.min(1.4, Math.max(0.25, Math.min(ancho / (x1 - x0 + 160), alto / (y1 - y0 + 120))));
    setVista({ k, x: -((x0 + x1) / 2) * k, y: -((y0 + y1) / 2) * k });
  }

  const porClave = useMemo(() => new Map(datos.nodos.map((n) => [n.clave, n])), [datos]);

  // Simulación de fuerzas: los nodos se acomodan solos; el central queda fijo al medio.
  useEffect(() => {
    const anteriores = puntos.current;
    const nodos: Punto[] = datos.nodos.map((n) => {
      const p = anteriores.get(n.clave);
      return { clave: n.clave, x: p?.x ?? (Math.random() - 0.5) * 200, y: p?.y ?? (Math.random() - 0.5) * 200 };
    });
    const centro = nodos.find((n) => n.clave === datos.centro);
    if (centro) {
      centro.fx = 0;
      centro.fy = 0;
    }
    puntos.current = new Map(nodos.map((n) => [n.clave, n]));
    const enlaces = datos.aristas.map((a) => ({ source: a.desde, target: a.hacia }));
    let cuadro = 0;
    const sim = forceSimulation<Punto>(nodos)
      .force("enlaces", forceLink<Punto, { source: string; target: string }>(enlaces).id((n) => n.clave).distance(110))
      .force("carga", forceManyBody().strength(-420))
      .force("choque", forceCollide<Punto>().radius((n) => radio(porClave.get(n.clave)!) + 26))
      .force("centro", forceCenter(0, 0).strength(0.04))
      .on("end", () => encuadrar())
      .on("tick", () => {
        if (cuadro) return;
        cuadro = requestAnimationFrame(() => {
          cuadro = 0;
          setPosiciones(Object.fromEntries(nodos.map((n) => [n.clave, { x: n.x || 0, y: n.y || 0 }])));
        });
      });
    simulacion.current = sim;
    setVista({ x: 0, y: 0, k: datos.nodos.length > 40 ? 0.6 : 1 });
    const primerEncuadre = window.setTimeout(encuadrar, 900);
    return () => {
      sim.stop();
      window.clearTimeout(primerEncuadre);
      cancelAnimationFrame(cuadro);
    };
  }, [datos, porClave]);

  // El origen (0, 0) queda en el centro del lienzo, mida lo que mida.
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
    try {
      (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    } catch {
      /* puntero sintético o ya liberado: el arrastre funciona igual */
    }
    arrastre.current = { tipo: clave ? "nodo" : "fondo", clave, x: e.clientX, y: e.clientY, movido: false };
    if (clave) simulacion.current?.alphaTarget(0.25).restart();
  }

  function mover(e: EventoPuntero<SVGSVGElement>) {
    const a = arrastre.current;
    if (!a) return;
    if (Math.abs(e.clientX - a.x) + Math.abs(e.clientY - a.y) > 3) a.movido = true;
    if (a.tipo === "fondo") {
      setVista((v) => ({ ...v, x: v.x + e.clientX - a.x, y: v.y + e.clientY - a.y }));
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
    if (a?.tipo === "nodo" && a.clave) {
      simulacion.current?.alphaTarget(0);
      if (!a.movido) alSeleccionar(a.clave);
    }
  }

  function rueda(e: WheelEvent<SVGSVGElement>) {
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    setVista((v) => ({ ...v, k: Math.min(3, Math.max(0.25, v.k * factor)) }));
  }

  const zoom = (factor: number) => setVista((v) => ({ ...v, k: Math.min(3, Math.max(0.25, v.k * factor)) }));
  // Resaltar: las relaciones del nodo elegido. Atenuar el resto: solo al
  // pasar el cursor, para no esconder nodos que el usuario no ha mirado.
  const activo = encima || seleccion;
  const atenuar = encima;
  // Las etiquetas de las flechas solo aparecen al pasar el cursor sobre un
  // nodo (o en grafos pequeños): así no se amontonan. El panel las lista todas.
  const mostrarEtiquetasAristas = datos.aristas.length <= 6;

  return (
    <div className="lienzo-grafo">
      <div className="controles-grafo" role="group" aria-label="Zoom del grafo">
        <button type="button" className="boton chico" onClick={() => zoom(1.25)} aria-label="Acercar">+</button>
        <button type="button" className="boton chico" onClick={() => zoom(0.8)} aria-label="Alejar">−</button>
        <button type="button" className="boton chico" onClick={encuadrar}>Reencuadrar</button>
      </div>
      <svg ref={lienzo} className="svg-grafo" role="img"
           viewBox={`${-tamano.ancho / 2} ${-tamano.alto / 2} ${tamano.ancho} ${tamano.alto}`} aria-label={`Grafo con ${datos.nodos.length} nodos y ${datos.aristas.length} relaciones`}
           onPointerDown={(e) => bajar(e)} onPointerMove={mover} onPointerUp={soltar} onPointerLeave={soltar} onWheel={rueda}>
        <defs>
          <marker id="flecha" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" className="punta" />
          </marker>
        </defs>
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
              const fin = { x: q.x - (dx / largo) * (radio(nq) + 3), y: q.y - (dy / largo) * (radio(nq) + 3) };
              const resaltada = activo === a.desde || activo === a.hacia;
              return (
                <g key={`${a.desde}-${a.hacia}-${a.codigo_ric}`} className={`arista${resaltada ? " resaltada" : ""}${atenuar && atenuar !== a.desde && atenuar !== a.hacia ? " tenue" : ""}`}>
                  <line x1={p.x} y1={p.y} x2={fin.x} y2={fin.y} markerEnd="url(#flecha)" />
                  {(mostrarEtiquetasAristas || encima === a.desde || encima === a.hacia) && (
                    <text x={(p.x + q.x) / 2} y={(p.y + q.y) / 2 - 4} textAnchor="middle">{a.etiqueta}</text>
                  )}
                </g>
              );
            })}
            {datos.nodos.map((n) => {
              const p = posiciones[n.clave];
              if (!p) return null;
              const r = radio(n);
              const conectado = !atenuar || atenuar === n.clave || datos.aristas.some(
                (a) => (a.desde === atenuar && a.hacia === n.clave) || (a.hacia === atenuar && a.desde === n.clave));
              return (
                <g key={n.clave} transform={`translate(${p.x} ${p.y})`}
                   className={`nodo n-${claseVisual(n)}${seleccion === n.clave ? " elegido" : ""}${n.clave === datos.centro ? " central" : ""}${conectado ? "" : " tenue"}`}
                   tabIndex={0} role="button" aria-label={`${n.etiqueta}${n.subtitulo ? `, ${n.subtitulo}` : ""}`}
                   onPointerDown={(e) => bajar(e, n.clave)} onPointerEnter={() => setEncima(n.clave)} onPointerLeave={() => setEncima(null)}
                   onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && alSeleccionar(n.clave)}>
                  {n.tipo === "instanciacion" ? <rect x={-r} y={-r} width={r * 2} height={r * 2} rx={3} /> : <circle r={r} />}
                  <text y={r + 13} textAnchor="middle">{corto(n.etiqueta)}</text>
                </g>
              );
            })}
          </g>
        </g>
      </svg>
    </div>
  );
}
