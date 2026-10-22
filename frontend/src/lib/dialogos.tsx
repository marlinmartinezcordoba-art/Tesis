import { useEffect, useState } from "react";
import { Ventana } from "@/components/Ventana";

// Diálogos propios en lugar de las ventanas del navegador (confirm, prompt,
// alert): se ven como el resto del sistema, explican qué pasa y se cierran con
// Esc. Se llaman como funciones y devuelven una promesa:
//   if (!(await confirmar("¿Anular…?"))) return;
//   const motivo = await pedirTexto("Motivo de la anulación", { minimo: 10 });

interface Pedido {
  tipo: "confirmar" | "texto" | "aviso";
  titulo: string;
  texto: string;
  aceptar: string;
  peligro: boolean;
  minimo: number;
  valor: string;
  opcional: boolean;
  resolver: (v: unknown) => void;
}

let mostrar: ((p: Pedido) => void) | null = null;
const pendientes: Pedido[] = [];

function pedir<T>(p: Omit<Pedido, "resolver">): Promise<T> {
  return new Promise<T>((resolver) => {
    const pedido = { ...p, resolver: resolver as (v: unknown) => void };
    if (mostrar) mostrar(pedido);
    else pendientes.push(pedido);
  });
}

export function confirmar(texto: string, o: { titulo?: string; aceptar?: string; peligro?: boolean } = {}) {
  return pedir<boolean>({ tipo: "confirmar", titulo: o.titulo || "Confirmar", texto, aceptar: o.aceptar || "Sí, continuar",
    peligro: o.peligro ?? false, minimo: 0, valor: "", opcional: false });
}

export function pedirTexto(texto: string, o: { titulo?: string; aceptar?: string; minimo?: number; valor?: string;
  opcional?: boolean } = {}) {
  return pedir<string | null>({ tipo: "texto", titulo: o.titulo || "Escriba el motivo", texto, aceptar: o.aceptar || "Aceptar",
    peligro: false, minimo: o.minimo ?? 0, valor: o.valor || "", opcional: o.opcional ?? false });
}

export function avisar(texto: string, titulo = "Aviso") {
  return pedir<void>({ tipo: "aviso", titulo, texto, aceptar: "Entendido", peligro: false, minimo: 0, valor: "",
    opcional: true });
}

/** Se monta una vez (en App): muestra los diálogos pedidos, de a uno. */
export function Dialogos() {
  const [cola, setCola] = useState<Pedido[]>(() => pendientes.splice(0));
  const [valor, setValor] = useState("");
  useEffect(() => {
    mostrar = (p) => setCola((c) => [...c, p]);
    return () => { mostrar = null; };
  }, []);
  const actual = cola[0];
  useEffect(() => setValor(actual?.valor || ""), [actual]);
  if (!actual) return null;

  const terminar = (v: unknown) => {
    actual.resolver(v);
    setCola((c) => c.slice(1));
  };
  const cancelar = () => terminar(actual.tipo === "confirmar" ? false : actual.tipo === "texto" ? null : undefined);
  const corto = actual.tipo === "texto" && !actual.opcional && valor.trim().length < Math.max(actual.minimo, 1);

  return (
    <Ventana titulo={actual.titulo} alCerrar={cancelar}>
      <form className="dialogo" onSubmit={(e) => {
        e.preventDefault();
        if (corto) return;
        terminar(actual.tipo === "confirmar" ? true : actual.tipo === "texto" ? valor.trim() : undefined);
      }}>
        <p className="dialogo-texto">{actual.texto}</p>
        {actual.tipo === "texto" && (
          <>
            <textarea className="entrada" rows={3} value={valor} onChange={(e) => setValor(e.target.value)}
                      aria-label={actual.titulo} />
            {actual.minimo > 0 && (
              <p className="meta">Al menos {actual.minimo} caracteres · llevas {valor.trim().length}.</p>
            )}
          </>
        )}
        <div className="acciones dialogo-acciones">
          {actual.tipo !== "aviso" && <button type="button" className="boton" onClick={cancelar}>Cancelar</button>}
          <button type="submit" className={`boton primario${actual.peligro ? " peligro" : ""}`} disabled={corto}>
            {actual.aceptar}
          </button>
        </div>
      </form>
    </Ventana>
  );
}
