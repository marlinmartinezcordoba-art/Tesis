import { pedirTexto } from "@/lib/dialogos";
import { useCallback, useEffect, useState } from "react";
import { ErrorAPI, descargar, pedir } from "@/lib/api";

// FUID, guía e índice aprobados: documentos fijos con su huella, acta y
// responsable (app/servicios/instrumentos_aprobados.py). Lo aprobado no cambia
// aunque la descripción siga creciendo; se aprueba una versión nueva.

export type TipoInstrumento = "inventario" | "guia" | "indice";

export interface InstrumentoAprobado {
  id: string; tipo: TipoInstrumento; tipo_nombre: string; version: number; titulo: string;
  nivel: { id: string; titulo: string }; estado: "vigente" | "reemplazado" | "anulado"; huella: string;
  tamano_bytes: number; acta: string | null; fecha_acta: string | null; aprobado_por: string; aprobado_en: string;
  motivo_anulacion: string | null;
}

const ESTADO: Record<InstrumentoAprobado["estado"], string> = {
  vigente: "insignia bien", reemplazado: "insignia", anulado: "insignia alerta",
};

/** Botón y formulario para aprobar lo que se ve en pantalla como documento fijo. */
export function AprobarInstrumento({ tipo, recursoId, extra, bloqueo, alAprobar }: {
  tipo: TipoInstrumento; recursoId: string; extra?: Record<string, unknown>;
  bloqueo?: string | null; alAprobar: () => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const [acta, setActa] = useState("");
  const [fecha, setFecha] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");

  async function aprobar() {
    setOcupado(true);
    setError("");
    try {
      await pedir("/api/instrumentos/aprobados", { method: "POST", body: JSON.stringify({
        tipo, recurso_id: recursoId, acta: acta.trim() || null, fecha_acta: fecha || null, ...extra }) });
      setAbierto(false);
      setActa("");
      setFecha("");
      alAprobar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo aprobar.");
    } finally {
      setOcupado(false);
    }
  }

  if (!abierto) {
    return (
      <button type="button" className="boton chico" disabled={!!bloqueo} title={bloqueo || undefined}
              onClick={() => setAbierto(true)}>
        Aprobar como documento…
      </button>
    );
  }
  return (
    <div className="tarjeta" style={{ marginTop: 12 }}>
      <div className="tarjeta-cab">Aprobar como documento</div>
      <div className="tarjeta-cuerpo">
        <p className="meta" style={{ marginTop: 0 }}>
          Se guarda el archivo tal como está ahora, con su huella SHA-256, su fecha y su nombre como responsable. Si ya
          había una versión aprobada, queda reemplazada (no se borra).
        </p>
        {error && <div className="aviso error" role="alert">{error}</div>}
        <div className="rejilla">
          <label>Acta o soporte de la aprobación <span className="meta">(opcional)</span>
            <input className="entrada" value={acta} maxLength={200} onChange={(e) => setActa(e.target.value)}
                   placeholder="Acta 07 del Comité Institucional de Gestión y Desempeño" />
          </label>
          <label>Fecha del acta
            <input className="entrada" type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} />
          </label>
        </div>
        <div className="acciones" style={{ marginTop: 10 }}>
          <button type="button" className="boton chico" disabled={ocupado} onClick={() => setAbierto(false)}>Cancelar</button>
          <button type="button" className="boton chico primario" disabled={ocupado} onClick={aprobar}>
            {ocupado ? "Aprobando…" : "Aprobar"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Versiones aprobadas de un instrumento (de un nivel, si se da). */
export function ListaAprobados({ fondoId, tipo, recursoId, puede, recargar }: {
  fondoId: string; tipo: TipoInstrumento; recursoId?: string; puede: boolean; recargar: number;
}) {
  const [lista, setLista] = useState<InstrumentoAprobado[] | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(() => {
    pedir<InstrumentoAprobado[]>(`/api/instrumentos/aprobados?fondo_id=${fondoId}`)
      .then((todos) => setLista(todos.filter((i) => i.tipo === tipo && (!recursoId || i.nivel.id === recursoId))))
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar lo aprobado."));
  }, [fondoId, tipo, recursoId]);

  useEffect(cargar, [cargar, recargar]);

  async function bajar(i: InstrumentoAprobado) {
    setError("");
    try {
      await descargar(`/api/instrumentos/aprobados/${i.id}/archivo`);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo descargar.");
    }
  }

  async function anular(i: InstrumentoAprobado) {
    const motivo = await pedirTexto(`«${i.titulo}» queda anulado con su motivo; el archivo no se borra y, si había una `
      + "versión anterior, vuelve a regir.", { titulo: "Anular un instrumento aprobado", aceptar: "Anular", minimo: 10 });
    if (!motivo) return;
    setError("");
    try {
      await pedir(`/api/instrumentos/aprobados/${i.id}/anular`, { method: "POST", body: JSON.stringify({ motivo }) });
      cargar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo anular.");
    }
  }

  if (!lista) return error ? <div className="aviso error">{error}</div> : null;
  return (
    <div className="tarjeta" style={{ marginTop: 16 }}>
      <div className="tarjeta-cab">Versiones aprobadas · {lista.length}</div>
      {error && <div className="aviso error" role="alert" style={{ margin: 12 }}>{error}</div>}
      {lista.length === 0 ? (
        <p className="meta" style={{ margin: 14 }}>Todavía no hay una versión aprobada. Lo que se exporta sin aprobar es
          una consulta del momento, no un documento del archivo.</p>
      ) : (
        <div className="tabla-desplazable">
          <table>
            <thead>
              <tr><th>Versión</th><th>Nivel</th><th>Estado</th><th>Aprobación</th><th>Huella SHA-256</th><th /></tr>
            </thead>
            <tbody>
              {lista.map((i) => (
                <tr key={i.id}>
                  <td>{i.version}</td>
                  <td>{i.nivel.titulo}</td>
                  <td>
                    <span className={ESTADO[i.estado]}>{i.estado}</span>
                    {i.motivo_anulacion && <div className="meta">{i.motivo_anulacion}</div>}
                  </td>
                  <td>
                    {new Date(i.aprobado_en).toLocaleDateString("es-CO")} · {i.aprobado_por}
                    {i.acta && <div className="meta">{i.acta}{i.fecha_acta ? ` del ${i.fecha_acta}` : ""}</div>}
                  </td>
                  <td><code title={i.huella}>{i.huella.slice(0, 12)}…</code></td>
                  <td className="acciones">
                    <button type="button" className="boton chico" onClick={() => bajar(i)}>Descargar</button>
                    {puede && i.estado !== "anulado" && (
                      <button type="button" className="boton chico" onClick={() => anular(i)}>Anular</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
