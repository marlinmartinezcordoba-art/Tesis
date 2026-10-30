import { pedirTexto } from "@/lib/dialogos";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, pedir } from "@/lib/api";
import { useFondo } from "@/lib/fondo";
import { fecha } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";
import { atiendeAlertas } from "@/components/Marco";
import { TIPO_ALERTA, enlaceDeAlerta } from "@/lib/alertas";

interface Alerta {
  id: string;
  tipo: string;
  severidad: "alta" | "media" | "baja";
  modulo: string;
  mensaje: string;
  creada_en: string;
  atendida_en: string | null;
  atendida_por: string | null;
  nota_atencion: string | null;
  entidad_tipo: string;
  entidad_id: string;
}

const CLASE: Record<Alerta["severidad"], string> = { alta: "error", media: "alerta", baja: "proceso" };
const MODULO: Record<string, string> = {
  ingesta: "Carga de documentos", descripcion: "Descripción", vocabularios: "Autoridades y términos",
  instrumentos: "Consulta y difusión", preservacion: "Preservación",
};
const TIPO = TIPO_ALERTA;

export function Alertas() {
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const puedeAtender = atiendeAlertas(usuario);
  const [vista, setVista] = useState<"pendientes" | "atendidas">("pendientes");
  const [alertas, setAlertas] = useState<Alerta[] | null>(null);
  const [error, setError] = useState("");

  const cargar = useCallback(async () => {
    if (!fondo) return;
    try {
      setAlertas(await pedir<Alerta[]>(`/api/alertas?fondo_id=${fondo.id}&atendidas=${vista === "atendidas"}`));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudieron cargar las alertas.");
    }
  }, [fondo, vista]);

  useEffect(() => {
    setAlertas(null);
    cargar();
  }, [cargar]);

  // Para los archivos cargados antes de que existiera la búsqueda de datos personales (Ley 1581).
  const [revisando, setRevisando] = useState(false);
  const [revision, setRevision] = useState("");
  async function revisarDatos() {
    if (!fondo) return;
    setRevisando(true);
    setError("");
    try {
      const r = await pedir<{ archivos: number; hallazgos_nuevos: number; sensibles_o_menores: number }>(
        `/api/descripcion/datos-personales/revisar-fondo?fondo_id=${fondo.id}`, { method: "POST" });
      setRevision(`Se revisaron ${r.archivos} archivo(s): ${r.hallazgos_nuevos} posible(s) dato(s) personal(es) nuevos, `
        + `${r.sensibles_o_menores} sensibles o de menores. Se revisan al describir cada documento.`);
      window.dispatchEvent(new Event("ricora:alertas"));
      cargar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo hacer la búsqueda.");
    } finally {
      setRevisando(false);
    }
  }

  async function atender(a: Alerta) {
    const nota = await pedirTexto("Nota breve de lo que se hizo. Es opcional y queda con la alerta.",
      { titulo: "Atender la alerta", aceptar: "Marcar como atendida", opcional: true });
    if (nota === null) return;
    setError("");
    try {
      await pedir(`/api/alertas/${a.id}/atender`, { method: "POST", body: JSON.stringify({ nota }) });
      window.dispatchEvent(new Event("ricora:alertas"));
      cargar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo marcar como atendida.");
    }
  }

  return (
    <>
      <h1>Panel de alertas</h1>
      <p className="sub">
        Todo lo que requiere revisión humana en el fondo, venga del módulo que venga. Las más graves aparecen primero.
        Una alerta no se borra: se marca como atendida.
      </p>
      <div className="pestanas" role="tablist">
        {(["pendientes", "atendidas"] as const).map((v) => (
          <button key={v} type="button" role="tab" aria-selected={vista === v}
                  className={`pestana${vista === v ? " activa" : ""}`} onClick={() => setVista(v)}>
            {v === "pendientes" ? "Pendientes" : "Atendidas"}
          </button>
        ))}
      </div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {usuario?.es_administrador && (
        <div className="acciones" style={{ marginBottom: 12 }}>
          <button type="button" className="boton chico" disabled={revisando} onClick={revisarDatos}
                  title="Busca cédulas, tarjetas de identidad, correos, teléfonos, datos de salud y de menores en el texto de los archivos ya cargados">
            {revisando ? "Buscando…" : "Buscar datos personales en lo ya cargado"}</button>
          {revision && <span className="meta">{revision}</span>}
        </div>
      )}
      <div className="tarjeta">
        {alertas === null ? (
          <div className="vacio">Cargando…</div>
        ) : alertas.length === 0 ? (
          <div className="vacio">{vista === "pendientes" ? "No hay alertas pendientes en este fondo." : "Todavía no se ha atendido ninguna alerta."}</div>
        ) : (
          alertas.map((a) => (
            <div className="fila" key={a.id}>
              <div className="fila-principal">
                <div className="nombre">{TIPO[a.tipo] || a.tipo}</div>
                <div className="meta" style={{ color: "var(--ink)", fontSize: ".86rem" }}>{a.mensaje}</div>
                <div className="meta">
                  {MODULO[a.modulo] || a.modulo} · {fecha(a.creada_en)}
                  {a.atendida_en && ` · atendida por ${a.atendida_por || "el sistema"} el ${fecha(a.atendida_en)}`}
                  {a.nota_atencion && ` · «${a.nota_atencion}»`}
                </div>
              </div>
              <span className={`insignia ${CLASE[a.severidad]}`}>Severidad {a.severidad}</span>
              {vista === "pendientes" && enlaceDeAlerta(a) && (
                <Link className="boton chico" to={enlaceDeAlerta(a)!.ruta}>{enlaceDeAlerta(a)!.texto}</Link>
              )}
              {vista === "pendientes" && puedeAtender && (
                <button type="button" className="boton chico" onClick={() => atender(a)}>Marcar atendida</button>
              )}
            </div>
          ))
        )}
      </div>
    </>
  );
}
