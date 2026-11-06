// Logo de RICORA: un documento unido a sus contextos (nodos de un grafo), la idea de Records in Contexts.
// Geométrico y sobrio, en la paleta: azul noche y azul eléctrico de fondo, nodos turquesa y violeta.

export function Emblema({ tamano = 40 }: { tamano?: number }) {
  return (
    <svg width={tamano} height={tamano} viewBox="0 0 48 48" role="img" aria-label="RICORA" className="logo-emblema">
      <defs>
        <linearGradient id="ricora-fondo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#0c2560" /><stop offset="1" stopColor="#147dce" />
        </linearGradient>
      </defs>
      <rect width="48" height="48" rx="12" fill="url(#ricora-fondo)" />
      {/* Enlaces del documento con sus contextos */}
      <path d="M25 18 L33.5 13.5 M25 25.5 L35 25.5 M25 32 L32.5 36.5" stroke="#ffffff" strokeOpacity=".55" strokeWidth="1.6" strokeLinecap="round" />
      {/* El documento, con la esquina doblada */}
      <path d="M10 10h11l5 5v23H10z" fill="#ffffff" />
      <path d="M21 10v5h5" fill="#dbe6fa" />
      <path d="M13.5 20.5h8.5M13.5 25h8.5M13.5 29.5h5.5" stroke="#147dce" strokeWidth="1.8" strokeLinecap="round" />
      {/* Contextos: agente, actividad, lugar */}
      <circle cx="35" cy="12.5" r="3.4" fill="#16c6c1" stroke="#ffffff" strokeWidth="1.4" />
      <circle cx="37" cy="25.5" r="3.4" fill="#8555e8" stroke="#ffffff" strokeWidth="1.4" />
      <circle cx="34" cy="37.5" r="3.4" fill="#16c6c1" stroke="#ffffff" strokeWidth="1.4" />
    </svg>
  );
}
