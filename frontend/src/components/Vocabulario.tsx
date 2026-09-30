import { useState, type FormEvent } from "react";
import {
  EN_VOCABULARIO, ROL_NOMBRE, SUBTIPO_NOMBRE, TIPO_NOMBRE, type TipoEntidad, type Verificacion,
} from "@/lib/descripcion";

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
  const [subtipo, setSubtipo] = useState(inicial?.subtipo || "persona");
  const [rol, setRol] = useState(inicial?.rol || "productor");
  const [fecha, setFecha] = useState(inicial?.fecha_normalizada || "");

  function guardar(e: FormEvent) {
    e.preventDefault();
    if (!valor.trim()) return;
    alGuardar({
      tipo, valor: valor.trim(),
      subtipo: tipo === "agente" ? subtipo : null,
      rol: tipo === "agente" ? rol : null,
      fecha_normalizada: tipo === "fecha" && fecha ? fecha : null,
    });
  }

  return (
    <form className="form-entidad" onSubmit={guardar}>
      <div className="rejilla">
        {!inicial?.tipo && (
          <select className="selector" aria-label="Tipo" value={tipo} onChange={(e) => setTipo(e.target.value as TipoEntidad)}>
            {(Object.keys(TIPO_NOMBRE) as TipoEntidad[]).map((t) => <option key={t} value={t}>{TIPO_NOMBRE[t]}</option>)}
          </select>
        )}
        <input className="entrada" aria-label="Valor" required autoFocus value={valor} onChange={(e) => setValor(e.target.value)}
               placeholder={tipo === "fecha" ? "15 de marzo de 1948" : "Nombre"} />
        {tipo === "agente" && (
          <>
            <select className="selector" aria-label="Clase de agente" value={subtipo} onChange={(e) => setSubtipo(e.target.value)}>
              {Object.entries(SUBTIPO_NOMBRE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select className="selector" aria-label="Rol en el documento" value={rol} onChange={(e) => setRol(e.target.value)}>
              {Object.entries(ROL_NOMBRE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </>
        )}
        {tipo === "fecha" && (
          <input className="entrada" type="date" aria-label="Fecha normalizada (si es exacta)" value={fecha}
                 onChange={(e) => setFecha(e.target.value)} />
        )}
      </div>
      <div className="acciones" style={{ marginTop: 8 }}>
        <button type="submit" className="boton chico primario">{textoBoton}</button>
        <button type="button" className="boton chico" onClick={alCancelar}>Cancelar</button>
      </div>
      {EN_VOCABULARIO.includes(tipo) && (
        <p className="pista">Antes de confirmarla se compara con el vocabulario del fondo para no duplicarla.</p>
      )}
    </form>
  );
}
