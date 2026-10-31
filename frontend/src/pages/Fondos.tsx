import { Link, useSearchParams } from "react-router-dom";
import { useVista } from "@/components/Marco";
import { AsistenteTrd } from "@/components/AsistenteTrd";
import { CuadroClasificacion } from "@/components/CuadroClasificacion";
import { DisposicionFinal } from "@/components/DisposicionFinal";
import { BancoTrd, DependenciasTrd, MatrizTrd, VersionesTrd } from "@/components/ParametrizacionTrd";
import { useFondo } from "@/lib/fondo";
import { useSesion } from "@/lib/sesion";

// Fondos: el punto de partida del archivo. Todo nace de cargar el cuadro de
// clasificación (CCD) y la tabla de retención (TRD): el fondo, sus dependencias,
// series, subseries, tipos y matriz. Lo demás es ajuste manual, aplicación y consulta.
type VistaFondos = "cargar" | "versiones" | "disposicion" | "tvd";

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
        mano, y aplíquela. Las dependencias y las series del periodo se revisan en el paso 3 de{" "}
        <Link to="/fondos?vista=dependencias">TRD y CCD</Link>.
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

export function Fondos() {
  const vista = useVista<VistaFondos>("/fondos");
  const { fondo } = useFondo();
  if (vista === "cargar") return <AsistenteTrd key={fondo?.id || "sin-fondo"} />;
  if (!fondo) return <div className="vacio">Registre un fondo primero (Cargar el CCD y la TRD).</div>;
  if (vista === "tvd") return <Tvd key={fondo.id} fondoId={fondo.id} />;
  if (vista === "disposicion") return <DisposicionFinal key={fondo.id} fondoId={fondo.id} />;
  return (
    <>
      <VersionesTrd key={fondo.id} fondoId={fondo.id} />
      <div className="bloque-secundario"><CuadroClasificacion key={`c-${fondo.id}`} fondoId={fondo.id} /></div>
    </>
  );
}
