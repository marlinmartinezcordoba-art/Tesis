import { useState, type FormEvent } from "react";
import { ErrorAPI, pedir } from "@/lib/api";

export interface RolInfo {
  clave: string;
  nombre: string;
  descripcion: string | null;
  base: boolean;
  activo: boolean;
  permisos: Record<string, string>;
  usuarios: number;
}

const MODULOS: { clave: string; nombre: string; niveles: [string, string][] }[] = [
  ...[
    ["ingesta", "Ingesta"], ["descripcion", "Descripción"], ["vocabularios", "Vocabularios"],
    ["instrumentos", "Instrumentos"], ["preservacion", "Preservación"],
  ].map(([clave, nombre]) => ({
    clave, nombre, niveles: [["ninguno", "Sin acceso"], ["leer", "Consultar"], ["escribir", "Trabajar"]] as [string, string][],
  })),
  { clave: "catalogo", nombre: "Catálogo de consulta", niveles: [["ninguno", "Sin acceso"], ["leer", "Consultar"]] },
  { clave: "auditoria", nombre: "Auditoría", niveles: [["ninguno", "Sin acceso"], ["propia", "Solo lo propio"], ["todo", "Todo el equipo"]] },
];

const NOMBRE_NIVEL: Record<string, string> = Object.fromEntries(MODULOS.flatMap((m) => m.niveles));

function Resumen({ permisos }: { permisos: Record<string, string> }) {
  const partes = MODULOS.filter((m) => permisos[m.clave] && permisos[m.clave] !== "ninguno")
    .map((m) => `${m.nombre}: ${NOMBRE_NIVEL[permisos[m.clave]].toLowerCase()}`);
  return <>{partes.length ? partes.join(" · ") : "Sin acceso a ningún módulo"}</>;
}

function Editor({ inicial, alGuardar, alCancelar }: {
  inicial?: RolInfo;
  alGuardar: (datos: { nombre: string; descripcion: string; permisos: Record<string, string> }) => Promise<void>;
  alCancelar: () => void;
}) {
  const [nombre, setNombre] = useState(inicial?.nombre || "");
  const [descripcion, setDescripcion] = useState(inicial?.descripcion || "");
  const [permisos, setPermisos] = useState<Record<string, string>>(
    inicial?.permisos || { catalogo: "leer", auditoria: "propia" });
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setError("");
    setGuardando(true);
    try {
      await alGuardar({ nombre, descripcion, permisos });
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo guardar el rol.");
      setGuardando(false);
    }
  }

  return (
    <form className="formulario-nuevo" onSubmit={enviar}>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="rejilla">
        <div className="campo"><label htmlFor="rol-nombre">Nombre del rol</label>
          <input id="rol-nombre" className="entrada" required minLength={3} value={nombre} onChange={(e) => setNombre(e.target.value)} /></div>
        <div className="campo"><label htmlFor="rol-desc">Descripción (opcional)</label>
          <input id="rol-desc" className="entrada" value={descripcion} onChange={(e) => setDescripcion(e.target.value)} /></div>
      </div>
      <table className="tabla-permisos">
        <thead><tr><th>Módulo</th><th>Acceso</th></tr></thead>
        <tbody>
          {MODULOS.map((m) => (
            <tr key={m.clave}>
              <td>{m.nombre}</td>
              <td>
                <div className="opciones" role="radiogroup" aria-label={`Acceso a ${m.nombre}`}>
                  {m.niveles.map(([valor, texto]) => (
                    <label key={valor} className={(permisos[m.clave] || "ninguno") === valor ? "elegida" : ""}>
                      <input type="radio" name={`p-${m.clave}`} value={valor} checked={(permisos[m.clave] || "ninguno") === valor}
                             onChange={() => setPermisos((p) => ({ ...p, [m.clave]: valor }))} />
                      {texto}
                    </label>
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="pista">
        «Trabajar» incluye consultar. La gestión de usuarios, roles y configuración es siempre solo del Administrador.
      </p>
      <div className="acciones">
        <button type="submit" className="boton primario" disabled={guardando}>{guardando ? "Guardando…" : inicial ? "Guardar cambios" : "Crear rol"}</button>
        <button type="button" className="boton" onClick={alCancelar}>Cancelar</button>
      </div>
    </form>
  );
}

export function PanelRoles({ roles, alCambiar }: { roles: RolInfo[] | null; alCambiar: (mensaje: string) => void }) {
  const [creando, setCreando] = useState(false);
  const [editando, setEditando] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function crear(datos: { nombre: string; descripcion: string; permisos: Record<string, string> }) {
    await pedir("/api/auth/roles", { method: "POST", body: JSON.stringify(datos) });
    setCreando(false);
    alCambiar(`Se creó el rol «${datos.nombre}».`);
  }

  async function editar(clave: string, datos: object, mensaje: string) {
    await pedir(`/api/auth/roles/${clave}`, { method: "PATCH", body: JSON.stringify(datos) });
    setEditando(null);
    alCambiar(mensaje);
  }

  async function activar(r: RolInfo) {
    setError("");
    try {
      await editar(r.clave, { activo: !r.activo }, r.activo ? `Se desactivó el rol «${r.nombre}».` : `Se reactivó el rol «${r.nombre}».`);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cambiar el rol.");
    }
  }

  return (
    <>
      <p className="sub">
        Los cuatro roles base del diseño no se modifican. Los demás corresponden a los perfiles usuales de los sistemas de
        gestión y descripción archivística (AtoM, ArchivesSpace, Archivematica y el modelo de requisitos SGDEA del AGN) y se
        pueden ajustar; también puede crear otros.
      </p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="tarjeta">
        <div className="tarjeta-cab">
          <span>{roles ? `${roles.length} roles` : "Roles"}</span>
          <button type="button" className="boton chico primario" onClick={() => setCreando(!creando)}>{creando ? "Cerrar" : "+ Nuevo rol"}</button>
        </div>
        {creando && <Editor alGuardar={crear} alCancelar={() => setCreando(false)} />}
        {roles?.map((r) => (
          editando === r.clave ? (
            <Editor key={r.clave} inicial={r} alCancelar={() => setEditando(null)}
                    alGuardar={(d) => editar(r.clave, d, `Se guardó el rol «${d.nombre}».`)} />
          ) : (
            <div className="fila" key={r.clave}>
              <div className="fila-principal">
                <div className="nombre">{r.nombre}</div>
                {r.descripcion && <div className="meta">{r.descripcion}</div>}
                <div className="meta"><Resumen permisos={r.permisos} /></div>
              </div>
              <div className="insignias">
                {r.base && <span className="insignia agente">Base</span>}
                <span className={`insignia ${r.activo ? "bien" : "error"}`}>{r.activo ? "Activo" : "Inactivo"}</span>
                <span className="insignia proceso">{r.usuarios} usuario{r.usuarios === 1 ? "" : "s"}</span>
              </div>
              {!r.base && (
                <div className="acciones">
                  <button type="button" className="boton chico" onClick={() => setEditando(r.clave)}>Editar</button>
                  <button type="button" className={`boton chico${r.activo ? " peligro" : ""}`} onClick={() => activar(r)}>
                    {r.activo ? "Desactivar" : "Reactivar"}
                  </button>
                </div>
              )}
            </div>
          )
        ))}
      </div>
    </>
  );
}
