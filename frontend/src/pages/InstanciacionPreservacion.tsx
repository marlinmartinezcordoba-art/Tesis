import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { EnlaceHistoria } from "@/components/Historia";
import { ErrorAPI, descargar, pedir, puede as tienePermiso, subir } from "@/lib/api";
import { NIVEL_NOMBRE } from "@/lib/descripcion";
import { fecha, peso } from "@/lib/formato";
import {
  ACCESOS, BASES_DERECHOS, INTEGRIDAD, REPRODUCCIONES, RIESGO, SEGUNDA_COPIA, type Detalle, type MigracionHist,
  type MecanismoBreve, type ResultadoCopia,
} from "@/lib/preservacion";
import { useSesion } from "@/lib/sesion";

const ESTADO_MIGRACION: Record<MigracionHist["estado"], { texto: string; clase: string }> = {
  en_curso: { texto: "En curso", clase: "proceso" },
  completada: { texto: "Completada", clase: "bien" },
  fallida: { texto: "Fallida", clase: "error" },
  esperando_archivo: { texto: "Esperando el archivo convertido", clase: "alerta" },
};

function CargaConvertido({ instId, migracion, alTerminar }: { instId: string; migracion: MigracionHist; alTerminar: (texto: string) => void }) {
  const entrada = useRef<HTMLInputElement>(null);
  const [avance, setAvance] = useState<number | null>(null);
  const [error, setError] = useState("");

  async function enviar(archivo: File) {
    setError("");
    setAvance(0);
    const datos = new FormData();
    datos.append("migracion_id", migracion.id);
    datos.append("archivo", archivo);
    try {
      await subir(`/api/preservacion/instanciacion/${instId}/migrar/cargar`, datos, setAvance);
      alTerminar(`Se cargó «${archivo.name}» como la nueva instanciación en ${migracion.destino_nombre}.`);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar el archivo.");
    } finally {
      setAvance(null);
    }
  }

  return (
    <div className="zona" role="button" tabIndex={0} onClick={() => entrada.current?.click()}
         onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && entrada.current?.click()}
         onDragOver={(e) => e.preventDefault()}
         onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) enviar(f); }}>
      <div className="zona-titulo">{avance !== null ? `Subiendo… ${Math.round(avance * 100)} %` : `Suba aquí el archivo ya convertido a ${migracion.destino_nombre}`}</div>
      <div className="zona-sub">Se identificará con PRONOM y quedará enlazado a la original. La original no cambia.</div>
      {error && <div className="aviso error" style={{ marginTop: 10 }}>{error}</div>}
      <input ref={entrada} type="file" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) enviar(f); e.target.value = ""; }} />
    </div>
  );
}

const RESULTADO_COPIA: Record<ResultadoCopia, { texto: string; clase: string }> = {
  integra: { texto: "Íntegra", clase: "bien" },
  alterada: { texto: "Alterada", clase: "error" },
  ausente: { texto: "No está", clase: "error" },
  sin_copia: { texto: "Sin copia", clase: "alerta" },
};

// Derechos (PREMIS): la declaración que rige el archivo, heredada o propia,
// y el formulario para declarar una nueva en este archivo o en un nivel.
function TarjetaDerechos({ d, puede, alTerminar }: { d: Detalle; puede: boolean; alTerminar: (texto: string) => void }) {
  const [abierto, setAbierto] = useState(false);
  const niveles = [{ tipo: "instanciacion", id: d.id, nombre: `Solo este archivo (${d.nombre})` },
    ...[...d.contexto].reverse().map((c) => ({ tipo: "recurso_documental", id: c.id,
      nombre: `${NIVEL_NOMBRE[c.nivel] || c.nivel}: ${c.titulo} (y todo lo que contiene)` }))];
  const [form, setForm] = useState({ destino: 0, base: "estatuto", acceso: "publico", reproduccion: "permitida",
    fundamento: "", nota: "", vigente_hasta: "" });
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const r = d.derechos;

  async function guardar(e: FormEvent) {
    e.preventDefault();
    setOcupado(true);
    setError("");
    const n = niveles[form.destino];
    try {
      await pedir("/api/preservacion/derechos", { method: "PUT", body: JSON.stringify({
        entidad_tipo: n.tipo, entidad_id: n.id, base: form.base, acceso: form.acceso, reproduccion: form.reproduccion,
        fundamento: form.fundamento, nota: form.nota || null, vigente_hasta: form.vigente_hasta || null }) });
      setAbierto(false);
      alTerminar("Declaración de derechos guardada. La anterior, si había, queda en el historial como reemplazada.");
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo guardar la declaración.");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Derechos (PREMIS)</div>
      <div className="tarjeta-cuerpo">
        {!r ? <p className="meta" style={{ marginTop: 0 }}>No hay una declaración de derechos para este archivo ni para los niveles
          que lo contienen. El paquete de preservación lo dirá así.</p> : (
          <dl className="pares" style={{ margin: 0 }}>
            <dt>Acceso</dt><dd><span className={`insignia ${r.acceso === "publico" ? "bien" : "alerta"}`}>{r.acceso_nombre}</span></dd>
            <dt>Reproducción</dt><dd>{r.reproduccion_nombre}</dd>
            <dt>Base</dt><dd>{r.base_nombre}</dd>
            <dt>Fundamento</dt><dd>{r.fundamento}{r.nota && <span className="meta"> · {r.nota}</span>}</dd>
            {r.vigente_hasta && <><dt>Vigente hasta</dt><dd>{r.vigente_hasta}</dd></>}
            <dt>Declarada en</dt>
            <dd className="meta">{r.heredada ? `Heredada de ${NIVEL_NOMBRE[r.nivel || ""] || r.nivel}: ${r.titulo}` : "Este archivo"}</dd>
          </dl>
        )}
        {puede && !abierto && (
          <div className="acciones"><button type="button" className="boton chico" onClick={() => setAbierto(true)}>Declarar derechos</button></div>
        )}
        {abierto && (
          <form onSubmit={guardar} style={{ marginTop: 12 }}>
            <div className="campo">
              <label htmlFor="d-destino">Aplica a</label>
              <select id="d-destino" className="selector" value={form.destino} onChange={(e) => setForm({ ...form, destino: Number(e.target.value) })}>
                {niveles.map((n, i) => <option key={n.id} value={i}>{n.nombre}</option>)}
              </select>
            </div>
            <div className="campo">
              <label htmlFor="d-acceso">Acceso</label>
              <select id="d-acceso" className="selector" value={form.acceso} onChange={(e) => setForm({ ...form, acceso: e.target.value })}>
                {ACCESOS.map((a) => <option key={a.clave} value={a.clave}>{a.nombre}</option>)}
              </select>
            </div>
            <div className="campo">
              <label htmlFor="d-repro">Reproducción</label>
              <select id="d-repro" className="selector" value={form.reproduccion} onChange={(e) => setForm({ ...form, reproduccion: e.target.value })}>
                {REPRODUCCIONES.map((a) => <option key={a.clave} value={a.clave}>{a.nombre}</option>)}
              </select>
            </div>
            <div className="campo">
              <label htmlFor="d-base">Base</label>
              <select id="d-base" className="selector" value={form.base} onChange={(e) => setForm({ ...form, base: e.target.value })}>
                {BASES_DERECHOS.map((a) => <option key={a.clave} value={a.clave}>{a.nombre}</option>)}
              </select>
            </div>
            <div className="campo">
              <label htmlFor="d-fund">Fundamento</label>
              <input id="d-fund" required minLength={3} maxLength={500} value={form.fundamento}
                     placeholder="p. ej. Ley 594 de 2000, art. 27; Ley 1712 de 2014, art. 4"
                     onChange={(e) => setForm({ ...form, fundamento: e.target.value })} />
            </div>
            <div className="campo">
              <label htmlFor="d-nota">Nota (opcional)</label>
              <input id="d-nota" maxLength={500} value={form.nota} onChange={(e) => setForm({ ...form, nota: e.target.value })} />
            </div>
            <div className="campo">
              <label htmlFor="d-hasta">Vigente hasta (opcional)</label>
              <input id="d-hasta" type="date" value={form.vigente_hasta} onChange={(e) => setForm({ ...form, vigente_hasta: e.target.value })} />
            </div>
            {error && <div className="aviso error" role="alert">{error}</div>}
            <div className="acciones">
              <button type="button" className="boton" onClick={() => setAbierto(false)}>Cancelar</button>
              <button type="submit" className="boton primario" disabled={ocupado}>{ocupado ? "Guardando…" : "Guardar declaración"}</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function PanelMigracion({ d, alTerminar }: { d: Detalle; alTerminar: (texto: string) => void }) {
  const [destino, setDestino] = useState(d.riesgo.destino_sugerido && d.destinos.some((x) => x.clave === d.riesgo.destino_sugerido)
    ? d.riesgo.destino_sugerido : "");
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  const elegido = d.destinos.find((x) => x.clave === destino);

  async function aprobar() {
    setOcupado(true);
    setError("");
    try {
      const m = await pedir<MigracionHist & { nueva_instanciacion: Detalle | null }>(
        `/api/preservacion/instanciacion/${d.id}/migrar`, { method: "POST", body: JSON.stringify({ destino, aprobada: true }) });
      alTerminar(m.estado === "completada" ? `Migración completada: se creó «${m.nueva_instanciacion?.nombre}». La original no cambió.`
        : m.estado === "esperando_archivo" ? "Migración registrada. Suba el archivo convertido en el historial de migraciones."
          : `La migración falló: ${m.mensaje}. La original no cambió.`);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo registrar la migración.");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Migrar formato</div>
      <div className="tarjeta-cuerpo">
        <div className="campo">
          <label htmlFor="destino">Formato destino</label>
          <select id="destino" className="selector" value={destino} onChange={(e) => setDestino(e.target.value)}>
            <option value="">Elija un formato…</option>
            {d.destinos.map((x) => (
              <option key={x.clave} value={x.clave}>{x.nombre}{x.automatica ? " · automática" : " · carga manual"}</option>
            ))}
          </select>
        </div>
        {elegido && (elegido.automatica ? (
          <div className="aviso bien">
            <strong>Conversión automática.</strong> Al aprobar, el sistema convierte una copia con {elegido.conversor}, comprueba con
            PRONOM que el resultado sea {elegido.nombre} y crea una instanciación nueva, enlazada a esta y a su descripción.
            Esta instanciación no se modifica ni se borra.
          </div>
        ) : (
          <div className="aviso alerta">
            <strong>Formato no soportado para conversión automática.</strong> Al aprobar, solo se registra la solicitud de migración.
            Después usted convierte el archivo por fuera y lo sube aquí; entonces se crea la instanciación nueva, enlazada a esta.
          </div>
        ))}
        {error && <div className="aviso error" role="alert">{error}</div>}
        <div className="acciones">
          <button type="button" className="boton primario" disabled={!elegido || ocupado} onClick={aprobar}>
            {ocupado ? "Migrando…" : "Aprobar migración"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function InstanciacionPreservacion() {
  const { id = "" } = useParams();
  const { usuario } = useSesion();
  const puede = tienePermiso(usuario, "preservacion", "escribir");
  const veCatalogo = tienePermiso(usuario, "catalogo");
  const [d, setD] = useState<Detalle | null>(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [avisoTipo, setAvisoTipo] = useState<"bien" | "error">("bien");
  const [verificando, setVerificando] = useState(false);
  const [migrando, setMigrando] = useState(false);
  const [exportando, setExportando] = useState(false);
  const [confirmar, setConfirmar] = useState<"restaurar" | "reponer" | null>(null);

  const cargar = useCallback(async () => {
    try {
      setD(await pedir<Detalle>(`/api/preservacion/instanciacion/${id}`));
      setError("");
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar la instanciación.");
    }
  }, [id]);

  useEffect(() => {
    setD(null);
    setAviso("");
    setMigrando(false);
    cargar();
  }, [cargar]);

  async function verificar() {
    setVerificando(true);
    setError("");
    try {
      const r = await pedir<{ resultado: string; segunda_copia: ResultadoCopia }>(`/api/preservacion/instanciacion/${id}/verificar`,
        { method: "POST" });
      const copiaBien = r.segunda_copia === "integra";
      setAvisoTipo(r.resultado === "integra" && copiaBien ? "bien" : "error");
      setAviso(r.resultado !== "integra"
        ? "¡Atención! La verificación encontró la copia primaria alterada o ausente. Se generó una alerta de severidad alta."
        : copiaBien ? "Verificación hecha: la copia primaria y la segunda copia están íntegras (las huellas coinciden)."
          : "La copia primaria está íntegra, pero la segunda copia no: se generó su alerta propia.");
      window.dispatchEvent(new Event("ricora:alertas"));
      cargar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo verificar.");
    } finally {
      setVerificando(false);
    }
  }

  async function exportar() {
    setExportando(true);
    setError("");
    try {
      await descargar(`/api/preservacion/instanciacion/${id}/exportar-paquete`, { method: "POST" });
      setAvisoTipo("bien");
      setAviso("Paquete de preservación exportado (BagIt con PREMIS y las cinco categorías de la PDI). Quedó registrado en la auditoría.");
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo exportar el paquete.");
    } finally {
      setExportando(false);
    }
  }

  async function contingencia(accion: "restaurar" | "reponer") {
    setError("");
    try {
      await pedir(`/api/preservacion/instanciacion/${id}/${accion === "restaurar" ? "restaurar" : "segunda-copia/reponer"}`,
        { method: "POST", body: JSON.stringify({ aprobada: true }) });
      terminar(accion === "restaurar"
        ? "Copia primaria restaurada desde la segunda copia. El archivo dañado quedó apartado en cuarentena, sin borrarse."
        : "Segunda copia rehecha desde la primaria. La copia dañada se conserva como «reemplazada».");
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo completar la acción.");
    } finally {
      setConfirmar(null);
    }
  }

  const terminar = (texto: string) => {
    setAvisoTipo("bien");
    setAviso(texto);
    setMigrando(false);
    window.dispatchEvent(new Event("ricora:alertas"));
    cargar();
  };

  if (!d) return error ? <div className="aviso error">{error}</div> : <div className="cargando">Cargando…</div>;
  const integridad = INTEGRIDAD[d.estado_integridad];
  const copia = d.almacenamiento.segunda_copia;
  const recurso = d.contexto[d.contexto.length - 1];

  return (
    <>
      <nav className="migas" aria-label="Ubicación">
        <Link className="enlace" to="/preservacion">Preservación</Link>
        {d.contexto.map((c) => (
          <span key={c.id}> › {veCatalogo ? <Link className="enlace" to={`/instrumentos?ficha=${c.id}`}>{c.nivel === "fondo" ? `Fondo · ${c.titulo}` : c.titulo}</Link>
            : c.titulo}</span>
        ))}
        {!d.contexto.length && <span> › Sin describir todavía</span>}
      </nav>
      <div className="ficha-titulo">
        <div>
          <span className="insignia proceso">Instanciación{recurso && ` de ${NIVEL_NOMBRE[recurso.nivel]?.toLowerCase()}`}</span>
          <h1 style={{ marginTop: 8 }}>{d.nombre}</h1>
        </div>
        <div className="insignias">
          <EnlaceHistoria tipo="instanciacion" id={d.id} nombre={d.nombre} />
          <span className={`insignia ${integridad.clase}`}>{integridad.texto}</span>
          <span className={`insignia ${SEGUNDA_COPIA[copia.estado].clase}`}>
            Segunda copia {copia.estado === "sin_copia" ? "pendiente" : copia.estado === "ausente" ? "perdida" : copia.estado}
          </span>
          <span className={`insignia ${d.riesgo.mitigado_por ? "bien" : RIESGO[d.riesgo.nivel].clase}`}>
            {d.riesgo.mitigado_por ? "Riesgo mitigado" : RIESGO[d.riesgo.nivel].texto}
          </span>
        </div>
      </div>
      {aviso && <div className={`aviso ${avisoTipo}`} role="status">{aviso}</div>}
      {error && <div className="aviso error" role="alert">{error}</div>}

      <div className="tarjeta">
        <div className="tarjeta-cab">Ficha técnica (PREMIS · Objeto)</div>
        <div className="tarjeta-cuerpo">
          <dl className="pares" style={{ margin: 0 }}>
            <dt>Identificador</dt><dd><code className="huella">urn:uuid:{d.id}</code></dd>
            <dt>Categoría</dt><dd>Archivo (PREMIS file) · Instantiation, RiC-E06</dd>
            <dt>Nombre original</dt><dd>{d.nombre}</dd>
            <dt>Formato</dt>
            <dd>{d.formato.nombre || "No identificado"}{d.formato.version && ` · versión ${d.formato.version}`}
              {d.formato.puid && <span className="meta"> · PRONOM {d.formato.puid}</span>}</dd>
            <dt>Tipo MIME</dt><dd>{d.formato.mime || "—"}</dd>
            <dt>Identificado con</dt><dd className="meta"><Mecanismo m={d.formato.mecanismo} texto={d.formato.herramienta} /></dd>
            <dt>Tamaño</dt><dd>{peso(d.tamano_bytes)}{d.paginas ? ` · ${d.paginas} página(s)` : ""}</dd>
            <dt>Huella digital</dt><dd><code className="huella">{d.algoritmo_huella} {d.huella}</code></dd>
            <dt>Aplicación creadora</dt><dd className="meta">{d.aplicacion_creadora || "Desconocida (el archivo llegó por la ingesta)"}</dd>
            <dt>Copia primaria</dt><dd className="meta">{d.almacenamiento.primaria.ubicacion}/{d.almacenamiento.primaria.ruta}</dd>
            <dt>Segunda copia</dt>
            <dd>
              <span className={`insignia ${SEGUNDA_COPIA[copia.estado].clase}`}>{SEGUNDA_COPIA[copia.estado].texto}</span>
              {copia.ubicacion && <span className="meta"> · {copia.ubicacion}/{copia.ruta}</span>}
              {copia.ultima_verificacion_en && <span className="meta"> · verificada {fecha(copia.ultima_verificacion_en)}</span>}
              {copia.estado === "sin_copia" && <span className="meta"> · el sistema la crea en el próximo minuto</span>}
            </dd>
            <dt>Ingreso</dt><dd>{fecha(d.cargado_en)}</dd>
            <dt>Última verificación</dt><dd>{d.ultima_verificacion_en ? fecha(d.ultima_verificacion_en) : "Todavía no"}</dd>
            {d.derivada_de && (
              <><dt>Migrada desde</dt>
                <dd><Link to={`/preservacion/instanciacion/${d.derivada_de.id}`}>{d.derivada_de.nombre}</Link>
                  {d.migrada_desde?.herramienta && <span className="meta"> · <Mecanismo m={d.migrada_desde.mecanismo} texto={d.migrada_desde.herramienta} /></span>}</dd></>
            )}
          </dl>
        </div>
      </div>

      <div className="tarjeta">
        <div className="tarjeta-cab">Riesgo de obsolescencia del formato</div>
        <div className="tarjeta-cuerpo">
          <p style={{ marginTop: 0 }}><span className={`insignia ${RIESGO[d.riesgo.nivel].clase}`}>{RIESGO[d.riesgo.nivel].texto}</span> {d.riesgo.razon}</p>
          {d.riesgo.recomendacion && !d.riesgo.mitigado_por && <p className="meta" style={{ marginBottom: 0 }}>Recomendación: {d.riesgo.recomendacion}</p>}
          {d.riesgo.mitigado_por && (
            <p className="meta" style={{ marginBottom: 0 }}>Mitigado: ya existe una versión de conservación,{" "}
              <Link to={`/preservacion/instanciacion/${d.riesgo.mitigado_por.id}`}>{d.riesgo.mitigado_por.nombre}</Link>.</p>
          )}
        </div>
      </div>

      <div className="tarjeta">
        <div className="tarjeta-cab">Historial de verificaciones de integridad</div>
        {d.verificaciones.length === 0 ? <div className="vacio">Todavía no se ha verificado.</div> : (
          <div className="tabla-desplazable">
            <table className="tabla-permisos">
              <thead><tr><th>Fecha</th><th>Copia primaria</th><th>Segunda copia</th><th>Cómo</th></tr></thead>
              <tbody>
                {d.verificaciones.map((v, i) => (
                  <tr key={i}>
                    <td>{fecha(v.fecha)}</td>
                    <td><span className={`insignia ${INTEGRIDAD[v.resultado].clase}`}>{INTEGRIDAD[v.resultado].texto}</span></td>
                    <td>{v.segunda_copia ? <span className={`insignia ${RESULTADO_COPIA[v.segunda_copia].clase}`}>{RESULTADO_COPIA[v.segunda_copia].texto}</span>
                      : <span className="meta">No se verificaba</span>}</td>
                    <td className="meta">{v.origen === "periodica" ? "Verificación periódica automática" : `Manual${v.por ? ` · ${v.por}` : ""}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {(d.acciones.restaurar || d.acciones.reponer_segunda_copia) && puede && (
        <div className="aviso error" role="alert">
          {d.acciones.restaurar ? (
            <><strong>La copia primaria está {d.estado_integridad === "ausente" ? "perdida" : "alterada"} y la segunda copia está íntegra.</strong>{" "}
              Puede restaurarla: el archivo dañado no se borra, se aparta a la cuarentena, y todo queda en la auditoría.</>
          ) : (
            <><strong>La segunda copia {copia.estado === "ausente" ? "no está en su lugar" : "está alterada"}.</strong>{" "}
              La copia primaria está íntegra: puede rehacer la segunda copia desde ella. La dañada se conserva.</>
          )}
          <div className="acciones">
            {confirmar ? (
              <>
                <button type="button" className="boton" onClick={() => setConfirmar(null)}>Cancelar</button>
                <button type="button" className="boton primario" onClick={() => contingencia(confirmar)}>
                  Sí, apruebo {confirmar === "restaurar" ? "restaurar la copia primaria" : "rehacer la segunda copia"}
                </button>
              </>
            ) : (
              <button type="button" className="boton primario" onClick={() => setConfirmar(d.acciones.restaurar ? "restaurar" : "reponer")}>
                {d.acciones.restaurar ? "Restaurar desde la segunda copia" : "Rehacer la segunda copia"}
              </button>
            )}
          </div>
        </div>
      )}

      {d.restauraciones.length > 0 && (
        <div className="tarjeta">
          <div className="tarjeta-cab">Restauraciones (contingencia)</div>
          {d.restauraciones.map((r, i) => (
            <div key={i} className="fila">
              <div className="fila-principal">
                <div className="nombre">Copia primaria {r.estado_previo} restaurada desde la segunda copia</div>
                <div className="meta">{fecha(r.fecha)} · {r.por || "—"}{r.cuarentena && ` · archivo dañado en ${r.cuarentena}`}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      <TarjetaDerechos d={d} puede={puede} alTerminar={terminar} />

      <div className="tarjeta">
        <div className="tarjeta-cab">Historial de migraciones</div>
        {d.migraciones.length === 0 && <div className="vacio">Esta instanciación no tiene migraciones.</div>}
        {d.migraciones.map((m) => (
          <div key={m.id} className="fila" style={{ alignItems: "flex-start" }}>
            <div className="fila-principal">
              <div className="nombre">{m.destino_nombre} · {m.modo === "automatica" ? "automática" : "carga manual"}</div>
              <div className="meta">
                Aprobada por {m.aprobada_por || "—"} el {fecha(m.aprobada_en)}
                {m.mecanismo ? <> · ejecutada por <Mecanismo m={m.mecanismo} texto={null} />{m.parametros && ` (${m.parametros})`}</>
                  : m.herramienta && ` · ${m.herramienta}`}
                {m.mensaje && ` · ${m.mensaje}`}
              </div>
              {m.resultado && (
                <div className="meta">Resultado: <Link to={`/preservacion/instanciacion/${m.resultado.id}`}>{m.resultado.nombre}</Link>
                  {m.resultado.puid && ` (${m.resultado.puid})`}</div>
              )}
              {m.estado === "esperando_archivo" && puede && (
                <div style={{ marginTop: 10 }}><CargaConvertido instId={d.id} migracion={m} alTerminar={terminar} /></div>
              )}
            </div>
            <span className={`insignia ${ESTADO_MIGRACION[m.estado].clase}`}>{ESTADO_MIGRACION[m.estado].texto}</span>
          </div>
        ))}
      </div>

      {puede && (
        <>
          {migrando && <PanelMigracion d={d} alTerminar={terminar} />}
          <div className="acciones">
            <button type="button" className="boton" disabled={verificando} onClick={verificar}>
              {verificando ? "Verificando…" : "Verificar integridad ahora"}
            </button>
            <button type="button" className="boton" disabled={exportando || d.estado_integridad === "alterada" || d.estado_integridad === "ausente"}
                    title="Paquete de información de archivo (OAIS): BagIt con el archivo, PREMIS y la PDI"
                    onClick={exportar}>{exportando ? "Armando el paquete…" : "Exportar paquete de preservación"}</button>
            {!migrando && (
              <button type="button" className="boton primario" disabled={d.estado_integridad === "alterada" || d.estado_integridad === "ausente"}
                      title={d.estado_integridad === "alterada" ? "Resuelva primero la alerta de integridad" : undefined}
                      onClick={() => setMigrando(true)}>Migrar formato</button>
            )}
          </div>
        </>
      )}
    </>
  );
}

// El programa que actuó es un agente del vocabulario del fondo: se enlaza a
// su ficha (con su versión exacta), no se muestra como texto suelto.
function Mecanismo({ m, texto }: { m: MecanismoBreve | null; texto: string | null }) {
  if (!m) return <>{texto || "—"}</>;
  return (
    <Link to={`/vocabularios/${m.id}`} title="Agente mecanismo (RiC-E13) del vocabulario del fondo">
      {m.nombre}{texto && texto !== m.nombre && texto.startsWith(m.nombre) ? texto.slice(m.nombre.length) : ""}
    </Link>
  );
}
