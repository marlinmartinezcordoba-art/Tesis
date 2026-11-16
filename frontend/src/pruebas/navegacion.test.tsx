// Pruebas del árbol de submódulos de la barra lateral (rediseño de navegación).
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { UsuarioBreve } from "@/lib/api";

const sesion: { usuario: UsuarioBreve | null } = { usuario: null };
vi.mock("@/lib/sesion", () => ({ useSesion: () => ({ usuario: sesion.usuario, salir: vi.fn() }) }));
vi.mock("@/lib/fondo", () => ({ useFondo: () => ({ fondo: null, fondos: [], elegir: vi.fn() }) }));

const { ArbolNavegacion, PestanasModulo, submodulosDe, vistasDe } = await import("@/components/Marco");

const TODO = { ingesta: "escribir", descripcion: "escribir", vocabularios: "escribir", instrumentos: "escribir",
  preservacion: "escribir", catalogo: "escribir", auditoria: "todo" };
const ADMIN: UsuarioBreve = { id: "1", nombre: "Marlín", correo: "m@x.co", rol: "administrador", rol_nombre: "Administrador",
  iniciales: "MM", es_administrador: true, permisos: TODO };
const CONSULTA: UsuarioBreve = { ...ADMIN, rol: "consulta", rol_nombre: "Consulta", es_administrador: false,
  permisos: { catalogo: "leer", auditoria: "propia" } };

function Ubicacion() {
  const l = useLocation();
  return <output data-testid="ubicacion">{l.pathname + l.search}</output>;
}

function montar(ruta: string, usuario: UsuarioBreve = ADMIN) {
  sesion.usuario = usuario;
  return render(<MemoryRouter initialEntries={[ruta]}><ArbolNavegacion /><PestanasModulo /><Ubicacion /></MemoryRouter>);
}

// El nombre visible (la pista de ayuda va aparte, oculta para el lector de pantalla).
const nombre = (el: Element) => el.querySelector("span")?.textContent ?? el.textContent;
const rama = (n: string) => screen.getAllByRole("button").find((b) => nombre(b.querySelector(".rama-nombre") ?? b) === n)!;
const submodulosVisibles = (modulo: string) => {
  const id = rama(modulo).getAttribute("aria-controls")!;
  const lista = document.getElementById(id);
  return lista ? within(lista).getAllByRole("link").map((a) => nombre(a)) : [];
};
const pestanas = () => {
  const barra = document.querySelector(".pestanas-modulo") as HTMLElement | null;
  return barra ? within(barra).getAllByRole("link").map((a) => a.textContent) : [];
};
const pestanaActual = () => (document.querySelector(".pestanas-modulo [aria-current=page]") as HTMLElement | null)?.textContent;

afterEach(cleanup);

describe("menú por procesos: módulos, uno con submódulos, y pestañas dentro de la pantalla", () => {
  it("solo Conocimiento RiC se despliega; lo demás es un enlace", () => {
    montar("/ingesta");
    expect(screen.getAllByRole("button", { expanded: false }).concat(screen.queryAllByRole("button", { expanded: true }))
      .map((b) => nombre(b.querySelector(".rama-nombre") ?? b)).sort()).toEqual(["Conocimiento RiC"]);
    for (const m of ["Instrumentos", "Carga de documentos", "Descripción", "Agentes y autoridades", "Preservación", "Auditoría",
      "Evaluación", "Administración", "Búsqueda"]) {
      expect(screen.getByRole("link", { name: m })).toBeTruthy();
    }
  });

  it("la TRD y el CCD son pasos guiados; las direcciones de antes llevan al paso donde quedó cada tarea", () => {
    montar("/fondos?vista=matriz");
    expect(pestanas()).toEqual(expect.arrayContaining(["Instrumentos de la entidad", "Cargar TRD y CCD", "Cuadro y versiones",
      "TVD", "Disposición final"]));
    expect(pestanaActual()).toBe("Cargar TRD y CCD");
    cleanup();
    montar("/fondos?vista=ajustar");
    expect(pestanaActual()).toBe("Cargar TRD y CCD");
    cleanup();
    montar("/fondos?vista=cuadro");
    expect(pestanaActual()).toBe("Cuadro y versiones");
    cleanup();
    montar("/fondos?vista=fondos");
    expect(pestanaActual()).toBe("Cargar TRD y CCD");
  });

  it("un módulo sin submódulos muestra sus vistas como pestañas", () => {
    montar("/vocabularios?vista=sugerencias");
    expect(pestanas()).toEqual(["Autoridades", "Posibles duplicados", "Tesauros"]);
    expect(pestanaActual()).toBe("Posibles duplicados");
  });

  it("elegir un submódulo lleva a su primera vista; la pestaña cambia de vista dentro de él", () => {
    montar("/instrumentos");
    expect(submodulosVisibles("Conocimiento RiC")).toEqual(["Catálogo y grafo", "Datos enlazados (RiC-O)"]);
    expect(pestanas()).toEqual(["Catálogo", "Grafo de contexto"]);
    fireEvent.click(screen.getByRole("link", { name: "Datos enlazados (RiC-O)" }));
    expect(screen.getByTestId("ubicacion").textContent).toBe("/instrumentos?vista=rico");
    expect(pestanas()).toEqual(["Datos enlazados (RiC-O)", "Adopción de RiC"]);
  });

  it("el inventario (FUID) está en Instrumentos; las direcciones de la guía y el índice llevan al catálogo", () => {
    montar("/fondos?vista=fuid");
    expect(pestanaActual()).toBe("Inventario (FUID)");
    cleanup();
    montar("/instrumentos?vista=guia");
    expect(pestanaActual()).toBe("Catálogo");
  });

  it("acordeón: tocar el módulo abierto lo cierra", () => {
    montar("/instrumentos");
    expect(rama("Conocimiento RiC").getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(rama("Conocimiento RiC"));
    expect(screen.queryAllByRole("button", { expanded: true })).toEqual([]);
  });

  it("la configuración de preservación es una pestaña con ruta propia", () => {
    montar("/preservacion/configuracion");
    expect(pestanas()).toEqual(["Panel", "Configuración"]);
    expect(pestanaActual()).toBe("Configuración");
  });

  it("cada rol ve solo lo suyo; sin pestañas de una sola vista", () => {
    expect(submodulosDe("/instrumentos", CONSULTA).map((sm) => [sm.nombre, sm.vistas.map((v) => v.nombre)])).toEqual([
      ["Catálogo y grafo", ["Catálogo", "Grafo de contexto"]],
      ["Datos enlazados (RiC-O)", ["Datos enlazados (RiC-O)", "Adopción de RiC"]]]);
    expect(vistasDe("/auditoria", ADMIN).map((v) => v.vista)).toEqual(["propia", "decisiones", "hallazgos"]);
    montar("/instrumentos?vista=rico", CONSULTA);
    expect(screen.queryByRole("link", { name: "Agentes y autoridades" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Administración" })).toBeNull();
  });
});
