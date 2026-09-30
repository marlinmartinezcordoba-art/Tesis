import { Link, useLocation } from "react-router-dom";
import { puede } from "@/lib/api";
import { enlaceHistoria } from "@/lib/auditoria";
import { useSesion } from "@/lib/sesion";

// Enlace «Historial de auditoría» que aparece en cada pantalla que muestra
// una entidad. Solo se ve si el rol consulta la auditoría (propia o toda);
// el servidor decide qué eventos entrega.
export function EnlaceHistoria({ tipo, id, nombre }: { tipo: string; id: string; nombre: string }) {
  const { usuario } = useSesion();
  const ubicacion = useLocation();
  if (!puede(usuario, "auditoria")) return null;
  return (
    <Link className="boton chico" to={enlaceHistoria(tipo, id, nombre, ubicacion.pathname + ubicacion.search)}>
      Historial de auditoría
    </Link>
  );
}
