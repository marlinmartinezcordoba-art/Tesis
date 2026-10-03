import { useCallback, useEffect, useState, type FormEvent } from "react";
import { EnlaceHistoria } from "@/components/Historia";
import { claseRol, ErrorAPI, pedir, type Rol } from "@/lib/api";
import { PanelRoles, type RolInfo } from "@/pages/Roles";
import { fecha } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";
import { useVista } from "@/components/Marco";

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

  return (
    <div className="fila">
      <span className="avatar">{u.iniciales}</span>
      <div className="fila-principal">
        <div className="nombre">{u.nombre}{propio && <span className="meta"> (usted)</span>}</div>
        <div className="meta">{u.correo} · último ingreso: {fecha(u.ultimo_ingreso)}</div>
        {error && <div className="aviso error" style={{ margin: "8px 0 0" }} role="alert">{error}</div>}
        {editando && (
          <div className="rejilla" style={{ marginTop: 10 }}>
            <input className="entrada" aria-label="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} />
            <select className="selector" aria-label="Rol" value={rol} disabled={propio} onChange={(e) => setRol(e.target.value as Rol)}
                    title={propio ? "Nadie puede cambiar su propio rol" : undefined}>
              {roles.filter((r) => r.activo || r.clave === u.rol).map((r) => <option key={r.clave} value={r.clave}>{r.nombre}</option>)}
            </select>
            <div className="acciones">
              <button type="button" className="boton chico primario" disabled={ocupado}
                      onClick={() => editar({ nombre, ...(propio ? {} : { rol }) }, `Se guardaron los cambios de ${nombre}.`)}>
                Guardar
              </button>
              <button type="button" className="boton chico" onClick={() => { setEditando(false); setNombre(u.nombre); setRol(u.rol); }}>
                Cancelar
              </button>
            </div>
          </div>
        )}
      </div>
      <div className="insignias">
        <span className={`insignia ${claseRol(u.rol)}`}>{u.rol_nombre}</span>
        <span className={`insignia ${u.activo ? "bien" : "error"}`}>{u.activo ? "Activo" : "Inactivo"}</span>
        {u.invitacion_pendiente && u.activo && <span className="insignia acento">Invitación pendiente</span>}
        {u.recuperacion_solicitada && u.activo && <span className="insignia alerta">Pidió recuperar contraseña</span>}
      </div>
      {!editando && (
        <div className="acciones">
          <button type="button" className="boton chico" onClick={() => setEditando(true)}>Editar</button>
          <EnlaceHistoria tipo="usuario" id={u.id} nombre={u.nombre} />
          {!propio && u.activo && (
            <button type="button" className="boton chico" disabled={ocupado}
                    onClick={() => accion(async () => {
                      const e = await pedir<Entrega>(`/api/auth/usuarios/${u.id}/enlace`, { method: "POST" });
                      alEntregar(e);
                    })}>
              {u.invitacion_pendiente ? "Reenviar invitación" : "Enviar enlace de contraseña"}
            </button>
          )}
          {u.sesiones_abiertas > 0 && !propio && (
            <button type="button" className="boton chico" disabled={ocupado}
                    onClick={() => accion(async () => {
                      const r = await pedir<{ mensaje: string }>(`/api/auth/usuarios/${u.id}/cerrar-sesiones`, { method: "POST" });
                      alCambiar(r.mensaje);
                    })}>
              Cerrar sesiones
            </button>
          )}
          {!propio && (u.activo ? (
            <button type="button" className="boton chico peligro" disabled={ocupado}
                    onClick={() => {
                      if (window.confirm(`¿Desactivar la cuenta de ${u.nombre}? No podrá ingresar; sus datos y su trazabilidad se conservan.`)) {
                        editar({ activo: false }, `Se desactivó la cuenta de ${u.nombre}.`);
                      }
                    }}>
              Desactivar
            </button>
          ) : (
            <button type="button" className="boton chico" disabled={ocupado}
                    onClick={() => editar({ activo: true }, `Se reactivó la cuenta de ${u.nombre}.`)}>
              Reactivar
            </button>
          ))}
        </div>
      )}
    </div>
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
  const [estado, setEstado] = useState("");
  const [nuevo, setNuevo] = useState(false);
  const [entrega, setEntrega] = useState<Entrega | null>(null);
  const [mensaje, setMensaje] = useState("");
  const [error, setError] = useState("");
  const pestana = useVista<"usuarios" | "roles">("/usuarios");
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
      <h1>{pestana === "roles" ? "Roles y permisos" : "Usuarios"}</h1>
      <p className="sub">
        Solo visible para el rol administrador. Crear, reasignar rol o desactivar sin perder trazabilidad en auditoría.
      </p>
      {pestana === "roles" ? (
        <>
          {mensaje && <div className="aviso bien" role="status">{mensaje}</div>}
          <PanelRoles roles={roles} alCambiar={(m) => { setMensaje(m); cargarRoles(); }} />
        </>
      ) : (<>

      {!correoConfigurado ? (
        avisoCerrado ? (
          // Leído: queda un aviso discreto mientras el correo siga sin configurar.
          <div className="aviso-discreto" role="status">
            ⚠ Correo sin configurar: los enlaces se muestran en pantalla.
            <button type="button" className="enlace" onClick={() => recordarAviso(false)}>Ver detalle</button>
          </div>
        ) : (
          <div className="aviso alerta">
            <button type="button" className="cerrar-aviso" aria-label="Cerrar el aviso (queda una versión breve)"
                    onClick={() => recordarAviso(true)}>×</button>
            El envío de correo aún no está configurado en el servidor. Mientras tanto, al crear un usuario o enviarle un
            enlace, el sistema le muestra el enlace a usted una sola vez para que se lo haga llegar a la persona.
          </div>
        )
      ) : (
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
          <button type="button" className="boton chico primario" onClick={() => setNuevo(!nuevo)} aria-expanded={nuevo}>
            {nuevo ? "Cerrar" : "+ Nuevo usuario"}
          </button>
        </div>
        {nuevo && <NuevoUsuario roles={roles || []} alCrear={(e) => { setNuevo(false); alEntregar(e); }} />}
        {usuarios === null ? (
          <div className="vacio">Cargando…</div>
        ) : usuarios.length === 0 ? (
          <div className="vacio">Ningún usuario coincide con los filtros.</div>
        ) : (
          usuarios.map((u) => (
            <FilaUsuario key={u.id} roles={roles || []} u={u} propio={u.id === usuario?.id} alCambiar={alCambiar} alEntregar={alEntregar} />
          ))
        )}
      </div>
      </>)}
    </>
  );
}
