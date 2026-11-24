import { useEffect, useMemo, useRef, useState, type PointerEvent as EventoPuntero, type ReactNode } from "react";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from "d3-force";

export type Familia =
  | "RecordSet" | "Record" | "RecordPart" | "Agent" | "Place" | "Activity" | "Date" | "Instantiation"
  | "DocumentaryFormType" | "ActivityType" | "Mandate" | "Event" | "Concept";

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
  codigo?: string | null;
  sin_nombre?: boolean | null;
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
  Concept: <g {...trazo}><path d="M7 4h7l4 4v12H7z" /><path d="M9.5 12h6M9.5 15.5h6M9.5 8.5h3" /></g>,
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
  { clave: "DocumentaryFormType", nombre: "Tipo documental", ric: "Documentary Form Type", principal: false },
  { clave: "ActivityType", nombre: "Tipo de actividad", ric: "Activity Type", principal: false },
  { clave: "Mandate", nombre: "Mandato, norma o regla", ric: "Mandate · Rule", principal: false },
  { clave: "Event", nombre: "Hito institucional", ric: "Event", principal: false },
  { clave: "Concept", nombre: "Materia", ric: "Concept", principal: false },
];
// Las agrupaciones documentales comparten clase en RiC (rico:RecordSet), pero no
// son lo mismo para quien describe: cada nivel lleva su propio icono y color,
// y la leyenda los nombra (rico:RecordSetType).
export const NIVELES: { clave: string; nombre: string; icono: ReactNode }[] = [
  { clave: "fondo", nombre: "Fondo", icono: <g {...trazo}><path d="M3 9l9-5 9 5" /><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18" /></g> },
  { clave: "coleccion", nombre: "Colección", icono: <g {...trazo}><path d="M6 4h12v16l-6-4-6 4z" /></g> },
  { clave: "seccion", nombre: "Sección", icono: <g {...trazo}><rect x="9" y="3" width="6" height="5" rx="1" /><rect x="3" y="16" width="6" height="5" rx="1" /><rect x="15" y="16" width="6" height="5" rx="1" /><path d="M12 8v4M6 16v-4h12v4" /></g> },
  { clave: "subseccion", nombre: "Subsección", icono: <g {...trazo}><rect x="9" y="4" width="6" height="5" rx="1" /><rect x="9" y="15" width="6" height="5" rx="1" /><path d="M12 9v6" /></g> },
  { clave: "serie", nombre: "Serie", icono: <g {...trazo}><path d="M4 8h16v11H4z" /><path d="M6 5h12M8 2.5h8" /></g> },
  { clave: "subserie", nombre: "Subserie", icono: <g {...trazo}><path d="M5 9h14v10H5z" /><path d="M7 6h10" /></g> },
  { clave: "expediente", nombre: "Expediente", icono: <g {...trazo}><path d="M3 6h7l2 2h9v11H3z" /></g> },
  { clave: "unidad_documental", nombre: "Documento", icono: ICONO_FAMILIA.Record },
  { clave: "parte_documental", nombre: "Parte documental", icono: ICONO_FAMILIA.RecordPart },
];
const ICONO_NIVEL = Object.fromEntries(NIVELES.map((n) => [n.clave, n.icono])) as Record<string, ReactNode>;
const NOMBRE_NIVEL = Object.fromEntries(NIVELES.map((n) => [n.clave, n.nombre])) as Record<string, string>;
const esRecurso = (n: NodoGrafo) => n.tipo === "recurso_documental";
export const iconoDe = (n: NodoGrafo) => (esRecurso(n) && ICONO_NIVEL[n.clase]) || ICONO_FAMILIA[n.familia];
// El código del cuadro de clasificación distingue las series homónimas de dependencias distintas.
// Nombre provisional de una agrupación («Serie 27», «Dependencia 3203»): la TRD trajo el código sin el nombre.
export const esNombreProvisional = (titulo: string | null | undefined) =>
  /^(fondo|secci[oó]n|subsecci[oó]n|serie|subserie|expediente|dependencia)?\s*[\d.]*$/i.test((titulo || "").trim());
export const etiquetaDe = (n: NodoGrafo) => (n.codigo ? `${n.codigo} ${n.etiqueta}` : n.etiqueta);

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

function corto(texto: string, n = 30): string {
  return texto.length > n ? `${texto.slice(0, n - 1)}…` : texto;
}

/** El nombre en dos líneas como máximo, cortando entre palabras: así no se pierde la parte que
 *  distingue a dos homónimos («Despacho del Viceministro de Ordenamiento…» frente a «…de Políticas…»). */
export function lineas(texto: string, ancho = 28, maximo = 2): string[] {
  const salida: string[] = [];
  let actual = "";
  for (const palabra of texto.split(/\s+/).filter(Boolean)) {
    if (!actual) actual = palabra;
    else if ((actual + " " + palabra).length <= ancho) actual += " " + palabra;
    else { salida.push(actual); actual = palabra; }
  }
  if (actual) salida.push(actual);
  if (salida.length > maximo) {
    const resto = salida.slice(maximo - 1).join(" ");
    return [...salida.slice(0, maximo - 1), corto(resto, ancho)];
  }
  return salida.map((l) => corto(l, ancho));
}

type Punto = SimulationNodeDatum & { clave: string };
type Disposicion = "red" | "arbol" | "descripcion";
type Panel = { grupo: string; texto: string; x: number; y: number; w: number; h: number };
type Grupo = "raiz" | "estructura" | "contiene" | "agentes" | "funcion" | "norma" | "contexto";

const JERARQUIA = new Set(["includes_or_included", "has_or_had_constituent"]);
export const TITULO_GRUPO: Record<Exclude<Grupo, "raiz">, string> = {
  estructura: "Dónde está en el fondo", contiene: "Qué contiene y sus archivos", agentes: "Quién lo produjo e intervino",
  funcion: "Para qué función", norma: "Bajo qué norma", contexto: "Dónde, cuándo y de qué tipo",
};

// La descripción de una entidad leída como RiC: la cadena de agrupaciones que la contienen,
// sus agentes, su función y la norma que la regula, y su lugar, su fecha y su forma.
// Solo entra lo que describe a la raíz; los hermanos y las ramas ajenas se quedan en la vista Red.
export function seleccionDescripcion(d: DatosGrafo): { datos: DatosGrafo; grupos: Map<string, Grupo>; omitidos: number } {
  const por = new Map(d.nodos.map((n) => [n.clave, n]));
  const grupos = new Map<string, Grupo>([[d.centro, "raiz"]]);
  const usadas: typeof d.aristas = [];
  // Hacia arriba: quién la incluye, y quién incluye a esa, hasta el fondo.
  let actual = d.centro;
  for (let i = 0; i < 8; i++) {
    const a = d.aristas.find((x) => x.hacia === actual && JERARQUIA.has(x.codigo_ric) && !grupos.has(x.desde));
    if (!a) break;
    grupos.set(a.desde, "estructura");
    usadas.push(a);
    actual = a.desde;
  }
  const directas = d.aristas.filter((a) => (a.desde === d.centro || a.hacia === d.centro));
  for (const a of directas) {
    const otro = a.desde === d.centro ? a.hacia : a.desde;
    const n = por.get(otro);
    if (!n || grupos.has(otro)) continue;
    let g: Grupo;
    if (JERARQUIA.has(a.codigo_ric) && a.desde === d.centro) g = "contiene";
    else if (n.familia === "Instantiation") g = "contiene";
    else if (n.familia === "Agent") g = "agentes";
    else if (n.familia === "Activity" || n.familia === "ActivityType" || n.familia === "Event") g = "funcion";
    else if (n.familia === "Mandate") g = "norma";
    else if (n.familia === "RecordSet" || n.familia === "Record" || n.familia === "RecordPart") g = "contiene";
    else g = "contexto";
    grupos.set(otro, g);
    usadas.push(a);
  }
  // Un salto más solo donde completa la lectura: la actividad lleva a su tipo y a su norma,
  // y el agente al puesto o a la persona que lo ejerce.
  for (const a of d.aristas) {
    if (usadas.includes(a)) continue;
    for (const [aqui, alla] of [[a.desde, a.hacia], [a.hacia, a.desde]]) {
      const ga = grupos.get(aqui), n = por.get(alla);
      if (!ga || !n) continue;
      const g: Grupo | null = ga === "funcion" && (n.familia === "ActivityType" || n.familia === "Activity") ? "funcion"
        : (ga === "funcion" || ga === "norma") && n.familia === "Mandate" ? "norma"
        : ga === "agentes" && n.familia === "Agent" ? "agentes" : null;
      if (g && (!grupos.has(alla) || grupos.get(alla) === g)) {
        if (!grupos.has(alla)) grupos.set(alla, g);
        usadas.push(a);
        break;
      }
    }
  }
  const nodos = d.nodos.filter((n) => grupos.has(n.clave));
  const quedan = new Set(nodos.map((n) => n.clave));
  const aristas = d.aristas.filter((a) => usadas.includes(a) || (quedan.has(a.desde) && quedan.has(a.hacia)
    && grupos.get(a.desde) !== "raiz" && grupos.get(a.desde) === grupos.get(a.hacia)));
  return { datos: { ...d, nodos, aristas }, grupos, omitidos: d.nodos.length - nodos.length };
}

export function LienzoGrafo({ datos: completo, seleccion, alSeleccionar, enfoque, alArrastrar, disposicionInicial = "red" }: {
  // «red»: por fuerzas; «arbol»: por niveles desde la raíz, para ver la estructura;
  // «descripcion»: la descripción RiC de la raíz ordenada por preguntas (dónde, quién, para qué, bajo qué norma, cuándo).
  disposicionInicial?: Disposicion;
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
  // La leyenda no tapa el grafo: aparece flotando solo cuando se pide.
  const [verLeyenda, setVerLeyenda] = useState(false);
  const [disposicion, setDisposicion] = useState<Disposicion>(disposicionInicial);
  const { datos, grupos, omitidos } = useMemo(() => {
    let d = completo;
    if (ocultas.size) {
      const nodos = completo.nodos.filter((n) => !ocultas.has(n.familia) || n.clave === completo.centro);
      const quedan = new Set(nodos.map((n) => n.clave));
      d = { ...completo, nodos, aristas: completo.aristas.filter((a) => quedan.has(a.desde) && quedan.has(a.hacia)) };
    }
    if (disposicion !== "descripcion") return { datos: d, grupos: null as Map<string, Grupo> | null, omitidos: 0 };
    return seleccionDescripcion(d);
  }, [completo, ocultas, disposicion]);
  const [rotulos, setRotulos] = useState<Panel[]>([]);
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
  const paneles = useRef<Panel[]>([]);

  function encuadrar() {
    const lista = [...puntos.current.values()];
    if (!lista.length) return;
    const xs = lista.map((p) => p.x || 0);
    const ys = lista.map((p) => p.y || 0);
    for (const r of paneles.current) { xs.push(r.x + 65, r.x + r.w - 65); ys.push(r.y + 10, r.y + r.h - 20); }
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const { ancho, alto } = tamanoRef.current;
    // Que el grafo ocupe el lienzo: margen justo para las etiquetas y sin tope bajo de acercamiento.
    const tope = lista.length < 8 ? 1.1 : 1.8;  // pocos nodos: no se agrandan hasta tapar el lienzo
    const k = Math.min(tope, Math.max(0.2, Math.min(ancho / (x1 - x0 + 330), alto / (y1 - y0 + 130))));
    // Margen arriba para la barra de botones, que flota sobre el lienzo.
    setVista({ k, x: -((x0 + x1 + 200) / 2) * k, y: -((y0 + y1) / 2) * k + 24 });
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
    // Sin la entidad raíz entre los nodos no hay desde dónde ordenar: se dibuja por relaciones.
    if (disposicion === "descripcion" && grupos && puntos.current.has(datos.centro)) {
      const de = (g: Grupo) => nodos.filter((n) => grupos.get(n.clave) === g).map((n) => puntos.current.get(n.clave)!);
      const fijar = (p: Punto, x: number, y: number) => { p.x = x; p.y = y; p.fx = x; p.fy = y; };
      const fila = (ps: Punto[], y: number, x0: number, paso: number) => ps.forEach((p, j) => fijar(p, x0 + (j - (ps.length - 1) / 2) * paso, y));
      const columna = (ps: Punto[], x: number, y0: number, paso: number) => ps.forEach((p, j) => fijar(p, x, y0 + (j - (ps.length - 1) / 2) * paso));
      fijar(puntos.current.get(datos.centro)!, 0, 0);
      // La cadena de agrupaciones sube a la izquierda: la más cercana a la altura de la raíz, el fondo arriba.
      const cadena = de("estructura");
      const orden = new Map<string, number>();
      let paso = datos.centro;
      for (let i = 0; i < cadena.length; i++) {
        const a = datos.aristas.find((x) => x.hacia === paso && JERARQUIA.has(x.codigo_ric));
        if (!a) break;
        orden.set(a.desde, i);
        paso = a.desde;
      }
      cadena.sort((a, b) => (orden.get(a.clave) ?? 99) - (orden.get(b.clave) ?? 99)).forEach((p, i) => fijar(p, -360, -i * 85));
      const contiene = de("contiene");
      columna(contiene, -360, 120 + ((contiene.length - 1) / 2) * 70, 70);
      const agentes = de("agentes");
      fila(agentes, -250, 90, 200);
      const funcion = de("funcion"), norma = de("norma");
      columna(funcion, 340, 0, 95);
      columna(norma, 620, 0, 95);
      const contexto = de("contexto");
      fila(contexto, 250, 90, 175);
      // Cada pregunta es un panel: el grupo se lee como un bloque de la ficha, no como nodos sueltos.
      const r: Panel[] = [];
      for (const [g, ps] of [["estructura", cadena], ["contiene", contiene], ["agentes", agentes], ["funcion", funcion],
                              ["norma", norma], ["contexto", contexto]] as [Exclude<Grupo, "raiz">, Punto[]][]) {
        if (!ps.length) continue;
        const xs = ps.map((p) => p.x!), ys = ps.map((p) => p.y!);
        const x0 = Math.min(...xs) - 95, x1 = Math.max(...xs) + 95, y0 = Math.min(...ys) - 58, y1 = Math.max(...ys) + 46;
        r.push({ grupo: g, texto: TITULO_GRUPO[g], x: x0, y: y0, w: x1 - x0, h: y1 - y0 });
      }
      paneles.current = r;
      setRotulos(r);
      setPosiciones(Object.fromEntries(nodos.map((n) => [n.clave, { x: n.x || 0, y: n.y || 0 }])));
      simulacion.current = null;
      const t = window.setTimeout(encuadrar, 30);
      return () => window.clearTimeout(t);
    }
    paneles.current = [];
    setRotulos([]);
    if (disposicion === "arbol" && puntos.current.has(datos.centro)) {
      // Por niveles: cada entidad en la fila de su distancia a la raíz y, dentro de la fila,
      // junto a las demás hijas de su mismo padre. Sin fuerzas: la estructura se lee de arriba abajo.
      // Primero la estructura (inclusión y regla de cada serie), después lo demás: así la regla de
      // retención queda junto a su serie y no junto al documento de la TRD.
      const vecinos = (filtro: (a: AristaGrafo) => boolean) => {
        const m = new Map<string, string[]>();
        for (const a of datos.aristas.filter(filtro)) {
          for (const [x, y] of [[a.desde, a.hacia], [a.hacia, a.desde]]) m.set(x, [...(m.get(x) || []), y]);
        }
        return m;
      };
      const estructurales = vecinos((a) => JERARQUIA.has(a.codigo_ric) || a.codigo_ric === "regulates_or_regulated");
      const todos = vecinos(() => true);
      const raiz = datos.centro;
      const nivel = new Map<string, number>([[raiz, 0]]);
      const orden: string[] = [raiz];
      for (const vecinosDe of [estructurales, todos]) {
        for (let i = 0; i < orden.length; i++) {
          const hijos = (vecinosDe.get(orden[i]) || []).filter((v) => !nivel.has(v) && porClave.has(v))
            .sort((a, b) => etiquetaDe(porClave.get(a)!).localeCompare(etiquetaDe(porClave.get(b)!), "es", { numeric: true }));
          for (const h of hijos) { nivel.set(h, nivel.get(orden[i])! + 1); orden.push(h); }
        }
      }
      for (const n of nodos) if (!nivel.has(n.clave)) { nivel.set(n.clave, 1); orden.push(n.clave); }
      const filas = new Map<number, string[]>();
      for (const c of orden) filas.set(nivel.get(c)!, [...(filas.get(nivel.get(c)!) || []), c]);
      // De izquierda a derecha: el lienzo es más ancho que alto y cada nombre se lee completo a su derecha.
      const paso = 46;
      for (const [f, claves] of filas) {
        claves.forEach((c, j) => {
          const p = puntos.current.get(c)!;
          p.x = f * 300;
          p.y = (j - (claves.length - 1) / 2) * paso;
          p.fx = p.x;
          p.fy = p.y;
        });
      }
      setPosiciones(Object.fromEntries(nodos.map((n) => [n.clave, { x: n.x || 0, y: n.y || 0 }])));
      simulacion.current = null;
      const t = window.setTimeout(encuadrar, 30);
      return () => window.clearTimeout(t);
    }
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
      // El lienzo es más ancho que alto: los nodos se extienden a lo ancho para aprovecharlo.
      .force("ancho", forceX<Punto>(0).strength(0.015))
      .force("alto", forceY<Punto>(0).strength(0.015 * Math.max(1, tamanoRef.current.ancho / tamanoRef.current.alto)))
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
  }, [datos, porClave, disposicion, grupos]);

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
      const antes = tamanoRef.current;
      tamanoRef.current = { ancho: el.clientWidth || 800, alto: el.clientHeight || 560 };
      setTamano(tamanoRef.current);
      if (Math.abs(antes.ancho - tamanoRef.current.ancho) > 40 || Math.abs(antes.alto - tamanoRef.current.alto) > 40) encuadrar();
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
    if (clave && disposicion === "red") simulacion.current?.alphaTarget(0.25).restart();
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
        if (disposicion !== "red") {
          p.x = q.x;
          p.y = q.y;
          setPosiciones((ps) => ({ ...ps, [a.clave!]: { x: q.x, y: q.y } }));
        }
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
  const etiquetasLegibles = disposicion === "descripcion" || (datos.aristas.length <= 60 && vista.k >= 0.7);
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
      <button type="button" className={`boton chico boton-leyenda${ocultas.size ? " con-filtros" : ""}`}
              aria-expanded={verLeyenda} aria-controls="leyenda-grafo" onClick={() => setVerLeyenda(!verLeyenda)}>
        Tipos{ocultas.size > 0 && <span className="contador" aria-label={`${ocultas.size} ocultos`}>{ocultas.size}</span>}
      </button>
      {verLeyenda && (
      <div className="leyenda-grafo" id="leyenda-grafo" role="group"
           aria-label="Leyenda: toque un tipo para mostrarlo u ocultarlo">
        {FAMILIAS.filter((f) => familiasPresentes.has(f.clave)).map((f) => {
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
        {(() => {
          const niveles = NIVELES.filter((nv) => completo.nodos.some((n) => esRecurso(n) && n.clase === nv.clave));
          if (!niveles.length) return null;
          return (
            <div className="niveles-leyenda" aria-label="Niveles de las agrupaciones y documentos">
              <span className="titulo-niveles">Niveles</span>
              {niveles.map((nv) => (
                <span key={nv.clave} className="item-nivel">
                  <svg className={`muestra-familia n-${nv.clave}`} width={18} height={18} viewBox="-12 -12 24 24" aria-hidden="true">
                    <circle r="12" /><g transform="translate(-7.2 -7.2) scale(.6)" className="icono-nodo">{nv.icono}</g>
                  </svg>
                  <span>{nv.nombre}</span>
                  <span className="cuenta-leyenda">{completo.nodos.filter((n) => esRecurso(n) && n.clase === nv.clave).length}</span>
                </span>
              ))}
            </div>
          );
        })()}
        {ocultas.size > 0 && (
          <button type="button" className="enlace mostrar-todos" onClick={() => setOcultas(new Set())}>Mostrar todos</button>
        )}
      </div>
      )}
      <div className="disposicion-grafo" role="group" aria-label="Disposición del grafo">
        <button type="button" className={`boton chico${disposicion === "red" ? " activo" : ""}`} aria-pressed={disposicion === "red"}
                title="Por relaciones: para ver el contexto de una entidad" onClick={() => setDisposicion("red")}>Red</button>
        <button type="button" className={`boton chico${disposicion === "arbol" ? " activo" : ""}`} aria-pressed={disposicion === "arbol"}
                title="Por niveles desde la raíz: para ver la estructura del fondo" onClick={() => setDisposicion("arbol")}>Árbol</button>
        <button type="button" className={`boton chico${disposicion === "descripcion" ? " activo" : ""}`} aria-pressed={disposicion === "descripcion"}
                title="La descripción de la entidad raíz ordenada por preguntas: dónde está, quién, para qué, bajo qué norma, dónde y cuándo"
                onClick={() => setDisposicion("descripcion")}>Descripción</button>
        {disposicion === "descripcion" && omitidos > 0 && (
          <span className="nota-disposicion">{omitidos === 1 ? "1 entidad que no describe" : `${omitidos} entidades que no describen`} a la raíz {omitidos === 1 ? "queda" : "quedan"} en la vista Red</span>
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
          {rotulos.map((r) => (
            <g key={r.grupo} className={`panel-grupo g-${r.grupo}`}>
              <rect x={r.x} y={r.y} width={r.w} height={r.h} rx={14} />
              <text x={r.x + 14} y={r.y + 20} className="rotulo-grupo">{r.texto}</text>
            </g>
          ))}
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
              // «incluye» en cada flecha de la estructura no dice nada nuevo: solo se escribe al señalar el nodo.
              const ver = (etiquetasLegibles && (disposicion === "descripcion" || !JERARQUIA.has(a.codigo_ric))) || resaltada;
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
                   className={`nodo f-${n.familia}${esRecurso(n) ? ` n-${n.clase}` : ""}${n.sin_nombre ? " sin-nombre" : ""}${seleccion === n.clave ? " elegido" : ""}${raiz ? " central" : ""}${conectado ? "" : " tenue"}`}
                   tabIndex={0} role="button"
                   aria-label={`${esRecurso(n) ? NOMBRE_NIVEL[n.clase] || NOMBRE_FAMILIA[n.familia] : NOMBRE_FAMILIA[n.familia]}: ${etiquetaDe(n)}${n.sin_nombre ? " (sin nombre propio)" : ""}${raiz ? " (entidad raíz)" : ""}`}
                   onPointerDown={(e) => bajar(e, n.clave)} onPointerEnter={() => setEncima(n.clave)} onPointerLeave={() => setEncima(null)}
                   onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && alSeleccionar(n.clave)}>
                  <title>{`${esRecurso(n) ? NOMBRE_NIVEL[n.clase] || n.subtitulo : NOMBRE_FAMILIA[n.familia]} · ${etiquetaDe(n)}`}</title>
                  <circle r={r} />
                  <g className="icono-nodo" transform={`translate(${-12 * escala} ${-12 * escala}) scale(${escala})`}>{iconoDe(n)}</g>
                  {disposicion === "arbol" ? (<>
                    <text x={r + 6} y={n.sin_nombre ? -1 : 4} textAnchor="start">{corto(etiquetaDe(n), 44)}</text>
                    {n.sin_nombre && <text x={r + 6} y={11} textAnchor="start" className="subtitulo-nodo aviso-nodo">sin nombre en la TRD</text>}
                  </>) : (<>
                    {(() => {
                      const ls = lineas(etiquetaDe(n), disposicion === "descripcion" ? 34 : 28);
                      return (<>
                        <text y={r + 13} textAnchor="middle">
                          {ls.map((l, i) => <tspan key={i} x={0} dy={i ? 13 : 0}>{l}</tspan>)}
                        </text>
                        {n.sin_nombre && <text y={r + 13 + 13 * ls.length} textAnchor="middle" className="subtitulo-nodo aviso-nodo">
                          sin nombre en la TRD</text>}
                      </>);
                    })()}
                  </>)}
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
