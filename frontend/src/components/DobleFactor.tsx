import { useEffect, useState, type FormEvent } from "react";
import { ErrorAPI, pedir } from "@/lib/api";
import { fecha } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";

interface Estado { activo: boolean; activado_en: string | null; requerido: boolean; codigos_respaldo: number }

function agrupar(clave: string) {
  return clave.replace(/(.{4})/g, "$1 ").trim();
}

// Segundo factor de la propia cuenta: un código de seis dígitos que genera una
// aplicación del teléfono (Aegis, FreeOTP, Google Authenticator…), además de la contraseña.
export function DobleFactor() {
  const { refrescar } = useSesion();
  const [estado, setEstado] = useState<Estado | null>(null);
  const [alta, setAlta] = useState<{ clave: string; uri: string } | null>(null);
  const [respaldo, setRespaldo] = useState<string[] | null>(null);
  const [codigo, setCodigo] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [quitando, setQuitando] = useState(false);
  const [error, setError] = useState("");

  const cargar = () => pedir<Estado>("/api/auth/perfil/doble-factor").then(setEstado).catch(() => undefined);
  useEffect(() => { cargar(); }, []);

  async function iniciar() {
    setError("");
    try {
      setAlta(await pedir<{ clave: string; uri: string }>("/api/auth/perfil/doble-factor/iniciar", { method: "POST" }));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo generar la clave.");
    }
  }

  async function activar(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const r = await pedir<{ codigos_respaldo: string[] }>("/api/auth/perfil/doble-factor/activar",
                                                           { method: "POST", body: JSON.stringify({ codigo }) });
      setRespaldo(r.codigos_respaldo);
      setAlta(null);
      setCodigo("");
      await cargar();
      await refrescar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo activar.");
    }
  }

  async function quitar(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await pedir("/api/auth/perfil/doble-factor/desactivar", { method: "POST", body: JSON.stringify({ contrasena, codigo }) });
      setQuitando(false);
      setCodigo("");
      setContrasena("");
      await cargar();
      await refrescar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo quitar.");
    }
  }

  if (!estado) return null;
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Segundo factor de autenticación</div>
      <div className="tarjeta-cuerpo" style={{ maxWidth: 560 }}>
        {error && <div className="aviso error" role="alert">{error}</div>}
        {respaldo && (
          <div className="aviso alerta" role="status">
            <strong>Guarde estos códigos de respaldo ahora: no se vuelven a mostrar.</strong> Cada uno sirve una sola vez
            para entrar si pierde el teléfono.
            <pre style={{ margin: "8px 0 0", fontSize: "1rem" }}>{respaldo.join("\n")}</pre>
          </div>
        )}
        {estado.activo ? (
          <>
            <p style={{ marginTop: 0 }}>
              <span className="insignia bien">Activo</span> desde el {fecha(estado.activado_en)} · Le quedan
              {" "}{estado.codigos_respaldo} códigos de respaldo.
            </p>
            {estado.requerido ? (
              <p className="pista">Su rol exige segundo factor. Si cambia de teléfono, pida a un administrador que lo restablezca.</p>
            ) : !quitando ? (
              <button type="button" className="boton chico" onClick={() => setQuitando(true)}>Quitar el segundo factor</button>
            ) : (
              <form onSubmit={quitar}>
                <div className="campo">
                  <label htmlFor="df-contrasena">Contraseña</label>
                  <input id="df-contrasena" className="entrada" type="password" autoComplete="current-password" required
                         value={contrasena} onChange={(e) => setContrasena(e.target.value)} />
                </div>
                <div className="campo">
                  <label htmlFor="df-codigo-quitar">Código actual</label>
                  <input id="df-codigo-quitar" className="entrada" inputMode="numeric" required maxLength={20}
                         value={codigo} onChange={(e) => setCodigo(e.target.value)} />
                </div>
                <div className="acciones">
                  <button type="submit" className="boton chico">Quitar</button>
                  <button type="button" className="boton chico" onClick={() => setQuitando(false)}>Cancelar</button>
                </div>
              </form>
            )}
          </>
        ) : alta ? (
          <form onSubmit={activar}>
            <ol style={{ paddingLeft: 18, marginTop: 0 }}>
              <li>Abra en el teléfono una aplicación de autenticación (Aegis, FreeOTP o Google Authenticator).</li>
              <li>Agregue una cuenta nueva con esta clave (tipo «basada en el tiempo»):
                <div><code style={{ fontSize: "1rem", userSelect: "all" }}>{agrupar(alta.clave)}</code></div>
                <div className="pista">En el teléfono también puede tocar <a href={alta.uri}>este enlace</a>.</div>
              </li>
              <li>Escriba el código de seis dígitos que muestra la aplicación.</li>
            </ol>
            <div className="campo">
              <label htmlFor="df-codigo">Código</label>
              <input id="df-codigo" className="entrada" inputMode="numeric" autoComplete="one-time-code" required maxLength={6}
                     style={{ maxWidth: 160 }} value={codigo} onChange={(e) => setCodigo(e.target.value)} />
            </div>
            <div className="acciones">
              <button type="submit" className="boton primario chico">Activar</button>
              <button type="button" className="boton chico" onClick={() => setAlta(null)}>Cancelar</button>
            </div>
          </form>
        ) : (
          <>
            <p style={{ marginTop: 0 }}>
              {estado.requerido
                ? <strong>Su rol exige segundo factor: configúrelo para seguir trabajando.</strong>
                : "Además de la contraseña, al entrar se le pedirá un código de su teléfono. Protege la información clasificada y reservada si alguien conoce su contraseña."}
            </p>
            <button type="button" className="boton primario chico" onClick={iniciar}>Configurar segundo factor</button>
          </>
        )}
      </div>
    </div>
  );
}
