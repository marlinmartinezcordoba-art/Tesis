// El grafo distingue los niveles de las agrupaciones (todas rico:RecordSet) y
// antepone el código del cuadro para que las series homónimas no se confundan.
import { describe, expect, it } from "vitest";
import { ICONO_FAMILIA, NIVELES, etiquetaDe, iconoDe, seleccionDescripcion, type NodoGrafo } from "@/components/Grafo";

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

describe("vista Descripción", () => {
  const n = (clave: string, familia: NodoGrafo["familia"], tipo = "entidad_vocabulario", clase: string = familia): NodoGrafo => ({
    clave, id: clave, tipo, clase, familia, etiqueta: clave, subtitulo: null, estado: null, fecha_inicio: null, fecha_fin: null, salto: 1 });
  const a = (desde: string, hacia: string, codigo_ric: string) => ({ desde, hacia, codigo_ric, uri_rico: null, etiqueta: codigo_ric, dirigida: true });
  const datos = {
    fondo: { id: "f", titulo: "F" }, centro: "doc", saltos: 3, truncado: false, maximo_nodos: 300, filtros_activos: 0,
    nodos: [n("doc", "Record", "recurso_documental", "unidad_documental"), n("exp", "RecordSet", "recurso_documental", "expediente"),
      n("serie", "RecordSet", "recurso_documental", "serie"), n("hermano", "Record", "recurso_documental", "unidad_documental"),
      n("agente", "Agent"), n("act", "Activity"), n("tipo", "ActivityType"), n("ley", "Mandate"), n("lugar", "Place")],
    aristas: [a("exp", "doc", "includes_or_included"), a("serie", "exp", "includes_or_included"), a("exp", "hermano", "includes_or_included"),
      a("doc", "agente", "has_creator"), a("doc", "act", "documents"), a("act", "tipo", "has_activity_type"), a("ley", "act", "regulates_or_regulated"),
      a("doc", "lugar", "is_associated_with_place")],
  };
  it("agrupa por pregunta y deja fuera a los hermanos", () => {
    const { grupos, omitidos } = seleccionDescripcion(datos);
    expect(Object.fromEntries(grupos)).toEqual({ doc: "raiz", exp: "estructura", serie: "estructura", agente: "agentes", act: "funcion",
      tipo: "funcion", ley: "norma", lugar: "contexto" });
    expect(omitidos).toBe(1);
  });
});

describe("nombre provisional", () => {
  it("reconoce el que pone la carga de la TRD y respeta los nombres reales", async () => {
    const { esNombreProvisional } = await import("@/components/Grafo");
    expect(esNombreProvisional("Dependencia 3203")).toBe(true);
    expect(esNombreProvisional("Serie 27")).toBe(true);
    expect(esNombreProvisional("3000 Despacho del Viceministro")).toBe(false);
    expect(esNombreProvisional("Secretaría General")).toBe(false);
  });
});

describe("nombres en dos líneas", () => {
  it("no corta la parte que distingue a dos homónimos", async () => {
    const { lineas } = await import("@/components/Grafo");
    const a = lineas("2000 DESPACHO DEL VICEMINISTRO DE ORDENAMIENTO AMBIENTAL");
    const b = lineas("3000 DESPACHO DEL VICEMINISTRO DE POLÍTICAS");
    expect(a.length).toBe(2);
    expect(a.join(" ")).not.toBe(b.join(" "));
    expect(b.join(" ")).toContain("POLÍTICAS");
    expect(lineas("Tunja")).toEqual(["Tunja"]);
  });
});
