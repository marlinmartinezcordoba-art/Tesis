import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { SelectorFecha } from "@/components/SelectorFecha";
import { ErrorAPI, descargar, pedir } from "@/lib/api";
import { NIVEL_NOMBRE, SUBTIPO_NOMBRE } from "@/lib/descripcion";
import { controlInicial, type ControlFecha, type SubtipoFecha } from "@/lib/fechas";
import { fecha } from "@/lib/formato";
import { CLASE_NOMBRE, type ClaseVocabulario, type EntidadVocabulario } from "@/lib/vocabulario";

// --- Tipos que devuelve GET /api/vocabulario/{id} (campo «ficha») ---------------------------

export interface Vinculo {
  relacion_id: string;
  vinculo: string;
  codigo_ric: string;
  rol: string | null;
  sentido: "directa" | "inversa";
  etiqueta: string;
  propiedad_rico: string | null;
  estado_mapeo: "verificada" | "general";
  codigo_cm: string | null;
  vigencia: string | null;
  vigencia_legible: string | null;
  nota: string | null;
  con: { tipo: string; id: string; nombre: string; clase: string | null; subtipo: string | null; nivel: string | null } | null;
}

interface Nombre {
  id: string;
  tipo: "paralela" | "normalizada" | "otra" | "historica";
  nombre: string;
  idioma: string | null;
  regla: string | null;
  vigencia: string | null;
  vigencia_legible: string | null;
}

interface Breve { id: string; nombre: string; subtipo?: string | null }
interface FechaPublica { fecha_legible: string | null; edtf: string | null }

export interface Ficha {
  campos: Record<string, string | number | null>;
  nombres: Nombre[];
  vinculos: Vinculo[];
  clase_rico: string;
  control: { identificador_registro: string; reglas: string | null; nivel_detalle: string | null; creada_en: string;
             revisada_en: string | null; estado_elaboracion?: string | null; institucion_responsable?: string | null;
             lenguas?: string[]; escrituras?: string[]; notas_mantenimiento?: string | null };
  identificadores?: { id: string; esquema: string; valor: string; externo: boolean; uri: string | null }[];
  hitos?: { id: string; tipo: string; descripcion: string; edtf: string; fecha_legible: string; clase_rico: string; propiedad_rico: string }[];
  existencia_legible?: string | null;
  falta_version?: boolean;
  usos_tecnicos?: Record<string, number>;
  contiene?: Vinculo[];
  skos?: { broader: Breve | null; narrower: Breve[] };
  actividades?: Breve[];
  contexto?: { tipo_actividad: Breve | null; ejercida_por: Breve[]; regulada_por: (Breve & { expedicion: FechaPublica | null })[]; periodo: FechaPublica | null };
  expedicion?: FechaPublica | null;
}

interface Props {
  entidad: EntidadVocabulario;
  ficha: Ficha;
  fondoId: string;
  puede: boolean;
  alCambiar: (aviso?: string) => void; // recargar el detalle
}

const ESQUEMA_NOMBRE: Record<string, string> = {
  interno: "Código interno", viaf: "VIAF", wikidata: "Wikidata", isni: "ISNI", lcnaf: "LCNAF", otro: "Otro esquema",
};
const TIPO_NOMBRE_FORMA: Record<string, string> = {
  paralela: "Forma paralela (otra lengua)", normalizada: "Forma normalizada según otras reglas", otra: "Otra forma (variante, sigla)",
  historica: "Nombre histórico",
};
const HITO_NOMBRE: Record<string, string> = {
  creacion: "Creación", reforma: "Reforma administrativa", traslado: "Traslado del archivo", supresion: "Supresión", otro: "Otro hecho",
};
const ESTATUTO: Record<string, string> = { publica: "Pública", privada: "Privada", mixta: "Mixta" };
const DISPOSICION: Record<string, string> = {
  conservacion_total: "Conservación total", eliminacion: "Eliminación", seleccion: "Selección",
  medio_tecnico: "Reproducción por medio técnico",
};
const TIPO_LUGAR: Record<string, string> = {
  pais: "País", departamento: "Departamento", provincia: "Provincia", municipio: "Municipio", corregimiento: "Corregimiento",
  vereda: "Vereda", barrio: "Barrio", edificio: "Edificio", otro: "Otro",
};

async function enviar(ruta: string, metodo: string, cuerpo?: unknown) {
  return pedir(ruta, { method: metodo, body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo) });
}

function mensaje(err: unknown, porDefecto: string) {
  return err instanceof ErrorAPI ? err.message : porDefecto;
}

// --- Piezas comunes ---------------------------------------------------------------------------------

function Area({ titulo, insignia, abierta = true, children }: { titulo: string; insignia?: ReactNode; abierta?: boolean; children: ReactNode }) {
  return (
    <details className="area-isaar" open={abierta}>
      <summary>{titulo}{insignia}</summary>
      <div className="contenido">{children}</div>
    </details>
  );
}

function PropiedadRico({ v }: { v: Vinculo }) {
  if (!v.propiedad_rico) return null;
  return (
    <code className="rico" title={v.estado_mapeo === "general"
      ? "RiC-O no tiene una propiedad dedicada: se usa la más específica que existe (ver anexo de verificación)."
      : "Propiedad verificada contra el archivo OWL de RiC-O 1.1"}>
      {v.propiedad_rico}{v.codigo_cm ? ` · ${v.codigo_cm}` : ""}{v.estado_mapeo === "general" ? " · general" : ""}
    </code>
  );
}

// Un campo de texto que se edita en el lugar y se guarda con PATCH.
function TextoEditable({ etiqueta, campo, valor, multilinea, puede, entidadId, alCambiar, pista }: {
  etiqueta: string; campo: string; valor: string | number | null | undefined; multilinea?: boolean; puede: boolean;
  entidadId: string; alCambiar: Props["alCambiar"]; pista?: string;
}) {
  const [editando, setEditando] = useState(false);
  const [texto, setTexto] = useState(valor == null ? "" : String(valor));
  const [error, setError] = useState("");

  async function guardar(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await enviar(`/api/vocabulario/${entidadId}`, "PATCH", { [campo]: texto });
      setEditando(false);
      alCambiar();
    } catch (err) {
      setError(mensaje(err, "No se pudo guardar."));
    }
  }

  return (
    <>
      <dt>{etiqueta}</dt>
      <dd>
        {editando ? (
          <form onSubmit={guardar}>
            {multilinea
              ? <textarea className="entrada" rows={4} value={texto} onChange={(e) => setTexto(e.target.value)} aria-label={etiqueta} />
              : <input className="entrada" value={texto} onChange={(e) => setTexto(e.target.value)} aria-label={etiqueta} />}
            {pista && <div className="pista">{pista}</div>}
            {error && <div className="aviso error" role="alert">{error}</div>}
            <div className="acciones" style={{ marginTop: 6 }}>
              <button type="submit" className="boton chico primario">Guardar</button>
              <button type="button" className="boton chico" onClick={() => { setEditando(false); setTexto(valor == null ? "" : String(valor)); }}>Cancelar</button>
            </div>
          </form>
        ) : (
          <>
            {valor == null || valor === "" ? <span className="meta">Sin registrar</span>
              : multilinea ? <span style={{ whiteSpace: "pre-wrap" }}>{valor}</span> : <span>{valor}</span>}
            {puede && <> <button type="button" className="enlace" onClick={() => setEditando(true)}>{valor ? "Editar" : "Agregar"}</button></>}
          </>
        )}
      </dd>
    </>
  );
}

function ListaEditable({ etiqueta, campo, valor, opciones, puede, entidadId, alCambiar }: {
  etiqueta: string; campo: string; valor: string | null; opciones: Record<string, string>; puede: boolean;
  entidadId: string; alCambiar: Props["alCambiar"];
}) {
  const [error, setError] = useState("");
  async function cambiar(v: string) {
    setError("");
    try {
      await enviar(`/api/vocabulario/${entidadId}`, "PATCH", { [campo]: v || null });
      alCambiar();
    } catch (err) {
      setError(mensaje(err, "No se pudo guardar."));
    }
  }
  return (
    <>
      <dt>{etiqueta}</dt>
      <dd>
        {puede ? (
          <select className="selector" style={{ width: "auto" }} aria-label={etiqueta} value={valor || ""} onChange={(e) => cambiar(e.target.value)}>
            <option value="">Sin registrar</option>
            {Object.entries(opciones).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        ) : (valor ? opciones[valor] || valor : <span className="meta">Sin registrar</span>)}
        {error && <div className="aviso error" role="alert">{error}</div>}
      </dd>
    </>
  );
}

// Fecha EDTF editable (existencia de un agente).
function FechaEditable({ etiqueta, campo, edtf, legible, puede, entidadId, alCambiar, subtipos }: {
  etiqueta: string; campo: string; edtf: string | null; legible: string | null | undefined; puede: boolean; entidadId: string;
  alCambiar: Props["alCambiar"]; subtipos: SubtipoFecha[];
}) {
  const [editando, setEditando] = useState(false);
  const [control, setControl] = useState<ControlFecha>(controlInicial("rango"));
  const [valor, setValor] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function guardar(v: string | null) {
    setError("");
    try {
      await enviar(`/api/vocabulario/${entidadId}`, "PATCH", { [campo]: v || "" });
      setEditando(false);
      alCambiar();
    } catch (err) {
      setError(mensaje(err, "No se pudo guardar la fecha."));
    }
  }

  return (
    <>
      <dt>{etiqueta}</dt>
      <dd>
        {editando ? (
          <>
            <SelectorFecha valor={control} subtipos={subtipos} alCambiar={(c, x) => { setControl(c); setValor(x); }} />
            {error && <div className="aviso error" role="alert">{error}</div>}
            <div className="acciones" style={{ marginTop: 6 }}>
              <button type="button" className="boton chico primario" disabled={!valor} onClick={() => guardar(valor)}>Guardar</button>
              {edtf && <button type="button" className="boton chico" onClick={() => guardar(null)}>Quitar fecha</button>}
              <button type="button" className="boton chico" onClick={() => setEditando(false)}>Cancelar</button>
            </div>
          </>
        ) : (
          <>
            {edtf ? <><span>{legible}</span> <code className="rico">{edtf}</code></> : <span className="meta">Sin registrar</span>}
            {puede && <> <button type="button" className="enlace" onClick={() => setEditando(true)}>{edtf ? "Cambiar" : "Agregar"}</button></>}
          </>
        )}
      </dd>
    </>
  );
}

// Buscador de entidades del vocabulario (o de series) para declarar un vínculo.
function Buscador({ fondoId, busca, excluir, alElegir }: {
  fondoId: string; busca: ClaseVocabulario | "serie"; excluir: string; alElegir: (id: string, nombre: string) => void;
}) {
  const [q, setQ] = useState("");
  const [resultados, setResultados] = useState<{ id: string; nombre: string; meta: string }[]>([]);

  useEffect(() => {
    if (!q.trim()) {
      setResultados([]);
      return;
    }
    const t = setTimeout(async () => {
      try {
        if (busca === "serie") {
          const r = await pedir<{ id: string; titulo: string; nivel: string }[]>(
            `/api/vocabulario/series?${new URLSearchParams({ fondo_id: fondoId, q: q.trim() })}`);
          setResultados(r.map((x) => ({ id: x.id, nombre: x.titulo, meta: NIVEL_NOMBRE[x.nivel] || x.nivel })));
        } else {
          const r = await pedir<EntidadVocabulario[]>(
            `/api/vocabulario?${new URLSearchParams({ fondo_id: fondoId, clase: busca, q: q.trim(), orden: "nombre" })}`);
          setResultados(r.filter((x) => x.id !== excluir).slice(0, 8)
            .map((x) => ({ id: x.id, nombre: x.nombre, meta: x.subtipo ? SUBTIPO_NOMBRE[x.subtipo] || x.subtipo : CLASE_NOMBRE[x.clase] })));
        }
      } catch {
        setResultados([]);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [q, busca, fondoId, excluir]);

  return (
    <>
      <input className="entrada" type="search" autoFocus value={q} onChange={(e) => setQ(e.target.value)}
             aria-label="Buscar" placeholder={busca === "serie" ? "Buscar serie o subserie…" : `Buscar ${CLASE_NOMBRE[busca].toLowerCase()}…`} />
      {q.trim() && resultados.length === 0 && <div className="meta">Sin coincidencias en el vocabulario del fondo.</div>}
      {resultados.map((r) => (
        <div className="fila" key={r.id} style={{ padding: "6px 0" }}>
          <div className="fila-principal"><div className="nombre">{r.nombre}</div><div className="meta">{r.meta}</div></div>
          <button type="button" className="boton chico" onClick={() => alElegir(r.id, r.nombre)}>Elegir</button>
        </div>
      ))}
    </>
  );
}

// Cómo se declara cada vínculo desde la ficha: qué se busca, si lleva
// fecha de vigencia y, cuando la fila nace en la otra entidad («invertir»),
// desde cuál se envía.
// `subtipos`: solo se ofrece si la entidad que se edita es de uno de esos tipos de agente.
interface OpcionVinculo {
  tipo: string; etiqueta: string; busca: ClaseVocabulario | "serie"; conFecha?: boolean; invertir?: boolean; subtipos?: string[];
}
const GRUPOS = ["grupo", "entidad_corporativa", "familia"];

const OPCIONES: Record<string, OpcionVinculo[]> = {
  agente_relaciones: [
    { tipo: "subordinado", etiqueta: "Tiene o tuvo como subordinado a", busca: "agente", conFecha: true },
    { tipo: "subordinado", etiqueta: "Está o estuvo subordinado a", busca: "agente", conFecha: true, invertir: true },
    { tipo: "sucesor", etiqueta: "Tiene como sucesor a", busca: "agente", conFecha: true },
    { tipo: "sucesor", etiqueta: "Es sucesor de (su predecesor)", busca: "agente", conFecha: true, invertir: true },
    { tipo: "asociado", etiqueta: "Está asociado con", busca: "agente", conFecha: true },
    // Persona, cargo y grupo (RiC-R054, R055, R056, R005, R042).
    { tipo: "ocupa_cargo", etiqueta: "Ocupa u ocupó el cargo", busca: "agente", conFecha: true, subtipos: ["persona"] },
    { tipo: "ocupa_cargo", etiqueta: "Lo ocupa u ocupó (persona)", busca: "agente", conFecha: true, invertir: true, subtipos: ["cargo"] },
    { tipo: "cargo_en", etiqueta: "Existe o existió en (grupo o entidad)", busca: "agente", subtipos: ["cargo"] },
    { tipo: "cargo_en", etiqueta: "Tiene o tuvo el cargo", busca: "agente", invertir: true, subtipos: GRUPOS },
    { tipo: "miembro", etiqueta: "Tiene o tuvo como miembro a (persona)", busca: "agente", conFecha: true, subtipos: GRUPOS },
    { tipo: "miembro", etiqueta: "Es o fue miembro de", busca: "agente", conFecha: true, invertir: true, subtipos: ["persona"] },
    { tipo: "dirige", etiqueta: "Dirige o dirigió", busca: "agente", conFecha: true, subtipos: ["persona"] },
    { tipo: "subdivision", etiqueta: "Tiene o tuvo como subdivisión a", busca: "agente", conFecha: true, subtipos: GRUPOS },
    { tipo: "subdivision", etiqueta: "Es o fue subdivisión de", busca: "agente", conFecha: true, invertir: true, subtipos: GRUPOS },
    // Parentesco (ISAAR 5.3.2; rico:hasFamilyAssociationWith), con su tipo controlado.
    { tipo: "progenitor_de", etiqueta: "Es padre o madre de", busca: "agente", conFecha: true, subtipos: ["persona"] },
    { tipo: "progenitor_de", etiqueta: "Es hijo o hija de", busca: "agente", conFecha: true, invertir: true, subtipos: ["persona"] },
    { tipo: "hermano_de", etiqueta: "Es hermano o hermana de", busca: "agente", subtipos: ["persona"] },
    { tipo: "conyuge_de", etiqueta: "Es o fue cónyuge de", busca: "agente", conFecha: true, subtipos: ["persona"] },
    { tipo: "familiar_de", etiqueta: "Tiene otro parentesco con", busca: "agente", conFecha: true, subtipos: ["persona"] },
  ],
  agente_lugares: [{ tipo: "lugar_agente", etiqueta: "Actúa o actuó en", busca: "lugar" }],
  agente_creacion: [{ tipo: "creado_por", etiqueta: "Fue creado o establecido por", busca: "mandato" }],
  lugar: [{ tipo: "lugar_superior", etiqueta: "Está o estuvo dentro de", busca: "lugar", conFecha: true }],
  actividad: [
    { tipo: "actividad_mayor", etiqueta: "Es sub-actividad de", busca: "actividad" },
    { tipo: "ejercida_por", etiqueta: "Es o fue ejercida por", busca: "agente" },
    { tipo: "mandato_actividad", etiqueta: "Está regulada por", busca: "mandato" },
  ],
  mandato: [
    { tipo: "mandato_superior", etiqueta: "Desarrolla o deriva de (norma superior)", busca: "mandato" },
    { tipo: "expedido_por", etiqueta: "Fue expedido por", busca: "agente" },
    { tipo: "creado_por", etiqueta: "Crea o establece al agente", busca: "agente", invertir: true },
  ],
  tipo_actividad: [
    { tipo: "serie_producida", etiqueta: "Produce la serie (TRD)", busca: "serie" },
    { tipo: "competencia_creada_por", etiqueta: "Es una competencia creada por", busca: "mandato" },
  ],
};

function Vinculos({ vinculos, tipos, puede, entidad, fondoId, alCambiar, opciones, vacio }: {
  vinculos: Vinculo[]; tipos: string[]; puede: boolean; entidad: EntidadVocabulario; fondoId: string;
  alCambiar: Props["alCambiar"]; opciones: OpcionVinculo[]; vacio: string;
}) {
  const [abierta, setAbierta] = useState<OpcionVinculo | null>(null);
  const [elegida, setElegida] = useState<{ id: string; nombre: string } | null>(null);
  const [control, setControl] = useState<ControlFecha>(controlInicial("rango"));
  const [vigencia, setVigencia] = useState<string | null>(null);
  const [nota, setNota] = useState("");
  const [error, setError] = useState("");
  const propios = vinculos.filter((v) => tipos.includes(v.vinculo));

  function cerrar() {
    setAbierta(null); setElegida(null); setVigencia(null); setNota(""); setError(""); setControl(controlInicial("rango"));
  }

  async function confirmar() {
    if (!abierta || !elegida) return;
    setError("");
    const con_tipo = abierta.busca === "serie" ? "recurso_documental" : "entidad_vocabulario";
    const desde = abierta.invertir ? elegida.id : entidad.id;
    const con = abierta.invertir ? entidad.id : elegida.id;
    try {
      await enviar(`/api/vocabulario/${desde}/vinculos`, "POST", {
        tipo: abierta.tipo, con_id: con, con_tipo: abierta.invertir ? "entidad_vocabulario" : con_tipo,
        fecha_edtf: abierta.conFecha ? vigencia : null, nota: nota.trim() || null,
      });
      cerrar();
      alCambiar("Vínculo declarado. Queda en la auditoría.");
    } catch (err) {
      setError(mensaje(err, "No se pudo declarar el vínculo."));
    }
  }

  async function anular(v: Vinculo) {
    if (!window.confirm(`¿Anular «${v.etiqueta} ${v.con?.nombre}»? El vínculo no se borra: queda anulado en el historial.`)) return;
    try {
      await enviar(`/api/vocabulario/${entidad.id}/vinculos/${v.relacion_id}/anular`, "POST");
      alCambiar("Vínculo anulado.");
    } catch (err) {
      setError(mensaje(err, "No se pudo anular."));
    }
  }

  const enlace = (v: Vinculo) => !v.con ? "—" : v.con.tipo === "entidad_vocabulario"
    ? <Link to={`/vocabularios/${v.con.id}`}>{v.con.nombre}</Link> : <span>{v.con.nombre}</span>;

  return (
    <>
      {propios.length === 0 && <p className="meta" style={{ marginTop: 0 }}>{vacio}</p>}
      {propios.map((v) => (
        <div className="fila" key={v.relacion_id} style={{ padding: "8px 0" }}>
          <div className="fila-principal">
            <div className="nombre">{v.etiqueta} {enlace(v)}</div>
            <div className="meta">
              {v.vigencia_legible && <>vigencia {v.vigencia_legible} · </>}{v.nota && <>{v.nota} · </>}<PropiedadRico v={v} />
            </div>
          </div>
          {puede && <button type="button" className="enlace" onClick={() => anular(v)}>Anular</button>}
        </div>
      ))}
      {error && !abierta && <div className="aviso error" role="alert">{error}</div>}
      {puede && !abierta && (
        <div className="acciones" style={{ marginTop: 6, flexWrap: "wrap" }}>
          {opciones.filter((o) => !o.subtipos || o.subtipos.includes(entidad.subtipo || "")).map((o) => (
            <button key={`${o.tipo}-${o.invertir ? "i" : "d"}`} type="button" className="boton chico" onClick={() => setAbierta(o)}>
              + {o.etiqueta}
            </button>
          ))}
        </div>
      )}
      {abierta && (
        <div className="tarjeta" style={{ marginTop: 10 }}>
          <div className="tarjeta-cab">
            <span>«{entidad.nombre}» {abierta.etiqueta.toLowerCase()}…</span>
            <button type="button" className="enlace" onClick={cerrar}>Cerrar</button>
          </div>
          <div className="tarjeta-cuerpo">
            {!elegida ? (
              <Buscador fondoId={fondoId} busca={abierta.busca} excluir={entidad.id} alElegir={(id, nombre) => setElegida({ id, nombre })} />
            ) : (
              <>
                <p style={{ marginTop: 0 }}><b>{elegida.nombre}</b> <button type="button" className="enlace" onClick={() => setElegida(null)}>Cambiar</button></p>
                {abierta.conFecha && (
                  <>
                    <p className="pista" style={{ marginBottom: 0 }}>Vigencia de la relación (opcional):</p>
                    <SelectorFecha valor={control} subtipos={["simple", "rango"]} alCambiar={(c, x) => { setControl(c); setVigencia(x); }} />
                  </>
                )}
                <div className="campo">
                  <label htmlFor="nota-vinculo">Nota sobre su naturaleza (opcional)</label>
                  <input id="nota-vinculo" className="entrada" maxLength={500} value={nota} onChange={(e) => setNota(e.target.value)} />
                </div>
                {error && <div className="aviso error" role="alert">{error}</div>}
                <div className="acciones">
                  <button type="button" className="boton chico primario" onClick={confirmar}>Declarar vínculo</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

// --- Identificación: formas del nombre e identificadores ---------------------------------------------

function FormasDelNombre({ ficha, entidad, puede, alCambiar, historicos }: {
  ficha: Ficha; entidad: EntidadVocabulario; puede: boolean; alCambiar: Props["alCambiar"]; historicos?: boolean;
}) {
  const [abierta, setAbierta] = useState(false);
  const [tipo, setTipo] = useState<Nombre["tipo"]>(historicos ? "historica" : "otra");
  const [nombre, setNombre] = useState("");
  const [idioma, setIdioma] = useState("");
  const [regla, setRegla] = useState("");
  const [control, setControl] = useState<ControlFecha>(controlInicial("rango"));
  const [vigencia, setVigencia] = useState<string | null>(null);
  const [error, setError] = useState("");
  const lista = ficha.nombres.filter((n) => (historicos ? n.tipo === "historica" : n.tipo !== "historica"));

  async function agregar(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await enviar(`/api/vocabulario/${entidad.id}/nombres`, "POST", {
        tipo, nombre, idioma: idioma || null, regla: regla || null, vigencia_edtf: vigencia,
      });
      setAbierta(false); setNombre(""); setIdioma(""); setRegla(""); setVigencia(null);
      alCambiar();
    } catch (err) {
      setError(mensaje(err, "No se pudo agregar."));
    }
  }

  async function anular(n: Nombre) {
    if (!window.confirm(`¿Anular «${n.nombre}»? No se borra: queda en el historial.`)) return;
    await enviar(`/api/vocabulario/${entidad.id}/registros/nombre/${n.id}/anular`, "POST").catch(() => undefined);
    alCambiar();
  }

  return (
    <>
      {lista.length === 0 && <p className="meta" style={{ margin: 0 }}>{historicos ? "Sin nombres históricos registrados." : "Sin otras formas registradas."}</p>}
      {lista.map((n) => (
        <div className="fila" key={n.id} style={{ padding: "6px 0" }}>
          <div className="fila-principal">
            <div className="nombre">{n.nombre}</div>
            <div className="meta">
              {TIPO_NOMBRE_FORMA[n.tipo]}{n.idioma && ` · lengua ${n.idioma}`}{n.regla && ` · según ${n.regla}`}
              {n.vigencia_legible && ` · ${n.vigencia_legible}`}
            </div>
          </div>
          {puede && <button type="button" className="enlace" onClick={() => anular(n)}>Anular</button>}
        </div>
      ))}
      {puede && !abierta && (
        <button type="button" className="boton chico" style={{ marginTop: 6 }} onClick={() => setAbierta(true)}>
          + {historicos ? "Nombre histórico" : "Otra forma del nombre"}
        </button>
      )}
      {abierta && (
        <form className="form-entidad" onSubmit={agregar}>
          <div className="rejilla">
            {!historicos && (
              <select className="selector" aria-label="Tipo de forma" value={tipo} onChange={(e) => setTipo(e.target.value as Nombre["tipo"])}>
                {(["paralela", "normalizada", "otra"] as const).map((t) => <option key={t} value={t}>{TIPO_NOMBRE_FORMA[t]}</option>)}
              </select>
            )}
            <input className="entrada" required aria-label="Nombre" placeholder="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} />
            {tipo === "paralela" && <input className="entrada" aria-label="Lengua" placeholder="Lengua (ISO 639, p. ej. en)" maxLength={12} value={idioma} onChange={(e) => setIdioma(e.target.value)} />}
            {tipo === "normalizada" && <input className="entrada" aria-label="Regla" placeholder="Regla o convención" value={regla} onChange={(e) => setRegla(e.target.value)} />}
          </div>
          {(historicos || tipo === "otra") && (
            <>
              <p className="pista" style={{ marginBottom: 0 }}>Periodo en que llevó ese nombre (opcional):</p>
              <SelectorFecha valor={control} subtipos={["rango", "simple"]} alCambiar={(c, x) => { setControl(c); setVigencia(x); }} />
            </>
          )}
          {error && <div className="aviso error" role="alert">{error}</div>}
          <div className="acciones" style={{ marginTop: 8 }}>
            <button type="submit" className="boton chico primario">Agregar</button>
            <button type="button" className="boton chico" onClick={() => setAbierta(false)}>Cancelar</button>
          </div>
        </form>
      )}
    </>
  );
}

function Identificadores({ ficha, entidad, puede, alCambiar }: { ficha: Ficha; entidad: EntidadVocabulario; puede: boolean; alCambiar: Props["alCambiar"] }) {
  const [esquema, setEsquema] = useState("interno");
  const [valor, setValor] = useState("");
  const [abierta, setAbierta] = useState(false);
  const [error, setError] = useState("");

  async function agregar(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await enviar(`/api/vocabulario/${entidad.id}/identificadores`, "POST", { esquema, valor });
      setValor(""); setAbierta(false);
      alCambiar();
    } catch (err) {
      setError(mensaje(err, "No se pudo agregar."));
    }
  }

  async function anular(id: string) {
    if (!window.confirm("¿Anular este identificador? No se borra: queda en el historial.")) return;
    await enviar(`/api/vocabulario/${entidad.id}/registros/identificador/${id}/anular`, "POST").catch(() => undefined);
    alCambiar();
  }

  return (
    <>
      {(ficha.identificadores || []).length === 0 && <p className="meta" style={{ margin: 0 }}>Sin identificadores.</p>}
      {(ficha.identificadores || []).map((i) => (
        <div className="fila" key={i.id} style={{ padding: "6px 0" }}>
          <span className={`insignia ${i.externo ? "agente" : "proceso"}`}>{i.externo ? `Autoridad externa · ${ESQUEMA_NOMBRE[i.esquema]}` : ESQUEMA_NOMBRE[i.esquema]}</span>
          <div className="fila-principal">
            <div className="nombre">{i.uri ? <a href={i.uri} target="_blank" rel="noreferrer">{i.valor}</a> : i.valor}</div>
          </div>
          {puede && <button type="button" className="enlace" onClick={() => anular(i.id)}>Anular</button>}
        </div>
      ))}
      {puede && !abierta && <button type="button" className="boton chico" style={{ marginTop: 6 }} onClick={() => setAbierta(true)}>+ Identificador</button>}
      {abierta && (
        <form className="form-entidad" onSubmit={agregar}>
          <div className="rejilla">
            <select className="selector" aria-label="Esquema" value={esquema} onChange={(e) => setEsquema(e.target.value)}>
              {Object.entries(ESQUEMA_NOMBRE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <input className="entrada" required aria-label="Valor" value={valor} onChange={(e) => setValor(e.target.value)}
                   placeholder={esquema === "wikidata" ? "Q2841" : esquema === "viaf" ? "Número VIAF" : "Valor"} />
          </div>
          {error && <div className="aviso error" role="alert">{error}</div>}
          <div className="acciones" style={{ marginTop: 8 }}>
            <button type="submit" className="boton chico primario">Agregar</button>
            <button type="button" className="boton chico" onClick={() => setAbierta(false)}>Cancelar</button>
          </div>
        </form>
      )}
    </>
  );
}

// --- Descripción: línea de tiempo institucional (rico:Event) ------------------------------------------

function LineaDeTiempo({ ficha, entidad, puede, alCambiar }: { ficha: Ficha; entidad: EntidadVocabulario; puede: boolean; alCambiar: Props["alCambiar"] }) {
  const [abierta, setAbierta] = useState(false);
  const [tipo, setTipo] = useState("creacion");
  const [descripcion, setDescripcion] = useState("");
  const [control, setControl] = useState<ControlFecha>(controlInicial("simple"));
  const [edtf, setEdtf] = useState<string | null>(null);
  const [error, setError] = useState("");
  const hitos = ficha.hitos || [];

  async function agregar(e: FormEvent) {
    e.preventDefault();
    if (!edtf) return;
    setError("");
    try {
      await enviar(`/api/vocabulario/${entidad.id}/hitos`, "POST", { tipo, descripcion, edtf });
      setAbierta(false); setDescripcion(""); setEdtf(null); setControl(controlInicial("simple"));
      alCambiar();
    } catch (err) {
      setError(mensaje(err, "No se pudo agregar el hito."));
    }
  }

  async function anular(id: string) {
    if (!window.confirm("¿Anular este hito? No se borra: queda en el historial.")) return;
    await enviar(`/api/vocabulario/${entidad.id}/registros/hito/${id}/anular`, "POST").catch(() => undefined);
    alCambiar();
  }

  return (
    <>
      <p className="meta" style={{ marginTop: 0 }}>
        Hechos fechados y discretos de su historia. Cada hito es un <code className="rico">rico:Event</code> unido al agente por{" "}
        <code className="rico">rico:affectsOrAffected</code> (RiC-R059).
      </p>
      {hitos.length === 0 ? <p className="meta">Sin hitos registrados.</p> : (
        <ul className="linea-tiempo">
          {hitos.map((h) => (
            <li key={h.id}>
              <b>{h.fecha_legible}</b> · {HITO_NOMBRE[h.tipo]} — {h.descripcion}{" "}
              {puede && <button type="button" className="enlace" onClick={() => anular(h.id)}>Anular</button>}
            </li>
          ))}
        </ul>
      )}
      {puede && !abierta && <button type="button" className="boton chico" style={{ marginTop: 6 }} onClick={() => setAbierta(true)}>+ Hito</button>}
      {abierta && (
        <form className="form-entidad" onSubmit={agregar}>
          <div className="rejilla">
            <select className="selector" aria-label="Tipo de hito" value={tipo} onChange={(e) => setTipo(e.target.value)}>
              {Object.entries(HITO_NOMBRE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <input className="entrada" required maxLength={500} aria-label="Descripción" placeholder="Descripción breve"
                   value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
          </div>
          <SelectorFecha valor={control} subtipos={["simple", "rango"]} alCambiar={(c, x) => { setControl(c); setEdtf(x); }} />
          {error && <div className="aviso error" role="alert">{error}</div>}
          <div className="acciones" style={{ marginTop: 8 }}>
            <button type="submit" className="boton chico primario" disabled={!edtf}>Agregar</button>
            <button type="button" className="boton chico" onClick={() => setAbierta(false)}>Cancelar</button>
          </div>
        </form>
      )}
    </>
  );
}

// --- Fichas por clase ------------------------------------------------------------------------------------

function FichaAgente(p: Props) {
  const { entidad: e, ficha: f, puede, fondoId, alCambiar } = p;
  const comun = { puede, entidadId: e.id, alCambiar };
  const corporativa = e.subtipo === "entidad_corporativa" || e.subtipo === "grupo";
  return (
    <>
      <Area titulo="1. Área de identificación" insignia={<code className="rico">{f.clase_rico}</code>}>
        {e.subtipo !== "mecanismo" && (
          <p style={{ marginTop: 0 }}>
            <button type="button" className="enlace" onClick={() => descargar(`/api/publico/eac/${e.id}`).catch(() => undefined)}>
              Descargar la ficha en EAC-CPF 2.0 (.xml)</button>
          </p>
        )}
        <dl className="par-dato">
          <dt>Tipo de entidad</dt><dd>{e.subtipo ? SUBTIPO_NOMBRE[e.subtipo] || e.subtipo : "Agente"}</dd>
          <dt>Forma autorizada del nombre</dt><dd><b>{e.nombre}</b> <span className="meta">(se corrige desde la descripción, que la verifica contra el vocabulario)</span></dd>
          {e.subtipo === "mecanismo" && (
            <TextoEditable etiqueta="Versión exacta (obligatoria)" campo="version" valor={f.campos.version} {...comun}
                           pista="La versión del modelo o del programa. Si el mecanismo actuó sobre un archivo publicado (identificar su formato, convertirlo), se exporta con esa acción como rico:technicalCharacteristics; el motor de análisis no se exporta, porque es procedencia del dato." />
          )}
        </dl>
        {f.falta_version && <div className="aviso alerta">Falta la versión de este mecanismo: sin ella no se puede atribuir un resultado a una versión precisa.</div>}
        {f.usos_tecnicos && <UsosTecnicos usos={f.usos_tecnicos} />}
        <h4>Otras formas del nombre</h4>
        <FormasDelNombre ficha={f} entidad={e} puede={puede} alCambiar={alCambiar} />
        <h4>Identificadores</h4>
        <Identificadores ficha={f} entidad={e} puede={puede} alCambiar={alCambiar} />
      </Area>

      <Area titulo="2. Área de descripción">
        <dl className="par-dato">
          <FechaEditable etiqueta="Fechas de existencia" campo="existencia_edtf" edtf={(f.campos.existencia_edtf as string) || null}
                         legible={f.existencia_legible} subtipos={["rango", "simple"]} {...comun} />
          <TextoEditable etiqueta={e.subtipo === "persona" ? "Historia (biografía)" : "Historia"} campo="historia" valor={f.campos.historia} multilinea {...comun} />
          {corporativa && <ListaEditable etiqueta="Estatuto jurídico" campo="estatuto_juridico" valor={(f.campos.estatuto_juridico as string) || null} opciones={ESTATUTO} {...comun} />}
          <TextoEditable etiqueta="Estructura interna o genealogía" campo="estructura" valor={f.campos.estructura} multilinea {...comun} />
          <TextoEditable etiqueta="Contexto general" campo="contexto_general" valor={f.campos.contexto_general} multilinea {...comun} />
        </dl>
        <h4>Línea de tiempo institucional</h4>
        <LineaDeTiempo ficha={f} entidad={e} puede={puede} alCambiar={alCambiar} />
        <h4>Lugares de actuación</h4>
        <Vinculos vinculos={f.vinculos} tipos={["lugar_agente"]} opciones={OPCIONES.agente_lugares} vacio="Sin lugares de actuación."
                  entidad={e} fondoId={fondoId} puede={puede} alCambiar={alCambiar} />
        <h4>Funciones y actividades</h4>
        <Vinculos vinculos={f.vinculos} tipos={["ejercida_por"]} opciones={[]} entidad={e} fondoId={fondoId} puede={false} alCambiar={alCambiar}
                  vacio="Ninguna actividad registrada como ejercida por este agente. Se declaran al describir o desde la ficha de la actividad." />
        <h4>Mandato que lo creó o estableció</h4>
        <Vinculos vinculos={f.vinculos} tipos={["creado_por"]} opciones={OPCIONES.agente_creacion} vacio="Sin mandato de creación registrado."
                  entidad={e} fondoId={fondoId} puede={puede} alCambiar={alCambiar} />
      </Area>

      <Area titulo="3. Área de relaciones">
        <Vinculos vinculos={f.vinculos} tipos={["subordinado", "sucesor", "asociado", "ocupa_cargo", "cargo_en", "miembro", "dirige", "subdivision",
                 "progenitor_de", "hermano_de", "conyuge_de", "familiar_de"]}
                  opciones={OPCIONES.agente_relaciones}
                  vacio="Sin relaciones con otros agentes." entidad={e} fondoId={fondoId} puede={puede} alCambiar={alCambiar} />
      </Area>

      <AreaControl {...p} titulo="4. Área de control" />
    </>
  );
}

// Nivel de detalle (ISAAR 5.4.5 / ISDF 5.4.5): mínimo, parcial o completo.
export const NIVEL_FICHA: Record<string, string> = { minimo: "Ficha mínima", parcial: "Ficha parcial", completo: "Ficha completa" };
const ESTADO_ELABORACION: Record<string, string> = { borrador: "Borrador", revisado: "Revisado", definitivo: "Definitivo" };
const TIPO_FUNCION: Record<string, string> = { funcion: "Función", subfuncion: "Subfunción", proceso: "Proceso",
  actividad: "Actividad", transaccion: "Transacción" };

// Área de control común a la ficha ISAAR (agente) y a la ISDF (función), hallazgos VOC-01 y VOC-03.
function AreaControl(p: Props & { titulo: string }) {
  const { entidad: e, ficha: f, puede, alCambiar } = p;
  const comun = { puede, entidadId: e.id, alCambiar };
  const nivel = f.control.nivel_detalle || "minimo";
  return (
    <Area titulo={p.titulo} abierta={false}
          insignia={f.control.nivel_detalle && <span className={`insignia ${nivel === "completo" ? "bien" : "proceso"}`}>{NIVEL_FICHA[nivel]}</span>}>
      <dl className="par-dato">
        <dt>Identificador del registro</dt><dd><code className="rico">{f.control.identificador_registro}</code></dd>
        <TextoEditable etiqueta="Institución responsable" campo="institucion_responsable" valor={f.control.institucion_responsable} {...comun} />
        <TextoEditable etiqueta="Reglas o convenciones" campo="reglas" valor={f.control.reglas} {...comun} />
        <ListaEditable etiqueta="Estado de elaboración" campo="estado_elaboracion" valor={f.control.estado_elaboracion || null}
                       opciones={ESTADO_ELABORACION} {...comun} />
        <dt>Nivel de detalle</dt>
        <dd>{NIVEL_FICHA[nivel]} <span className="meta">(se calcula: parcial con el primer dato del área de descripción;
          completo con fechas, historia, otro elemento y las fuentes)</span></dd>
        <dt>Creación de la ficha</dt><dd>{fecha(f.control.creada_en)}</dd>
        <dt>Última revisión</dt><dd>{f.control.revisada_en ? fecha(f.control.revisada_en) : "—"} <span className="meta">(tomada de la auditoría)</span></dd>
        <TextoEditable etiqueta="Lenguas (ISO 639-3, separadas por coma)" campo="lenguas" valor={(f.control.lenguas || []).join(", ")} {...comun} />
        <TextoEditable etiqueta="Escrituras (ISO 15924, separadas por coma)" campo="escrituras" valor={(f.control.escrituras || []).join(", ")} {...comun} />
        <TextoEditable etiqueta="Fuentes" campo="fuentes" valor={f.campos.fuentes} multilinea {...comun} />
        <TextoEditable etiqueta="Notas de mantenimiento" campo="notas_mantenimiento" valor={f.control.notas_mantenimiento} multilinea {...comun} />
      </dl>
    </Area>
  );
}

function Mapa({ lat, lon }: { lat: number; lon: number }) {
  const d = 0.04;
  const caja = [lon - d, lat - d * 0.6, lon + d, lat + d * 0.6].map((x) => x.toFixed(5)).join(",");
  return (
    <>
      <iframe className="mapa-lugar" title="Ubicación en el mapa" loading="lazy"
              src={`https://www.openstreetmap.org/export/embed.html?bbox=${caja}&layer=mapnik&marker=${lat},${lon}`} />
      <div className="pista">
        Mapa de OpenStreetMap, sin costo y sin clave.{" "}
        <a href={`https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=13/${lat}/${lon}`} target="_blank" rel="noreferrer">Abrir en OpenStreetMap</a>
      </div>
    </>
  );
}

function FichaLugar(p: Props) {
  const { entidad: e, ficha: f, puede, fondoId, alCambiar } = p;
  const comun = { puede, entidadId: e.id, alCambiar };
  const lat = f.campos.latitud as number | null;
  const lon = f.campos.longitud as number | null;
  const [editandoCoord, setEditandoCoord] = useState(false);
  const [la, setLa] = useState(lat == null ? "" : String(lat));
  const [lo, setLo] = useState(lon == null ? "" : String(lon));
  const [error, setError] = useState("");

  async function guardarCoordenadas(ev: FormEvent) {
    ev.preventDefault();
    setError("");
    try {
      await enviar(`/api/vocabulario/${e.id}`, "PATCH", { latitud: la === "" ? null : Number(la.replace(",", ".")),
        longitud: lo === "" ? null : Number(lo.replace(",", ".")) });
      setEditandoCoord(false);
      alCambiar();
    } catch (err) {
      setError(mensaje(err, "No se pudieron guardar las coordenadas."));
    }
  }

  return (
    <>
      <Area titulo="Ficha del lugar" insignia={<code className="rico">{f.clase_rico}</code>}>
        <dl className="par-dato">
          <ListaEditable etiqueta="Tipo de lugar" campo="tipo_lugar" valor={(f.campos.tipo_lugar as string) || null} opciones={TIPO_LUGAR} {...comun} />
          <dt>Coordenadas</dt>
          <dd>
            {editandoCoord ? (
              <form onSubmit={guardarCoordenadas} className="acciones" style={{ flexWrap: "wrap", alignItems: "center" }}>
                <input className="entrada" style={{ width: 130 }} aria-label="Latitud" placeholder="Latitud" value={la} onChange={(x) => setLa(x.target.value)} />
                <input className="entrada" style={{ width: 130 }} aria-label="Longitud" placeholder="Longitud" value={lo} onChange={(x) => setLo(x.target.value)} />
                <button type="submit" className="boton chico primario">Guardar</button>
                <button type="button" className="boton chico" onClick={() => setEditandoCoord(false)}>Cancelar</button>
                {error && <div className="aviso error" role="alert" style={{ width: "100%" }}>{error}</div>}
              </form>
            ) : (
              <>
                {lat != null && lon != null ? <>{lat}, {lon} <code className="rico">rico:geographicalCoordinates</code></> : <span className="meta">Sin registrar</span>}
                {puede && <> <button type="button" className="enlace" onClick={() => setEditandoCoord(true)}>{lat != null ? "Cambiar" : "Agregar"}</button></>}
              </>
            )}
          </dd>
          <TextoEditable etiqueta="Historia o nota" campo="historia" valor={f.campos.historia} multilinea {...comun} />
        </dl>
        {lat != null && lon != null && <Mapa lat={lat} lon={lon} />}
      </Area>
      <Area titulo="Jerarquía">
        <h4 style={{ marginTop: 0 }}>Lugar superior</h4>
        <Vinculos vinculos={f.vinculos} tipos={["lugar_superior"]} opciones={OPCIONES.lugar} entidad={e} fondoId={fondoId} puede={puede}
                  alCambiar={alCambiar} vacio="No está registrado dentro de otro lugar." />
        <h4>Lugares que contiene</h4>
        {(f.contiene || []).length === 0 ? <p className="meta">Ninguno.</p> : (f.contiene || []).map((v) => (
          <div key={v.relacion_id} className="fila" style={{ padding: "6px 0" }}>
            <div className="fila-principal"><div className="nombre">{v.con && <Link to={`/vocabularios/${v.con.id}`}>{v.con.nombre}</Link>}</div></div>
            <PropiedadRico v={v} />
          </div>
        ))}
      </Area>
      <Area titulo="Nombres históricos">
        <p className="meta" style={{ marginTop: 0 }}>Cada nombre es un <code className="rico">rico:PlaceName</code> del mismo lugar, con su periodo.</p>
        <FormasDelNombre ficha={f} entidad={e} puede={puede} alCambiar={alCambiar} historicos />
      </Area>
    </>
  );
}

function SuperiorSkos({ ficha: f, entidad: e, puede, fondoId, alCambiar }: Props) {
  const [abierta, setAbierta] = useState(false);
  const [error, setError] = useState("");
  async function fijar(id: string | null) {
    setError("");
    try {
      await enviar(`/api/vocabulario/${e.id}/concepto-superior`, "PUT", { superior_id: id });
      setAbierta(false);
      alCambiar();
    } catch (err) {
      setError(mensaje(err, "No se pudo ubicar en el árbol."));
    }
  }
  return (
    <>
      <dl className="par-dato">
        <dt>Más amplio que esta función <code className="rico">skos:broader</code></dt>
        <dd>
          {f.skos?.broader ? <Link to={`/vocabularios/${f.skos.broader.id}`}>{f.skos.broader.nombre}</Link> : <span className="meta">Función de primer nivel</span>}
          {puede && <> <button type="button" className="enlace" onClick={() => setAbierta(!abierta)}>Cambiar</button></>}
          {puede && f.skos?.broader && <> <button type="button" className="enlace" onClick={() => fijar(null)}>Dejar en primer nivel</button></>}
        </dd>
        <dt>Más específicos <code className="rico">skos:narrower</code></dt>
        <dd>{(f.skos?.narrower || []).length === 0 ? <span className="meta">Ninguno</span>
          : f.skos!.narrower.map((n, i) => <span key={n.id}>{i > 0 && ", "}<Link to={`/vocabularios/${n.id}`}>{n.nombre}</Link></span>)}</dd>
      </dl>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {abierta && <Buscador fondoId={fondoId} busca="tipo_actividad" excluir={e.id} alElegir={(id) => fijar(id)} />}
    </>
  );
}

function FichaTipoActividad(p: Props) {
  const { entidad: e, ficha: f, puede, fondoId, alCambiar } = p;
  const comun = { puede, entidadId: e.id, alCambiar };
  return (
    <>
      <Area titulo="Identificación y descripción (ISDF)" insignia={<code className="rico">skos:notation · skos:scopeNote</code>}>
        <dl className="par-dato">
          <ListaEditable etiqueta="Tipo" campo="tipo_funcion" valor={(f.campos.tipo_funcion as string) || null} opciones={TIPO_FUNCION} {...comun} />
          <TextoEditable etiqueta="Código de clasificación" campo="codigo_clasificacion" valor={f.campos.codigo_clasificacion}
                         pista="El código del cuadro de clasificación documental (por ejemplo, 200.12)." {...comun} />
          <TextoEditable etiqueta="Fechas (EDTF)" campo="existencia_edtf" valor={f.campos.existencia_edtf} {...comun} />
          <TextoEditable etiqueta="Historia o nota de alcance" campo="historia" valor={f.campos.historia} multilinea {...comun} />
        </dl>
      </Area>
      <Area titulo="Otras formas del nombre" insignia={<code className="rico">skos:altLabel</code>}>
        <FormasDelNombre ficha={f} entidad={e} puede={puede} alCambiar={alCambiar} />
      </Area>
      <Area titulo="Posición en el árbol de funciones" insignia={<code className="rico">{f.clase_rico} · skos:Concept</code>}>
        <p className="meta" style={{ marginTop: 0 }}>
          La jerarquía función → subfunción → trámite no existe en RiC-O; se expresa con SKOS, que la complementa sin
          duplicarla. Admite tantos niveles como el fondo necesite, sin ciclos.
        </p>
        <SuperiorSkos {...p} />
      </Area>
      <Area titulo="Serie documental que produce (TRD)">
        <Vinculos vinculos={f.vinculos} tipos={["serie_producida"]} opciones={OPCIONES.tipo_actividad.slice(0, 1)} entidad={e} fondoId={fondoId}
                  puede={puede} alCambiar={alCambiar} vacio="Sin serie declarada." />
      </Area>
      <Area titulo="Mandato que creó esta competencia">
        <Vinculos vinculos={f.vinculos} tipos={["competencia_creada_por"]} opciones={OPCIONES.tipo_actividad.slice(1)} entidad={e}
                  fondoId={fondoId} puede={puede} alCambiar={alCambiar} vacio="Sin mandato de creación registrado." />
      </Area>
      <Area titulo={`Actividades con este tipo · ${(f.actividades || []).length}`}>
        {(f.actividades || []).length === 0 ? <p className="meta" style={{ margin: 0 }}>Ninguna actividad lo lleva asignado todavía.</p>
          : (f.actividades || []).map((a) => <div key={a.id} className="fila" style={{ padding: "6px 0" }}><Link to={`/vocabularios/${a.id}`}>{a.nombre}</Link></div>)}
      </Area>
      <AreaControl {...p} titulo="Área de control (ISDF)" />
    </>
  );
}

function FichaActividad(p: Props) {
  const { entidad: e, ficha: f, puede, fondoId, alCambiar } = p;
  const c = f.contexto;
  return (
    <>
      <Area titulo="Contexto de la actividad" insignia={<code className="rico">{f.clase_rico}</code>}>
        <dl className="par-dato">
          <dt>Tipo de actividad <code className="rico">rico:hasActivityType</code></dt>
          <dd>{c?.tipo_actividad ? <Link to={`/vocabularios/${c.tipo_actividad.id}`}>{c.tipo_actividad.nombre}</Link> : <span className="meta">Sin tipo asignado (se asigna al describir)</span>}</dd>
          <dt>Periodo</dt><dd>{c?.periodo?.fecha_legible || <span className="meta">Sin fechas</span>}</dd>
        </dl>
        <h4>Ejercida por</h4>
        <Vinculos vinculos={f.vinculos} tipos={["ejercida_por"]} opciones={OPCIONES.actividad.slice(1, 2)} entidad={e} fondoId={fondoId}
                  puede={puede} alCambiar={alCambiar} vacio="Sin agente registrado." />
        <h4>Regulada por</h4>
        <Vinculos vinculos={f.vinculos} tipos={["mandato_actividad"]} opciones={OPCIONES.actividad.slice(2)} entidad={e} fondoId={fondoId}
                  puede={puede} alCambiar={alCambiar} vacio="Sin mandato registrado." />
      </Area>
      <Area titulo="Estructura interna">
        <p className="meta" style={{ marginTop: 0 }}>
          Sub-actividades unidas por <code className="rico">rico:hasDirectSubevent</code>. No es el árbol de funciones: ese es SKOS, entre tipos de actividad.
        </p>
        <Vinculos vinculos={f.vinculos} tipos={["actividad_mayor"]} opciones={OPCIONES.actividad.slice(0, 1)} entidad={e} fondoId={fondoId}
                  puede={puede} alCambiar={alCambiar} vacio="No es sub-actividad de otra, ni tiene sub-actividades." />
      </Area>
    </>
  );
}

function FichaMandato(p: Props) {
  const { entidad: e, ficha: f, puede, fondoId, alCambiar } = p;
  return (
    <>
      <Area titulo="Datos del mandato" insignia={<code className="rico">{f.clase_rico}</code>}>
        <dl className="par-dato">
          <dt>Tipo de instrumento <code className="rico">rico:hasOrHadMandateType</code></dt><dd>{e.subtipo ? SUBTIPO_NOMBRE[e.subtipo] || e.subtipo : "—"}</dd>
          <dt>Fecha de expedición</dt><dd>{f.expedicion?.fecha_legible || <span className="meta">Sin fecha</span>}</dd>
        </dl>
        <h4>Entidad que lo expidió</h4>
        <Vinculos vinculos={f.vinculos} tipos={["expedido_por"]} opciones={OPCIONES.mandato.slice(1, 2)} entidad={e} fondoId={fondoId}
                  puede={puede} alCambiar={alCambiar} vacio="Sin entidad emisora registrada." />
        <h4>Actividades que regula</h4>
        <Vinculos vinculos={f.vinculos} tipos={["mandato_actividad"]} opciones={[]} entidad={e} fondoId={fondoId} puede={false}
                  alCambiar={alCambiar} vacio="Ninguna actividad registrada." />
        <h4>Agentes y competencias que creó</h4>
        <Vinculos vinculos={f.vinculos} tipos={["creado_por", "competencia_creada_por"]} opciones={OPCIONES.mandato.slice(2)} entidad={e}
                  fondoId={fondoId} puede={puede} alCambiar={alCambiar} vacio="No hay creación registrada." />
      </Area>
      <Area titulo="Jerarquía normativa">
        <Vinculos vinculos={f.vinculos} tipos={["mandato_superior"]} opciones={OPCIONES.mandato.slice(0, 1)} entidad={e} fondoId={fondoId}
                  puede={puede} alCambiar={alCambiar} vacio="No deriva de otra norma ni tiene normas derivadas registradas." />
      </Area>
    </>
  );
}

// Regla de retención de la TRD (rico:Rule): la serie que regula la hereda a sus expedientes.
function FichaRegla(p: Props) {
  const { entidad: e, ficha: f, puede, fondoId, alCambiar } = p;
  const comun = { puede, entidadId: e.id, alCambiar };
  return (
    <>
      <Area titulo="Regla de retención (TRD)" insignia={<code className="rico">{f.clase_rico}</code>}>
        <dl className="par-dato">
          <TextoEditable etiqueta="Años en el archivo de gestión" campo="retencion_gestion_anios"
                         valor={f.campos.retencion_gestion_anios != null ? String(f.campos.retencion_gestion_anios) : null} {...comun} />
          <TextoEditable etiqueta="Años en el archivo central" campo="retencion_central_anios"
                         valor={f.campos.retencion_central_anios != null ? String(f.campos.retencion_central_anios) : null} {...comun} />
          <ListaEditable etiqueta="Disposición final" campo="disposicion_final" valor={(f.campos.disposicion_final as string) || null}
                         opciones={DISPOSICION} {...comun} />
          <TextoEditable etiqueta="Procedimiento" campo="historia" valor={f.campos.historia} multilinea {...comun} />
        </dl>
      </Area>
      <Area titulo="Series o subseries que regula">
        <Vinculos vinculos={f.vinculos} tipos={["regla_serie"]}
                  opciones={[{ tipo: "regla_serie", etiqueta: "Regula la retención de", busca: "serie" }]} entidad={e} fondoId={fondoId}
                  puede={puede} alCambiar={alCambiar} vacio="Todavía no regula ninguna serie." />
      </Area>
    </>
  );
}

function FichaGeneral(p: Props) {
  const { entidad: e, ficha: f, puede, alCambiar } = p;
  return (
    <Area titulo="Ficha" insignia={<code className="rico">{f.clase_rico}</code>}>
      <dl className="par-dato">
        <TextoEditable etiqueta="Nota de alcance" campo="historia" valor={f.campos.historia} multilinea puede={puede} entidadId={e.id} alCambiar={alCambiar} />
      </dl>
    </Area>
  );
}

export function FichaAutoridad(p: Props) {
  if (p.entidad.estado !== "activa") return null;
  switch (p.entidad.clase) {
    case "agente": return <FichaAgente {...p} />;
    case "lugar": return <FichaLugar {...p} />;
    case "tipo_actividad": return <FichaTipoActividad {...p} />;
    case "actividad": return <FichaActividad {...p} />;
    case "mandato": return <FichaMandato {...p} />;
    case "regla": return <FichaRegla {...p} />;
    default: return <FichaGeneral {...p} />;
  }
}

// Qué hizo este mecanismo en el sistema: preservación y descripción apuntan
// a este mismo registro, no guardan el nombre del programa como texto.
const USO_NOMBRE: Record<string, string> = {
  "instanciaciones.mecanismo_identificacion_id": "Identificaciones de formato",
  migraciones: "Migraciones de formato",
  verificaciones_integridad: "Verificaciones de integridad",
  segundas_copias: "Segundas copias",
  restauraciones: "Restauraciones",
  "entidades_vocabulario.motor_id": "Entidades propuestas",
  "relaciones.motor_id": "Relaciones propuestas",
  "fechas.motor_id": "Fechas propuestas",
  "actividades.motor_id": "Actividades propuestas",
  "recursos_documentales.motor_id": "Descripciones propuestas",
};

function UsosTecnicos({ usos }: { usos: Record<string, number> }) {
  const filas = Object.entries(usos);
  return (
    <>
      <h4>Acciones técnicas que ejecutó</h4>
      {filas.length === 0 ? <p className="meta">Todavía ninguna.</p> : (
        <dl className="par-dato">
          {filas.flatMap(([clave, n]) => [<dt key={clave}>{USO_NOMBRE[clave] || clave}</dt>, <dd key={clave + "-n"}>{n}</dd>])}
        </dl>
      )}
    </>
  );
}
