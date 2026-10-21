import { Link } from "react-router-dom";
import { useVista } from "@/components/Marco";
import { CargarInstrumentos } from "@/components/CargarInstrumentos";
import { CuadroClasificacion } from "@/components/CuadroClasificacion";
import { BancoTrd, DependenciasTrd, MatrizTrd, VersionesTrd } from "@/components/ParametrizacionTrd";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";

// Fondos: el punto de partida del archivo. Todo nace de cargar el cuadro de
// clasificación (CCD) y la tabla de retención (TRD): el fondo, sus dependencias,
// series, subseries, tipos y matriz. Lo demás es ajuste manual, aplicación y consulta.
type VistaFondos = "cargar" | "fondos" | "versiones" | "dependencias" | "series" | "matriz" | "cuadro";

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

export function Fondos() {
  const vista = useVista<VistaFondos>("/fondos");
  const { fondo } = useFondo();
  if (vista === "fondos") return <ListaFondos />;
  if (vista === "cargar") return <CargarInstrumentos />;
  if (!fondo) return <div className="vacio">Registre un fondo primero (Fondos del archivo).</div>;
  const pantallas = { versiones: VersionesTrd, dependencias: DependenciasTrd, series: BancoTrd, matriz: MatrizTrd,
    cuadro: CuadroClasificacion };
  const Pantalla = pantallas[vista] || ListaFondos;
  return <Pantalla key={fondo.id} fondoId={fondo.id} />;
}
