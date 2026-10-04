import { AvisoSinCifrar } from "../components/SinCifrar";
import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Marca } from "@/components/Marco";
import { ErrorAPI } from "@/lib/api";
import { useSesion } from "@/lib/sesion";

export function Ingreso() {
  const { ingresar, segundoFactor } = useSesion();
  const navegar = useNavigate();
  const ubicacion = useLocation();
  const aviso = (ubicacion.state as { aviso?: string } | null)?.aviso;
  const [correo, setCorreo] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [desafio, setDesafio] = useState<string | null>(null);
  const [codigo, setCodigo] = useState("");

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setError("");
    setEnviando(true);
    try {
      if (desafio) {
        await segundoFactor(desafio, codigo);
      } else {
        const pendiente = await ingresar(correo, contrasena);
        if (pendiente) {
          setDesafio(pendiente);
          setContrasena("");
          return;
        }
      }
      const desde = (ubicacion.state as { desde?: string } | null)?.desde;
      navegar(desde || "/", { replace: true });
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo iniciar sesión.");
      setContrasena("");
      setCodigo("");
      if (err instanceof ErrorAPI && err.status === 401 && desafio && err.message.includes("venció")) setDesafio(null);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="acceso">
      <form className="acceso-tarjeta" onSubmit={enviar}>
        <Marca />
        <h1>Iniciar sesión</h1>
        <AvisoSinCifrar />
        <p className="sub">Ingrese con su correo institucional</p>
        {aviso && !error && <div className="aviso bien">{aviso}</div>}
        {error && <div className="aviso error" role="alert">{error}</div>}
        {desafio ? (
          <>
            <div className="campo">
              <label htmlFor="codigo">Código de verificación</label>
              <input id="codigo" className="entrada" inputMode="numeric" autoComplete="one-time-code" required autoFocus
                     maxLength={20} placeholder="123456" value={codigo} onChange={(e) => setCodigo(e.target.value)} />
              <div className="pista">Escriba el código de seis dígitos de su aplicación de autenticación. Si no tiene
                el teléfono, use uno de sus códigos de respaldo.</div>
            </div>
            <button className="boton primario ancho" type="submit" disabled={enviando}>
              {enviando ? "Verificando…" : "Verificar"}
            </button>
            <button type="button" className="enlace-acceso enlace" onClick={() => { setDesafio(null); setCodigo(""); setError(""); }}>
              Volver
            </button>
          </>
        ) : (<>
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
        </>)}
      </form>
    </div>
  );
}

