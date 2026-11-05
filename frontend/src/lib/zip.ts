// Empaqueta varios archivos en un .zip (sin compresión, formato «stored») en el navegador.
// Sirve para cargar de una vez la TRD o la TVD que la entidad entrega en un archivo por
// dependencia: el servidor ya lee un .zip con una tabla por dependencia.

const TABLA_CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(datos: Uint8Array): number {
  let c = 0xffffffff;
  for (let i = 0; i < datos.length; i++) c = TABLA_CRC[(c ^ datos[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function leerBytes(archivo: File): Promise<ArrayBuffer> {
  if (typeof archivo.arrayBuffer === "function") return archivo.arrayBuffer();
  return new Promise((ok, mal) => {
    const lector = new FileReader();
    lector.onload = () => ok(lector.result as ArrayBuffer);
    lector.onerror = () => mal(lector.error);
    lector.readAsArrayBuffer(archivo);
  });
}

/** Un .zip con los archivos tal cual (nombres en UTF-8). */
export async function empaquetar(archivos: File[], nombre = "archivos.zip"): Promise<File> {
  const codificar = new TextEncoder();
  const partes: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let desplazamiento = 0;
  for (const archivo of archivos) {
    const datos = new Uint8Array(await leerBytes(archivo));
    const nombreBytes = codificar.encode(archivo.name);
    const crc = crc32(datos);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true); local.setUint16(4, 20, true); local.setUint16(6, 0x0800, true);
    local.setUint16(8, 0, true); local.setUint32(14, crc, true);
    local.setUint32(18, datos.length, true); local.setUint32(22, datos.length, true);
    local.setUint16(26, nombreBytes.length, true);
    partes.push(new Uint8Array(local.buffer), nombreBytes, datos);
    const cab = new DataView(new ArrayBuffer(46));
    cab.setUint32(0, 0x02014b50, true); cab.setUint16(4, 20, true); cab.setUint16(6, 20, true);
    cab.setUint16(8, 0x0800, true); cab.setUint32(16, crc, true);
    cab.setUint32(20, datos.length, true); cab.setUint32(24, datos.length, true);
    cab.setUint16(28, nombreBytes.length, true); cab.setUint32(42, desplazamiento, true);
    central.push(new Uint8Array(cab.buffer), nombreBytes);
    desplazamiento += 30 + nombreBytes.length + datos.length;
  }
  const tamanoCentral = central.reduce((n, p) => n + p.length, 0);
  const fin = new DataView(new ArrayBuffer(22));
  fin.setUint32(0, 0x06054b50, true); fin.setUint16(8, archivos.length, true); fin.setUint16(10, archivos.length, true);
  fin.setUint32(12, tamanoCentral, true); fin.setUint32(16, desplazamiento, true);
  const piezas = [...partes, ...central, new Uint8Array(fin.buffer)] as unknown as BlobPart[];
  return new File(piezas, nombre, { type: "application/zip" });
}

/** Un archivo tal cual, o varios empaquetados en un .zip. */
export async function unoOVarios(lista: FileList | null, nombre: string): Promise<File | null> {
  const archivos = Array.from(lista || []);
  if (archivos.length === 0) return null;
  if (archivos.length === 1) return archivos[0];
  return empaquetar(archivos, nombre);
}
