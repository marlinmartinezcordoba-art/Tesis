import { useEffect, useState, type FormEvent } from "react";
import { ErrorAPI, pedir } from "@/lib/api";

// Datos del original físico y completitud de la descripción. Las reglas son las del Esquema de
// Metadatos del AGN v1.4 (adaptación colombiana de RiC-CM), aplicadas como lógica del sistema.

export interface Proteccion {
  datos_personales: string | null;
  nota_accesibilidad: string | null;
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

// Completitud de la descripción en tres niveles (básico, intermedio, avanzado).
export function CompletitudDescripcion({ recursoId, version }: { recursoId: string; version: unknown }) {
  const [c, setC] = useState<CalidadAgn | null>(null);
  useEffect(() => {
    pedir<CalidadAgn>(`/api/calidad/descripciones/${recursoId}`).then(setC).catch(() => setC(null));
  }, [recursoId, version]);
  if (!c) return null;
  const faltan = c.criterios.filter((x) => x.aplica && !x.cumple);
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Completitud de la descripción</div>
      <div className="tarjeta-cuerpo">
        <div className="resumen-preservacion compacto">
          {Object.entries(c.por_nivel).map(([n, v]) => (
            <div key={n} className={`cifra ${v.porcentaje === 100 ? "bien" : v.porcentaje === null ? "" : "alerta"}`}>
              <strong>{v.porcentaje === null ? "—" : `${v.porcentaje} %`}</strong>
              <span>{NIVEL_MADUREZ[n]} · {v.cumplen} de {v.aplican} datos</span>
            </div>
          ))}
        </div>
        {c.incoherencias.map((t) => <div key={t} className="aviso error" role="alert" style={{ marginTop: 10 }}>{t}</div>)}
        {c.avisos.map((t) => <div key={t} className="aviso" style={{ marginTop: 10 }}>{t}</div>)}
        {faltan.length > 0 ? (
          <>
            <p className="meta" style={{ margin: "10px 0 4px" }}>Falta:</p>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {faltan.map((x) => <li key={x.clave}>{x.elemento} <span className="tenue">({NIVEL_MADUREZ[x.nivel].toLowerCase()})</span></li>)}
            </ul>
          </>
        ) : <p className="meta" style={{ marginBottom: 0 }}>Tiene todos los datos que se le pueden pedir.</p>}
      </div>
    </div>
  );
}

interface CompletitudDelFondo {
  descripciones: number; truncado: boolean;
  criterios: { clave: string; elemento: string; nivel: string; aplican: number; cumplen: number; porcentaje: number }[];
  nivel_alcanzado: Record<string, number>;
  incoherencias: { id: string; titulo: string; detalle: string[] }[];
  pendientes: { id: string; titulo: string; nivel: string; porcentaje: number }[];
}

// En el resumen del fondo: cuántas descripciones tienen los datos de cada nivel y qué falta más.
export function CompletitudFondo({ fondoId, abrir }: { fondoId: string; abrir: (id: string) => void }) {
  const [c, setC] = useState<CompletitudDelFondo | null>(null);
  useEffect(() => {
    setC(null);
    pedir<CompletitudDelFondo>(`/api/calidad/fondos/${fondoId}`).then(setC).catch(() => undefined);
  }, [fondoId]);
  if (!c || c.descripciones === 0) return null;
  const debiles = [...c.criterios].filter((x) => x.porcentaje < 100).sort((a, b) => a.porcentaje - b.porcentaje).slice(0, 6);
  return (
    <div className="tarjeta resumen-fondo">
      <div className="tarjeta-cab">Completitud de las descripciones ({c.descripciones})</div>
      <div className="tarjeta-cuerpo">
        <div className="resumen-preservacion compacto">
          {["basico", "intermedio", "avanzado", "ninguno"].map((n) => (
            <div key={n} className={`cifra ${n === "ninguno" && c.nivel_alcanzado[n] ? "alerta" : ""}`}>
              <strong>{c.nivel_alcanzado[n] ?? 0}</strong>
              <span>{n === "ninguno" ? "Les falta algún dato básico" : `Completas hasta el nivel ${NIVEL_MADUREZ[n].toLowerCase()}`}</span>
            </div>
          ))}
        </div>
        {c.incoherencias.map((x) => (
          <div key={x.id} className="aviso error" role="alert" style={{ marginTop: 10 }}>
            <button type="button" className="enlace" onClick={() => abrir(x.id)}>{x.titulo}</button>: {x.detalle.join(" ")}
          </div>
        ))}
        {debiles.length > 0 && (
          <div className="resumen-rejilla" style={{ marginTop: 10 }}>
            <div className="resumen-bloque">
              <h3>Lo que más falta</h3>
              <ul>{debiles.map((x) => <li key={x.clave}><span>{x.elemento}</span><span className="meta">{x.cumplen} de {x.aplican}</span></li>)}</ul>
            </div>
            <div className="resumen-bloque">
              <h3>Descripciones por completar</h3>
              <ul>{c.pendientes.slice(0, 6).map((p) => (
                <li key={p.id}><button type="button" className="enlace" onClick={() => abrir(p.id)}>{p.titulo}</button>
                  <span className="meta">{p.porcentaje} %</span></li>
              ))}</ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
