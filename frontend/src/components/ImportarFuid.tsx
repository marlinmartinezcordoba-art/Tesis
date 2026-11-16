// Importar un FUID existente (Acuerdo AGN 042 de 2002): cada fila es un expediente (rico:RecordSet) en su serie
// del cuadro, con fechas, unidad de conservación, folios, soporte y frecuencia de consulta. Primero se ve qué
// se entendió; después se crea, todo o nada.
import { useState } from "react";
import { ErrorAPI, subir } from "@/lib/api";
import { ParaQueSirve } from "@/components/ParaQueSirve";

interface FilaFuid {
  fila: number; codigo_serie: string; serie: string | null; codigo: string | null; titulo: string;
  fechas_extremas: string | null; caja: string | null; carpeta: string | null; folios: number | null; soporte: string | null;
  problemas: string[];
}
interface Previa { filas: FilaFuid[]; validas: number; con_problemas: number }

export function ImportarFuid({ fondoId }: { fondoId: string }) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [resultado, setResultado] = useState<{ creados: number; fuera: number } | null>(null);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);

  async function enviar(paso: "vista-previa" | "aplicar") {
    if (!archivo) return;
    setError("");
    setOcupado(true);
    try {
      const datos = new FormData();
      datos.append("archivo", archivo, archivo.name);
      const r = await subir<Previa & { creados?: number; fuera?: number }>(`/api/fondos/${fondoId}/fuid/${paso}`, datos, () => undefined);
      if (paso === "vista-previa") { setPrevia(r); setResultado(null); } else { setResultado({ creados: r.creados || 0, fuera: r.fuera || 0 }); setPrevia(null); }
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo leer el FUID.");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <>
      <h1>Importar un inventario (FUID)</h1>
      <ParaQueSirve><p>Para los inventarios ya hechos. Cada fila del FUID pasa a ser un expediente (rico:RecordSet) dentro de
        la serie o subserie del cuadro cuyo código trae, con sus fechas extremas, su unidad de conservación, sus folios, su
        soporte y su frecuencia de consulta. Una fila cuyo código no esté en el cuadro no se crea.</p></ParaQueSirve>
      <div className="tarjeta" style={{ padding: 14 }}>
        <input type="file" accept=".xlsx,.csv,.pdf,.docx" aria-label="Archivo del FUID"
               onChange={(e) => { setArchivo(e.target.files?.[0] || null); setPrevia(null); setResultado(null); }} />
        <button type="button" className="boton chico" disabled={!archivo || ocupado} onClick={() => enviar("vista-previa")}>
          {ocupado ? "Leyendo…" : "Ver qué se entendió"}</button>
      </div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      {resultado && <div className="aviso bien" role="status">Se crearon {resultado.creados} expediente(s).
        {resultado.fuera > 0 && ` ${resultado.fuera} fila(s) quedaron fuera por sus problemas.`}</div>}
      {previa && (
        <>
          <p className="meta">{previa.validas} fila(s) listas · {previa.con_problemas} con problemas (no se crean)</p>
          <div className="tarjeta tabla-desplazable">
            <table className="tabla-permisos">
              <thead><tr><th>Fila</th><th>Serie</th><th>Expediente</th><th>Fechas</th><th>Caja · carpeta</th><th>Folios</th><th>Estado</th></tr></thead>
              <tbody>
                {previa.filas.map((f) => (
                  <tr key={f.fila}>
                    <td>{f.fila}</td>
                    <td>{f.codigo_serie} {f.serie && <span className="meta">· {f.serie}</span>}</td>
                    <td>{f.titulo}{f.codigo && <div className="meta">{f.codigo}</div>}</td>
                    <td>{f.fechas_extremas || "—"}</td>
                    <td>{[f.caja, f.carpeta].filter(Boolean).join(" · ") || "—"}</td>
                    <td>{f.folios ?? "—"}</td>
                    <td>{f.problemas.length ? <span className="meta" style={{ color: "var(--danger)" }}>{f.problemas.join(" ")}</span>
                      : <span className="insignia bien">Lista</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {previa.validas > 0 && (
            <div className="acciones" style={{ marginTop: 10 }}>
              <button type="button" className="boton primario" disabled={ocupado} onClick={() => enviar("aplicar")}>
                Crear {previa.validas} expediente(s)</button>
            </div>
          )}
        </>
      )}
    </>
  );
}
