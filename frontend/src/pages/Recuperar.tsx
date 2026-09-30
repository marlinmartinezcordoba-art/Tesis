import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Marca } from "@/components/Marco";
import { ErrorAPI, publico } from "@/lib/api";

export function Recuperar() {
  const [correo, setCorreo] = useState("");
  const [mensaje, setMensaje] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setError("");
    setEnviando(true);
    try {
      const r = await publico.post<{ mensaje: string }>("/api/auth/recuperar", { correo });
      setMensaje(r.mensaje);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo enviar la solicitud.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="acceso">
      <form className="acceso-tarjeta" onSubmit={enviar}>
        <Marca />
        <h1>Recuperar contraseña</h1>
        <p className="sub">Le enviaremos un enlace de un solo uso a su correo</p>
        {mensaje ? (
          <div className="aviso bien" role="status">{mensaje}</div>
        ) : (
          <>
            {error && <div className="aviso error" role="alert">{error}</div>}
            <div className="campo">
              <label htmlFor="correo">Correo</label>
              <input id="correo" className="entrada" type="email" autoComplete="username" required autoFocus
                     placeholder="nombre@correo.com" value={correo} onChange={(e) => setCorreo(e.target.value)} />
            </div>
            <button className="boton primario ancho" type="submit" disabled={enviando}>
              {enviando ? "Enviando…" : "Enviar enlace"}
            </button>
            <p className="pista">
              Si el correo existe en el sistema, recibirá un enlace válido por tiempo limitado. El enlace deja de
              funcionar después de usarse una vez.
            </p>
          </>
        )}
        <Link className="enlace-acceso" to="/ingresar">Volver al inicio de sesión</Link>
      </form>
    </div>
  );
}
