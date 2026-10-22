import { confirmar } from "@/lib/dialogos";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, descargar, pedir, subir } from "@/lib/api";
import { useSesion } from "@/lib/sesion";
import { Ventana } from "@/components/Ventana";
import { ResultadoValidacion, TablaVistaPrevia, type Validacion, type Vista } from "@/components/CuadroClasificacion";

// Parametrización de la TRD y el CCD en el orden de los SGDEA (Modelo de
// requisitos del AGN): versión de la TRD → dependencias → banco terminológico
// (series, subseries, tipos) → matriz por dependencia → aplicar, validado en
// RiC-O. Cada paso es una entrada del menú Fondos.

export interface VersionTrd {
  id: string; numero: number; nombre: string; acto_aprobacion: string | null; fecha_aprobacion: string | null;
  convalidacion: string | null; fecha_convalidacion: string | null; vigente_desde: string | null;
  ente_vigilancia?: string | null;
  vigente_hasta: string | null; estado: "borrador" | "vigente" | "historica" | "anulada"; observaciones: string | null;
  fondo_id: string;
  filas: number; editable: boolean;
}
interface Dependencia { id: string; codigo: string; nombre: string; superior_id: string | null; codigo_completo: string;
  nivel: "seccion" | "subseccion" }
interface Termino { id: string; clase: "serie" | "subserie" | "tipo_documental"; codigo: string | null; nombre: string;
  definicion: string | null; superior_id: string | null; superior: string | null; codigo_completo: string | null }
interface FilaTrd { id: string; dependencia_id: string; serie_id: string; subserie_id: string | null; tipos: string[];
  dependencia: string; codigo_dependencia: string | null; serie: string; subserie: string | null; codigo: string | null;
  nombres_tipos: string[]; gestion: number | null; central: number | null; disposicion: string | null;
  otras_disposiciones: string[]; soporte: string | null; procedimiento: string | null; funcion: string | null }
interface Aplicacion { aplicada: boolean; version: VersionTrd; validacion: Validacion;
  informe: { reglas: number; reglas_reemplazadas?: number; reglas_sin_cambio?: number; creados: Record<string, number>;
    avisos: string[]; faltan_para_aplicar?: string[]; series_sin_funcion?: string[] } }

const ESTADO: Record<VersionTrd["estado"], [string, string]> = {
  borrador: ["En borrador", "proceso"], vigente: ["Vigente", "bien"], historica: ["Histórica", "acento"],
  anulada: ["Anulada", "alerta"],
};
const DISP = [["ct", "CT", "Conservación total"], ["e", "E", "Eliminación"], ["s", "S", "Selección"],
  ["m", "M", "Medio técnico"]] as const;
const SOPORTE: Record<string, string> = { fisico: "Físico", electronico: "Electrónico", hibrido: "Híbrido" };

function mensaje(err: unknown, porDefecto: string) {
  return err instanceof ErrorAPI ? err.message : porDefecto;
}

function useAdmin() {
  return !!useSesion().usuario?.es_administrador;
}

function useLista<T>(ruta: string | null) {
  const [datos, setDatos] = useState<T[] | null>(null);
  const [error, setError] = useState("");
  const cargar = useCallback(() => {
    if (!ruta) return;
    pedir<T[]>(ruta).then(setDatos).catch((err) => setError(mensaje(err, "No se pudo cargar.")));
  }, [ruta]);
  useEffect(cargar, [cargar]);
  return { datos, error, cargar };
}

// El recorrido de la parametrización: todo parte de cargar los instrumentos; lo
// demás es revisar y ajustar a mano lo que la carga configuró, y aplicar.
// Aviso en las pantallas de ajuste: lo que se ve salió de la carga de los instrumentos.
function DesdeLaCarga() {
  return (
    <div className="aviso" role="note">
      Esto lo configura la carga del CCD y la TRD (<Link to="/fondos?vista=cargar">Cargar CCD y TRD</Link>). Aquí se
      revisa y se ajusta a mano lo que haga falta; los cambios valen al aplicar la versión.
    </div>
  );
}

// --- 1. Versiones ---------------------------------------------------------------------------------------

function FormVersion({ fondoId, version, hayVigente, alTerminar }: { fondoId: string; version: VersionTrd | null;
  hayVigente: boolean; alTerminar: () => void }) {
  const [d, setD] = useState({
    nombre: version?.nombre || "", acto_aprobacion: version?.acto_aprobacion || "",
    fecha_aprobacion: version?.fecha_aprobacion || "", convalidacion: version?.convalidacion || "",
    fecha_convalidacion: version?.fecha_convalidacion || "", vigente_desde: version?.vigente_desde || "",
    observaciones: version?.observaciones || "", ente_vigilancia: version?.ente_vigilancia || "",
  });
  const [copiar, setCopiar] = useState(true);
  const [error, setError] = useState("");
  const poner = (k: keyof typeof d) => (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value });

  async function guardar(e: FormEvent) {
    e.preventDefault();
    setError("");
    const cuerpo = Object.fromEntries(Object.entries(d).map(([k, v]) => [k, v.trim() || null]));
    try {
      if (version) await pedir(`/api/trd/versiones/${version.id}`, { method: "PATCH", body: JSON.stringify(cuerpo) });
      else await pedir("/api/trd/versiones", { method: "POST",
        body: JSON.stringify({ ...cuerpo, fondo_id: fondoId, copiar_vigente: copiar }) });
      alTerminar();
    } catch (err) {
      setError(mensaje(err, "No se pudo guardar."));
    }
  }

  const campo = (k: keyof typeof d, etiqueta: string, tipo = "text", pista?: string) => (
    <div className="campo">
      <label htmlFor={`v-${k}`}>{etiqueta}</label>
      <input id={`v-${k}`} className="entrada" type={tipo} value={d[k]} onChange={poner(k)} />
      {pista && <div className="pista">{pista}</div>}
    </div>
  );
  return (
    <form onSubmit={guardar}>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="rejilla">
        {campo("nombre", "Nombre", "text", "Si lo deja vacío: «TRD versión N».")}
        {campo("acto_aprobacion", "Acto administrativo que la aprueba", "text", "Por ejemplo «Resolución 045».")}
        {campo("fecha_aprobacion", "Fecha de aprobación", "date")}
        {campo("convalidacion", "Convalidación", "text", "Certificado del AGN o del consejo departamental.")}
        {campo("fecha_convalidacion", "Fecha de convalidación", "date")}
        {campo("vigente_desde", "Rige desde", "date", "Las reglas de retención valen desde este día.")}
        {campo("ente_vigilancia", "Ente que vigila su aplicación", "text",
               "El AGN o el consejo departamental de archivos (rico:isOrWasEnforcedBy). Queda en el vocabulario del fondo.")}
      </div>
      <div className="campo">
        <label htmlFor="v-obs">Observaciones</label>
        <textarea id="v-obs" className="entrada" rows={2} value={d.observaciones} onChange={poner("observaciones")} />
      </div>
      {!version && hayVigente && (
        <label className="meta"><input type="checkbox" checked={copiar} onChange={(e) => setCopiar(e.target.checked)} />
          {" "}Partir de la matriz de la TRD vigente (se cambian solo las series que cambian)</label>
      )}
      <div className="acciones">
        <button type="submit" className="boton primario">{version ? "Guardar" : "Abrir la versión en borrador"}</button>
      </div>
    </form>
  );
}

function CargarArchivo({ version, alTerminar }: { version: VersionTrd; alTerminar: (texto: string) => void }) {
  const [vista, setVista] = useState<Vista | null>(null);
  const [incluir, setIncluir] = useState<Set<number>>(new Set());
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");

  async function leer(archivo: File) {
    setError("");
    const datos = new FormData();
    datos.append("archivo", archivo, archivo.name);
    setOcupado(true);
    try {
      const v = await subir<Vista>("/api/cuadro/vista-previa", datos, () => undefined);
      setVista(v);
      setIncluir(new Set(v.filas.filter((f) => !f.problemas.length).map((f) => f.fila)));
    } catch (err) {
      setError(mensaje(err, "No se pudo leer el archivo."));
    } finally {
      setOcupado(false);
    }
  }

  async function agregar() {
    if (!vista) return;
    setOcupado(true);
    setError("");
    try {
      const r = await pedir<Record<string, number>>(`/api/trd/versiones/${version.id}/importar`, { method: "POST",
        body: JSON.stringify({ filas: vista.filas.filter((f) => incluir.has(f.fila)) }) });
      alTerminar(`Se agregaron ${r.filas} fila(s) a la matriz (${r.repetidas} ya estaban); al banco: ${r.series} serie(s), `
        + `${r.subseries} subserie(s), ${r.tipos_documentales} tipo(s) documental(es); ${r.dependencias} dependencia(s) nuevas.`);
    } catch (err) {
      setError(mensaje(err, "No se pudo agregar."));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <p className="meta" style={{ marginTop: 0 }}>
        La TRD en el formato de la entidad (Excel, PDF con texto, Word, CSV o un .zip): las columnas se reconocen por su nombre. Lo leído llena la matriz del borrador
        y el banco terminológico; nada se crea en el cuadro hasta que aplique la versión.
      </p>
      <div className="acciones">
        <button type="button" className="boton chico"
                onClick={() => descargar("/api/cuadro/plantilla").catch(() => undefined)}>Descargar la plantilla Excel</button>
        <label className="boton chico primario">
          {ocupado ? "Leyendo…" : "Leer un archivo"}
          <input type="file" accept=".xlsx,.xlsm,.pdf,.docx,.csv,.zip" hidden disabled={ocupado}
                 onChange={(e) => e.target.files?.[0] && leer(e.target.files[0])} />
        </label>
      </div>
      {vista && (
        <>
          <p className="meta">{vista.origen} · {vista.resumen.filas} fila(s), {vista.resumen.con_problemas} con problemas.</p>
          <div className="tabla-desplazable"><TablaVistaPrevia vista={vista} incluir={incluir} setIncluir={setIncluir} /></div>
          <div className="acciones">
            <button type="button" className="boton primario" disabled={ocupado || !incluir.size} onClick={agregar}>
              Agregar {incluir.size} fila(s) al borrador</button>
          </div>
        </>
      )}
    </>
  );
}

export function VersionesTrd({ fondoId }: { fondoId: string }) {
  const esAdmin = useAdmin();
  const { datos: versiones, error, cargar } = useLista<VersionTrd>(`/api/trd/versiones?fondo_id=${fondoId}`);
  const [formulario, setFormulario] = useState<VersionTrd | "nueva" | null>(null);
  const [cargando, setCargando] = useState<VersionTrd | null>(null);
  const [resultado, setResultado] = useState<Aplicacion | null>(null);
  const [aviso, setAviso] = useState("");
  const [fallo, setFallo] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const borrador = versiones?.find((v) => v.estado === "borrador") || null;
  const vigente = versiones?.find((v) => v.estado === "vigente") || null;

  async function probar(v: VersionTrd, crear: boolean) {
    setFallo("");
    setAviso("");
    setOcupado(true);
    try {
      const r = await pedir<Aplicacion>(`/api/trd/versiones/${v.id}/${crear ? "aplicar" : "validar"}`, { method: "POST" });
      setResultado(r);
      if (r.aplicada) cargar();
    } catch (err) {
      setFallo(mensaje(err, "No se pudo."));
    } finally {
      setOcupado(false);
    }
  }

  async function anular(v: VersionTrd) {
    if (!await confirmar(`¿Anular la ${v.nombre}? Queda registrada como anulada; no se borra.`)) return;
    try {
      await pedir(`/api/trd/versiones/${v.id}/anular`, { method: "POST", body: JSON.stringify({ motivo: null }) });
      setResultado(null);
      cargar();
    } catch (err) {
      setFallo(mensaje(err, "No se pudo anular."));
    }
  }

  return (
    <>
      <h1>Versiones de la TRD</h1>
      <p className="sub">
        Cada tabla de retención aprobada es una versión, con el acto que la aprueba, su convalidación y desde cuándo rige.
        Se trabaja en borrador (dependencias, series y matriz) y se aplica: entonces se arma el cuadro en RiC-O, se valida
        y queda vigente. La anterior pasa a histórica; nada se borra y cada expediente conserva la retención de la TRD con
        que se produjo.
      </p>
      {(error || fallo) && <div className="aviso error" role="alert">{error || fallo}</div>}
      {aviso && <div className="aviso bien" role="status">{aviso}</div>}
      {esAdmin && !borrador && versiones && (
        <div className="acciones">
          <button type="button" className="boton primario" onClick={() => setFormulario("nueva")}>
            + Abrir una versión nueva{vigente ? " (para modificar la TRD)" : ""}</button>
        </div>
      )}
      {borrador && (
        <div className="tarjeta">
          <div className="tarjeta-cab">{borrador.nombre} · en borrador</div>
          <div className="tarjeta-cuerpo">
            <p className="meta" style={{ marginTop: 0 }}>
              {borrador.filas} serie(s) o subserie(s) en la matriz. {borrador.acto_aprobacion
                ? `Aprobada por ${borrador.acto_aprobacion}${borrador.fecha_aprobacion ? ` del ${borrador.fecha_aprobacion}` : ""}.`
                : "Falta el acto administrativo que la aprueba."}{" "}
              {borrador.vigente_desde ? `Rige desde ${borrador.vigente_desde}.` : "Falta la fecha desde la que rige."}
            </p>
            {esAdmin && (
              <div className="acciones">
                <button type="button" className="boton chico" onClick={() => setFormulario(borrador)}>Datos de la versión</button>
                <button type="button" className="boton chico" onClick={() => setCargando(borrador)}>Cargar desde archivo</button>
                <button type="button" className="boton chico" disabled={ocupado} onClick={() => probar(borrador, false)}>
                  Validar en RiC-O</button>
                <button type="button" className="boton chico primario" disabled={ocupado || !resultado?.validacion.conforme
                  || resultado.version.id !== borrador.id || !!resultado.informe.faltan_para_aplicar?.length}
                        title="Primero valide en RiC-O y complete el acto y la vigencia" onClick={() => probar(borrador, true)}>
                  Aplicar la versión</button>
                <button type="button" className="boton chico" onClick={() => anular(borrador)}>Anular el borrador</button>
              </div>
            )}
          </div>
        </div>
      )}
      {resultado && (
        <div className="tarjeta">
          <div className="tarjeta-cab">{resultado.aplicada ? `${resultado.version.nombre} aplicada: vigente` : "Validación"}</div>
          <div className="tarjeta-cuerpo">
            <ResultadoValidacion v={resultado.validacion} />
            <p className="meta">
              {resultado.aplicada ? "Se crearon" : "Se crearían"}: {Object.entries(resultado.informe.creados)
                .map(([k, n]) => `${n} ${k}`).join(", ") || "ningún nivel nuevo"}; {resultado.informe.reglas} regla(s) de
              retención nuevas{resultado.informe.reglas_reemplazadas
                ? `, ${resultado.informe.reglas_reemplazadas} reemplazan a la de la versión anterior (que se conserva con su vigencia)` : ""}
              {resultado.informe.reglas_sin_cambio ? `; ${resultado.informe.reglas_sin_cambio} sin cambio` : ""}.
            </p>
            {!!resultado.informe.faltan_para_aplicar?.length && (
              <div className="aviso alerta">Para aplicarla falta {resultado.informe.faltan_para_aplicar.join(", ")}
                {" "}(Datos de la versión).</div>
            )}
            {!!resultado.informe.series_sin_funcion?.length && (
              <div className="aviso alerta">
                {resultado.informe.series_sin_funcion.length} serie(s) o subserie(s) sin la función que las produce. En RiC
                una serie existe porque una actividad la produce: asígnela en la Matriz de la TRD (no es obligatorio).
                <details><summary className="meta">Cuáles</summary>
                  <ul className="meta">{resultado.informe.series_sin_funcion.map((x) => <li key={x}>{x}</li>)}</ul></details>
              </div>
            )}
            {resultado.informe.avisos.length > 0 && <ul>{resultado.informe.avisos.map((a) => <li key={a}>{a}</li>)}</ul>}
          </div>
        </div>
      )}
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Todas las versiones</div>
        {!versiones ? <div className="cargando">Cargando…</div> : versiones.length === 0 ? (
          <p className="meta" style={{ padding: "0 18px" }}>Este fondo todavía no tiene TRD parametrizada.</p>
        ) : (
          <table className="tabla-permisos">
            <thead><tr><th>Versión</th><th>Acto de aprobación</th><th>Convalidación</th><th>Vigencia</th>
              <th>Series</th><th>Estado</th></tr></thead>
            <tbody>
              {versiones.map((v) => (
                <tr key={v.id}>
                  <td><strong>{v.nombre}</strong></td>
                  <td>{v.acto_aprobacion || "—"}{v.fecha_aprobacion && <div className="meta">{v.fecha_aprobacion}</div>}</td>
                  <td>{v.convalidacion || "—"}{v.fecha_convalidacion && <div className="meta">{v.fecha_convalidacion}</div>}</td>
                  <td>{v.vigente_desde ? `${v.vigente_desde} a ${v.vigente_hasta || "hoy"}` : "—"}</td>
                  <td>{v.filas}</td>
                  <td><span className={`insignia ${ESTADO[v.estado][1]}`}>{ESTADO[v.estado][0]}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {formulario && (
        <Ventana titulo={formulario === "nueva" ? "Abrir una versión de la TRD" : `Datos de la ${formulario.nombre}`}
                 alCerrar={() => setFormulario(null)} ancha>
          <FormVersion fondoId={fondoId} version={formulario === "nueva" ? null : formulario} hayVigente={!!vigente}
                       alTerminar={() => { setFormulario(null); setResultado(null); cargar(); }} />
        </Ventana>
      )}
      {cargando && (
        <Ventana titulo={`Cargar la TRD desde un archivo · ${cargando.nombre}`} alCerrar={() => setCargando(null)} ancha>
          <CargarArchivo version={cargando} alTerminar={(t) => { setCargando(null); setAviso(t); setResultado(null); cargar(); }} />
        </Ventana>
      )}
    </>
  );
}

// --- 2. Dependencias ------------------------------------------------------------------------------------

function FormDependencia({ fondoId, dep, secciones, alTerminar }: { fondoId: string; dep: Dependencia | null;
  secciones: Dependencia[]; alTerminar: () => void }) {
  const [codigo, setCodigo] = useState(dep?.codigo || "");
  const [nombre, setNombre] = useState(dep?.nombre || "");
  const [superior, setSuperior] = useState(dep?.superior_id || "");
  const [error, setError] = useState("");
  async function guardar(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      if (dep) await pedir(`/api/trd/dependencias/${dep.id}`, { method: "PATCH", body: JSON.stringify({ codigo, nombre }) });
      else await pedir("/api/trd/dependencias", { method: "POST",
        body: JSON.stringify({ fondo_id: fondoId, codigo, nombre, superior_id: superior || null }) });
      alTerminar();
    } catch (err) {
      setError(mensaje(err, "No se pudo guardar."));
    }
  }
  return (
    <form onSubmit={guardar}>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="rejilla">
        {!dep && (
          <div className="campo">
            <label htmlFor="d-sup">Es</label>
            <select id="d-sup" className="selector" value={superior} onChange={(e) => setSuperior(e.target.value)}>
              <option value="">Una sección (dependencia productora)</option>
              {secciones.map((s) => <option key={s.id} value={s.id}>Una subsección de {s.codigo} {s.nombre}</option>)}
            </select>
          </div>
        )}
        <div className="campo">
          <label htmlFor="d-cod">Código</label>
          <input id="d-cod" className="entrada" required value={codigo} onChange={(e) => setCodigo(e.target.value)} />
          <div className="pista">El de la dependencia en el organigrama (por ejemplo 100 o 110).</div>
        </div>
        <div className="campo">
          <label htmlFor="d-nom">Nombre</label>
          <input id="d-nom" className="entrada" required value={nombre} onChange={(e) => setNombre(e.target.value)} />
        </div>
      </div>
      <div className="acciones"><button type="submit" className="boton primario">Guardar</button></div>
    </form>
  );
}

export function DependenciasTrd({ fondoId }: { fondoId: string }) {
  const esAdmin = useAdmin();
  const { datos, error, cargar } = useLista<Dependencia>(`/api/trd/dependencias?fondo_id=${fondoId}`);
  const [form, setForm] = useState<Dependencia | "nueva" | null>(null);
  const [fallo, setFallo] = useState("");
  const secciones = (datos || []).filter((d) => d.nivel === "seccion");

  async function anular(d: Dependencia) {
    if (!await confirmar(`¿Anular ${d.codigo} ${d.nombre}? Queda registrada como anulada; no se borra.`)) return;
    setFallo("");
    try {
      await pedir(`/api/trd/dependencias/${d.id}/anular`, { method: "POST" });
      cargar();
    } catch (err) {
      setFallo(mensaje(err, "No se pudo anular."));
    }
  }

  return (
    <>
      <h1>Dependencias productoras</h1>
      <p className="sub">
        Las secciones (dependencias) y subsecciones (oficinas) que producen los documentos, con el código del organigrama.
        Al aplicar la TRD cada una es una sección del cuadro (rico:RecordSet) y la dependencia es su productor
        (rico:CorporateBody). Su código encabeza el de sus series: la serie 2 de la dependencia 110 es la 110.2.
      </p>
      <DesdeLaCarga />
      {(error || fallo) && <div className="aviso error" role="alert">{error || fallo}</div>}
      {esAdmin && <div className="acciones"><button type="button" className="boton primario" onClick={() => setForm("nueva")}>
        + Registrar una dependencia</button></div>}
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Dependencias</div>
        {!datos ? <div className="cargando">Cargando…</div> : datos.length === 0 ? (
          <p className="meta" style={{ padding: "0 18px" }}>Todavía no hay dependencias. Regístrelas o cárguelas con la TRD
            desde un archivo (Versiones de la TRD).</p>
        ) : (
          <table className="tabla-permisos">
            <thead><tr><th>Código</th><th>Dependencia</th><th>Nivel</th>{esAdmin && <th />}</tr></thead>
            <tbody>
              {secciones.flatMap((s) => [s, ...datos.filter((d) => d.superior_id === s.id)]).map((d) => (
                <tr key={d.id}>
                  <td><strong>{d.codigo_completo}</strong></td>
                  <td style={{ paddingLeft: d.superior_id ? 28 : undefined }}>{d.nombre}</td>
                  <td>{d.nivel === "seccion" ? "Sección" : "Subsección"}</td>
                  {esAdmin && <td><button type="button" className="boton chico" onClick={() => setForm(d)}>Corregir</button>
                    {" "}<button type="button" className="boton chico" onClick={() => anular(d)}>Anular</button></td>}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {form && (
        <Ventana titulo={form === "nueva" ? "Registrar una dependencia" : `Corregir ${form.nombre}`} alCerrar={() => setForm(null)}>
          <FormDependencia fondoId={fondoId} dep={form === "nueva" ? null : form} secciones={secciones}
                           alTerminar={() => { setForm(null); cargar(); }} />
        </Ventana>
      )}
    </>
  );
}

// --- 3. Banco terminológico -----------------------------------------------------------------------------

function FormTermino({ fondoId, termino, clase, series, alTerminar }: { fondoId: string; termino: Termino | null;
  clase: Termino["clase"]; series: Termino[]; alTerminar: () => void }) {
  const [codigo, setCodigo] = useState(termino?.codigo || "");
  const [nombre, setNombre] = useState(termino?.nombre || "");
  const [definicion, setDefinicion] = useState(termino?.definicion || "");
  const [superior, setSuperior] = useState(termino?.superior_id || series[0]?.id || "");
  const [error, setError] = useState("");
  async function guardar(e: FormEvent) {
    e.preventDefault();
    setError("");
    const cuerpo = { codigo: codigo.trim() || null, nombre, definicion: definicion.trim() || null };
    try {
      if (termino) await pedir(`/api/trd/banco/${termino.id}`, { method: "PATCH", body: JSON.stringify(cuerpo) });
      else await pedir("/api/trd/banco", { method: "POST", body: JSON.stringify({ ...cuerpo, fondo_id: fondoId, clase,
        superior_id: clase === "subserie" ? superior : null }) });
      alTerminar();
    } catch (err) {
      setError(mensaje(err, "No se pudo guardar."));
    }
  }
  return (
    <form onSubmit={guardar}>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="rejilla">
        {clase === "subserie" && !termino && (
          <div className="campo">
            <label htmlFor="b-sup">Serie</label>
            <select id="b-sup" className="selector" value={superior} onChange={(e) => setSuperior(e.target.value)}>
              {series.map((s) => <option key={s.id} value={s.id}>{s.codigo} {s.nombre}</option>)}
            </select>
          </div>
        )}
        {clase !== "tipo_documental" && (
          <div className="campo">
            <label htmlFor="b-cod">Código</label>
            <input id="b-cod" className="entrada" required value={codigo} onChange={(e) => setCodigo(e.target.value)} />
            <div className="pista">Solo el propio (2, o 1 en una subserie): el de la dependencia se antepone solo.</div>
          </div>
        )}
        <div className="campo">
          <label htmlFor="b-nom">Nombre</label>
          <input id="b-nom" className="entrada" required value={nombre} onChange={(e) => setNombre(e.target.value)} />
        </div>
      </div>
      <div className="campo">
        <label htmlFor="b-def">Definición</label>
        <textarea id="b-def" className="entrada" rows={3} value={definicion} onChange={(e) => setDefinicion(e.target.value)} />
        <div className="pista">Qué agrupa y para qué se produce: es la nota de alcance del banco terminológico.</div>
      </div>
      <div className="acciones"><button type="submit" className="boton primario">Guardar</button></div>
    </form>
  );
}

export function BancoTrd({ fondoId }: { fondoId: string }) {
  const esAdmin = useAdmin();
  const { datos, error, cargar } = useLista<Termino>(`/api/trd/banco?fondo_id=${fondoId}`);
  const [form, setForm] = useState<{ clase: Termino["clase"]; termino: Termino | null } | null>(null);
  const [fallo, setFallo] = useState("");
  const series = (datos || []).filter((t) => t.clase === "serie");
  const tipos = (datos || []).filter((t) => t.clase === "tipo_documental");

  async function anular(t: Termino) {
    if (!await confirmar(`¿Anular «${t.nombre}»? Queda registrado como anulado; no se borra.`)) return;
    setFallo("");
    try {
      await pedir(`/api/trd/banco/${t.id}/anular`, { method: "POST" });
      cargar();
    } catch (err) {
      setFallo(mensaje(err, "No se pudo anular."));
    }
  }

  const botones = (t: Termino) => esAdmin && (
    <td><button type="button" className="boton chico" onClick={() => setForm({ clase: t.clase, termino: t })}>Corregir</button>
      {" "}<button type="button" className="boton chico" onClick={() => anular(t)}>Anular</button></td>
  );

  return (
    <>
      <h1>Series, subseries y tipos documentales</h1>
      <p className="sub">
        El banco terminológico del fondo: los nombres normalizados de las series, subseries y tipos documentales, con su
        código y su definición. Se registran una vez y la matriz de la TRD los usa en cada dependencia. Al aplicar, cada
        serie y subserie es un rico:RecordSet del cuadro y cada tipo documental un rico:DocumentaryFormType.
      </p>
      <DesdeLaCarga />
      {(error || fallo) && <div className="aviso error" role="alert">{error || fallo}</div>}
      {esAdmin && (
        <div className="acciones">
          <button type="button" className="boton primario" onClick={() => setForm({ clase: "serie", termino: null })}>+ Serie</button>
          <button type="button" className="boton" disabled={!series.length}
                  onClick={() => setForm({ clase: "subserie", termino: null })}>+ Subserie</button>
          <button type="button" className="boton" onClick={() => setForm({ clase: "tipo_documental", termino: null })}>
            + Tipo documental</button>
        </div>
      )}
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Series y subseries</div>
        {!datos ? <div className="cargando">Cargando…</div> : series.length === 0 ? (
          <p className="meta" style={{ padding: "0 18px" }}>Todavía no hay series en el banco.</p>
        ) : (
          <table className="tabla-permisos">
            <thead><tr><th>Código</th><th>Nombre</th><th>Definición</th>{esAdmin && <th />}</tr></thead>
            <tbody>
              {series.flatMap((s) => [s, ...datos.filter((t) => t.superior_id === s.id)]).map((t) => (
                <tr key={t.id}>
                  <td><strong>{t.codigo_completo}</strong></td>
                  <td style={{ paddingLeft: t.superior_id ? 28 : undefined }}>
                    {t.clase === "subserie" && <span className="meta">Subserie · </span>}{t.nombre}</td>
                  <td className="meta">{t.definicion || "—"}</td>
                  {botones(t)}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="tarjeta tabla-desplazable">
        <div className="tarjeta-cab">Tipos documentales</div>
        {datos && tipos.length === 0 ? <p className="meta" style={{ padding: "0 18px" }}>Todavía no hay tipos documentales.</p> : (
          <table className="tabla-permisos">
            <thead><tr><th>Tipo documental</th><th>Definición</th>{esAdmin && <th />}</tr></thead>
            <tbody>{tipos.map((t) => <tr key={t.id}><td>{t.nombre}</td><td className="meta">{t.definicion || "—"}</td>{botones(t)}</tr>)}</tbody>
          </table>
        )}
      </div>
      {form && (
        <Ventana titulo={`${form.termino ? "Corregir" : "Registrar"} ${{ serie: "una serie", subserie: "una subserie",
          tipo_documental: "un tipo documental" }[form.clase]}`} alCerrar={() => setForm(null)}>
          <FormTermino fondoId={fondoId} termino={form.termino} clase={form.clase} series={series}
                       alTerminar={() => { setForm(null); cargar(); }} />
        </Ventana>
      )}
    </>
  );
}

// --- 4. Matriz ------------------------------------------------------------------------------------------

function FormFila({ version, fila, deps, banco, alTerminar }: { version: VersionTrd; fila: FilaTrd | null;
  deps: Dependencia[]; banco: Termino[]; alTerminar: () => void }) {
  const series = banco.filter((t) => t.clase === "serie");
  const [d, setD] = useState({
    dependencia_id: fila?.dependencia_id || deps[0]?.id || "", serie_id: fila?.serie_id || series[0]?.id || "",
    subserie_id: fila?.subserie_id || "", gestion: fila?.gestion?.toString() ?? "", central: fila?.central?.toString() ?? "",
    disposicion: fila?.disposicion || "", soporte: fila?.soporte || "", procedimiento: fila?.procedimiento || "",
    funcion: fila?.funcion || "",
  });
  const [tipos, setTipos] = useState<Set<string>>(new Set(fila?.tipos || []));
  const [otras, setOtras] = useState<Set<string>>(new Set(fila?.otras_disposiciones || []));
  const [filtro, setFiltro] = useState("");
  const [error, setError] = useState("");
  const [funciones, setFunciones] = useState<string[]>([]);
  useEffect(() => {
    pedir<{ nombre: string }[]>(`/api/vocabulario?fondo_id=${version.fondo_id}&clase=tipo_actividad`)
      .then((l) => setFunciones(l.map((x) => x.nombre))).catch(() => setFunciones([]));
  }, [version.fondo_id]);
  const subseries = banco.filter((t) => t.clase === "subserie" && t.superior_id === d.serie_id);
  const todosTipos = banco.filter((t) => t.clase === "tipo_documental");
  const visibles = todosTipos.filter((t) => tipos.has(t.id) || t.nombre.toLowerCase().includes(filtro.toLowerCase()));
  const poner = (k: keyof typeof d) => (e: { target: { value: string } }) =>
    setD({ ...d, [k]: e.target.value, ...(k === "serie_id" ? { subserie_id: "" } : {}) });
  const alternar = (s: Set<string>, set: (x: Set<string>) => void, id: string) => {
    const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); set(n);
  };

  async function guardar(e: FormEvent) {
    e.preventDefault();
    setError("");
    const numero = (x: string) => (x.trim() === "" ? null : Number(x));
    const cuerpo = { dependencia_id: d.dependencia_id, serie_id: d.serie_id, subserie_id: d.subserie_id || null,
      tipos: [...tipos], gestion: numero(d.gestion), central: numero(d.central), disposicion: d.disposicion || null,
      otras_disposiciones: [...otras].filter((x) => x !== d.disposicion), soporte: d.soporte || null,
      procedimiento: d.procedimiento.trim() || null, funcion: d.funcion.trim() || null };
    try {
      if (fila) await pedir(`/api/trd/filas/${fila.id}`, { method: "PUT", body: JSON.stringify(cuerpo) });
      else await pedir(`/api/trd/versiones/${version.id}/filas`, { method: "POST", body: JSON.stringify(cuerpo) });
      alTerminar();
    } catch (err) {
      setError(mensaje(err, "No se pudo guardar."));
    }
  }

  return (
    <form onSubmit={guardar}>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="rejilla">
        <div className="campo">
          <label htmlFor="f-dep">Dependencia productora</label>
          <select id="f-dep" className="selector" value={d.dependencia_id} onChange={poner("dependencia_id")}>
            {deps.map((x) => <option key={x.id} value={x.id}>{x.codigo_completo} {x.nombre}</option>)}
          </select>
        </div>
        <div className="campo">
          <label htmlFor="f-serie">Serie</label>
          <select id="f-serie" className="selector" value={d.serie_id} onChange={poner("serie_id")}>
            {series.map((x) => <option key={x.id} value={x.id}>{x.codigo} {x.nombre}</option>)}
          </select>
        </div>
        <div className="campo">
          <label htmlFor="f-sub">Subserie</label>
          <select id="f-sub" className="selector" value={d.subserie_id} onChange={poner("subserie_id")}>
            <option value="">(la serie, sin subserie)</option>
            {subseries.map((x) => <option key={x.id} value={x.id}>{x.codigo_completo} {x.nombre}</option>)}
          </select>
        </div>
        <div className="campo">
          <label htmlFor="f-ag">Retención en archivo de gestión (años)</label>
          <input id="f-ag" className="entrada" type="number" min={0} max={100} value={d.gestion} onChange={poner("gestion")} />
        </div>
        <div className="campo">
          <label htmlFor="f-ac">Retención en archivo central (años)</label>
          <input id="f-ac" className="entrada" type="number" min={0} max={100} value={d.central} onChange={poner("central")} />
        </div>
        <div className="campo">
          <label htmlFor="f-sop">Soporte</label>
          <select id="f-sop" className="selector" value={d.soporte} onChange={poner("soporte")}>
            <option value="">—</option>
            {Object.entries(SOPORTE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
      </div>
      <fieldset className="campo">
        <legend>Disposición final</legend>
        {DISP.map(([k, sigla, nombre]) => (
          <label key={k} className="opcion">
            <input type="radio" name="disp" checked={d.disposicion === k} onChange={() => setD({ ...d, disposicion: k })} />
            {" "}{sigla} · {nombre}
          </label>
        ))}
        <div className="pista">La principal. Si además aplica otra (por ejemplo CT y M), márquela aquí:{" "}
          {DISP.filter(([k]) => k !== d.disposicion).map(([k, sigla]) => (
            <label key={k} className="opcion">
              <input type="checkbox" checked={otras.has(k)} onChange={() => alternar(otras, setOtras, k)} /> {sigla}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="campo">
        <legend>Tipos documentales ({tipos.size})</legend>
        <input className="entrada" placeholder="Filtrar los tipos del banco…" value={filtro}
               onChange={(e) => setFiltro(e.target.value)} aria-label="Filtrar los tipos documentales" />
        <div style={{ maxHeight: 160, overflowY: "auto", marginTop: 6 }}>
          {visibles.map((t) => (
            <label key={t.id} className="opcion bloque">
              <input type="checkbox" checked={tipos.has(t.id)} onChange={() => alternar(tipos, setTipos, t.id)} /> {t.nombre}
            </label>
          ))}
          {!todosTipos.length && <span className="meta">Registre los tipos en Series, subseries y tipos.</span>}
        </div>
      </fieldset>
      <div className="campo">
        <label htmlFor="f-proc">Procedimiento</label>
        <textarea id="f-proc" className="entrada" rows={3} value={d.procedimiento} onChange={poner("procedimiento")} />
      </div>
      <div className="campo">
        <label htmlFor="f-fun">Función que produce la serie</label>
        <input id="f-fun" className="entrada" list="funciones-fondo" value={d.funcion} onChange={poner("funcion")} />
        <datalist id="funciones-fondo">{funciones.map((n) => <option key={n} value={n} />)}</datalist>
        <div className="pista">En RiC la serie existe porque una actividad la produce (rico:ActivityType). Sale del manual
          de funciones; elija una ya registrada o escriba una nueva.</div>
      </div>
      <div className="acciones"><button type="submit" className="boton primario">Guardar</button></div>
    </form>
  );
}

export function MatrizTrd({ fondoId }: { fondoId: string }) {
  const esAdmin = useAdmin();
  const versiones = useLista<VersionTrd>(`/api/trd/versiones?fondo_id=${fondoId}`);
  const deps = useLista<Dependencia>(`/api/trd/dependencias?fondo_id=${fondoId}`);
  const banco = useLista<Termino>(`/api/trd/banco?fondo_id=${fondoId}`);
  const visibles = useMemo(() => (versiones.datos || []).filter((v) => v.estado !== "anulada"), [versiones.datos]);
  const [elegida, setElegida] = useState("");
  const version = visibles.find((v) => v.id === elegida) || visibles.find((v) => v.estado === "borrador")
    || visibles.find((v) => v.estado === "vigente") || visibles[0] || null;
  const filas = useLista<FilaTrd>(version ? `/api/trd/versiones/${version.id}/filas` : null);
  const [form, setForm] = useState<FilaTrd | "nueva" | null>(null);
  const [fallo, setFallo] = useState("");
  const editable = esAdmin && !!version?.editable;

  async function quitar(f: FilaTrd) {
    if (!await confirmar(`¿Quitar ${f.codigo} ${f.subserie || f.serie} de la matriz del borrador?`)) return;
    setFallo("");
    try {
      await pedir(`/api/trd/filas/${f.id}/anular`, { method: "POST" });
      filas.cargar();
    } catch (err) {
      setFallo(mensaje(err, "No se pudo quitar."));
    }
  }

  const porDependencia = useMemo(() => {
    const grupos = new Map<string, FilaTrd[]>();
    for (const f of filas.datos || []) {
      const clave = `${f.codigo_dependencia || ""} ${f.dependencia}`;
      grupos.set(clave, [...(grupos.get(clave) || []), f]);
    }
    return [...grupos.entries()];
  }, [filas.datos]);

  return (
    <>
      <h1>Matriz de la TRD</h1>
      <p className="sub">
        La tabla de retención por dependencia: cada serie o subserie con sus tipos documentales, cuántos años en el archivo
        de gestión (AG) y en el central (AC), la disposición final, el soporte y el procedimiento. Se edita solo en una
        versión en borrador; la vigente y las históricas se consultan.
      </p>
      <DesdeLaCarga />
      {(versiones.error || filas.error || fallo) && (
        <div className="aviso error" role="alert">{versiones.error || filas.error || fallo}</div>
      )}
      {versiones.datos && !visibles.length ? (
        <div className="vacio">Abra primero una versión de la TRD (Versiones de la TRD).</div>
      ) : (
        <>
          <div className="acciones">
            <label className="meta" htmlFor="m-version">Versión</label>
            <select id="m-version" className="selector" value={version?.id || ""} onChange={(e) => setElegida(e.target.value)}>
              {visibles.map((v) => <option key={v.id} value={v.id}>{v.nombre} · {ESTADO[v.estado][0].toLowerCase()}</option>)}
            </select>
            {editable && (
              <button type="button" className="boton primario" disabled={!deps.datos?.length || !banco.datos?.some((t) => t.clase === "serie")}
                      title="Necesita al menos una dependencia y una serie" onClick={() => setForm("nueva")}>
                + Agregar una serie o subserie</button>
            )}
          </div>
          {version && !version.editable && esAdmin && (
            <p className="meta">Esta versión no se edita ({ESTADO[version.estado][0].toLowerCase()}). Para cambiarla, abra una
              versión nueva en Versiones de la TRD: parte de esta matriz.</p>
          )}
          <div className="tarjeta tabla-desplazable">
            <div className="tarjeta-cab">{version?.nombre}</div>
            {!filas.datos ? <div className="cargando">Cargando…</div> : filas.datos.length === 0 ? (
              <p className="meta" style={{ padding: "0 18px" }}>La matriz está vacía.</p>
            ) : (
              <table className="tabla-permisos">
                <thead><tr><th>Código</th><th>Serie / subserie y tipos documentales</th><th>AG</th><th>AC</th>
                  <th>Disposición</th><th>Soporte</th><th>Función que la produce</th><th>Procedimiento</th>
                  {editable && <th />}</tr></thead>
                <tbody>
                  {porDependencia.flatMap(([dep, lista]) => [
                    <tr key={dep}><td colSpan={editable ? 9 : 8}><strong>{dep}</strong></td></tr>,
                    ...lista.map((f) => (
                      <tr key={f.id}>
                        <td><strong>{f.codigo}</strong></td>
                        <td>{f.serie}{f.subserie && <> › {f.subserie}</>}
                          {f.nombres_tipos.length > 0 && <div className="meta">{f.nombres_tipos.join("; ")}</div>}</td>
                        <td>{f.gestion ?? "—"}</td>
                        <td>{f.central ?? "—"}</td>
                        <td>{f.disposicion ? [f.disposicion, ...f.otras_disposiciones].map((x) => x.toUpperCase()).join(" + ") : "—"}</td>
                        <td>{f.soporte ? SOPORTE[f.soporte] : "—"}</td>
                        <td>{f.funcion || <span className="insignia alerta" title="En RiC una serie existe porque una actividad la produce">sin función</span>}</td>
                        <td className="meta">{f.procedimiento || "—"}</td>
                        {editable && <td><button type="button" className="boton chico" onClick={() => setForm(f)}>Corregir</button>
                          {" "}<button type="button" className="boton chico" onClick={() => quitar(f)}>Quitar</button></td>}
                      </tr>
                    )),
                  ])}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
      {form && version && deps.datos && banco.datos && (
        <Ventana titulo={form === "nueva" ? "Agregar a la matriz" : `Corregir ${form.codigo}`} alCerrar={() => setForm(null)} ancha>
          <FormFila version={version} fila={form === "nueva" ? null : form} deps={deps.datos} banco={banco.datos}
                    alTerminar={() => { setForm(null); filas.cargar(); versiones.cargar(); }} />
        </Ventana>
      )}
    </>
  );
}
