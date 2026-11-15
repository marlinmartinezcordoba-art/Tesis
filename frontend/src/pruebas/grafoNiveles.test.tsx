// El grafo distingue los niveles de las agrupaciones (todas rico:RecordSet) y
// antepone el código del cuadro para que las series homónimas no se confundan.
import { describe, expect, it } from "vitest";
import { ICONO_FAMILIA, NIVELES, etiquetaDe, iconoDe, type NodoGrafo } from "@/components/Grafo";

const nodo = (clase: string, extra: Partial<NodoGrafo> = {}): NodoGrafo => ({
  clave: "k", id: "k", tipo: "recurso_documental", clase, familia: "RecordSet", etiqueta: "Informes", subtitulo: null,
  estado: "publicada", fecha_inicio: null, fecha_fin: null, salto: 0, ...extra });

describe("niveles del grafo", () => {
  it("cada nivel de agrupación tiene su propio icono", () => {
    const iconos = new Set(["fondo", "seccion", "serie", "expediente"].map((c) => iconoDe(nodo(c))));
    expect(iconos.size).toBe(4);
    expect(NIVELES.map((n) => n.clave)).toContain("subserie");
  });

  it("una entidad que no es descripción conserva el icono de su tipo RiC", () => {
    expect(iconoDe(nodo("agente", { tipo: "entidad_vocabulario", familia: "Agent" }))).toBe(ICONO_FAMILIA.Agent);
  });

  it("el código del cuadro va antes del nombre", () => {
    expect(etiquetaDe(nodo("serie", { codigo: "2100.30" }))).toBe("2100.30 Informes");
    expect(etiquetaDe(nodo("serie", { codigo: null }))).toBe("Informes");
  });
});
