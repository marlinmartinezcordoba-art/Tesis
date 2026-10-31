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

const rama = (nombre: string) => screen.getByRole("button", { name: nombre });
const submodulosVisibles = (nombre: string) => {
  const id = rama(nombre).getAttribute("aria-controls")!;
  const lista = document.getElementById(id);
  return lista ? within(lista).getAllByRole("link").map((a) => a.textContent) : [];
};
const pestanas = () => {
  const barra = document.querySelector(".pestanas-modulo") as HTMLElement | null;
  return barra ? within(barra).getAllByRole("link").map((a) => a.textContent) : [];
};
const pestanaActual = () => (document.querySelector(".pestanas-modulo [aria-current=page]") as HTMLElement | null)?.textContent;

afterEach(cleanup);

describe("menú por procesos: módulos, dos con submódulos, y pestañas dentro de la pantalla", () => {
  it("solo Instrumentos archivísticos y Consulta y difusión se despliegan; lo demás es un enlace", () => {
    montar("/ingesta");
    expect(screen.getAllByRole("button", { expanded: false }).concat(screen.queryAllByRole("button", { expanded: true }))
      .map((b) => b.textContent)).toEqual(["Instrumentos archivísticos", "Consulta y difusión"]);
    for (const m of ["Carga de documentos", "Descripción", "Autoridades y términos", "Preservación", "Auditoría",
      "Evaluación", "Usuarios y permisos"]) {
      expect(screen.getByRole("link", { name: m })).toBeTruthy();
    }
  });

  it("la TRD y el CCD son pasos guiados; las direcciones de antes llevan al paso donde quedó cada tarea", () => {
    montar("/fondos?vista=matriz");
    expect(rama("Instrumentos archivísticos").getAttribute("aria-expanded")).toBe("true");
    expect(submodulosVisibles("Instrumentos archivísticos")).toEqual(["TRD y CCD", "TVD", "Disposición final"]);
    expect(screen.getByRole("link", { name: "TRD y CCD" }).getAttribute("aria-current")).toBe("page");
    expect(pestanas()).toEqual(["Paso a paso", "Cuadro y versiones"]);
    expect(pestanaActual()).toBe("Paso a paso");
    cleanup();
    montar("/fondos?vista=ajustar");
    expect(pestanaActual()).toBe("Paso a paso");
    cleanup();
    montar("/fondos?vista=cuadro");
    expect(pestanaActual()).toBe("Cuadro y versiones");
    cleanup();
    montar("/fondos?vista=fondos");
    expect(pestanaActual()).toBe("Paso a paso");
  });

  it("un módulo sin submódulos muestra sus vistas como pestañas", () => {
    montar("/vocabularios?vista=sugerencias");
    expect(pestanas()).toEqual(["Autoridades", "Posibles duplicados", "Tesauros"]);
    expect(pestanaActual()).toBe("Posibles duplicados");
  });

  it("elegir un submódulo lleva a su primera vista; la pestaña cambia de vista dentro de él", () => {
    montar("/instrumentos");
    expect(submodulosVisibles("Consulta y difusión")).toEqual(["Catálogo y grafo", "Instrumentos de descripción", "Datos enlazados (RiC-O)"]);
    expect(pestanas()).toEqual(["Catálogo", "Grafo de contexto"]);
    fireEvent.click(screen.getByRole("link", { name: "Instrumentos de descripción" }));
    expect(screen.getByTestId("ubicacion").textContent).toBe("/instrumentos?vista=inventario");
    expect(pestanas()).toEqual(["Inventario (FUID)", "Guía del fondo", "Índice"]);
    fireEvent.click(screen.getByRole("link", { name: "Índice" }));
    expect(screen.getByTestId("ubicacion").textContent).toBe("/instrumentos?vista=indice");
    expect(pestanaActual()).toBe("Índice");
  });

  it("acordeón: abrir un módulo cierra el otro; tocar el abierto lo cierra", () => {
    montar("/fondos");
    fireEvent.click(rama("Consulta y difusión"));
    expect(rama("Instrumentos archivísticos").getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(rama("Consulta y difusión"));
    expect(screen.queryAllByRole("button", { expanded: true })).toEqual([]);
  });

  it("la configuración de preservación es una pestaña con ruta propia", () => {
    montar("/preservacion/configuracion");
    expect(pestanas()).toEqual(["Panel", "Configuración"]);
    expect(pestanaActual()).toBe("Configuración");
  });

  it("cada rol ve solo lo suyo: consulta ve el índice, no el FUID ni la guía; sin pestañas de una sola vista", () => {
    expect(submodulosDe("/instrumentos", CONSULTA).map((sm) => [sm.nombre, sm.vistas.map((v) => v.nombre)])).toEqual([
      ["Catálogo y grafo", ["Catálogo", "Grafo de contexto"]], ["Instrumentos de descripción", ["Índice"]],
      ["Datos enlazados (RiC-O)", ["Datos enlazados (RiC-O)"]]]);
    expect(vistasDe("/auditoria", ADMIN).map((v) => v.vista)).toEqual(["propia", "decisiones", "hallazgos"]);
    montar("/instrumentos?vista=indice", CONSULTA);
    expect(pestanas()).toEqual([]);
    expect(screen.queryByRole("link", { name: "Autoridades y términos" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Usuarios y permisos" })).toBeNull();
  });
});
