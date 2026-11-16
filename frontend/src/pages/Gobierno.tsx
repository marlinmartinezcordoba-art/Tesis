// Gobierno archivístico: el PGD y el PINAR como mandatos RiC (rico:Mandate) adoptados por su acto
// administrativo, y sus programas, proyectos y acciones como actividades que regulan.
import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, descargar, pedir, puede, subir } from "@/lib/api";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";
import { ParaQueSirve } from "@/components/ParaQueSirve";

interface Plan {
  id: string; tipo: string; sigla: string; nombre: string; acto: string | null; vigencia: string | null;
  vigencia_legible: string | null; acciones: { id: string; nombre: string; documentos: number }[];
  documento: { nombre: string; tamano: number; huella: string; formato: string } | null;
}
interface Datos { planes: Plan[]; faltan: string[] }

// El documento del plan (el PGD o el PINAR tal como se aprobó), en cualquier formato, con su huella.
function DocumentoPlan({ fondoId, plan, puedeAdjuntar, alGuardar }: {
  fondoId: string; plan: Plan; puedeAdjuntar: boolean; alGuardar: (d: Datos) => void;
}) {
  const [error, setError] = useState("");
  const [subiendo, setSubiendo] = useState(false);
  const url = `/api/fondos/${fondoId}/gobierno/planes/${plan.id}/documento`;
  async function adjuntar(archivo: File | undefined) {
    if (!archivo) return;
    setError("");
    setSubiendo(true);
    try {
      const datos = new FormData();
      datos.append("archivo", archivo, archivo.name);
      alGuardar(await subir<Datos>(url, datos, () => undefined));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo adjuntar.");
    } finally {
      setSubiendo(false);
    }
  }
  return (
    <p className="meta" style={{ marginTop: 0 }}>
      {plan.documento ? <>Documento: <button type="button" className="enlace" onClick={() => descargar(url).catch(() => undefined)}>
        {plan.documento.nombre}</button> · {Math.max(1, Math.round(plan.documento.tamano / 1024))} KB
        · <span title={`SHA-256 ${plan.documento.huella}`}>huella {plan.documento.huella.slice(0, 12)}…</span></>
        : "Sin documento adjunto."}
      {puedeAdjuntar && (
        <label className="boton chico" style={{ marginLeft: 8, cursor: "pointer" }}>
          {subiendo ? "Adjuntando…" : plan.documento ? "Reemplazar documento" : "Adjuntar documento"}
          <input type="file" hidden disabled={subiendo} onChange={(e) => { adjuntar(e.target.files?.[0]); e.target.value = ""; }} />
        </label>
      )}
      {error && <span className="aviso error" role="alert" style={{ marginLeft: 8 }}>{error}</span>}
    </p>
  );
}

function NuevaAccion({ fondoId, plan, alGuardar }: { fondoId: string; plan: Plan; alGuardar: (d: Datos) => void }) {
  const [tipo, setTipo] = useState("programa");
  const [nombre, setNombre] = useState("");
  const [error, setError] = useState("");
  async function guardar(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      alGuardar(await pedir<Datos>(`/api/fondos/${fondoId}/gobierno/planes/${plan.id}/acciones`,
        { method: "POST", body: JSON.stringify({ tipo, nombre }) }));
      setNombre("");
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo agregar.");
    }
  }
  return (
    <form onSubmit={guardar} className="acciones" style={{ alignItems: "center", marginTop: 8 }}>
      <select className="selector" style={{ width: "auto" }} aria-label="Tipo" value={tipo} onChange={(e) => setTipo(e.target.value)}>
        <option value="programa">Programa</option><option value="proyecto">Proyecto</option><option value="accion">Acción</option>
      </select>
      <input className="entrada" style={{ flex: 1, minWidth: 200 }} required minLength={3} maxLength={300} value={nombre}
             onChange={(e) => setNombre(e.target.value)} placeholder="Ej.: Programa de documentos vitales" aria-label="Nombre" />
      <button type="submit" className="boton chico">Agregar</button>
      {error && <span className="aviso error" role="alert">{error}</span>}
    </form>
  );
}

export function Gobierno() {
  const { fondo } = useFondo();
  const { usuario } = useSesion();
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState("");
  const [tipo, setTipo] = useState("pgd");
  const [vigencia, setVigencia] = useState("");
  const [acto, setActo] = useState("");
  const [archivo, setArchivo] = useState<File | null>(null);

  useEffect(() => {
    if (!fondo) return;
    pedir<Datos>(`/api/fondos/${fondo.id}/gobierno`).then(setDatos)
      .catch((e) => setError(e instanceof ErrorAPI ? e.message : "No se pudo cargar."));
  }, [fondo]);

  async function registrar(e: FormEvent) {
    e.preventDefault();
    if (!fondo) return;
    setError("");
    try {
      const antes = new Set((datos?.planes || []).map((p) => p.id));
      let nuevos = await pedir<Datos>(`/api/fondos/${fondo.id}/gobierno/planes`,
        { method: "POST", body: JSON.stringify({ tipo, vigencia, acto: acto.trim() || null }) });
      const creado = nuevos.planes.find((p) => !antes.has(p.id));
      if (archivo && creado) {
        const f = new FormData();
        f.append("archivo", archivo, archivo.name);
        nuevos = await subir<Datos>(`/api/fondos/${fondo.id}/gobierno/planes/${creado.id}/documento`, f, () => undefined);
      }
      setDatos(nuevos);
      setVigencia("");
      setActo("");
      setArchivo(null);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo registrar.");
    }
  }

  if (!fondo) return <div className="aviso">Elija un fondo.</div>;
  return (
    <>
      <h1>Gobierno archivístico</h1>
      <ParaQueSirve><p>El Programa de Gestión Documental (PGD) y el Plan Institucional de Archivos (PINAR) como contexto
        de la gestión. En RiC, un plan adoptado por acto administrativo es un mandato (rico:Mandate), y sus programas,
        proyectos y acciones son actividades que ese mandato regula. Los documentos que documentan una de ellas aparecen
        bajo ella.</p></ParaQueSirve>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {datos?.faltan.length ? <p className="pista">Falta registrar: {datos.faltan.join(" y ")}.</p> : null}
      {usuario?.es_administrador && (
        <form className="tarjeta tca-form" onSubmit={registrar} style={{ padding: 14 }}>
          <div className="campo"><label htmlFor="g-tipo">Plan</label>
            <select id="g-tipo" className="selector" value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="pgd">PGD · Programa de Gestión Documental</option><option value="pinar">PINAR · Plan Institucional de Archivos</option>
            </select></div>
          <div className="campo"><label htmlFor="g-vig">Vigencia <span className="meta">(p. ej. 2025-2028)</span></label>
            <input id="g-vig" className="entrada" required value={vigencia} onChange={(e) => setVigencia(e.target.value)}
                   placeholder="2025-2028" /></div>
          <div className="campo"><label htmlFor="g-acto">Acto que lo adopta <span className="meta">(opcional)</span></label>
            <input id="g-acto" className="entrada" minLength={5} value={acto} onChange={(e) => setActo(e.target.value)}
                   placeholder="Resolución 123 de 2024" /></div>
          <div className="campo"><label htmlFor="g-doc">Documento del plan <span className="meta">(opcional, cualquier formato)</span></label>
            <input id="g-doc" type="file" onChange={(e) => setArchivo(e.target.files?.[0] || null)} /></div>
          <div className="acciones"><button type="submit" className="boton primario chico">Registrar plan</button></div>
        </form>
      )}
      {!datos && !error && <div className="cargando">Cargando…</div>}
      {datos?.planes.map((p) => (
        <div className="tarjeta" key={p.id}>
          <div className="tarjeta-cab">
            <span><span className="cf-etiqueta funcion">{p.sigla}</span> {p.nombre}</span>
            <span className="meta">{p.vigencia_legible || p.vigencia}</span>
          </div>
          <div className="tarjeta-cuerpo">
            <DocumentoPlan fondoId={fondo.id} plan={p} puedeAdjuntar={!!usuario?.es_administrador} alGuardar={setDatos} />
            <p className="meta" style={{ marginTop: 0 }}>{p.acto || "Sin acto administrativo registrado."} <code className="rico">rico:Mandate</code>
              {puede(usuario, "vocabularios") && <> · <Link to={`/vocabularios/${p.id}`}>Abrir su ficha</Link></>}</p>
            {p.acciones.length === 0 ? <p className="pista">Sin programas, proyectos ni acciones todavía.</p> : (
              <ul className="cf-docs">
                {p.acciones.map((a) => (
                  <li key={a.id}>{a.nombre} <span className="meta">· regulada por el plan (rico:regulatesOrRegulated) · {a.documentos} documento(s)</span>
                    {" "}<Link to={`/buscar?contexto_id=${a.id}`}>Ver documentos</Link></li>
                ))}
              </ul>
            )}
            {usuario?.es_administrador && <NuevaAccion fondoId={fondo.id} plan={p} alGuardar={setDatos} />}
          </div>
        </div>
      ))}
    </>
  );
}
