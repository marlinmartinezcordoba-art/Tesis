export type NivelRiesgo = "bajo" | "medio" | "alto";

// Agente mecanismo (RiC-E13) del vocabulario del fondo, con su versión exacta.
export interface MecanismoBreve { id: string; nombre: string; version: string | null }

export interface InstBreve {
  id: string;
  nombre: string;
  formato: string | null;
  puid: string | null;
}

export interface Miga {
  id: string;
  nivel: string;
  titulo: string;
}

export interface Panel {
  resumen: { total: number; alerta_integridad: number; alerta_segunda_copia: number; riesgo_obsolescencia: number;
    buen_estado: number };
  atencion: {
    alerta_id: string;
    tipo: "integridad_alterada" | "segunda_copia_alterada" | "riesgo_obsolescencia" | "formato_no_identificado";
    severidad: "alta" | "media" | "baja";
    mensaje: string;
    instanciacion: InstBreve;
    contexto: Miga[];
  }[];
  frecuencia_dias: number;
  ultima_verificacion: string | null;
  sin_segunda_copia: number;
}

export interface Riesgo {
  nivel: NivelRiesgo;
  razon: string;
  recomendacion: string | null;
  destino_sugerido: string | null;
  mitigado_por: { id: string; nombre: string } | null;
}

export interface MigracionHist {
  id: string;
  destino: string;
  destino_nombre: string;
  modo: "automatica" | "manual";
  estado: "en_curso" | "completada" | "fallida" | "esperando_archivo";
  herramienta: string | null;
  mecanismo: MecanismoBreve | null;
  parametros: string | null;
  mensaje: string | null;
  aprobada_por: string | null;
  aprobada_en: string;
  terminada_en: string | null;
  resultado: InstBreve | null;
}

export interface Detalle {
  id: string;
  nombre: string;
  fondo_id: string;
  formato: { puid: string | null; nombre: string | null; version: string | null; mime: string | null; identificado: boolean;
    herramienta: string | null; mecanismo: MecanismoBreve | null; base: string | null };
  tamano_bytes: number;
  paginas: number | null;
  huella: string | null;
  algoritmo_huella: string;
  cargado_en: string;
  estado_integridad: "sin_verificar" | "integra" | "alterada" | "ausente";
  ultima_verificacion_en: string | null;
  riesgo: Riesgo;
  contexto: Miga[];
  derivada_de: InstBreve | null;
  migrada_desde: { herramienta: string | null; modo: string; mecanismo: MecanismoBreve | null } | null;
  verificaciones: { fecha: string; resultado: "integra" | "alterada" | "ausente"; origen: "periodica" | "manual";
    segunda_copia: ResultadoCopia | null; por: string | null }[];
  migraciones: MigracionHist[];
  destinos: { clave: string; nombre: string; automatica: boolean; conversor: string | null }[];
  almacenamiento: { primaria: { ubicacion: string; ruta: string }; segunda_copia: SegundaCopia };
  restauraciones: { fecha: string; por: string | null; estado_previo: string; cuarentena: string | null }[];
  acciones: { restaurar: boolean; reponer_segunda_copia: boolean };
  derechos: Derechos | null;
  aplicacion_creadora: string | null;
}

export type ResultadoCopia = "integra" | "alterada" | "ausente" | "sin_copia";

export interface SegundaCopia {
  estado: "sincronizada" | "alterada" | "ausente" | "reemplazada" | "sin_copia";
  id?: string;
  ubicacion?: string;
  ruta?: string;
  huella?: string;
  motivo?: string;
  creada_en?: string;
  ultima_verificacion_en?: string | null;
}

export interface Derechos {
  id: string;
  entidad_tipo: "instanciacion" | "recurso_documental";
  nivel: string | null;
  titulo: string | null;
  base: string;
  base_nombre: string;
  acceso: "publico" | "clasificado" | "reservado";
  acceso_nombre: string;
  reproduccion: string;
  reproduccion_nombre: string;
  fundamento: string;
  nota: string | null;
  vigente_hasta: string | null;
  heredada: boolean;
}

export const BASES_DERECHOS = [
  { clave: "estatuto", nombre: "Norma (ley, decreto, acuerdo)" },
  { clave: "licencia", nombre: "Licencia" },
  { clave: "derecho_de_autor", nombre: "Derecho de autor" },
  { clave: "politica_institucional", nombre: "Política institucional" },
  { clave: "otra", nombre: "Otra" },
];
export const ACCESOS = [
  { clave: "publico", nombre: "Público" },
  { clave: "clasificado", nombre: "Clasificado (Ley 1712, art. 18)" },
  { clave: "reservado", nombre: "Reservado (Ley 1712, art. 19)" },
];
export const REPRODUCCIONES = [
  { clave: "permitida", nombre: "Permitida" },
  { clave: "condicionada", nombre: "Con condiciones" },
  { clave: "no_permitida", nombre: "No permitida" },
];

export const SEGUNDA_COPIA: Record<SegundaCopia["estado"], { texto: string; clase: string }> = {
  sincronizada: { texto: "Sincronizada", clase: "bien" },
  alterada: { texto: "Alerta: alterada", clase: "error" },
  ausente: { texto: "Alerta: no está", clase: "error" },
  reemplazada: { texto: "Reemplazada", clase: "proceso" },
  sin_copia: { texto: "Pendiente de crear", clase: "alerta" },
};

export interface Configuracion {
  frecuencia_dias: number;
  formatos: { id: string; origen: string; origen_mime: string[]; destino: string; conversor: string; activo: boolean }[];
  conversores: { clave: string; nombre: string; destino: string }[];
  destinos: { clave: string; nombre: string }[];
  herramientas: { ghostscript: boolean };
  segunda_copia: {
    actual: string | null;
    primaria: string;
    ubicaciones: { ruta: string; existe: boolean; escribible: boolean; libre_bytes: number | null;
      mismo_disco_que_primaria: boolean }[];
    pendientes: number;
  };
}

export const INTEGRIDAD: Record<Detalle["estado_integridad"], { texto: string; clase: string }> = {
  sin_verificar: { texto: "Sin verificar todavía", clase: "proceso" },
  integra: { texto: "Íntegra", clase: "bien" },
  alterada: { texto: "Alterada", clase: "error" },
  ausente: { texto: "Archivo ausente", clase: "error" },
};

export const RIESGO: Record<NivelRiesgo, { texto: string; clase: string }> = {
  bajo: { texto: "Riesgo bajo", clase: "bien" },
  medio: { texto: "Riesgo medio", clase: "alerta" },
  alto: { texto: "Riesgo alto", clase: "error" },
};

export const TIPO_ATENCION: Record<Panel["atencion"][number]["tipo"], { texto: string; clase: string }> = {
  integridad_alterada: { texto: "Alerta de integridad", clase: "error" },
  segunda_copia_alterada: { texto: "Alerta de segunda copia", clase: "error" },
  riesgo_obsolescencia: { texto: "Riesgo de obsolescencia", clase: "alerta" },
  formato_no_identificado: { texto: "Formato no identificado", clase: "alerta" },
};

export const FRECUENCIAS = [
  { dias: 7, nombre: "Semanal" },
  { dias: 15, nombre: "Quincenal" },
  { dias: 30, nombre: "Mensual (recomendado para un fondo histórico)" },
  { dias: 90, nombre: "Trimestral" },
  { dias: 180, nombre: "Semestral" },
  { dias: 365, nombre: "Anual" },
];
