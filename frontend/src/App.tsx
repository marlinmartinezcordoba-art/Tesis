import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Marco, VEN_ALERTAS, inicioDe } from "@/components/Marco";
import type { Rol } from "@/lib/api";
import { useSesion } from "@/lib/sesion";
import { Alertas } from "@/pages/Alertas";
import { DefinirContrasena } from "@/pages/DefinirContrasena";
import { Ingesta } from "@/pages/Ingesta";
import { Ingreso } from "@/pages/Ingreso";
import { Perfil } from "@/pages/Perfil";
import { Recuperar } from "@/pages/Recuperar";
import { Usuarios } from "@/pages/Usuarios";

// La interfaz solo oculta lo que un rol no puede usar; quien de verdad
// decide es el backend, que valida sesión y rol en cada petición.
function Protegida({ roles, children }: { roles?: Rol[]; children: ReactNode }) {
  const { usuario } = useSesion();
  const ubicacion = useLocation();
  if (!usuario) return <Navigate to="/ingresar" replace state={{ desde: ubicacion.pathname }} />;
  if (roles && !roles.includes(usuario.rol)) return <Navigate to={inicioDe(usuario.rol)} replace />;
  return <Marco>{children}</Marco>;
}

function SoloSinSesion({ children }: { children: ReactNode }) {
  const { usuario } = useSesion();
  return usuario ? <Navigate to={inicioDe(usuario.rol)} replace /> : <>{children}</>;
}

export default function App() {
  const { usuario, cargando } = useSesion();
  if (cargando) return <div className="cargando">Cargando RICORA…</div>;
  return (
    <Routes>
      <Route path="/ingresar" element={<SoloSinSesion><Ingreso /></SoloSinSesion>} />
      <Route path="/recuperar" element={<SoloSinSesion><Recuperar /></SoloSinSesion>} />
      <Route path="/acceso/:token" element={<DefinirContrasena />} />
      <Route path="/ingesta" element={<Protegida roles={["administrador", "archivista", "revisor"]}><Ingesta /></Protegida>} />
      <Route path="/alertas" element={<Protegida roles={VEN_ALERTAS}><Alertas /></Protegida>} />
      <Route path="/perfil" element={<Protegida><Perfil /></Protegida>} />
      <Route path="/usuarios" element={<Protegida roles={["administrador"]}><Usuarios /></Protegida>} />
      <Route path="*" element={<Navigate to={usuario ? inicioDe(usuario.rol) : "/ingresar"} replace />} />
    </Routes>
  );
}
