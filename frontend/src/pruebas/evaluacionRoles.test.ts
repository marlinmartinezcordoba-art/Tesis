// Brecha P1: cada rol ve solo los pasos que le corresponden en «Mis tareas».
// El servidor también lo impide (evaluacion_participantes.PERMITE): esto alinea la pantalla.
import { describe, expect, it } from "vitest";
import { PASOS_POR_ROL } from "@/lib/evaluacionRoles";

describe("pasos por rol en la evaluación", () => {
  it("la validadora no ve el botón de describir a ciegas", () => {
    expect(PASOS_POR_ROL.validadora).toEqual(["asistida"]);
  });
  it("la descriptora solo describe a ciegas y nunca ve la propuesta", () => {
    expect(PASOS_POR_ROL.descriptora).toEqual(["ciega"]);
  });
  it("la adjudicadora solo consolida la referencia", () => {
    expect(PASOS_POR_ROL.adjudicadora).toEqual(["adjudicar"]);
  });
  it("la calificadora solo califica", () => {
    expect(PASOS_POR_ROL.calificadora).toEqual(["calificar"]);
  });
  it("«ambas» conserva el flujo completo de una sola persona", () => {
    expect(PASOS_POR_ROL.ambas).toEqual(["ciega", "asistida", "calificar"]);
  });
  it("el piloto ensaya describir a ciegas y con la propuesta", () => {
    expect(PASOS_POR_ROL.piloto).toEqual(["ciega", "asistida"]);
  });
});
