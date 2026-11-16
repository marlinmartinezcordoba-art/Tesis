// Configuración archivística institucional: los instrumentos que alimentan el contexto RiC del
// fondo, cada uno con su estado en RICORA, y la tabla de versiones con su acto, vigencia y estado.
// Los instrumentos no gobiernan el modelo RiC: lo alimentan (series → Record Set, retención → rico:Rule,
// función → rico:ActivityType, términos → vocabulario controlado).
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { pedir } from "@/lib/api";
import { diaCivil as fecha } from "@/lib/formato";
import { ParaQueSirve } from "@/components/ParaQueSirve";

interface Version {
  id: string; numero: number; nombre: string; acto_aprobacion: string | null; fecha_aprobacion: string | null;
  vigente_desde: string | null; vigente_hasta: string | null; estado: string; filas: number; instrumento: string;
  periodo?: string | null;
}

type Estado = "disponible" | "parcial" | "pendiente";
const INSTRUMENTOS: { nombre: string; que: string; ric: string; estado: Estado; ruta?: string; nota?: string }[] = [
  { nombre: "Institución", que: "Datos, naturaleza jurídica y custodia", ric: "rico:CorporateBody (ISDIAH)", estado: "parcial",
    ruta: "/vocabularios", nota: "La ficha de la entidad como agente; faltan sedes y responsables." },
  { nombre: "Estructura orgánica", que: "Dependencias como agentes, su jerarquía y su vigencia",
    ric: "rico:CorporateBody · hasOrHadSubordinate", estado: "disponible", ruta: "/fondos?vista=estructura" },
  { nombre: "CCD", que: "Códigos, series y subseries", ric: "rico:RecordSet con su tipo", estado: "disponible", ruta: "/fondos?vista=cargar" },
  { nombre: "TRD", que: "Retención y disposición final", ric: "rico:Rule que regula la serie", estado: "disponible", ruta: "/fondos?vista=versiones" },
  { nombre: "TVD", que: "Valoración del fondo acumulado", ric: "rico:Rule por periodo", estado: "disponible", ruta: "/fondos?vista=tvd" },
  { nombre: "Banco terminológico", que: "Denominaciones controladas", ric: "skos:Concept · vocabularios", estado: "disponible",
    ruta: "/vocabularios?vista=tesauros" },
  { nombre: "Mapas de procesos", que: "Funciones, procesos y actividades", ric: "rico:ActivityType · rico:Activity", estado: "parcial",
    ruta: "/funciones", nota: "La función sale de la TRD; falta cargar el mapa de procesos." },
  { nombre: "TCA", que: "Condiciones y restricciones de acceso por serie", ric: "rico:Rule de acceso · conditionsOfAccess",
    estado: "disponible", ruta: "/fondos?vista=tca" },
  { nombre: "FUID", que: "Inventario y localización", ric: "rico:RecordSet expediente · unidad de conservación",
    estado: "disponible", ruta: "/fondos?vista=fuid", nota: "Se importa uno existente o se genera desde el catálogo." },
  { nombre: "PGD y PINAR", que: "Programas y planeación", ric: "rico:Mandate que regula actividades", estado: "disponible",
    ruta: "/gobierno" },
  { nombre: "SIC", que: "Conservación y preservación", ric: "Eventos de conservación", estado: "pendiente",
    nota: "Fuera del alcance del prototipo." },
];
const ESTADO: Record<Estado, { texto: string; clase: string }> = {
  disponible: { texto: "En RICORA", clase: "bien" }, parcial: { texto: "Parcial", clase: "alerta" },
  pendiente: { texto: "Pendiente", clase: "" },
};
const ESTADO_VERSION: Record<string, string> = { vigente: "Vigente", historica: "Histórico", borrador: "Borrador", anulada: "Anulada" };

export function ConfiguracionInstitucional({ fondoId }: { fondoId: string }) {
  const [versiones, setVersiones] = useState<Version[] | null>(null);
  useEffect(() => {
    Promise.all(["trd", "tvd"].map((i) => pedir<Version[]>(`/api/trd/versiones?fondo_id=${fondoId}&instrumento=${i}`).catch(() => [])))
      .then(([trd, tvd]) => setVersiones([...trd, ...tvd]));
  }, [fondoId]);

  return (
    <>
      <h1>Configuración archivística institucional</h1>
      <ParaQueSirve><p>Los instrumentos de la entidad alimentan el contexto RiC del fondo: las series pasan a ser
        conjuntos documentales (Record Set), la retención y la valoración, reglas (rico:Rule) que los regulan, las
        funciones, tipos de actividad, y los términos, vocabularios controlados. No gobiernan la descripción: la
        alimentan.</p></ParaQueSirve>
      <div className="config-rejilla">
        {INSTRUMENTOS.map((i) => {
          const e = ESTADO[i.estado];
          const cuerpo = (
            <>
              <div className="config-cab"><strong>{i.nombre}</strong><span className={`insignia ${e.clase}`}>{e.texto}</span></div>
              <span className="meta">{i.que}</span>
              <code className="rico">{i.ric}</code>
              {i.nota && <span className="pista" style={{ margin: 0 }}>{i.nota}</span>}
            </>
          );
          return i.ruta ? <Link key={i.nombre} className="config-ficha" to={i.ruta}>{cuerpo}</Link>
            : <div key={i.nombre} className="config-ficha">{cuerpo}</div>;
        })}
      </div>
      <div className="tarjeta tabla-desplazable" style={{ marginTop: 16 }}>
        <div className="tarjeta-cab"><span>Versiones de los instrumentos</span></div>
        {!versiones ? <div className="cargando">Cargando…</div> : versiones.length === 0 ? (
          <div className="vacio">Todavía no hay versiones. <Link to="/fondos?vista=cargar">Cargue el CCD y la TRD</Link>.</div>
        ) : (
          <table className="tabla-permisos">
            <thead><tr><th>Instrumento</th><th>Versión</th><th>Acto de aprobación</th><th>Vigencia</th><th>Estado</th><th>Filas</th></tr></thead>
            <tbody>
              {versiones.map((v) => (
                <tr key={v.id}>
                  <td>{v.instrumento.toUpperCase()}{v.periodo ? ` · ${v.periodo}` : ""}</td>
                  <td>{String(v.numero).padStart(2, "0")} · {v.nombre}</td>
                  <td>{v.acto_aprobacion || "—"}{v.fecha_aprobacion && <span className="meta"> · {fecha(v.fecha_aprobacion)}</span>}</td>
                  <td>{fecha(v.vigente_desde)} – {v.vigente_hasta ? fecha(v.vigente_hasta) : "hoy"}</td>
                  <td><span className={`insignia ${v.estado === "vigente" ? "bien" : ""}`}>{ESTADO_VERSION[v.estado] || v.estado}</span></td>
                  <td>{v.filas}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
