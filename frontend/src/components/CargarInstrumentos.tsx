import { useState } from "react";
import { Link } from "react-router-dom";
import { ErrorAPI, descargar, pedir, subir } from "@/lib/api";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";
import { TablaVistaPrevia, type Vista } from "@/components/CuadroClasificacion";
import { Pasos, type VersionTrd } from "@/components/ParametrizacionTrd";
import { ImportarRico, type Importado } from "@/components/ImportarRico";
import { RegistrarFondo, type Respuesta } from "@/components/RegistrarFondo";

// El punto de partida de todo: se cargan el CCD y la TRD y de ahí el sistema
// configura el fondo, sus dependencias, series, subseries, tipos documentales y la
// matriz de retención. Después se revisa y se ajusta a mano, y se aplica.

interface Configurado {
  fondo: string;
  version: { nombre: string; estado: string } | null;
  conteo: Record<string, number> | null;
  cuadroCreado: boolean;
  importado?: Record<string, number>;
}

const CONTEO: [string, string][] = [["dependencias", "dependencia(s) productora(s)"], ["series", "serie(s)"],
  ["subseries", "subserie(s)"], ["tipos_documentales", "tipo(s) documental(es)"], ["filas", "fila(s) de la matriz de retención"]];

function Resumen({ c }: { c: Configurado }) {
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Lo que se configuró en «{c.fondo}»</div>
      <div className="tarjeta-cuerpo">
        {c.conteo ? (
          <ul>
            {CONTEO.map(([k, nombre]) => <li key={k}><strong>{c.conteo?.[k] ?? 0}</strong> {nombre}</li>)}
            {!!c.conteo.repetidas && <li className="meta">{c.conteo.repetidas} fila(s) ya estaban y no se repitieron.</li>}
          </ul>
        ) : <p className="meta">La matriz no se llenó sola: complétela a mano en los pasos siguientes.</p>}
        {c.importado && (
          <p className="meta">Del RiC-O también se importaron {c.importado.expedientes ?? 0} expediente(s),
            {" "}{c.importado.documentos ?? 0} documento(s), {c.importado.entidades ?? 0} entidad(es) del vocabulario y
            {" "}{c.importado.relaciones ?? 0} relación(es).</p>
        )}
        {c.version && (
          <p>
            {c.version.nombre}: {c.version.estado === "vigente"
              ? "quedó vigente y el cuadro de clasificación ya está creado en RiC-O."
              : "quedó en borrador. Revise, ajuste y aplíquela para que rija."}
          </p>
        )}
        <p className="meta" style={{ marginBottom: 6 }}>Revise y, si hace falta, ajuste a mano:</p>
        <div className="acciones">
          <Link className="boton chico" to="/fondos?vista=dependencias">2. Dependencias</Link>
          <Link className="boton chico" to="/fondos?vista=series">3. Series, subseries y tipos</Link>
          <Link className="boton chico" to="/fondos?vista=matriz">4. Matriz de la TRD</Link>
          {c.version?.estado === "vigente"
            ? <Link className="boton chico primario" to="/fondos?vista=cuadro">Ver el cuadro de clasificación</Link>
            : <Link className="boton chico primario" to="/fondos?vista=versiones">5. Aplicar la versión</Link>}
          {c.cuadroCreado && c.version?.estado !== "vigente" && (
            <Link className="boton chico" to="/fondos?vista=cuadro">Ver el cuadro de clasificación</Link>)}
        </div>
      </div>
    </div>
  );
}

function NuevaVersion({ fondoId, titulo, alConfigurar }: { fondoId: string; titulo: string;
  alConfigurar: (c: Configurado) => void }) {
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
      setError(err instanceof ErrorAPI ? err.message : "No se pudo leer el archivo.");
    } finally {
      setOcupado(false);
    }
  }

  async function configurar() {
    if (!vista) return;
    setError("");
    setOcupado(true);
    try {
      const r = await pedir<{ version: VersionTrd; parametrizacion: Record<string, number> }>("/api/trd/cargar", {
        method: "POST", body: JSON.stringify({ fondo_id: fondoId, filas: vista.filas.filter((f) => incluir.has(f.fila)) }) });
      alConfigurar({ fondo: titulo, version: r.version, conteo: r.parametrizacion, cuadroCreado: false });
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo configurar.");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <p className="meta">
        Cargue la TRD nueva (o modificada) de «{titulo}». Con ella se configura el borrador de la versión siguiente:
        dependencias, series, subseries, tipos documentales y matriz. La vigente sigue rigiendo hasta que aplique la nueva.
      </p>
      <div className="acciones">
        <button type="button" className="boton chico" onClick={() => descargar("/api/cuadro/plantilla").catch(() => undefined)}>
          Descargar la plantilla Excel</button>
        <label className="boton chico primario">
          {ocupado ? "Leyendo…" : vista ? "Leer otro archivo" : "Leer el CCD y la TRD (Excel o PDF)"}
          <input type="file" accept=".xlsx,.xlsm,.pdf" hidden disabled={ocupado}
                 onChange={(e) => e.target.files?.[0] && leer(e.target.files[0])} />
        </label>
      </div>
      {vista && (
        <>
          <p className="meta">Lo que el sistema entendió · {vista.origen} · {vista.resumen.filas} fila(s),
            {" "}{vista.resumen.con_problemas} con problemas.</p>
          <div className="tabla-desplazable"><TablaVistaPrevia vista={vista} incluir={incluir} setIncluir={setIncluir} /></div>
          <div className="acciones">
            <button type="button" className="boton primario" disabled={ocupado || !incluir.size} onClick={configurar}>
              Configurar desde este archivo ({incluir.size} fila(s))</button>
          </div>
        </>
      )}
    </>
  );
}

export function CargarInstrumentos() {
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const [modo, setModo] = useState<"nuevo" | "version" | "rico">(fondo ? "version" : "nuevo");
  const [hecho, setHecho] = useState<Configurado | null>(null);

  function alImportar(r: Importado) {
    setHecho({ fondo: r.fondo?.titulo || "", conteo: r.parametrizacion, cuadroCreado: r.creado, version: r.version,
      importado: r.contenido });
  }

  function alCrear(r: Respuesta) {
    setHecho({ fondo: r.fondo?.titulo || "", conteo: r.parametrizacion, cuadroCreado: r.creado, version: r.version });
  }

  return (
    <>
      <h1>Cargar el CCD y la TRD</h1>
      <p className="sub">
        Todo parte de aquí. Cargue el cuadro de clasificación y la tabla de retención (plantilla del sistema o formato del
        AGN, en Excel o PDF) y el sistema configura el fondo, sus dependencias productoras, series, subseries, tipos
        documentales y la matriz de retención. Después revise y ajuste a mano lo que haga falta y aplique la versión.
      </p>
      <Pasos actual={1} />
      {!usuario?.es_administrador ? (
        <div className="vacio">Solo la administración carga los instrumentos archivísticos.</div>
      ) : hecho ? (
        <>
          <Resumen c={hecho} />
          <div className="acciones"><button type="button" className="boton" onClick={() => setHecho(null)}>Cargar otro</button></div>
        </>
      ) : (
        <>
          <div className="acciones" role="radiogroup" aria-label="Qué se carga">
            <label className="boton chico"><input type="radio" checked={modo === "nuevo"} onChange={() => setModo("nuevo")} />
              {" "}Un fondo nuevo</label>
            <label className={`boton chico${fondo ? "" : " deshabilitado"}`}>
              <input type="radio" disabled={!fondo} checked={modo === "version"} onChange={() => setModo("version")} />
              {" "}Una versión nueva de la TRD de {fondo ? `«${fondo.titulo}»` : "un fondo existente"}</label>
            <label className="boton chico"><input type="radio" checked={modo === "rico"} onChange={() => setModo("rico")} />
              {" "}Un fondo en RiC-O de otro sistema</label>
          </div>
          <div className="tarjeta">
            <div className="tarjeta-cuerpo">
              {modo === "rico" ? <ImportarRico alImportar={alImportar} />
                : modo === "nuevo" || !fondo
                ? <RegistrarFondo alTerminar={() => undefined} alCrear={alCrear} />
                : <NuevaVersion key={fondo.id} fondoId={fondo.id} titulo={fondo.titulo} alConfigurar={setHecho} />}
            </div>
          </div>
        </>
      )}
    </>
  );
}
