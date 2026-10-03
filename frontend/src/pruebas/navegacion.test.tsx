// Pruebas del árbol de submódulos de la barra lateral (rediseño de navegación).
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { UsuarioBreve } from "@/lib/api";

const sesion: { usuario: UsuarioBreve | null } = { usuario: null };
vi.mock("@/lib/sesion", () => ({ useSesion: () => ({ usuario: sesion.usuario, salir: vi.fn() }) }));
vi.mock("@/lib/fondo", () => ({ useFondo: () => ({ fondo: null, fondos: [], elegir: vi.fn() }) }));

const { ArbolNavegacion, vistasDe } = await import("@/components/Marco");

const TODO = { ingesta: "escribir", descripcion: "escribir", vocabularios: "escribir", instrumentos: "escribir",
  preservacion: "escribir", catalogo: "escribir", auditoria: "todo" };
const ADMIN: UsuarioBreve = { id: "1", nombre: "Marlín", correo: "m@x.co", rol: "administrador", rol_nombre: "Administrador",
  iniciales: "MM", es_administrador: true, permisos: TODO };
const CONSULTA: UsuarioBreve = { ...ADMIN, rol: "consulta", rol_nombre: "Consulta", es_administrador: false,
  permisos: { ingesta: "leer", descripcion: "leer", vocabularios: "leer", instrumentos: "leer", preservacion: "leer",
    catalogo: "leer", auditoria: "propia" } };

function Ubicacion() {
  const l = useLocation();
  return <output data-testid="ubicacion">{l.pathname + l.search}</output>;
}

function montar(ruta: string, usuario: UsuarioBreve = ADMIN) {
  sesion.usuario = usuario;
  return render(<MemoryRouter initialEntries={[ruta]}><ArbolNavegacion /><Ubicacion /></MemoryRouter>);
}

const rama = (nombre: string) => screen.getByRole("button", { name: nombre });
const vistasVisibles = (nombre: string) => {
  const id = rama(nombre).getAttribute("aria-controls")!;
  const lista = document.getElementById(id);
  return lista ? within(lista).getAllByRole("link").map((a) => a.textContent) : [];
};

afterEach(cleanup);

describe("árbol de submódulos", () => {
  it("al entrar por la URL de una vista interna expande su módulo y la resalta", () => {
    montar("/vocabularios?vista=sugerencias");
    expect(rama("Vocabularios").getAttribute("aria-expanded")).toBe("true");
    expect(vistasVisibles("Vocabularios")).toEqual(["Vocabulario", "Sugerencias de fusión"]);
    const activa = screen.getByRole("link", { current: "page" });
    expect(activa.textContent).toBe("Sugerencias de fusión");
    // Los demás módulos quedan contraídos.
    for (const m of ["Ingesta", "Descripción", "Instrumentos", "Preservación", "Auditoría", "Usuarios"]) {
      expect(rama(m).getAttribute("aria-expanded")).toBe("false");
    }
  });

  it("acordeón: abrir un módulo revela exactamente sus vistas y esconde las del que estaba abierto", () => {
    montar("/vocabularios");
    // Sin ?vista, la primera vista del módulo es la activa.
    expect(screen.getByRole("link", { current: "page" }).textContent).toBe("Vocabulario");
    fireEvent.click(rama("Instrumentos"));
    expect(vistasVisibles("Instrumentos")).toEqual(["Catálogo", "Grafo", "Inventario", "Guía", "Índice", "RiC-O"]);
    expect(rama("Vocabularios").getAttribute("aria-expanded")).toBe("false");
    expect(vistasVisibles("Vocabularios")).toEqual([]);
    // Tocar el módulo abierto lo cierra: no queda ninguno abierto.
    fireEvent.click(rama("Instrumentos"));
    expect(screen.queryAllByRole("button", { expanded: true })).toEqual([]);
  });

  it("al pasar de un módulo a otro, las vistas del anterior se esconden solas", () => {
    montar("/ingesta");
    fireEvent.click(rama("Descripción"));
    fireEvent.click(screen.getByRole("link", { name: "Descritas" }));
    fireEvent.click(rama("Instrumentos"));
    fireEvent.click(screen.getByRole("link", { name: "Grafo" }));
    expect(screen.getByTestId("ubicacion").textContent).toBe("/instrumentos?vista=grafo");
    const abiertos = screen.getAllByRole("button", { expanded: true }).map((b) => b.textContent);
    expect(abiertos).toEqual(["Instrumentos"]);
  });

  it("elegir una vista navega a ella y pasa a ser la resaltada", () => {
    montar("/instrumentos");
    fireEvent.click(screen.getByRole("link", { name: "Grafo" }));
    expect(screen.getByTestId("ubicacion").textContent).toBe("/instrumentos?vista=grafo");
    expect(screen.getByRole("link", { current: "page" }).textContent).toBe("Grafo");
  });

  it("la configuración de preservación es una vista del árbol con ruta propia", () => {
    montar("/preservacion/configuracion");
    expect(rama("Preservación").getAttribute("aria-expanded")).toBe("true");
    expect(vistasVisibles("Preservación")).toEqual(["Panel", "Configuración"]);
    expect(screen.getByRole("link", { current: "page" }).textContent).toBe("Configuración");
  });

  it("cada rol ve solo sus vistas; un módulo con una sola vista es un enlace simple", () => {
    montar("/auditoria", CONSULTA);
    expect(screen.queryByRole("button", { name: "Auditoría" })).toBeNull();
    expect(screen.getByRole("link", { name: "Auditoría" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Usuarios" })).toBeNull(); // solo la administración
    expect(vistasDe("/preservacion", CONSULTA).map((v) => v.vista)).toEqual(["panel"]);
    expect(vistasDe("/auditoria", ADMIN).map((v) => v.vista)).toEqual(["propia", "consolidado", "decisiones", "hallazgos"]);
    // Evaluación no tiene vistas internas: enlace simple también para la administración.
    cleanup();
    montar("/evaluacion");
    expect(screen.queryByRole("button", { name: "Evaluación" })).toBeNull();
    expect(screen.getByRole("link", { name: "Evaluación" })).toBeTruthy();
  });
});
