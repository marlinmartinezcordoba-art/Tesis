import { useEffect, useState, type FormEvent } from "react";
import { Reglas } from "@/components/Reglas";
import { CLASE_ROL, ErrorAPI, pedir, type Rol } from "@/lib/api";
import { reglasContrasena } from "@/lib/contrasena";
import { fecha } from "@/lib/formato";

interface Perfil {
  nombre: string;
  correo: string;
  rol: Rol;
  rol_nombre: string;
  iniciales: string;
  contrasena_cambiada_en: string | null;
}

export function Perfil() {
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [mensaje, setMensaje] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  const cargar = () => pedir<Perfil>("/api/auth/perfil").then(setPerfil).catch(() => undefined);
  useEffect(() => { cargar(); }, []);

  const reglas = reglasContrasena(nueva, confirmacion, perfil?.correo);
  const lista = actual.length > 0 && reglas.every((r) => r.cumple);

  async function cambiar(e: FormEvent) {
    e.preventDefault();
    setError("");
    setMensaje("");
    setEnviando(true);
    try {
      const r = await pedir<{ mensaje: string }>("/api/auth/perfil/contrasena", {
        method: "PATCH",
        body: JSON.stringify({ actual, nueva }),
      });
      setMensaje(r.mensaje);
      setActual("");
      setNueva("");
      setConfirmacion("");
      cargar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cambiar la contraseña.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <>
      <h1>Mi perfil</h1>
      <p className="sub">El rol lo asigna únicamente un administrador; nadie puede cambiárselo a sí mismo.</p>

      <div className="tarjeta">
        <div className="tarjeta-cab">Datos de la cuenta</div>
        <div className="tarjeta-cuerpo">
          {perfil ? (
            <dl className="pares" style={{ margin: 0 }}>
              <dt>Nombre</dt>
              <dd>{perfil.nombre}</dd>
              <dt>Correo</dt>
              <dd>{perfil.correo}</dd>
              <dt>Rol</dt>
              <dd><span className={`insignia ${CLASE_ROL[perfil.rol]}`}>{perfil.rol_nombre}</span></dd>
              <dt>Contraseña</dt>
              <dd>Cambiada por última vez: {fecha(perfil.contrasena_cambiada_en)}</dd>
            </dl>
          ) : (
            <div className="vacio">Cargando…</div>
          )}
        </div>
      </div>

      <form className="tarjeta" onSubmit={cambiar}>
        <div className="tarjeta-cab">Cambiar contraseña</div>
        <div className="tarjeta-cuerpo" style={{ maxWidth: 420 }}>
          {mensaje && <div className="aviso bien" role="status">{mensaje}</div>}
          {error && <div className="aviso error" role="alert">{error}</div>}
          <input type="email" autoComplete="username" value={perfil?.correo || ""} readOnly hidden />
          <div className="campo">
            <label htmlFor="actual">Contraseña actual</label>
            <input id="actual" className="entrada" type="password" autoComplete="current-password" required
                   value={actual} onChange={(e) => setActual(e.target.value)} />
          </div>
          <div className="campo">
            <label htmlFor="nueva">Nueva contraseña</label>
            <input id="nueva" className="entrada" type="password" autoComplete="new-password" required
                   value={nueva} onChange={(e) => setNueva(e.target.value)} />
          </div>
          <div className="campo">
            <label htmlFor="confirmar">Repita la nueva contraseña</label>
            <input id="confirmar" className="entrada" type="password" autoComplete="new-password" required
                   value={confirmacion} onChange={(e) => setConfirmacion(e.target.value)} />
          </div>
          <Reglas reglas={reglas} />
          <button className="boton primario" type="submit" disabled={!lista || enviando}>
            {enviando ? "Actualizando…" : "Actualizar contraseña"}
          </button>
          <p className="pista">Al cambiarla se cierran sus sesiones abiertas en otros equipos.</p>
        </div>
      </form>
    </>
  );
}
