import { Link } from "react-router-dom";
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
type VistaFondos = "cargar" | "fondos" | "versiones" | "dependencias" | "series" | "matriz" | "cuadro" | "disposicion" | "tvd";

function ListaFondos() {
  const { usuario } = useSesion();
  const { fondos, fondo, elegir } = useFondo();
  return (
    <>
      <h1>Fondos</h1>
      <p className="sub">
        Los fondos del archivo. Elija con cuál trabajar: la carga, la descripción y la consulta se hacen sobre el fondo
        activo (también se cambia arriba, en el selector). Cada fondo nace de cargar su CCD y su TRD.
      </p>
      {usuario?.es_administrador && (
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

export function Fondos() {
  const vista = useVista<VistaFondos>("/fondos");
  const { fondo } = useFondo();
  if (vista === "fondos") return <ListaFondos />;
  if (vista === "cargar") return <CargarInstrumentos />;
  if (vista === "tvd") return <TvdEnConstruccion />;
  if (!fondo) return <div className="vacio">Registre un fondo primero (Fondos del archivo).</div>;
  const pantallas = { versiones: VersionesTrd, dependencias: DependenciasTrd, series: BancoTrd, matriz: MatrizTrd,
    cuadro: CuadroClasificacion, disposicion: DisposicionFinal };
  const Pantalla = pantallas[vista] || ListaFondos;
  return <Pantalla key={fondo.id} fondoId={fondo.id} />;
}
