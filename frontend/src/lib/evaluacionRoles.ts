// Qué pasos hace cada rol. «Ambas» conserva el flujo completo de una sola persona.
export type Paso = "ciega" | "asistida" | "calificar" | "adjudicar";
export const PASOS_POR_ROL: Record<string, Paso[]> = {
  descriptora: ["ciega"], validadora: ["asistida"], calificadora: ["calificar"], adjudicadora: ["adjudicar"],
  piloto: ["ciega", "asistida"], ambas: ["ciega", "asistida", "calificar"],
};
export const NOMBRE_PASO: Record<Paso, string> = { ciega: "A ciegas", asistida: "Con la propuesta", calificar: "Calificación",
  adjudicar: "Referencia adjudicada" };
export const PISTA_PASO: Record<Paso, string> = { ciega: "Describir a ciegas, sin ver la propuesta",
  asistida: "Describir con la propuesta del motor", calificar: "Calificar la propuesta de 1 a 5",
  adjudicar: "Consolidar la referencia a partir de dos descripciones ciegas, sin ver la propuesta" };
export const NOMBRE_ROL: Record<string, string> = { descriptora: "describe a ciegas", validadora: "valida con la propuesta",
  calificadora: "califica la propuesta", adjudicadora: "adjudica la referencia", piloto: "prueba piloto",
  ambas: "describe y califica" };
