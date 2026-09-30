import type { Regla } from "@/lib/contrasena";

export function Reglas({ reglas }: { reglas: Regla[] }) {
  return (
    <ul className="reglas" aria-label="Reglas de la contraseña">
      {reglas.map((r) => (
        <li key={r.texto} className={r.cumple ? "cumple" : ""}>
          {r.texto}
        </li>
      ))}
    </ul>
  );
}
