import { useState } from "react";
import { ErrorAPI, pedir } from "@/lib/api";
import { confianzaTexto } from "@/lib/formato";

// Posibles datos personales (Ley 1581 de 2012) que el sistema encontró con reglas en el texto de
// cada documento. Cada uno se confirma, se corrige (otra categoría) o se descarta con su motivo;
// mientras quede alguno pendiente, la descripción no se publica.

export interface HallazgoDato {
  id: string; tipo: string; tipo_nombre: string; categoria: Categoria; categoria_nombre: string; confianza: number;
  muestra: string; veces: number; paginas: number[]; recomendacion: string;
  contexto: { antes: string; valor: string; despues: string } | null;
  estado: "pendiente" | "confirmado" | "corregido" | "descartado"; categoria_final: Categoria | null;
  motivo: string | null; decidido_por: string | null;
}
export interface RevisionDatos {
  documentos: { id: string; nombre: string; revisado: boolean; hallazgos: HallazgoDato[] }[];
  pendientes: number; nivel_propuesto: string | null; sin_texto: string[];
}
type Categoria = "personal" | "sensible" | "menores";

const CATEGORIA: Record<Categoria, string> = { personal: "Personal", sensible: "Sensible", menores: "De menores" };
const CLASE: Record<Categoria, string> = { personal: "proceso", sensible: "alerta", menores: "error" };
const ESTADO: Record<HallazgoDato["estado"], string> = {
  pendiente: "Por revisar", confirmado: "Confirmado", corregido: "Corregido", descartado: "Descartado",
};
const MOTIVOS = ["No se refiere a una persona", "Es un dato institucional (de la entidad)",
  "Es información pública de un servidor en ejercicio de su cargo", "El sistema leyó mal el texto"];

export function DatosPersonales({ trabajoId, datos, alCambiar }: {
  trabajoId: string; datos: RevisionDatos; alCambiar: (d: RevisionDatos) => void;
}) {
  const [abierto, setAbierto] = useState<{ id: string; modo: "corregir" | "descartar" } | null>(null);
  const [categoria, setCategoria] = useState<Categoria>("sensible");
  const [motivo, setMotivo] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  const total = datos.documentos.reduce((n, d) => n + d.hallazgos.length, 0);

  async function decidir(h: HallazgoDato, accion: "confirmar" | "corregir" | "descartar") {
    setOcupado(true);
    setError("");
    try {
      alCambiar(await pedir<RevisionDatos>(`/api/descripcion/datos-personales/${h.id}/decision`, {
        method: "POST",
        body: JSON.stringify({ trabajo_id: trabajoId, accion, motivo: motivo || null,
                               categoria: accion === "corregir" ? categoria : null }),
      }));
      setAbierto(null);
      setMotivo("");
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo guardar la decisión.");
    } finally {
      setOcupado(false);
    }
  }

  if (!total && !datos.sin_texto.length) {
    return (
      <div className="aviso bien" role="note" style={{ marginBottom: 12 }}>
        <strong>Datos personales:</strong> el sistema no encontró cédulas, tarjetas de identidad, correos, teléfonos,
        cuentas ni datos de salud o de menores en el texto. <span className="meta">Son reglas sobre el texto, no IA:
        si ve alguno, declárelo abajo en «Datos personales».</span>
      </div>
    );
  }

  return (
    <div className={`aviso ${datos.pendientes ? "alerta" : "bien"} datos-personales`} role="region"
         aria-label="Posibles datos personales" style={{ marginBottom: 12 }}>
      <strong>{datos.pendientes
        ? `${datos.pendientes} posible(s) dato(s) personal(es) por revisar (Ley 1581 de 2012)`
        : "Datos personales revisados"}</strong>
      <span className="meta"> · los encontró el sistema con reglas, en el servidor; el texto no salió a ningún
        servicio para esto. Confirme, corrija o descarte cada uno antes de publicar.</span>
      {datos.sin_texto.length > 0 && (
        <div className="meta">Sin texto para revisar (revíselo a mano): {datos.sin_texto.join(", ")}.</div>
      )}
      {error && <div className="aviso error" role="alert">{error}</div>}
      {datos.documentos.filter((d) => d.hallazgos.length).map((d) => (
        <div key={d.id}>
          {datos.documentos.length > 1 && <div className="meta" style={{ marginTop: 8 }}>{d.nombre}</div>}
          <ul className="lista-datos">
            {d.hallazgos.map((h) => {
              const cat = h.categoria_final || h.categoria;
              return (
                <li key={h.id} className={h.estado === "descartado" ? "descartado" : undefined}>
                  <div>
                    <span className={`insignia ${CLASE[cat]}`}>{CATEGORIA[cat]}</span>{" "}
                    <strong>{h.tipo_nombre}</strong>
                    <span className="meta">
                      {h.paginas.length ? ` · página${h.paginas.length > 1 ? "s" : ""} ${h.paginas.join(", ")}` : ""}
                      {h.veces > 1 ? ` · aparece ${h.veces} veces` : ""} · confianza {confianzaTexto(h.confianza * 100)}
                      {" · "}{ESTADO[h.estado]}{h.decidido_por ? ` por ${h.decidido_por}` : ""}
                    </span>
                  </div>
                  {h.contexto && (
                    <div className="linea-contexto">{h.contexto.antes}<mark>{h.contexto.valor}</mark>{h.contexto.despues}</div>
                  )}
                  {h.estado === "pendiente" && <div className="pista">{h.recomendacion}</div>}
                  {h.motivo && <div className="meta">Motivo: {h.motivo}</div>}
                  {h.estado === "pendiente" && abierto?.id !== h.id && (
                    <div className="acciones-chicas">
                      <button type="button" className="boton chico primario" disabled={ocupado}
                              onClick={() => decidir(h, "confirmar")}>Confirmar</button>
                      <button type="button" className="boton chico" disabled={ocupado}
                              onClick={() => { setAbierto({ id: h.id, modo: "corregir" });
                                               setCategoria(h.categoria === "personal" ? "sensible" : "personal"); }}>
                        Corregir</button>
                      <button type="button" className="boton chico" disabled={ocupado}
                              onClick={() => { setAbierto({ id: h.id, modo: "descartar" }); setMotivo(""); }}>
                        Descartar</button>
                    </div>
                  )}
                  {abierto?.id === h.id && abierto.modo === "corregir" && (
                    <div className="acciones-chicas">
                      <select className="selector" aria-label="Categoría correcta" value={categoria}
                              onChange={(e) => setCategoria(e.target.value as Categoria)}>
                        {(Object.keys(CATEGORIA) as Categoria[]).filter((c) => c !== h.categoria).map((c) =>
                          <option key={c} value={c}>{CATEGORIA[c]}</option>)}
                      </select>
                      <input className="entrada" placeholder="Por qué (opcional)" value={motivo} maxLength={500}
                             onChange={(e) => setMotivo(e.target.value)} />
                      <button type="button" className="boton chico primario" disabled={ocupado}
                              onClick={() => decidir(h, "corregir")}>Guardar</button>
                      <button type="button" className="boton chico" onClick={() => setAbierto(null)}>Cancelar</button>
                    </div>
                  )}
                  {abierto?.id === h.id && abierto.modo === "descartar" && (
                    <div className="acciones-chicas">
                      <select className="selector" aria-label="Motivo" value={MOTIVOS.includes(motivo) ? motivo : ""}
                              onChange={(e) => setMotivo(e.target.value)}>
                        <option value="">Elija o escriba el motivo…</option>
                        {MOTIVOS.map((m) => <option key={m} value={m}>{m}</option>)}
                      </select>
                      <input className="entrada" placeholder="Motivo" value={motivo} maxLength={500}
                             onChange={(e) => setMotivo(e.target.value)} />
                      <button type="button" className="boton chico primario" disabled={ocupado || motivo.trim().length < 4}
                              onClick={() => decidir(h, "descartar")}>Descartar</button>
                      <button type="button" className="boton chico" onClick={() => setAbierto(null)}>Cancelar</button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
      {datos.nivel_propuesto && (
        <div className="meta">Según lo confirmado, la descripción declarará: <strong>{{
          personales: "contiene datos personales", sensibles: "contiene datos sensibles",
          menores: "contiene datos de niños, niñas o adolescentes" }[datos.nivel_propuesto]}</strong>.</div>
      )}
    </div>
  );
}
