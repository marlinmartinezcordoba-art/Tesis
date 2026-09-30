import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Marco, inicioDe, veAlertas } from "@/components/Marco";
import { puede, type Modulo, type UsuarioBreve } from "@/lib/api";
import { useSesion } from "@/lib/sesion";
import { Alertas } from "@/pages/Alertas";
import { DefinirContrasena } from "@/pages/DefinirContrasena";
import { Descripcion } from "@/pages/Descripcion";
import { EspacioTrabajo } from "@/pages/EspacioTrabajo";
import { RegistroDescripcion } from "@/pages/Registro";
import { Ingesta } from "@/pages/Ingesta";
import { Ingreso } from "@/pages/Ingreso";
import { Instrumentos } from "@/pages/Instrumentos";
import { Perfil } from "@/pages/Perfil";
import { Recuperar } from "@/pages/Recuperar";
import { Usuarios } from "@/pages/Usuarios";
import { Vocabularios } from "@/pages/Vocabularios";
import { EntidadVocabularioDetalle } from "@/pages/EntidadVocabulario";

// La interfaz solo oculta lo que un rol no puede usar; quien de verdad
// decide es el backend, que valida sesión y rol en cada petición.
function Protegida({ modulo, tipo = "leer", permitir, children }: {
  modulo?: Modulo | "usuarios";
  tipo?: "leer" | "escribir";
  permitir?: (u: UsuarioBreve) => boolean;
  children: ReactNode;
}) {
  const { usuario } = useSesion();
  const ubicacion = useLocation();
  if (!usuario) return <Navigate to="/ingresar" replace state={{ desde: ubicacion.pathname }} />;
  const permitido = (!modulo || puede(usuario, modulo, tipo)) && (!permitir || permitir(usuario));
  if (!permitido) return <Navigate to={inicioDe(usuario)} replace />;
  return <Marco>{children}</Marco>;
}

function SoloSinSesion({ children }: { children: ReactNode }) {
  const { usuario } = useSesion();
  return usuario ? <Navigate to={inicioDe(usuario)} replace /> : <>{children}</>;
}

export default function App() {
  const { usuario, cargando } = useSesion();
  if (cargando) return <div className="cargando">Cargando RICORA…</div>;
  return (
    <Routes>
      <Route path="/ingresar" element={<SoloSinSesion><Ingreso /></SoloSinSesion>} />
      <Route path="/recuperar" element={<SoloSinSesion><Recuperar /></SoloSinSesion>} />
      <Route path="/acceso/:token" element={<DefinirContrasena />} />
      <Route path="/ingesta" element={<Protegida modulo="ingesta"><Ingesta /></Protegida>} />
      <Route path="/descripcion" element={<Protegida modulo="descripcion"><Descripcion /></Protegida>} />
      <Route path="/descripcion/trabajo/:id" element={<Protegida modulo="descripcion" tipo="escribir"><EspacioTrabajo /></Protegida>} />
      <Route path="/descripcion/registro/:id" element={<Protegida modulo="descripcion"><RegistroDescripcion /></Protegida>} />
      <Route path="/vocabularios" element={<Protegida modulo="vocabularios"><Vocabularios /></Protegida>} />
      <Route path="/vocabularios/:id" element={<Protegida modulo="vocabularios"><EntidadVocabularioDetalle /></Protegida>} />
      <Route path="/instrumentos" element={<Protegida modulo="catalogo"><Instrumentos /></Protegida>} />
      <Route path="/alertas" element={<Protegida permitir={veAlertas}><Alertas /></Protegida>} />
      <Route path="/perfil" element={<Protegida><Perfil /></Protegida>} />
      <Route path="/usuarios" element={<Protegida modulo="usuarios"><Usuarios /></Protegida>} />
      <Route path="*" element={<Navigate to={usuario ? inicioDe(usuario) : "/ingresar"} replace />} />
    </Routes>
  );
}
