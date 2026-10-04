import { Fragment, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { EnlaceHistoria } from "@/components/Historia";
import { CadenaActividad, type ContextoActividad } from "@/components/ContextoActividad";
import {
  CLASIFICACION_VACIA, CamposRegistro, DATOS_PERSONALES, IDIOMAS, ISADG_TEXTOS, PartesDocumentales, camposVacios, clasificacionParaEnviar,
  proteccionParaEnviar,
  parteParaEnviar, partePendiente,
  type CamposRegistroValor, type Clasificacion, type ParteBorrador,
} from "@/components/DescripcionV3";
import { CompletitudDescripcion, OriginalesFisicos, type InstanciacionRegistro, type Proteccion } from "@/components/PerfilAgn";
import { FormEntidad, PreguntaVocabulario, type EntidadManual } from "@/components/Vocabulario";
import { ErrorAPI, pedir, puede as tienePermiso } from "@/lib/api";
import {
  EN_VOCABULARIO, NIVEL_NOMBRE, ORIGEN_NOMBRE, ROL_NOMBRE, SUBTIPO_NOMBRE, TIPO_CLASE, TIPO_NOMBRE, nivelesSuperiores,
  verificarVocabulario, type NivelSuperior, type TipoEntidad, type Verificacion,
} from "@/lib/descripcion";
import { fecha } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";

interface EntidadRegistrada {
  relacion_id: string;
  tipo: TipoEntidad;
  valor: string;
  subtipo: string | null;
  rol: string | null;
  codigo_ric: string;
  uri_rico: string | null;
  fragmento: string | null;
  origen: string;
  confianza: number | null;
  fecha_normalizada?: string | null;
  fecha_legible?: string | null;
  edtf?: string | null;
  contexto?: ContextoActividad;
  entidad_id?: string;
  antes_de_fusion?: { id: string; nombre: string };
}

interface ClasificacionGuardada {
  acceso: "publico" | "clasificado" | "reservado";
  fundamento: string;
  reproduccion: Clasificacion["reproduccion"];
  vigente_hasta: string | null;
}

function clasificacionInicial(c: ClasificacionGuardada | null): Clasificacion {
  if (!c) return CLASIFICACION_VACIA;
  return { acceso: c.acceso, fundamento: c.fundamento, hasta: c.vigente_hasta || "", reproduccion: c.reproduccion };
}

interface Registro {
  id: string;
  nivel: string;
  titulo: string;
  alcance_contenido: string | null;
  fondo_id: string;
  incluido_en: { id: string; titulo: string; nivel: string } | null;
  forma_documental: { id: string; nombre: string; origen: string } | null;
  entidades: EntidadRegistrada[];
  instanciaciones: InstanciacionRegistro[];
  proteccion: Proteccion;
  origen_titulo: string | null;
  origen_alcance: string | null;
  publicado_en: string | null;
  actualizado_en: string | null;
  control: Control;
  idiomas: string[];
  origen_idiomas: string | null;
  condiciones_acceso: string | null;
  clasificacion: ClasificacionGuardada | null;
  clasificacion_heredada: (ClasificacionGuardada & { de: string | null }) | null;
  condiciones_uso: string | null;
  historia_archivistica: string | null;
  isadg: Record<string, string | null> & { escrituras: string[] };
  tipo_parte: { id: string; nombre: string } | null;
  partes: { id: string; titulo: string; tipo_parte: string | null; alcance_contenido: string | null;
            instanciaciones: { id: string; nombre: string }[] }[];
  parte_de: { id: string; titulo: string; nivel: string } | null;
  secuencia: { relacion_id: string; id: string; titulo: string; posicion: "precede_a" | "sigue_a"; uri_rico: string }[];
}

// Datos de control del inventario (FUID); los usa el módulo de instrumentos.
interface Control {
  codigo_referencia: string | null;
  caja: string | null;
  carpeta: string | null;
  folios: number | null;
  soporte: string | null;
  tomo: string | null;
  otra_unidad: string | null;
  frecuencia_consulta: string | null;
}

const CAMPOS_CONTROL: { clave: keyof Control; nombre: string; pista?: string }[] = [
  { clave: "codigo_referencia", nombre: "Código de referencia", pista: "p. ej. CO-AM-114" },
  { clave: "caja", nombre: "Caja" },
  { clave: "carpeta", nombre: "Carpeta" },
  { clave: "folios", nombre: "N.º de folios" },
  { clave: "soporte", nombre: "Soporte", pista: "Papel, electrónico…" },
  { clave: "tomo", nombre: "Tomo" },
  { clave: "otra_unidad", nombre: "Otra unidad de conservación", pista: "Rollo, sobre…" },
  { clave: "frecuencia_consulta", nombre: "Frecuencia de consulta", pista: "alta, media, baja o ninguna" },
];

interface Nueva extends EntidadManual {
  clave: string;
  verif: Verificacion;
}

// Descripción publicada: vista interna (con procedencia de cada dato) y corrección.
export function RegistroDescripcion() {
  const { id = "" } = useParams();
  const navegar = useNavigate();
  const { usuario } = useSesion();
  const puede = tienePermiso(usuario, "descripcion", "escribir");
  const veVocabulario = tienePermiso(usuario, "vocabularios");
  const [registro, setRegistro] = useState<Registro | null>(null);
  const [trabajo, setTrabajo] = useState<string | null>(null);
  const [titulo, setTitulo] = useState("");
  const [alcance, setAlcance] = useState("");
  const [incluido, setIncluido] = useState("");
  const [superiores, setSuperiores] = useState<NivelSuperior[]>([]);
  const [quitar, setQuitar] = useState<string[]>([]);
  const [quitarForma, setQuitarForma] = useState(false);
  const [nuevas, setNuevas] = useState<Nueva[]>([]);
  const [agregando, setAgregando] = useState(false);
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [campos, setCampos] = useState<CamposRegistroValor>(camposVacios());
  const [partes, setPartes] = useState<ParteBorrador[]>([]);
  const [control, setControl] = useState<Record<keyof Control, string>>(
    { codigo_referencia: "", caja: "", carpeta: "", folios: "", soporte: "", tomo: "", otra_unidad: "", frecuencia_consulta: "" });

  function cargar(r: Registro) {
    setRegistro(r);
    setTitulo(r.titulo);
    setAlcance(r.alcance_contenido || "");
    setIncluido(r.incluido_en?.id || "");
    setQuitar([]);
    setQuitarForma(false);
    setNuevas([]);
    setPartes([]);
    setCampos({ idiomas: r.idiomas, clasificacion: clasificacionInicial(r.clasificacion), condicionesAcceso: r.condiciones_acceso || "", condicionesUso: r.condiciones_uso || "",
                historiaArchivistica: r.historia_archivistica || "", secuencia: null,
                isadg: Object.fromEntries(ISADG_TEXTOS.map(([c]) => [c, (r.isadg[c] as string | null) || ""])),
                escrituras: r.isadg.escrituras || [],
                datosPersonales: r.proteccion?.datos_personales || "", notaAccesibilidad: r.proteccion?.nota_accesibilidad || "" });
    setControl({
      codigo_referencia: r.control.codigo_referencia || "", caja: r.control.caja || "", carpeta: r.control.carpeta || "",
      folios: r.control.folios === null ? "" : String(r.control.folios), soporte: r.control.soporte || "",
      tomo: r.control.tomo || "", otra_unidad: r.control.otra_unidad || "",
      frecuencia_consulta: r.control.frecuencia_consulta || "",
    });
    nivelesSuperiores(r.fondo_id, r.nivel).then(setSuperiores).catch(() => undefined);
  }

  useEffect(() => {
    pedir<Registro>(`/api/descripcion/registros/${id}`).then(cargar)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar la descripción."));
  }, [id]);

  async function corregir() {
    setError("");
    try {
      const r = await pedir<{ trabajo_id: string; descripcion: Registro }>(`/api/descripcion/registros/${id}/reabrir`, { method: "POST" });
      setTrabajo(r.trabajo_id);
      cargar(r.descripcion);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo abrir para corregir.");
    }
  }

  async function agregar(e: EntidadManual) {
    if (!registro) return;
    const nueva: Nueva = { ...e, clave: `n${Date.now()}`, verif: { estado: EN_VOCABULARIO.includes(e.tipo) ? "verificando" : "no_aplica", coincidencias: [] } };
    setNuevas((l) => [...l, nueva]);
    setAgregando(false);
    if (!EN_VOCABULARIO.includes(e.tipo)) return;
    const c = await verificarVocabulario(registro.fondo_id, e.tipo, e.valor).catch(() => []);
    setNuevas((l) => l.map((n) => (n.clave === nueva.clave
      ? { ...n, verif: c.length ? { estado: "pregunta", coincidencias: c } : { estado: "resuelta", coincidencias: [], crearNueva: true } }
      : n)));
  }

  async function guardar() {
    if (!registro || !trabajo) return;
    setError("");
    setGuardando(true);
    try {
      const r = await pedir<Registro>(`/api/descripcion/${registro.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          trabajo_id: trabajo, titulo, alcance_contenido: alcance,
          incluido_en_id: incluido !== registro.incluido_en?.id ? incluido : null,
          anular_relaciones: quitar, quitar_forma_documental: quitarForma,
          agregar_entidades: nuevas.map((n) => ({
            tipo: n.tipo, valor: n.valor, subtipo: n.subtipo, rol: n.rol, edtf: n.edtf, fecha_subtipo: n.fecha_subtipo,
            reutilizar_id: n.verif.reutilizarId || null, crear_nueva: !!n.verif.crearNueva,
          })),
          idiomas: campos.idiomas,
          condiciones_acceso: campos.condicionesAcceso,
          // La clasificación solo se envía si cambió: cada cambio queda en la historia de derechos.
          ...(JSON.stringify(campos.clasificacion) === JSON.stringify(clasificacionInicial(registro.clasificacion)) ? {}
            : campos.clasificacion.acceso === "hereda" ? { clasificacion_hereda: true }
            : { clasificacion: clasificacionParaEnviar(campos.clasificacion) }),
          condiciones_uso: campos.condicionesUso,
          historia_archivistica: campos.historiaArchivistica,
          isadg: campos.isadg, escrituras: campos.escrituras,
          precede_a_id: campos.secuencia?.posicion === "precede" ? campos.secuencia.id : null,
          sigue_a_id: campos.secuencia?.posicion === "sigue" ? campos.secuencia.id : null,
          agregar_partes: partes.map(parteParaEnviar),
          control: {
            codigo_referencia: control.codigo_referencia.trim() || null, caja: control.caja.trim() || null,
            carpeta: control.carpeta.trim() || null, soporte: control.soporte.trim() || null,
            folios: control.folios.trim() === "" ? null : Number(control.folios),
            tomo: control.tomo.trim() || null, otra_unidad: control.otra_unidad.trim() || null,
            frecuencia_consulta: control.frecuencia_consulta.trim().toLowerCase() || null,
          },
          proteccion: proteccionParaEnviar(campos, registro.proteccion),
        }),
      });
      setTrabajo(null);
      cargar(r);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudieron guardar los cambios.");
    } finally {
      setGuardando(false);
    }
  }

  async function descartarCambios() {
    if (trabajo) await pedir(`/api/descripcion/${trabajo}/cancelar`, { method: "POST" }).catch(() => undefined);
    setTrabajo(null);
    if (registro) cargar(registro);
  }

  if (!registro) return error ? <div className="aviso error">{error}</div> : <div className="cargando">Cargando…</div>;
  const editando = !!trabajo;
  const pendientes = nuevas.filter((n) => ["verificando", "pregunta"].includes(n.verif.estado)).length
    + partes.filter(partePendiente).length;

  return (
    <>
      <div className="cabecera-nivel" style={{ marginBottom: 0 }}>
        <button type="button" className="enlace" onClick={() => navegar("/descripcion")}>← Volver a Descripción</button>
        <EnlaceHistoria tipo="recurso_documental" id={registro.id} nombre={registro.titulo} />
      </div>
      <h1 style={{ marginTop: 10 }}>{registro.titulo}</h1>
      <p className="sub">
        {NIVEL_NOMBRE[registro.nivel]} · publicada {fecha(registro.publicado_en)}
        {registro.actualizado_en && ` · corregida ${fecha(registro.actualizado_en)}`} · {registro.instanciaciones.map((i) => i.nombre).join(", ")}
      </p>
      {error && <div className="aviso error" role="alert">{error}</div>}

      <div className="tarjeta">
        <div className="tarjeta-cab">
          <span>Descripción</span>
          {puede && !editando && <button type="button" className="boton chico primario" onClick={corregir}>Corregir</button>}
        </div>
        <div className="tarjeta-cuerpo">
          {editando ? (
            <>
              <div className="campo"><label htmlFor="r-titulo">Título</label>
                <input id="r-titulo" className="entrada" value={titulo} onChange={(e) => setTitulo(e.target.value)} /></div>
              <div className="campo"><label htmlFor="r-alcance">Alcance y contenido</label>
                <textarea id="r-alcance" className="entrada" rows={5} value={alcance} onChange={(e) => setAlcance(e.target.value)} /></div>
              <div className="campo"><label htmlFor="r-incluido">Queda incluido en</label>
                <select id="r-incluido" className="selector" value={incluido} onChange={(e) => setIncluido(e.target.value)}>
                  {superiores.map((s) => <option key={s.id} value={s.id}>{NIVEL_NOMBRE[s.nivel]}: {s.titulo}</option>)}
                </select></div>
            </>
          ) : (
            <dl className="pares" style={{ margin: 0 }}>
              <dt>Alcance y contenido</dt><dd>{registro.alcance_contenido || "—"}</dd>
              <dt>Incluido en</dt><dd>{registro.incluido_en ? `${NIVEL_NOMBRE[registro.incluido_en.nivel]}: ${registro.incluido_en.titulo}` : "—"}</dd>
              <dt>Procedencia</dt>
              <dd className="meta" style={{ fontSize: ".82rem" }}>
                Título: {ORIGEN_NOMBRE[registro.origen_titulo || "persona"]}.{" "}
                {registro.origen_alcance && `Alcance: ${ORIGEN_NOMBRE[registro.origen_alcance]}.`}
              </dd>
            </dl>
          )}
        </div>
      </div>

      {registro.parte_de && (
        <div className="aviso" role="note">
          Parte documental{registro.tipo_parte && ` (${registro.tipo_parte.nombre})`} de{" "}
          <Link to={`/descripcion/registro/${registro.parte_de.id}`}>«{registro.parte_de.titulo}»</Link>{" "}
          <code className="rico">rico:isOrWasConstituentOf · RiC-R003i</code>
        </div>
      )}

      {editando ? (
        <CamposRegistro valor={campos} alCambiar={setCampos} fondoId={registro.fondo_id} propuestos={[]} confianza={null}
                        heredada={registro.clasificacion_heredada} />
      ) : (
        <div className="tarjeta">
          <div className="tarjeta-cab">Idioma, condiciones y secuencia</div>
          <div className="tarjeta-cuerpo">
            <dl className="pares" style={{ margin: 0 }}>
              <dt>Idioma del contenido</dt>
              <dd>{registro.idiomas.length ? registro.idiomas.map((c) => `${IDIOMAS[c] || c} (${c})`).join(", ") : "—"}
                {registro.origen_idiomas && <span className="meta"> · {ORIGEN_NOMBRE[registro.origen_idiomas]}</span>}</dd>
              <dt>Condiciones de acceso</dt><dd>{registro.condiciones_acceso || "—"}</dd>
              <dt>Condiciones de uso</dt><dd>{registro.condiciones_uso || "—"}</dd>
              <dt>Datos personales</dt>
              <dd>{DATOS_PERSONALES.find(([k]) => k === registro.proteccion?.datos_personales)?.[1]
                ?? <span className="texto-alerta">Sin revisar (Ley 1581)</span>}</dd>
              <dt>Versión accesible</dt><dd>{registro.proteccion?.nota_accesibilidad || "—"}</dd>
              <dt>Historia archivística</dt><dd>{registro.historia_archivistica || "—"}</dd>
              <dt>Secuencia</dt>
              <dd>{registro.secuencia.length === 0 ? "—" : registro.secuencia.map((x) => (
                <div key={x.relacion_id}>
                  {x.posicion === "precede_a" ? "Precede a" : "Sigue a"} <Link to={`/descripcion/registro/${x.id}`}>{x.titulo}</Link>{" "}
                  <code className="rico">{x.uri_rico}</code>
                </div>
              ))}</dd>
            </dl>
          </div>
        </div>
      )}
      {!editando && <FichaIsadg recursoId={registro.id} actualizado={registro.actualizado_en} />}
      {editando && registro.secuencia.map((x) => (
        <div key={x.relacion_id} className={`fila${quitar.includes(x.relacion_id) ? " tachada" : ""}`}>
          <div className="fila-principal">{x.posicion === "precede_a" ? "Precede a" : "Sigue a"} {x.titulo}</div>
          <button type="button" className="boton chico"
                  onClick={() => setQuitar((q) => (q.includes(x.relacion_id) ? q.filter((y) => y !== x.relacion_id) : [...q, x.relacion_id]))}>
            {quitar.includes(x.relacion_id) ? "Deshacer" : "Quitar"}
          </button>
        </div>
      ))}

      {(registro.nivel === "unidad_documental" || registro.partes.length > 0) && (
        <div className="tarjeta">
          <div className="tarjeta-cab">Partes documentales · {registro.partes.length}</div>
          {registro.partes.length === 0 && !editando && <div className="vacio">Sin partes registradas.</div>}
          {registro.partes.map((p) => (
            <div className="fila" key={p.id}>
              <span className="insignia acento">{p.tipo_parte || "Parte"}</span>
              <div className="fila-principal">
                <div className="nombre"><Link to={`/descripcion/registro/${p.id}`}>{p.titulo}</Link></div>
                <div className="meta">{p.alcance_contenido || ""}{p.instanciaciones.length > 0 && ` · recorte: ${p.instanciaciones.map((i) => i.nombre).join(", ")}`}</div>
              </div>
            </div>
          ))}
          {editando && trabajo && registro.nivel === "unidad_documental" && (
            <PartesDocumentales partes={partes} alCambiar={setPartes} trabajoId={trabajo} fondoId={registro.fondo_id}
                                documentos={registro.instanciaciones} />
          )}
        </div>
      )}

      <div className="tarjeta">
        <div className="tarjeta-cab">Datos de control para el inventario (FUID)</div>
        <div className="tarjeta-cuerpo">
          {editando ? (
            <div className="rejilla">
              {CAMPOS_CONTROL.map((c) => (
                <div className="campo" key={c.clave} style={{ margin: 0 }}>
                  <label htmlFor={`c-${c.clave}`}>{c.nombre}</label>
                  <input id={`c-${c.clave}`} className="entrada" value={control[c.clave]} placeholder={c.pista}
                         inputMode={c.clave === "folios" ? "numeric" : undefined}
                         onChange={(e) => setControl({ ...control, [c.clave]: c.clave === "folios" ? e.target.value.replace(/\D/g, "") : e.target.value })} />
                </div>
              ))}
            </div>
          ) : (
            <dl className="pares" style={{ margin: 0 }}>
              {CAMPOS_CONTROL.map((c) => (
                <Fragment key={c.clave}>
                  <dt>{c.nombre}</dt>
                  <dd>{registro.control[c.clave] ?? <span className="texto-alerta">Sin dato: saldrá pendiente en el inventario</span>}</dd>
                </Fragment>
              ))}
            </dl>
          )}
        </div>
      </div>

      <OriginalesFisicos recursoId={registro.id} instanciaciones={registro.instanciaciones} puede={puede && !editando}
                         alGuardar={(r) => cargar(r as Registro)} />
      <CompletitudDescripcion recursoId={registro.id} version={registro} />

      <div className="tarjeta">
        <div className="tarjeta-cab">Entidades y relaciones RiC</div>
        {registro.forma_documental && (
          <div className={`fila${quitarForma ? " tachada" : ""}`}>
            <span className="insignia bien">Forma documental</span>
            <div className="fila-principal"><div className="nombre">{registro.forma_documental.nombre}</div>
              <div className="meta">Atributo RiC-A17 · {ORIGEN_NOMBRE[registro.forma_documental.origen]}</div></div>
            {editando && <button type="button" className="boton chico" onClick={() => setQuitarForma(!quitarForma)}>{quitarForma ? "Deshacer" : "Quitar"}</button>}
          </div>
        )}
        {registro.entidades.map((e) => (
          <div key={e.relacion_id} className={`fila${quitar.includes(e.relacion_id) ? " tachada" : ""}`}>
            <span className={`insignia ${TIPO_CLASE[e.tipo]}`}>
              {TIPO_NOMBRE[e.tipo]}{e.rol && ROL_NOMBRE[e.rol] ? ` · ${ROL_NOMBRE[e.rol]}` : ""}
            </span>
            <div className="fila-principal">
              <div className="nombre">
                {veVocabulario && EN_VOCABULARIO.includes(e.tipo) && e.entidad_id
                  ? <Link to={`/vocabularios/${e.entidad_id}`}>{e.valor}</Link> : e.valor}
                {e.subtipo ? ` · ${SUBTIPO_NOMBRE[e.subtipo] || e.subtipo}` : ""}
                {e.tipo === "fecha" && e.fecha_legible && e.fecha_legible !== e.valor ? ` · ${e.fecha_legible}` : ""}
                {e.edtf && <code style={{ marginLeft: 6 }}>{e.edtf}</code>}
              </div>
              {e.contexto && <CadenaActividad contexto={e.contexto} enlazar={veVocabulario} />}
              {e.antes_de_fusion && (
                <div className="meta">
                  Antes citaba a{" "}
                  {veVocabulario ? <Link to={`/vocabularios/${e.antes_de_fusion.id}`}>«{e.antes_de_fusion.nombre}»</Link>
                    : `«${e.antes_de_fusion.nombre}»`}, fusionada en esta entidad
                </div>
              )}
              <div className="meta">
                {e.uri_rico || e.codigo_ric} · {ORIGEN_NOMBRE[e.origen]}{e.confianza !== null ? ` · confianza ${Math.round(e.confianza * 100)} %` : ""}
                {e.fragmento && ` · «${e.fragmento}»`}
              </div>
            </div>
            {editando && (
              <button type="button" className="boton chico"
                      onClick={() => setQuitar((q) => (q.includes(e.relacion_id) ? q.filter((x) => x !== e.relacion_id) : [...q, e.relacion_id]))}>
                {quitar.includes(e.relacion_id) ? "Deshacer" : "Quitar"}
              </button>
            )}
          </div>
        ))}
        {nuevas.map((n) => (
          <div key={n.clave} className="fila" style={{ display: "block" }}>
            <span className={`insignia ${TIPO_CLASE[n.tipo]}`}>{TIPO_NOMBRE[n.tipo]} nueva</span> <b>{n.valor}</b>
            <button type="button" className="boton chico" style={{ marginLeft: 8 }} onClick={() => setNuevas((l) => l.filter((x) => x.clave !== n.clave))}>Quitar</button>
            <PreguntaVocabulario valor={n.valor} verificacion={n.verif}
                                 alDecidir={(v) => setNuevas((l) => l.map((x) => (x.clave === n.clave ? { ...x, verif: v } : x)))} />
          </div>
        ))}
        {editando && (
          <div className="tarjeta-cuerpo">
            {agregando ? <FormEntidad alGuardar={agregar} alCancelar={() => setAgregando(false)} />
              : <button type="button" className="enlace" onClick={() => setAgregando(true)}>+ Agregar entidad</button>}
          </div>
        )}
      </div>

      {editando && (
        <div className="barra-publicar">
          <span>Los cambios quedan en auditoría con el valor anterior y el nuevo. Lo que se quita no se borra: queda anulado.</span>
          <div className="acciones">
            <button type="button" className="boton" onClick={descartarCambios}>Descartar cambios</button>
            <button type="button" className="boton primario" disabled={guardando || pendientes > 0 || titulo.trim().length < 3} onClick={guardar}>
              {guardando ? "Guardando…" : "Guardar cambios"}
            </button>
          </div>
        </div>
      )}
    </>
  );
}


// Ficha ISAD(G) completa (hallazgo DES-07): los 26 elementos, cada uno con su
// valor o vacío, de dónde sale en el sistema y con qué propiedad RiC-O se
// exporta (o por qué no tiene una).
interface ElementoIsadg {
  elemento: string; area: string; nombre: string; valor: string | null; fuente: string; rico: string | null;
  sin_propiedad: string | null;
}

function FichaIsadg({ recursoId, actualizado }: { recursoId: string; actualizado: string | null }) {
  const [ficha, setFicha] = useState<{ elementos: ElementoIsadg[]; con_dato: number; total: number } | null>(null);
  useEffect(() => {
    pedir<{ elementos: ElementoIsadg[]; con_dato: number; total: number }>(`/api/descripcion/registros/${recursoId}/isadg`)
      .then(setFicha).catch(() => setFicha(null));
  }, [recursoId, actualizado]);
  if (!ficha) return null;
  let area = "";
  return (
    <details className="tarjeta">
      <summary className="tarjeta-cab">Ficha ISAD(G) · {ficha.con_dato} de {ficha.total} elementos con dato</summary>
      <div className="tarjeta-cuerpo">
        <dl className="pares" style={{ margin: 0 }}>
          {ficha.elementos.map((e) => {
            const cabecera = e.area !== area ? (area = e.area) : null;
            return (
              <Fragment key={e.elemento}>
                {cabecera && <dt style={{ gridColumn: "1 / -1", fontWeight: 600, marginTop: 8 }}>Área de {cabecera.toLowerCase()}</dt>}
                <dt>{e.elemento} {e.nombre}</dt>
                <dd>{e.valor || <span className="meta">Sin dato</span>}
                  <div className="meta">{e.rico ? <code className="rico">{e.rico}</code> : e.sin_propiedad}</div></dd>
              </Fragment>
            );
          })}
        </dl>
      </div>
    </details>
  );
}
