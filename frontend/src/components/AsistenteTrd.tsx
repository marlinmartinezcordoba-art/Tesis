import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ErrorAPI, descargar, pedir, subir } from "@/lib/api";
import { confirmar } from "@/lib/dialogos";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";
import { ResultadoValidacion, TablaVistaPrevia, type Vista } from "@/components/CuadroClasificacion";
import {
  BancoTrd, DependenciasTrd, FormVersion, MatrizTrd, type Aplicacion, type VersionTrd,
} from "@/components/ParametrizacionTrd";
import { ImportarRico } from "@/components/ImportarRico";
import { ComparacionTrd } from "@/components/ComparacionTrd";
import { CotejoCcd } from "@/components/CotejoCcd";
import { RegistrarFondo } from "@/components/RegistrarFondo";
import { Ventana } from "@/components/Ventana";

// La TRD del fondo, paso a paso (decisión de la autora: pasos guiados). Arriba, lo que rige
// y lo que se prepara; debajo, cuatro pasos con su estado y un solo botón para seguir:
// 1. subir el archivo, 2. revisar lo que el sistema leyó, 3. corregir (opcional),
// 4. aprobar y poner a regir. Crear un fondo e importar de otro sistema van aparte, abajo.

type EstadoPaso = "hecho" | "ahora" | "opcional" | "pendiente";

function Paso({ n, titulo, estado, children, resumen }: {
  n: number; titulo: string; estado: EstadoPaso; children?: ReactNode; resumen?: ReactNode;
}) {
  return (
    <li className={`paso paso-${estado}`} aria-current={estado === "ahora" ? "step" : undefined}>
      <div className="paso-marca" aria-hidden="true">{estado === "hecho" ? "✓" : n}</div>
      <div className="paso-cuerpo">
        <div className="paso-titulo">
          <strong>{n}. {titulo}</strong>
          <span className={`insignia ${estado === "hecho" ? "bien" : estado === "ahora" ? "acento" : "proceso"}`}>
            {{ hecho: "Hecho", ahora: "Ahora", opcional: "Opcional", pendiente: "Pendiente" }[estado]}</span>
        </div>
        {resumen && <div className="meta">{resumen}</div>}
        {estado !== "pendiente" && children}
      </div>
    </li>
  );
}

interface Carga { id: string; archivo: string; huella: string; filas_cargadas: number; cargado_en: string }

function Originales({ versionId }: { versionId: string }) {
  const [cargas, setCargas] = useState<Carga[]>([]);
  useEffect(() => { pedir<Carga[]>(`/api/trd/versiones/${versionId}/cargas`).then(setCargas).catch(() => setCargas([])); }, [versionId]);
  if (!cargas.length) return null;
  return (
    <ul className="meta" style={{ margin: "4px 0 0" }}>
      {cargas.map((c) => (
        <li key={c.id}>Archivo original: <button type="button" className="enlace"
          onClick={() => descargar(`/api/trd/cargas/${c.id}/archivo`).catch(() => undefined)}>{c.archivo}</button>
          {" "}· {c.filas_cargadas} fila(s) · huella SHA-256 <code title={c.huella}>{c.huella.slice(0, 12)}…</code></li>
      ))}
    </ul>
  );
}

// Un .zip puede traer varios instrumentos (requisito 3): el sistema sugiere qué es cada archivo
// y la persona lo confirma. La TRD llena la versión, la TVD su propio borrador y el CCD se coteja.
type Rol = "trd" | "ccd" | "tvd" | "omitir";
interface Parte { archivo: string; filas: number; con_problemas: number; con_retencion: number; sugerido: Rol }
type VistaPaquete = Vista & { partes?: Parte[]; original?: { huella: string; archivo: string } };
const ROL_NOMBRE: Record<Rol, string> = { trd: "TRD (llena la versión)", ccd: "CCD (se coteja con la TRD)",
  tvd: "TVD (abre su propio borrador)", omitir: "No usar" };

function Subir({ fondoId, versionTrdId, alTerminar }: { fondoId: string; versionTrdId: string | null; alTerminar: () => void }) {
  const [vista, setVista] = useState<VistaPaquete | null>(null);
  const [roles, setRoles] = useState<Record<string, Rol>>({});
  const [incluir, setIncluir] = useState<Set<number>>(new Set());
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");

  async function leer(archivo: File) {
    setError("");
    const datos = new FormData();
    datos.append("archivo", archivo, archivo.name);
    setOcupado(true);
    try {
      const v = await subir<VistaPaquete>("/api/cuadro/vista-previa", datos, () => undefined);
      setVista(v);
      setRoles(Object.fromEntries((v.partes || []).map((x) => [x.archivo, x.sugerido])));
      setIncluir(new Set(v.filas.filter((f) => !f.problemas.length).map((f) => f.fila)));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo leer el archivo.");
    } finally {
      setOcupado(false);
    }
  }

  async function guardar() {
    if (!vista) return;
    setOcupado(true);
    setError("");
    try {
      // El archivo tal como llegó queda guardado con su huella y cada fila dice de dónde salió.
      const original = vista.original ? { huella: vista.original.huella, archivo: vista.original.archivo, origen: vista.origen } : null;
      const cargar = (filas: unknown[], instrumento: "trd" | "tvd") => pedir<{ version: { id: string } }>("/api/trd/cargar", {
        method: "POST", body: JSON.stringify({ fondo_id: fondoId, instrumento, filas, original }) });
      if (paquete) {
        const de = (rol: Rol) => vista.filas.filter((f) => roles[(f as { parte?: string }).parte || ""] === rol && !f.problemas.length);
        if (Object.values(roles).filter((r) => r === "tvd").length > 1) {
          throw new ErrorAPI(422, "Marque una sola TVD por paquete: cada TVD es un periodo y se carga en su propio borrador.");
        }
        let versionId = versionTrdId;
        if (de("trd").length) versionId = (await cargar(de("trd"), "trd")).version.id;
        if (de("tvd").length) await cargar(de("tvd"), "tvd");
        if (de("ccd").length) {
          if (!versionId) throw new ErrorAPI(422, "Para cotejar el CCD hace falta una TRD: marque también el archivo de la TRD.");
          await pedir(`/api/trd/versiones/${versionId}/cotejo`, { method: "POST", body: JSON.stringify({ filas: de("ccd"), original }) });
        }
      } else {
        await cargar(vista.filas.filter((f) => incluir.has(f.fila)), "trd");
      }
      alTerminar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo guardar.");
    } finally {
      setOcupado(false);
    }
  }

  const conProblemas = vista ? vista.filas.filter((f) => f.problemas.length).length : 0;
  const paquete = !!vista?.partes && vista.partes.length > 1;
  return (
    <>
      <p>El archivo de la TRD tal como lo tenga la entidad: Excel, PDF con texto, Word o CSV. También un .zip con varios
        archivos (la TRD, el CCD, una TVD): el sistema le pregunta qué es cada uno.</p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="acciones">
        <label className="boton primario">
          {ocupado && !vista ? "Leyendo…" : vista ? "Elegir otro archivo" : "Elegir el archivo"}
          <input type="file" accept=".xlsx,.xlsm,.pdf,.docx,.csv,.zip" hidden disabled={ocupado}
                 onChange={(e) => e.target.files?.[0] && leer(e.target.files[0])} />
        </label>
        <button type="button" className="enlace" onClick={() => descargar("/api/cuadro/plantilla").catch(() => undefined)}>
          ¿No tiene el archivo? Descargue la plantilla Excel</button>
      </div>
      {vista && (
        <>
          <div className={`aviso ${conProblemas ? "alerta" : "bien"}`} role="status" style={{ marginTop: 10 }}>
            El sistema leyó <strong>{vista.resumen.filas}</strong> fila(s) de «{vista.origen}».
            {conProblemas ? <> <strong>{conProblemas}</strong> tienen problemas y quedan fuera; revíselas abajo (cada una
              dice qué le falta). Puede corregirlas en el archivo y volver a subirlo, o agregarlas a mano en el paso 3.</>
              : " Todas se leyeron bien."}
          </div>
          {paquete && (
            <div className="tarjeta" style={{ marginTop: 10 }}>
              <div className="tarjeta-cab">El paquete trae {vista.partes!.length} archivos: confirme qué es cada uno</div>
              <div className="tabla-desplazable">
                <table className="tabla-permisos">
                  <thead><tr><th>Archivo</th><th>Filas</th><th>Con retención</th><th>Es</th></tr></thead>
                  <tbody>
                    {vista.partes!.map((x) => (
                      <tr key={x.archivo}>
                        <td><strong>{x.archivo}</strong>{x.con_problemas > 0 && <div className="meta">{x.con_problemas} con problemas (quedan fuera)</div>}</td>
                        <td>{x.filas}</td><td>{x.con_retencion}</td>
                        <td><select className="selector" aria-label={`Qué es ${x.archivo}`} value={roles[x.archivo]}
                                    onChange={(e) => setRoles({ ...roles, [x.archivo]: e.target.value as Rol })}>
                          {(Object.keys(ROL_NOMBRE) as Rol[]).map((r) => <option key={r} value={r}>{ROL_NOMBRE[r]}</option>)}
                        </select></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="meta" style={{ padding: "0 16px" }}>El sistema lo sugiere por el nombre del archivo y por si trae
                retención; cámbielo si no acierta.</p>
            </div>
          )}
          <details open={conProblemas > 0 && !paquete}>
            <summary className="meta">Ver fila por fila lo que se leyó</summary>
            <div className="tabla-desplazable"><TablaVistaPrevia vista={vista} incluir={incluir} setIncluir={setIncluir} /></div>
          </details>
          <div className="acciones">
            <button type="button" className="boton primario" disabled={ocupado || (!paquete && !incluir.size)} onClick={guardar}>
              {ocupado ? "Guardando…" : paquete ? "Guardar el paquete y seguir" : `Guardar estas ${incluir.size} fila(s) y seguir`}</button>
          </div>
        </>
      )}
    </>
  );
}

const CORRECCIONES: [string, string, string][] = [
  ["dependencias", "Dependencias", "Las oficinas productoras y su código"],
  ["series", "Series, subseries y tipos documentales", "Los nombres y códigos que usa la tabla"],
  ["matriz", "Retención por dependencia", "Años en archivo de gestión y central, disposición final, soporte y procedimiento"],
];

export function AsistenteTrd() {
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const [parametros] = useSearchParams();
  const [versiones, setVersiones] = useState<VersionTrd[] | null>(null);
  const [revision, setRevision] = useState<Aplicacion | null>(null);
  const [datos, setDatos] = useState(false);
  const [resubir, setResubir] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  const [aplicada, setAplicada] = useState<Aplicacion | null>(null);
  const [otra, setOtra] = useState<"fondo" | "importar" | null>(null);
  const esAdmin = !!usuario?.es_administrador;
  const abrir = parametros.get("vista");

  const cargar = useCallback(async () => {
    if (!fondo) return;
    try {
      setVersiones(await pedir<VersionTrd[]>(`/api/trd/versiones?fondo_id=${fondo.id}&instrumento=trd`));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudieron leer las versiones.");
    }
  }, [fondo]);
  useEffect(() => { setRevision(null); setAplicada(null); cargar(); }, [cargar]);

  const borrador = versiones?.find((v) => v.estado === "borrador") || null;
  const vigente = versiones?.find((v) => v.estado === "vigente") || null;

  async function revisar(aplicar: boolean) {
    if (!borrador) return;
    setOcupado(true);
    setError("");
    try {
      const r = await pedir<Aplicacion>(`/api/trd/versiones/${borrador.id}/${aplicar ? "aplicar" : "validar"}`, { method: "POST" });
      if (r.aplicada) {
        setAplicada(r);
        setRevision(null);
        await cargar();
      } else {
        setRevision(r);
      }
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo.");
    } finally {
      setOcupado(false);
    }
  }

  async function descartar() {
    if (!borrador || !await confirmar(`¿Descartar la ${borrador.nombre} en preparación? Queda registrada como anulada; `
      + "no se borra. La versión que rige no cambia.")) return;
    try {
      await pedir(`/api/trd/versiones/${borrador.id}/anular`, { method: "POST", body: JSON.stringify({ motivo: null }) });
      setRevision(null);
      cargar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo descartar.");
    }
  }

  // Estado de cada paso.
  const subido = !!borrador && borrador.filas > 0 && !resubir;
  const revisada = subido && !!revision && revision.version.id === borrador?.id && revision.validacion.conforme;
  const faltan = revision?.informe.faltan_para_aplicar || [];
  const datosCompletos = !!borrador?.acto_aprobacion && !!borrador?.fecha_aprobacion && !!borrador?.vigente_desde;
  const e1: EstadoPaso = subido ? "hecho" : "ahora";
  const e2: EstadoPaso = !subido ? "pendiente" : revisada ? "hecho" : "ahora";
  const e3: EstadoPaso = subido ? "opcional" : "pendiente";
  const e4: EstadoPaso = revisada ? "ahora" : "pendiente";

  return (
    <>
      <h1>TRD y CCD</h1>
      <p className="sub">La tabla de retención documental del fondo y su cuadro de clasificación, paso a paso.</p>
      {!esAdmin && <div className="aviso" role="note">Solo la administración carga y aprueba la TRD. Aquí puede ver cuál rige.</div>}
      {error && <div className="aviso error" role="alert">{error}</div>}

      {!fondo ? (
        <div className="tarjeta"><div className="tarjeta-cuerpo">
          <p style={{ marginTop: 0 }}>Todavía no hay fondos. Empiece por registrar el fondo con su CCD y su TRD.</p>
          {esAdmin && <RegistrarFondo alTerminar={() => undefined} />}
        </div></div>
      ) : (
        <>
          <div className="tarjeta estado-trd">
            <div className="tarjeta-cab">TRD de «{fondo.titulo}»</div>
            <div className="tarjeta-cuerpo">
              <dl className="par-dato" style={{ margin: 0 }}>
                <dt>Rige hoy</dt>
                <dd>{vigente ? <>{vigente.nombre}{vigente.acto_aprobacion && ` · ${vigente.acto_aprobacion}`}
                  {vigente.vigente_desde && ` · desde ${vigente.vigente_desde}`} · {vigente.filas} serie(s) y subserie(s)</>
                  : <span className="meta">Ninguna todavía</span>}</dd>
                <dt>En preparación</dt>
                <dd>{borrador ? <>{borrador.nombre} · {borrador.filas} serie(s) y subserie(s)
                  {esAdmin && <> · <button type="button" className="enlace" onClick={descartar}>Descartar</button></>}</>
                  : <span className="meta">Ninguna</span>}</dd>
              </dl>
              {vigente && <Link className="boton chico" to="/fondos?vista=versiones" style={{ marginTop: 8 }}>
                Ver el cuadro de clasificación y el historial de versiones</Link>}
            </div>
          </div>

          {aplicada && (
            <div className="aviso bien" role="status">
              <strong>{aplicada.version.nombre} quedó vigente.</strong> El cuadro de clasificación se armó en RiC-O y se validó.
              La versión anterior pasó a histórica: nada se borra y cada expediente conserva la retención de la TRD con que
              se produjo. <Link to="/fondos?vista=versiones">Ver el cuadro</Link>
            </div>
          )}

          {esAdmin && versiones && (
            <>
              {!borrador && vigente && !aplicada && (
                <p className="meta">¿La TRD cambió (nueva estructura, nuevas series, otros tiempos)? Prepare la versión nueva
                  con los pasos siguientes. La que rige no cambia hasta que apruebe la nueva.</p>
              )}
              <ol className="pasos">
                <Paso n={1} titulo="Subir el archivo de la TRD" estado={e1}
                      resumen={subido ? <>{borrador?.filas} serie(s) y subserie(s) guardadas en la {borrador?.nombre}.{" "}
                        <button type="button" className="enlace" onClick={() => setResubir(true)}>Subir otro archivo</button>
                        <Originales versionId={borrador!.id} /></> : undefined}>
                  {!subido && <Subir fondoId={fondo.id} versionTrdId={borrador?.id || vigente?.id || null}
                                     alTerminar={() => { setResubir(false); setRevision(null); cargar(); }} />}
                </Paso>

                <Paso n={2} titulo="Revisar lo que leyó el sistema" estado={e2}
                      resumen={revisada ? "Revisada: el cuadro cumple RiC-O 1.1." : undefined}>
                  {subido && vigente && <ComparacionTrd key={`${borrador!.id}-${borrador!.filas}`} versionId={borrador!.id} />}
                  {subido && <CotejoCcd versionId={borrador!.id} />}
                  {!revisada && (
                    <>
                      <p>El sistema arma el cuadro de clasificación con lo que guardó y comprueba que esté completo y sea
                        correcto (RiC-O 1.1). Si algo falla, le dice qué y dónde corregirlo.</p>
                      <div className="acciones">
                        <button type="button" className="boton primario" disabled={ocupado} onClick={() => revisar(false)}>
                          {ocupado ? "Revisando…" : revision ? "Revisar de nuevo" : "Revisar ahora"}</button>
                      </div>
                    </>
                  )}
                  {revision && revision.version.id === borrador?.id && (
                    <>
                      <ResultadoValidacion v={revision.validacion} />
                      {!!revision.informe.series_sin_funcion?.length && (
                        <div className="aviso alerta">{revision.informe.series_sin_funcion.length} serie(s) sin la función
                          que las produce. No impide aprobar; puede asignarla en el paso 3, «Retención por dependencia».</div>
                      )}
                      {revision.informe.avisos.length > 0 && <ul className="meta">{revision.informe.avisos.map((a) => <li key={a}>{a}</li>)}</ul>}
                    </>
                  )}
                </Paso>

                <Paso n={3} titulo="Corregir (solo si hace falta)" estado={e3}
                      resumen="Lo que el archivo no traía bien se arregla aquí; después vuelva a revisar.">
                  {CORRECCIONES.map(([clave, titulo, ayuda]) => (
                    <details key={clave} className="seccion-ajuste tarjeta" open={abrir === clave}>
                      <summary><strong>{titulo}</strong> <span className="meta">{ayuda}</span></summary>
                      <div className="seccion-ajuste-cuerpo">
                        {clave === "dependencias" ? <DependenciasTrd fondoId={fondo.id} incrustado />
                          : clave === "series" ? <BancoTrd fondoId={fondo.id} incrustado />
                          : <MatrizTrd fondoId={fondo.id} incrustado />}
                      </div>
                    </details>
                  ))}
                </Paso>

                <Paso n={4} titulo="Aprobar y poner a regir" estado={e4}
                      resumen={!revisada ? "Se habilita cuando la revisión del paso 2 sale bien." : undefined}>
                  <p>Con el acto administrativo que la aprueba y la fecha desde la que rige. La versión que rige hoy pasa a
                    histórica y se conserva.</p>
                  <ul className="lista-control">
                    <li className={borrador?.acto_aprobacion ? "bien" : ""}>Acto que la aprueba: {borrador?.acto_aprobacion || "falta"}</li>
                    <li className={borrador?.fecha_aprobacion ? "bien" : ""}>Fecha del acto: {borrador?.fecha_aprobacion || "falta"}</li>
                    <li className={borrador?.vigente_desde ? "bien" : ""}>Rige desde: {borrador?.vigente_desde || "falta"}</li>
                  </ul>
                  {faltan.length > 0 && <div className="aviso alerta">Falta {faltan.join(", ")}.</div>}
                  <div className="acciones">
                    <button type="button" className={`boton${datosCompletos ? "" : " primario"}`} onClick={() => setDatos(true)}>
                      {datosCompletos ? "Corregir los datos de aprobación" : "Escribir los datos de aprobación"}</button>
                    <button type="button" className="boton primario" disabled={ocupado || !datosCompletos} onClick={() => revisar(true)}>
                      {ocupado ? "Aplicando…" : "Aprobar y poner a regir"}</button>
                  </div>
                </Paso>
              </ol>
            </>
          )}

          {esAdmin && (
            <details className="tarjeta otras-tareas">
              <summary><strong>Otras tareas</strong> <span className="meta">Registrar un fondo nuevo · traer un fondo de otro
                sistema (RiC-O o EAD)</span></summary>
              <div className="tarjeta-cuerpo">
                <div className="acciones">
                  <button type="button" className="boton chico" onClick={() => setOtra(otra === "fondo" ? null : "fondo")}>
                    Registrar un fondo nuevo</button>
                  <button type="button" className="boton chico" onClick={() => setOtra(otra === "importar" ? null : "importar")}>
                    Traer un fondo de otro sistema</button>
                </div>
                {otra === "fondo" && <RegistrarFondo alTerminar={() => setOtra(null)} />}
                {otra === "importar" && <ImportarRico alImportar={() => setOtra(null)} />}
              </div>
            </details>
          )}
        </>
      )}

      {datos && borrador && fondo && (
        <Ventana titulo={`Datos de aprobación · ${borrador.nombre}`} alCerrar={() => setDatos(false)} ancha>
          <FormVersion fondoId={fondo.id} version={borrador} hayVigente={!!vigente}
                       alTerminar={() => { setDatos(false); cargar(); }} />
        </Ventana>
      )}
    </>
  );
}
