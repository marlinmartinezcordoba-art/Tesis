import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { pedir } from "./api";
import { useSesion } from "./sesion";

export interface Fondo {
  id: string;
  titulo: string;
  fechas_extremas: string | null;
  documentos: number;
}

interface ContextoFondo {
  fondos: Fondo[] | null;
  fondo: Fondo | null;
  elegir: (id: string) => void;
  recargar: () => Promise<void>;
}

const Contexto = createContext<ContextoFondo | null>(null);
const CLAVE = "ricora.fondo";

function leerGuardado(): string | null {
  try {
    return localStorage.getItem(CLAVE);
  } catch {
    return null;
  }
}

export function ProveedorFondo({ children }: { children: ReactNode }) {
  const { usuario } = useSesion();
  const [fondos, setFondos] = useState<Fondo[] | null>(null);
  const [elegido, setElegido] = useState<string | null>(leerGuardado);

  const recargar = useCallback(async () => {
    try {
      setFondos(await pedir<Fondo[]>("/api/fondos"));
    } catch {
      setFondos([]);
    }
  }, []);

  useEffect(() => {
    if (usuario) recargar();
    else setFondos(null);
  }, [usuario, recargar]);

  const elegir = useCallback((id: string) => {
    setElegido(id);
    try {
      localStorage.setItem(CLAVE, id);
    } catch {
      /* sin almacenamiento local: se recuerda solo en esta pestaña */
    }
  }, []);

  const fondo = useMemo(() => {
    if (!fondos || fondos.length === 0) return null;
    return fondos.find((f) => f.id === elegido) || fondos[0];
  }, [fondos, elegido]);

  const valor = useMemo(() => ({ fondos, fondo, elegir, recargar }), [fondos, fondo, elegir, recargar]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useFondo(): ContextoFondo {
  const c = useContext(Contexto);
  if (!c) throw new Error("useFondo fuera de ProveedorFondo");
  return c;
}
