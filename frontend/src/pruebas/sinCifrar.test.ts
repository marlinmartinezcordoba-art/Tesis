import { describe, expect, it } from "vitest";
import { conexionSinCifrar } from "../components/SinCifrar";

describe("aviso de conexión sin cifrar (NFR-01)", () => {
  it("avisa en HTTP por la dirección del servidor", () => {
    expect(conexionSinCifrar({ protocol: "http:", hostname: "203.0.113.5" })).toBe(true);
  });
  it("no avisa con HTTPS ni en el propio equipo", () => {
    expect(conexionSinCifrar({ protocol: "https:", hostname: "203-0-113-5.sslip.io" })).toBe(false);
    expect(conexionSinCifrar({ protocol: "http:", hostname: "localhost" })).toBe(false);
  });
});
