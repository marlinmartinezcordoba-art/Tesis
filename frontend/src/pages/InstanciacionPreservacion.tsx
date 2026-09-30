import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { EnlaceHistoria } from "@/components/Historia";
import { ErrorAPI, pedir, puede as tienePermiso, subir } from "@/lib/api";
import { NIVEL_NOMBRE } from "@/lib/descripcion";
import { fecha, peso } from "@/lib/formato";
import { INTEGRIDAD, RIESGO, type Detalle, type MigracionHist } from "@/lib/preservacion";
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
  const [verificando, setVerificando] = useState(false);
  const [migrando, setMigrando] = useState(false);

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
      const r = await pedir<{ resultado: string }>(`/api/preservacion/instanciacion/${id}/verificar`, { method: "POST" });
      setAviso(r.resultado === "integra" ? "Verificación hecha: el archivo está íntegro (la huella coincide)."
        : "¡Atención! La verificación encontró el archivo alterado o ausente. Se generó una alerta de severidad alta.");
      window.dispatchEvent(new Event("ricora:alertas"));
      cargar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo verificar.");
    } finally {
      setVerificando(false);
    }
  }

  const terminar = (texto: string) => {
    setAviso(texto);
    setMigrando(false);
    window.dispatchEvent(new Event("ricora:alertas"));
    cargar();
  };

  if (!d) return error ? <div className="aviso error">{error}</div> : <div className="cargando">Cargando…</div>;
  const integridad = INTEGRIDAD[d.estado_integridad];
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
          <span className={`insignia ${d.riesgo.mitigado_por ? "bien" : RIESGO[d.riesgo.nivel].clase}`}>
            {d.riesgo.mitigado_por ? "Riesgo mitigado" : RIESGO[d.riesgo.nivel].texto}
          </span>
        </div>
      </div>
      {aviso && <div className="aviso bien" role="status">{aviso}</div>}
      {error && <div className="aviso error" role="alert">{error}</div>}

      <div className="tarjeta">
        <div className="tarjeta-cab">Ficha técnica (PREMIS)</div>
        <div className="tarjeta-cuerpo">
          <dl className="pares" style={{ margin: 0 }}>
            <dt>Formato</dt>
            <dd>{d.formato.nombre || "No identificado"}{d.formato.version && ` · versión ${d.formato.version}`}
              {d.formato.puid && <span className="meta"> · PRONOM {d.formato.puid}</span>}</dd>
            <dt>Tipo MIME</dt><dd>{d.formato.mime || "—"}</dd>
            <dt>Identificado con</dt><dd className="meta">{d.formato.herramienta || "—"}</dd>
            <dt>Tamaño</dt><dd>{peso(d.tamano_bytes)}{d.paginas ? ` · ${d.paginas} página(s)` : ""}</dd>
            <dt>Huella digital</dt><dd><code className="huella">{d.algoritmo_huella} {d.huella}</code></dd>
            <dt>Ingreso</dt><dd>{fecha(d.cargado_en)}</dd>
            <dt>Última verificación</dt><dd>{d.ultima_verificacion_en ? fecha(d.ultima_verificacion_en) : "Todavía no"}</dd>
            {d.derivada_de && (
              <><dt>Migrada desde</dt>
                <dd><Link to={`/preservacion/instanciacion/${d.derivada_de.id}`}>{d.derivada_de.nombre}</Link>
                  {d.migrada_desde?.herramienta && <span className="meta"> · {d.migrada_desde.herramienta}</span>}</dd></>
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
              <thead><tr><th>Fecha</th><th>Resultado</th><th>Cómo</th></tr></thead>
              <tbody>
                {d.verificaciones.map((v, i) => (
                  <tr key={i}>
                    <td>{fecha(v.fecha)}</td>
                    <td><span className={`insignia ${INTEGRIDAD[v.resultado].clase}`}>{INTEGRIDAD[v.resultado].texto}</span></td>
                    <td className="meta">{v.origen === "periodica" ? "Verificación periódica automática" : `Manual${v.por ? ` · ${v.por}` : ""}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="tarjeta">
        <div className="tarjeta-cab">Historial de migraciones</div>
        {d.migraciones.length === 0 && <div className="vacio">Esta instanciación no tiene migraciones.</div>}
        {d.migraciones.map((m) => (
          <div key={m.id} className="fila" style={{ alignItems: "flex-start" }}>
            <div className="fila-principal">
              <div className="nombre">{m.destino_nombre} · {m.modo === "automatica" ? "automática" : "carga manual"}</div>
              <div className="meta">
                Aprobada por {m.aprobada_por || "—"} el {fecha(m.aprobada_en)}{m.herramienta && ` · ${m.herramienta}`}
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
