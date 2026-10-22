import { pedirTexto } from "@/lib/dialogos";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ErrorAPI, pedir, subir } from "@/lib/api";
import { useSesion } from "@/lib/sesion";
import { type Concepto, type Normalizacion, type Tesauro, normalizar } from "@/lib/tesauros";
import { Ventana } from "@/components/Ventana";

// Tesauros (UNESCO, ambiental de Minambiente u otro): se importan una vez,
// los comparten todos los fondos y normalizan las materias al describir.

function mensaje(err: unknown, porDefecto: string) {
  return err instanceof ErrorAPI ? err.message : porDefecto;
}

export function FichaConcepto({ c }: { c: Concepto }) {
  return (
    <div className="ficha-concepto">
      <strong>{c.preferente}</strong>
      <span className="meta"> · {c.tesauro.nombre}{c.notacion ? ` · ${c.notacion}` : ""}</span>
      {c.ruta.length > 0 && <div className="meta">Término general: {c.ruta.join(" › ")}</div>}
      {c.no_preferentes.length > 0 && <div className="meta">Usado por: {c.no_preferentes.join("; ")}</div>}
      {c.nota_alcance && <div className="meta">Nota de alcance: {c.nota_alcance}</div>}
      {c.uri && <div className="meta"><a href={c.uri} target="_blank" rel="noreferrer">{c.uri}</a></div>}
    </div>
  );
}

// Sugerencia mientras se escribe una materia: el concepto exacto (o al que
// lleva un término no preferente) y los parecidos, para elegir uno.
export function SugerenciaTesauro({ texto, elegido, alElegir }: {
  texto: string; elegido: string | null; alElegir: (c: Concepto | null) => void;
}) {
  const [n, setN] = useState<Normalizacion | null>(null);
  useEffect(() => {
    if (texto.trim().length < 3) {
      setN(null);
      return;
    }
    const t = setTimeout(() => normalizar(texto.trim()).then(setN).catch(() => setN(null)), 300);
    return () => clearTimeout(t);
  }, [texto]);
  if (!n) return null;
  if (!n.exacto && !n.parecidos.length) {
    return <div className="aviso" role="status">No está en ningún tesauro: quedará como término local del fondo.</div>;
  }
  return (
    <div className="sugerencia-tesauro" role="status">
      {n.exacto && (
        <div className="aviso bien">
          {n.via === "no_preferente"
            ? <>«{n.exacto.etiqueta_coincidente}» es un término no preferente: se usará <strong>«{n.exacto.preferente}»</strong>.</>
            : <>Término preferente del tesauro.</>}
          <FichaConcepto c={n.exacto} />
        </div>
      )}
      {!n.exacto && n.parecidos.length > 0 && <p className="meta">¿Quiso decir alguno de estos? Elegirlo normaliza la materia.</p>}
      {n.parecidos.map((c) => (
        <label key={c.id} className="opcion-concepto">
          <input type="radio" name="concepto" checked={elegido === c.id} onChange={() => alElegir(c)} />
          <FichaConcepto c={c} />
        </label>
      ))}
      {!n.exacto && n.parecidos.length > 0 && (
        <label className="opcion-concepto">
          <input type="radio" name="concepto" checked={elegido === null} onChange={() => alElegir(null)} />
          Ninguno: dejarlo como término local
        </label>
      )}
    </div>
  );
}

function Importar({ alImportar }: { alImportar: () => void }) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [nombre, setNombre] = useState("");
  const [fuente, setFuente] = useState("");
  const [licencia, setLicencia] = useState("");
  const [avance, setAvance] = useState<number | null>(null);
  const [error, setError] = useState("");
  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (!archivo) return;
    setError("");
    const datos = new FormData();
    datos.append("archivo", archivo);
    datos.append("nombre", nombre);
    datos.append("fuente", fuente);
    datos.append("licencia", licencia);
    try {
      setAvance(0);
      await subir("/api/tesauros", datos, setAvance);
      setArchivo(null);
      setNombre("");
      alImportar();
    } catch (err) {
      setError(mensaje(err, "No se pudo importar."));
    } finally {
      setAvance(null);
    }
  }
  return (
    <form onSubmit={enviar}>
      <div>
        <p className="meta">
          SKOS (Turtle, RDF/XML, N-Triples o JSON-LD), como el Tesauro de la UNESCO, que se descarga libre desde su
          sitio. O una tabla Excel o CSV con las columnas <strong>Término preferente</strong>, <strong>Usado por</strong>{" "}
          (términos no preferentes separados por «;»), <strong>Término general</strong>, <strong>Nota de alcance</strong>,{" "}
          <strong>URI</strong> y <strong>Código</strong>, para un tesauro que no publica SKOS (como el ambiental de
          Minambiente). Verifique la licencia antes de importar.
        </p>
        <label className="meta" htmlFor="tes-archivo">Archivo</label>
        <input id="tes-archivo" type="file" accept=".ttl,.rdf,.xml,.nt,.jsonld,.json,.xlsx,.csv,.tsv"
               onChange={(e) => setArchivo(e.target.files?.[0] || null)} />
        <label className="meta" htmlFor="tes-nombre" style={{ display: "block", marginTop: 8 }}>Nombre</label>
        <input id="tes-nombre" className="entrada" required minLength={3} value={nombre} placeholder="Tesauro de la UNESCO"
               onChange={(e) => setNombre(e.target.value)} />
        <label className="meta" htmlFor="tes-fuente" style={{ display: "block", marginTop: 8 }}>Fuente (sitio o publicación)</label>
        <input id="tes-fuente" className="entrada" value={fuente} onChange={(e) => setFuente(e.target.value)} />
        <label className="meta" htmlFor="tes-licencia" style={{ display: "block", marginTop: 8 }}>Licencia</label>
        <input id="tes-licencia" className="entrada" value={licencia} placeholder="CC BY-SA 3.0 IGO"
               onChange={(e) => setLicencia(e.target.value)} />
        {error && <div className="aviso error" role="alert">{error}</div>}
        <div className="acciones">
          <button type="submit" className="boton chico primario" disabled={!archivo || avance !== null}>
            {avance !== null ? `Importando… ${Math.round(avance * 100)} %` : "Importar"}</button>
        </div>
      </div>
    </form>
  );
}

function Probar() {
  const [texto, setTexto] = useState("");
  const [elegido, setElegido] = useState<string | null>(null);
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab">Probar la normalización</div>
      <div className="tarjeta-cuerpo">
        <p className="meta">Escriba un tema como lo escribiría al describir: el sistema dice qué término preferente usará.</p>
        <input className="entrada" aria-label="Término" value={texto} onChange={(e) => setTexto(e.target.value)}
               placeholder="archivos históricos" />
        <SugerenciaTesauro texto={texto} elegido={elegido} alElegir={(c) => setElegido(c?.id || null)} />
      </div>
    </div>
  );
}

export function Tesauros() {
  const { usuario } = useSesion();
  const esAdmin = !!usuario?.es_administrador;
  const [lista, setLista] = useState<Tesauro[] | null>(null);
  const [importando, setImportando] = useState(false);
  const [error, setError] = useState("");
  const cargar = useCallback(() => {
    pedir<Tesauro[]>("/api/tesauros").then(setLista).catch((err) => setError(mensaje(err, "No se pudieron cargar.")));
  }, []);
  useEffect(cargar, [cargar]);

  async function anular(t: Tesauro) {
    const motivo = await pedirTexto(`Las materias ya normalizadas con «${t.nombre}» no cambian.`,
      { titulo: "Anular el tesauro", aceptar: "Anular", minimo: 5 });
    if (!motivo) return;
    try {
      await pedir(`/api/tesauros/${t.id}/anular`, { method: "POST", body: JSON.stringify({ motivo }) });
      cargar();
    } catch (err) {
      setError(mensaje(err, "No se pudo anular."));
    }
  }

  return (
    <>
      <h1>Tesauros</h1>
      <p className="sub">
        Normalizan las materias (temas) de la descripción: quien escribe un término no preferente («archivos históricos»)
        recibe el preferente del tesauro («Archivo histórico»), y todos los documentos con el mismo tema quedan unidos al
        mismo nodo del grafo. En la exportación RiC-O, cada materia lleva el enlace al concepto de origen (skos:exactMatch).
      </p>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="tarjeta">
        <div className="tarjeta-cab">Importados</div>
        <div className="tarjeta-cuerpo">
          {!lista ? <div className="cargando">Cargando…</div> : lista.length === 0 ? (
            <p className="meta">Todavía no hay tesauros. {esAdmin ? "Importe uno con «+ Importar un tesauro»." : "Los importa la administración."}</p>
          ) : lista.map((t) => (
            <div key={t.id} className="fila">
              <div className="fila-principal">
                <div className="nombre">{t.nombre}</div>
                <div className="meta">{t.conceptos.toLocaleString("es-CO")} conceptos · {t.formato.toUpperCase()}
                  {t.licencia ? ` · ${t.licencia}` : ""}{t.fuente ? ` · ${t.fuente}` : ""}</div>
              </div>
              <span className={`insignia ${t.estado === "vigente" ? "bien" : "proceso"}`}>{t.estado === "vigente" ? "Vigente" : "Anulado"}</span>
              {esAdmin && t.estado === "vigente" && (
                <button type="button" className="boton chico" onClick={() => anular(t)}>Anular</button>
              )}
            </div>
          ))}
        </div>
      </div>
      <Probar />
      {esAdmin && (
        <div className="acciones">
          <button type="button" className="boton chico primario" onClick={() => setImportando(true)}>+ Importar un tesauro</button>
        </div>
      )}
      {importando && (
        <Ventana titulo="Importar un tesauro" alCerrar={() => setImportando(false)}>
          <Importar alImportar={() => { setImportando(false); cargar(); }} />
        </Ventana>
      )}
    </>
  );
}
