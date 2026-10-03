// Hallazgo ING-07: las dos alertas de la ingesta que no bloquean llevan al
// espacio de descripción del documento; las demás no inventan un destino.
import { describe, expect, it } from "vitest";
import { TIPO_ALERTA, enlaceDeAlerta } from "@/lib/alertas";

describe("enlace de cada alerta", () => {
  it("formato no identificado y OCR dudoso llevan a describir el documento", () => {
    for (const tipo of ["formato_no_identificado", "ocr_baja_confianza"]) {
      expect(enlaceDeAlerta({ tipo, entidad_tipo: "instanciacion", entidad_id: "abc-1" }))
        .toEqual({ ruta: "/descripcion?documento=abc-1", texto: "Ir a describir" });
    }
  });

  it("las demás alertas no tienen enlace a descripción", () => {
    expect(enlaceDeAlerta({ tipo: "integridad_alterada", entidad_tipo: "instanciacion", entidad_id: "x" })).toBeNull();
    expect(enlaceDeAlerta({ tipo: "respaldo_fallido", entidad_tipo: "base_de_datos", entidad_id: "x" })).toBeNull();
  });

  it("cada tipo de alerta del servidor tiene nombre legible", () => {
    for (const tipo of ["respaldo_fallido", "exportacion_no_conforme", "verificacion_atrasada"])
      expect(TIPO_ALERTA[tipo]).toBeTruthy();
  });
});
