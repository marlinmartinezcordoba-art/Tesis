import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import * as api from "./api";
import type { UsuarioBreve } from "./api";

interface Sesion {
  usuario: UsuarioBreve | null;
  cargando: boolean;
  ingresar: (correo: string, contrasena: string) => Promise<void>;
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
    setUsuario(await api.ingresar(correo, contrasena));
  }, []);

  const salir = useCallback(async () => {
    await api.salir();
    setUsuario(null);
  }, []);

  const valor = useMemo(() => ({ usuario, cargando, ingresar, salir }), [usuario, cargando, ingresar, salir]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSesion(): Sesion {
  const s = useContext(Contexto);
  if (!s) throw new Error("useSesion fuera de ProveedorSesion");
  return s;
}
