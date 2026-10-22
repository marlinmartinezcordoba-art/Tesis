import { Link, useSearchParams } from "react-router-dom";
import { useVista } from "@/components/Marco";
import { CargarInstrumentos } from "@/components/CargarInstrumentos";
import { CuadroClasificacion } from "@/components/CuadroClasificacion";
import { DisposicionFinal } from "@/components/DisposicionFinal";
import { BancoTrd, DependenciasTrd, MatrizTrd, VersionesTrd } from "@/components/ParametrizacionTrd";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";

// Fondos: el punto de partida del archivo. Todo nace de cargar el cuadro de
// clasificación (CCD) y la tabla de retención (TRD): el fondo, sus dependencias,
// series, subseries, tipos y matriz. Lo demás es ajuste manual, aplicación y consulta.
type VistaFondos = "cargar" | "ajustar" | "versiones" | "disposicion" | "tvd";

function ListaFondos({ seccion = false }: { seccion?: boolean }) {
  const { usuario } = useSesion();
  const { fondos, fondo, elegir } = useFondo();
  const Titulo = seccion ? "h2" : "h1";
  return (
    <>
      <Titulo>Fondos del archivo</Titulo>
      <p className="sub">
        Los fondos del archivo. Elija con cuál trabajar: la carga, la descripción y la consulta se hacen sobre el fondo
        activo (también se cambia arriba, en el selector). Cada fondo nace de cargar su CCD y su TRD.
      </p>
      {usuario?.es_administrador && !seccion && (
        <div className="acciones">
          <Link className="boton primario" to="/fondos?vista=cargar">+ Registrar un fondo desde su CCD y TRD</Link>
        </div>
      )}
      <div className="tarjeta">
        <div className="tarjeta-cab">Fondos registrados</div>
        {!fondos ? <div className="cargando">Cargando…</div> : fondos.length === 0 ? (
          <p className="meta" style={{ padding: "0 18px" }}>Todavía no hay fondos.</p>
        ) : (
          <table className="tabla-permisos">
            <thead><tr><th>Fondo</th><th>Fechas extremas</th><th>Documentos</th><th /></tr></thead>
            <tbody>
              {fondos.map((f) => (
                <tr key={f.id}>
                  <td><strong>{f.titulo}</strong></td>
                  <td>{f.fechas_extremas || "—"}</td>
                  <td>{f.documentos}</td>
                  <td>{fondo?.id === f.id ? <span className="insignia bien">Activo</span> : (
                    <button type="button" className="boton chico" onClick={() => elegir(f.id)}>Trabajar con este</button>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

// La TVD (Acuerdo 004 de 2019): la valoración del fondo acumulado por periodos
// institucionales. Mismo recorrido que la TRD; las dependencias y el banco de
// series son los del fondo (Ajustar).
function Tvd({ fondoId }: { fondoId: string }) {
  return (
    <>
      <h1>Tabla de valoración documental (TVD)</h1>
      <p className="sub">
        Para el fondo acumulado: una TVD por periodo institucional (cada cambio de estructura orgánica), con su acto de
        aprobación y su convalidación. Sus reglas rigen los documentos producidos en ese periodo: un expediente de 2008 se
        valora con la TVD 2006–2011 y uno de 2020 con la TRD. Al aplicarla se arma el cuadro del periodo en RiC-O.
      </p>
      <div className="aviso" role="note">
        Abra la TVD del periodo, cárguela desde el archivo (Excel, PDF con texto, Word, CSV o .zip) o llene la matriz a
        mano, y aplíquela. Las dependencias y las series del periodo se revisan en{" "}
        <Link to="/fondos?vista=ajustar">Ajustar</Link>.
      </div>
      <VersionesTrd fondoId={fondoId} instrumento="tvd" />
      <details className="seccion-ajuste tarjeta" open>
        <summary><strong>Matriz de la TVD</strong> <span className="meta">Por dependencia del periodo: series, tipos,
          retención en archivo central y disposición final.</span></summary>
        <div className="seccion-ajuste-cuerpo"><MatrizTrd fondoId={fondoId} instrumento="tvd" /></div>
      </details>
    </>
  );
}

// Ajustar: lo que la carga ya configuró, en tres secciones que se abren. Se abre
// la que pidió la dirección (las de antes: ?vista=dependencias, series o matriz).
const AJUSTES: [string, string, string][] = [
  ["dependencias", "Dependencias", "Secciones y subsecciones productoras, con su código."],
  ["series", "Series, subseries y tipos documentales", "El banco terminológico del fondo."],
  ["matriz", "Matriz de la TRD", "Por dependencia: series, tipos, retención, disposición, soporte y procedimiento."],
];

function Ajustar({ fondoId }: { fondoId: string }) {
  const [parametros] = useSearchParams();
  const pedida = parametros.get("vista");
  const pantallas = { dependencias: DependenciasTrd, series: BancoTrd, matriz: MatrizTrd };
  return (
    <>
      <h1>Ajustar la TRD y el CCD</h1>
      <p className="sub">Lo que dejó la carga, para revisarlo y corregirlo a mano. Los cambios valen al aplicar la versión.</p>
      {AJUSTES.map(([clave, titulo, ayuda]) => {
        const Pantalla = pantallas[clave as keyof typeof pantallas];
        return (
          <details key={clave} className="seccion-ajuste tarjeta" open={pedida === clave}>
            <summary><strong>{titulo}</strong> <span className="meta">{ayuda}</span></summary>
            <div className="seccion-ajuste-cuerpo"><Pantalla fondoId={fondoId} /></div>
          </details>
        );
      })}
    </>
  );
}

export function Fondos() {
  const vista = useVista<VistaFondos>("/fondos");
  const { fondo } = useFondo();
  if (vista === "cargar") {
    return (
      <>
        <CargarInstrumentos />
        <div className="bloque-secundario"><ListaFondos seccion /></div>
      </>
    );
  }
  if (!fondo) return <div className="vacio">Registre un fondo primero (Cargar el CCD y la TRD).</div>;
  if (vista === "tvd") return <Tvd key={fondo.id} fondoId={fondo.id} />;
  if (vista === "ajustar") return <Ajustar key={fondo.id} fondoId={fondo.id} />;
  if (vista === "disposicion") return <DisposicionFinal key={fondo.id} fondoId={fondo.id} />;
  return (
    <>
      <VersionesTrd key={fondo.id} fondoId={fondo.id} />
      <div className="bloque-secundario"><CuadroClasificacion key={`c-${fondo.id}`} fondoId={fondo.id} /></div>
    </>
  );
}
