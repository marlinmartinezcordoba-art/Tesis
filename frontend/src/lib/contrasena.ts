// Las mismas reglas que verifica el backend (app/core/seguridad.py), para
// mostrarlas mientras la persona escribe. El backend las vuelve a
// verificar: la interfaz solo ayuda, no decide.

export interface Regla {
  texto: string;
  cumple: boolean;
}

export function reglasContrasena(contrasena: string, confirmacion: string, correo = ""): Regla[] {
  const inicioCorreo = correo.split("@")[0].toLowerCase();
  return [
    { texto: "Al menos 10 caracteres", cumple: contrasena.length >= 10 },
    { texto: "Al menos una letra", cumple: /\p{L}/u.test(contrasena) },
    { texto: "Al menos un número", cumple: /\d/.test(contrasena) },
    {
      texto: "No contiene la parte inicial de su correo",
      cumple: contrasena.length > 0 && !(inicioCorreo.length >= 4 && contrasena.toLowerCase().includes(inicioCorreo)),
    },
    { texto: "Las dos contraseñas coinciden", cumple: contrasena.length > 0 && contrasena === confirmacion },
  ];
}
