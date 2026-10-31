import { useEffect, useState, type FormEvent } from "react";
import { ErrorAPI, pedir } from "@/lib/api";
import { useFondo } from "@/lib/fondo";

// Puesta en marcha: dejar RICORA en blanco para empezar a usarlo de verdad.
// Es la única excepción a «nada se borra, se anula»: por eso pide contraseña y frase,
// hace antes un respaldo completo (si falla, no borra nada), aparta los archivos en vez de
// eliminarlos y deja el hecho en la auditoría, que no se puede borrar.

interface Inventario {
  frase: string;
  se_borra: { que: string; cantidad: number }[];
  tesauros: number;
  se_conserva: string[];
  sin_clasificar: string[];
}
interface Resultado {
  borrado: { que: string; cantidad: number }[];
  respaldo: { archivo: string | null; huella: string | null };
  archivos_apartados: { movidos: number; destino: string | null };
  aviso_grafos: string | null;
  tesauros_borrados: boolean;
}

export function PuestaEnMarcha() {
  const { recargar } = useFondo();
  const [inv, setInv] = useState<Inventario | null>(null);
  const [contrasena, setContrasena] = useState("");
  const [frase, setFrase] = useState("");
  const [tesauros, setTesauros] = useState(false);
  const [trabajando, setTrabajando] = useState(false);
  const [error, setError] = useState("");
  const [hecho, setHecho] = useState<Resultado | null>(null);

  const cargar = () => pedir<Inventario>("/api/sistema/reinicio").then(setInv)
    .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo leer el inventario."));
  useEffect(() => { cargar(); }, []);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setError("");
    setTrabajando(true);
    try {
      const r = await pedir<Resultado>("/api/sistema/reinicio", {
        method: "POST", body: JSON.stringify({ contrasena, frase, incluir_tesauros: tesauros }) });
      setHecho(r);
      recargar(); // el fondo elegido ya no existe: la barra superior deja de mostrarlo
      setContrasena("");
      setFrase("");
      cargar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo dejar el sistema en blanco.");
    } finally {
      setTrabajando(false);
    }
  }

  if (!inv) return error ? <div className="aviso error" role="alert">{error}</div> : <div className="cargando">Leyendo…</div>;
  const total = inv.se_borra.reduce((n, x) => n + x.cantidad, 0);
  const listo = frase.trim().toUpperCase().replace(/\s+/g, " ") === inv.frase && contrasena.length > 0;

  return (
    <>
      {hecho && (
        <div className="aviso bien" role="status">
          <strong>El sistema quedó en blanco.</strong> Respaldo previo: <code>{hecho.respaldo.archivo}</code>
          {hecho.archivos_apartados.movidos > 0 && <> · Los archivos quedaron apartados en el servidor
            (<code>_retirado</code>), no se eliminaron.</>}
          {hecho.aviso_grafos && <> · Aviso: el almacén del grafo no se pudo vaciar ({hecho.aviso_grafos}); no queda visible.</>}
          {" "}Para empezar, cree el primer fondo en Instrumentos o cargue el CCD y la TRD.
        </div>
      )}
      <div className="tarjeta">
        <div className="tarjeta-cab">Qué se borra</div>
        <div className="tarjeta-cuerpo">
          <table className="tabla-permisos">
            <tbody>
              {inv.se_borra.map((x) => <tr key={x.que}><td>{x.que}</td><td style={{ textAlign: "right" }}>{x.cantidad.toLocaleString("es-CO")}</td></tr>)}
            </tbody>
          </table>
          <p className="meta" style={{ marginBottom: 0 }}>También: fechas, alertas, CCD y TRD, cargas, evaluaciones, propuestas del motor,
            grafos RiC-O y verificaciones. Los archivos se apartan en el servidor, no se eliminan del disco.</p>
        </div>
      </div>
      <div className="tarjeta">
        <div className="tarjeta-cab">Qué se conserva</div>
        <div className="tarjeta-cuerpo">
          <ul style={{ margin: 0 }}>{inv.se_conserva.map((x) => <li key={x}>{x}</li>)}</ul>
          {inv.tesauros > 0 && <p className="meta">Tesauros cargados: {inv.tesauros.toLocaleString("es-CO")} conceptos. Se conservan,
            salvo que marque la casilla de abajo.</p>}
        </div>
      </div>
      {inv.sin_clasificar.length > 0 && (
        <div className="aviso error" role="alert">Hay tablas sin clasificar ({inv.sin_clasificar.join(", ")}). No se puede dejar en blanco
          hasta corregirlo en el sistema.</div>
      )}
      <form className="tarjeta" onSubmit={enviar}>
        <div className="tarjeta-cab">Dejar el sistema en blanco</div>
        <div className="tarjeta-cuerpo">
          <div className="aviso alerta" role="note">Antes de borrar, RICORA hace un respaldo completo de la base de datos. Si el respaldo
            falla, no se borra nada. El archivo del respaldo queda en el servidor: pida a quien lo opera que lo copie a un lugar seguro.</div>
          {total === 0 && <p className="meta">El sistema ya está en blanco.</p>}
          <div className="casillas" style={{ margin: "10px 0 14px" }}><label><input type="checkbox" checked={tesauros} onChange={(e) => setTesauros(e.target.checked)} />
            Borrar también los tesauros cargados</label></div>
          <div className="campo">
            <label htmlFor="frase-reinicio">Escriba <strong>{inv.frase}</strong></label>
            <input id="frase-reinicio" className="entrada" autoComplete="off" value={frase} onChange={(e) => setFrase(e.target.value)} />
          </div>
          <div className="campo">
            <label htmlFor="clave-reinicio">Su contraseña</label>
            <input id="clave-reinicio" className="entrada" type="password" autoComplete="current-password" value={contrasena}
                   onChange={(e) => setContrasena(e.target.value)} />
          </div>
          {error && <div className="aviso error" role="alert">{error}</div>}
          <div className="acciones">
            <button type="submit" className="boton primario peligro" disabled={!listo || trabajando || inv.sin_clasificar.length > 0}>
              {trabajando ? "Respaldando y borrando…" : "Respaldar y dejar en blanco"}</button>
          </div>
        </div>
      </form>
    </>
  );
}
