import { useEffect, useState, type FormEvent } from "react";
import { ErrorAPI, descargar, pedir } from "@/lib/api";

// Perfil RiC-Col del AGN (Esquema de Metadatos v1.4) en la ficha de una descripción.

export type DatosPersonales = "no_contiene" | "personales" | "sensibles" | "menores";

export interface Proteccion {
  datos_personales: DatosPersonales | null;
  nota_accesibilidad: string | null;
}

export const DATOS_PERSONALES_NOMBRE: Record<DatosPersonales, string> = {
  no_contiene: "No contiene datos personales",
  personales: "Contiene datos personales",
  sensibles: "Contiene datos sensibles (salud, origen, creencias…)",
  menores: "Contiene datos de niños, niñas o adolescentes",
};

export function ProteccionDatos({ valor, editando, alCambiar }: {
  valor: { datos: string; nota: string }; editando: boolean; alCambiar: (v: { datos: string; nota: string }) => void;
}) {
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Datos personales y accesibilidad (perfil AGN)</div>
      <div className="tarjeta-cuerpo">
        <p className="ayuda" style={{ marginTop: 0 }}>
          Ley 1581 de 2012: qué clase de datos personales contiene. No es la clasificación de acceso de la Ley 1712: un
          documento público puede tener datos que se anonimizan al consultarlo. Vacío quiere decir «sin revisar».
        </p>
        {editando ? (
          <div className="rejilla">
            <div className="campo" style={{ margin: 0 }}>
              <label htmlFor="p-datos">Datos personales</label>
              <select id="p-datos" className="selector" value={valor.datos}
                      onChange={(e) => alCambiar({ ...valor, datos: e.target.value })}>
                <option value="">Sin revisar</option>
                {Object.entries(DATOS_PERSONALES_NOMBRE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div className="campo" style={{ margin: 0 }}>
              <label htmlFor="p-accesible">Versión accesible (Ley 1680 de 2013)</label>
              <textarea id="p-accesible" className="entrada" rows={2} value={valor.nota} maxLength={2000}
                        placeholder="p. ej. Transcripción en texto plano para lector de pantalla"
                        onChange={(e) => alCambiar({ ...valor, nota: e.target.value })} />
            </div>
          </div>
        ) : (
          <dl className="pares" style={{ margin: 0 }}>
            <dt>Datos personales</dt>
            <dd>{valor.datos ? DATOS_PERSONALES_NOMBRE[valor.datos as DatosPersonales]
              : <span className="texto-alerta">Sin revisar</span>}</dd>
            <dt>Versión accesible</dt>
            <dd>{valor.nota || <span className="tenue">Sin nota (sale en la ficha pública cuando la hay)</span>}</dd>
          </dl>
        )}
      </div>
    </div>
  );
}

export interface InstanciacionRegistro {
  id: string;
  nombre: string;
  fisica?: boolean;
  soporte?: string | null;
  ubicacion?: string | null;
  caracteristicas_fisicas?: string | null;
  estado_conservacion?: string | null;
  deposito?: string | null;
  estante?: string | null;
  entrepano?: string | null;
  signatura?: string | null;
}

const SOPORTES = ["papel", "pergamino", "papel_fotografico", "microfilme", "cinta_magnetica", "disco_optico", "otro"];
const ESTADOS = ["bueno", "regular", "malo", "restaurado"];
const VACIO = { soporte: "papel", ubicacion: "", deposito: "", estante: "", entrepano: "", estado_conservacion: "",
                caracteristicas_fisicas: "" };

function nombreSoporte(s: string) {
  return (s.charAt(0).toUpperCase() + s.slice(1)).replace(/_/g, " ");
}

// El original en papel (u otro soporte) como instanciación sin archivo, con
// la signatura topográfica y el estado de conservación que pide el AGN (tabla 4).
export function OriginalesFisicos({ recursoId, instanciaciones, puede, alGuardar }: {
  recursoId: string; instanciaciones: InstanciacionRegistro[]; puede: boolean; alGuardar: (r: unknown) => void;
}) {
  const fisicos = instanciaciones.filter((i) => i.fisica);
  const [editando, setEditando] = useState<string | null>(null);
  const [datos, setDatos] = useState(VACIO);
  const [error, setError] = useState("");

  function abrir(i: InstanciacionRegistro | null) {
    setError("");
    setEditando(i ? i.id : "nuevo");
    setDatos(i ? { soporte: i.soporte || "papel", ubicacion: i.ubicacion || "", deposito: i.deposito || "",
                   estante: i.estante || "", entrepano: i.entrepano || "", estado_conservacion: i.estado_conservacion || "",
                   caracteristicas_fisicas: i.caracteristicas_fisicas || "" } : VACIO);
  }

  async function guardar(e: FormEvent) {
    e.preventDefault();
    setError("");
    const cuerpo = { ubicacion: datos.ubicacion, deposito: datos.deposito, estante: datos.estante, entrepano: datos.entrepano,
                     estado_conservacion: datos.estado_conservacion || null, caracteristicas_fisicas: datos.caracteristicas_fisicas };
    try {
      const r = editando === "nuevo"
        ? await pedir(`/api/descripcion/registros/${recursoId}/original-fisico`, { method: "POST",
                                                                                  body: JSON.stringify({ ...cuerpo, soporte: datos.soporte }) })
        : await pedir(`/api/descripcion/registros/${recursoId}/original-fisico/${editando}`, { method: "PATCH",
                                                                                              body: JSON.stringify(cuerpo) });
      setEditando(null);
      alGuardar(r);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo guardar el original físico.");
    }
  }

  const campo = (clave: keyof typeof VACIO, etiqueta: string, pista?: string) => (
    <div className="campo" style={{ margin: 0 }}>
      <label htmlFor={`f-${clave}`}>{etiqueta}</label>
      <input id={`f-${clave}`} className="entrada" value={datos[clave]} maxLength={clave === "ubicacion" ? 300 : 40}
             placeholder={pista} onChange={(e) => setDatos({ ...datos, [clave]: e.target.value })} />
    </div>
  );

  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Original físico (instanciación sin archivo)</div>
      <div className="tarjeta-cuerpo">
        {fisicos.length === 0 && editando === null && (
          <p className="tenue" style={{ marginTop: 0 }}>No hay un original en papel u otro soporte registrado.</p>
        )}
        {fisicos.map((i) => (
          <div className="fila" key={i.id}>
            <span className={`insignia ${i.estado_conservacion === "malo" ? "error" : i.estado_conservacion === "regular" || !i.estado_conservacion ? "alerta" : "bien"}`}>
              {i.estado_conservacion ? `Conservación: ${i.estado_conservacion}` : "Conservación sin dato"}
            </span>
            <div className="fila-principal">
              <div className="nombre">{i.nombre}</div>
              <div className="meta">
                {[i.signatura, i.ubicacion, i.caracteristicas_fisicas].filter(Boolean).join(" · ") || "Sin ubicación"}
              </div>
            </div>
            {puede && editando === null && <button type="button" className="boton chico" onClick={() => abrir(i)}>Corregir</button>}
          </div>
        ))}
        {editando !== null && (
          <form className="form-entidad" onSubmit={guardar}>
            <div className="rejilla">
              {editando === "nuevo" && (
                <div className="campo" style={{ margin: 0 }}>
                  <label htmlFor="f-soporte">Soporte</label>
                  <select id="f-soporte" className="selector" value={datos.soporte}
                          onChange={(e) => setDatos({ ...datos, soporte: e.target.value })}>
                    {SOPORTES.map((s) => <option key={s} value={s}>{nombreSoporte(s)}</option>)}
                  </select>
                </div>
              )}
              <div className="campo" style={{ margin: 0 }}>
                <label htmlFor="f-estado">Estado de conservación</label>
                <select id="f-estado" className="selector" value={datos.estado_conservacion}
                        onChange={(e) => setDatos({ ...datos, estado_conservacion: e.target.value })}>
                  <option value="">Sin dato</option>
                  {ESTADOS.map((s) => <option key={s} value={s}>{nombreSoporte(s)}</option>)}
                </select>
              </div>
              {campo("deposito", "Depósito")}
              {campo("estante", "Estante")}
              {campo("entrepano", "Entrepaño")}
              {campo("ubicacion", "Ubicación (texto)", "Archivo central, sede norte")}
            </div>
            <div className="campo">
              <label htmlFor="f-caract">Características físicas y daños</label>
              <textarea id="f-caract" className="entrada" rows={2} value={datos.caracteristicas_fisicas}
                        onChange={(e) => setDatos({ ...datos, caracteristicas_fisicas: e.target.value })} />
            </div>
            {error && <div className="aviso error" role="alert">{error}</div>}
            <div className="acciones">
              <button type="submit" className="boton chico primario">Guardar</button>
              <button type="button" className="boton chico" onClick={() => setEditando(null)}>Cancelar</button>
            </div>
          </form>
        )}
        {puede && editando === null && (
          <button type="button" className="boton chico" style={{ marginTop: 6 }} onClick={() => abrir(null)}>+ Original físico</button>
        )}
      </div>
    </div>
  );
}

interface Criterio { clave: string; fila: string; elemento: string; nivel: string; aplica: boolean; cumple: boolean | null }
export interface CalidadAgn {
  criterios: Criterio[];
  por_nivel: Record<string, { aplican: number; cumplen: number; porcentaje: number | null }>;
  avisos: string[];
  incoherencias: string[];
  porcentaje: number | null;
  nivel_alcanzado: string | null;
}

export const NIVEL_MADUREZ: Record<string, string> = { basico: "Básico", intermedio: "Intermedio", avanzado: "Avanzado" };

// Medición de calidad según el perfil del AGN (KPI de la fase 3 del esquema).
export function CalidadDescripcion({ recursoId, version }: { recursoId: string; version: unknown }) {
  const [c, setC] = useState<CalidadAgn | null>(null);
  useEffect(() => {
    pedir<CalidadAgn>(`/api/perfil-agn/calidad/${recursoId}`).then(setC).catch(() => setC(null));
  }, [recursoId, version]);
  if (!c) return null;
  const faltan = c.criterios.filter((x) => x.aplica && !x.cumple);
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Calidad según el perfil del AGN</div>
      <div className="tarjeta-cuerpo">
        <div className="resumen-preservacion compacto">
          {Object.entries(c.por_nivel).map(([n, v]) => (
            <div key={n} className={`cifra ${v.porcentaje === 100 ? "bien" : v.porcentaje === null ? "" : "alerta"}`}>
              <strong>{v.porcentaje === null ? "—" : `${v.porcentaje} %`}</strong>
              <span>{NIVEL_MADUREZ[n]} · {v.cumplen} de {v.aplican} criterios</span>
            </div>
          ))}
        </div>
        <p className="ayuda">
          Nivel alcanzado: <strong>{c.nivel_alcanzado ? NIVEL_MADUREZ[c.nivel_alcanzado] : "ninguno (falta el básico)"}</strong>.
          El esquema del AGN es una referencia: estos criterios orientan, no bloquean la publicación.
        </p>
        {c.incoherencias.map((t) => <div key={t} className="aviso error" role="alert">{t}</div>)}
        {c.avisos.map((t) => <div key={t} className="aviso">{t}</div>)}
        {faltan.length > 0 && (
          <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
            {faltan.map((x) => <li key={x.clave}>{x.elemento} <span className="tenue">({NIVEL_MADUREZ[x.nivel]} · {x.fila})</span></li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

// --- Vista «Perfil AGN» del módulo de instrumentos -------------------------------------------------

interface FilaPerfil {
  id: string; origen: string; entidad: string; elemento: string; codigo_agn: string; obligatoriedad: string;
  regla_agn: string; ric_cm: string; ric_o: string[]; campo: string; capa: string; estado: string; nivel: string;
  nota: string; codigo_agn_correcto: boolean;
}
interface CatalogoPerfil {
  fuentes: Record<string, { nombre: string; version: string; fecha: string; url: string; caracter?: string }>;
  capas: Record<string, string>; estados: Record<string, string>; niveles: Record<string, string>;
  filas: FilaPerfil[]; resumen: Record<string, number>; codigos_agn_incorrectos: number;
  erratas: { pagina: string; dice: string; correcto: string }[];
}
interface CalidadFondo {
  descripciones: number; truncado: boolean;
  criterios: { clave: string; fila: string; elemento: string; nivel: string; aplican: number; cumplen: number; porcentaje: number }[];
  nivel_alcanzado: Record<string, number>;
  incoherencias: { id: string; titulo: string; detalle: string[] }[];
  pendientes: { id: string; titulo: string; nivel: string; porcentaje: number }[];
}

const CLASE_ESTADO: Record<string, string> = { cubierto: "bien", parcial: "alerta", ausente: "error", no_adoptado: "neutra-borde" };

export function PerfilAgnVista({ fondoId, abrir }: { fondoId: string; abrir: (id: string) => void }) {
  const [cat, setCat] = useState<CatalogoPerfil | null>(null);
  const [calidad, setCalidad] = useState<CalidadFondo | null>(null);
  const [parte, setParte] = useState<"calidad" | "catalogo" | "erratas">("calidad");
  const [capa, setCapa] = useState("");
  const [estado, setEstado] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    pedir<CatalogoPerfil>("/api/perfil-agn").then(setCat)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar el perfil."));
  }, []);
  useEffect(() => {
    setCalidad(null);
    pedir<CalidadFondo>(`/api/perfil-agn/fondos/${fondoId}`).then(setCalidad).catch(() => undefined);
  }, [fondoId]);

  if (error) return <div className="aviso error" role="alert">{error}</div>;
  if (!cat) return <div className="cargando">Cargando…</div>;
  const filas = cat.filas.filter((f) => (!capa || f.capa === capa) && (!estado || f.estado === estado));
  const agn = cat.fuentes.agn;

  return (
    <>
      <aside className="proposito">
        <strong>Para alinear la descripción con la adaptación colombiana de RiC.</strong>
        {agn.nombre}, versión {agn.version} ({agn.fecha}). {agn.caracter}. Los códigos y las propiedades del RDF
        siguen RiC-CM {cat.fuentes.ric_cm.version} y RiC-O {cat.fuentes.ric_o.version}: el esquema del AGN cita
        {" "}{cat.codigos_agn_incorrectos} códigos que no corresponden y se corrigen aquí.
      </aside>
      <div className="acciones" role="tablist" style={{ margin: "12px 0" }}>
        {([["calidad", "Calidad del fondo"], ["catalogo", "Correspondencias"], ["erratas", "Erratas del esquema"]] as const).map(([k, n]) => (
          <button key={k} type="button" role="tab" aria-selected={parte === k}
                  className={`boton chico${parte === k ? " primario" : ""}`} onClick={() => setParte(k)}>{n}</button>
        ))}
        <button type="button" className="boton chico" onClick={() => descargar("/api/perfil-agn/catalogo.xlsx").catch(() => undefined)}>
          Descargar el perfil en Excel
        </button>
      </div>

      {parte === "calidad" && (!calidad ? <div className="cargando">Midiendo…</div> : (
        <div className="tarjeta">
          <div className="tarjeta-cab">Calidad de metadatos del fondo ({calidad.descripciones} descripciones)</div>
          <div className="tarjeta-cuerpo">
            <div className="resumen-preservacion compacto">
              {["basico", "intermedio", "avanzado", "ninguno"].map((n) => (
                <div key={n} className={`cifra ${n === "ninguno" && calidad.nivel_alcanzado[n] ? "alerta" : ""}`}>
                  <strong>{calidad.nivel_alcanzado[n] ?? 0}</strong>
                  <span>{n === "ninguno" ? "Sin el nivel básico" : `Alcanzan el nivel ${NIVEL_MADUREZ[n].toLowerCase()}`}</span>
                </div>
              ))}
            </div>
            {calidad.incoherencias.map((x) => (
              <div key={x.id} className="aviso error" role="alert">
                <button type="button" className="enlace" onClick={() => abrir(x.id)}>{x.titulo}</button>: {x.detalle.join(" ")}
              </div>
            ))}
            <div className="envoltura-tabla">
              <table className="tabla-perfil">
                <thead><tr><th>Criterio</th><th>Nivel</th><th>Cumplen</th><th>%</th><th>Perfil</th></tr></thead>
                <tbody>
                  {calidad.criterios.map((c) => (
                    <tr key={c.clave}>
                      <td>{c.elemento}</td><td>{NIVEL_MADUREZ[c.nivel]}</td><td>{c.cumplen} de {c.aplican}</td>
                      <td><span className={`insignia ${c.porcentaje === 100 ? "bien" : c.porcentaje >= 50 ? "alerta" : "error"}`}>{c.porcentaje} %</span></td>
                      <td className="meta">{c.fila}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {calidad.pendientes.length > 0 && (
              <>
                <h3 style={{ marginBottom: 4 }}>Descripciones con más por completar</h3>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {calidad.pendientes.map((p) => (
                    <li key={p.id}><button type="button" className="enlace" onClick={() => abrir(p.id)}>{p.titulo}</button>
                      <span className="meta"> · {p.porcentaje} %</span></li>
                  ))}
                </ul>
              </>
            )}
            {calidad.truncado && <p className="meta">Se midieron las primeras 2000 descripciones del fondo.</p>}
          </div>
        </div>
      ))}

      {parte === "catalogo" && (
        <div className="tarjeta">
          <div className="tarjeta-cab">
            AGN ↔ RiC-CM ↔ RiC-O ↔ RICORA · {Object.entries(cat.resumen).map(([k, v]) => `${v} ${cat.estados[k].toLowerCase()}`).join(" · ")}
          </div>
          <div className="tarjeta-cuerpo">
            <div className="rejilla" style={{ marginBottom: 10 }}>
              <select className="selector" aria-label="Capa" value={capa} onChange={(e) => setCapa(e.target.value)}>
                <option value="">Todas las capas</option>
                {Object.entries(cat.capas).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <select className="selector" aria-label="Estado" value={estado} onChange={(e) => setEstado(e.target.value)}>
                <option value="">Todos los estados</option>
                {Object.entries(cat.estados).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div className="envoltura-tabla">
              <table className="tabla-perfil">
                <thead><tr><th>Elemento (AGN)</th><th>Código del AGN</th><th>RiC-CM 1.0 y RiC-O 1.1</th><th>En RICORA</th><th>Estado</th></tr></thead>
                <tbody>
                  {filas.map((f) => (
                    <tr key={f.id}>
                      <td><strong>{f.elemento}</strong><div className="meta">{f.id} · {f.origen} · {f.entidad} · {f.obligatoriedad}</div>
                        {f.regla_agn && <div className="meta">{f.regla_agn}</div>}</td>
                      <td><code className={f.codigo_agn_correcto ? "" : "tachado"}>{f.codigo_agn}</code>
                        {!f.codigo_agn_correcto && <div className="meta">No corresponde a RiC-CM 1.0 / RiC-O 1.1</div>}</td>
                      <td>{f.ric_cm}<div><code>{f.ric_o.map((t) => `rico:${t}`).join(" · ") || "Sin término RiC-O"}</code></div></td>
                      <td>{f.campo}{f.nota && <div className="meta">{f.nota}</div>}</td>
                      <td><span className={`insignia ${CLASE_ESTADO[f.estado]}`}>{cat.estados[f.estado]}</span>
                        <div className="meta">{NIVEL_MADUREZ[f.nivel]}</div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {parte === "erratas" && (
        <div className="tarjeta">
          <div className="tarjeta-cab">Erratas del esquema del AGN, comprobadas contra el OWL oficial</div>
          <div className="envoltura-tabla">
            <table className="tabla-perfil">
              <thead><tr><th>Página</th><th>El esquema dice</th><th>Lo correcto</th></tr></thead>
              <tbody>{cat.erratas.map((e) => <tr key={e.pagina + e.dice}><td>{e.pagina}</td><td>{e.dice}</td><td>{e.correcto}</td></tr>)}</tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
