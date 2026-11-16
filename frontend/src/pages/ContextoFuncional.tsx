// Contexto funcional: por qué existen los documentos. Cada función (en RiC-O, un tipo de
// actividad) con sus actividades, quién las ejerce, los mandatos que las regulan, su periodo,
// las series que produce según la TRD y los documentos que documentan cada actividad (R033).
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, pedir, puede } from "@/lib/api";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";
import { NIVEL_NOMBRE } from "@/lib/descripcion";

interface Breve { id: string; nombre: string; clase: string }
interface Docs { total: number; ejemplos: { id: string; titulo: string; nivel: string }[] }
interface Actividad extends Breve {
  ejercida_por: Breve[]; mandatos: Breve[]; periodo: { fecha_legible: string | null } | null; documentos: Docs;
}
interface Funcion extends Breve {
  actividades: Actividad[]; series: { id: string; titulo: string; codigo: string | null }[]; documentos: Docs;
}
interface Datos {
  funciones: Funcion[]; actividades_sin_funcion: Actividad[];
  totales: { funciones: number; actividades: number; con_documentos: number };
}

function Entidad({ e }: { e: Breve }) {
  const { usuario } = useSesion();
  return puede(usuario, "vocabularios") ? <Link to={`/vocabularios/${e.id}`}>{e.nombre}</Link> : <>{e.nombre}</>;
}

function Documentos({ d }: { d: Docs }) {
  if (!d.total) return <span className="meta">Sin documentos descritos todavía</span>;
  return (
    <ul className="cf-docs">
      {d.ejemplos.map((x) => (
        <li key={x.id}><Link to={`/instrumentos?vista=catalogo&ficha=${x.id}`}>{x.titulo}</Link>
          <span className="meta"> · {NIVEL_NOMBRE[x.nivel] || x.nivel}</span></li>
      ))}
      {d.total > d.ejemplos.length && <li className="meta">y {d.total - d.ejemplos.length} más</li>}
    </ul>
  );
}

function FichaActividad({ a }: { a: Actividad }) {
  return (
    <div className="cf-actividad">
      <div className="cf-cab"><span className="cf-etiqueta actividad">Actividad</span> <strong><Entidad e={a} /></strong>
        {a.periodo?.fecha_legible && <span className="meta"> · {a.periodo.fecha_legible}</span>}</div>
      {a.ejercida_por.length > 0 && <div className="meta">Ejercida por: {a.ejercida_por.map((x, i) => <span key={x.id}>{i > 0 && ", "}<Entidad e={x} /></span>)}</div>}
      {a.mandatos.length > 0 && <div className="meta">Regulada por: {a.mandatos.map((x, i) => <span key={x.id}>{i > 0 && ", "}<Entidad e={x} /></span>)}</div>}
      <div className="cf-conector meta">↓ se documenta en (RiC-R033)</div>
      <Documentos d={a.documentos} />
    </div>
  );
}

export function ContextoFuncional() {
  const { fondo } = useFondo();
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState("");
  const [abierta, setAbierta] = useState<string | null>(null);
  const [filtro, setFiltro] = useState("");

  useEffect(() => {
    if (!fondo) return;
    setDatos(null);
    pedir<Datos>(`/api/fondos/${fondo.id}/contexto-funcional`).then(setDatos)
      .catch((e) => setError(e instanceof ErrorAPI ? e.message : "No se pudo cargar el contexto funcional."));
  }, [fondo]);

  if (!fondo) return <div className="aviso">Elija un fondo para ver su contexto funcional.</div>;
  const f = filtro.trim().toLowerCase();
  const funciones = (datos?.funciones || []).filter((x) => !f || x.nombre.toLowerCase().includes(f)
    || x.actividades.some((a) => a.nombre.toLowerCase().includes(f)));

  return (
    <>
      <h1>Contexto funcional</h1>
      <p className="sub">Por qué existen los documentos: las funciones del fondo (en RiC-O, tipos de actividad), las
        actividades que las desarrollan, quién las ejerce, los mandatos que las regulan y los documentos que las
        documentan. Las funciones nacen de la TRD; las actividades, de la descripción.</p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!datos && !error && <div className="cargando">Cargando…</div>}
      {datos && (
        <>
          <section className="panel-conocimiento" aria-label="Totales">
            <div className="cifra-ric funciones"><strong>{datos.totales.funciones}</strong><span>Funciones</span></div>
            <div className="cifra-ric actividades"><strong>{datos.totales.actividades}</strong><span>Actividades</span></div>
            <div className="cifra-ric recursos"><strong>{datos.totales.con_documentos}</strong><span>Funciones con documentos</span></div>
          </section>
          <input className="entrada" type="search" placeholder="Buscar una función o actividad" aria-label="Buscar una función o actividad"
                 value={filtro} onChange={(e) => setFiltro(e.target.value)} style={{ marginBottom: 12 }} />
          {funciones.length === 0 && (
            <div className="tarjeta"><div className="vacio">Este fondo todavía no tiene funciones. Se crean al aplicar la TRD
              (columna «función») o al describir la actividad que documenta un documento.</div></div>
          )}
          {funciones.map((fn) => (
            <div className="tarjeta cf-funcion" key={fn.id}>
              <button type="button" className="componente-fila" aria-expanded={abierta === fn.id}
                      onClick={() => setAbierta(abierta === fn.id ? null : fn.id)}>
                <span className="cf-etiqueta funcion">Función</span>
                <span className="componente-nombre">{fn.nombre}</span>
                <span className="meta">{fn.actividades.length} actividad(es) · {fn.documentos.total} documento(s)</span>
              </button>
              {abierta === fn.id && (
                <div className="tarjeta-cuerpo">
                  <p className="meta"><Entidad e={fn} /> · <Link to={`/buscar?contexto_id=${fn.id}`}>Ver todos sus documentos en la búsqueda</Link>
                    {" · "}<Link to={`/instrumentos?vista=grafo&centro=entidad_vocabulario:${fn.id}`}>Verla en el grafo</Link></p>
                  {fn.series.length > 0 && (
                    <p className="meta">Series que produce (TRD): {fn.series.map((s) => `${s.codigo ? `${s.codigo} ` : ""}${s.titulo}`).join("; ")}</p>
                  )}
                  {fn.actividades.length === 0
                    ? <p className="pista">Ninguna actividad registrada con esta función. Al describir un documento, indique la
                      actividad que documenta y su función.</p>
                    : fn.actividades.map((a) => <FichaActividad key={a.id} a={a} />)}
                </div>
              )}
            </div>
          ))}
          {datos.actividades_sin_funcion.length > 0 && (
            <div className="tarjeta">
              <div className="tarjeta-cab"><span>Actividades sin función asignada</span></div>
              <div className="tarjeta-cuerpo">
                <p className="pista">Asígneles su función (tipo de actividad) desde su ficha para completar el contexto.</p>
                {datos.actividades_sin_funcion.map((a) => <FichaActividad key={a.id} a={a} />)}
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}
