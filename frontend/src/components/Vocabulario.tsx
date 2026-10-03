import { useState, type FormEvent } from "react";
import { SelectorFecha } from "@/components/SelectorFecha";
import {
  EN_VOCABULARIO, ROL_NOMBRE, SUBTIPO_AGENTE, SUBTIPO_MANDATO, SUBTIPO_NOMBRE, TIPO_NOMBRE, type TipoEntidad,
  type Verificacion,
} from "@/lib/descripcion";
import { desarmar, type ControlFecha } from "@/lib/fechas";

// Pregunta del vocabulario: «¿es la misma entidad?», con reutilizar o crear nueva.
export function PreguntaVocabulario({ valor, verificacion, alDecidir }: {
  valor: string;
  verificacion: Verificacion;
  alDecidir: (v: Verificacion) => void;
}) {
  if (verificacion.estado === "verificando") return <div className="vocab">Buscando en el vocabulario del fondo…</div>;
  if (verificacion.estado === "resuelta") {
    return (
      <div className="vocab resuelta">
        {verificacion.reutilizarId
          ? <>Se usará la entidad existente «{verificacion.reutilizarNombre}».</>
          : <>Se creará como entidad nueva en el vocabulario.</>}
        {verificacion.coincidencias.length > 0 && (
          <button type="button" className="enlace" style={{ marginLeft: 8 }}
                  onClick={() => alDecidir({ ...verificacion, estado: "pregunta", reutilizarId: undefined, crearNueva: undefined })}>
            Cambiar
          </button>
        )}
      </div>
    );
  }
  if (verificacion.estado !== "pregunta") return null;
  return (
    <div className="vocab">
      <div className="q">Ya existe algo parecido a «{valor}» en el vocabulario del fondo. ¿Es la misma entidad?</div>
      {verificacion.coincidencias.map((c) => (
        <div key={c.id} className="vocab-opcion">
          <span>
            <b>{c.nombre}</b>
            {c.subtipo && ` · ${SUBTIPO_NOMBRE[c.subtipo] || c.subtipo}`} · {Math.round(c.similitud * 100)} % parecido ·{" "}
            {c.conexiones} documento{c.conexiones === 1 ? "" : "s"}
          </span>
          <button type="button" className="boton chico primario"
                  onClick={() => alDecidir({ ...verificacion, estado: "resuelta", reutilizarId: c.id, reutilizarNombre: c.nombre, crearNueva: false })}>
            Reutilizar esta
          </button>
        </div>
      ))}
      <button type="button" className="boton chico" style={{ marginTop: 6 }}
              onClick={() => alDecidir({ ...verificacion, estado: "resuelta", reutilizarId: undefined, crearNueva: true })}>
        Es distinta: crear nueva
      </button>
    </div>
  );
}

export interface EntidadManual {
  tipo: TipoEntidad;
  valor: string;
  subtipo: string | null;
  rol: string | null;
  fecha_normalizada: string | null;
  edtf: string | null;
  fecha_subtipo: string | null;
}

// Formulario para agregar una entidad a mano (o corregir una propuesta).
export function FormEntidad({ inicial, alGuardar, alCancelar, textoBoton = "Agregar" }: {
  inicial?: Partial<EntidadManual>;
  alGuardar: (e: EntidadManual) => void;
  alCancelar: () => void;
  textoBoton?: string;
}) {
  const [tipo, setTipo] = useState<TipoEntidad>(inicial?.tipo || "agente");
  const [valor, setValor] = useState(inicial?.valor || "");
  const [subtipo, setSubtipo] = useState(inicial?.subtipo || (inicial?.tipo === "mandato" ? "otro" : "persona"));
  const [rol, setRol] = useState(inicial?.rol || "productor");
  const [fecha, setFecha] = useState<ControlFecha>(desarmar(inicial?.edtf, inicial?.fecha_subtipo as never));
  const [edtf, setEdtf] = useState<string | null>(inicial?.edtf || null);

  function guardar(e: FormEvent) {
    e.preventDefault();
    if (!valor.trim() || (tipo === "fecha" && !edtf)) return;
    alGuardar({
      tipo, valor: valor.trim(),
      subtipo: tipo === "agente" || tipo === "mandato" ? subtipo : null,
      rol: tipo === "agente" ? rol : null,
      fecha_normalizada: null,
      edtf: tipo === "fecha" || tipo === "mandato" ? edtf : null,
      fecha_subtipo: tipo === "fecha" ? fecha.subtipo : null,
    });
  }

  const cambiarTipo = (t: TipoEntidad) => {
    setTipo(t);
    setSubtipo(t === "mandato" ? "otro" : "persona");
  };

  return (
    <form className="form-entidad" onSubmit={guardar}>
      <div className="rejilla">
        {!inicial?.tipo && (
          <select className="selector" aria-label="Tipo" value={tipo} onChange={(e) => cambiarTipo(e.target.value as TipoEntidad)}>
            {(Object.keys(TIPO_NOMBRE) as TipoEntidad[]).map((t) => <option key={t} value={t}>{TIPO_NOMBRE[t]}</option>)}
          </select>
        )}
        <input className="entrada" aria-label="Valor" required autoFocus value={valor} onChange={(e) => setValor(e.target.value)}
               placeholder={tipo === "fecha" ? "Como aparece: «hacia 1948»" : tipo === "mandato" ? "Acuerdo 7 de 1946" : "Nombre"} />
        {tipo === "agente" && (
          <>
            <select className="selector" aria-label="Clase de agente" value={subtipo} onChange={(e) => setSubtipo(e.target.value)}>
              {Object.entries(SUBTIPO_AGENTE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select className="selector" aria-label="Rol en el documento" value={rol} onChange={(e) => setRol(e.target.value)}>
              {Object.entries(ROL_NOMBRE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </>
        )}
        {tipo === "mandato" && (
          <select className="selector" aria-label="Tipo de instrumento" value={subtipo} onChange={(e) => setSubtipo(e.target.value)}>
            {Object.entries(SUBTIPO_MANDATO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        )}
      </div>
      {(tipo === "fecha" || tipo === "mandato") && (
        <>
          {tipo === "mandato" && <p className="pista" style={{ marginBottom: 0 }}>Fecha de expedición (opcional):</p>}
          <SelectorFecha valor={fecha} subtipos={tipo === "mandato" ? ["simple"] : undefined}
                         alCambiar={(c, x) => { setFecha(c); setEdtf(x); }} />
        </>
      )}
      <div className="acciones" style={{ marginTop: 8 }}>
        <button type="submit" className="boton chico primario" disabled={tipo === "fecha" && !edtf}>{textoBoton}</button>
        <button type="button" className="boton chico" onClick={alCancelar}>Cancelar</button>
      </div>
      {tipo === "tipo_actividad" && (
        <p className="pista">Un tipo de actividad se asigna a una actividad del documento; no se conecta solo.</p>
      )}
      {EN_VOCABULARIO.includes(tipo) && (
        <p className="pista">Antes de confirmarla se compara con el vocabulario del fondo para no duplicarla.</p>
      )}
    </form>
  );
}
