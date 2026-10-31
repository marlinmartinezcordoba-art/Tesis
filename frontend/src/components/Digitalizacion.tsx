import { useCallback, useEffect, useState } from "react";
import { ErrorAPI, pedir } from "@/lib/api";
import { fecha } from "@/lib/formato";

// Estado de digitalización del documento (requisito 5): aparte de su estado documental (borrador,
// definitivo…). «Digitalizado» no es «verificado»: lo segundo lo declara una persona, comprobación
// por comprobación, y queda con su nombre y su fecha.

interface Par {
  relacion_id: string;
  original: { nombre: string; soporte: string | null };
  copia: { nombre: string; formato: string | null };
  datos: { responsable: string | null; fecha: string | null; equipo: string | null; resolucion_ppp: number | null; nota: string | null } | null;
  estado: "digitalizado" | "verificado" | "con_problemas";
  verificaciones: { id: string; resultado: string; comprobaciones: Record<string, boolean>; nota: string | null;
    verificado_por: string | null; verificado_en: string }[];
  pistas: { completitud: { revisable: boolean | null; hallazgos: string[]; explicacion?: string | null }; huella: string | null };
}
interface Estado { estado: string; estado_nombre: string; digitalizaciones: Par[]; comprobaciones: Record<string, string> }

const CLASE: Record<string, string> = { verificado: "bien", con_problemas: "error", digitalizado: "alerta",
  sin_digitalizar: "proceso", nacido_digital: "proceso", sin_instanciaciones: "proceso" };

export function Digitalizacion({ recursoId, puede }: { recursoId: string; puede: boolean }) {
  const [e, setE] = useState<Estado | null>(null);
  const [error, setError] = useState("");
  const cargar = useCallback(() => {
    pedir<Estado>(`/api/descripcion/registros/${recursoId}/digitalizacion`).then(setE).catch(() => setE(null));
  }, [recursoId]);
  useEffect(cargar, [cargar]);
  if (!e) return null;

  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">
        <span>Digitalización</span>
        <span className={`insignia ${CLASE[e.estado] || "proceso"}`}>{e.estado_nombre}</span>
      </div>
      <div className="tarjeta-cuerpo">
        <p className="meta" style={{ marginTop: 0 }}>
          Es aparte del estado del documento: un documento definitivo puede estar sin digitalizar, y una copia digital no
          está verificada hasta que alguien la revisa frente al original.
        </p>
        {e.estado === "sin_digitalizar" && <p className="meta">Tiene original físico y ninguna copia digital derivada.</p>}
        {e.estado === "nacido_digital" && <p className="meta">No tiene original físico registrado: no se digitalizó.</p>}
        {error && <div className="aviso error" role="alert">{error}</div>}
        {e.digitalizaciones.map((p) => (
          <ParDigital key={p.relacion_id} par={p} comprobaciones={e.comprobaciones} puede={puede}
                      alCambiar={(nuevo) => { setE(nuevo); setError(""); }} alFallar={setError} />
        ))}
      </div>
    </div>
  );
}

function ParDigital({ par, comprobaciones, puede, alCambiar, alFallar }: {
  par: Par; comprobaciones: Record<string, string>; puede: boolean; alCambiar: (e: Estado) => void; alFallar: (m: string) => void;
}) {
  const [editando, setEditando] = useState(false);
  const [verificando, setVerificando] = useState(false);
  const [datos, setDatos] = useState({ responsable: par.datos?.responsable || "", fecha: par.datos?.fecha || "",
    equipo: par.datos?.equipo || "", resolucion_ppp: par.datos?.resolucion_ppp ? String(par.datos.resolucion_ppp) : "",
    nota: par.datos?.nota || "" });
  const [marcas, setMarcas] = useState<Record<string, boolean>>(Object.fromEntries(Object.keys(comprobaciones).map((k) => [k, false])));
  const [nota, setNota] = useState("");
  const ultima = par.verificaciones[0];

  async function guardarDatos() {
    try {
      alCambiar(await pedir<Estado>(`/api/descripcion/digitalizaciones/${par.relacion_id}`, { method: "PUT", body: JSON.stringify({
        responsable: datos.responsable || null, fecha: datos.fecha || null, equipo: datos.equipo || null,
        resolucion_ppp: datos.resolucion_ppp ? Number(datos.resolucion_ppp) : null, nota: datos.nota || null }) }));
      setEditando(false);
    } catch (err) {
      alFallar(err instanceof ErrorAPI ? err.message : "No se pudo guardar.");
    }
  }

  async function verificar() {
    try {
      alCambiar(await pedir<Estado>(`/api/descripcion/digitalizaciones/${par.relacion_id}/verificaciones`, {
        method: "POST", body: JSON.stringify({ comprobaciones: marcas, nota: nota || null }) }));
      setVerificando(false);
      setNota("");
    } catch (err) {
      alFallar(err instanceof ErrorAPI ? err.message : "No se pudo registrar la verificación.");
    }
  }

  const todas = Object.values(marcas).every(Boolean);
  return (
    <div className="fila" style={{ display: "block", padding: "10px 0" }}>
      <div className="nombre">{par.original.nombre} → {par.copia.nombre}
        <span className={`insignia ${CLASE[par.estado]}`} style={{ marginLeft: 8 }}>
          {par.estado === "verificado" ? "Verificada" : par.estado === "con_problemas" ? "Con problemas" : "Sin verificar"}</span>
      </div>
      <div className="meta">
        {par.datos ? [par.datos.responsable && `Digitalizó: ${par.datos.responsable}`, par.datos.fecha && fecha(par.datos.fecha),
          par.datos.equipo, par.datos.resolucion_ppp && `${par.datos.resolucion_ppp} ppp`].filter(Boolean).join(" · ")
          : "Sin datos de quién y cuándo se digitalizó."}
        {puede && !editando && <> <button type="button" className="enlace" onClick={() => setEditando(true)}>{par.datos ? "Corregir" : "Registrar"}</button></>}
      </div>
      {editando && (
        <div className="acciones-chicas">
          <input className="entrada" placeholder="Quién digitalizó" value={datos.responsable} maxLength={200}
                 onChange={(x) => setDatos({ ...datos, responsable: x.target.value })} />
          <input className="entrada" type="date" aria-label="Fecha" value={datos.fecha} onChange={(x) => setDatos({ ...datos, fecha: x.target.value })} />
          <input className="entrada" placeholder="Equipo (escáner)" value={datos.equipo} maxLength={200}
                 onChange={(x) => setDatos({ ...datos, equipo: x.target.value })} />
          <input className="entrada" type="number" min={50} max={4800} placeholder="Resolución (ppp)" value={datos.resolucion_ppp}
                 onChange={(x) => setDatos({ ...datos, resolucion_ppp: x.target.value })} />
          <button type="button" className="boton chico primario" onClick={guardarDatos}>Guardar</button>
          <button type="button" className="boton chico" onClick={() => setEditando(false)}>Cancelar</button>
        </div>
      )}
      {ultima && (
        <div className="meta">Última verificación: {ultima.resultado === "verificada" ? "verificada" : "con problemas"} por
          {" "}{ultima.verificado_por || "—"} el {fecha(ultima.verificado_en)}{ultima.nota ? ` · «${ultima.nota}»` : ""}
          {par.verificaciones.length > 1 && ` · ${par.verificaciones.length - 1} anterior(es) en el historial`}</div>
      )}
      {puede && !verificando && <button type="button" className="boton chico" style={{ marginTop: 6 }} onClick={() => setVerificando(true)}>
        Verificar la copia</button>}
      {verificando && (
        <div className="tarjeta" style={{ marginTop: 8 }}>
          <div className="tarjeta-cuerpo">
            {par.pistas.completitud.revisable && par.pistas.completitud.hallazgos.length > 0 && (
              <div className="aviso alerta" role="note">El sistema encontró en el texto de la copia: {par.pistas.completitud.hallazgos.join("; ")}</div>
            )}
            {Object.entries(comprobaciones).map(([k, texto]) => (
              <label key={k} style={{ display: "block" }}>
                <input type="checkbox" checked={marcas[k]} onChange={(x) => setMarcas({ ...marcas, [k]: x.target.checked })} /> {texto}
              </label>
            ))}
            <textarea className="entrada" rows={2} maxLength={2000} value={nota} onChange={(x) => setNota(x.target.value)}
                      placeholder={todas ? "Nota (opcional)" : "Qué problema encontró (obligatorio si falta alguna comprobación)"} />
            <div className="acciones">
              <button type="button" className="boton chico primario" disabled={!todas && nota.trim().length < 4} onClick={verificar}>
                {todas ? "Registrar como verificada" : "Registrar con problemas"}</button>
              <button type="button" className="boton chico" onClick={() => setVerificando(false)}>Cancelar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
