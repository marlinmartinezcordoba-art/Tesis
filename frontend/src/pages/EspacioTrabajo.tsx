import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { SelectorFecha } from "@/components/SelectorFecha";
import { FormEntidad, PreguntaVocabulario, type EntidadManual } from "@/components/Vocabulario";
import { ErrorAPI, pedir } from "@/lib/api";
import {
  EN_VOCABULARIO, NIVEL_NOMBRE, ROL_NOMBRE, SUBTIPO_NOMBRE, TIPO_CLASE, TIPO_NOMBRE, nivelesSuperiores,
  verificacionInicial, verificarVocabulario, type Coincidencia, type NivelSuperior, type TipoEntidad, type Verificacion,
} from "@/lib/descripcion";
import { desarmar, legible, type ControlFecha, type SubtipoFecha } from "@/lib/fechas";

interface EntidadPropuesta {
  clave: string;
  tipo: TipoEntidad;
  valor: string;
  subtipo: string | null;
  rol: string | null;
  fecha_normalizada: string | null;
  edtf: string | null;
  fecha_subtipo: SubtipoFecha | null;
  tipo_clave: string | null;
  agente_clave: string | null;
  mandato_clave: string | null;
  fragmento: string | null;
  documento_id: string | null;
  inicio: number | null;
  confianza: number | null;
  fragmento_localizado: boolean;
}

interface Espacio {
  trabajo_id: string;
  nivel: string;
  fondo: { id: string; titulo: string };
  documentos: { id: string; nombre: string; texto: string; origen_texto: string | null; expediente_destino_id: string | null }[];
  propuesta: {
    titulo: string;
    alcance: string;
    entidades: EntidadPropuesta[];
    motor: string | null;
    version_prompt: string | null;
    disponible: boolean;
    aviso: string | null;
  } | null;
  umbral_confianza: number;
}

interface Item extends EntidadPropuesta {
  decision: "pendiente" | "aceptada" | "descartada";
  editada: boolean;
  manual: boolean;
  editando: boolean;
  verif: Verificacion;
  control: ControlFecha; // fecha de la entidad, periodo de la actividad o expedición del mandato
  conPeriodo: boolean;
}

// Lo que impide publicar: sin decidir, sin verificar en el vocabulario,
// una fecha sin completar o un tipo de actividad que ninguna actividad usa.
function porResolver(i: Item, todos: Item[]) {
  if (i.decision === "pendiente") return true;
  if (i.decision !== "aceptada") return false;
  if (["sin_verificar", "verificando", "pregunta"].includes(i.verif.estado)) return true;
  if (i.tipo === "fecha" && !i.edtf) return true;
  if (i.tipo === "tipo_actividad") {
    return !todos.some((a) => a.tipo === "actividad" && a.decision === "aceptada" && a.tipo_clave === i.clave);
  }
  return false;
}

function nuevoItem(e: EntidadPropuesta, manual = false): Item {
  return {
    ...e, decision: "pendiente", editada: false, manual, editando: false, verif: verificacionInicial(e.tipo),
    control: desarmar(e.edtf, e.fecha_subtipo), conPeriodo: !!e.edtf,
  };
}

// Texto del documento con los fragmentos citados resaltados.
function TextoResaltado({ texto, marcas, activa, alElegir }: {
  texto: string;
  marcas: { clave: string; inicio: number; largo: number }[];
  activa: string | null;
  alElegir: (clave: string) => void;
}) {
  const partes: ReactNode[] = [];
  let cursor = 0;
  for (const m of [...marcas].sort((a, b) => a.inicio - b.inicio)) {
    if (m.inicio < cursor) continue; // se superpone con otra: se muestra solo la primera
    partes.push(texto.slice(cursor, m.inicio));
    partes.push(
      <mark key={m.clave} id={`m-${m.clave}`} className={m.clave === activa ? "hl" : ""} onClick={() => alElegir(m.clave)}>
        {texto.slice(m.inicio, m.inicio + m.largo)}
      </mark>,
    );
    cursor = m.inicio + m.largo;
  }
  partes.push(texto.slice(cursor));
  return <div className="texto-doc">{partes}</div>;
}

export function EspacioTrabajo() {
  const { id = "" } = useParams();
  const navegar = useNavigate();
  const ubicacion = useLocation();
  const [espacio, setEspacio] = useState<Espacio | null>((ubicacion.state as { espacio?: Espacio } | null)?.espacio || null);
  const [items, setItems] = useState<Item[]>([]);
  const [titulo, setTitulo] = useState("");
  const [alcance, setAlcance] = useState("");
  const [superiores, setSuperiores] = useState<NivelSuperior[]>([]);
  const [incluidoEn, setIncluidoEn] = useState("");
  const [activa, setActiva] = useState<string | null>(null);
  const [agregando, setAgregando] = useState(false);
  const [error, setError] = useState("");
  const [publicando, setPublicando] = useState(false);
  const [vencido, setVencido] = useState(false);

  // Cargar (o recargar) el espacio de trabajo.
  useEffect(() => {
    if (espacio) return;
    pedir<Espacio>(`/api/descripcion/trabajos/${id}`).then(setEspacio).catch((err) => {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo abrir el espacio de trabajo.");
      setVencido(true);
    });
  }, [id, espacio]);

  useEffect(() => {
    if (!espacio) return;
    const p = espacio.propuesta;
    setTitulo(p?.titulo || "");
    setAlcance(p?.alcance || "");
    setItems((p?.entidades || []).map((e) => nuevoItem(e)));
    nivelesSuperiores(espacio.fondo.id, espacio.nivel).then((opciones) => {
      setSuperiores(opciones);
      const destino = espacio.documentos.length === 1 ? espacio.documentos[0].expediente_destino_id : null;
      setIncluidoEn(opciones.some((o) => o.id === destino) ? destino! : espacio.fondo.id);
    }).catch(() => undefined);
  }, [espacio]);

  // Latido: mantiene la marca «en edición» mientras la pantalla está abierta.
  useEffect(() => {
    if (!espacio || vencido) return;
    const t = setInterval(() => {
      pedir(`/api/descripcion/trabajos/${espacio.trabajo_id}/latido`, { method: "POST" }).catch((err) => {
        if (err instanceof ErrorAPI && err.status === 409) {
          setVencido(true);
          setError(err.message);
        }
      });
    }, 120000);
    return () => clearInterval(t);
  }, [espacio, vencido]);

  const cambiar = useCallback((clave: string, cambio: Partial<Item>) =>
    setItems((l) => l.map((i) => (i.clave === clave ? { ...i, ...cambio } : i))), []);

  async function aceptar(item: Item, valor = item.valor) {
    if (!espacio) return;
    if (!EN_VOCABULARIO.includes(item.tipo)) {
      cambiar(item.clave, { decision: "aceptada", editando: false });
      return;
    }
    cambiar(item.clave, { decision: "aceptada", editando: false, verif: { estado: "verificando", coincidencias: [] } });
    try {
      const c: Coincidencia[] = await verificarVocabulario(espacio.fondo.id, item.tipo, valor);
      cambiar(item.clave, { verif: c.length ? { estado: "pregunta", coincidencias: c } : { estado: "resuelta", coincidencias: [], crearNueva: true } });
    } catch (err) {
      cambiar(item.clave, { decision: "pendiente", verif: verificacionInicial(item.tipo) });
      setError(err instanceof ErrorAPI ? err.message : "No se pudo consultar el vocabulario.");
    }
  }

  function guardarEdicion(item: Item, e: EntidadManual) {
    const nuevo: Item = {
      ...item, valor: e.valor, subtipo: e.subtipo, rol: e.rol, fecha_normalizada: e.fecha_normalizada,
      edtf: item.tipo === "actividad" ? item.edtf : e.edtf, fecha_subtipo: (e.fecha_subtipo as SubtipoFecha) || item.fecha_subtipo,
      control: item.tipo === "actividad" ? item.control : desarmar(e.edtf, e.fecha_subtipo as SubtipoFecha), editada: true,
    };
    cambiar(item.clave, nuevo);
    aceptar(nuevo, e.valor);
  }

  function agregarManual(e: EntidadManual) {
    const item = nuevoItem({
      clave: `m${Date.now()}`, ...e, fecha_subtipo: e.fecha_subtipo as SubtipoFecha | null, tipo_clave: null,
      agente_clave: null, mandato_clave: null, fragmento: null, documento_id: null, inicio: null, confianza: null,
      fragmento_localizado: false,
    }, true);
    setItems((l) => [...l, item]);
    setAgregando(false);
    aceptar(item);
  }

  // Ajuste directo sobre la propuesta (fecha, periodo, cadena de la actividad).
  function ajustar(item: Item, cambio: Partial<Item>) {
    cambiar(item.clave, { ...cambio, editada: true });
  }

  function elegir(clave: string, desdeTexto = false) {
    setActiva(clave);
    const destino = document.getElementById(desdeTexto ? `t-${clave}` : `m-${clave}`);
    destino?.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  async function publicar() {
    if (!espacio) return;
    setError("");
    setPublicando(true);
    const enviadas = items.filter((i) => i.decision === "aceptada");
    const vigente = (clave: string | null) => (clave && enviadas.some((x) => x.clave === clave) ? clave : null);
    try {
      await pedir("/api/descripcion/publicar", {
        method: "POST",
        body: JSON.stringify({
          trabajo_id: espacio.trabajo_id, titulo, alcance_contenido: alcance, incluido_en_id: incluidoEn || null,
          entidades: enviadas.map((i) => ({
            tipo: i.tipo, valor: i.valor, subtipo: i.subtipo, rol: i.rol, fecha_normalizada: null,
            edtf: i.tipo === "actividad" && !i.conPeriodo ? null : i.edtf,
            fecha_subtipo: i.tipo === "fecha" ? i.control.subtipo : null,
            tipo_clave: i.tipo === "actividad" ? vigente(i.tipo_clave) : null,
            agente_clave: i.tipo === "actividad" ? vigente(i.agente_clave) : null,
            mandato_clave: i.tipo === "actividad" ? vigente(i.mandato_clave) : null,
            fragmento: i.fragmento, documento_id: i.documento_id, inicio: i.inicio, clave: i.clave,
            reutilizar_id: i.verif.reutilizarId || null, crear_nueva: !!i.verif.crearNueva,
          })),
        }),
      });
      navegar("/descripcion", { replace: true, state: { aviso: `Se publicó «${titulo}».` } });
    } catch (err) {
      setPublicando(false);
      if (err instanceof ErrorAPI) {
        setError(err.message);
        if (err.status === 409 && err.message.includes("liberó")) setVencido(true);
      } else {
        setError("No se pudo publicar.");
      }
      // Si el servidor encontró parecidos nuevos, se vuelve a preguntar.
      const detalle = err instanceof ErrorAPI ? (err.datos as { indice?: number; coincidencias?: Coincidencia[] }) : undefined;
      if (detalle?.coincidencias && detalle.indice !== undefined && enviadas[detalle.indice]) {
        cambiar(enviadas[detalle.indice].clave, { verif: { estado: "pregunta", coincidencias: detalle.coincidencias } });
      }
    }
  }

  async function salir() {
    if (espacio && !vencido) {
      await pedir(`/api/descripcion/${espacio.trabajo_id}/cancelar`, { method: "POST" }).catch(() => undefined);
    }
    navegar("/descripcion");
  }

  const marcasPorDocumento = useMemo(() => {
    const mapa: Record<string, { clave: string; inicio: number; largo: number }[]> = {};
    for (const i of items) {
      if (i.decision === "descartada" || i.inicio === null || !i.documento_id || !i.fragmento) continue;
      (mapa[i.documento_id] ||= []).push({ clave: i.clave, inicio: i.inicio, largo: i.fragmento.length });
    }
    return mapa;
  }, [items]);

  if (!espacio) {
    return (
      <>
        {error ? <div className="aviso error">{error}</div> : <div className="cargando">Abriendo el espacio de trabajo…</div>}
        {error && <button type="button" className="boton" onClick={() => navegar("/descripcion")}>Volver a la cola</button>}
      </>
    );
  }

  const umbral = espacio.umbral_confianza;
  const pendientes = items.filter((i) => porResolver(i, items)).length;
  const opciones = (tipo: TipoEntidad) => items.filter((x) => x.tipo === tipo && x.decision !== "descartada");
  const nombreDe = (clave: string | null) => items.find((x) => x.clave === clave)?.valor;
  const aceptadas = items.filter((i) => i.decision === "aceptada").length;
  const bajas = items.filter((i) => i.decision !== "descartada" && i.confianza !== null && i.confianza < umbral).length;
  const nombreDoc = (docId: string | null) => espacio.documentos.find((d) => d.id === docId)?.nombre;
  const propuesta = espacio.propuesta;

  return (
    <>
      <h1>Describiendo</h1>
      <p className="sub">
        {NIVEL_NOMBRE[espacio.nivel]} · {espacio.documentos.length} documento{espacio.documentos.length === 1 ? "" : "s"}
        {propuesta?.motor && propuesta.disponible && ` · propuesta del motor ${propuesta.motor}`}
        {propuesta?.version_prompt && propuesta.disponible && <> · instrucción <code>{propuesta.version_prompt}</code></>}
      </p>
      {propuesta?.aviso && <div className="aviso alerta">{propuesta.aviso}</div>}
      {error && <div className="aviso error" role="alert">{error}</div>}

      <div className="espacio">
        <div className="panel-doc">
          {espacio.documentos.map((d) => (
            <div key={d.id} className="doc">
              <div className="docname">{d.nombre} — texto extraído{d.origen_texto === "ocr" ? " por OCR" : ""}</div>
              {d.texto ? (
                <TextoResaltado texto={d.texto} marcas={marcasPorDocumento[d.id] || []} activa={activa}
                                alElegir={(c) => elegir(c, true)} />
              ) : <p className="pista">Este documento no tiene texto extraído.</p>}
            </div>
          ))}
        </div>

        <div className="propuestas">
          <div className="tarjeta-prop fija">
            <div className="campo">
              <label htmlFor="titulo">Título</label>
              <input id="titulo" className="entrada" value={titulo} onChange={(e) => setTitulo(e.target.value)} />
            </div>
            <div className="campo">
              <label htmlFor="alcance">Alcance y contenido</label>
              <textarea id="alcance" className="entrada" rows={5} value={alcance} onChange={(e) => setAlcance(e.target.value)} />
            </div>
            <div className="campo" style={{ marginBottom: 0 }}>
              <label htmlFor="incluido">Queda incluido en</label>
              <select id="incluido" className="selector" value={incluidoEn} onChange={(e) => setIncluidoEn(e.target.value)}>
                {superiores.map((s) => <option key={s.id} value={s.id}>{NIVEL_NOMBRE[s.nivel]}: {s.titulo}</option>)}
              </select>
            </div>
          </div>

          {items.map((i) => {
            const baja = i.confianza !== null && i.confianza < umbral;
            return (
              <div key={i.clave} id={`t-${i.clave}`}
                   className={`tarjeta-prop${activa === i.clave ? " activa" : ""}${i.decision === "descartada" ? " descartada" : ""}`}
                   onClick={() => i.inicio !== null && elegir(i.clave)}>
                <div className="prop-cab">
                  <span className={`insignia ${TIPO_CLASE[i.tipo]}`}>
                    {TIPO_NOMBRE[i.tipo]}{i.subtipo ? ` · ${SUBTIPO_NOMBRE[i.subtipo] || i.subtipo}` : ""}{i.rol ? ` · ${ROL_NOMBRE[i.rol] || i.rol}` : ""}
                  </span>
                  <span className="insignias">
                    {baja && <span className="insignia alerta">Confianza baja</span>}
                    {i.manual && <span className="insignia proceso">Agregada a mano</span>}
                    {i.decision === "aceptada" && <span className="insignia bien">{i.editada ? "Corregida" : "Aceptada"}</span>}
                  </span>
                </div>
                {i.editando ? (
                  <FormEntidad inicial={i} textoBoton="Guardar y aceptar" alGuardar={(e) => guardarEdicion(i, e)}
                               alCancelar={() => cambiar(i.clave, { editando: false })} />
                ) : (
                  <>
                    <div className="prop-valor">{i.valor}</div>
                    {i.tipo === "fecha" && i.decision !== "descartada" && (
                      <div onClick={(e) => e.stopPropagation()}>
                        <SelectorFecha valor={i.control}
                                       alCambiar={(c, edtf) => ajustar(i, { control: c, edtf, fecha_subtipo: c.subtipo })} />
                      </div>
                    )}
                    {i.tipo === "mandato" && (
                      <div className="linea-contexto">
                        {i.subtipo ? SUBTIPO_NOMBRE[i.subtipo] : "Instrumento"}{i.edtf ? ` · expedido ${legible(i.edtf)}` : ""}
                      </div>
                    )}
                    {i.tipo === "tipo_actividad" && (
                      <div className="linea-contexto">
                        {items.filter((a) => a.tipo === "actividad" && a.tipo_clave === i.clave && a.decision !== "descartada")
                          .map((a) => a.valor).join(" · ") || "Sin actividad: asígneselo a una o descártelo"}
                      </div>
                    )}
                    {i.tipo === "actividad" && i.decision !== "descartada" && (
                      <>
                        <div className="linea-contexto">
                          Tipo: {nombreDe(i.tipo_clave) || "sin asignar"}
                          {i.agente_clave && ` · ejercida por ${nombreDe(i.agente_clave)}`}
                          {i.mandato_clave && ` · regulada por ${nombreDe(i.mandato_clave)}`}
                          {i.conPeriodo && i.edtf && ` · ${legible(i.edtf)}`}
                        </div>
                        <div className="contexto-actividad" onClick={(e) => e.stopPropagation()}>
                          <label htmlFor={`ta-${i.clave}`}>Tipo de actividad</label>
                          <select id={`ta-${i.clave}`} className="selector" value={i.tipo_clave || ""}
                                  onChange={(e) => ajustar(i, { tipo_clave: e.target.value || null })}>
                            <option value="">Sin asignar</option>
                            {opciones("tipo_actividad").map((x) => <option key={x.clave} value={x.clave}>{x.valor}</option>)}
                          </select>
                          <label htmlFor={`ag-${i.clave}`}>Ejercida por</label>
                          <select id={`ag-${i.clave}`} className="selector" value={i.agente_clave || ""}
                                  onChange={(e) => ajustar(i, { agente_clave: e.target.value || null })}>
                            <option value="">Sin indicar</option>
                            {opciones("agente").map((x) => <option key={x.clave} value={x.clave}>{x.valor}</option>)}
                          </select>
                          <label htmlFor={`ma-${i.clave}`}>Mandato o norma</label>
                          <select id={`ma-${i.clave}`} className="selector" value={i.mandato_clave || ""}
                                  onChange={(e) => ajustar(i, { mandato_clave: e.target.value || null })}>
                            <option value="">Sin mandato</option>
                            {opciones("mandato").map((x) => <option key={x.clave} value={x.clave}>{x.valor}</option>)}
                          </select>
                          <label>
                            <input type="checkbox" checked={i.conPeriodo} onChange={(e) => ajustar(i, { conPeriodo: e.target.checked })} /> Periodo
                          </label>
                          <span className="meta">{i.conPeriodo ? "" : "La actividad no tiene periodo indicado."}</span>
                        </div>
                        {i.conPeriodo && (
                          <div onClick={(e) => e.stopPropagation()}>
                            <SelectorFecha valor={i.control} subtipos={["simple", "rango"]}
                                           alCambiar={(c, edtf) => ajustar(i, { control: c, edtf })} />
                          </div>
                        )}
                        {opciones("tipo_actividad").length === 0 && (
                          <p className="pista">Para asignar un tipo de actividad, agréguelo con «+ Agregar una entidad».</p>
                        )}
                      </>
                    )}
                    {i.fragmento && (
                      <div className="prop-frag">
                        «{i.fragmento}»{espacio.documentos.length > 1 && nombreDoc(i.documento_id) ? ` — ${nombreDoc(i.documento_id)}` : ""}
                        {!i.fragmento_localizado && !i.manual && " · no se encontró en el texto: verifíquelo"}
                      </div>
                    )}
                    <div className="acciones" onClick={(e) => e.stopPropagation()}>
                      {i.decision !== "aceptada" && i.decision !== "descartada" && (
                        <button type="button" className="boton chico primario" disabled={i.tipo === "fecha" && !i.edtf}
                                title={i.tipo === "fecha" && !i.edtf ? "Complete la fecha" : undefined}
                                onClick={() => aceptar(i)}>Aceptar</button>
                      )}
                      {i.decision !== "descartada" && (
                        <button type="button" className="boton chico" onClick={() => cambiar(i.clave, { editando: true })}>Editar</button>
                      )}
                      {i.decision === "descartada" ? (
                        <button type="button" className="boton chico" onClick={() => cambiar(i.clave, { decision: "pendiente" })}>Deshacer</button>
                      ) : (
                        <button type="button" className="boton chico"
                                onClick={() => cambiar(i.clave, { decision: "descartada", verif: verificacionInicial(i.tipo) })}>
                          Descartar
                        </button>
                      )}
                    </div>
                  </>
                )}
                {i.decision === "aceptada" && (
                  <div onClick={(e) => e.stopPropagation()}>
                    <PreguntaVocabulario valor={i.valor} verificacion={i.verif} alDecidir={(v) => cambiar(i.clave, { verif: v })} />
                  </div>
                )}
              </div>
            );
          })}

          <div className="tarjeta-prop">
            {agregando ? (
              <FormEntidad alGuardar={agregarManual} alCancelar={() => setAgregando(false)} />
            ) : (
              <button type="button" className="enlace" onClick={() => setAgregando(true)}>+ Agregar una entidad que el motor no propuso</button>
            )}
          </div>
        </div>
      </div>

      <div className="barra-publicar">
        <span>
          {items.length} entidad{items.length === 1 ? "" : "es"} · {aceptadas} aceptada{aceptadas === 1 ? "" : "s"}
          {bajas > 0 && ` · ${bajas} con confianza baja`}
          {pendientes > 0 ? ` · ${pendientes} pendiente${pendientes === 1 ? "" : "s"} de resolver` : " · nada pendiente"}
        </span>
        <div className="acciones">
          <button type="button" className="boton" onClick={salir}>Salir sin publicar</button>
          <button type="button" className="boton primario" disabled={pendientes > 0 || publicando || vencido || titulo.trim().length < 3}
                  onClick={publicar}>
            {publicando ? "Publicando…" : "Publicar descripción"}
          </button>
        </div>
      </div>
    </>
  );
}
