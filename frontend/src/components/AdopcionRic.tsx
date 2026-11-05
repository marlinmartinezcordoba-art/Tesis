import { useEffect, useState } from "react";
import { ErrorAPI, pedir } from "@/lib/api";
import { useFondo } from "@/lib/fondo";

// Adopción de RiC: el sistema se evalúa a sí mismo contra los siete criterios de un sistema nativo
// y contra la escala de niveles de adopción, con datos reales de la base y del almacén del grafo.
// Es la demostración de que RICORA adopta el lineamiento, no una afirmación.

interface Criterio {
  numero: number; criterio: string; estado: "cumplido" | "parcial"; evidencia: string[]; verificacion: string;
  prueba: string; motivo: string | null; en_uso: boolean;
}
interface Nivel { codigo: number; nombre: string; que: string }
interface Adopcion {
  nivel: Nivel; niveles: Nivel[]; cumplidos: number; criterios: Criterio[];
  conformidad: { fondos: number; grafos: number; conformes: number; no_conformes: number; pendientes: number; tripletas: number;
    clases_usadas: number; clases_total: number };
  cobertura: { atributos: { cubiertos: number; por_especializacion: number; total: number };
    relaciones: { cubiertos: number; por_especializacion: number; total: number } };
  perfil_agn: { total: number; cubierto: number; parcial: number; ausente: number; no_adoptado: number; codigos_agn_incorrectos: number };
  consultas: { titulo: string; consulta: string }[];
}
interface Resultado { head: { vars: string[] }; results: { bindings: Record<string, { value: string }>[] } }

const num = (x: number) => x.toLocaleString("es-CO");

function Consulta({ titulo, consulta }: { titulo: string; consulta: string }) {
  const [r, setR] = useState<Resultado | null>(null);
  const [error, setError] = useState("");
  const [abierta, setAbierta] = useState(false);

  async function ejecutar() {
    setError("");
    try {
      setR(await pedir<Resultado>(`/api/publico/sparql?query=${encodeURIComponent(consulta)}`));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo ejecutar la consulta.");
    }
  }

  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">{titulo}</div>
      <div className="tarjeta-cuerpo">
        <button type="button" className="enlace" onClick={() => setAbierta(!abierta)}>
          {abierta ? "Ocultar la consulta SPARQL" : "Ver la consulta SPARQL"}</button>
        {abierta && <pre className="codigo-sparql">{consulta}</pre>}
        <div className="acciones"><button type="button" className="boton chico" onClick={ejecutar}>Ejecutar sobre todo el acervo</button></div>
        {error && <div className="aviso error" role="alert">{error}</div>}
        {r && (r.results.bindings.length === 0 ? <p className="meta">Sin resultados todavía.</p> : (
          <div className="tabla-desplazable">
            <table className="tabla-permisos">
              <thead><tr>{r.head.vars.map((v) => <th key={v}>{v}</th>)}</tr></thead>
              <tbody>
                {r.results.bindings.slice(0, 20).map((fila, i) => (
                  <tr key={i}>{r.head.vars.map((v) => <td key={v}>{fila[v]?.value ?? "—"}</td>)}</tr>
                ))}
              </tbody>
            </table>
            {r.results.bindings.length > 20 && <p className="meta">Se muestran 20 de {r.results.bindings.length}.</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function AdopcionRic() {
  const [a, setA] = useState<Adopcion | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    pedir<Adopcion>("/api/exportacion/adopcion-ric").then(setA)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo evaluar la adopción de RiC."));
  }, []);
  if (error) return <div className="aviso error" role="alert">{error}</div>;
  if (!a) return <div className="cargando">Evaluando…</div>;
  const { atributos: at, relaciones: re } = a.cobertura;
  const c = a.conformidad;
  return (
    <>
      <div className="tarjeta">
        <div className="tarjeta-cab">Nivel de adopción de RiC</div>
        <div className="tarjeta-cuerpo">
          <p style={{ marginTop: 0 }}>
            <span className={`insignia ${a.nivel.codigo === 3 ? "bien" : "alerta"}`}>Nivel {a.nivel.codigo}</span>{" "}
            <strong style={{ fontSize: "1.15rem" }}>{a.nivel.nombre}</strong>
            <span className="meta"> · {a.cumplidos} de {a.criterios.length} criterios cumplidos
              ({a.criterios.filter((k) => k.en_uso).length} ya en uso en el acervo), medidos ahora con los datos del sistema</span>
          </p>
          <ol className="escala-ric" aria-label="Escala de niveles de adopción de RiC">
            {a.niveles.map((n) => (
              <li key={n.codigo} className={n.codigo === a.nivel.codigo ? "actual" : n.codigo < a.nivel.codigo ? "superado" : undefined}
                  aria-current={n.codigo === a.nivel.codigo ? "step" : undefined}>
                <strong>{n.codigo}. {n.nombre}</strong><span>{n.que}</span>
              </li>
            ))}
          </ol>
          <p className="meta" style={{ marginBottom: 0 }}>RiC no define niveles de conformidad; esta escala y sus siete criterios son la
            propuesta de la investigación para que la afirmación «el sistema es nativo en RiC» se pueda verificar.</p>
        </div>
      </div>

      <div className="resumen-preservacion">
        <div className="cifra"><strong>{at.cubiertos + at.por_especializacion} / {at.total}</strong><span>Atributos de RiC-CM 1.0</span></div>
        <div className="cifra"><strong>{re.cubiertos + re.por_especializacion} / {re.total}</strong><span>Relaciones de RiC-CM citadas por RiC-O</span></div>
        <div className="cifra"><strong>{c.conformes} / {c.grafos}</strong><span>Grafos guardados conformes (OWL y SHACL)</span></div>
        <div className="cifra"><strong>{c.clases_usadas} / {c.clases_total}</strong><span>Clases de RiC-O 1.1 en uso</span></div>
        <div className="cifra"><strong>{num(c.tripletas)}</strong><span>Tripletas publicadas</span></div>
        <div className="cifra"><strong>{a.perfil_agn.cubierto} / {a.perfil_agn.total}</strong><span>Elementos del Esquema del AGN cubiertos</span></div>
      </div>

      <h3>Los siete criterios de un sistema nativo en RiC</h3>
      {a.criterios.map((k) => (
        <div className="tarjeta" key={k.numero}>
          <div className="tarjeta-cab">
            <span>{k.numero}. {k.criterio}</span>{" "}
            <span>
              {k.estado === "cumplido" && !k.en_uso && <span className="insignia">Sin casos aún en el acervo</span>}{" "}
              <span className={`insignia ${k.estado === "cumplido" ? "bien" : "alerta"}`}>{k.estado === "cumplido" ? "Cumplido" : "Parcial"}</span>
            </span>
          </div>
          <div className="tarjeta-cuerpo">
            {k.motivo && <div className="aviso alerta" role="status">{k.motivo}</div>}
            {k.estado === "cumplido" && !k.en_uso && <p className="meta" style={{ marginTop: 0 }}>La capacidad existe y la
              demuestra la prueba automática; el acervo todavía no tiene casos que la ejerzan.</p>}
            <ul style={{ marginTop: 0 }}>{k.evidencia.map((e) => <li key={e}>{e}</li>)}</ul>
            <p className="meta" style={{ marginBottom: 0 }}><strong>Cómo se verifica:</strong> {k.verificacion}.
              {" "}<strong>Prueba automática:</strong> <code>{k.prueba}</code></p>
          </div>
        </div>
      ))}

      <Interoperabilidad />

      <h3>Compruébelo usted: consultas sobre todo el acervo</h3>
      <p className="meta">Cada consulta se ejecuta en el punto SPARQL público, sobre la unión de los grafos de todos los fondos.
        Nunca incluye lo clasificado o reservado.</p>
      {a.consultas.map((q) => <Consulta key={q.titulo} {...q} />)}
    </>
  );
}

interface Prueba { prueba: string; norma: string; superada: boolean; detalle: string }
interface Informe { fondo: { titulo: string }; tripletas: number; clases: string[]; superadas: number; total: number; pruebas: Prueba[] }

// Prueba de interoperabilidad: lo que RICORA publica del fondo activo, ¿lo puede leer otro sistema?
// Se ejecuta en el servidor sobre lo público (sin lo restringido) y no guarda nada.
function Interoperabilidad() {
  const { fondo } = useFondo();
  const [inf, setInf] = useState<Informe | null>(null);
  const [probando, setProbando] = useState(false);
  const [error, setError] = useState("");
  async function probar() {
    if (!fondo) return;
    setError(""); setProbando(true);
    try {
      setInf(await pedir<Informe>(`/api/exportacion/interoperabilidad?fondo_id=${fondo.id}`));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo hacer la prueba.");
    } finally {
      setProbando(false);
    }
  }
  return (
    <>
      <h3>Prueba de interoperabilidad</h3>
      <div className="tarjeta">
        <div className="tarjeta-cab">
          <span>¿Otro sistema puede leer lo que RICORA publica{fondo ? ` de «${fondo.titulo}»` : ""}?</span>
          <button type="button" className="boton chico primario" disabled={!fondo || probando} onClick={probar}>
            {probando ? "Probando…" : inf ? "Volver a probar" : "Hacer la prueba"}</button>
        </div>
        <div className="tarjeta-cuerpo">
          {!inf && !error && <p className="meta" style={{ margin: 0 }}>Comprueba lo público del fondo frente a RiC-O 1.1, el perfil SHACL,
            cuatro formatos de la web de datos, el importador de RiC-O, EAD3 y EAC-CPF, y los enlaces con Wikidata o VIAF.
            No guarda nada; queda en la auditoría que se hizo.</p>}
          {error && <div className="aviso error" role="alert">{error}</div>}
          {inf && (
            <>
              <p style={{ marginTop: 0 }}><strong>{inf.superadas} de {inf.total} pruebas superadas</strong>
                <span className="meta"> · {inf.tripletas.toLocaleString("es-CO")} tripletas · {inf.clases.length} clases de RiC-O</span></p>
              <div className="tabla-desplazable">
                <table className="tabla-datos">
                  <thead><tr><th>Prueba</th><th>Norma</th><th>Resultado</th><th>Detalle</th></tr></thead>
                  <tbody>
                    {inf.pruebas.map((p) => (
                      <tr key={p.prueba}>
                        <td><strong>{p.prueba}</strong></td>
                        <td className="meta">{p.norma}</td>
                        <td>{p.superada ? <span className="insignia bien">✓ Superada</span> : <span className="insignia alerta">Pendiente</span>}</td>
                        <td>{p.detalle}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
