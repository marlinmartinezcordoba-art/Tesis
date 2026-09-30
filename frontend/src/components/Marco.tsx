import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import type { Rol } from "@/lib/api";
import { useSesion } from "@/lib/sesion";

const trazo = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

export const ICONOS: Record<string, ReactNode> = {
  ingesta: <svg viewBox="0 0 24 24" {...trazo}><path d="M12 4v10m0 0l-3.5-3.5M12 14l3.5-3.5M5 16v2a2 2 0 002 2h10a2 2 0 002-2v-2" /></svg>,
  descripcion: <svg viewBox="0 0 24 24" {...trazo}><circle cx="12" cy="6" r="2.2" /><circle cx="6" cy="17" r="2.2" /><circle cx="18" cy="17" r="2.2" /><path d="M10.5 7.5L7.5 15M13.5 7.5l3 7.5M8.2 17h7.6" /></svg>,
  vocabularios: <svg viewBox="0 0 24 24" {...trazo}><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 9h8M8 13h5" /></svg>,
  instrumentos: <svg viewBox="0 0 24 24" {...trazo}><path d="M6 4h9l3 3v13H6z" /><path d="M9 12h6M9 15h6M9 9h3" /></svg>,
  preservacion: <svg viewBox="0 0 24 24" {...trazo}><path d="M12 3l7 3v6c0 4.5-3 7-7 9-4-2-7-4.5-7-9V6z" /></svg>,
  auditoria: <svg viewBox="0 0 24 24" {...trazo}><path d="M4 19V5m5 14V9m5 10V12m5 7V6" /></svg>,
  usuarios: <svg viewBox="0 0 24 24" {...trazo}><circle cx="12" cy="8" r="3.2" /><path d="M5 20c1-4 4.5-6 7-6s6 2 7 6" /></svg>,
};

interface Entrada {
  ruta: string;
  nombre: string;
  icono: string;
  grupo: "trabajo" | "sistema";
  roles: Rol[];
}

// Solo aparecen los módulos ya construidos; cada módulo nuevo se agrega
// aquí cuando se entrega, en el orden de la barra del diseño consolidado:
// Ingesta, Descripción, Vocabularios, Instrumentos, Preservación ·
// Auditoría, Usuarios.
const ENTRADAS: Entrada[] = [
  { ruta: "/usuarios", nombre: "Usuarios", icono: "usuarios", grupo: "sistema", roles: ["administrador"] },
];

export function Marca() {
  return (
    <div className="marca">
      RICORA<span>Archivo histórico</span>
    </div>
  );
}

function MenuPersona() {
  const { usuario, salir } = useSesion();
  const [abierto, setAbierto] = useState(false);
  const caja = useRef<HTMLDivElement>(null);
  const navegar = useNavigate();

  useEffect(() => {
    if (!abierto) return;
    const cerrar = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !caja.current?.contains(e.target as Node)) setAbierto(false);
    };
    document.addEventListener("mousedown", cerrar);
    document.addEventListener("keydown", cerrar);
    return () => {
      document.removeEventListener("mousedown", cerrar);
      document.removeEventListener("keydown", cerrar);
    };
  }, [abierto]);

  if (!usuario) return null;
  return (
    <div className="persona" ref={caja}>
      <button type="button" aria-haspopup="menu" aria-expanded={abierto} onClick={() => setAbierto(!abierto)}>
        <span className="avatar chico">{usuario.iniciales}</span>
        {usuario.nombre.split(" ")[0]} · {usuario.rol_nombre}
      </button>
      {abierto && (
        <div className="menu" role="menu">
          <Link to="/perfil" role="menuitem" onClick={() => setAbierto(false)}>Mi perfil</Link>
          <button
            type="button"
            role="menuitem"
            onClick={async () => {
              await salir();
              navegar("/ingresar", { replace: true });
            }}
          >
            Cerrar sesión
          </button>
        </div>
      )}
    </div>
  );
}

export function Marco({ children }: { children: ReactNode }) {
  const { usuario } = useSesion();
  const visibles = ENTRADAS.filter((e) => usuario && e.roles.includes(usuario.rol));
  const grupos: [string, Entrada[]][] = [
    ["Trabajo archivístico", visibles.filter((e) => e.grupo === "trabajo")],
    ["Sistema", visibles.filter((e) => e.grupo === "sistema")],
  ];
  return (
    <div className="app">
      <aside className="lateral">
        <Marca />
        <div className="navegacion" role="navigation" aria-label="Módulos">
          {grupos.map(([titulo, entradas]) =>
            entradas.length ? (
              <div key={titulo} style={{ display: "contents" }}>
                <div className="grupo">{titulo}</div>
                {entradas.map((e) => (
                  <NavLink key={e.ruta} to={e.ruta}>
                    {ICONOS[e.icono]}
                    {e.nombre}
                  </NavLink>
                ))}
              </div>
            ) : null,
          )}
        </div>
      </aside>
      <main className="contenido">
        <div className="superior">
          <MenuPersona />
        </div>
        {children}
      </main>
    </div>
  );
}

// Primera pantalla de cada rol después de ingresar.
export function inicioDe(rol: Rol): string {
  const primera = ENTRADAS.find((e) => e.roles.includes(rol));
  return primera ? primera.ruta : "/perfil";
}
