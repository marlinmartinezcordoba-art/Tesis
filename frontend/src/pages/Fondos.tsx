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

// La TVD (Acuerdo 004 de 2019) se está construyendo con la misma lógica de la TRD:
// versiones, periodos institucionales, series, retención, disposición y RiC-O.
function TvdEnConstruccion() {
  return (
    <>
      <h1>Tabla de valoración documental (TVD)</h1>
      <div className="aviso" role="note">
        En construcción. La TVD tendrá el mismo recorrido que la TRD: versiones con su acto de aprobación y su
        convalidación, los periodos institucionales del fondo acumulado, sus series y tipos, la retención y la
        disposición final, y su paso a RiC-O como regla del fondo.
      </div>
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
  if (vista === "tvd") return <TvdEnConstruccion />;
  if (!fondo) return <div className="vacio">Registre un fondo primero (Cargar el CCD y la TRD).</div>;
  if (vista === "ajustar") return <Ajustar key={fondo.id} fondoId={fondo.id} />;
  if (vista === "disposicion") return <DisposicionFinal key={fondo.id} fondoId={fondo.id} />;
  return (
    <>
      <VersionesTrd key={fondo.id} fondoId={fondo.id} />
      <div className="bloque-secundario"><CuadroClasificacion key={`c-${fondo.id}`} fondoId={fondo.id} /></div>
    </>
  );
}
