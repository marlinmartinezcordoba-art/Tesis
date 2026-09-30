import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { FormEntidad, PreguntaVocabulario, type EntidadManual } from "@/components/Vocabulario";
import { ErrorAPI, pedir } from "@/lib/api";
import {
  EN_VOCABULARIO, NIVEL_NOMBRE, ORIGEN_NOMBRE, ROL_NOMBRE, SUBTIPO_NOMBRE, TIPO_CLASE, TIPO_NOMBRE, nivelesSuperiores,
  verificarVocabulario, type NivelSuperior, type TipoEntidad, type Verificacion,
} from "@/lib/descripcion";
import { fecha } from "@/lib/formato";
import { useSesion } from "@/lib/sesion";

interface EntidadRegistrada {
  relacion_id: string;
  tipo: TipoEntidad;
  valor: string;
  subtipo: string | null;
  rol: string | null;
  codigo_ric: string;
  uri_rico: string | null;
  fragmento: string | null;
  origen: string;
  confianza: number | null;
  fecha_normalizada?: string | null;
}

interface Registro {
  id: string;
  nivel: string;
  titulo: string;
  alcance_contenido: string | null;
  fondo_id: string;
  incluido_en: { id: string; titulo: string; nivel: string } | null;
  forma_documental: { id: string; nombre: string; origen: string } | null;
  entidades: EntidadRegistrada[];
  instanciaciones: { id: string; nombre: string }[];
  origen_titulo: string | null;
  origen_alcance: string | null;
  publicado_en: string | null;
  actualizado_en: string | null;
}

interface Nueva extends EntidadManual {
  clave: string;
  verif: Verificacion;
}

// Descripción publicada: vista interna (con procedencia de cada dato) y corrección.
export function RegistroDescripcion() {
  const { id = "" } = useParams();
  const navegar = useNavigate();
  const { usuario } = useSesion();
  const puede = usuario?.rol === "administrador" || usuario?.rol === "archivista";
  const [registro, setRegistro] = useState<Registro | null>(null);
  const [trabajo, setTrabajo] = useState<string | null>(null);
  const [titulo, setTitulo] = useState("");
  const [alcance, setAlcance] = useState("");
  const [incluido, setIncluido] = useState("");
  const [superiores, setSuperiores] = useState<NivelSuperior[]>([]);
  const [quitar, setQuitar] = useState<string[]>([]);
  const [quitarForma, setQuitarForma] = useState(false);
  const [nuevas, setNuevas] = useState<Nueva[]>([]);
  const [agregando, setAgregando] = useState(false);
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);

  function cargar(r: Registro) {
    setRegistro(r);
    setTitulo(r.titulo);
    setAlcance(r.alcance_contenido || "");
    setIncluido(r.incluido_en?.id || "");
    setQuitar([]);
    setQuitarForma(false);
    setNuevas([]);
    nivelesSuperiores(r.fondo_id, r.nivel).then(setSuperiores).catch(() => undefined);
  }

  useEffect(() => {
    pedir<Registro>(`/api/descripcion/registros/${id}`).then(cargar)
      .catch((err) => setError(err instanceof ErrorAPI ? err.message : "No se pudo cargar la descripción."));
  }, [id]);

  async function corregir() {
    setError("");
    try {
      const r = await pedir<{ trabajo_id: string; descripcion: Registro }>(`/api/descripcion/registros/${id}/reabrir`, { method: "POST" });
      setTrabajo(r.trabajo_id);
      cargar(r.descripcion);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo abrir para corregir.");
    }
  }

  async function agregar(e: EntidadManual) {
    if (!registro) return;
    const nueva: Nueva = { ...e, clave: `n${Date.now()}`, verif: { estado: EN_VOCABULARIO.includes(e.tipo) ? "verificando" : "no_aplica", coincidencias: [] } };
    setNuevas((l) => [...l, nueva]);
    setAgregando(false);
    if (!EN_VOCABULARIO.includes(e.tipo)) return;
    const c = await verificarVocabulario(registro.fondo_id, e.tipo, e.valor).catch(() => []);
    setNuevas((l) => l.map((n) => (n.clave === nueva.clave
      ? { ...n, verif: c.length ? { estado: "pregunta", coincidencias: c } : { estado: "resuelta", coincidencias: [], crearNueva: true } }
      : n)));
  }

  async function guardar() {
    if (!registro || !trabajo) return;
    setError("");
    setGuardando(true);
    try {
      const r = await pedir<Registro>(`/api/descripcion/${registro.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          trabajo_id: trabajo, titulo, alcance_contenido: alcance,
          incluido_en_id: incluido !== registro.incluido_en?.id ? incluido : null,
          anular_relaciones: quitar, quitar_forma_documental: quitarForma,
          agregar_entidades: nuevas.map((n) => ({
            tipo: n.tipo, valor: n.valor, subtipo: n.subtipo, rol: n.rol, fecha_normalizada: n.fecha_normalizada,
            reutilizar_id: n.verif.reutilizarId || null, crear_nueva: !!n.verif.crearNueva,
          })),
        }),
      });
      setTrabajo(null);
      cargar(r);
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudieron guardar los cambios.");
    } finally {
      setGuardando(false);
    }
  }

  async function descartarCambios() {
    if (trabajo) await pedir(`/api/descripcion/${trabajo}/cancelar`, { method: "POST" }).catch(() => undefined);
    setTrabajo(null);
    if (registro) cargar(registro);
  }

  if (!registro) return error ? <div className="aviso error">{error}</div> : <div className="cargando">Cargando…</div>;
  const editando = !!trabajo;
  const pendientes = nuevas.filter((n) => ["verificando", "pregunta"].includes(n.verif.estado)).length;

  return (
    <>
      <button type="button" className="enlace" onClick={() => navegar("/descripcion")}>← Volver a Descripción</button>
      <h1 style={{ marginTop: 10 }}>{registro.titulo}</h1>
      <p className="sub">
        {NIVEL_NOMBRE[registro.nivel]} · publicada {fecha(registro.publicado_en)}
        {registro.actualizado_en && ` · corregida ${fecha(registro.actualizado_en)}`} · {registro.instanciaciones.map((i) => i.nombre).join(", ")}
      </p>
      {error && <div className="aviso error" role="alert">{error}</div>}

      <div className="tarjeta">
        <div className="tarjeta-cab">
          <span>Descripción</span>
          {puede && !editando && <button type="button" className="boton chico primario" onClick={corregir}>Corregir</button>}
        </div>
        <div className="tarjeta-cuerpo">
          {editando ? (
            <>
              <div className="campo"><label htmlFor="r-titulo">Título</label>
                <input id="r-titulo" className="entrada" value={titulo} onChange={(e) => setTitulo(e.target.value)} /></div>
              <div className="campo"><label htmlFor="r-alcance">Alcance y contenido</label>
                <textarea id="r-alcance" className="entrada" rows={5} value={alcance} onChange={(e) => setAlcance(e.target.value)} /></div>
              <div className="campo"><label htmlFor="r-incluido">Queda incluido en</label>
                <select id="r-incluido" className="selector" value={incluido} onChange={(e) => setIncluido(e.target.value)}>
                  {superiores.map((s) => <option key={s.id} value={s.id}>{NIVEL_NOMBRE[s.nivel]}: {s.titulo}</option>)}
                </select></div>
            </>
          ) : (
            <dl className="pares" style={{ margin: 0 }}>
              <dt>Alcance y contenido</dt><dd>{registro.alcance_contenido || "—"}</dd>
              <dt>Incluido en</dt><dd>{registro.incluido_en ? `${NIVEL_NOMBRE[registro.incluido_en.nivel]}: ${registro.incluido_en.titulo}` : "—"}</dd>
              <dt>Procedencia</dt>
              <dd className="meta" style={{ fontSize: ".82rem" }}>
                Título: {ORIGEN_NOMBRE[registro.origen_titulo || "persona"]}.{" "}
                {registro.origen_alcance && `Alcance: ${ORIGEN_NOMBRE[registro.origen_alcance]}.`}
              </dd>
            </dl>
          )}
        </div>
      </div>

      <div className="tarjeta">
        <div className="tarjeta-cab">Entidades y relaciones RiC</div>
        {registro.forma_documental && (
          <div className={`fila${quitarForma ? " tachada" : ""}`}>
            <span className="insignia bien">Forma documental</span>
            <div className="fila-principal"><div className="nombre">{registro.forma_documental.nombre}</div>
              <div className="meta">Atributo RiC-A13 · {ORIGEN_NOMBRE[registro.forma_documental.origen]}</div></div>
            {editando && <button type="button" className="boton chico" onClick={() => setQuitarForma(!quitarForma)}>{quitarForma ? "Deshacer" : "Quitar"}</button>}
          </div>
        )}
        {registro.entidades.map((e) => (
          <div key={e.relacion_id} className={`fila${quitar.includes(e.relacion_id) ? " tachada" : ""}`}>
            <span className={`insignia ${TIPO_CLASE[e.tipo]}`}>
              {TIPO_NOMBRE[e.tipo]}{e.rol && ROL_NOMBRE[e.rol] ? ` · ${ROL_NOMBRE[e.rol]}` : ""}
            </span>
            <div className="fila-principal">
              <div className="nombre">{e.valor}{e.subtipo ? ` · ${SUBTIPO_NOMBRE[e.subtipo] || e.subtipo}` : ""}{e.fecha_normalizada ? ` (${e.fecha_normalizada})` : ""}</div>
              <div className="meta">
                {e.uri_rico || e.codigo_ric} · {ORIGEN_NOMBRE[e.origen]}{e.confianza !== null ? ` · confianza ${Math.round(e.confianza * 100)} %` : ""}
                {e.fragmento && ` · «${e.fragmento}»`}
              </div>
            </div>
            {editando && (
              <button type="button" className="boton chico"
                      onClick={() => setQuitar((q) => (q.includes(e.relacion_id) ? q.filter((x) => x !== e.relacion_id) : [...q, e.relacion_id]))}>
                {quitar.includes(e.relacion_id) ? "Deshacer" : "Quitar"}
              </button>
            )}
          </div>
        ))}
        {nuevas.map((n) => (
          <div key={n.clave} className="fila" style={{ display: "block" }}>
            <span className={`insignia ${TIPO_CLASE[n.tipo]}`}>{TIPO_NOMBRE[n.tipo]} nueva</span> <b>{n.valor}</b>
            <button type="button" className="boton chico" style={{ marginLeft: 8 }} onClick={() => setNuevas((l) => l.filter((x) => x.clave !== n.clave))}>Quitar</button>
            <PreguntaVocabulario valor={n.valor} verificacion={n.verif}
                                 alDecidir={(v) => setNuevas((l) => l.map((x) => (x.clave === n.clave ? { ...x, verif: v } : x)))} />
          </div>
        ))}
        {editando && (
          <div className="tarjeta-cuerpo">
            {agregando ? <FormEntidad alGuardar={agregar} alCancelar={() => setAgregando(false)} />
              : <button type="button" className="enlace" onClick={() => setAgregando(true)}>+ Agregar entidad</button>}
          </div>
        )}
      </div>

      {editando && (
        <div className="barra-publicar">
          <span>Los cambios quedan en auditoría con el valor anterior y el nuevo. Lo que se quita no se borra: queda anulado.</span>
          <div className="acciones">
            <button type="button" className="boton" onClick={descartarCambios}>Descartar cambios</button>
            <button type="button" className="boton primario" disabled={guardando || pendientes > 0 || titulo.trim().length < 3} onClick={guardar}>
              {guardando ? "Guardando…" : "Guardar cambios"}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
