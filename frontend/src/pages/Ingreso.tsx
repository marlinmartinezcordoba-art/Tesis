import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Marca } from "@/components/Marco";
import { ErrorAPI } from "@/lib/api";
import { useSesion } from "@/lib/sesion";

export function Ingreso() {
  const { ingresar } = useSesion();
  const navegar = useNavigate();
  const ubicacion = useLocation();
  const aviso = (ubicacion.state as { aviso?: string } | null)?.aviso;
  const [correo, setCorreo] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setError("");
    setEnviando(true);
    try {
      await ingresar(correo, contrasena);
      const desde = (ubicacion.state as { desde?: string } | null)?.desde;
      navegar(desde || "/", { replace: true });
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo iniciar sesión.");
      setContrasena("");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="acceso">
      <form className="acceso-tarjeta" onSubmit={enviar}>
        <Marca />
        <h1>Iniciar sesión</h1>
        <p className="sub">Ingrese con su correo institucional</p>
        {aviso && !error && <div className="aviso bien">{aviso}</div>}
        {error && <div className="aviso error" role="alert">{error}</div>}
        <div className="campo">
          <label htmlFor="correo">Correo</label>
          <input id="correo" className="entrada" type="email" autoComplete="username" required autoFocus
                 placeholder="nombre@correo.com" value={correo} onChange={(e) => setCorreo(e.target.value)} />
        </div>
        <div className="campo">
          <label htmlFor="contrasena">Contraseña</label>
          <input id="contrasena" className="entrada" type="password" autoComplete="current-password" required
                 value={contrasena} onChange={(e) => setContrasena(e.target.value)} />
        </div>
        <button className="boton primario ancho" type="submit" disabled={enviando}>
          {enviando ? "Entrando…" : "Entrar"}
        </button>
        <Link className="enlace-acceso" to="/recuperar">Olvidé mi contraseña</Link>
      </form>
    </div>
  );
}

