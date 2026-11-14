// La clasificación sugerida a partir del detector de datos personales: pública por defecto,
// clasificada si hay datos sensibles o de menores; lo descartado no cuenta; sin texto no sugiere.
import { describe, expect, it } from "vitest";
import { sugerirClasificacion, type HallazgoResumen } from "@/lib/sugerenciaClasificacion";

const h = (categoria: HallazgoResumen["categoria"], estado: HallazgoResumen["estado"] = "pendiente"): HallazgoResumen =>
  ({ tipo_nombre: categoria === "personal" ? "Cédula de ciudadanía" : "Historia clínica", categoria, categoria_final: null,
     estado, veces: 2, paginas: [1, 3] });
const rev = (hallazgos: HallazgoResumen[], sin_texto: string[] = []) =>
  ({ documentos: [{ hallazgos }], pendientes: hallazgos.filter((x) => x.estado === "pendiente").length, sin_texto });

describe("sugerencia de clasificación", () => {
  it("sin hallazgos: pública y sin datos personales", () => {
    const s = sugerirClasificacion(rev([]));
    expect(s?.acceso).toBe("publico");
    expect(s?.datosPersonales).toBe("no_contiene");
  });
  it("con cédulas: pública, con datos personales y dice dónde", () => {
    const s = sugerirClasificacion(rev([h("personal")]))!;
    expect([s.acceso, s.datosPersonales, s.reproduccion]).toEqual(["publico", "personales", "permitida"]);
    expect(s.motivos.join(" ")).toContain("Cédula de ciudadanía: 2 veces (pág. 1, 3)");
  });
  it("con datos sensibles: clasificada con fundamento y sin reproducción", () => {
    const s = sugerirClasificacion(rev([h("personal"), h("sensible")]))!;
    expect([s.acceso, s.datosPersonales, s.reproduccion]).toEqual(["clasificado", "sensibles", "no_permitida"]);
    expect(s.fundamento).toContain("art. 18");
  });
  it("lo descartado por la persona no cuenta", () => {
    expect(sugerirClasificacion(rev([h("sensible", "descartado")]))?.datosPersonales).toBe("no_contiene");
  });
  it("si arriba ya está restringida, conserva lo heredado", () => {
    expect(sugerirClasificacion(rev([h("sensible")]), { acceso: "reservado" })?.acceso).toBe("hereda");
  });
  it("sin texto extraído no sugiere", () => {
    expect(sugerirClasificacion(rev([], ["oficio.pdf"]))).toBeNull();
  });
});
