import { useEffect, useRef, useState, type PointerEvent as EventoPuntero } from "react";
import { PreguntaVocabulario } from "@/components/Vocabulario";
import { pedir, pedirArchivo } from "@/lib/api";
import { NIVEL_NOMBRE, verificarVocabulario, type Coincidencia, type Verificacion } from "@/lib/descripcion";

// --- Idioma, condiciones de acceso y de uso, secuencia ------------------------------------------

export const IDIOMAS: Record<string, string> = {
  spa: "español", lat: "latín", eng: "inglés", fra: "francés", por: "portugués", ita: "italiano", deu: "alemán",
  que: "quechua", chb: "chibcha (muisca)", guc: "wayuunaiki",
};

/** Clasificación del acceso según la Ley 1712 de 2014 (se declara al publicar). */
export interface Clasificacion {
  acceso: "hereda" | "publico" | "clasificado" | "reservado";
  fundamento: string;
  hasta: string; // AAAA-MM-DD, solo para la reserva
  reproduccion: "permitida" | "condicionada" | "no_permitida";
}

export const CLASIFICACION_VACIA: Clasificacion = { acceso: "hereda", fundamento: "", hasta: "", reproduccion: "permitida" };

export function clasificacionParaEnviar(c: Clasificacion) {
  if (c.acceso === "hereda") return null;
  return { acceso: c.acceso, fundamento: c.fundamento.trim() || null, reproduccion: c.reproduccion,
           vigente_hasta: c.acceso === "reservado" ? c.hasta || null : null };
}

export interface CamposRegistroValor {
  idiomas: string[];
  clasificacion: Clasificacion;
  condicionesAcceso: string;
  condicionesUso: string;
  historiaArchivistica: string;
  secuencia: { posicion: "precede" | "sigue"; id: string; titulo: string } | null;
  // Resto de ISAD(G) (hallazgo DES-07): textos de una persona y escrituras ISO 15924.
  isadg: Record<string, string>;
  escrituras: string[];
  // Ley 1581 de 2012 (clase de datos personales; vacío = sin revisar) y Ley 1680 de 2013 (versión accesible).
  datosPersonales: string;
  notaAccesibilidad: string;
}

// Elementos de ISAD(G) que se escriben a mano; el resto sale de otros datos
// del sistema (lote, regla de retención, instanciaciones…). Mismo orden y
// claves que app/servicios/isadg.py.
export const ISADG_TEXTOS: [string, string, string][] = [
  ["forma_ingreso", "3.2.4", "Forma de ingreso (además del lote de transferencia)"],
  ["valoracion", "3.3.2", "Valoración, selección y eliminación (además de la regla de retención)"],
  ["nuevos_ingresos", "3.3.3", "Nuevos ingresos"],
  ["organizacion", "3.3.4", "Organización"],
  ["instrumentos_descripcion", "3.4.5", "Instrumentos de descripción (además de los del sistema)"],
  ["localizacion_originales", "3.5.1", "Existencia y localización de los originales"],
  ["localizacion_copias", "3.5.2", "Existencia y localización de copias"],
  ["unidades_relacionadas", "3.5.3", "Unidades de descripción relacionadas (fuera del sistema)"],
  ["nota_publicaciones", "3.5.4", "Nota de publicaciones"],
  ["nota", "3.6.1", "Notas"],
  ["nota_archivero", "3.7.1", "Nota del archivero"],
  ["reglas_descripcion", "3.7.2", "Reglas o normas"],
];

export const ESCRITURAS: Record<string, string> = {
  Latn: "latina", Grek: "griega", Hebr: "hebrea", Arab: "árabe", Cyrl: "cirílica", Hani: "han (china)",
  Jpan: "japonesa", Zmth: "notación matemática", Zsym: "símbolos", Zyyy: "común", Zxxx: "sin escritura",
  Zzzz: "desconocida",
};

export function camposVacios(idiomas: string[] = []): CamposRegistroValor {
  return { idiomas, clasificacion: CLASIFICACION_VACIA, condicionesAcceso: "", condicionesUso: "", historiaArchivistica: "", secuencia: null,
           isadg: {}, escrituras: [], datosPersonales: "", notaAccesibilidad: "" };
}

export const DATOS_PERSONALES: [string, string][] = [
  ["no_contiene", "No contiene datos personales"],
  ["personales", "Contiene datos personales (nombres, documentos de identidad, direcciones…)"],
  ["sensibles", "Contiene datos sensibles (salud, origen étnico, creencias, orientación sexual…)"],
  ["menores", "Contiene datos de niños, niñas o adolescentes"],
];

/** Lo que se envía al publicar o corregir: solo lo que cambió frente a `antes` (null = no cambia). */
export function proteccionParaEnviar(v: CamposRegistroValor, antes?: { datos_personales: string | null; nota_accesibilidad: string | null }) {
  return {
    datos_personales: v.datosPersonales && v.datosPersonales !== (antes?.datos_personales || "") ? v.datosPersonales : null,
    nota_accesibilidad: v.notaAccesibilidad !== (antes?.nota_accesibilidad || "") ? v.notaAccesibilidad : null,
  };
}

/** Datos sensibles o de menores en algo que quedaría público: Ley 1712 (art. 18) y Ley 1581 (arts. 5 a 7). */
export function datosSensiblesEnPublico(v: CamposRegistroValor, heredada?: { acceso: string } | null): boolean {
  if (!["sensibles", "menores"].includes(v.datosPersonales)) return false;
  const acceso = v.clasificacion.acceso === "hereda" ? heredada?.acceso || "publico" : v.clasificacion.acceso;
  return acceso === "publico";
}

const OPCIONES_ACCESO: [Clasificacion["acceso"], string, string][] = [
  ["hereda", "Igual que el nivel superior", "Toma la clasificación del expediente, la serie o el fondo."],
  ["publico", "Pública", "Cualquiera puede consultarla (Ley 1712, art. 2: máxima publicidad)."],
  ["clasificado", "Clasificada", "Información pública clasificada (art. 18): intimidad, vida o salud de las personas, "
    + "secretos comerciales. Solo la ven quienes tienen permiso."],
  ["reservado", "Reservada", "Información pública reservada (art. 19): defensa, seguridad, relaciones internacionales, "
    + "investigaciones… Con plazo máximo de 15 años (art. 22)."],
];

const NOMBRE_ACCESO: Record<string, string> = { publico: "pública", clasificado: "clasificada", reservado: "reservada" };

function ClasificacionAcceso({ valor, alCambiar, heredada }: {
  valor: Clasificacion; alCambiar: (c: Clasificacion) => void; heredada?: { acceso: string; de: string | null } | null;
}) {
  const restringe = valor.acceso === "clasificado" || valor.acceso === "reservado";
  return (
    <fieldset className="campo" style={{ border: 0, padding: 0, margin: "0 0 14px" }}>
      <legend style={{ fontWeight: 600, marginBottom: 6 }}>
        ¿Quién puede consultarlo? <span className="meta">(Ley 1712 de 2014 · lo decide la institución, no el motor)</span>
      </legend>
      {OPCIONES_ACCESO.map(([clave, nombre, ayuda]) => (
        <label key={clave} className="opcion-radio">
          <input type="radio" name="clasificacion-acceso" value={clave} checked={valor.acceso === clave}
                 onChange={() => alCambiar({
                   ...valor, acceso: clave,
                   // Lo restringido no se reproduce, salvo que la persona diga otra cosa.
                   reproduccion: clave === "clasificado" || clave === "reservado" ? "no_permitida"
                     : valor.acceso === "clasificado" || valor.acceso === "reservado" ? "permitida" : valor.reproduccion,
                 })} />
          <span><b>{nombre}</b> <span className="meta">— {ayuda}
            {clave === "hereda" && heredada && ` Hoy: ${NOMBRE_ACCESO[heredada.acceso] || heredada.acceso}${heredada.de ? `, de «${heredada.de}»` : ""}.`}
            {clave === "hereda" && heredada === null && " Hoy no hay ninguna clasificación arriba: se trata como pública."}</span></span>
        </label>
      ))}
      {restringe && (
        <div style={{ marginTop: 8, paddingLeft: 24 }}>
          <label htmlFor="fundamento">Fundamento legal <span className="meta">(obligatorio)</span></label>
          <input id="fundamento" className="entrada" maxLength={500} value={valor.fundamento}
                 placeholder={valor.acceso === "reservado" ? "Ej.: Ley 1712 de 2014, art. 19, literal f"
                   : "Ej.: Ley 1712 de 2014, art. 18, literal a (intimidad)"}
                 onChange={(e) => alCambiar({ ...valor, fundamento: e.target.value })} />
          {valor.acceso === "reservado" && (
            <>
              <label htmlFor="hasta" style={{ marginTop: 8 }}>Reservada hasta <span className="meta">(obligatorio · máximo 15 años)</span></label>
              <input id="hasta" type="date" className="entrada" style={{ width: "auto" }} value={valor.hasta}
                     onChange={(e) => alCambiar({ ...valor, hasta: e.target.value })} />
            </>
          )}
          <div className="pista">No se mostrará en el catálogo público, la guía, los datos abiertos ni el paquete de
            consulta. Se puede cambiar después en Preservación → Derechos.</div>
        </div>
      )}
      {valor.acceso !== "hereda" && (
        <div style={{ marginTop: 8, paddingLeft: 24 }}>
          <label htmlFor="reproduccion">Reproducción</label>
          <select id="reproduccion" className="selector" style={{ width: "auto" }} value={valor.reproduccion}
                  onChange={(e) => alCambiar({ ...valor, reproduccion: e.target.value as Clasificacion["reproduccion"] })}>
            <option value="permitida">Permitida</option>
            <option value="condicionada">Condicionada</option>
            <option value="no_permitida">No permitida</option>
          </select>
        </div>
      )}
    </fieldset>
  );
}

function OtrosIsadg({ valor, alCambiar }: { valor: CamposRegistroValor; alCambiar: (v: CamposRegistroValor) => void }) {
  const llenos = ISADG_TEXTOS.filter(([c]) => (valor.isadg[c] || "").trim()).length + (valor.escrituras.length ? 1 : 0);
  return (
    <details className="campo">
      <summary>Otros elementos de ISAD(G) <span className="meta">({llenos} con dato · opcionales)</span></summary>
      <div className="campo" style={{ marginTop: 8 }}>
        <label>Escritura <span className="meta">(ISAD-G 3.4.3 · ISO 15924)</span></label>
        <div className="insignias" style={{ flexWrap: "wrap" }}>
          {valor.escrituras.map((c) => (
            <span key={c} className="pastilla">{ESCRITURAS[c] || c} <code className="rico">{c}</code>{" "}
              <button type="button" className="enlace" aria-label={`Quitar ${c}`}
                      onClick={() => alCambiar({ ...valor, escrituras: valor.escrituras.filter((x) => x !== c) })}>×</button>
            </span>
          ))}
          <select className="selector" style={{ width: "auto" }} aria-label="Agregar escritura" value=""
                  onChange={(e) => e.target.value && alCambiar({ ...valor, escrituras: [...valor.escrituras, e.target.value] })}>
            <option value="">Agregar escritura…</option>
            {Object.entries(ESCRITURAS).filter(([c]) => !valor.escrituras.includes(c))
              .map(([c, n]) => <option key={c} value={c}>{n} ({c})</option>)}
          </select>
        </div>
      </div>
      {ISADG_TEXTOS.map(([clave, elemento, nombre]) => (
        <div className="campo" key={clave}>
          <label htmlFor={`isadg-${clave}`}>{nombre} <span className="meta">(ISAD-G {elemento})</span></label>
          <textarea id={`isadg-${clave}`} className="entrada" rows={2} maxLength={20000} value={valor.isadg[clave] || ""}
                    onChange={(e) => alCambiar({ ...valor, isadg: { ...valor.isadg, [clave]: e.target.value } })} />
        </div>
      ))}
    </details>
  );
}

function BuscarPublicada({ fondoId, alElegir }: { fondoId: string; alElegir: (id: string, titulo: string) => void }) {
  const [q, setQ] = useState("");
  const [lista, setLista] = useState<{ id: string; titulo: string; nivel: string }[]>([]);
  useEffect(() => {
    const t = setTimeout(() => {
      pedir<{ id: string; titulo: string; nivel: string }[]>(
        `/api/descripcion/buscar-publicadas?${new URLSearchParams({ fondo_id: fondoId, q })}`).then(setLista).catch(() => setLista([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q, fondoId]);
  return (
    <>
      <input className="entrada" type="search" placeholder="Buscar por título…" aria-label="Buscar documento" value={q}
             onChange={(e) => setQ(e.target.value)} />
      {lista.slice(0, 8).map((r) => (
        <div key={r.id} className="fila" style={{ padding: "6px 0" }}>
          <div className="fila-principal"><div className="nombre">{r.titulo}</div><div className="meta">{NIVEL_NOMBRE[r.nivel]}</div></div>
          <button type="button" className="boton chico" onClick={() => alElegir(r.id, r.titulo)}>Elegir</button>
        </div>
      ))}
    </>
  );
}

export function CamposRegistro({ valor, alCambiar, fondoId, propuestos, confianza, heredada }: {
  valor: CamposRegistroValor; alCambiar: (v: CamposRegistroValor) => void; fondoId: string;
  propuestos: string[]; confianza: number | null;
  heredada?: { acceso: string; de: string | null } | null;
}) {
  const [nuevo, setNuevo] = useState("");
  const [buscando, setBuscando] = useState<"precede" | "sigue" | null>(null);
  const agregar = (c: string) => {
    const codigo = c.trim().toLowerCase();
    if (/^[a-z]{3}$/.test(codigo) && !valor.idiomas.includes(codigo)) alCambiar({ ...valor, idiomas: [...valor.idiomas, codigo] });
    setNuevo("");
  };
  return (
    <div className="tarjeta-prop fija">
      <div className="campo">
        <label>Idioma del contenido <span className="meta">(ISO 639-3)</span></label>
        <div className="insignias" style={{ flexWrap: "wrap" }}>
          {valor.idiomas.map((c) => (
            <span key={c} className="pastilla">
              {IDIOMAS[c] || c} <code className="rico">{c}</code>{" "}
              <button type="button" className="enlace" aria-label={`Quitar ${c}`}
                      onClick={() => alCambiar({ ...valor, idiomas: valor.idiomas.filter((x) => x !== c) })}>×</button>
            </span>
          ))}
          {valor.idiomas.length === 0 && <span className="meta">Sin idioma indicado</span>}
        </div>
        {propuestos.length > 0 && (
          <div className="pista">Propuesta del motor: {propuestos.map((c) => IDIOMAS[c] || c).join(", ")}
            {confianza !== null && ` (confianza ${Math.round(confianza * 100)} %)`}</div>
        )}
        <div className="acciones" style={{ marginTop: 6 }}>
          <select className="selector" style={{ width: "auto" }} aria-label="Agregar idioma" value=""
                  onChange={(e) => e.target.value && agregar(e.target.value)}>
            <option value="">Agregar idioma…</option>
            {Object.entries(IDIOMAS).filter(([c]) => !valor.idiomas.includes(c)).map(([c, n]) => <option key={c} value={c}>{n}</option>)}
          </select>
          <input className="entrada" style={{ width: 110 }} maxLength={3} placeholder="otro: xxx" aria-label="Otro código"
                 value={nuevo} onChange={(e) => setNuevo(e.target.value)} />
          <button type="button" className="boton chico" disabled={!/^[a-zA-Z]{3}$/.test(nuevo)} onClick={() => agregar(nuevo)}>Agregar</button>
        </div>
      </div>
      <ClasificacionAcceso valor={valor.clasificacion} heredada={heredada}
                           alCambiar={(clasificacion) => alCambiar({ ...valor, clasificacion })} />
      <div className="campo">
        <label htmlFor="datos-personales">Datos personales <span className="meta">(Ley 1581 de 2012 · lo revisa una persona)</span></label>
        <select id="datos-personales" className="selector" value={valor.datosPersonales}
                onChange={(e) => alCambiar({ ...valor, datosPersonales: e.target.value })}>
          <option value="">Sin revisar</option>
          {DATOS_PERSONALES.map(([k, n]) => <option key={k} value={k}>{n}</option>)}
        </select>
        {datosSensiblesEnPublico(valor, heredada) ? (
          <div className="aviso alerta" role="status" style={{ marginTop: 6 }}>
            Quedaría pública con datos {valor.datosPersonales === "menores" ? "de menores de edad" : "sensibles"}:
            clasifíquela (Ley 1712, art. 18, literal a) o anonimice la versión de consulta (Ley 1581, arts. 5 a 7).
          </div>
        ) : (
          <div className="pista">No es lo mismo que la clasificación de arriba: un documento público puede tener datos
            personales que se anonimizan al consultarlo. No sale en el catálogo público ni en los datos abiertos.</div>
        )}
      </div>
      <div className="campo">
        <label htmlFor="acceso">Condiciones de acceso, en palabras <span className="meta">(ISAD-G 3.4.1 · opcional · las decide la institución, no el motor)</span></label>
        <textarea id="acceso" className="entrada" rows={2} value={valor.condicionesAcceso} maxLength={5000}
                  placeholder="Ej.: «Consulta en sala con cita previa» o «Contiene datos de salud de terceros»"
                  onChange={(e) => alCambiar({ ...valor, condicionesAcceso: e.target.value })} />
        <div className="pista">Este texto explica el acceso en la ficha. Lo que decide si el documento se muestra o se
          oculta es la clasificación de arriba.</div>
      </div>
      <div className="campo">
        <label htmlFor="uso">Condiciones de uso o de reproducción</label>
        <textarea id="uso" className="entrada" rows={2} value={valor.condicionesUso} maxLength={5000}
                  placeholder="Condición para copiarlo o reproducirlo"
                  onChange={(e) => alCambiar({ ...valor, condicionesUso: e.target.value })} />
      </div>
      <div className="campo">
        <label htmlFor="accesible">Versión accesible <span className="meta">(Ley 1680 de 2013 · opcional · se muestra en la ficha pública)</span></label>
        <textarea id="accesible" className="entrada" rows={2} value={valor.notaAccesibilidad} maxLength={2000}
                  placeholder="Ej.: «Transcripción en texto plano para lector de pantalla»"
                  onChange={(e) => alCambiar({ ...valor, notaAccesibilidad: e.target.value })} />
      </div>
      <div className="campo">
        <label htmlFor="historia">Historia archivística <span className="meta">(ISAD-G 3.2.3 · cómo llegó a su custodio actual)</span></label>
        <textarea id="historia" className="entrada" rows={2} value={valor.historiaArchivistica} maxLength={20000}
                  placeholder="Transferencias, depósitos y custodios anteriores"
                  onChange={(e) => alCambiar({ ...valor, historiaArchivistica: e.target.value })} />
      </div>
      <OtrosIsadg valor={valor} alCambiar={alCambiar} />
      <div className="campo" style={{ marginBottom: 0 }}>
        <label>Secuencia en la serie <span className="meta">(opcional · rico:precedesOrPreceded)</span></label>
        {valor.secuencia ? (
          <p style={{ margin: "4px 0" }}>
            Este documento {valor.secuencia.posicion === "precede" ? "precede a" : "sigue a"} <b>{valor.secuencia.titulo}</b>{" "}
            <button type="button" className="enlace" onClick={() => alCambiar({ ...valor, secuencia: null })}>Quitar</button>
          </p>
        ) : buscando ? (
          <>
            <BuscarPublicada fondoId={fondoId} alElegir={(id, titulo) => { alCambiar({ ...valor, secuencia: { posicion: buscando, id, titulo } }); setBuscando(null); }} />
            <button type="button" className="enlace" onClick={() => setBuscando(null)}>Cancelar</button>
          </>
        ) : (
          <div className="acciones">
            <button type="button" className="boton chico" onClick={() => setBuscando("sigue")}>Sigue a…</button>
            <button type="button" className="boton chico" onClick={() => setBuscando("precede")}>Precede a…</button>
          </div>
        )}
      </div>
    </div>
  );
}

// --- Actividad mayor (sub-actividad) ------------------------------------------------------------------

export function ElegirActividadMayor({ fondoId, actual, alElegir }: {
  fondoId: string; actual: { id: string; nombre: string } | null; alElegir: (a: { id: string; nombre: string } | null) => void;
}) {
  const [abierta, setAbierta] = useState(false);
  const [q, setQ] = useState("");
  const [lista, setLista] = useState<{ id: string; nombre: string }[]>([]);
  useEffect(() => {
    if (!abierta || !q.trim()) { setLista([]); return; }
    const t = setTimeout(() => {
      pedir<{ id: string; nombre: string }[]>(`/api/vocabulario?${new URLSearchParams({ fondo_id: fondoId, clase: "actividad", q, orden: "nombre" })}`)
        .then((r) => setLista(r.slice(0, 6))).catch(() => setLista([]));
    }, 250);
    return () => clearTimeout(t);
  }, [abierta, q, fondoId]);
  if (actual) {
    return (
      <div className="linea-contexto">
        Sub-actividad de <b>{actual.nombre}</b> <code className="rico">rico:isDirectSubeventOf</code>{" "}
        <button type="button" className="enlace" onClick={() => alElegir(null)}>Quitar</button>
      </div>
    );
  }
  if (!abierta) return <button type="button" className="enlace" onClick={() => setAbierta(true)}>Es sub-actividad de otra ya registrada…</button>;
  return (
    <div>
      <input className="entrada" type="search" autoFocus placeholder="Buscar la actividad mayor…" aria-label="Buscar actividad mayor"
             value={q} onChange={(e) => setQ(e.target.value)} />
      {lista.map((a) => (
        <div key={a.id} className="fila" style={{ padding: "4px 0" }}>
          <div className="fila-principal"><div className="nombre">{a.nombre}</div></div>
          <button type="button" className="boton chico" onClick={() => { alElegir(a); setAbierta(false); }}>Elegir</button>
        </div>
      ))}
      <button type="button" className="enlace" onClick={() => setAbierta(false)}>Cancelar</button>
    </div>
  );
}

// --- Partes documentales y recorte sobre la página -----------------------------------------------------

export interface Zona { instanciacion_id: string; pagina: number; x: number; y: number; ancho: number; alto: number }

export interface ParteBorrador {
  clave: string;
  titulo: string;
  tipo: string;
  tipoVerif: Verificacion;
  alcance: string;
  recorte: Zona | null;
}

function Visor({ trabajoId, documento, alRecortar }: {
  trabajoId: string; documento: { id: string; nombre: string }; alRecortar: (z: Zona) => void;
}) {
  const [info, setInfo] = useState<{ admite: boolean; total: number } | null>(null);
  const [pagina, setPagina] = useState(1);
  const [url, setUrl] = useState<string | null>(null);
  const [inicio, setInicio] = useState<{ x: number; y: number } | null>(null);
  const [caja, setCaja] = useState<{ x: number; y: number; ancho: number; alto: number } | null>(null);
  const marco = useRef<HTMLDivElement>(null);

  useEffect(() => {
    pedir<{ admite: boolean; total: number }>(`/api/descripcion/trabajos/${trabajoId}/documentos/${documento.id}/paginas`)
      .then(setInfo).catch(() => setInfo({ admite: false, total: 0 }));
  }, [trabajoId, documento.id]);

  useEffect(() => {
    if (!info?.admite) return;
    let vivo = true, actual: string | null = null;
    pedirArchivo(`/api/descripcion/trabajos/${trabajoId}/documentos/${documento.id}/paginas/${pagina}`).then((b) => {
      if (!vivo) return;
      actual = URL.createObjectURL(b);
      setUrl(actual);
    }).catch(() => setUrl(null));
    setCaja(null);
    return () => { vivo = false; if (actual) URL.revokeObjectURL(actual); };
  }, [info, pagina, trabajoId, documento.id]);

  const punto = (e: EventoPuntero) => {
    const r = marco.current!.getBoundingClientRect();
    return { x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)) };
  };

  if (info && !info.admite) return <p className="pista">Este formato no se puede mostrar como página: la parte se registra sin recorte.</p>;
  return (
    <div>
      <div className="acciones" style={{ alignItems: "center", marginBottom: 6 }}>
        <span className="meta">{documento.nombre} · página</span>
        <button type="button" className="boton chico" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>‹</button>
        <span>{pagina} de {info?.total ?? "…"}</span>
        <button type="button" className="boton chico" disabled={!info || pagina >= info.total} onClick={() => setPagina(pagina + 1)}>›</button>
      </div>
      <p className="pista" style={{ marginTop: 0 }}>Arrastre sobre la página para marcar la zona de la parte (la firma, el sello, el anexo).</p>
      <div ref={marco} className="visor-pagina"
           onPointerDown={(e) => { (e.target as HTMLElement).setPointerCapture?.(e.pointerId); const p = punto(e); setInicio(p); setCaja({ ...p, ancho: 0, alto: 0 }); }}
           onPointerMove={(e) => { if (!inicio) return; const p = punto(e); setCaja({ x: Math.min(inicio.x, p.x), y: Math.min(inicio.y, p.y), ancho: Math.abs(p.x - inicio.x), alto: Math.abs(p.y - inicio.y) }); }}
           onPointerUp={() => setInicio(null)}>
        {url ? <img src={url} alt={`Página ${pagina} de ${documento.nombre}`} draggable={false} /> : <div className="cargando">Cargando la página…</div>}
        {caja && caja.ancho > 0 && (
          <div className="zona-recorte" style={{ left: `${caja.x * 100}%`, top: `${caja.y * 100}%`, width: `${caja.ancho * 100}%`, height: `${caja.alto * 100}%` }} />
        )}
      </div>
      <div className="acciones" style={{ marginTop: 6 }}>
        <button type="button" className="boton chico primario" disabled={!caja || caja.ancho < 0.01 || caja.alto < 0.01}
                onClick={() => caja && alRecortar({ instanciacion_id: documento.id, pagina, ...caja })}>Usar esta zona</button>
      </div>
    </div>
  );
}

export function PartesDocumentales({ partes, alCambiar, trabajoId, fondoId, documentos }: {
  partes: ParteBorrador[]; alCambiar: (p: ParteBorrador[]) => void; trabajoId: string; fondoId: string;
  documentos: { id: string; nombre: string }[];
}) {
  const [abierta, setAbierta] = useState<string | null>(null);
  const actualizar = (clave: string, cambio: Partial<ParteBorrador>) => alCambiar(partes.map((p) => (p.clave === clave ? { ...p, ...cambio } : p)));

  async function verificarTipo(p: ParteBorrador) {
    if (!p.tipo.trim()) { actualizar(p.clave, { tipoVerif: { estado: "resuelta", coincidencias: [], crearNueva: true } }); return; }
    actualizar(p.clave, { tipoVerif: { estado: "verificando", coincidencias: [] } });
    const c: Coincidencia[] = await verificarVocabulario(fondoId, "tipo_parte", p.tipo).catch(() => []);
    actualizar(p.clave, { tipoVerif: c.length ? { estado: "pregunta", coincidencias: c } : { estado: "resuelta", coincidencias: [], crearNueva: true } });
  }

  return (
    <div className="tarjeta-prop">
      <div className="prop-cab">
        <span className="insignia acento">Partes documentales · {partes.length}</span>
        <code className="rico">rico:RecordPart · RiC-R003</code>
      </div>
      <p className="pista" style={{ marginTop: 4 }}>
        Opcional. Registre por separado un anexo, un folio, una firma o un sello cuando el fondo o la investigación lo
        justifiquen. Cada parte puede llevar el recorte de su zona como instanciación propia.
      </p>
      {partes.map((p) => (
        <div key={p.clave} className="parte-borrador">
          <div className="rejilla">
            <input className="entrada" aria-label="Título de la parte" placeholder="Título (p. ej. «Sello de la Alcaldía»)" value={p.titulo}
                   onChange={(e) => actualizar(p.clave, { titulo: e.target.value })} />
            <input className="entrada" aria-label="Tipo de parte" placeholder="Tipo: anexo, folio, firma, sello…" value={p.tipo}
                   onChange={(e) => actualizar(p.clave, { tipo: e.target.value, tipoVerif: { estado: "sin_verificar", coincidencias: [] } })}
                   onBlur={() => verificarTipo(p)} />
          </div>
          <PreguntaVocabulario valor={p.tipo} verificacion={p.tipoVerif} alDecidir={(v) => actualizar(p.clave, { tipoVerif: v })} />
          <textarea className="entrada" rows={2} aria-label="Alcance de la parte" placeholder="Qué es y qué contiene (opcional)" value={p.alcance}
                    onChange={(e) => actualizar(p.clave, { alcance: e.target.value })} />
          <div className="acciones" style={{ marginTop: 6, alignItems: "center" }}>
            {p.recorte ? (
              <span className="meta">Recorte: página {p.recorte.pagina}, {Math.round(p.recorte.ancho * 100)} % × {Math.round(p.recorte.alto * 100)} % de la página{" "}
                <button type="button" className="enlace" onClick={() => actualizar(p.clave, { recorte: null })}>Quitar</button></span>
            ) : (
              <button type="button" className="boton chico" onClick={() => setAbierta(abierta === p.clave ? null : p.clave)}>
                {abierta === p.clave ? "Cerrar el visor" : "Recortar sobre el documento"}
              </button>
            )}
            <button type="button" className="enlace" onClick={() => alCambiar(partes.filter((x) => x.clave !== p.clave))}>Quitar la parte</button>
          </div>
          {abierta === p.clave && !p.recorte && documentos.map((d) => (
            <Visor key={d.id} trabajoId={trabajoId} documento={d} alRecortar={(z) => { actualizar(p.clave, { recorte: z }); setAbierta(null); }} />
          ))}
        </div>
      ))}
      <button type="button" className="enlace" onClick={() => alCambiar([...partes, {
        clave: `parte${Date.now()}`, titulo: "", tipo: "", tipoVerif: { estado: "resuelta", coincidencias: [], crearNueva: true }, alcance: "", recorte: null,
      }])}>+ Registrar una parte documental</button>
    </div>
  );
}

export function partePendiente(p: ParteBorrador): boolean {
  return p.titulo.trim().length < 2 || ["verificando", "pregunta", "sin_verificar"].includes(p.tipoVerif.estado);
}

export function parteParaEnviar(p: ParteBorrador) {
  return {
    titulo: p.titulo.trim(), alcance: p.alcance.trim() || null, recorte: p.recorte,
    tipo_parte: p.tipo.trim() ? { valor: p.tipo.trim(), reutilizar_id: p.tipoVerif.reutilizarId || null, crear_nueva: !!p.tipoVerif.crearNueva } : null,
  };
}
