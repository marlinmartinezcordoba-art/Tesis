// Buscador unificado (brechas RF-SEARCH-001 y RF-SEARCH-002): descripción,
// texto de los documentos, identificadores y autoridades en una sola caja.
// La reserva de la Ley 1712 la aplica el servidor: aquí solo se muestra lo
// que llega.
import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ErrorAPI, pedir, puede } from "@/lib/api";
import { ALCANCE_NOMBRE, Alcance, DocumentoHallado, ResultadoBusqueda, partesResaltadas } from "@/lib/busqueda";
import { NIVEL_NOMBRE } from "@/lib/descripcion";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";
import { CLASE_NOMBRE, ClaseVocabulario } from "@/lib/vocabulario";

function Fragmento({ texto }: { texto: string }) {
  return (
    <div className="busqueda-fragmento">
      {partesResaltadas(texto).map((p, i) => (p.resaltado ? <mark key={i}>{p.texto}</mark> : <span key={i}>{p.texto}</span>))}
    </div>
  );
}

export function Buscar() {
  const { usuario } = useSesion();
  const { fondo, elegir } = useFondo();
  const navegar = useNavigate();
  const [parametros, setParametros] = useSearchParams();
  const q = parametros.get("q") || "";
  const alcance = (parametros.get("alcance") || "todo") as Alcance;
  const todos = parametros.get("fondos") === "todos";
  const [texto, setTexto] = useState(q);
  const [datos, setDatos] = useState<ResultadoBusqueda | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => setTexto(q), [q]);

  useEffect(() => {
    if (q.trim().length < 2) {
      setDatos(null);
      return;
    }
    const p = new URLSearchParams({ q, alcance });
    if (!todos && fondo) p.set("fondo_id", fondo.id);
    for (const k of ["nivel", "desde", "hasta", "agente_id", "pagina"]) {
      const v = parametros.get(k);
      if (v) p.set(k, v);
    }
    setCargando(true);
    setError("");
    pedir<ResultadoBusqueda>(`/api/buscar?${p}`)
      .then(setDatos)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo buscar."))
      .finally(() => setCargando(false));
  }, [parametros, q, alcance, todos, fondo]);

  function cambiar(cambios: Record<string, string | null>) {
    setParametros((p) => {
      const n = new URLSearchParams(p);
      for (const [k, v] of Object.entries(cambios)) {
        if (v) n.set(k, v);
        else n.delete(k);
      }
      if (!("pagina" in cambios)) n.delete("pagina");
      return n;
    });
  }

  function enviar(e: FormEvent) {
    e.preventDefault();
    cambiar({ q: texto.trim() });
  }

  function abrir(d: DocumentoHallado) {
    if (d.fondo.id !== fondo?.id) elegir(d.fondo.id);
    // Un borrador todavía no está en el catálogo: se abre su registro de descripción.
    navegar(d.borrador ? `/descripcion/registro/${d.id}` : `/instrumentos?vista=catalogo&ficha=${d.id}`);
  }

  const anioDesde = parametros.get("desde") || "";
  const anioHasta = parametros.get("hasta") || "";
  const nivel = parametros.get("nivel");
  const agente = parametros.get("agente_id");
  const paginas = datos ? Math.ceil(datos.total / datos.por_pagina) : 0;

  return (
    <>
      <h1>Buscar</h1>
      <p className="sub">
        En la descripción, en el texto de los documentos (OCR), en los códigos de referencia e identificadores
        (VIAF, ORCID…) y en las autoridades. No importan las tildes ni las mayúsculas; use comillas para una frase
        exacta y un guion delante para excluir una palabra.
      </p>
      <form className="busqueda-barra" onSubmit={enviar} role="search">
        <input className="entrada" type="search" value={texto} onChange={(e) => setTexto(e.target.value)} autoFocus
               aria-label="Qué buscar" placeholder="Ej.: «archivo municipal» Cuervo -1950" maxLength={200} />
        <button className="boton primario" type="submit" disabled={texto.trim().length < 2}>Buscar</button>
      </form>
      <div className="filtros">
        <select className="selector" aria-label="Dónde buscar" value={alcance} onChange={(e) => cambiar({ alcance: e.target.value })}>
          {(Object.keys(ALCANCE_NOMBRE) as Alcance[]).map((a) => <option key={a} value={a}>{ALCANCE_NOMBRE[a]}</option>)}
        </select>
        <select className="selector" aria-label="Fondos" value={todos ? "todos" : "activo"}
                onChange={(e) => cambiar({ fondos: e.target.value === "todos" ? "todos" : null })}>
          <option value="activo">Solo el fondo activo{fondo ? `: ${fondo.titulo}` : ""}</option>
          <option value="todos">Todos los fondos</option>
        </select>
        <input className="entrada busqueda-anio" type="number" placeholder="Desde (año)" aria-label="Desde el año"
               value={anioDesde} onChange={(e) => cambiar({ desde: e.target.value })} />
        <input className="entrada busqueda-anio" type="number" placeholder="Hasta (año)" aria-label="Hasta el año"
               value={anioHasta} onChange={(e) => cambiar({ hasta: e.target.value })} />
      </div>
      {datos?.alcance_reserva === "publico" && (
        <p className="pista">Solo se busca en lo publicado y de acceso público (Ley 1712 de 2014, arts. 18 y 19).</p>
      )}
      {error && <div className="aviso error" role="alert">{error}</div>}
      {!q && <div className="tarjeta"><div className="vacio">Escriba lo que busca: una palabra, un nombre, un código o una frase.</div></div>}
      {cargando && <div className="cargando">Buscando…</div>}
      {datos && !cargando && (
        <div className="busqueda-cuerpo">
          <aside className="busqueda-facetas">
            {Object.keys(datos.facetas.niveles).length > 0 && (
              <div className="tarjeta">
                <div className="tarjeta-cab">Nivel</div>
                <div className="tarjeta-cuerpo busqueda-opciones">
                  {nivel && <button type="button" className="enlace" onClick={() => cambiar({ nivel: null })}>Todos los niveles</button>}
                  {Object.entries(datos.facetas.niveles).map(([n, c]) => (
                    <button key={n} type="button" className={`enlace${nivel === n ? " activo" : ""}`} onClick={() => cambiar({ nivel: n })}>
                      {NIVEL_NOMBRE[n] || n} <span className="meta">({c})</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {datos.facetas.agentes.length > 0 && (
              <div className="tarjeta">
                <div className="tarjeta-cab">Agentes citados</div>
                <div className="tarjeta-cuerpo busqueda-opciones">
                  {agente && <button type="button" className="enlace" onClick={() => cambiar({ agente_id: null })}>Todos los agentes</button>}
                  {datos.facetas.agentes.map((a) => (
                    <button key={a.id} type="button" className={`enlace${agente === a.id ? " activo" : ""}`}
                            onClick={() => cambiar({ agente_id: a.id })}>
                      {a.nombre} <span className="meta">({a.documentos})</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {datos.facetas.anios && (
              <p className="pista">Fechas de los resultados: {datos.facetas.anios[0]}–{datos.facetas.anios[1]}</p>
            )}
            {todos && datos.facetas.fondos.length > 1 && (
              <p className="pista">{datos.facetas.fondos.map((f) => `${f.titulo} (${f.total})`).join(" · ")}</p>
            )}
          </aside>
          <section className="busqueda-resultados">
            {datos.autoridades.length > 0 && (
              <div className="tarjeta">
                <div className="tarjeta-cab">Autoridades ({datos.autoridades.length})</div>
                {datos.autoridades.map((a) => (
                  <div className="fila" key={a.id}>
                    <div className="fila-principal">
                      <div className="nombre">
                        {puede(usuario, "vocabularios") ? <Link to={`/vocabularios/${a.id}`}>{a.nombre}</Link> : a.nombre}
                      </div>
                      <div className="meta">
                        {CLASE_NOMBRE[a.clase as ClaseVocabulario] || a.clase} · coincide por {a.motivo} ·{" "}
                        {a.documentos === 1 ? "1 documento" : `${a.documentos} documentos`}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="tarjeta">
              <div className="tarjeta-cab">
                {datos.total === 0 ? "Documentos" : datos.total === 1 ? "1 documento" : `${datos.total} documentos`}
              </div>
              {datos.documentos.length === 0 ? (
                <div className="vacio">
                  Ningún documento coincide{nivel || agente || anioDesde || anioHasta ? " con estos filtros" : ""}.
                  {!todos && " Pruebe en todos los fondos."}
                </div>
              ) : datos.documentos.map((d) => (
                <div className="fila busqueda-fila" key={d.id}>
                  <div className="fila-principal">
                    <button type="button" className="enlace nombre" onClick={() => abrir(d)}>{d.titulo}</button>
                    <div className="meta">
                      {NIVEL_NOMBRE[d.nivel] || d.nivel}
                      {d.codigo_referencia && ` · ${d.codigo_referencia}`}
                      {d.fechas && ` · ${d.fechas}`}
                      {(todos || d.fondo.id !== fondo?.id) && ` · ${d.fondo.titulo}`}
                      {d.ruta.length > 0 && ` · ${d.ruta.join(" › ")}`}
                    </div>
                    {d.fragmento && <Fragmento texto={d.fragmento} />}
                    <div className="insignias">
                      {d.borrador && <span className="insignia alerta">Borrador sin publicar</span>}
                      {d.motivos.map((m) => <span key={m} className="insignia neutra-borde">{m}</span>)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {paginas > 1 && (
              <div className="filtros">
                <button type="button" className="boton chico" disabled={datos.pagina <= 1}
                        onClick={() => cambiar({ pagina: String(datos.pagina - 1) })}>Anterior</button>
                <span className="meta">Página {datos.pagina} de {paginas}</span>
                <button type="button" className="boton chico" disabled={datos.pagina >= paginas}
                        onClick={() => cambiar({ pagina: String(datos.pagina + 1) })}>Siguiente</button>
              </div>
            )}
            {datos.archivos_sin_describir.length > 0 && (
              <div className="tarjeta">
                <div className="tarjeta-cab">Archivos todavía sin describir ({datos.archivos_sin_describir.length})</div>
                {datos.archivos_sin_describir.map((a) => (
                  <div className="fila" key={a.id}>
                    <div className="fila-principal">
                      <div className="nombre">{a.nombre}</div>
                      <div className="meta">{a.fondo} · el texto coincide, pero nadie lo ha descrito</div>
                    </div>
                    <Link className="boton chico" to="/descripcion?vista=cola">Ir a Por describir</Link>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}

/** Caja de la barra superior: lleva a la página de búsqueda. */
export function CajaBusqueda() {
  const { usuario } = useSesion();
  const navegar = useNavigate();
  const [texto, setTexto] = useState("");
  if (!puede(usuario, "catalogo")) return null;
  return (
    <form className="caja-busqueda" role="search" onSubmit={(e) => {
      e.preventDefault();
      if (texto.trim().length < 2) return;
      navegar(`/buscar?q=${encodeURIComponent(texto.trim())}`);
      setTexto("");
    }}>
      <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2"
           strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
      <input type="search" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Buscar en el archivo…"
             aria-label="Buscar en el archivo" maxLength={200} />
    </form>
  );
}
