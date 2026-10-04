// Cliente de la API. El token de acceso vive solo en memoria (nunca en
// localStorage, donde un script ajeno podría leerlo). Cuando vence, se
// renueva una vez con la galleta HttpOnly de la sesión y se repite la
// petición; si la sesión ya se cerró, se avisa para volver al ingreso.

export class ErrorAPI extends Error {
  status: number;
  datos?: any; // cuerpo completo de la respuesta de error, cuando trae más que el mensaje
  constructor(status: number, mensaje: string, datos?: unknown) {
    super(mensaje);
    this.status = status;
    this.datos = datos;
  }
}

// Clave del rol: uno de los cuatro base o uno creado por la administradora.
export type Rol = string;

// Color de la insignia de cada rol (mismo criterio en todas las pantallas).
const CLASES: Record<string, string> = { administrador: "agente", consulta: "alerta" };
export function claseRol(rol: Rol): string {
  return CLASES[rol] || "proceso";
}

export type Modulo = "ingesta" | "descripcion" | "vocabularios" | "instrumentos" | "preservacion" | "catalogo" | "auditoria";

// La interfaz solo oculta lo que el rol no puede usar; decide el servidor.
export function puede(u: UsuarioBreve | null, modulo: Modulo | "usuarios", tipo: "leer" | "escribir" = "leer"): boolean {
  if (!u) return false;
  if (modulo === "usuarios") return u.es_administrador;
  const nivel = u.permisos?.[modulo] || "ninguno";
  if (modulo === "auditoria") return tipo === "leer" && (nivel === "propia" || nivel === "todo");
  return tipo === "escribir" ? nivel === "escribir" : nivel === "leer" || nivel === "escribir";
}

export const MODULOS_TRABAJO: Modulo[] = ["ingesta", "descripcion", "vocabularios", "instrumentos", "preservacion"];

export interface UsuarioBreve {
  id: string;
  nombre: string;
  correo: string;
  rol: Rol;
  rol_nombre: string;
  iniciales: string;
  es_administrador: boolean;
  permisos: Record<string, string>;
  doble_factor?: boolean; // la cuenta usa segundo factor
  doble_factor_requerido?: boolean; // su rol lo exige
}

interface RespuestaSesion {
  token_acceso: string;
  expira_en: number;
  rol: Rol;
  usuario: UsuarioBreve;
}

let token: string | null = null;
let alCerrar: () => void = () => {};
let alRenovar: (u: UsuarioBreve) => void = () => {};
let renovando: Promise<UsuarioBreve | null> | null = null;

export function configurarSesion(opciones: { alCerrar: () => void; alRenovar: (u: UsuarioBreve) => void }) {
  alCerrar = opciones.alCerrar;
  alRenovar = opciones.alRenovar;
}

function mensajeDe(cuerpo: unknown, status: number): string {
  const detalle = (cuerpo as { detail?: unknown })?.detail;
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle)) {
    return detalle
      .map((d: { msg?: string }) => (d.msg || "").replace(/^Value error, /, ""))
      .filter(Boolean)
      .join(" ");
  }
  if (status >= 500) return "El servidor no pudo completar la acción. Intente de nuevo en un momento.";
  return "No se pudo completar la acción.";
}

async function llamar(ruta: string, opciones: RequestInit, conToken: boolean): Promise<Response> {
  const cabeceras = new Headers(opciones.headers);
  if (typeof opciones.body === "string" && !cabeceras.has("Content-Type")) cabeceras.set("Content-Type", "application/json");
  if (conToken && token) cabeceras.set("Authorization", `Bearer ${token}`);
  try {
    return await fetch(ruta, { ...opciones, headers: cabeceras, credentials: "same-origin" });
  } catch {
    throw new ErrorAPI(0, "No hay conexión con el servidor. Revise su conexión a internet.");
  }
}

export function renovar(): Promise<UsuarioBreve | null> {
  if (!renovando) {
    renovando = (async () => {
      const r = await llamar("/api/auth/refresh", { method: "POST" }, false);
      if (!r.ok) {
        token = null;
        return null;
      }
      const datos: RespuestaSesion = await r.json();
      token = datos.token_acceso;
      alRenovar(datos.usuario);
      return datos.usuario;
    })().finally(() => {
      renovando = null;
    });
  }
  return renovando;
}

async function conSesion(ruta: string, opciones: RequestInit): Promise<Response> {
  let r = await llamar(ruta, opciones, true);
  if (r.status === 401 && token) {
    const cuerpo = await r.clone().json().catch(() => ({}));
    if (cuerpo.detail === "token_expirado" && (await renovar())) {
      r = await llamar(ruta, opciones, true);
    }
    if (r.status === 401) {
      token = null;
      alCerrar();
      throw new ErrorAPI(401, "Su sesión se cerró. Ingrese de nuevo.");
    }
  }
  return r;
}

export async function pedir<T>(ruta: string, opciones: RequestInit = {}): Promise<T> {
  const r = await conSesion(ruta, opciones);
  if (r.status === 204) return undefined as T;
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new ErrorAPI(r.status, mensajeDe(cuerpo, r.status), cuerpo);
  return cuerpo as T;
}

// Un archivo del servidor como Blob (p. ej. la imagen de una página), con sesión.
export async function pedirArchivo(ruta: string): Promise<Blob> {
  const r = await conSesion(ruta, { method: "GET" });
  if (!r.ok) {
    const cuerpo = await r.json().catch(() => ({}));
    throw new ErrorAPI(r.status, mensajeDe(cuerpo, r.status), cuerpo);
  }
  return r.blob();
}

// Descarga un archivo generado por el servidor (inventario, guía) y lo
// entrega al navegador con el nombre que propone el servidor.
export async function descargar(ruta: string, opciones: RequestInit = {}): Promise<Headers> {
  const r = await conSesion(ruta, opciones);
  if (!r.ok) {
    const cuerpo = await r.json().catch(() => ({}));
    throw new ErrorAPI(r.status, mensajeDe(cuerpo, r.status), cuerpo);
  }
  const nombre = /filename="([^"]+)"/.exec(r.headers.get("Content-Disposition") || "")?.[1] || "archivo";
  const url = URL.createObjectURL(await r.blob());
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return r.headers;
}

/** Primer paso: la contraseña. Si la cuenta tiene segundo factor, devuelve el desafío en lugar de la sesión. */
export async function ingresar(correo: string, contrasena: string): Promise<UsuarioBreve | { desafio: string }> {
  const r = await llamar("/api/auth/login", { method: "POST", body: JSON.stringify({ correo, contrasena }) }, false);
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new ErrorAPI(r.status, mensajeDe(cuerpo, r.status));
  if ((cuerpo as { segundo_factor?: boolean }).segundo_factor) return { desafio: (cuerpo as { desafio: string }).desafio };
  token = (cuerpo as RespuestaSesion).token_acceso;
  return (cuerpo as RespuestaSesion).usuario;
}

/** Segundo paso: el código de la aplicación de autenticación o uno de respaldo. */
export async function ingresarSegundoFactor(desafio: string, codigo: string): Promise<UsuarioBreve> {
  const r = await llamar("/api/auth/login/segundo-factor", { method: "POST", body: JSON.stringify({ desafio, codigo }) }, false);
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new ErrorAPI(r.status, mensajeDe(cuerpo, r.status));
  token = (cuerpo as RespuestaSesion).token_acceso;
  return (cuerpo as RespuestaSesion).usuario;
}

export async function salir(): Promise<void> {
  token = null;
  await llamar("/api/auth/logout", { method: "POST" }, false).catch(() => undefined);
}

export const publico = {
  async post<T>(ruta: string, cuerpo: unknown): Promise<T> {
    const r = await llamar(ruta, { method: "POST", body: JSON.stringify(cuerpo) }, false);
    const datos = await r.json().catch(() => ({}));
    if (!r.ok) throw new ErrorAPI(r.status, mensajeDe(datos, r.status));
    return datos as T;
  },
  async get<T>(ruta: string): Promise<T> {
    const r = await llamar(ruta, { method: "GET" }, false);
    const datos = await r.json().catch(() => ({}));
    if (!r.ok) throw new ErrorAPI(r.status, mensajeDe(datos, r.status));
    return datos as T;
  },
};

// Subida de archivos con avance (fetch no informa el progreso de envío).
// El servidor verifica la sesión antes de leer el archivo, así que basta
// con renovar el token si ya venció antes de empezar.
export function subir<T>(ruta: string, datos: FormData, alAvanzar: (fraccion: number) => void,
                         señal?: AbortSignal): Promise<T> {
  const intentar = (reintento: boolean): Promise<T> =>
    new Promise<T>((resolver, rechazar) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", ruta);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (e) => e.lengthComputable && alAvanzar(e.loaded / e.total);
      xhr.onerror = () => rechazar(new ErrorAPI(0, "Se perdió la conexión durante la subida."));
      xhr.onabort = () => rechazar(new ErrorAPI(0, "Subida cancelada."));
      xhr.onload = async () => {
        let cuerpo: unknown = {};
        try { cuerpo = JSON.parse(xhr.responseText); } catch { /* respuesta vacía */ }
        if (xhr.status === 401 && !reintento && (cuerpo as { detail?: string }).detail === "token_expirado" && (await renovar())) {
          intentar(true).then(resolver, rechazar);
          return;
        }
        if (xhr.status === 401) {
          token = null;
          alCerrar();
          rechazar(new ErrorAPI(401, "Su sesión se cerró. Ingrese de nuevo."));
          return;
        }
        if (xhr.status < 200 || xhr.status >= 300) {
          rechazar(new ErrorAPI(xhr.status, mensajeDe(cuerpo, xhr.status)));
          return;
        }
        resolver(cuerpo as T);
      };
      señal?.addEventListener("abort", () => xhr.abort());
      xhr.send(datos);
    });
  return intentar(false);
}
