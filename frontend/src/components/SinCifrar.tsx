/**
 * Brecha NFR-01 (lote 3): si RICORA se abre por HTTP fuera del propio equipo,
 * las contraseñas y los documentos viajan sin cifrar. El despliegue intenta
 * siempre HTTPS; si no lo logra, se mantiene disponible pero lo dice aquí,
 * en cada pantalla y en el ingreso, en lugar de callarlo.
 */
const LOCALES = new Set(["localhost", "127.0.0.1", "[::1]"]);

export function conexionSinCifrar(ubicacion: Pick<Location, "protocol" | "hostname"> = window.location): boolean {
  return ubicacion.protocol === "http:" && !LOCALES.has(ubicacion.hostname);
}

export function AvisoSinCifrar() {
  if (!conexionSinCifrar()) return null;
  return (
    <div className="aviso error sin-cifrar" role="alert">
      <b>Conexión sin cifrar.</b> No cargue documentos clasificados o reservados ni datos personales sensibles
      hasta que RICORA funcione con HTTPS (candado en la barra del navegador).
    </div>
  );
}
