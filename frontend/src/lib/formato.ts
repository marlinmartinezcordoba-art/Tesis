const fechaHora = new Intl.DateTimeFormat("es-CO", {
  timeZone: "America/Bogota",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

export function fecha(iso: string | null | undefined): string {
  return iso ? fechaHora.format(new Date(iso)) : "—";
}
