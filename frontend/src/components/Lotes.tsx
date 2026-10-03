import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ErrorAPI, pedir } from "@/lib/api";
import { fecha } from "@/lib/formato";

// Lote de transferencia (hallazgos ING-01 e ING-02): la procedencia de lo
// que llega (quién lo remite, de qué dependencia, con qué acta) y, al
// confirmarlo, el paquete de envío en BagIt y el acuse de recibo.

export interface Lote {
  id: string;
  numero: string;
  estado: "abierto" | "confirmado" | "anulado";
  forma_ingreso: string;
  forma_ingreso_nombre: string;
  remitente: { id: string; nombre: string } | null;
  dependencia_origen: { id: string; nombre: string } | null;
  acta_numero: string | null;
  acta_fecha_legible: string | null;
  acta_instanciacion_id: string | null;
  observaciones: string | null;
  creado_en: string;
  confirmado_en: string | null;
  motivo_anulacion: string | null;
  archivos: { id: string; nombre: string; estado: string; huella: string | null }[];
  listos: number;
  sip: { huella: string; archivos: number; bytes: number } | null;
}

const FORMAS: [string, string][] = [
  ["transferencia_primaria", "Transferencia primaria"], ["transferencia_secundaria", "Transferencia secundaria"],
  ["donacion", "Donación"], ["compra", "Compra"], ["comodato", "Comodato"], ["deposito", "Depósito"],
  ["otro", "Otra forma de ingreso"],
];

function ElegirAgente({ fondoId, etiqueta, valor, alCambiar }: {
  fondoId: string; etiqueta: string; valor: { id: string; nombre: string } | null;
  alCambiar: (v: { id: string; nombre: string } | null) => void;
}) {
  const [q, setQ] = useState("");
  const [lista, setLista] = useState<{ id: string; nombre: string }[]>([]);
  useEffect(() => {
    if (!q.trim()) { setLista([]); return; }
    const t = setTimeout(() => {
      pedir<{ id: string; nombre: string }[]>(`/api/vocabulario?${new URLSearchParams({ fondo_id: fondoId, clase: "agente", q: q.trim(), orden: "nombre" })}`)
        .then((l) => setLista(l.slice(0, 6))).catch(() => setLista([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q, fondoId]);
  return (
    <div className="campo">
      <label>{etiqueta}</label>
      {valor ? (
        <p style={{ margin: "4px 0" }}><b>{valor.nombre}</b>{" "}
          <button type="button" className="enlace" onClick={() => alCambiar(null)}>Cambiar</button></p>
      ) : (
        <>
          <input className="entrada" type="search" placeholder="Buscar en el vocabulario de agentes…" value={q}
                 aria-label={etiqueta} onChange={(e) => setQ(e.target.value)} />
          {lista.map((a) => (
            <div key={a.id} className="fila" style={{ padding: "4px 0" }}>
              <div className="fila-principal"><div className="nombre">{a.nombre}</div></div>
              <button type="button" className="boton chico" onClick={() => { alCambiar(a); setQ(""); }}>Elegir</button>
            </div>
          ))}
          {q.trim() && lista.length === 0 && <div className="pista">Sin coincidencias: créelo primero en Vocabularios.</div>}
        </>
      )}
    </div>
  );
}

export function NuevoLote({ fondoId, alCrear, alCancelar }: {
  fondoId: string; alCrear: (l: Lote) => void; alCancelar: () => void;
}) {
  const [forma, setForma] = useState("transferencia_primaria");
  const [dependencia, setDependencia] = useState<{ id: string; nombre: string } | null>(null);
  const [remitente, setRemitente] = useState<{ id: string; nombre: string } | null>(null);
  const [acta, setActa] = useState("");
  const [fechaActa, setFechaActa] = useState("");
  const [obs, setObs] = useState("");
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setOcupado(true);
    setError("");
    try {
      alCrear(await pedir<Lote>("/api/ingesta/lotes", { method: "POST", body: JSON.stringify({
        fondo_id: fondoId, forma_ingreso: forma, dependencia_origen_id: dependencia?.id || null,
        remitente_id: remitente?.id || null, acta_numero: acta.trim() || null, acta_fecha_edtf: fechaActa.trim() || null,
        observaciones: obs.trim() || null }) }));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo abrir el lote.");
    } finally {
      setOcupado(false);
    }
  }

  const transferencia = forma.startsWith("transferencia");
  return (
    <form className="tarjeta-cuerpo" onSubmit={enviar}>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="campo">
        <label htmlFor="forma-ingreso">Forma de ingreso <span className="meta">(ISAD-G 3.2.4)</span></label>
        <select id="forma-ingreso" className="selector" value={forma} onChange={(e) => setForma(e.target.value)}>
          {FORMAS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
        </select>
      </div>
      <ElegirAgente fondoId={fondoId} etiqueta={`Dependencia de origen${transferencia ? " (obligatoria)" : ""}`}
                    valor={dependencia} alCambiar={setDependencia} />
      <ElegirAgente fondoId={fondoId} etiqueta="Quién remite" valor={remitente} alCambiar={setRemitente} />
      <div className="campo">
        <label htmlFor="acta">Número del acta{transferencia ? " de transferencia (obligatorio)" : ""}</label>
        <input id="acta" className="entrada" maxLength={60} value={acta} onChange={(e) => setActa(e.target.value)} />
      </div>
      <div className="campo">
        <label htmlFor="fecha-acta">Fecha del acta <span className="meta">(AAAA-MM-DD)</span></label>
        <input id="fecha-acta" className="entrada" maxLength={40} placeholder="2026-09-30" value={fechaActa}
               onChange={(e) => setFechaActa(e.target.value)} />
      </div>
      <div className="campo">
        <label htmlFor="obs-lote">Observaciones</label>
        <textarea id="obs-lote" className="entrada" rows={2} maxLength={5000} value={obs} onChange={(e) => setObs(e.target.value)} />
      </div>
      <div className="acciones">
        <button className="boton primario" disabled={ocupado}>{ocupado ? "Abriendo…" : "Abrir el lote"}</button>
        <button type="button" className="boton" onClick={alCancelar}>Cancelar</button>
      </div>
    </form>
  );
}

function guardarJson(nombre: string, datos: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(datos, null, 2)], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function LotesDelFondo({ fondoId, version, puedeEscribir }: { fondoId: string; version: number; puedeEscribir: boolean }) {
  const [lotes, setLotes] = useState<Lote[] | null>(null);
  const [mensaje, setMensaje] = useState("");
  const [error, setError] = useState("");

  const cargar = useCallback(() => {
    pedir<Lote[]>(`/api/ingesta/lotes?fondo_id=${fondoId}`).then(setLotes).catch(() => setLotes([]));
  }, [fondoId]);
  useEffect(cargar, [cargar, version]);

  async function accion(ruta: string, cuerpo: unknown, aviso: string) {
    setError("");
    setMensaje("");
    try {
      await pedir(ruta, { method: ruta.endsWith("/acta") ? "PUT" : "POST", body: JSON.stringify(cuerpo) });
      setMensaje(aviso);
      cargar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo completar.");
    }
  }

  async function acuse(l: Lote) {
    try {
      guardarJson(`acuse-${l.numero}.json`, await pedir(`/api/ingesta/lotes/${l.id}/acuse`));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo obtener el acuse.");
    }
  }

  if (!lotes || lotes.length === 0) return null;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Lotes de transferencia · {lotes.length}</div>
      {mensaje && <div className="aviso bien" role="status">{mensaje}</div>}
      {error && <div className="aviso error" role="alert">{error}</div>}
      {lotes.map((l) => (
        <div className="fila" key={l.id}>
          <div className="fila-principal">
            <div className="nombre">{l.numero} · {l.forma_ingreso_nombre}
              {l.dependencia_origen && ` desde ${l.dependencia_origen.nombre}`}</div>
            <div className="meta">
              {l.acta_numero && `Acta ${l.acta_numero}${l.acta_fecha_legible ? ` (${l.acta_fecha_legible})` : ""} · `}
              {l.archivos.length} archivo{l.archivos.length === 1 ? "" : "s"}, {l.listos} listo{l.listos === 1 ? "" : "s"}
              {l.confirmado_en && ` · recibido el ${fecha(l.confirmado_en)}`}
              {l.sip && ` · paquete BagIt ${l.sip.huella.slice(0, 12)}…`}
              {l.motivo_anulacion && ` · anulado: ${l.motivo_anulacion}`}
            </div>
            {l.estado === "abierto" && puedeEscribir && l.archivos.length > 0 && (
              <div className="acciones" style={{ marginTop: 4 }}>
                <select className="selector" style={{ width: "auto" }} aria-label="Acta escaneada"
                        value={l.acta_instanciacion_id || ""}
                        onChange={(e) => e.target.value && accion(`/api/ingesta/lotes/${l.id}/acta`,
                          { instanciacion_id: e.target.value }, "Acta indicada.")}>
                  <option value="">¿Cuál archivo es el acta?</option>
                  {l.archivos.filter((a) => a.estado === "listo_para_descripcion")
                    .map((a) => <option key={a.id} value={a.id}>{a.nombre}</option>)}
                </select>
              </div>
            )}
          </div>
          <span className={`insignia ${l.estado === "confirmado" ? "bien" : l.estado === "anulado" ? "error" : "proceso"}`}>
            {l.estado}</span>
          {l.estado === "abierto" && puedeEscribir && (
            <>
              <button type="button" className="boton chico" disabled={!l.archivos.length || l.listos < l.archivos.length}
                      title={l.listos < l.archivos.length ? "Hay archivos sin terminar la ingesta" : undefined}
                      onClick={() => accion(`/api/ingesta/lotes/${l.id}/confirmar`, {},
                        `Lote ${l.numero} recibido: se armó el paquete de envío y quedó el acuse.`)}>Confirmar</button>
              <button type="button" className="boton chico" onClick={() => {
                const motivo = window.prompt("Motivo de la anulación:");
                if (motivo) accion(`/api/ingesta/lotes/${l.id}/anular`, { motivo }, `Lote ${l.numero} anulado.`);
              }}>Anular</button>
            </>
          )}
          {l.estado === "confirmado" && <button type="button" className="boton chico" onClick={() => acuse(l)}>Acuse</button>}
        </div>
      ))}
    </div>
  );
}
