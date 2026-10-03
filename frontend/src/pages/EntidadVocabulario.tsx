import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { FichaAutoridad, type Ficha } from "@/components/FichaAutoridad";
import { EnlaceHistoria } from "@/components/Historia";
import { ErrorAPI, pedir, puede as tienePermiso } from "@/lib/api";
import { NIVEL_NOMBRE, SUBTIPO_NOMBRE } from "@/lib/descripcion";
import { useFondo } from "@/lib/fondo";
import { fecha } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";
import { CLASE_INSIGNIA, CLASE_NOMBRE, claseRicDe, conexionesTexto, type EntidadVocabulario } from "@/lib/vocabulario";

interface Documento {
  id: string;
  titulo: string;
  nivel: string;
}

interface Detalle {
  entidad: EntidadVocabulario;
  creada_en: string;
  documentos: Documento[];
  documentos_historicos: Documento[];
  absorbidas: { id: string; nombre: string }[];
  historial: { fecha: string; por: string | null; detalle: string | null; relaciones_movidas: number | null; origen: string | null }[];
  ficha: Ficha;
}

// Fusión manual: el archivista encuentra otra entidad del mismo tipo que
// es la misma, elige cuál queda como definitiva y confirma.
function FusionManual({ entidad, fondoId, alFusionar }: {
  entidad: EntidadVocabulario;
  fondoId: string;
  alFusionar: (definitivaId: string, aviso: string) => void;
}) {
  const [abierta, setAbierta] = useState(false);
  const [q, setQ] = useState("");
  const [resultados, setResultados] = useState<EntidadVocabulario[]>([]);
  const [otra, setOtra] = useState<EntidadVocabulario | null>(null);
  const [quedaEsta, setQuedaEsta] = useState(true);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    if (!abierta || !q.trim()) {
      setResultados([]);
      return;
    }
    const t = setTimeout(async () => {
      const params = new URLSearchParams({ fondo_id: fondoId, clase: entidad.clase, q: q.trim(), orden: "nombre" });
      try {
        const r = await pedir<EntidadVocabulario[]>(`/api/vocabulario?${params}`);
        setResultados(r.filter((e) => e.id !== entidad.id).slice(0, 8));
      } catch {
        setResultados([]);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [abierta, q, fondoId, entidad]);

  function elegir(e: EntidadVocabulario) {
    setOtra(e);
    setQuedaEsta(entidad.conexiones >= e.conexiones);
  }

  async function confirmar() {
    if (!otra) return;
    const definitiva = quedaEsta ? entidad : otra;
    const absorbida = quedaEsta ? otra : entidad;
    setOcupado(true);
    setError("");
    try {
      await pedir("/api/vocabulario/fusionar", {
        method: "POST",
        body: JSON.stringify({ definitiva_id: definitiva.id, absorbida_id: absorbida.id }),
      });
      alFusionar(definitiva.id, `«${absorbida.nombre}» se fusionó en «${definitiva.nombre}».`);
      setAbierta(false);
      setOtra(null);
      setQ("");
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo fusionar.");
    } finally {
      setOcupado(false);
    }
  }

  if (!abierta) {
    return <button type="button" className="boton chico" onClick={() => setAbierta(true)}>Fusionar con otra entidad</button>;
  }

  return (
    <div className="tarjeta" style={{ marginTop: 14 }}>
      <div className="tarjeta-cab">
        <span>Fusionar con otra entidad</span>
        <button type="button" className="enlace" onClick={() => { setAbierta(false); setOtra(null); }}>Cerrar</button>
      </div>
      <div className="tarjeta-cuerpo">
        {!otra ? (
          <>
            <div className="campo">
              <label htmlFor="buscar-otra">Buscar {CLASE_NOMBRE[entidad.clase].toLowerCase()} del mismo fondo</label>
              <input id="buscar-otra" className="entrada" type="search" autoFocus value={q} onChange={(e) => setQ(e.target.value)}
                     placeholder="Escriba parte del nombre…" />
            </div>
            {q.trim() && resultados.length === 0 && <div className="meta">Sin coincidencias.</div>}
            {resultados.map((e) => (
              <div className="fila" key={e.id} style={{ padding: "8px 0" }}>
                <div className="fila-principal">
                  <div className="nombre">{e.nombre}</div>
                  <div className="meta">{e.subtipo ? `${SUBTIPO_NOMBRE[e.subtipo] || e.subtipo} · ` : ""}{conexionesTexto(e.conexiones)}</div>
                </div>
                <button type="button" className="boton chico" onClick={() => elegir(e)}>Elegir</button>
              </div>
            ))}
          </>
        ) : (
          <>
            <p className="meta" style={{ marginTop: 0 }}>¿Cuál queda como definitiva? La otra deja de aparecer en el vocabulario y sus
              documentos pasan a la definitiva. Queda registrada como fusionada, con su historia.</p>
            <div className="par-fusion" style={{ padding: 0, marginBottom: 12 }}>
              {[{ e: entidad, esta: true }, { e: otra, esta: false }].map(({ e, esta }) => (
                <label key={e.id} className={`candidata${quedaEsta === esta ? " elegida" : ""}`}>
                  <input type="radio" name="definitiva" checked={quedaEsta === esta} onChange={() => setQuedaEsta(esta)} />
                  <span>
                    <span className="nombre">{e.nombre}</span>
                    <span className="meta">{conexionesTexto(e.conexiones)}</span>
                    {quedaEsta === esta && <span className="insignia bien" style={{ marginTop: 6 }}>Queda como definitiva</span>}
                  </span>
                </label>
              ))}
            </div>
            {error && <div className="aviso error" role="alert">{error}</div>}
            <div className="acciones">
              <button type="button" className="boton chico" onClick={() => setOtra(null)}>Elegir otra</button>
              <button type="button" className="boton chico primario" disabled={ocupado} onClick={confirmar}>Confirmar fusión</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// Cada documento enlaza a su ficha en el catálogo (módulo 4); si el rol no
// consulta el catálogo pero sí describe, a la descripción interna.
function ListaDocumentos({ documentos, enlace }: { documentos: Documento[]; enlace: ((id: string) => string) | null }) {
  return (
    <>
      {documentos.map((d) => (
        <div className="fila" key={d.id}>
          <span className="insignia acento">{NIVEL_NOMBRE[d.nivel] || d.nivel}</span>
          <div className="fila-principal">
            <div className="nombre">{enlace ? <Link to={enlace(d.id)}>{d.titulo}</Link> : d.titulo}</div>
          </div>
        </div>
      ))}
    </>
  );
}

export function EntidadVocabularioDetalle() {
  const { id = "" } = useParams();
  const navegar = useNavigate();
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const puede = tienePermiso(usuario, "vocabularios", "escribir");
  const enlace = tienePermiso(usuario, "catalogo") ? (d: string) => `/instrumentos?ficha=${d}`
    : tienePermiso(usuario, "descripcion") ? (d: string) => `/descripcion/registro/${d}` : null;
  const [detalle, setDetalle] = useState<Detalle | null>(null);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");

  const cargar = useCallback(async () => {
    try {
      setDetalle(await pedir<Detalle>(`/api/vocabulario/${id}`));
      setError("");
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar la entidad.");
    }
  }, [id]);

  useEffect(() => {
    setDetalle(null);
    cargar();
  }, [cargar]);

  if (!detalle) return error ? <div className="aviso error">{error}</div> : <div className="cargando">Cargando…</div>;
  const e = detalle.entidad;

  return (
    <>
      <div className="cabecera-nivel" style={{ marginBottom: 0 }}>
        <button type="button" className="enlace" onClick={() => navegar("/vocabularios")}>← Volver a Vocabularios</button>
        <div className="acciones">
          {e.estado === "activa" && tienePermiso(usuario, "catalogo") && (
            <Link className="boton chico primario" to={`/instrumentos?vista=grafo&centro=entidad_vocabulario:${e.id}`}>Ver en grafo</Link>
          )}
          <EnlaceHistoria tipo="entidad_vocabulario" id={e.id} nombre={e.nombre} />
        </div>
      </div>
      <h1 style={{ marginTop: 10 }}>
        {e.nombre}{" "}
        {e.nivel_detalle && (
          <span className={`insignia ${e.nivel_detalle === "completo" ? "bien" : "proceso"}`} style={{ verticalAlign: "middle" }}>
            {e.nivel_detalle === "completo" ? "Ficha completa" : "Ficha mínima"}
          </span>
        )}
      </h1>
      <p className="sub">
        <span className={`insignia ${CLASE_INSIGNIA[e.clase]}`}>{CLASE_NOMBRE[e.clase]}</span>{" "}
        {e.subtipo && <span className="insignia neutra-borde">{SUBTIPO_NOMBRE[e.subtipo] || e.subtipo}</span>}{" "}
        <code className="rico">{claseRicDe(e)}</code> · {conexionesTexto(e.conexiones)} conectado{e.conexiones === 1 ? "" : "s"} ·
        registrada {fecha(detalle.creada_en)}
      </p>
      {aviso && <div className="aviso bien" role="status">{aviso}</div>}
      {e.estado === "fusionada" && (
        <div className="aviso alerta" role="status">
          Esta entidad se fusionó{e.fusionada_en && <> en <Link to={`/vocabularios/${e.fusionada_en.id}`}>«{e.fusionada_en.nombre}»</Link></>}.
          Ya no se ofrece al describir; se conserva para la trazabilidad.
        </div>
      )}

      {fondo && (
        <FichaAutoridad entidad={e} ficha={detalle.ficha} fondoId={fondo.id} puede={puede}
                        alCambiar={(texto) => { if (texto) setAviso(texto); cargar(); }} />
      )}

      <div className="tarjeta">
        <div className="tarjeta-cab">
          <span>Documentos conectados · {detalle.documentos.length}</span>
        </div>
        {detalle.documentos.length === 0 && (
          <div className="vacio">{e.estado === "fusionada" ? "Sus documentos pasaron a la entidad definitiva." : "Ningún documento publicado la menciona."}</div>
        )}
        <ListaDocumentos documentos={detalle.documentos} enlace={enlace} />
      </div>

      {detalle.documentos_historicos.length > 0 && (
        <div className="tarjeta">
          <div className="tarjeta-cab">Documentos que la citaban antes de la fusión</div>
          <ListaDocumentos documentos={detalle.documentos_historicos} enlace={enlace} />
        </div>
      )}

      {detalle.absorbidas.length > 0 && (
        <div className="tarjeta">
          <div className="tarjeta-cab">Formas absorbidas</div>
          <div className="tarjeta-cuerpo insignias">
            {detalle.absorbidas.map((a) => <Link key={a.id} className="pastilla" to={`/vocabularios/${a.id}`}>{a.nombre}</Link>)}
          </div>
        </div>
      )}

      <div className="tarjeta">
        <div className="tarjeta-cab">Historial de fusiones</div>
        {detalle.historial.length === 0 && <div className="vacio">Sin fusiones.</div>}
        {detalle.historial.map((h, i) => (
          <div className="fila" key={i}>
            <div className="fila-principal">
              <div className="nombre">{h.detalle}</div>
              <div className="meta">
                {fecha(h.fecha)}{h.por && ` · ${h.por}`}
                {h.origen && ` · ${h.origen === "sugerencia" ? "desde una sugerencia" : "fusión manual"}`}
                {h.relaciones_movidas !== null && ` · ${h.relaciones_movidas} relación(es) redirigida(s)`}
              </div>
            </div>
          </div>
        ))}
      </div>

      {puede && e.estado === "activa" && fondo && (
        <FusionManual entidad={e} fondoId={fondo.id} alFusionar={(definitivaId, texto) => {
          setAviso(texto);
          if (definitivaId === e.id) cargar();
          else navegar(`/vocabularios/${definitivaId}`);
        }} />
      )}
    </>
  );
}
