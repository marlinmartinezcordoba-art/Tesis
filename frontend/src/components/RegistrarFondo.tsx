import { useState, type FormEvent } from "react";
import { ErrorAPI, pedir } from "@/lib/api";
import { useFondo, type Fondo } from "@/lib/fondo";

// Solo el administrador registra fondos: es el punto de partida del trabajo.
export function RegistrarFondo({ alTerminar }: { alTerminar: () => void }) {
  const { recargar, elegir } = useFondo();
  const [titulo, setTitulo] = useState("");
  const [fechas, setFechas] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setError("");
    setEnviando(true);
    try {
      const f = await pedir<Fondo>("/api/fondos", {
        method: "POST",
        body: JSON.stringify({ titulo, fechas_extremas: fechas || null }),
      });
      await recargar();
      elegir(f.id);
      alTerminar();
    } catch (err) {
      setError(err instanceof ErrorAPI ? err.message : "No se pudo registrar el fondo.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form className="formulario-nuevo" onSubmit={enviar}>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="rejilla">
        <div className="campo">
          <label htmlFor="f-titulo">Nombre del fondo</label>
          <input id="f-titulo" className="entrada" required minLength={3} value={titulo}
                 placeholder="Correspondencia municipal" onChange={(e) => setTitulo(e.target.value)} />
        </div>
        <div className="campo">
          <label htmlFor="f-fechas">Fechas extremas (opcional)</label>
          <input id="f-fechas" className="entrada" value={fechas} placeholder="1930–1955"
                 onChange={(e) => setFechas(e.target.value)} />
        </div>
      </div>
      <div className="acciones">
        <button className="boton primario" type="submit" disabled={enviando}>{enviando ? "Registrando…" : "Registrar fondo"}</button>
        <button className="boton" type="button" onClick={alTerminar}>Cancelar</button>
      </div>
    </form>
  );
}
