# Vocabulario de relaciones de RICORA

<!-- GENERADO por `python -m app.cli terminos` desde app/servicios/terminos.py: no editar a mano. -->

Un solo nombre por relación en todo el sistema: el grafo, la descripción, las fichas, los instrumentos,
la auditoría y la evaluación. La propiedad, el código RiC-CM y la etiqueta oficial en español vienen del
mapeo verificado contra RiC-O 1.1 (`app/servicios/ric_o.py`).

- **Término archivístico:** el sustantivo con que se elige y se muestra la relación.
- **Lectura directa:** desde el origen (por ejemplo, documento → «producido por» → agente). Es la etiqueta del grafo.
- **Lectura inversa:** desde el destino (agente → «productor de» → documento).

| Término archivístico | Rol | Lectura directa | Lectura inversa | Propiedad RiC-O | RiC-CM | Etiqueta oficial (es) |
|---|---|---|---|---|---|---|
| Productor | — | producido por | productor de | rico:hasCreator | RiC-R027 | tiene como creador a |
| Autor | — | escrito por | autor de | rico:hasAuthor | RiC-R079 | tiene como autor a |
| Remitente | — | remitido por | remitente de | rico:hasSender | RiC-R031 | tiene como remitente a |
| Destinatario | — | dirigido a | destinatario de | rico:hasAddressee | RiC-R032 | se dirige a |
| Acumulador | — | acumulado por | acumulador de | rico:hasAccumulator | RiC-R028 | tiene como acumulador a |
| Custodio | — | custodiado por | custodia o custodió | rico:hasOrHadHolder | RiC-R039i | tiene o tenía como conservador a |
| Inclusión | — | incluye | está incluido en | rico:includesOrIncluded | RiC-R024 | incluye o incluía |
| Parte documental | — | tiene la parte | es parte de | rico:hasOrHadConstituent | RiC-R003 | tiene o tenía como elemento constitutivo |
| Secuencia | — | precede a | sigue a | rico:precedesOrPreceded | RiC-R008 | precede o precedía secuencialmente a |
| Instanciación | — | tiene la instanciación | es instanciación de | rico:hasOrHadInstantiation | RiC-R025 | tiene o tenía como instanciación |
| Migración | — | migrada a | migrada desde | rico:migratedInto | RiC-R015 | migrado a |
| Instanciación derivada | — | tiene como derivada a | deriva de | rico:hasOrHadDerivedInstantiation | RiC-R014 | tiene o tenía como instanciación derivada |
| Actividad documentada | — | documenta | está documentada en | rico:documents | RiC-R033 | documenta |
| Función (tipo de actividad) | — | es del tipo | es el tipo de | rico:hasActivityType | — | tiene como tipo de actividad |
| Agente que ejerce la actividad | — | ejerce o ejerció | es o fue ejercida por | rico:performsOrPerformed | RiC-R060i | desarrolla o desarrollaba |
| Subactividad | — | tiene como sub-actividad a | es sub-actividad de | rico:hasDirectSubevent | — | tiene directamente como parte de evento |
| Norma que regula | — | regula | está regulada por | rico:regulatesOrRegulated | RiC-R063 | regula o regulaba |
| Norma superior | jerarquia_normativa | es norma superior de | desarrolla o deriva de | rico:regulatesOrRegulated | RiC-R063 | regula o regulaba |
| Norma que crea la competencia | creacion | crea la competencia | es una competencia creada por | rico:regulatesOrRegulated | RiC-R063 | regula o regulaba |
| Regla de retención | retencion | regula la retención de | tiene su retención regulada por | rico:regulatesOrRegulated | RiC-R063 | regula o regulaba |
| Quien expide la norma | — | fue expedido por | expidió | rico:issuedBy | RiC-R065 | emitido por |
| Norma que autoriza al agente | — | autoriza a | está autorizado por | rico:authorizes | RiC-R067 | controla |
| Norma de creación | creacion | crea o establece a | fue creado o establecido por | rico:authorizes | RiC-R067 | controla |
| Relación general | — | está relacionado con | está relacionado con | rico:isRelatedTo | RiC-R001 | está relacionado con |
| Función que produce la serie | serie_producida | produce la serie | es producida por la función | rico:isRelatedTo | RiC-R001 | está relacionado con |
| Subordinación | — | tiene o tuvo como subordinado a | está o estuvo subordinado a | rico:hasOrHadSubordinate | RiC-R045 | tiene o tenía como subordinado o subordinada a |
| Sucesión | — | tiene como sucesor a | es sucesor de | rico:hasSuccessor | RiC-R016 | tiene como sucesor(a) a |
| Agentes asociados | — | está asociado con | está asociado con | rico:isAgentAssociatedWithAgent | RiC-R044 | agente está asociado con agente |
| Ocupación de un cargo | — | ocupa u ocupó el cargo | es o fue ocupado por | rico:occupiesOrOccupied | RiC-R054 | ocupa u ocupaba |
| Parentesco | — | tiene parentesco con | tiene parentesco con | rico:hasFamilyAssociationWith | — | tiene asociación familiar con |
| Parentesco: progenitor | progenitor | es padre o madre de | es hijo o hija de | rico:hasFamilyAssociationWith | — | tiene asociación familiar con |
| Parentesco: hermanos | hermano | es hermano o hermana de | es hermano o hermana de | rico:hasFamilyAssociationWith | — | tiene asociación familiar con |
| Parentesco: cónyuges | conyuge | es o fue cónyuge de | es o fue cónyuge de | rico:hasFamilyAssociationWith | — | tiene asociación familiar con |
| Miembro de un grupo | — | tiene o tuvo como miembro a | es o fue miembro de | rico:hasOrHadMember | RiC-R055 | tiene o tenía como miembro a |
| Dirección de un grupo | — | dirige o dirigió | es o fue dirigido por | rico:isOrWasLeaderOf | RiC-R042 | es o era líder de |
| Subdivisión | — | tiene o tuvo como subdivisión a | es o fue subdivisión de | rico:hasOrHadSubdivision | RiC-R005 | tiene o tenía como subdivisión |
| Cargo dentro de una entidad | — | existe o existió en | tiene o tuvo el cargo | rico:existsOrExistedIn | RiC-R056 | existe o existía en |
| Hito | — | afecta o afectó a | es o fue afectado por | rico:affectsOrAffected | RiC-R059 | afecta o afectaba a |
| Lugar que contiene a otro | — | contiene a | está dentro de | rico:containsOrContained | RiC-R007 | contiene o contenía |
| Localización | — | es o fue lugar de | está o estuvo en | rico:isOrWasLocationOf | RiC-R075 | es o era localización de |
| Lugar de expedición | expedicion | es lugar de expedición de | fue expedido en | rico:isOrWasLocationOf | RiC-R075 | es o era localización de |
| Lugar de actuación | actuacion | es o fue lugar de actuación de | actúa o actuó en | rico:isOrWasLocationOf | RiC-R075 | es o era localización de |
| Tema o mencionado | — | trata de | es tema de | rico:hasOrHadSubject | RiC-R019 | tiene o tenía como materia |
| Mencionado | mencionado | menciona a | es mencionado en | rico:hasOrHadSubject | RiC-R019 | tiene o tenía como materia |
| Lugar del que trata | lugar | trata del lugar | es lugar tratado en | rico:hasOrHadSubject | RiC-R019 | tiene o tenía como materia |
| Norma citada | mandato | cita la norma | es citada en | rico:hasOrHadSubject | RiC-R019 | tiene o tenía como materia |
| Fecha de creación | — | es fecha de creación de | fue creado en | rico:isCreationDateOf | RiC-R080 | es fecha de creación de |
| Fecha asociada | — | es fecha de | tiene la fecha | rico:isDateAssociatedWith | RiC-R068 | es fecha asociada con |
| Fecha de expedición | expedicion | es fecha de expedición de | fue expedido el | rico:isDateAssociatedWith | RiC-R068 | es fecha asociada con |
| Tipo documental | — | es del tipo documental | es el tipo documental de | rico:hasDocumentaryFormType | — | tiene como tipo documental |
