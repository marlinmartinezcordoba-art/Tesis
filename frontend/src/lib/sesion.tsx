import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import * as api from "./api";
import type { UsuarioBreve } from "./api";

interface Sesion {
  usuario: UsuarioBreve | null;
  cargando: boolean;
  /** null si entró; el desafío si falta el segundo factor. */
  ingresar: (correo: string, contrasena: string) => Promise<string | null>;
  segundoFactor: (desafio: string, codigo: string) => Promise<void>;
  /** Vuelve a leer la cuenta (p. ej. después de activar el segundo factor). */
  refrescar: () => Promise<void>;
  salir: () => Promise<void>;
}

const Contexto = createContext<Sesion | null>(null);

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<UsuarioBreve | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    api.configurarSesion({ alCerrar: () => setUsuario(null), alRenovar: setUsuario });
    // Al abrir o recargar la página, la sesión se recupera con la galleta.
    api.renovar().finally(() => setCargando(false));
  }, []);

  const ingresar = useCallback(async (correo: string, contrasena: string) => {
    const r = await api.ingresar(correo, contrasena);
    if ("desafio" in r) return r.desafio;
    setUsuario(r);
    return null;
  }, []);

  const segundoFactor = useCallback(async (desafio: string, codigo: string) => {
    setUsuario(await api.ingresarSegundoFactor(desafio, codigo));
  }, []);

  const refrescar = useCallback(async () => {
    await api.renovar();
  }, []);

  const salir = useCallback(async () => {
    await api.salir();
    setUsuario(null);
  }, []);

  const valor = useMemo(() => ({ usuario, cargando, ingresar, segundoFactor, refrescar, salir }),
                        [usuario, cargando, ingresar, segundoFactor, refrescar, salir]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSesion(): Sesion {
  const s = useContext(Contexto);
  if (!s) throw new Error("useSesion fuera de ProveedorSesion");
  return s;
}
