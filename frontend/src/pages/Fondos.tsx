import { useState } from "react";
import { useVista } from "@/components/Marco";
import { CuadroClasificacion } from "@/components/CuadroClasificacion";
import { BancoTrd, DependenciasTrd, MatrizTrd, VersionesTrd } from "@/components/ParametrizacionTrd";
import { RegistrarFondo } from "@/components/RegistrarFondo";
import { Ventana } from "@/components/Ventana";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";

// Fondos: el punto de partida del archivo. Cada fondo se registra desde su
// cuadro de clasificación (CCD) y su tabla de retención (TRD); aquí se elige con
// cuál se trabaja y se parametriza su TRD, paso a paso, en el orden de los SGDEA.
type VistaFondos = "fondos" | "versiones" | "dependencias" | "series" | "matriz" | "cuadro";

function ListaFondos() {
  const { usuario } = useSesion();
  const { fondos, fondo, elegir } = useFondo();
  const [registrando, setRegistrando] = useState(false);
  return (
    <>
      <h1>Fondos</h1>
      <p className="sub">
        Los fondos del archivo. Elija con cuál trabajar: la carga, la descripción y la consulta se hacen sobre el fondo
        activo (también se cambia arriba, en el selector). Cada fondo nace de su cuadro de clasificación.
      </p>
      {usuario?.es_administrador && (
        <div className="acciones">
          <button type="button" className="boton primario" onClick={() => setRegistrando(true)}>+ Registrar un fondo</button>
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
      {registrando && (
        <Ventana titulo="Registrar un fondo" alCerrar={() => setRegistrando(false)} ancha>
          <RegistrarFondo alTerminar={() => setRegistrando(false)} />
        </Ventana>
      )}
    </>
  );
}

export function Fondos() {
  const vista = useVista<VistaFondos>("/fondos");
  const { fondo } = useFondo();
  if (vista === "fondos") return <ListaFondos />;
  if (!fondo) return <div className="vacio">Registre un fondo primero (Fondos del archivo).</div>;
  const pantallas = { versiones: VersionesTrd, dependencias: DependenciasTrd, series: BancoTrd, matriz: MatrizTrd,
    cuadro: CuadroClasificacion };
  const Pantalla = pantallas[vista] || ListaFondos;
  return <Pantalla key={fondo.id} fondoId={fondo.id} />;
}
