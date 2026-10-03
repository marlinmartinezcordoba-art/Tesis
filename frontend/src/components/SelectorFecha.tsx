import {
  CALIFICADOR_NOMBRE, MESES, PRECISION_NOMBRE, SUBTIPO_FECHA_NOMBRE, construir, controlInicial, legible, puntoVacio,
  type Calificador, type ControlFecha, type Precision, type PuntoFecha, type SubtipoFecha,
} from "@/lib/fechas";

function Punto({ p, cambiar, conCalificador, permitirVacio, etiqueta }: {
  p: PuntoFecha;
  cambiar: (p: PuntoFecha) => void;
  conCalificador: boolean;
  permitirVacio: boolean;
  etiqueta?: string;
}) {
  const exacto = p.precision === "exacto";
  return (
    <div className="fila-fecha">
      {etiqueta && <span className="meta" style={{ minWidth: 44 }}>{etiqueta}</span>}
      {permitirVacio && (
        <label className="meta">
          <input type="checkbox" checked={p.vacio} onChange={(e) => cambiar({ ...p, vacio: e.target.checked })} /> desconocido
        </label>
      )}
      {!p.vacio && (
        <>
          <select className="selector" aria-label="Precisión" value={p.precision}
                  onChange={(e) => cambiar({ ...p, precision: e.target.value as Precision })}>
            {Object.entries(PRECISION_NOMBRE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          {p.precision !== "desconocido" && (
            <input className="entrada anio" aria-label="Año" inputMode="numeric" maxLength={4} placeholder="1948" value={p.anio}
                   onChange={(e) => cambiar({ ...p, anio: e.target.value.replace(/\D/g, "") })} />
          )}
          {exacto && (
            <select className="selector" aria-label="Mes" value={p.mes} onChange={(e) => cambiar({ ...p, mes: e.target.value, dia: e.target.value ? p.dia : "" })}>
              <option value="">sin mes</option>
              {MESES.map((m, i) => <option key={m} value={String(i + 1).padStart(2, "0")}>{m}</option>)}
            </select>
          )}
          {exacto && p.mes && (
            <input className="entrada dia" aria-label="Día" inputMode="numeric" maxLength={2} placeholder="día" value={p.dia}
                   onChange={(e) => cambiar({ ...p, dia: e.target.value.replace(/\D/g, "") })} />
          )}
          {conCalificador && (
            <select className="selector" aria-label="Calificador" value={p.calificador}
                    onChange={(e) => cambiar({ ...p, calificador: e.target.value as Calificador })}>
              {Object.entries(CALIFICADOR_NOMBRE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          )}
        </>
      )}
    </div>
  );
}

// Captura de una fecha según su subtipo, con la forma legible en vivo. La
// expresión EDTF se construye por debajo; se muestra solo como referencia.
export function SelectorFecha({ valor, alCambiar, subtipos = ["simple", "rango", "conjunto"] }: {
  valor: ControlFecha;
  alCambiar: (c: ControlFecha, edtf: string | null) => void;
  subtipos?: SubtipoFecha[];
}) {
  const edtf = construir(valor);
  const cambiar = (c: ControlFecha) => alCambiar(c, construir(c));
  const punto = (i: number, p: PuntoFecha) => cambiar({ ...valor, puntos: valor.puntos.map((x, j) => (j === i ? p : x)) });

  return (
    <div className="selector-fecha">
      {subtipos.length > 1 && (
        <div className="opciones" role="radiogroup" aria-label="Tipo de fecha">
          {subtipos.map((s) => (
            <label key={s} className={valor.subtipo === s ? "elegida" : ""}>
              <input type="radio" checked={valor.subtipo === s}
                     onChange={() => cambiar({ ...controlInicial(s), puntos: s === "simple" ? [valor.puntos[0]]
                       : [valor.puntos[0], valor.puntos[1] || puntoVacio()] })} />
              {SUBTIPO_FECHA_NOMBRE[s]}
            </label>
          ))}
        </div>
      )}
      {valor.subtipo === "simple" && <Punto p={valor.puntos[0]} cambiar={(p) => punto(0, p)} conCalificador permitirVacio={false} />}
      {valor.subtipo === "rango" && (
        <>
          <Punto p={valor.puntos[0]} cambiar={(p) => punto(0, p)} conCalificador permitirVacio etiqueta="Desde" />
          <Punto p={valor.puntos[1]} cambiar={(p) => punto(1, p)} conCalificador permitirVacio etiqueta="Hasta" />
        </>
      )}
      {valor.subtipo === "conjunto" && (
        <>
          {valor.puntos.map((p, i) => (
            <div key={i} className="fila-fecha">
              <Punto p={p} cambiar={(x) => punto(i, x)} conCalificador={false} permitirVacio={false} />
              {valor.puntos.length > 2 && (
                <button type="button" className="enlace" onClick={() => cambiar({ ...valor, puntos: valor.puntos.filter((_, j) => j !== i) })}>
                  quitar
                </button>
              )}
            </div>
          ))}
          <button type="button" className="enlace" onClick={() => cambiar({ ...valor, puntos: [...valor.puntos, puntoVacio()] })}>
            + otra fecha
          </button>
        </>
      )}
      <div className="legible" aria-live="polite">
        {edtf ? <><strong>{legible(edtf)}</strong><code>{edtf}</code></> : <span className="meta">Complete la fecha.</span>}
      </div>
    </div>
  );
}
