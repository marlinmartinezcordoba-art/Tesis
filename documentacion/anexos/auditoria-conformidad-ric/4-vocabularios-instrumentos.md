# Auditoría 4 · Normas complementarias de Vocabularios e Instrumentos

Alcance: sección 6 del prompt de auditoría (frentes Vocabularios e Instrumentos), contrastada con
`8a0fabdd-…Modulo_3_Vocabularios_Actualizado_2.md` y `51926adf-…Modulo_4_Instrumentos.md`.
Solo lectura: no se modificó ningún archivo del repo (`git status` limpio). Para comprobar las fugas se
escribió una prueba ad hoc **fuera del repo**:
`/tmp/claude-0/-home-user-Tesis/a0124175-e96d-5498-bade-bcd7606d68dc/scratchpad/auditoria/prueba_ad_hoc_ins/test_fugas_ad_hoc.py`
(reutiliza los fixtures `fondo_rico` y `fondo_descrito` de las pruebas del repo, contra la base PostgreSQL de pruebas, y pasa 4/4).
Esta es su salida literal:

```
ANON /api/exportacion/rdf 401
ANON /api/exportacion/conformidad 401
ANON /id (por defecto) 401
ANON catalogo 401
RDF incluye instanciacion reservada: True
ANON /id instanciacion reservada: 200 True          (con rdf_uris_publicas encendido)
consulta ficha o114: 200 True                        (rol «consulta» ve el nombre del archivo reservado)
/api/instrumentos/catalogo/<o114> 200 parte reservada visible: True hermano reservado visible: True
/api/catalogo/registros/<o114>   200 parte reservada visible: True hermano reservado visible: True
ficha directa de la parte reservada: 404
RDF parte reservada: False RDF hermano: False
RDF exporta agente solo citado en doc reservado: True
RDF doc reservado: False
```

---

## A. Vocabularios

### Tabla ISAAR-CPF (2.ª ed.) elemento por elemento, para la ficha de agente

Modelo: `app/models/descripcion.py` (EntidadVocabulario 75–126, NombreEntidad 274–293, IdentificadorEntidad 296–310, Hito 313–334); migración `alembic/versions/0011_autoridad_isaar.py:35-115`; servicio `app/servicios/autoridad.py`; API `app/routers/vocabulario.py`.

| ISAAR | Elemento | Dónde vive (columna / tabla / relación) | Estado |
|---|---|---|---|
| 5.1.1 | Tipo de entidad | `entidades_vocabulario.subtipo` (persona, entidad_corporativa, grupo, cargo, familia, mecanismo) `descripcion.py:34,86` — columna `String(40)` sin restricción en BD | presente (lista solo en código) |
| 5.1.2 | Forma autorizada del nombre | `entidades_vocabulario.nombre` `descripcion.py:87`; no editable desde vocabularios `routers/vocabulario.py:248-251` | presente |
| 5.1.3 | Formas paralelas | `nombres_entidad.tipo='paralela'` + `idioma` `descripcion.py:45,283-285` | presente |
| 5.1.4 | Formas normalizadas según otras reglas | `nombres_entidad.tipo='normalizada'` + `regla` `descripcion.py:286` | presente |
| 5.1.5 | Otras formas | `nombres_entidad.tipo='otra'` | presente |
| 5.1.6 | Identificadores de instituciones | `identificadores_entidad(esquema, valor)` `descripcion.py:296-310`; esquemas `ESQUEMA_IDENTIFICADOR` `descripcion.py:42`; validación VIAF/Wikidata/ISNI `autoridad.py:201-226` | presente |
| — | Versión del mecanismo (exigida por el prompt) | `entidades_vocabulario.version` `descripcion.py:99`; obligatoria al editar `autoridad.py:139-143` | presente, con excepción (ver VOC-07) |
| 5.2.1 | Fechas de existencia | `existencia_edtf/_inicio/_fin` `descripcion.py:102-104`; EDTF validado `autoridad.py:109-120` | presente |
| 5.2.2 | Historia | `historia` (Text) `descripcion.py:105` | presente |
| 5.2.3 | Lugares | relación `is_or_was_location_of` rol `actuacion` (vínculo `lugar_agente`) `autoridad.py:335-336` | presente (relación tipada) |
| 5.2.4 | Estatuto jurídico | `estatuto_juridico` (pública/privada/mixta) `descripcion.py:36,106`, validado `autoridad.py:121-125` | presente |
| 5.2.5 | Funciones, ocupaciones y actividades | relación `performs_or_performed` agente→actividad (vínculo `ejercida_por`) `autoridad.py:344-345`; sin vínculo directo agente→tipo de actividad | presente, indirecto |
| 5.2.6 | Atribuciones / fuentes legales | relación `authorizes` rol `creacion` (mandato que crea al agente) `autoridad.py:354-355` + cadena actividad→mandato `autoridad.py:347-348` | presente |
| 5.2.7 | Estructura interna / genealogía | `estructura` (Text) `descripcion.py:107` — no se exporta a RDF `exportacion_rico.py:384-385` | presente (texto libre, sin RDF) |
| 5.2.8 | Contexto general | `contexto_general` `descripcion.py:108` → `rico:generalDescription` `exportacion_rico.py:382-383` | presente |
| — | Línea de tiempo (hitos, rico:Event) | tabla `hitos` `descripcion.py:313-334`; `autoridad.py:245-278`; RDF `exportacion_rico.py:427-434` | presente |
| 5.3.1 | Nombre/identificador de la entidad relacionada | `relaciones.origen_id/destino_id` `descripcion.py:178-181` | presente |
| 5.3.2 | Categoría de la relación (jerárquica, temporal, **familiar**, asociativa) | `VINCULOS` `autoridad.py:328-333`: `subordinado`, `sucesor`, `asociado`. **Categoría familiar: ausente** | incompleto |
| 5.3.3 | Descripción de la relación | `relaciones.nota` `descripcion.py:199` | presente (no se exporta a RDF) |
| 5.3.4 | Fechas de la relación | `relaciones.fecha_edtf` `descripcion.py:198` | presente (no se exporta a RDF) |
| 5.4.1 | Identificador del registro de autoridad | `entidades_vocabulario.id` → `control.identificador_registro` `autoridad.py:607` | presente |
| 5.4.2 | Identificadores de la institución | — | **ausente** |
| 5.4.3 | Reglas o convenciones | `reglas` `descripcion.py:111`, valor por defecto ISAAR 2.ª ed. `autoridad.py:36,608` | presente |
| 5.4.4 | Estado de elaboración (borrador/finalizado/revisado) | — | **ausente** |
| 5.4.5 | Nivel de detalle | `nivel_detalle` (mínimo/completo; ISAAR prevé mínimo/parcial/completo) `descripcion.py:112`; recálculo `autoridad.py:88-96` | presente (2 de 3 valores) |
| 5.4.6 | Fechas de creación y revisión | `creado_en` + última fecha de auditoría `autoridad.py:591-613` | presente |
| 5.4.7 | Lenguas y escrituras | — | **ausente** |
| 5.4.8 | Fuentes | `fuentes` (Text) `descripcion.py:114` | presente |
| 5.4.9 | Notas de mantenimiento | — (solo el registro de auditoría) | **ausente** |

### Tabla ISDF elemento por elemento, para el tipo de actividad (`clase='tipo_actividad'`)

Campos editables del tipo de actividad: solo `historia` (`CAMPOS_GENERALES`, `autoridad.py:50,57-62`).

| ISDF | Elemento | Dónde vive | Estado |
|---|---|---|---|
| 5.1.1 | Tipo (función, subfunción, proceso, actividad, transacción) | — (solo la profundidad del árbol; `subtipo` sin uso para esta clase) | **ausente** |
| 5.1.2 | Forma autorizada del nombre | `entidades_vocabulario.nombre` | presente |
| 5.1.3 | Formas paralelas | `agregar_nombre` rechaza clases distintas de agente/lugar `autoridad.py:177-178` | **ausente** |
| 5.1.4 | Otras formas del nombre | ídem | **ausente** |
| 5.1.5 | Clasificación (código del cuadro / TRD) | no hay columna de código en `entidades_vocabulario` (`descripcion.py:83-121`) | **ausente** |
| 5.2.1 | Fechas | `existencia_edtf` solo editable en agentes (`CAMPOS_AGENTE`, `autoridad.py:47`); `_periodo` solo para agente/actividad `exportacion_rico.py:386-387` | **ausente** |
| 5.2.2 | Descripción | `historia` usado como nota de alcance `autoridad.py:50` — **no se exporta para tipo_actividad** `exportacion_rico.py:380` | incompleto |
| 5.2.3 | Historia | el mismo campo único `historia` | fusionado con 5.2.2 |
| 5.2.4 | Legislación | vínculo `competencia_creada_por` (mandato→tipo_actividad, R063 rol `creacion`) `autoridad.py:357-359` | presente |
| 5.3 | Relación función–función (jerárquica, temporal, asociativa) | solo jerárquica: `concepto_superior_id` (skos:broader) `descripcion.py:121`, `autoridad.py:527-584`; temporal y asociativa ausentes | incompleto |
| 6.1 | Función–entidad corporativa | solo indirecta (agente→actividad→tipo) | incompleto |
| 6.2 | Función–documentos | vínculo `serie_producida` (R001 rol `serie_producida`) `autoridad.py:364-365` | presente |
| 5.4.1 | Identificador de la descripción | `id` (`control.identificador_registro`) | presente |
| 5.4.2 | Identificadores de la institución | — | **ausente** |
| 5.4.3 | Reglas | `reglas` no editable para esta clase (`CAMPOS_GENERALES`) y `control.reglas` = None salvo agente `autoridad.py:608` | **ausente** |
| 5.4.4 | Estado de elaboración | — | **ausente** |
| 5.4.5 | Nivel de detalle | `control.nivel_detalle` = None salvo agente `autoridad.py:609` | **ausente** |
| 5.4.6 | Fechas de creación/revisión | `control.creada_en/revisada_en` `autoridad.py:611-612` | presente |
| 5.4.7 | Lenguas | — | **ausente** |
| 5.4.8 | Fuentes | `fuentes` no editable para esta clase | **ausente** |
| 5.4.9 | Notas de mantenimiento | — | **ausente** |

Balance ISDF: 6 de 21 elementos presentes (nombre, legislación, función–documentos, identificador, fechas de control, nota de alcance). En la práctica, el tipo de actividad es **nombre + jerarquía SKOS + una nota + dos vínculos**.

---

### VOC-01 · Ficha de agente ISAAR-CPF: cuatro áreas, pero control e identificación incompletos
- Rama: ISAAR-CPF
- Módulo(s): vocabularios
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/descripcion.py:95-114` — columnas de las áreas de descripción y control
  - `app/models/descripcion.py:274-334` — formas del nombre, identificadores, hitos
  - `alembic/versions/0011_autoridad_isaar.py:35-115` — migración de todo lo anterior
  - `app/servicios/autoridad.py:47-54,88-164` — campos editables, recálculo del nivel de detalle
  - `app/servicios/autoridad.py:587-651` — ficha con el bloque `control`
  - `app/routers/vocabulario.py:242-305` — PATCH, nombres, identificadores, hitos
  - `frontend/src/components/FichaAutoridad.tsx` — pantalla de la ficha
  - Buscado en models, alembic, servicios, routers, tests y frontend con los términos `estado_elaboracion|status|lengua|escritura|notas_mantenimiento|institucion_responsable`: sin resultado para 5.4.2, 5.4.4, 5.4.7 y 5.4.9
- Prueba automatizada: `tests/test_autoridad.py::test_ficha_de_agente_guarda_sus_cuatro_areas_con_existencia_abierta`, `::test_nivel_de_detalle_pasa_a_completo_y_el_filtro_lo_respeta`, `::test_identificador_externo_conserva_su_esquema_y_se_distingue_del_interno`, `::test_hitos_se_guardan_con_su_fecha_y_se_listan_cronologicamente`, `::test_agente_grupo_se_guarda_lista_y_filtra`
- Razonamiento: las áreas de identificación y descripción están completas y persisten en columnas o tablas propias. El área de control cubre 5 de 9 elementos: faltan los identificadores de la institución, el estado de elaboración, las lenguas y escrituras y las notas de mantenimiento. El nivel de detalle tiene 2 valores donde ISAAR prevé 3. El tipo de entidad (`subtipo`) es un `String(40)` sin restricción en la base (`descripcion.py:86`): la lista controlada solo existe en el código. Por la prueba de profundidad, «Entidad corporativa» y «entidad_corporativa» no podrían convivir solo porque lo impide la API, no la base de datos.
- Acción recomendada: agregar `estado_elaboracion`, `lenguas` (ISO 639/15924), `institucion_responsable` y `notas_mantenimiento`; restringir `subtipo` con un ENUM o CHECK por clase; agregar el valor «parcial».

### VOC-02 · Relaciones de parentesco, cargo y membresía: no se pueden declarar como relaciones tipadas
- Rama: ISAAR-CPF (5.3.2) / RiC-O
- Módulo(s): vocabularios
- Clasificación: No implementado
- Evidencia:
  - `app/servicios/autoridad.py:326-333` — `VINCULOS` entre agentes: solo `subordinado` (R045), `sucesor` (R016) y `asociado` (R044)
  - `app/routers/vocabulario.py:90-94` — `RelacionAgentesIn.tipo: Literal["subordinado","sucesor","asociado"]`
  - `app/servicios/vocabulario.py:318-322` — `RELACION_AGENTES`, con los mismos tres tipos
  - `app/models/enums.py:89-92` — `occupies_or_occupied` (R054), `exists_or_existed_in` (R056), `has_or_had_member` (R055) e `is_or_was_leader_of` (R042) están en el catálogo de códigos
  - `app/servicios/ric_o.py:179-180` — `occupies_or_occupied` tiene propiedad RiC-O, pero ningún servicio ni ruta la crea
  - Buscado con `occupies_or_occupied|has_or_had_member|parentesco|hasFamily|isOrWasMemberOf|membres` en app, tests, alembic y frontend: solo aparece en el catálogo y en etiquetas (`instrumentos.py:571`)
- Prueba automatizada: ninguna encontrada. `tests/test_autoridad.py::test_jerarquia_entre_cargos_usa_la_misma_relacion` cubre la jerarquía entre cargos, no la ocupación de un cargo por una persona.
- Razonamiento: la relación familiar (categoría 5.3.2 de ISAAR; en RiC-O, `rico:hasFamilyAssociationWith` o una relación familiar), la relación persona ocupa cargo (R054) y la membresía persona→grupo (R055) no se pueden declarar. Los tres códigos existen en el ENUM de la base, pero ninguna ruta ni servicio los escribe. Hoy el archivista tendría que usar «asociado» (R044) y poner «hermano de» o «miembro de» en la `nota` de texto libre. Prueba de profundidad: dos archivistas que registran «es hijo de» y «hijo» terminan en dos notas libres sobre la misma R044 genérica, no en un tipo controlado.
- Acción recomendada: agregar a `VINCULOS` los vínculos `familia` (verificando la propiedad en el OWL), `ocupa_cargo` (R054, persona→cargo, con vigencia) y `miembro_de` (R055), con validación de subtipos y sus pruebas.

### VOC-03 · Tipo de actividad (ISDF): poco más que nombre y jerarquía SKOS
- Rama: ISDF
- Módulo(s): vocabularios
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia: tabla ISDF anterior; además:
  - `app/servicios/autoridad.py:50` — `CAMPOS_GENERALES = ("historia",)`
  - `app/servicios/autoridad.py:177-178` — sin formas del nombre para el tipo de actividad
  - `app/routers/vocabulario.py:283-284` — sin identificadores fuera de los agentes
  - `app/servicios/exportacion_rico.py:380` — la `historia` del tipo de actividad no se exporta
  - Buscado con `codigo_clasificacion|clasificacion|codigo_trd|tipo_funcion` en models y alembic: solo `TIPO_FUNCION` en `app/models/enums.py:43`, sin uso
- Prueba automatizada: `tests/test_autoridad.py::test_arbol_de_funciones_se_arma_con_skos_y_no_admite_ciclos`, `::test_tipo_de_actividad_con_su_serie_documental`, `::test_mandato_que_crea_una_competencia`
- Razonamiento: la sección 6 de la auditoría pide verificar que el cuadro de funciones no sea «solo un nombre y una jerarquía SKOS». Hay algo más: una nota, el vínculo con la serie (TRD) y el mandato que crea la competencia. Pero 15 de 21 elementos ISDF faltan: tipo, formas del nombre, código de clasificación (central en la TRD colombiana), fechas, relaciones temporal y asociativa entre funciones, y todo el área de control salvo id y fechas. Prueba de profundidad: el código de la función en el cuadro de clasificación solo puede escribirse dentro del nombre («200.12 Gestión de permisos»), en texto libre.
- Acción recomendada: agregar para `tipo_actividad` las columnas tipo ISDF, `codigo_clasificacion` (con `skos:notation`), fechas EDTF, formas del nombre, reglas, estado, nivel de detalle y fuentes; agregar las relaciones temporal y asociativa entre funciones; exportar la nota como `skos:scopeNote`.

### VOC-04 · SKOS: broader/narrower y prefLabel sí; altLabel y notation no
- Rama: SKOS
- Módulo(s): vocabularios, instrumentos
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/descripcion.py:121` — `concepto_superior_id` (broader)
  - `app/servicios/autoridad.py:527-584` — `fijar_concepto_superior` sin ciclos, `arbol_funciones`
  - `app/routers/vocabulario.py:185-188` — `GET /api/vocabulario/funciones/arbol`
  - `app/servicios/autoridad.py:638-641` — `broader`/`narrower` en la ficha
  - `app/servicios/exportacion_rico.py:368-379` — `skos:Concept`, `skos:prefLabel`, `skos:inScheme` y `skos:hasTopConcept` (solo `tipo_actividad`), `skos:broader`
  - Buscado `altLabel|notation|hiddenLabel|scopeNote|definition` en app: sin resultado; `narrower` solo aparece en la ficha JSON, no en el RDF
- Prueba automatizada: `tests/test_autoridad.py::test_arbol_de_funciones_se_arma_con_skos_y_no_admite_ciclos`, `tests/test_exportacion_rico.py::test_contexto_agentes_lugar_funciones_actividad_mandato`
- Razonamiento: la jerarquía funciona con niveles ilimitados y sin ciclos, y se exporta como `skos:broader` dentro de un `ConceptScheme` por fondo. Faltan `skos:altLabel`: el tipo de actividad no admite otras formas del nombre, y las de agentes y lugares van a `rico:AgentName`/`PlaceName`. Falta `skos:notation`: no hay código. Falta `skos:narrower` explícito: sin razonador, un consumidor no ve los hijos. Las formas documentales y los tipos de parte se emiten como `skos:Concept` sin `inScheme`.
- Acción recomendada: emitir `skos:narrower` y `skos:altLabel`; agregar `skos:notation` (ver VOC-03); crear un `ConceptScheme` para formas documentales.

### VOC-05 · Detección de duplicados y fusión
- Rama: ISAAR-CPF / RiC-CM (registro único y reutilizable)
- Módulo(s): vocabularios
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `alembic/versions/0003_descripcion.py:24` — `CREATE EXTENSION pg_trgm`; índice GIN `app/models/descripcion.py:123-126`
  - `app/servicios/vocabulario.py:81-98` — `verificar()` compara **solo** `nombre_normalizado`
  - `app/servicios/vocabulario.py:253-291` — `detectar_candidatos()`, comparación solo nombre contra nombre, siempre dentro de un mismo fondo
  - `app/servicios/vocabulario.py:294-315` — `deteccion_periodica()`, la llama el trabajador en `app/trabajador.py:66` (servicio `trabajador` de `docker-compose.yml`)
  - `app/servicios/vocabulario.py:137-198,201-250` — fusión transaccional, que redirige origen y destino, mueve hitos, nombres, identificadores, hijos SKOS y usos de mecanismo, y deja auditoría
  - `app/routers/exportacion.py:151-157` — la URI de una entidad fusionada responde 301 hacia la definitiva
  - `app/servicios/autoridad.py:214-218` — un identificador repetido solo se rechaza **en la misma entidad**
  - Decisiones documentadas: `documentacion/modulo-3-vocabularios.md:372-374`
- Prueba automatizada: `tests/test_vocabularios.py::test_verificacion_detecta_parecidos_sin_falsos_positivos`, `::test_deteccion_sugiere_solo_pares_parecidos_y_poco_conectados`, `::test_la_busqueda_periodica_respeta_el_intervalo`, `::test_aprobar_sugerencia_redirige_relaciones_marca_fusionada_y_audita`, `::test_descartar_no_cambia_nada`, `::test_fusion_manual_igual_que_sugerencia`, `::test_fusionada_fuera_del_listado_pero_accesible`, `::test_ninguna_fusion_sin_permiso_ni_sin_auditoria`; `tests/test_autoridad.py::test_fusion_lleva_la_ficha_a_la_definitiva_y_queda_en_auditoria`; `tests/test_exportacion_rico.py::test_la_uri_de_una_entidad_fusionada_redirige_a_la_definitiva`
- Razonamiento: la fusión es sólida: transaccional, sin borrado físico, auditada y con URI persistente. La detección tiene tres huecos:
  1. Ignora las otras formas del nombre (`nombres_entidad`). «Alcaldía de Tunja» y «Municipio de Tunja» no se detectan aunque una figure como forma paralela de la otra.
  2. Ignora los identificadores. Dos agentes con el mismo Wikidata `Q…` o el mismo VIAF coexisten sin ninguna sugerencia, que es la señal de duplicado más fuerte.
  3. El registro es «único por fondo». La misma persona en dos fondos queda en dos registros no relacionados, y nada los compara. RiC concibe el agente como reutilizable entre fondos.

  Prueba de profundidad: dos archivistas que registran «Secretaría de Gobierno» en dos fondos terminan con dos registros distintos. Las pruebas de verificación y detección solo usan agentes (y un negativo con lugar); el prompt exige cubrir los seis tipos (§11).
- Acción recomendada: incluir `nombres_entidad` y la coincidencia exacta de `(esquema, valor)` externos en `verificar()` y `detectar_candidatos()`; evaluar autoridades compartidas entre fondos; parametrizar las pruebas para los seis tipos.

### VOC-06 · Relaciones entre agentes: tipadas en la base, pero sin fechas ni nota en RDF
- Rama: RiC-O / ISAAR-CPF 5.3.3–5.3.4
- Módulo(s): vocabularios, instrumentos
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/autoridad.py:415-466` — `vincular()`: una fila en `relaciones` con `codigo_ric`, `fecha_edtf`, `nota`, sin ciclos y auditada
  - `app/models/enums.py:157-163` — inversas
  - `app/servicios/exportacion_rico.py:243-252` — `_relacion()` emite solo la tripleta directa; `fecha_edtf` y `nota` no salen
  - `app/servicios/autoridad.py:347-359` — `mandato_superior` y `competencia_creada_por` usan el mismo `regulates_or_regulated`, y `creado_por` usa `authorizes`; el `rol` que los distingue no sale en el RDF
- Prueba automatizada: `tests/test_autoridad.py::test_relacion_entre_agentes_es_una_fila_con_su_inversa_fecha_y_nota`, `::test_mandato_derivado_se_navega_en_ambos_sentidos_sin_ciclos`
- Razonamiento: subordinación, sucesión y asociación son relaciones tipadas entre registros, no texto libre. Cumple la exigencia de la sección 6 para esos tres tipos (no para parentesco, cargo ni membresía: VOC-02). La inversa se lee de la misma fila, con una prueba que lo confirma. En la exportación, la vigencia y la descripción de la relación se pierden porque no se usa la forma n-aria `rico:AgentHierarchicalRelation`/`AgentTemporalRelation`. Por la misma razón, «el decreto X deriva de la ley Y» y «el decreto X regula la actividad Z» salen con la misma propiedad, sin distinguirse.
- Acción recomendada: exportar las relaciones fechadas o con nota como `rico:*Relation` con `rico:hasBeginningDate`/`hasEndDate` y `rico:generalDescription`; reflejar el `rol` en la clase de relación.

### VOC-07 · Mecanismo con versión como registro reutilizable
- Rama: RiC-CM (Mechanism RiC-E13) / PREMIS Agent
- Módulo(s): vocabularios, preservacion, descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/vocabulario.py:375-403` — `mecanismo()` reutiliza por (fondo, nombre normalizado, versión)
  - `app/servicios/vocabulario.py:406-416` — `usos_mecanismo`: FK desde instanciaciones, migraciones, verificaciones, segundas copias, restauraciones y procedencia del motor
  - `alembic/versions/0013_mecanismos_reutilizados.py` — migración
  - `app/servicios/mecanismos.py:34-36` — **`version or "desconocida"`**: un programa sin versión se registra con la versión literal «desconocida»
  - `app/servicios/vocabulario.py:279-282` — dos versiones nunca se sugieren como duplicadas
  - `app/servicios/exportacion_rico.py:214` — los mecanismos no se exportan
  - `app/servicios/mecanismos.py:139` — `vincular_anteriores`, la llama el trabajador
- Prueba automatizada: `tests/test_mecanismos.py::test_migracion_automatica_queda_vinculada_a_ghostscript_con_su_version_exacta`, `::test_un_mecanismo_ya_registrado_en_el_vocabulario_se_reutiliza`, `::test_identificacion_verificacion_y_segunda_copia_apuntan_a_su_mecanismo`, `::test_fusionar_dos_mecanismos_mueve_sus_acciones_tecnicas`; `tests/test_autoridad.py::test_mecanismo_guarda_su_version_y_se_reutiliza`, `::test_mecanismo_sin_version_queda_marcado`
- Razonamiento: preservación y descripción reutilizan el mismo registro, con versión y FK, y hay pruebas de ello. Hay dos brechas:
  1. El registro es por fondo: Ghostscript 10.02.1 existe tantas veces como fondos hay.
  2. El valor por defecto «desconocida» satisface la obligatoriedad de la versión sin declararla. El prompt la exige obligatoria, y ese valor mezcla todas las ejecuciones sin versión bajo un mismo mecanismo.
- Acción recomendada: mecanismos globales (no por fondo) o vinculados entre fondos; marcar el caso sin versión como pendiente (`falta_version`) en vez de inventar el valor.

### VOC-08 · Lugar ampliado, actividad y mandato (compromisos 5bis y 6 del prompt)
- Rama: RiC-CM / RiC-O
- Módulo(s): vocabularios
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/models/descripcion.py:116-118` — latitud, longitud, tipo de lugar
  - `app/servicios/autoridad.py:131-134,144-148` — coordenadas validadas por pares
  - `app/servicios/autoridad.py:338-339` — lugar contenido en otro (R007), sin ciclos y con un solo superior
  - `app/servicios/autoridad.py:175-176` — nombres históricos con vigencia
  - `app/servicios/exportacion_rico.py:392-397,402-411` — exportación
  - `app/servicios/autoridad.py:341-342` — sub-actividad (`hasDirectSubevent`), distinta de SKOS
  - `app/servicios/autoridad.py:349-362` — jerarquía normativa, mandato creador, emisor
  - Mapa: `documentacion/modulo-3-vocabularios.md:374` (incrustación de OSM) y `frontend/src/components/FichaAutoridad.tsx`
- Prueba automatizada: `tests/test_autoridad.py::test_lugar_con_coordenadas_tipo_superior_y_nombres_historicos`, `::test_sub_actividades_se_listan_y_no_se_confunden_con_skos`, `::test_mandato_derivado_se_navega_en_ambos_sentidos_sin_ciclos`, `::test_mandato_que_crea_un_agente_y_entidad_que_lo_expidio`
- Razonamiento: los compromisos 5bis y 6 tienen modelo, servicio, API y prueba. La salvedad sobre la pérdida del `rol` en el RDF está en VOC-06.

### VOC-09 · Compromisos del prompt de vocabularios sin implementar o parciales (lista)
- Rama: ISAAR-CPF / ISDF / SKOS
- Módulo(s): vocabularios
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia: búsquedas en models, alembic, servicios, routers, tests y frontend descritas en VOC-01 a VOC-07.
- Prueba automatizada: ninguna para los puntos listados.
- Razonamiento: lo prometido que falta o está a medias es:
  1. Relaciones de parentesco, cargo y membresía (VOC-02).
  2. Pruebas de verificación y detección «para cada uno de los seis tipos» (§11): solo hay agentes.
  3. Mecanismo como registro único fuera del fondo y versión realmente obligatoria (VOC-07).
  4. La ficha del tipo de actividad no tiene área de control (VOC-03).
  5. La serialización RDF de la vigencia y la nota de las relaciones entre agentes (VOC-06).

  El resto de §3 a §8 (verificación, detección periódica con el trabajador, fusión con aprobación, árbol SKOS, ficha ISAAR, lugar ampliado, hitos, VIAF/Wikidata, nivel de detalle con filtro) tiene código y prueba. La confirmación contra el OWL de la asociativa quedó hecha (R044, `documentacion/modulo-3-vocabularios.md:490`).
- Acción recomendada: ver las acciones de cada hallazgo.

---

## B. Instrumentos

### INS-01 · La exportación RDF (Turtle/JSON-LD) NO responde sin autenticación; las URI solo si el administrador lo enciende
- Rama: RiC-O / Datos abiertos (Ley 1712, art. 11)
- Módulo(s): instrumentos, autenticacion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/routers/exportacion.py:46-48` — `GET /api/exportacion/rdf` exige `Depends(lectura_catalogo)`; `lectura_catalogo` → `_catalogo` → `usuario_actual` (`app/core/permisos.py:109-122,184-191`), que exige un token Bearer
  - `app/routers/exportacion.py:61-63` — `/conformidad`, ídem
  - `app/routers/exportacion.py:140-145` — `/id/{…}`: sin sesión responde **401** salvo que `rdf_uris_publicas` sea verdadero
  - `app/servicios/parametros.py:44` — `rdf_uris_publicas` vale **False** por defecto; `app/routers/exportacion.py:85-90` — solo el administrador lo cambia
  - `app/routers/exportacion.py:126-137` — `_actor_si_hay`: un token inválido se trata como anónimo
  - `app/servicios/exportacion_rico.py:55-60` y `app/core/config.py:80` — la URI es `RICORA_URL_PUBLICA + /id/ + uuid`, y en el despliegue esa base es `http://${IP}` (`deploy-ricora.sh:29`)
  - Prueba ad hoc (salida al inicio): anónimo → `/api/exportacion/rdf` 401, `/conformidad` 401, `/id/…` 401 por defecto
- Prueba automatizada: `tests/test_exportacion_rico.py::test_las_uri_se_resuelven_con_negociacion_de_contenido` (401 sin sesión por defecto; 200 tras encenderlo), `::test_con_uris_publicas_lo_reservado_sigue_sin_resolverse`, `::test_turtle_y_json_ld_dicen_lo_mismo`
- Razonamiento: la sección 6 pide verificar que la exportación con URI estables «responde de verdad sin exigir autenticación». No es así:
  - la descarga del fondo completo (Turtle o JSON-LD) exige sesión siempre;
  - la resolución nodo por nodo existe, con negociación de contenido, extensión y redirección 301 de entidades fusionadas, pero está apagada por defecto y depende de una decisión del administrador.

  Además, las URI no son estables mientras la base sea `http://<IP>` (`deploy-ricora.sh:29`): cambiar a un dominio cambia todas las URI ya publicadas, y no hay ningún mecanismo de redirección desde la base anterior. Código presente ≠ capacidad operando.
- Acción recomendada: un punto público de descarga del subconjunto público (sin sesión, con el mismo filtro que `/id/`); fijar un dominio permanente (o un servicio PURL o w3id) antes de publicar URI, y documentar que `url_publica` no puede cambiar.

### INS-02 · Filtro por nivel de acceso Ley 1712: funciona por descripción, pero hay fugas en la ficha del catálogo y en el RDF
- Rama: Ley 1712 de 2014 (arts. 18–19)
- Módulo(s): instrumentos, descripcion, preservacion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/preservacion.py:41,118-134` — `DeclaracionDerechos.acceso` ∈ (publico, clasificado, reservado), sobre una instanciación **o** un recurso
  - `app/servicios/exportacion_rico.py:98-113` — `_restringidas()` solo consulta declaraciones cuyo `entidad_id` es un **recurso** (`in_(list(recursos))`). Ignora las declaraciones sobre una instanciación.
  - `app/servicios/exportacion_rico.py:116-136` — `_recursos()` quita lo restringido (propio o heredado) y lo que cuelga de un nivel quitado
  - `app/servicios/exportacion_rico.py:225-231` — `_cargar()` incluye cualquier instanciación enlazada, sin mirar su derecho propio
  - `app/servicios/exportacion_rico.py:157-181` — la frontera se expande de entidad en entidad sin volver a comprobar que la entidad tenga un documento visible
  - `app/servicios/consulta.py:35,41-47` — `ficha_publica` copia `instanciaciones`, `partes` y `secuencia` de `descripcion.detalle()` (`app/servicios/descripcion.py:790-818`) **sin filtrarlos** por acceso ni por publicación
  - `app/servicios/instrumentos.py:205-209` y `app/routers/descripcion.py:428-435` — solo se comprueba que el documento consultado sea visible, no sus partes, hermanos o archivos
  - `app/routers/instrumentos.py:70-73` — `ve_restringidos`: archivista sí, rol consulta no
  - `app/servicios/previsualizacion.py:31-40` — la previsualización sí respeta la declaración heredada (403)
  - `app/servicios/derechos.py:80-96` y `app/models/preservacion.py:130` — `vigente_hasta` se guarda, pero ningún filtro lo usa (Ley 1712, art. 22: la reserva caduca)
  - `app/models/enums.py:20` — `CONDICION_ACCESO` (abierto/restringido/reservado) quedó como código muerto: un segundo vocabulario de acceso que nadie usa
  - **Prueba ad hoc** (`…/prueba_ad_hoc_ins/test_fugas_ad_hoc.py`):
    - (a) con un PDF declarado reservado sobre la propia instanciación, el RDF lo incluye (`True`), `/id/<inst>` lo sirve sin sesión cuando las URI son públicas (200, con el nombre del archivo), y el rol consulta ve su nombre en la ficha;
    - (b) una parte documental reservada y un documento hermano reservado enlazado por `precedes_or_preceded`: el rol consulta ve su título en `/api/instrumentos/catalogo/{id}` y en `/api/catalogo/registros/{id}`, aunque la ficha directa de la parte da 404 y el RDF los excluye;
    - (c) un agente citado solo en un documento reservado, y vinculado como «asociado» a otro agente público, sale en el RDF por defecto (`True`).
- Prueba automatizada: `tests/test_exportacion_rico.py::test_lo_clasificado_o_reservado_no_se_exporta_por_defecto`, `::test_con_uris_publicas_lo_reservado_sigue_sin_resolverse`, `::test_incluir_lo_reservado_exige_permiso_de_escritura`. Ninguna cubre declaraciones sobre instanciaciones, partes, secuencia ni entidades alcanzadas por vínculos.
- Razonamiento: el filtro es real para el árbol de descripciones (propio y heredado), tanto en el catálogo como en el índice, el grafo, el RDF y `/id/`. Pero no es hermético. La ficha pública arma partes, secuencia e instanciaciones desde la vista interna sin filtrarlas, y el RDF ignora la clasificación hecha a nivel de archivo, aunque es justo el nivel donde el módulo de preservación permite declararla. El nombre del archivo y el título de una parte reservada pueden ser información reservada en sí mismos. Un consumidor anónimo (con URI públicas) o el rol consulta los recibe. La reserva vencida nunca se levanta: es un exceso de restricción, no una fuga, pero también incumple el art. 22.
- Acción recomendada: aplicar en `ficha_publica` (o en `instrumentos.ficha`) el filtro de `arbol(...).nodos` a `partes` y `secuencia`, y `derechos.aplicable()` a cada instanciación; incluir en `_restringidas`/`_cargar` las declaraciones de instanciación; no expandir la frontera desde una entidad que no tenga un documento visible; aplicar `vigente_hasta`; retirar `CONDICION_ACCESO` o unificarlo; agregar pruebas de regresión con los tres casos de la prueba ad hoc.

### INS-03 · La guía del fondo incluye lo reservado y lo envía al motor externo
- Rama: Ley 1712 de 2014
- Módulo(s): instrumentos
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/instrumentos.py:95` — `arbol(..., ver_restringidos=True)` por defecto
  - `app/servicios/instrumentos.py:423-455` — `datos_guia()` llama a `arbol(db, fondo)` (línea 426) sin filtro, y los agentes «principales» se cuentan con `conexiones_de` sobre todos los documentos
  - `app/servicios/instrumentos.py:472-480` — esos datos se envían a `motor.redactar` (Gemini, `app/servicios/motor.py:261-262`)
  - `app/servicios/instrumentos.py:489-517` — `guia_docx` pone los títulos de las secciones y series en el documento exportable
- Prueba automatizada: `tests/test_instrumentos.py::test_guia_redactada_por_el_motor_y_exportada_tal_como_se_edito` (no cubre acceso)
- Razonamiento: la guía es un instrumento de difusión pública, pero se arma con todo lo publicado, incluidas las secciones o series clasificadas o reservadas y sus «alcance y contenido». Esos datos se envían además a un servicio externo de IA. El inventario FUID también incluye lo reservado, lo que es defendible como instrumento interno de transferencia, pero no lo marca.
- Acción recomendada: `datos_guia` con `ver_restringidos=False`; marcar en el FUID los renglones clasificados o reservados.

### INS-04 · No hay punto SPARQL
- Rama: SPARQL
- Módulo(s): instrumentos
- Clasificación: No implementado
- Evidencia: buscado `sparql` (sin distinguir mayúsculas) en todo el repo, excluidos `.venv` y `node_modules`: **cero resultados** en app, routers, servicios, tests, frontend, documentación y alembic, salvo dentro del OWL. `requirements.txt:46-47` solo trae `rdflib` y `pyshacl`, sin almacén de tripletas (`pyoxigraph` aparece únicamente en `.venv`, fuera de `requirements.txt`). `app/main.py:37-52` no monta ninguna ruta de consulta.
- Prueba automatizada: ninguna encontrada.
- Razonamiento: no existe un punto de consulta SPARQL de solo lectura, ni sobre el subconjunto público ni sobre el grafo completo. El riesgo de alcance que señala la auditoría (responder sobre el grafo interno) no se materializa porque no hay punto alguno. Si se construye, la fuente debe ser `exportacion_rico.exportar(..., incluir_restringidos=False)` ya corregido según INS-02, nunca la base.
- Acción recomendada: si la tesis lo compromete, un punto `/sparql` de solo lectura (rdflib u Oxigraph en memoria) cargado solo con el grafo público por fondo, con límite de tiempo y sin `SERVICE`/`LOAD`; con pruebas que verifiquen que una consulta no devuelve recursos reservados.

### INS-05 · EAD3, EAC-CPF e IIIF: no existen
- Rama: EAD3, EAC-CPF, IIIF
- Módulo(s): instrumentos, vocabularios
- Clasificación: No implementado
- Evidencia:
  - Buscado `ead3|\bEAD\b|eac-cpf|eac_cpf|eaccpf|iiif|manifest.json|presentation api` en app, tests, alembic, frontend y documentación: sin código
  - `documentacion/modulo-4-instrumentos.md:241` — «Pendiente para más adelante: EAD y CSV»
  - `documentacion/rediseno-navegacion.md:13,247` — «No existía ningún visor IIIF … **No es IIIF**»: el visor es un renderizador PNG propio (`app/servicios/previsualizacion.py`)
  - `tests/test_auditoria_v7.py:48` — el propio sistema registra el hallazgo «Sin exportación EAD»
- Prueba automatizada: ninguna encontrada.
- Razonamiento: no hay exportación EAD3 del fondo ni EAC-CPF de las fichas de autoridad, aunque estas tienen casi todos los datos ISAAR que EAC-CPF necesita (VOC-01). Tampoco hay manifiestos IIIF Presentation ni servidor IIIF Image. El equipo lo reconoce en su documentación.
- Acción recomendada: EAC-CPF desde `autoridad.ficha()` es el paso de menor costo; EAD3 desde `instrumentos.arbol()`; IIIF solo si la tesis lo compromete (Cantaloupe con manifiestos generados).

### INS-06 · Inventario FUID: generado y con pendientes marcados, pero con columnas incompletas frente al Acuerdo 042 de 2002
- Rama: CCD/TRD (AGN, FUID)
- Módulo(s): instrumentos
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/instrumentos.py:242-254` — `COLUMNAS_FUID`: orden, código, nombre, fecha inicial, fecha final, caja, carpeta, folios, soporte, notas
  - `app/servicios/instrumentos.py:273-308` — renglones y pendientes
  - `app/servicios/instrumentos.py:323-346` — alerta con conteo
  - `app/servicios/instrumentos.py:349-405` — xlsx (openpyxl), encabezado: fondo, nivel, «Objeto: Inventario documental», fecha
  - `app/routers/instrumentos.py:173-194`
- Prueba automatizada: `tests/test_instrumentos.py::test_inventario_un_renglon_por_unidad_o_expediente_con_columnas_fuid`, `::test_campo_obligatorio_vacio_queda_pendiente_sin_bloquear`, `::test_alerta_con_conteo_solo_cuando_hay_pendientes`, `::test_ningun_archivo_exportado_lleva_campos_internos`
- Razonamiento: el flujo pedido por el prompt (generar sin bloquear, celdas pendientes en ámbar, alerta en el panel central) está implementado y probado. Frente al formato del AGN faltan:
  - las unidades de conservación «Tomo» y «Otro»;
  - «Frecuencia de consulta»;
  - del encabezado: entidad remitente, entidad productora, unidad administrativa, oficina productora, objeto (transferencia primaria o secundaria, valoración, fondo acumulado…) y registro de entrada;
  - el bloque de firmas: elaborado, entregado y recibido por (nombre, cargo, firma, lugar, fecha).

  El «Objeto» queda fijo en «Inventario documental».
- Acción recomendada: completar las columnas y el encabezado del FUID; permitir elegir el objeto.

### INS-07 · Catálogo, guía e índice (compromisos del prompt de instrumentos)
- Rama: ISAD-G / instrumentos de descripción
- Módulo(s): instrumentos
- Clasificación: Implementado y conforme (salvo lo señalado en INS-02, INS-03 e INS-06)
- Evidencia:
  - `app/routers/instrumentos.py:76-90,155-158,197-213`
  - `app/servicios/instrumentos.py:45-56` — `sin_campos_internos` falla en voz alta
  - `app/servicios/instrumentos.py:472-517` — guía con motor y texto editado
  - `app/servicios/instrumentos.py:524-555` — índice agrupado y alfabético, sin mecanismos
  - Decisiones: `documentacion/modulo-4-instrumentos.md`
- Prueba automatizada: `tests/test_instrumentos.py::test_catalogo_navega_el_arbol_por_niveles`, `::test_ficha_con_entidades_vivas_y_preservacion_sin_campos_internos`, `::test_guia_redactada_por_el_motor_y_exportada_tal_como_se_edito`, `::test_indice_agrupa_por_tipo_y_ordena_alfabeticamente`, `::test_el_indice_no_lista_los_mecanismos`, `::test_generar_exige_rol_y_consultar_no`
- Razonamiento: lo que el prompt de instrumentos pide de forma explícita (§5, §6, §9) existe y está probado. El «catálogo público» no es público: exige sesión con un rol de catálogo, como manda el prompt («Todos exigen autenticación»), y la prueba ad hoc lo confirma (anónimo → 401). Para la Ley 1712, el «público» es el rol consulta, y para ese rol valen las fugas de INS-02.
- Acción recomendada: (ver INS-02 e INS-03)

### INS-08 · Compromisos de instrumentos sin implementar o parciales (lista)
- Rama: Ley 1712 / SPARQL / EAD3 / EAC-CPF / IIIF / CCD-TRD
- Módulo(s): instrumentos
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia: INS-01 a INS-06.
- Prueba automatizada: ninguna para los puntos listados.
- Razonamiento: frente al prompt del módulo 4 solo faltan las columnas completas del FUID (INS-06). Frente a las normas complementarias que exige la sección 6 de la auditoría faltan:
  1. La exportación RDF sin autenticación (INS-01).
  2. El filtro hermético Ley 1712 (INS-02 e INS-03).
  3. El punto SPARQL (INS-04).
  4. EAD3, EAC-CPF e IIIF (INS-05).
  5. El índice de información clasificada y reservada de la Ley 1712 (art. 20): buscado con `información clasificada y reservada|art. 20`, sin resultado.
- Acción recomendada: ver cada hallazgo.

---

## Tabla resumen

| ID | Título | Clasificación |
|---|---|---|
| VOC-01 | Ficha ISAAR-CPF: cuatro áreas, control e identificación incompletos | Implementado pero incompleto o no conforme |
| VOC-02 | Parentesco, cargo y membresía no declarables como relaciones tipadas | No implementado |
| VOC-03 | Tipo de actividad (ISDF): poco más que nombre + jerarquía SKOS | Implementado pero incompleto o no conforme |
| VOC-04 | SKOS: broader/prefLabel sí; altLabel, notation, narrower en RDF no | Implementado pero incompleto o no conforme |
| VOC-05 | Detección de duplicados (solo nombre, por fondo) y fusión | Implementado pero incompleto o no conforme |
| VOC-06 | Relaciones entre agentes tipadas, sin vigencia ni nota en RDF | Implementado pero incompleto o no conforme |
| VOC-07 | Mecanismo con versión reutilizable (por fondo; «desconocida») | Implementado pero incompleto o no conforme |
| VOC-08 | Lugar ampliado, actividad y mandato | Implementado y conforme |
| VOC-09 | Compromisos del prompt de vocabularios pendientes | Implementado pero incompleto o no conforme |
| INS-01 | RDF Turtle/JSON-LD exige autenticación; /id/ público solo si el administrador lo enciende; URI con base IP | Implementado pero incompleto o no conforme |
| INS-02 | Filtro Ley 1712 con fugas (instanciaciones, partes, secuencia, agentes por vínculo) | Implementado pero incompleto o no conforme |
| INS-03 | La guía incluye lo reservado y lo envía al motor externo | Implementado pero incompleto o no conforme |
| INS-04 | Punto SPARQL | No implementado |
| INS-05 | EAD3, EAC-CPF, IIIF | No implementado |
| INS-06 | FUID con columnas y encabezado incompletos | Implementado pero incompleto o no conforme |
| INS-07 | Catálogo, guía e índice del prompt | Implementado y conforme |
| INS-08 | Compromisos de instrumentos y normas complementarias pendientes | Implementado pero incompleto o no conforme |
