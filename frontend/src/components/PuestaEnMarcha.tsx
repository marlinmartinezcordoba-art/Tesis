import { useEffect, useState, type FormEvent } from "react";
import { ErrorAPI, descargar, pedir } from "@/lib/api";
import { fecha, peso } from "@/lib/formato";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";

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
  respaldos: { id: string; archivo: string | null; fecha: string; tamano_bytes: number | null; huella: string | null;
    descargado_en: string | null; disponible: boolean }[];
}
interface Resultado {
  borrado: { que: string; cantidad: number }[];
  respaldo: { id: string; archivo: string | null; huella: string | null };
  archivos_apartados: { movidos: number; destino: string | null };
  aviso_grafos: string | null;
  tesauros_borrados: boolean;
}

export function PuestaEnMarcha() {
  const { recargar } = useFondo();
  const { usuario } = useSesion();
  const [inv, setInv] = useState<Inventario | null>(null);
  const [contrasena, setContrasena] = useState("");
  const [frase, setFrase] = useState("");
  const [tesauros, setTesauros] = useState(false);
  const [trabajando, setTrabajando] = useState(false);
  const [error, setError] = useState("");
  const [hecho, setHecho] = useState<Resultado | null>(null);
  const bajar = (id: string) => descargar(`/api/sistema/reinicio/respaldos/${id}/descargar`)
    .then(() => cargar()).catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo descargar el respaldo."));

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
  const fraseBien = frase.trim().toUpperCase().replace(/\s+/g, " ") === inv.frase;
  const listo = fraseBien && contrasena.length > 0;

  return (
    <>
      {hecho && (
        <div className="aviso bien" role="status">
          <strong>El sistema quedó en blanco.</strong> Respaldo previo: <code>{hecho.respaldo.archivo}</code>
          {hecho.archivos_apartados.movidos > 0 && <> · Los archivos quedaron apartados en el servidor
            (<code>_retirado</code>), no se eliminaron.</>}
          {hecho.aviso_grafos && <> · Aviso: el almacén del grafo no se pudo vaciar ({hecho.aviso_grafos}); no queda visible.</>}
          {" "}Para empezar, cree el primer fondo en Instrumentos o cargue el CCD y la TRD.
          <div className="acciones" style={{ marginTop: 10 }}>
            <button type="button" className="boton primario" onClick={() => bajar(hecho.respaldo.id)}>Descargar el respaldo a este equipo</button>
          </div>
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
      {inv.respaldos.length > 0 && (
        <div className="tarjeta">
          <div className="tarjeta-cab">Respaldos de puestas en marcha anteriores</div>
          <div className="tabla-desplazable">
            <table className="tabla-datos">
              <thead><tr><th>Fecha</th><th>Archivo</th><th className="num">Tamaño</th><th>Copia fuera del servidor</th><th /></tr></thead>
              <tbody>
                {inv.respaldos.map((r) => (
                  <tr key={r.id}>
                    <td style={{ whiteSpace: "nowrap" }}>{fecha(r.fecha)}</td>
                    <td><code>{r.archivo}</code><span className="secundario" title="Huella SHA-256 para comprobar que la copia llegó entera">SHA-256 {r.huella?.slice(0, 16)}…</span></td>
                    <td className="num">{r.tamano_bytes ? peso(r.tamano_bytes) : "—"}</td>
                    <td>{r.descargado_en ? <span className="insignia bien">✓ Descargado {fecha(r.descargado_en)}</span>
                      : <span className="insignia alerta">Sin copia todavía</span>}</td>
                    <td className="acciones-celda" style={{ width: 120 }}>
                      {r.disponible ? <button type="button" className="boton chico" onClick={() => bajar(r.id)}>Descargar</button>
                        : <span className="meta">Ya no está en el servidor</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {inv.sin_clasificar.length > 0 && (
        <div className="aviso error" role="alert">Hay tablas sin clasificar ({inv.sin_clasificar.join(", ")}). No se puede dejar en blanco
          hasta corregirlo en el sistema.</div>
      )}
      <form className="tarjeta" onSubmit={enviar}>
        <div className="tarjeta-cab">Dejar el sistema en blanco</div>
        <div className="tarjeta-cuerpo">
          <div className="aviso alerta" role="note">Antes de borrar, RICORA hace un respaldo completo de la base de datos. Si el respaldo
            falla, no se borra nada. Después podrá descargar ese respaldo desde esta misma pantalla y guardarlo fuera del servidor.</div>
          {total === 0 && <p className="meta">El sistema ya está en blanco.</p>}
          <div className="casillas" style={{ margin: "10px 0 14px" }}><label><input type="checkbox" checked={tesauros} onChange={(e) => setTesauros(e.target.checked)} />
            Borrar también los tesauros cargados</label></div>
          {/* El navegador rellena el primer campo de texto antes de una contraseña con el correo guardado.
              Este campo oculto recibe ese relleno para que no caiga en la frase. */}
          <input type="text" name="username" autoComplete="username" value={usuario?.correo ?? ""} readOnly hidden aria-hidden="true" />
          <div className="campo">
            <label htmlFor="frase-reinicio">Escriba <strong>{inv.frase}</strong></label>
            <input id="frase-reinicio" name="frase-confirmacion" className="entrada" autoComplete="off" spellCheck={false}
                   placeholder={inv.frase} value={frase} onChange={(e) => setFrase(e.target.value)} />
            {frase.trim() !== "" && !fraseBien && (
              <p className="meta" role="status" style={{ color: "var(--danger)", margin: "6px 0 0" }}>
                La frase no coincide. Borre lo que hay y escriba exactamente {inv.frase}.</p>
            )}
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
