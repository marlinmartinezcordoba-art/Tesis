import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ErrorAPI, pedir } from "@/lib/api";
import { NIVEL_NOMBRE } from "@/lib/descripcion";
import { useFondo } from "@/lib/fondo";
import { fecha, peso } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";

interface PorDescribir {
  id: string;
  nombre: string;
  tamano_bytes: number;
  formato: string | null;
  expediente: string | null;
  origen_texto: string | null;
  cargado_en: string;
  en_edicion_por: string | null;
}

interface Publicada {
  id: string;
  titulo: string;
  nivel: string;
  documentos: number;
  publicado_en: string | null;
  actualizado_en: string | null;
  en_edicion_por: string | null;
}

const TEXTO: Record<string, string> = { capa_de_texto: "con texto", ocr: "texto por OCR", sin_texto: "sin texto" };

function extension(nombre: string) {
  const p = nombre.split(".");
  return p.length > 1 ? p.pop()!.slice(0, 4) : "·";
}

export function Descripcion() {
  const { usuario } = useSesion();
  const { fondo } = useFondo();
  const navegar = useNavigate();
  const ubicacion = useLocation();
  const puede = usuario?.rol === "administrador" || usuario?.rol === "archivista";
  const [pestana, setPestana] = useState<"cola" | "publicadas">("cola");
  const [cola, setCola] = useState<PorDescribir[] | null>(null);
  const [publicadas, setPublicadas] = useState<Publicada[] | null>(null);
  const [seleccion, setSeleccion] = useState<string[]>([]);
  const [nivel, setNivel] = useState("expediente");
  const [abriendo, setAbriendo] = useState(false);
  const [error, setError] = useState("");
  const aviso = (ubicacion.state as { aviso?: string } | null)?.aviso;

  const cargar = useCallback(async () => {
    if (!fondo) return;
    try {
      const [c, p] = await Promise.all([
        pedir<PorDescribir[]>(`/api/descripcion/cola?fondo_id=${fondo.id}`),
        pedir<Publicada[]>(`/api/descripcion/publicadas?fondo_id=${fondo.id}`),
      ]);
      setCola(c);
      setPublicadas(p);
      setSeleccion((s) => s.filter((id) => c.some((x) => x.id === id && !x.en_edicion_por)));
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar la cola.");
    }
  }, [fondo]);

  useEffect(() => {
    cargar();
    const t = setInterval(cargar, 30000);
    return () => clearInterval(t);
  }, [cargar]);

  async function describir(ids: string[], nivelConjunto?: string) {
    setError("");
    setAbriendo(true);
    try {
      const espacio = await pedir<{ trabajo_id: string }>("/api/descripcion/iniciar", {
        method: "POST",
        body: JSON.stringify({ instanciacion_ids: ids, ...(nivelConjunto ? { nivel: nivelConjunto } : {}) }),
      });
      navegar(`/descripcion/trabajo/${espacio.trabajo_id}`, { state: { espacio } });
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo abrir la descripción.");
      setAbriendo(false);
      cargar();
    }
  }

  if (!fondo) return <div className="vacio">Primero debe existir un fondo (se registra en Ingesta).</div>;

  const alternar = (id: string) => setSeleccion((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <>
      <div className="pestanas" role="tablist">
        <button type="button" role="tab" aria-selected={pestana === "cola"} className={`pestana${pestana === "cola" ? " activa" : ""}`}
                onClick={() => setPestana("cola")}>
          Por describir {cola && cola.length > 0 && <span className="contador">{cola.length}</span>}
        </button>
        <button type="button" role="tab" aria-selected={pestana === "publicadas"} className={`pestana${pestana === "publicadas" ? " activa" : ""}`}
                onClick={() => setPestana("publicadas")}>
          Descritas
        </button>
      </div>
      {aviso && <div className="aviso bien" role="status">{aviso}</div>}
      {error && <div className="aviso error" role="alert">{error}</div>}

      {pestana === "cola" ? (
        <>
          <h1>Por describir</h1>
          <p className="sub">
            Documentos que ya salieron de ingesta y están listos. Abra uno para describirlo solo, o seleccione varios para
            describirlos como conjunto a nivel de expediente, subserie o serie.
          </p>
          <div className="tarjeta">
            <div className="tarjeta-cab">
              {cola === null ? "Cargando…" : `${cola.length} documento${cola.length === 1 ? "" : "s"} listo${cola.length === 1 ? "" : "s"}`}
            </div>
            {cola !== null && cola.length === 0 && (
              <div className="vacio">No hay documentos por describir. Los que termina de procesar la ingesta aparecen aquí solos.</div>
            )}
            {cola?.map((d) => (
              <div className="fila" key={d.id}>
                {puede && (
                  <input type="checkbox" aria-label={`Seleccionar ${d.nombre}`} disabled={!!d.en_edicion_por}
                         checked={seleccion.includes(d.id)} onChange={() => alternar(d.id)} />
                )}
                <span className="icono-archivo" aria-hidden="true">{extension(d.nombre)}</span>
                <div className="fila-principal">
                  <div className="nombre">{d.nombre}</div>
                  <div className="meta">
                    {d.expediente ? `Expediente: ${d.expediente}` : "Sin expediente asignado"} · {peso(d.tamano_bytes)}
                    {d.origen_texto && ` · ${TEXTO[d.origen_texto] || d.origen_texto}`} · cargado {fecha(d.cargado_en)}
                  </div>
                </div>
                {d.en_edicion_por ? (
                  <span className="insignia proceso">En edición por {d.en_edicion_por}</span>
                ) : puede && (
                  <button type="button" className="boton chico" disabled={abriendo} onClick={() => describir([d.id])}>Describir</button>
                )}
              </div>
            ))}
            {puede && seleccion.length > 1 && (
              <div className="confirmar">
                <span>{seleccion.length} documentos seleccionados</span>
                <div className="acciones" style={{ alignItems: "center" }}>
                  <label className="pista" style={{ margin: 0 }} htmlFor="nivel-conjunto">Son un</label>
                  <select id="nivel-conjunto" className="selector" style={{ width: "auto" }} value={nivel} onChange={(e) => setNivel(e.target.value)}>
                    <option value="expediente">Expediente</option>
                    <option value="subserie">Subserie</option>
                    <option value="serie">Serie</option>
                  </select>
                  <button type="button" className="boton primario" disabled={abriendo} onClick={() => describir(seleccion, nivel)}>
                    {abriendo ? "Abriendo…" : "Describir como conjunto"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      ) : (
        <>
          <h1>Descritas</h1>
          <p className="sub">Descripciones ya publicadas en el fondo. Se pueden reabrir para corregirlas; cada cambio queda en auditoría.</p>
          <div className="tarjeta">
            {publicadas === null ? <div className="vacio">Cargando…</div> : publicadas.length === 0 ? (
              <div className="vacio">Todavía no se ha publicado ninguna descripción.</div>
            ) : publicadas.map((p) => (
              <div className="fila" key={p.id}>
                <div className="fila-principal">
                  <div className="nombre">{p.titulo}</div>
                  <div className="meta">
                    {NIVEL_NOMBRE[p.nivel] || p.nivel} · {p.documentos} documento{p.documentos === 1 ? "" : "s"} · publicada {fecha(p.publicado_en)}
                    {p.actualizado_en && ` · corregida ${fecha(p.actualizado_en)}`}
                  </div>
                </div>
                {p.en_edicion_por && <span className="insignia proceso">En edición por {p.en_edicion_por}</span>}
                <button type="button" className="boton chico" onClick={() => navegar(`/descripcion/registro/${p.id}`)}>
                  {puede ? "Ver y corregir" : "Ver"}
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
