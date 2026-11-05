import { describe, expect, it } from "vitest";
import { writeFileSync } from "node:fs";
import { empaquetar, unoOVarios } from "@/lib/zip";

describe("empaquetar varios archivos en un .zip", () => {
  it("arma un .zip que otro programa puede leer", async () => {
    const a = new File(["Dependencia 1000;Serie 1"], "1000_TRD_Despacho del Ministro.csv");
    const b = new File(["Dependencia 1001;Serie 2"], "1001_TRD_Comunicaciones.csv");
    const zip = await empaquetar([a, b], "TRD.zip");
    const bytes = new Uint8Array(await new Promise<ArrayBuffer>((ok) => { const l = new FileReader(); l.onload = () => ok(l.result as ArrayBuffer); l.readAsArrayBuffer(zip); }));
    expect(zip.name).toBe("TRD.zip");
    expect([bytes[0], bytes[1], bytes[2], bytes[3]]).toEqual([0x50, 0x4b, 0x03, 0x04]);
    if (process.env.RICORA_ZIP_SALIDA) writeFileSync(process.env.RICORA_ZIP_SALIDA, bytes);
  });
  it("un solo archivo pasa tal cual", async () => {
    const a = new File(["x"], "uno.pdf");
    const lista = { 0: a, length: 1, item: () => a, [Symbol.iterator]: function* () { yield a; } } as unknown as FileList;
    expect(await unoOVarios(lista, "TRD.zip")).toBe(a);
  });
});
