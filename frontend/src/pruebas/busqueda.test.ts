import { describe, expect, it } from "vitest";
import { partesResaltadas } from "../lib/busqueda";

describe("fragmentos resaltados del buscador", () => {
  it("parte el texto en lo resaltado y lo demás", () => {
    expect(partesResaltadas("el inspector ⟦Cuervo⟧ informa … de ⟦Cuervo⟧")).toEqual([
      { texto: "el inspector ", resaltado: false }, { texto: "Cuervo", resaltado: true },
      { texto: " informa … de ", resaltado: false }, { texto: "Cuervo", resaltado: true },
    ]);
  });
  it("no interpreta HTML ni deja marcas sueltas", () => {
    expect(partesResaltadas("<b>x</b> ⟦a")).toEqual([{ texto: "<b>x</b> a", resaltado: false }]);
  });
});
