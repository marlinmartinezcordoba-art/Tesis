const fechaHora = new Intl.DateTimeFormat("es-CO", {
  timeZone: "America/Bogota",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

const soloFecha = new Intl.DateTimeFormat("es-CO", { timeZone: "America/Bogota", day: "numeric", month: "long", year: "numeric" });

export function fecha(iso: string | null | undefined): string {
  return iso ? fechaHora.format(new Date(iso)) : "—";
}

export function dia(iso: string | null | undefined): string {
  return iso ? soloFecha.format(new Date(iso)) : "—";
}

const numero = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export function peso(bytes: number | null | undefined): string {
  // Un original en papel (registro físico, sin archivo) no tiene tamaño.
  if (bytes == null) return "sin archivo digital";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${numero.format(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${numero.format(bytes / 1024 / 1024)} MB`;
  return `${numero.format(bytes / 1024 / 1024 / 1024)} GB`;
}

// Confianza del OCR, sobre 100, con coma decimal.
export function confianzaTexto(c: number): string {
  return `${c.toLocaleString("es-CO", { maximumFractionDigits: 1 })} / 100`;
}
