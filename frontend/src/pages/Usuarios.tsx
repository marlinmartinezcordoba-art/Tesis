import { confirmar } from "@/lib/dialogos";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { enlaceHistoria } from "@/lib/auditoria";
import { MenuAcciones, type Accion } from "@/components/Encabezado";
import { useNavigate } from "react-router-dom";
import { claseRol, ErrorAPI, pedir, puede, type Rol } from "@/lib/api";
import { PanelRoles, type RolInfo } from "@/pages/Roles";
import { fecha } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";
import { useVista } from "@/components/Marco";
import { Ventana } from "@/components/Ventana";
import { PuestaEnMarcha } from "@/components/PuestaEnMarcha";
import { PruebaInyeccion } from "@/components/PruebaInyeccion";
import { BibliotecaAsistente } from "@/components/BibliotecaAsistente";

interface Usuario {
  id: string;
  nombre: string;
  correo: string;
  rol: Rol;
  rol_nombre: string;
  iniciales: string;
  activo: boolean;
  invitacion_pendiente: boolean;
  recuperacion_solicitada: boolean;
  ultimo_ingreso: string | null;
  sesiones_abiertas: number;
  creado_en: string;
  doble_factor?: boolean;
}

interface Entrega {
  enviado: boolean;
  mensaje: string;
  enlace: string | null;
}



function Resultado({ entrega, alCerrar }: { entrega: Entrega; alCerrar: () => void }) {
  const [copiado, setCopiado] = useState(false);
  return (
    <div className={`aviso ${entrega.enviado ? "bien" : "alerta"}`} role="status">
      {entrega.mensaje}
      {entrega.enlace && (
        <>
          <div className="copiar">
            <input className="entrada" readOnly value={entrega.enlace} onFocus={(e) => e.target.select()} aria-label="Enlace de un solo uso" />
            <button type="button" className="boton chico" onClick={async (e) => {
              // Sin HTTPS el navegador no ofrece el portapapeles moderno.
              if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(entrega.enlace!);
              } else {
                (e.currentTarget.previousElementSibling as HTMLInputElement).select();
                document.execCommand("copy");
              }
              setCopiado(true);
            }}>
              {copiado ? "Copiado" : "Copiar"}
            </button>
          </div>
          <div className="pista" style={{ color: "inherit" }}>
            Este enlace solo se muestra ahora. Sirve una vez; quien lo abra define la contraseña de esa cuenta.
          </div>
        </>
      )}
      <div style={{ marginTop: 8 }}>
        <button type="button" className="boton chico" onClick={alCerrar}>Entendido</button>
      </div>
    </div>
  );
}

function NuevoUsuario({ alCrear, roles }: { alCrear: (e: Entrega) => void; roles: RolInfo[] }) {
  const [nombre, setNombre] = useState("");
  const [correo, setCorreo] = useState("");
  const [rol, setRol] = useState<Rol>("archivista");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function crear(e: FormEvent) {
    e.preventDefault();
    setError("");
    setEnviando(true);
    try {
      const r = await pedir<{ entrega: Entrega }>("/api/auth/usuarios", {
        method: "POST",
        body: JSON.stringify({ nombre, correo, rol }),
      });
      alCrear(r.entrega);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo crear el usuario.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form className="formulario-nuevo" onSubmit={crear}>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="rejilla">
        <div className="campo">
          <label htmlFor="n-nombre">Nombre completo</label>
          <input id="n-nombre" className="entrada" required minLength={3} value={nombre} onChange={(e) => setNombre(e.target.value)} />
        </div>
        <div className="campo">
          <label htmlFor="n-correo">Correo</label>
          <input id="n-correo" className="entrada" type="email" required value={correo} onChange={(e) => setCorreo(e.target.value)} />
        </div>
        <div className="campo">
          <label htmlFor="n-rol">Rol</label>
          <select id="n-rol" className="selector" value={rol} onChange={(e) => setRol(e.target.value as Rol)}>
            {roles.filter((r) => r.activo).map((r) => <option key={r.clave} value={r.clave}>{r.nombre}</option>)}
          </select>
        </div>
      </div>
      <p className="pista" style={{ marginTop: 0 }}>{roles.find((r) => r.clave === rol)?.descripcion}</p>
      <button className="boton primario" type="submit" disabled={enviando}>
        {enviando ? "Creando…" : "Crear usuario y enviar invitación"}
      </button>
      <p className="pista">
        La persona recibe un correo con un enlace para definir su propia contraseña. El administrador nunca la conoce
        ni la define.
      </p>
    </form>
  );
}

function FilaUsuario({ u, propio, alCambiar, alEntregar, roles }: {
  roles: RolInfo[];
  u: Usuario;
  propio: boolean;
  alCambiar: (mensaje: string) => void;
  alEntregar: (e: Entrega) => void;
}) {
  const { usuario: usuarioSesion } = useSesion();
  const navegar = useNavigate();
  const [editando, setEditando] = useState(false);
  const [nombre, setNombre] = useState(u.nombre);
  const [rol, setRol] = useState<Rol>(u.rol);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);

  async function accion(fn: () => Promise<void>) {
    setError("");
    setOcupado(true);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo completar la acción.");
    } finally {
      setOcupado(false);
    }
  }

  const editar = (datos: object, mensaje: string) =>
    accion(async () => {
      await pedir(`/api/auth/usuarios/${u.id}`, { method: "PATCH", body: JSON.stringify(datos) });
      setEditando(false);
      alCambiar(mensaje);
    });

  const enviarEnlace = () => accion(async () => {
    const e = await pedir<Entrega>(`/api/auth/usuarios/${u.id}/enlace`, { method: "POST" });
    alEntregar(e);
  });
  const secundarias: Accion[] = [];
  if (puede(usuarioSesion, "auditoria")) {
    secundarias.push({ texto: "Ver su historial de auditoría", alHacer: () => navegar(enlaceHistoria("usuario", u.id, u.nombre, "/usuarios")) });
  }
  if (!propio && u.activo) {
    secundarias.push({ texto: u.invitacion_pendiente ? "Reenviar invitación" : "Enviar enlace de contraseña", alHacer: enviarEnlace, deshabilitada: ocupado });
  }
  if (u.sesiones_abiertas > 0 && !propio) {
    secundarias.push({ texto: "Cerrar sus sesiones", deshabilitada: ocupado, alHacer: () => accion(async () => {
      const r = await pedir<{ mensaje: string }>(`/api/auth/usuarios/${u.id}/cerrar-sesiones`, { method: "POST" });
      alCambiar(r.mensaje);
    }) });
  }
  if (u.doble_factor && !propio) {
    secundarias.push({ texto: "Restablecer segundo factor", deshabilitada: ocupado, alHacer: async () => {
      if (await confirmar(`¿Quitar el segundo factor de ${u.nombre}? Úselo si perdió el teléfono: se cierran sus `
          + "sesiones y deberá configurarlo de nuevo.")) {
        accion(async () => {
          const r = await pedir<{ mensaje: string }>(`/api/auth/usuarios/${u.id}/doble-factor/restablecer`, { method: "POST" });
          alCambiar(r.mensaje);
        });
      }
    } });
  }
  if (!propio) {
    secundarias.push(u.activo ? { texto: "Desactivar la cuenta", peligro: true, deshabilitada: ocupado, alHacer: async () => {
      if (await confirmar(`¿Desactivar la cuenta de ${u.nombre}? No podrá ingresar; sus datos y su trazabilidad se conservan.`)) {
        editar({ activo: false }, `Se desactivó la cuenta de ${u.nombre}.`);
      }
    } } : { texto: "Reactivar la cuenta", deshabilitada: ocupado, alHacer: () => editar({ activo: true }, `Se reactivó la cuenta de ${u.nombre}.`) });
  }

  return (
    <>
      <tr>
        <td>
          <div className="celda-usuario">
            <span className="avatar">{u.iniciales}</span>
            <span><strong>{u.nombre}</strong>{propio && <span className="meta"> (usted)</span>}<span className="secundario">{u.correo}</span></span>
          </div>
        </td>
        <td><span className={`insignia ${claseRol(u.rol)}`}>{u.rol_nombre}</span></td>
        <td>
          <span className={`insignia ${u.activo ? "bien" : "error"}`}>{u.activo ? "✓ Activo" : "✕ Inactivo"}</span>
          {u.invitacion_pendiente && u.activo && <span className="secundario">Invitación pendiente</span>}
          {u.recuperacion_solicitada && u.activo && <span className="secundario">Pidió recuperar la contraseña</span>}
        </td>
        <td style={{ whiteSpace: "nowrap" }}>{u.ultimo_ingreso ? fecha(u.ultimo_ingreso) : <span className="meta">Nunca</span>}</td>
        <td className="acciones-celda" style={{ width: 150 }}>
          <div style={{ display: "flex", gap: 6, justifyContent: "flex-end", alignItems: "center" }}>
            {!editando && <button type="button" className="boton chico" onClick={() => setEditando(true)}>Editar</button>}
            <MenuAcciones etiqueta={`Más acciones para ${u.nombre}`} acciones={secundarias} />
          </div>
        </td>
      </tr>
      {(editando || error) && (
        <tr className="fila-edicion">
          <td colSpan={5}>
            {error && <div className="aviso error" style={{ margin: "0 0 8px" }} role="alert">{error}</div>}
            {editando && (
              <div className="rejilla">
                <input className="entrada" aria-label="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} />
                <select className="selector" aria-label="Rol" value={rol} disabled={propio} onChange={(e) => setRol(e.target.value as Rol)}
                        title={propio ? "Nadie puede cambiar su propio rol" : undefined}>
                  {roles.filter((r) => r.activo || r.clave === u.rol).map((r) => <option key={r.clave} value={r.clave}>{r.nombre}</option>)}
                </select>
                <div className="acciones">
                  <button type="button" className="boton chico primario" disabled={ocupado}
                          onClick={() => editar({ nombre, ...(propio ? {} : { rol }) }, `Se guardaron los cambios de ${nombre}.`)}>Guardar</button>
                  <button type="button" className="boton chico" onClick={() => { setEditando(false); setNombre(u.nombre); setRol(u.rol); }}>Cancelar</button>
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

const CLAVE_AVISO_CORREO = "ricora:aviso-correo-leido";

export function Usuarios() {
  const { usuario } = useSesion();
  const [usuarios, setUsuarios] = useState<Usuario[] | null>(null);
  const [correoConfigurado, setCorreoConfigurado] = useState(true);
  // Preferencia de quien mira (solo en su navegador): el aviso de correo ya leído.
  const [avisoCerrado, setAvisoCerrado] = useState(() => {
    try { return localStorage.getItem(CLAVE_AVISO_CORREO) === "1"; } catch { return false; }
  });
  const recordarAviso = (cerrado: boolean) => {
    setAvisoCerrado(cerrado);
    try {
      if (cerrado) localStorage.setItem(CLAVE_AVISO_CORREO, "1");
      else localStorage.removeItem(CLAVE_AVISO_CORREO);
    } catch { /* sin almacenamiento: el aviso vuelve a verse completo, nada se rompe */ }
  };
  const [q, setQ] = useState("");
  const [rol, setRol] = useState("");
  const [estado, setEstado] = useState("true");
  const [nuevo, setNuevo] = useState(false);
  const [entrega, setEntrega] = useState<Entrega | null>(null);
  const [mensaje, setMensaje] = useState("");
  const [error, setError] = useState("");
  const pestana = useVista<"usuarios" | "roles" | "puesta" | "biblioteca">("/usuarios");
  const [roles, setRoles] = useState<RolInfo[] | null>(null);

  const cargarRoles = useCallback(() => {
    pedir<RolInfo[]>("/api/auth/roles").then(setRoles).catch(() => setRoles([]));
  }, []);
  useEffect(cargarRoles, [cargarRoles]);

  const cargar = useCallback(async () => {
    const p = new URLSearchParams();
    if (q.trim()) p.set("q", q.trim());
    if (rol) p.set("rol", rol);
    if (estado) p.set("activo", estado);
    try {
      const r = await pedir<{ usuarios: Usuario[]; correo_configurado: boolean }>(`/api/auth/usuarios?${p}`);
      setUsuarios(r.usuarios);
      setCorreoConfigurado(r.correo_configurado);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar la lista.");
    }
  }, [q, rol, estado]);

  useEffect(() => {
    const t = setTimeout(cargar, 250);
    return () => clearTimeout(t);
  }, [cargar]);

  async function probarCorreo() {
    setError("");
    try {
      const r = await pedir<{ mensaje: string }>("/api/auth/correo/prueba", { method: "POST" });
      setMensaje(r.mensaje);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo enviar el correo de prueba.");
    }
  }

  const alCambiar = (m: string) => { setMensaje(m); setEntrega(null); cargar(); };
  const alEntregar = (e: Entrega) => { setEntrega(e); setMensaje(""); cargar(); };

  return (
    <>
      <h1>{pestana === "roles" ? "Roles y permisos" : pestana === "puesta" ? "Puesta en marcha"
        : pestana === "biblioteca" ? "Biblioteca del asistente" : "Usuarios"}</h1>
      <p className="sub">
        {pestana === "biblioteca" ? "Las normas y manuales con los que responde el Asistente RICORA (RAG)."
          : pestana === "puesta"
          ? "Prueba del motor contra instrucciones incrustadas y puesta en marcha: dejar el sistema en blanco para empezar a usarlo (borra lo cargado y lo descrito, conserva usuarios y configuración)."
          : "Solo visible para el rol administrador. Crear, reasignar rol o desactivar sin perder trazabilidad en auditoría."}
      </p>
      {pestana === "biblioteca" ? <BibliotecaAsistente /> : pestana === "puesta" ? <><PruebaInyeccion /><PuestaEnMarcha /></> : pestana === "roles" ? (
        <>
          {mensaje && <div className="aviso bien" role="status">{mensaje}</div>}
          <PanelRoles roles={roles} alCambiar={(m) => { setMensaje(m); cargarRoles(); }} />
        </>
      ) : (<>

      {correoConfigurado && (
        <div className="filtros" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="boton chico" onClick={probarCorreo}>Enviar correo de prueba a mi cuenta</button>
        </div>
      )}
      {mensaje && <div className="aviso bien" role="status">{mensaje}</div>}
      {error && <div className="aviso error" role="alert">{error}</div>}
      {entrega && <Resultado entrega={entrega} alCerrar={() => setEntrega(null)} />}

      <div className="filtros">
        <input className="entrada" type="search" placeholder="Buscar por nombre o correo" aria-label="Buscar"
               value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="selector" aria-label="Filtrar por rol" value={rol} onChange={(e) => setRol(e.target.value)}>
          <option value="">Todos los roles</option>
          {(roles || []).map((r) => <option key={r.clave} value={r.clave}>{r.nombre}</option>)}
        </select>
        <select className="selector" aria-label="Filtrar por estado" value={estado} onChange={(e) => setEstado(e.target.value)}>
          <option value="">Activos e inactivos</option>
          <option value="true">Activos</option>
          <option value="false">Inactivos</option>
        </select>
      </div>

      <div className="tarjeta">
        <div className="tarjeta-cab">
          <span>{usuarios ? `${usuarios.length} usuario${usuarios.length === 1 ? "" : "s"}` : "Usuarios"}</span>
          <button type="button" className="boton chico primario" onClick={() => setNuevo(true)}>
            + Nuevo usuario
          </button>
        </div>
        {nuevo && (
          <Ventana titulo="Nuevo usuario" alCerrar={() => setNuevo(false)}>
            <NuevoUsuario roles={roles || []} alCrear={(e) => { setNuevo(false); alEntregar(e); }} />
          </Ventana>
        )}
        {usuarios === null ? (
          <div className="vacio">Cargando…</div>
        ) : usuarios.length === 0 ? (
          <div className="vacio">Ningún usuario coincide con los filtros.</div>
        ) : (
          <div className="tabla-desplazable">
            <table className="tabla-datos">
              <thead><tr><th>Usuario</th><th>Rol</th><th>Estado</th><th>Último ingreso</th><th className="acciones-celda"><span className="sr-only">Acciones</span></th></tr></thead>
              <tbody>
                {usuarios.map((u) => (
                  <FilaUsuario key={u.id} roles={roles || []} u={u} propio={u.id === usuario?.id} alCambiar={alCambiar} alEntregar={alEntregar} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      </>)}
    </>
  );
}
