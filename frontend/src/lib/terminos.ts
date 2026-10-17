// GENERADO por `python -m app.cli terminos` desde app/servicios/terminos.py: no editar a mano.
// Vocabulario único de las relaciones (nombre archivístico, lectura directa e inversa).

export interface Termino { nombre: string; directa: string; inversa: string; rico: string | null;
  codigo_cm: string | null; etiqueta_oficial: string | null }

// Clave: «código» o «código|rol».
export const TERMINOS: Record<string, Termino> = {
  "has_creator": { nombre: "Productor", directa: "producido por", inversa: "productor de", rico: "rico:hasCreator", codigo_cm: "RiC-R027", etiqueta_oficial: "tiene como creador a" },
  "has_author": { nombre: "Autor", directa: "escrito por", inversa: "autor de", rico: "rico:hasAuthor", codigo_cm: "RiC-R079", etiqueta_oficial: "tiene como autor a" },
  "has_sender": { nombre: "Remitente", directa: "remitido por", inversa: "remitente de", rico: "rico:hasSender", codigo_cm: "RiC-R031", etiqueta_oficial: "tiene como remitente a" },
  "has_addressee": { nombre: "Destinatario", directa: "dirigido a", inversa: "destinatario de", rico: "rico:hasAddressee", codigo_cm: "RiC-R032", etiqueta_oficial: "se dirige a" },
  "has_accumulator": { nombre: "Acumulador", directa: "acumulado por", inversa: "acumulador de", rico: "rico:hasAccumulator", codigo_cm: "RiC-R028", etiqueta_oficial: "tiene como acumulador a" },
  "has_or_had_holder": { nombre: "Custodio", directa: "custodiado por", inversa: "custodia o custodió", rico: "rico:hasOrHadHolder", codigo_cm: "RiC-R039i", etiqueta_oficial: "tiene o tenía como conservador a" },
  "includes_or_included": { nombre: "Inclusión", directa: "incluye", inversa: "está incluido en", rico: "rico:includesOrIncluded", codigo_cm: "RiC-R024", etiqueta_oficial: "incluye o incluía" },
  "has_or_had_constituent": { nombre: "Parte documental", directa: "tiene la parte", inversa: "es parte de", rico: "rico:hasOrHadConstituent", codigo_cm: "RiC-R003", etiqueta_oficial: "tiene o tenía como elemento constitutivo" },
  "precedes_or_preceded": { nombre: "Secuencia", directa: "precede a", inversa: "sigue a", rico: "rico:precedesOrPreceded", codigo_cm: "RiC-R008", etiqueta_oficial: "precede o precedía secuencialmente a" },
  "has_or_had_instantiation": { nombre: "Instanciación", directa: "tiene la instanciación", inversa: "es instanciación de", rico: "rico:hasOrHadInstantiation", codigo_cm: "RiC-R025", etiqueta_oficial: "tiene o tenía como instanciación" },
  "migrated_into": { nombre: "Migración", directa: "migrada a", inversa: "migrada desde", rico: "rico:migratedInto", codigo_cm: "RiC-R015", etiqueta_oficial: "migrado a" },
  "has_or_had_derived_instantiation": { nombre: "Instanciación derivada", directa: "tiene como derivada a", inversa: "deriva de", rico: "rico:hasOrHadDerivedInstantiation", codigo_cm: "RiC-R014", etiqueta_oficial: "tiene o tenía como instanciación derivada" },
  "documents": { nombre: "Actividad documentada", directa: "documenta", inversa: "está documentada en", rico: "rico:documents", codigo_cm: "RiC-R033", etiqueta_oficial: "documenta" },
  "has_activity_type": { nombre: "Función (tipo de actividad)", directa: "es del tipo", inversa: "es el tipo de", rico: "rico:hasActivityType", codigo_cm: null, etiqueta_oficial: "tiene como tipo de actividad" },
  "performs_or_performed": { nombre: "Agente que ejerce la actividad", directa: "ejerce o ejerció", inversa: "es o fue ejercida por", rico: "rico:performsOrPerformed", codigo_cm: "RiC-R060i", etiqueta_oficial: "desarrolla o desarrollaba" },
  "has_direct_subevent": { nombre: "Subactividad", directa: "tiene como sub-actividad a", inversa: "es sub-actividad de", rico: "rico:hasDirectSubevent", codigo_cm: null, etiqueta_oficial: "tiene directamente como parte de evento" },
  "regulates_or_regulated": { nombre: "Norma que regula", directa: "regula", inversa: "está regulada por", rico: "rico:regulatesOrRegulated", codigo_cm: "RiC-R063", etiqueta_oficial: "regula o regulaba" },
  "regulates_or_regulated|jerarquia_normativa": { nombre: "Norma superior", directa: "es norma superior de", inversa: "desarrolla o deriva de", rico: "rico:regulatesOrRegulated", codigo_cm: "RiC-R063", etiqueta_oficial: "regula o regulaba" },
  "regulates_or_regulated|creacion": { nombre: "Norma que crea la competencia", directa: "crea la competencia", inversa: "es una competencia creada por", rico: "rico:regulatesOrRegulated", codigo_cm: "RiC-R063", etiqueta_oficial: "regula o regulaba" },
  "regulates_or_regulated|retencion": { nombre: "Regla de retención", directa: "regula la retención de", inversa: "tiene su retención regulada por", rico: "rico:regulatesOrRegulated", codigo_cm: "RiC-R063", etiqueta_oficial: "regula o regulaba" },
  "issued_by": { nombre: "Quien expide la norma", directa: "fue expedido por", inversa: "expidió", rico: "rico:issuedBy", codigo_cm: "RiC-R065", etiqueta_oficial: "emitido por" },
  "authorizes": { nombre: "Norma que autoriza al agente", directa: "autoriza a", inversa: "está autorizado por", rico: "rico:authorizes", codigo_cm: "RiC-R067", etiqueta_oficial: "controla" },
  "authorizes|creacion": { nombre: "Norma de creación", directa: "crea o establece a", inversa: "fue creado o establecido por", rico: "rico:authorizes", codigo_cm: "RiC-R067", etiqueta_oficial: "controla" },
  "is_related_to": { nombre: "Relación general", directa: "está relacionado con", inversa: "está relacionado con", rico: "rico:isRelatedTo", codigo_cm: "RiC-R001", etiqueta_oficial: "está relacionado con" },
  "is_related_to|serie_producida": { nombre: "Función que produce la serie", directa: "produce la serie", inversa: "es producida por la función", rico: "rico:isRelatedTo", codigo_cm: "RiC-R001", etiqueta_oficial: "está relacionado con" },
  "has_or_had_subordinate": { nombre: "Subordinación", directa: "tiene o tuvo como subordinado a", inversa: "está o estuvo subordinado a", rico: "rico:hasOrHadSubordinate", codigo_cm: "RiC-R045", etiqueta_oficial: "tiene o tenía como subordinado o subordinada a" },
  "has_successor": { nombre: "Sucesión", directa: "tiene como sucesor a", inversa: "es sucesor de", rico: "rico:hasSuccessor", codigo_cm: "RiC-R016", etiqueta_oficial: "tiene como sucesor(a) a" },
  "is_agent_associated_with_agent": { nombre: "Agentes asociados", directa: "está asociado con", inversa: "está asociado con", rico: "rico:isAgentAssociatedWithAgent", codigo_cm: "RiC-R044", etiqueta_oficial: "agente está asociado con agente" },
  "occupies_or_occupied": { nombre: "Ocupación de un cargo", directa: "ocupa u ocupó el cargo", inversa: "es o fue ocupado por", rico: "rico:occupiesOrOccupied", codigo_cm: "RiC-R054", etiqueta_oficial: "ocupa u ocupaba" },
  "has_family_association_with": { nombre: "Parentesco", directa: "tiene parentesco con", inversa: "tiene parentesco con", rico: "rico:hasFamilyAssociationWith", codigo_cm: null, etiqueta_oficial: "tiene asociación familiar con" },
  "has_family_association_with|progenitor": { nombre: "Parentesco: progenitor", directa: "es padre o madre de", inversa: "es hijo o hija de", rico: "rico:hasFamilyAssociationWith", codigo_cm: null, etiqueta_oficial: "tiene asociación familiar con" },
  "has_family_association_with|hermano": { nombre: "Parentesco: hermanos", directa: "es hermano o hermana de", inversa: "es hermano o hermana de", rico: "rico:hasFamilyAssociationWith", codigo_cm: null, etiqueta_oficial: "tiene asociación familiar con" },
  "has_family_association_with|conyuge": { nombre: "Parentesco: cónyuges", directa: "es o fue cónyuge de", inversa: "es o fue cónyuge de", rico: "rico:hasFamilyAssociationWith", codigo_cm: null, etiqueta_oficial: "tiene asociación familiar con" },
  "has_or_had_member": { nombre: "Miembro de un grupo", directa: "tiene o tuvo como miembro a", inversa: "es o fue miembro de", rico: "rico:hasOrHadMember", codigo_cm: "RiC-R055", etiqueta_oficial: "tiene o tenía como miembro a" },
  "is_or_was_leader_of": { nombre: "Dirección de un grupo", directa: "dirige o dirigió", inversa: "es o fue dirigido por", rico: "rico:isOrWasLeaderOf", codigo_cm: "RiC-R042", etiqueta_oficial: "es o era líder de" },
  "has_or_had_subdivision": { nombre: "Subdivisión", directa: "tiene o tuvo como subdivisión a", inversa: "es o fue subdivisión de", rico: "rico:hasOrHadSubdivision", codigo_cm: "RiC-R005", etiqueta_oficial: "tiene o tenía como subdivisión" },
  "exists_or_existed_in": { nombre: "Cargo dentro de una entidad", directa: "existe o existió en", inversa: "tiene o tuvo el cargo", rico: "rico:existsOrExistedIn", codigo_cm: "RiC-R056", etiqueta_oficial: "existe o existía en" },
  "affects_or_affected": { nombre: "Hito", directa: "afecta o afectó a", inversa: "es o fue afectado por", rico: "rico:affectsOrAffected", codigo_cm: "RiC-R059", etiqueta_oficial: "afecta o afectaba a" },
  "contains_or_contained": { nombre: "Lugar que contiene a otro", directa: "contiene a", inversa: "está dentro de", rico: "rico:containsOrContained", codigo_cm: "RiC-R007", etiqueta_oficial: "contiene o contenía" },
  "is_or_was_location_of": { nombre: "Localización", directa: "es o fue lugar de", inversa: "está o estuvo en", rico: "rico:isOrWasLocationOf", codigo_cm: "RiC-R075", etiqueta_oficial: "es o era localización de" },
  "is_or_was_location_of|expedicion": { nombre: "Lugar de expedición", directa: "es lugar de expedición de", inversa: "fue expedido en", rico: "rico:isOrWasLocationOf", codigo_cm: "RiC-R075", etiqueta_oficial: "es o era localización de" },
  "is_or_was_location_of|actuacion": { nombre: "Lugar de actuación", directa: "es o fue lugar de actuación de", inversa: "actúa o actuó en", rico: "rico:isOrWasLocationOf", codigo_cm: "RiC-R075", etiqueta_oficial: "es o era localización de" },
  "has_or_had_subject": { nombre: "Tema o mencionado", directa: "trata de", inversa: "es tema de", rico: "rico:hasOrHadSubject", codigo_cm: "RiC-R019", etiqueta_oficial: "tiene o tenía como materia" },
  "has_or_had_subject|mencionado": { nombre: "Mencionado", directa: "menciona a", inversa: "es mencionado en", rico: "rico:hasOrHadSubject", codigo_cm: "RiC-R019", etiqueta_oficial: "tiene o tenía como materia" },
  "has_or_had_subject|lugar": { nombre: "Lugar del que trata", directa: "trata del lugar", inversa: "es lugar tratado en", rico: "rico:hasOrHadSubject", codigo_cm: "RiC-R019", etiqueta_oficial: "tiene o tenía como materia" },
  "has_or_had_subject|mandato": { nombre: "Norma citada", directa: "cita la norma", inversa: "es citada en", rico: "rico:hasOrHadSubject", codigo_cm: "RiC-R019", etiqueta_oficial: "tiene o tenía como materia" },
  "has_or_had_subject|materia": { nombre: "Materia", directa: "tiene como materia", inversa: "es materia de", rico: "rico:hasOrHadSubject", codigo_cm: "RiC-R019", etiqueta_oficial: "tiene o tenía como materia" },
  "is_creation_date_of": { nombre: "Fecha de creación", directa: "es fecha de creación de", inversa: "fue creado en", rico: "rico:isCreationDateOf", codigo_cm: "RiC-R080", etiqueta_oficial: "es fecha de creación de" },
  "is_date_associated_with": { nombre: "Fecha asociada", directa: "es fecha de", inversa: "tiene la fecha", rico: "rico:isDateAssociatedWith", codigo_cm: "RiC-R068", etiqueta_oficial: "es fecha asociada con" },
  "is_date_associated_with|expedicion": { nombre: "Fecha de expedición", directa: "es fecha de expedición de", inversa: "fue expedido el", rico: "rico:isDateAssociatedWith", codigo_cm: "RiC-R068", etiqueta_oficial: "es fecha asociada con" },
  "forma_documental": { nombre: "Tipo documental", directa: "es del tipo documental", inversa: "es el tipo documental de", rico: "rico:hasDocumentaryFormType", codigo_cm: null, etiqueta_oficial: "tiene como tipo documental" },
};

// El término de una relación: el de su rol si lo hay, si no el general.
export function termino(codigo: string | null | undefined, rol?: string | null): Termino | null {
  if (!codigo) return null;
  return (rol ? TERMINOS[`${codigo}|${rol}`] : undefined) ?? TERMINOS[codigo] ?? null;
}

// Rol del agente en la descripción → relación de RiC-O que crea al publicar.
export const RELACION_DEL_ROL: Record<string, string> = {
  productor: "has_creator",
  remitente: "has_sender",
  destinatario: "has_addressee",
  autor: "has_author",
  acumulador: "has_accumulator",
  mencionado: "has_or_had_subject",
  custodio: "has_or_had_holder",
};

// Nivel de descripción → clase de RiC-O y tipo de agrupación (recordSetTypes). «cercano»: el
// tipo oficial más próximo (skos:broadMatch) cuando el nivel no tiene uno propio en RiC-O.
export const NIVEL_RIC: Record<string, { clase: string; tipo: string | null; cercano: string | null }> = {
  fondo: { clase: "rico:RecordSet", tipo: "rst:Fonds", cercano: null },
  seccion: { clase: "rico:RecordSet", tipo: null, cercano: "rst:Fonds" },
  subseccion: { clase: "rico:RecordSet", tipo: null, cercano: "rst:Fonds" },
  serie: { clase: "rico:RecordSet", tipo: "rst:Series", cercano: null },
  subserie: { clase: "rico:RecordSet", tipo: null, cercano: "rst:Series" },
  expediente: { clase: "rico:RecordSet", tipo: "rst:File", cercano: null },
  unidad_documental: { clase: "rico:Record", tipo: null, cercano: null },
  parte_documental: { clase: "rico:RecordPart", tipo: null, cercano: null },
};
