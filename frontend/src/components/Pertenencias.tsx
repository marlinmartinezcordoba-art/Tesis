import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Ventana } from "@/components/Ventana";
import { ErrorAPI, pedir, puede } from "@/lib/api";
import { NIVEL_NOMBRE, nivelesSuperiores, type NivelSuperior } from "@/lib/descripcion";
import { useSesion } from "@/lib/sesion";

// RiC: un documento puede estar en varios conjuntos. El lugar orgánico (el del
// cuadro de clasificación) es uno solo; las pertenencias adicionales, por
// ejemplo en una colección (rst:Collection), se agregan y se quitan aquí.

interface Breve { id: string; titulo: string; nivel: string; relacion_id: string }

export function Pertenencias<R extends { id: string; fondo_id: string; nivel: string; tambien_en?: Breve[];
  miembros_adicionales?: Breve[]; incluido_en?: { id: string } | null }>({ registro, alCambiar }: {
  registro: R; alCambiar: (r: R) => void;
}) {
  const { usuario } = useSesion();
  const puedeEditar = puede(usuario, "descripcion", "escribir");
  const [abierta, setAbierta] = useState(false);
  const tambien = registro.tambien_en || [];
  const miembros = registro.miembros_adicionales || [];

  async function quitar(b: Breve) {
    if (!window.confirm(`¿Quitar esta descripción de «${b.titulo}»? Su lugar en el cuadro no cambia.`)) return;
    try {
      alCambiar(await pedir<R>(`/api/descripcion/registros/${registro.id}/inclusiones/${b.relacion_id}/anular`,
        { method: "POST" }));
    } catch (err) {
      window.alert(err instanceof ErrorAPI ? err.message : "No se pudo quitar.");
    }
  }

  if (!tambien.length && !miembros.length && !puedeEditar) return null;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Pertenece también a</div>
      <div className="tarjeta-cuerpo">
        <p className="meta" style={{ marginTop: 0 }}>
          En RiC un documento puede estar en varios conjuntos a la vez <code className="rico">rico:isOrWasIncludedIn</code>.
          Su lugar orgánico es el del cuadro de clasificación; aquí se agregan otros, como una colección.
        </p>
        {tambien.length === 0 && <p className="meta">Solo está en su lugar orgánico.</p>}
        <ul className="lista-simple">
          {tambien.map((b) => (
            <li key={b.relacion_id}>
              {NIVEL_NOMBRE[b.nivel] || b.nivel}: <Link to={`/descripcion/registro/${b.id}`}>{b.titulo}</Link>
              {puedeEditar && <button type="button" className="enlace" style={{ marginLeft: 8 }} onClick={() => quitar(b)}>Quitar</button>}
            </li>
          ))}
        </ul>
        {miembros.length > 0 && (
          <>
            <div className="meta" style={{ marginTop: 10 }}>Reúne además ({miembros.length}):</div>
            <ul className="lista-simple">
              {miembros.map((b) => (
                <li key={b.relacion_id}>{NIVEL_NOMBRE[b.nivel] || b.nivel}: <Link to={`/descripcion/registro/${b.id}`}>{b.titulo}</Link></li>
              ))}
            </ul>
          </>
        )}
        {puedeEditar && registro.nivel !== "fondo" && (
          <button type="button" className="boton chico" onClick={() => setAbierta(true)}>+ Incluir en otro conjunto</button>
        )}
      </div>
      {abierta && <Incluir registro={registro} alCerrar={() => setAbierta(false)}
                           alIncluir={(r) => { setAbierta(false); alCambiar(r); }} />}
    </div>
  );
}

function Incluir<R extends { id: string; fondo_id: string; nivel: string; incluido_en?: { id: string } | null;
  tambien_en?: Breve[] }>({ registro, alCerrar, alIncluir }: {
  registro: R; alCerrar: () => void; alIncluir: (r: R) => void;
}) {
  const [opciones, setOpciones] = useState<NivelSuperior[] | null>(null);
  const [conjunto, setConjunto] = useState("");
  const [nueva, setNueva] = useState("");
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    // Cualquier agrupación del fondo, menos la orgánica y las que ya lo incluyen.
    const ya = new Set([registro.id, registro.incluido_en?.id, ...(registro.tambien_en || []).map((b) => b.id)]);
    nivelesSuperiores(registro.fondo_id, registro.nivel, true)
      .then((l) => setOpciones(l.filter((x) => !ya.has(x.id) && x.nivel !== "fondo")))
      .catch(() => setOpciones([]));
  }, [registro]);

  async function incluir(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setOcupado(true);
    try {
      let destino = conjunto;
      if (!destino) {
        const c = await pedir<{ id: string }>("/api/descripcion/agrupaciones", { method: "POST", body: JSON.stringify({
          fondo_id: registro.fondo_id, nivel: "coleccion", titulo: nueva.trim() }) });
        destino = c.id;
      }
      alIncluir(await pedir<R>(`/api/descripcion/registros/${registro.id}/inclusiones`,
        { method: "POST", body: JSON.stringify({ conjunto_id: destino }) }));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo incluir.");
    } finally {
      setOcupado(false);
    }
  }

  const colecciones = (opciones || []).filter((o) => o.nivel === "coleccion");
  const otras = (opciones || []).filter((o) => o.nivel !== "coleccion");
  return (
    <Ventana titulo="Incluir en otro conjunto" alCerrar={alCerrar}>
      <form onSubmit={incluir}>
        {error && <div className="aviso error" role="alert">{error}</div>}
        <div className="campo">
          <label htmlFor="conjunto">Conjunto existente</label>
          <select id="conjunto" className="selector" value={conjunto} onChange={(e) => setConjunto(e.target.value)}
                  disabled={!opciones}>
            <option value="">{opciones ? "— Elija, o cree una colección nueva abajo —" : "Cargando…"}</option>
            {colecciones.length > 0 && <optgroup label="Colecciones">
              {colecciones.map((o) => <option key={o.id} value={o.id}>{o.titulo}</option>)}</optgroup>}
            {otras.length > 0 && <optgroup label="Otras agrupaciones del fondo">
              {otras.map((o) => <option key={o.id} value={o.id}>{NIVEL_NOMBRE[o.nivel] || o.nivel}: {o.titulo}</option>)}</optgroup>}
          </select>
        </div>
        {!conjunto && (
          <div className="campo">
            <label htmlFor="nueva-col">O una colección nueva <span className="meta">(rico:RecordSet · rst:Collection)</span></label>
            <input id="nueva-col" className="entrada" value={nueva} placeholder="Documentos sobre el ferrocarril"
                   onChange={(e) => setNueva(e.target.value)} />
          </div>
        )}
        <p className="meta">Su lugar en el cuadro de clasificación no cambia: esto agrega una pertenencia.</p>
        <div className="acciones">
          <button type="submit" className="boton primario" disabled={ocupado || (!conjunto && nueva.trim().length < 3)}>
            {ocupado ? "Incluyendo…" : "Incluir"}</button>
          <button type="button" className="boton" onClick={alCerrar}>Cancelar</button>
        </div>
      </form>
    </Ventana>
  );
}
