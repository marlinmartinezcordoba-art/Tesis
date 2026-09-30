import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Marca } from "@/components/Marco";
import { Reglas } from "@/components/Reglas";
import { ErrorAPI, publico } from "@/lib/api";
import { reglasContrasena } from "@/lib/contrasena";
import { useSesion } from "@/lib/sesion";

interface InfoEnlace {
  tipo: "invitacion" | "recuperacion";
  nombre: string;
  correo: string;
}

export function DefinirContrasena() {
  const { token = "" } = useParams();
  const navegar = useNavigate();
  const { usuario, salir } = useSesion();
  const [info, setInfo] = useState<InfoEnlace | null>(null);
  const [invalido, setInvalido] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    publico
      .get<InfoEnlace>(`/api/auth/token/${encodeURIComponent(token)}`)
      .then(setInfo)
      .catch((e) => setInvalido(e instanceof ErrorAPI ? e.message : "El enlace no es válido."));
  }, [token]);

  const reglas = reglasContrasena(contrasena, confirmacion, info?.correo);
  const lista = reglas.every((r) => r.cumple);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (!lista) return;
    setError("");
    setEnviando(true);
    try {
      const r = await publico.post<{ mensaje: string }>(`/api/auth/recuperar/${encodeURIComponent(token)}`, { contrasena });
      // Si había otra sesión abierta en este navegador, se cierra: la
      // contraseña nueva cierra todas las sesiones anteriores.
      if (usuario) await salir();
      navegar("/ingresar", { replace: true, state: { aviso: r.mensaje } });
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo guardar la contraseña.");
    } finally {
      setEnviando(false);
    }
  }

  if (invalido) {
    return (
      <div className="acceso">
        <div className="acceso-tarjeta">
          <Marca />
          <h1>Enlace no disponible</h1>
          <div className="aviso error" role="alert">{invalido}</div>
          <Link className="boton primario ancho" style={{ display: "block", textAlign: "center", textDecoration: "none" }} to="/recuperar">
            Pedir un enlace nuevo
          </Link>
          <Link className="enlace-acceso" to="/ingresar">Volver al inicio de sesión</Link>
        </div>
      </div>
    );
  }
  if (!info) return <div className="cargando">Verificando el enlace…</div>;

  const invitacion = info.tipo === "invitacion";
  return (
    <div className="acceso">
      <form className="acceso-tarjeta" onSubmit={enviar}>
        <Marca />
        <h1>{invitacion ? "Defina su contraseña" : "Nueva contraseña"}</h1>
        <p className="sub">
          Hola, {info.nombre}.{" "}
          {invitacion ? "Solo usted conocerá esta contraseña." : "Escriba la contraseña nueva de su cuenta."}
        </p>
        {error && <div className="aviso error" role="alert">{error}</div>}
        <div className="campo">
          <label htmlFor="correo">Correo</label>
          <input id="correo" className="entrada" type="email" autoComplete="username" value={info.correo} readOnly />
        </div>
        <div className="campo">
          <label htmlFor="nueva">Contraseña</label>
          <input id="nueva" className="entrada" type="password" autoComplete="new-password" required autoFocus
                 value={contrasena} onChange={(e) => setContrasena(e.target.value)} />
        </div>
        <div className="campo">
          <label htmlFor="confirmar">Repita la contraseña</label>
          <input id="confirmar" className="entrada" type="password" autoComplete="new-password" required
                 value={confirmacion} onChange={(e) => setConfirmacion(e.target.value)} />
        </div>
        <Reglas reglas={reglas} />
        <button className="boton primario ancho" type="submit" disabled={!lista || enviando}>
          {enviando ? "Guardando…" : "Guardar contraseña"}
        </button>
      </form>
    </div>
  );
}
