# Auditoría RiC-CM: entidad por entidad (frente 1)

Alcance: sección 4 del prompt de auditoría, solo la rama RiC-CM (entidades, subtipos, cardinalidad y direccionalidad de sus relaciones, nombres internos, API y pruebas). Los nombres RiC-O se citan solo cuando sirven para juzgar la correspondencia conceptual. La conformidad de la serialización RDF se audita en el frente RiC-O.

Método: lectura de `app/models`, `alembic/versions`, `app/servicios`, `app/routers`, `tests` y `frontend/src` con `grep -n`. Las clases, dominios, rangos y la ausencia de propiedades funcionales se comprobaron contra `app/recursos/ric-o/RiC-O_1-1.rdf` con rdflib (solo lectura). En RiC-O 1.1 no hay **ninguna** `owl:FunctionalProperty` ni `owl:InverseFunctionalProperty`; por eso toda restricción «a lo sumo uno» que impone el sistema es más estricta que el estándar.

Pruebas ejecutadas (solo lectura): `pytest tests/test_ric_o.py tests/test_autoridad.py tests/test_descripcion_contexto.py tests/test_descripcion_v3.py tests/test_exportacion_rico.py` dio 90 aprobadas y 2 errores. Los dos errores son `psycopg2.OperationalError: SSL connection has been closed unexpectedly` (infraestructura de la base de datos de prueba compartida), no fallos de aserción. Al repetir la prueba aislada, pasa.

---

### CM-01 · Record Resource: una tabla, y el subtipo se deduce del nivel
- Rama: RiC-CM
- Módulo(s): descripcion, ingesta
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/recurso_documental.py:13` — `NIVEL_DESCRIPCION = ("fondo","seccion","serie","subserie","expediente","unidad_documental","parte_documental")`
  - `app/models/recurso_documental.py:16` y `:28` — clase `RecursoDocumental` («RiC-E02») con `nivel` como enumerado de PostgreSQL (`nivel_descripcion`)
  - `app/servicios/ric_o.py:58-65` — `CLASE_NIVEL`: nivel → `RecordSet` / `Record` / `RecordPart`. Esta es la **única** declaración de la jerarquía de subtipos, y vive en el mapeo de exportación, no en el modelo.
  - `app/models/recurso_documental.py:30` — `fechas_extremas = String(60)` en texto libre («tal como se describe»), no es una entidad Date (ver CM-16)
  - `app/models/recurso_documental.py:73` — `soporte = String(40)` («RiC-A05 Carrier Type del original») está en el Record Resource, aunque en RiC-CM el tipo de soporte es atributo de la Instantiation (ver CM-04)
  - `app/models/enums.py:8` y `:11` — `NIVEL_DOCUMENTO` y `SOPORTE_DOCUMENTO` están declarados y nadie los usa (grep en `app/`, `alembic/`, `tests/`: sin resultado)
  - API: `app/routers/descripcion.py:207` (publicar), `:375` (ver), `:395` (corregir); `app/routers/instrumentos.py:76,85` (catálogo)
- Prueba automatizada: `tests/test_exportacion_rico.py::test_cada_nivel_con_su_clase_y_su_tipo_de_agrupacion`, `tests/test_descripcion.py::test_documento_individual_de_la_cola_a_la_publicacion`, `tests/test_ric_o.py::test_parte_documental_es_record_part_y_se_une_por_constituyente`
- Razonamiento: El Record Resource tiene su propia tabla, y sus niveles son un enumerado cerrado en la base de datos. Eso es profundo. Pero el subtipo RiC (Record Set, Record o Record Part) no existe como dato: se infiere del nivel ISAD en el momento de exportar. La correspondencia nivel → clase es fija y razonable, así que el problema es menor. Más serio es que dos atributos RiC-CM están en el lugar equivocado o en texto libre. Las fechas extremas son una cadena de 60 caracteres que el exportador interpreta con una expresión regular (`app/servicios/exportacion_rico.py:322,345`). Prueba de profundidad: si una persona escribe «1930–1955» y otra «1930 a 1955», la segunda no se interpreta y queda como literal sin normalizar.
- Acción recomendada: Guardar las fechas extremas como nodos `Fecha` (EDTF), igual que las fechas de documento. Llevar el tipo de soporte a la Instantiation (física) cuando exista (ver CM-04). Eliminar o usar `NIVEL_DOCUMENTO` y `SOPORTE_DOCUMENTO`.

### CM-02 · Record Set (fondo, sección, serie, subserie, expediente): los niveles intermedios solo nacen de archivos, y la sección no se puede crear
- Rama: RiC-CM
- Módulo(s): descripcion, ingesta
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - Puntos de creación de un `RecursoDocumental` en todo `app/` (grep `RecursoDocumental(`): solo `app/routers/fondos.py:48` (fondo), `app/servicios/descripcion.py:669` (parte documental) y `app/servicios/descripcion.py:736` (publicar)
  - `app/servicios/descripcion.py:61` — `NIVELES_CONJUNTO = ("expediente","subserie","serie")`; `:188-193` — `abrir()` exige al menos una instanciación. Un único archivo da `unidad_documental`; varios archivos dan uno de los tres niveles de conjunto.
  - Buscado «seccion» en `app/servicios` y `app/routers`: solo aparece en etiquetas y filtros (`descripcion.py:630`, `instrumentos.py:28,30,428`), nunca en una ruta de creación. La sección solo existe en las pruebas, insertada directamente en la base de datos (`tests/test_exportacion_rico.py` fixture `fondo_rico`, `_recurso(db, "seccion", …)`).
  - `app/models/recurso_documental.py:33` — `incluido_en_id`: una sola clave foránea al superior inmediato, y a la vez la fila `includes_or_included` en `relaciones` (`app/servicios/descripcion.py:747`, `:976`). La misma inclusión se guarda dos veces.
  - `app/servicios/descripcion.py:702-708` — `_superior()`: el superior debe tener un rango estrictamente menor (no puede haber expediente dentro de expediente ni serie dentro de serie)
  - OWL: `isOrWasIncludedIn` tiene dominio `Record`/`RecordSet` y rango `RecordSet`, y **no** es funcional.
  - `app/servicios/ric_o.py:67-68` — tipo de agrupación: oficial para fondo, serie y expediente; para sección y subserie, concepto propio con `skos:broadMatch`.
- Prueba automatizada: `tests/test_descripcion.py::test_nivel_superior_valido`, `tests/test_descripcion.py::test_conjunto_como_expediente_sintetiza_y_cita_el_documento_correcto`, `tests/test_instrumentos.py::test_catalogo_navega_el_arbol_por_niveles`, `tests/test_exportacion_rico.py::test_cada_nivel_con_su_clase_y_su_tipo_de_agrupacion`. Ninguna crea una sección ni una serie vacía por la API.
- Razonamiento: En RiC-CM un Record Set es una agregación intelectual. Una serie existe porque agrupa expedientes, no porque tenga archivos propios. En RICORA una serie o subserie solo se crea al describir un lote de archivos a ese nivel, y esos archivos quedan como instanciaciones de la propia serie. No hay manera de declarar una serie pura que solo contenga expedientes. La sección no se puede crear por ninguna vía de la API aunque esté en el enumerado. Además, la inclusión admite un único superior, cuando RiC-O permite que un recurso pertenezca a varios conjuntos (por ejemplo, una colección facticia además de su expediente orgánico), y el orden estricto de niveles impide subseries anidadas o subfondos.
- Acción recomendada: Agregar una ruta para crear Record Sets sin instanciaciones (sección, serie, subserie, expediente vacío) con su productor y fechas. Hacer de la tabla `relaciones` la fuente única de la inclusión, o documentar que `incluido_en_id` es solo la inclusión «orgánica» principal y admitir más filas `includes_or_included`.

### CM-03 · Record y parte documental: los documentos de un expediente nunca llegan a ser Records
- Rama: RiC-CM
- Módulo(s): descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/descripcion.py:189-190` — un solo archivo da `nivel = "unidad_documental"` (Record)
  - `app/servicios/descripcion.py:754-757` — al publicar un conjunto, **cada archivo** se une al Record Set con `has_or_had_instantiation`; no se crea un Record por documento
  - `app/servicios/descripcion.py:157-159` y `:724-727` — una instanciación que ya tiene `has_or_had_instantiation` vigente desaparece de la cola y no se puede volver a describir («Alguno de estos documentos ya fue descrito», 409)
  - `tests/test_descripcion.py:177-206` — dos oficios distintos (Oficio 114 y Oficio 115) quedan como dos instanciaciones del mismo expediente
  - Parte documental: `app/servicios/descripcion.py:653-699` — `_partes()` crea un `RecursoDocumental` de nivel `parte_documental` solo dentro de una `unidad_documental`, unido por `has_or_had_constituent` (`:682`) y con su recorte como instanciación propia (`:694`). Se mapea a `RecordPart` (`app/servicios/ric_o.py:65`).
- Prueba automatizada: `tests/test_descripcion_v3.py::test_parte_documental_con_recorte_queda_unida_a_su_unidad_documental`, `tests/test_descripcion_v3.py::test_partes_solo_en_una_unidad_documental_y_el_recorte_de_sus_documentos`, `tests/test_grafo_contexto.py::test_la_parte_documental_es_constitutiva_como_en_la_exportacion`
- Razonamiento: El Record individual y su parte (Record Part) están bien modelados y probados cuando el documento se describe solo. Pero el flujo de conjunto viola la definición de RiC-CM: una Instantiation es la inscripción de **un mismo** Record Resource en un soporte, y dos oficios distintos no son dos inscripciones de lo mismo. En el diseño actual, esos oficios no pueden tener nunca su propio productor, fecha o destinatario, porque la cola los excluye para siempre. Prueba de profundidad: el remitente del oficio 114 y el del 115 terminan atribuidos al expediente, sin distinguirse.
- Acción recomendada: Al describir un expediente, crear (o permitir crear después) un Record por documento, incluido en el expediente con `includes_or_included`, y unir cada archivo a su Record, no al expediente.

### CM-04 · Instantiation: tabla propia y rica en datos técnicos, pero solo digital, de un único recurso y sin las relaciones entre instanciaciones que declara el catálogo
- Rama: RiC-CM
- Módulo(s): ingesta, preservacion, descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/instanciacion.py:20` — clase `Instanciacion` («RiC-E06») con huella, formato PRONOM y mecanismo de identificación (`:56`, `:64`)
  - `app/models/instanciacion.py:30,32` — `fondo_id` y `expediente_destino_id` como claves foráneas directas al Record Resource (operativas, fuera de RiC)
  - `app/models/instanciacion.py:83` — `derivada_de_id` además de la fila `migrated_into` (`app/servicios/preservacion.py:522-524`). La migración también copia `has_or_had_instantiation` al nuevo archivo (`:525-530`).
  - `app/models/instanciacion.py:87` — `recorte_de_id`: el recorte no deja fila en `relaciones` (grep `Relacion` en `app/servicios/recorte.py`: sin resultado). `has_or_had_derived_instantiation`, `is_original_of` y `has_copy` están en el enumerado (`app/models/enums.py:96-98`), pero ningún servicio los escribe.
  - `app/models/enums.py:14` — `TIPO_COPIA = ("master_preservacion","copia_acceso")`, sin uso
  - Buscado «instanciación física», «papel», «original físico» y `soporte` en `app/models/instanciacion.py` y `app/servicios/`: el original en papel no existe como Instantiation; solo queda el texto `soporte` en el Record Resource (`app/models/recurso_documental.py:73`)
  - `app/servicios/descripcion.py:724-727` — una instanciación solo puede pertenecer a un Record Resource (en RiC-O `isOrWasInstantiationOf` no es funcional)
  - API: `app/routers/ingesta.py:90` (cargar), `:176` (cola); `app/routers/preservacion.py`; exportación en `app/servicios/exportacion_rico.py:453-465`
- Prueba automatizada: `tests/test_ingesta.py::test_carga_unica_llega_a_listo_para_descripcion`, `tests/test_preservacion.py::test_migracion_soportada_crea_nueva_instanciacion_sin_tocar_la_original`, `tests/test_grafo_contexto.py::test_la_version_de_conservacion_cuelga_de_su_original_y_no_parece_un_duplicado`
- Razonamiento: La Instantiation digital está modelada en profundidad (PREMIS, huella, formato y migración con `migrated_into`). Como entidad RiC-CM queda corta en tres puntos. Primero, el soporte original (papel) no es una Instantiation, así que no se puede decir que el PDF es copia de un original físico, aunque los códigos existen en el enumerado. Segundo, el recorte es una instanciación derivada sin relación RiC. Tercero, la cardinalidad «una instanciación, un solo recurso» y el uso de instanciaciones para documentos distintos (CM-03) distorsionan la entidad.
- Acción recomendada: Escribir `has_or_had_derived_instantiation` para los recortes. Modelar el original físico como Instantiation (con su tipo de soporte) cuando se conozca, y unirlo con `has_copy`/`is_original_of` a la digitalización. Quitar `TIPO_COPIA` o usarlo.

### CM-05 · Agent (supertipo) y su enumerado de subtipos: declarado en Python, sin restricción en la base de datos, y duplicado
- Rama: RiC-CM
- Módulo(s): vocabularios, descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/descripcion.py:30` — `CLASE_VOCABULARIO` (enumerado de PostgreSQL `clase_vocabulario`), donde `agente` es una de siete clases de la tabla única `entidades_vocabulario` (`:75-126`)
  - `app/models/descripcion.py:34` — `SUBTIPO_AGENTE = ("persona","entidad_corporativa","grupo","cargo","familia","mecanismo")`. Los seis subtipos RiC-CM están al mismo nivel del mismo enumerado, y cargo y mecanismo están declarados explícitamente.
  - `app/models/descripcion.py:86` y `alembic/versions/0003_descripcion.py:30` — la columna `subtipo` es `String(40)` libre, sin `Enum` ni `CHECK` (grep `CheckConstraint|CHECK` en `app/models` y `alembic/versions`: solo en `evaluacion` y `hallazgo`)
  - `app/servicios/descripcion.py:368-369` y `app/servicios/motor.py:337` — un subtipo desconocido se convierte en «persona» sin preguntar. `app/servicios/vocabulario.py:101-104` — `crear()` no valida el subtipo.
  - `app/models/enums.py:35` — un segundo `TIPO_AGENTE`, en otro orden y sin uso
  - `app/servicios/ric_o.py:70-77` (`CLASE_AGENTE`) y `:111-122` (`SUPERCLASES`: `CorporateBody` y `Family` bajo `Group`). Un subtipo fuera de la lista cae en `Agent` (`:99`).
  - API: `app/routers/vocabulario.py:125` (listar con filtro por clase), `:204` (detalle), `:242` (enriquecer)
- Prueba automatizada: `tests/test_ric_o.py::test_grupo_se_instancia_directamente`, `tests/test_autoridad.py::test_agente_grupo_se_guarda_lista_y_filtra`
- Razonamiento: El agente es un registro controlado y reutilizable, con detección de similitud y fusión. Pasa la prueba de profundidad: «Alcaldía Municipal» y «Alcaldía Mpal.» terminan en el mismo registro. La jerarquía de subtipos está declarada explícitamente, incluidos cargo y mecanismo. La debilidad está en que esa declaración es una tupla de Python, no una restricción de la base de datos (a diferencia de `subtipo_fecha`). Además, la jerarquía Group → CorporateBody/Family solo existe en el diccionario de exportación, y hay un segundo enumerado muerto que puede divergir.
- Acción recomendada: Convertir `entidades_vocabulario.subtipo` en `Enum` o añadir un `CHECK (clase <> 'agente' OR subtipo IN (…))`. Eliminar `enums.TIPO_AGENTE`. Rechazar un subtipo desconocido en lugar de forzarlo a «persona».

### CM-06 · Persona
- Rama: RiC-CM
- Módulo(s): vocabularios, descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/descripcion.py:34` — subtipo `persona`; `app/servicios/ric_o.py:71` → `Person`
  - Ficha ISAAR común a todos los agentes: `app/models/descripcion.py:99-114` (existencia EDTF, historia, reglas, fuentes); otras formas del nombre e identificadores en `:274-310`
  - Relaciones propias de una persona: `occupies_or_occupied` (R054, Person→Position) está en `app/models/enums.py:89` y `app/servicios/ric_o.py:179`, pero ningún servicio la escribe (grep `"occupies_or_occupied"`: solo `ric_o.py` y una etiqueta en `app/servicios/instrumentos.py:571`). `has_or_had_member` (`enums.py:91`) no tiene mapeo ni ruta de escritura.
  - API: `app/routers/vocabulario.py:322` (vínculos) y `:367` (relaciones entre agentes: solo `subordinado`, `sucesor` y `asociado`)
- Prueba automatizada: `tests/test_vocabularios.py` (helper `entidad(..., subtipo="persona")`, línea 64), `tests/test_grafo_contexto.py::test_carga_con_un_fondo_de_mas_de_quinientas_entidades`. Ninguna prueba relaciona una persona con un cargo o con un grupo.
- Razonamiento: La persona existe como subtipo controlado con ficha de autoridad. Pero las dos relaciones que distinguen a una persona en RiC-CM no se pueden declarar: ocupar un cargo (R054) y ser miembro de un grupo (R055). Solo quedan las genéricas entre agentes.
- Acción recomendada: Agregar a `VINCULOS` (`app/servicios/autoridad.py:326`) `occupies_or_occupied` (persona → cargo, con vigencia EDTF) y `has_or_had_member` / `isOrWasMemberOf` (grupo ↔ persona), validando el subtipo y no solo la clase.

### CM-07 · Grupo (Group usado directamente)
- Rama: RiC-CM
- Módulo(s): vocabularios, descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/descripcion.py:31-34` — subtipo `grupo`, con comentario sobre la nota de alcance de `rico:Group`; `app/servicios/ric_o.py:74`
  - `has_or_had_member` (`app/models/enums.py:91`) y `has_or_had_subdivision` (`:88`) no se escriben ni se mapean (grep: solo `enums.py`)
- Prueba automatizada: `tests/test_autoridad.py::test_agente_grupo_se_guarda_lista_y_filtra`, `tests/test_descripcion_v3.py::test_agente_grupo_se_crea_desde_la_descripcion`, `tests/test_ric_o.py::test_grupo_se_instancia_directamente`
- Razonamiento: El grupo se crea, se filtra y se exporta con su clase correcta, y las pruebas lo confirman. Pero un grupo sin miembros ni subdivisiones es solo una etiqueta con subtipo: no hay modo de decir quién compone una junta o un comité.
- Acción recomendada: Implementar la pertenencia (R055) y la subdivisión (R005) como vínculos declarables.

### CM-08 · Entidad corporativa
- Rama: RiC-CM (con ISAAR-CPF)
- Módulo(s): vocabularios, descripcion
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/models/descripcion.py:34` (subtipo), `:36` (`ESTATUTO_JURIDICO`), `:106-108` (estatuto, estructura, contexto)
  - `app/servicios/autoridad.py:121-125` — el estatuto se valida contra la lista
  - `app/servicios/autoridad.py:328-333` — subordinación (R045, jerárquica y sin ciclos), sucesión (R016) y asociación (R044, simétrica), una fila por relación con la inversa leída de ella
  - `app/servicios/autoridad.py:354-362` — mandato que crea al agente (`authorizes`, rol «creacion») y entidad que expide (`issued_by`)
  - API: `app/routers/vocabulario.py:242`, `:322`, `:367`
- Prueba automatizada: `tests/test_autoridad.py::test_ficha_de_agente_guarda_sus_cuatro_areas_con_existencia_abierta`, `tests/test_autoridad.py::test_relacion_entre_agentes_es_una_fila_con_su_inversa_fecha_y_nota`, `tests/test_autoridad.py::test_mandato_que_crea_un_agente_y_entidad_que_lo_expidio`
- Razonamiento: Es el subtipo más completo. Tiene registro controlado, estatuto jurídico en lista cerrada, relaciones jerárquicas, de sucesión y asociativas con dirección y vigencia, y origen normativo. Pasa la prueba de profundidad. La estructura interna en texto (`estructura`) se reconoce como dato sin propiedad (`app/servicios/ric_o.py:248`).

### CM-09 · Familia
- Rama: RiC-CM
- Módulo(s): vocabularios, descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/descripcion.py:34` (subtipo `familia`); `app/servicios/ric_o.py:72` → `Family`
  - Buscado `"familia"` y `subtipo="familia"` en `tests/`: ninguna prueba crea ni ejercita una familia (los resultados de `familia` en `tests/test_grafo_contexto.py` se refieren a la clave «familia» de la clase del nodo)
  - Sin relaciones de parentesco ni de pertenencia (ver CM-07)
- Prueba automatizada: ninguna encontrada
- Razonamiento: La familia existe solo como valor del enumerado y como clase de exportación. No tiene prueba ni relaciones propias (miembros), así que no se distingue en la práctica de un grupo con otro nombre.
- Acción recomendada: Agregar una prueba que cree una familia desde la descripción y la exporte como `rico:Family`, y la pertenencia de personas (R055).

### CM-10 · Cargo (Position): solo admite jerarquía entre cargos, nunca se une a quien lo ocupa ni al grupo donde existe
- Rama: RiC-CM
- Módulo(s): vocabularios, descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/descripcion.py:34` (subtipo `cargo`); `app/models/enums.py:22-35` (comentario: el cargo «independiente de quién lo ocupe»); `app/servicios/ric_o.py:75` → `Position`
  - `app/models/enums.py:89-90` — `occupies_or_occupied` (R054) y `exists_or_existed_in` (R056) declarados. `app/servicios/ric_o.py:179` mapea R054. **R056 no tiene mapeo** (no está en `PROPIEDADES`). Ninguno de los dos está en `VINCULOS` (`app/servicios/autoridad.py:326-366`) ni en `RelacionAgentesIn` (`app/routers/vocabulario.py`, `Literal["subordinado","sucesor","asociado"]`).
  - OWL: `occupiesOrOccupied` tiene dominio `Person` y rango `Position`; `existsOrExistedIn` tiene dominio `Position` y rango `Group`; `hasOrHadPosition` tiene dominio `Group` y rango `Position`. Están en la ontología y el sistema no los usa.
  - `app/servicios/autoridad.py:375-382` — `_admite()` compara por `clase` («agente»), no por subtipo
- Prueba automatizada: `tests/test_autoridad.py::test_jerarquia_entre_cargos_usa_la_misma_relacion`; `tests/test_descripcion.py` y `tests/test_descripcion_contexto.py` (agente `subtipo: "cargo"` como destinatario)
- Razonamiento: El cargo está declarado explícitamente en el mismo enumerado que persona y grupo, y se puede subordinar a otro cargo. Pero falta justo lo que lo justifica en RiC-CM. Prueba de profundidad: «Secretario de Gobierno» (cargo) y «Juan Pérez» (persona que lo ocupó de 1948 a 1950) quedan como dos registros sin ninguna relación entre ellos, y el cargo tampoco se puede situar dentro de la Alcaldía. En la práctica es una etiqueta con subtipo.
- Acción recomendada: Implementar R054 (persona → cargo, con vigencia) y R056 / `hasOrHadPosition` (cargo ↔ grupo), validados por subtipo, con prueba.

### CM-11 · Mecanismo (Mechanism): registro propio y reutilizable con versión (profundo), pero excluido de la exportación y unido a las acciones técnicas solo por clave foránea
- Rama: RiC-CM
- Módulo(s): vocabularios, preservacion, ingesta, descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/descripcion.py:34` (subtipo `mecanismo`), `:99` (`version`), `:62-70` (`motor_id` en toda entidad y relación propuesta por el motor)
  - `app/servicios/vocabulario.py:375-396` — `mecanismo()`: un registro por programa y versión, reutilizado; `app/servicios/mecanismos.py:1-60`
  - `app/servicios/autoridad.py:139-142` — un mecanismo sin versión se rechaza al enriquecerlo
  - `app/models/preservacion.py:61,80,100,115` y `app/models/instanciacion.py:64` — `mecanismo_id` como clave foránea en verificación, migración, segunda copia, restauración e identificación de formato. No hay fila `performs_or_performed` (Mechanism → Activity).
  - `app/servicios/exportacion_rico.py:214` — `_cargar()` descarta toda entidad con `subtipo == "mecanismo"`. `tests/test_exportacion_rico.py:169` exige que «Motor de análisis» no salga. `rico:technicalCharacteristics` (`app/servicios/ric_o.py:220`) no lo escribe ningún exportador (grep `version_mecanismo|technicalCharacteristics`: solo `ric_o.py`). Eso contradice `documentacion/anexos/verificacion-ric-o-1-1.md:25`, que afirma que la versión «se exporta con `rico:technicalCharacteristics`».
- Prueba automatizada: `tests/test_autoridad.py::test_mecanismo_guarda_su_version_y_se_reutiliza`, `tests/test_autoridad.py::test_mecanismo_sin_version_queda_marcado`, `tests/test_mecanismos.py::test_migracion_automatica_queda_vinculada_a_ghostscript_con_su_version_exacta`, `tests/test_mecanismos.py::test_identificacion_verificacion_y_segunda_copia_apuntan_a_su_mecanismo`
- Razonamiento: Por la prueba de profundidad, el mecanismo es profundo: «Ghostscript 10.02» se resuelve siempre al mismo registro con su versión declarada una sola vez, y cada acción técnica apunta a él. Pero como entidad RiC-CM se queda a medias. Lo que hace no se modela como Activity ejercida por un Agent (son claves foráneas en tablas PREMIS), y el agente desaparece por completo de la salida RDF. Además, la documentación del equipo afirma una exportación que el código no hace.
- Acción recomendada: Decidir y documentar una política. O se exporta el mecanismo (con `technicalCharacteristics`), quizá sin los datos internos del motor, o se corrige el anexo de verificación. Modelar al menos la migración como Activity ejercida por el mecanismo (ver CM-22).

### CM-12 · Lugar (Place): nombres históricos, coordenadas, tipo y jerarquía presentes; jerarquía de un solo superior sin tiempo y lugar del documento siempre como «tema»
- Rama: RiC-CM
- Módulo(s): vocabularios, descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/descripcion.py:30` (clase `lugar`), `:116-118` (latitud, longitud y `tipo_lugar` como `String(30)`), `:38-39` (`TIPO_LUGAR`, 9 valores), `:274-293` (`NombreEntidad` con `tipo="historica"` y vigencia EDTF = PlaceName)
  - `app/models/enums.py:56` — **otro** `TIPO_LUGAR` de 4 valores (`pais`, `departamento`, `municipio`, `direccion`) que no coincide con el anterior y no se usa
  - `app/servicios/autoridad.py:128-130` — validación de `tipo_lugar` en el servicio (no en la base de datos); `:131-134` — latitud y longitud con rango
  - `app/servicios/autoridad.py:338-339` — `lugar_superior` = `contains_or_contained` (R007) con `unico_superior=True`; `:392-398` — `_superiores()` ignora `fecha_edtf`, así que un segundo superior se rechaza aunque los periodos no se solapen. En el OWL, `isOrWasContainedBy` no es funcional.
  - `app/servicios/autoridad.py:335-336` — `lugar_agente` = `is_or_was_location_of` (R075) solo hacia agentes
  - `app/servicios/descripcion.py:75` — en un documento, el lugar siempre es `has_or_had_subject` (tema), nunca lugar de expedición o de creación
  - API: `app/routers/vocabulario.py:242` (coordenadas y tipo), `:260` (nombres), `:322` (vínculos)
- Prueba automatizada: `tests/test_autoridad.py::test_lugar_con_coordenadas_tipo_superior_y_nombres_historicos` (que verifica además que un segundo superior da 422)
- Razonamiento: El lugar es un registro controlado con PlaceName histórico y coordenadas: pasa la prueba de profundidad, porque «Tunja» y «Hunza» resuelven al mismo Place. Hay dos brechas. Primera: la jerarquía admite un solo superior y no considera la vigencia, así que no se puede representar un municipio que perteneció a una provincia hasta 1886 y luego a un departamento, aunque la columna `fecha_edtf` existe para eso. Segunda: «Tunja, 2 de abril de 1948» (lugar de expedición) y «trata sobre Tunja» (tema) terminan en la misma relación de tema. El tipo de lugar es una lista fija en código, no un vocabulario administrable, y está duplicada con valores distintos.
- Acción recomendada: Permitir varios superiores con vigencia (y comprobar el solapamiento, no la unicidad). Agregar un rol de lugar de expedición o creación con `isOrWasLocationOf` hacia el Record. Unificar `TIPO_LUGAR` y moverlo a un `Enum` o `CHECK`.

### CM-13 · Event (no Activity): tabla «hitos» atada a un solo agente
- Rama: RiC-CM
- Módulo(s): vocabularios
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/descripcion.py:313-334` — `Hito` («rico:Event usado directamente»), con `agente_id` como **una** clave foránea obligatoria (`:323`), `tipo` como enumerado cerrado `TIPO_HITO` (`:46`, `:324`) y la fecha como cadena EDTF (`:326`), no como nodo `Fecha`
  - `app/servicios/autoridad.py:245-269` — `agregar_hito()`; `app/routers/vocabulario.py:292` — `POST /{entidad_id}/hitos`
  - `app/servicios/ric_o.py:182-187` — `affects_or_affected` con destino `AGENTES + RECURSOS`, pero el modelo solo admite un agente. La relación no se guarda en `relaciones`: la reconstruye la exportación (`app/servicios/exportacion_rico.py:428-433`).
  - Buscado `hito|Hito|Event` en `app/servicios/grafo.py`: sin resultado (los hitos no aparecen en el grafo navegable)
- Prueba automatizada: `tests/test_autoridad.py::test_hitos_se_guardan_con_su_fecha_y_se_listan_cronologicamente`, `tests/test_autoridad.py::test_anular_una_forma_del_nombre_o_un_hito_no_los_borra`
- Razonamiento: Existe un modelo propio para Event distinto de Activity, como pide el anexo. Pero su cardinalidad es más estrecha que la de RiC-CM. Una fusión de dos entidades o el traslado de un fondo (que afecta a un Record Set, no a un agente) obligan a duplicar el hito o no se pueden registrar. Tampoco admite lugar ni participantes. El tipo de evento es una lista fija en el código, no un vocabulario.
- Acción recomendada: Unir el hito por filas `affects_or_affected` en `relaciones` (muchos agentes y recursos), admitir lugar (`hasOrHadLocation`) y fecha como nodo `Fecha`, y mostrarlo en el grafo.

### CM-14 · Activity: registro del vocabulario con su cadena tipo–agente–mandato–subactividad; sin vínculo con Event ni con las acciones técnicas
- Rama: RiC-CM
- Módulo(s): descripcion, vocabularios
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/descripcion.py:30` — clase `actividad` en `entidades_vocabulario`; `app/servicios/ric_o.py:82` → `Activity` (subclase de `Event` en `SUPERCLASES`, `:118`)
  - `app/servicios/descripcion.py:419-465` — `documents` (R033, documento → actividad), `has_activity_type`, `performs_or_performed` (agente → actividad), `regulates_or_regulated` (mandato → actividad) y periodo como `Fecha` con `is_date_associated_with`
  - `app/servicios/descripcion.py:471-490` y `app/servicios/autoridad.py:341-342` — `has_direct_subevent`, con un único superior y sin ciclos
  - `app/models/descripcion.py:152-162` — la tabla antigua `actividades`, «sin uso», se sigue leyendo en `app/servicios/grafo.py:162` y `app/servicios/descripcion.py:841`
  - Doble lugar para la fecha de una actividad: `existencia_edtf` (exportada en `app/servicios/exportacion_rico.py:386`) y la fila `Fecha` → `is_date_associated_with`
  - API: `app/routers/descripcion.py:207`; `app/routers/vocabulario.py:322` (`ejercida_por`, `mandato_actividad`, `actividad_mayor`)
- Prueba automatizada: `tests/test_descripcion_contexto.py::test_la_actividad_queda_conectada_a_su_tipo_agente_y_mandato_y_se_ve_en_el_catalogo`, `tests/test_descripcion_v3.py::test_actividad_publicada_como_sub_actividad_de_otra_existente`, `tests/test_autoridad.py::test_sub_actividades_se_listan_y_no_se_confunden_con_skos`
- Razonamiento: Es una implementación profunda en el sentido de la sección 5 del prompt: la actividad es un registro reutilizable, unido al documento, a su tipo, a su agente y a su mandato, cada uno por su relación con dirección. Hay tres reservas. Primera: como la actividad se deduplica por similitud de nombre, dos ejercicios concretos y distintos de la misma competencia («expedición de licencia» en 1948 y en 1952) pueden fusionarse, y ese es el error que `ActivityType` debía evitar. Segunda: la fecha puede vivir en dos sitios. Tercera: ni las acciones técnicas (CM-22) ni los hitos (CM-13) se integran con Activity.
- Acción recomendada: Advertir en la verificación de similitud de actividades que se trata de ejercicios concretos, no de competencias. Usar una sola fuente para el periodo de la actividad. Retirar las lecturas de la tabla `actividades` cuando no queden filas.

### CM-15 · ActivityType (tipo de actividad / función) como vocabulario controlado con jerarquía SKOS
- Rama: RiC-CM (con SKOS)
- Módulo(s): vocabularios, descripcion
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/models/descripcion.py:24-30` — clase `tipo_actividad`, con comentario explícito de que «Función» no es entidad; `:119-121` — `concepto_superior_id` (`skos:broader`), sin fila en `relaciones`
  - `app/servicios/autoridad.py:527-546` — `fijar_concepto_superior()` con control de ciclos y solo entre tipos de actividad
  - `app/servicios/descripcion.py:374-376` — un tipo de actividad suelto (sin actividad que lo lleve) no se publica
  - `app/servicios/descripcion.py:434-435` — `has_activity_type` (Activity → ActivityType)
  - `app/servicios/autoridad.py:363-365` — `serie_producida` (función ↔ serie/subserie, R001, marcada como «general»)
  - Exportación: `app/servicios/exportacion_rico.py:369-379` (`skos:Concept`, `inScheme`, `broader`, `hasTopConcept`)
  - API: `app/routers/vocabulario.py:185` (`/funciones/arbol`), `:352` (`/concepto-superior`), `:191` (series)
  - Sin uso: `app/models/enums.py:43` `TIPO_FUNCION = ("sustantiva","de_apoyo")`
- Prueba automatizada: `tests/test_autoridad.py::test_arbol_de_funciones_se_arma_con_skos_y_no_admite_ciclos`, `tests/test_autoridad.py::test_tipo_de_actividad_con_su_serie_documental`, `tests/test_descripcion_contexto.py::test_tipo_de_actividad_suelto_no_se_publica`, `tests/test_autoridad.py::test_mandato_que_crea_una_competencia`
- Razonamiento: Cumple exactamente el criterio profundo del prompt. Es un valor controlado y reutilizable con verificación de similitud y fusión, asignado a la actividad mediante `hasActivityType`, con jerarquía función → subfunción → trámite en SKOS y no como relación RiC (la prueba lo verifica), y con su vínculo a la serie de la TRD. Prueba de profundidad: «Policía local» y «Policía Local» se resuelven al mismo concepto. La monojerarquía (un solo `broader`) es una decisión válida en SKOS. Solo sobra `TIPO_FUNCION`, que está muerto.

### CM-16 · Date: entidad propia con subtipo y EDTF, pero dispersa en cadenas para agentes, hitos, relaciones y conjuntos
- Rama: RiC-CM (con EDTF)
- Módulo(s): descripcion, vocabularios
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/descripcion.py:129-149` — tabla `fechas` con `expresion` (A19), `edtf` (A29), `subtipo` como `Enum` de PostgreSQL `subtipo_fecha` (`:52`, `:139`; migración `alembic/versions/0009_descripcion_contexto.py:32-34`), límites y calendario
  - `app/servicios/fechas.py:1-40` — subconjunto EDTF acotado y validado
  - Códigos de fecha escritos: solo `is_creation_date_of` (`app/servicios/descripcion.py:356-357`, `:406`) e `is_date_associated_with` (`:463`). `is_beginning_date_of`, `is_end_date_of` e `is_modification_date_of` (`app/models/enums.py:106-108`) no se escriben nunca.
  - Fechas fuera de la entidad Date, como cadenas: `recursos_documentales.fechas_extremas` (`app/models/recurso_documental.py:30`), `entidades_vocabulario.existencia_edtf` (`app/models/descripcion.py:102`), `hitos.edtf` (`:326`), `relaciones.fecha_edtf` (`:198`) y `nombres_entidad.vigencia_edtf` (`:287`)
  - Sin uso: `app/models/enums.py:49` `TIPO_FECHA` y `:53` `PRECISION_FECHA`
- Prueba automatizada: `tests/test_descripcion_contexto.py::test_fecha_se_interpreta_y_normaliza`, `tests/test_descripcion_contexto.py::test_fechas_aproximada_rango_y_conjunto_quedan_en_edtf`, `tests/test_descripcion_v3.py::test_la_fecha_declara_su_calendario`
- Razonamiento: La fecha del documento es una entidad RiC propia con sus tres subtipos declarados en la base de datos. Es la entidad mejor restringida de todo el modelo. Pero RiC-CM trata Date como entidad para cualquier cosa fechada, y aquí las fechas de existencia, de los hitos, de la vigencia de relaciones y nombres, y las fechas extremas de los conjuntos son cadenas sueltas. Las cuatro primeras se validan como EDTF en el servicio; las fechas extremas no. Solo se usan dos de los cinco roles temporales del catálogo.
- Acción recomendada: Validar `fechas_extremas` como EDTF (o convertirla en nodo `Fecha`). Documentar qué fechas son atributos y cuáles entidades. Eliminar `TIPO_FECHA` y `PRECISION_FECHA`, o implementar fechas de inicio, fin y modificación.

### CM-17 · Mandate
- Rama: RiC-CM
- Módulo(s): vocabularios, descripcion
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/models/descripcion.py:30` (clase `mandato`), `:49` (`SUBTIPO_MANDATO`: ley, decreto, ordenanza, acuerdo, resolución u otro, en `subtipo` String validado en `app/servicios/descripcion.py:62,370-371`)
  - `app/servicios/descripcion.py:403-417` — fecha de expedición como nodo `Fecha` (`is_creation_date_of`); un mandato citado sin actividad queda como tema
  - `app/servicios/descripcion.py:439-444` — `regulates_or_regulated` (mandato → actividad) y `authorizes` (mandato → agente que ejerce)
  - `app/servicios/autoridad.py:347-362` — jerarquía normativa (R063, rol `jerarquia_normativa`, sin ciclos), creación de agente (`authorizes`, rol `creacion`), creación de competencia (R063 → tipo de actividad) y expedido por (R065)
  - OWL: `authorizes` tiene dominio `Mandate` y rango `Agent`; `regulatesOrRegulated` tiene dominio `Rule` y rango `Thing`. Las direcciones del código coinciden.
  - Exportación: `app/servicios/exportacion_rico.py:398-400` (`hasOrHadMandateType`)
  - Sin uso: `app/models/enums.py:46` `TIPO_NORMA = ("externa","interna")`; `is_or_was_expressed_by` (R064) declarado en `enums.py:102` y no escrito
- Prueba automatizada: `tests/test_autoridad.py::test_mandato_derivado_se_navega_en_ambos_sentidos_sin_ciclos`, `tests/test_autoridad.py::test_mandato_que_crea_un_agente_y_entidad_que_lo_expidio`, `tests/test_autoridad.py::test_mandato_que_crea_una_competencia`, `tests/test_descripcion_contexto.py::test_la_actividad_queda_conectada_a_su_tipo_agente_y_mandato_y_se_ve_en_el_catalogo`
- Razonamiento: El mandato es un registro controlado con tipo, fecha como entidad, y relaciones con dirección hacia la actividad, el agente, la competencia y la norma superior, todas probadas. Pasa la prueba de profundidad: «Acuerdo 12 de 1946» se reutiliza. Hay un detalle: el anexo (sección 3) describe la relación como «Actividad `authorizedBy` Mandato», pero en RiC-O 1.1 `authorizedBy` va de Agent a Mandate. El código usa correctamente `regulatesOrRegulated` para la actividad y `authorizes` para el agente.

### CM-18 · Rule (distinta de Mandate): no existe
- Rama: RiC-CM
- Módulo(s): vocabularios, descripcion, instrumentos
- Clasificación: No implementado
- Evidencia:
  - Buscado `Rule`, `rico:Rule`, `regla`, `retenci`, `disposicion_final` y `TRD` en `app/models`, `app/servicios`, `app/routers`, `alembic/versions` y `tests`. Solo aparecen `app/servicios/ric_o.py:123-124` (superclase en `SUPERCLASES`), el comentario de `app/models/enums.py:101` («una Rule regula un Record Resource (p. ej. retención)»), el comentario TRD de `app/servicios/autoridad.py:363` y el campo de control `reglas` del registro de autoridad (`app/models/descripcion.py:111`, que son las convenciones de descripción, no una Rule RiC)
  - `CLASE_VOCABULARIO` (`app/models/descripcion.py:30`) no tiene una clase `regla`
- Prueba automatizada: ninguna encontrada
- Razonamiento: RiC-CM (RiC-E16 Rule) cubre también reglas no normativas, como los plazos de retención y la disposición final de la TRD, o las reglas internas de un procedimiento. El sistema solo instancia su subclase Mandate. El enumerado promete el caso de la retención y nada lo implementa.
- Acción recomendada: Agregar la clase `regla` (Rule) al vocabulario, o documentar explícitamente que el alcance se limita a Mandate. Si se implementa, unir la regla de retención con la serie mediante `regulates_or_regulated`.

### CM-19 · Transversal: la tabla polimórfica de relaciones no restringe dominio ni rango al escribir
- Rama: RiC-CM
- Módulo(s): descripcion, vocabularios, preservacion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/descripcion.py:170-202` — `Relacion` con `origen_tipo`/`destino_tipo` como `String(40)` e identificadores sin clave foránea; `TIPOS_NODO` (`:167`) declarado y sin uso
  - `app/servicios/ric_o.py:342-345` — `uso_valido()` solo se invoca al exportar (`app/servicios/exportacion_rico.py:249`), y lo que no cumple se **omite en silencio**, con un contador
  - `app/servicios/autoridad.py:375-382` — la validación de vínculos usa la clase del vocabulario, no el subtipo (un «mecanismo» puede ser subordinado de una «persona», o un cargo sucesor de una familia)
  - Categoría amplia incoherente para el mismo código: `performs_or_performed` es `"asociacion"` en `app/servicios/descripcion.py:438` y `"procedencia"` en `app/servicios/autoridad.py:344`
- Prueba automatizada: `tests/test_ric_o.py::test_parte_documental_es_record_part_y_se_une_por_constituyente` (usa `uso_valido` de forma unitaria), `tests/test_exportacion_rico.py::test_la_exportacion_es_conforme_al_owl_y_al_perfil_shacl`. Ninguna prueba intenta escribir una relación con un dominio inválido por la API.
- Razonamiento: La dirección de cada relación está bien fijada en el código que la escribe. Pero la integridad semántica (que el origen sea de la clase que exige el código RiC) no la garantiza ni la base de datos ni el servicio común de escritura. Un error en una ruta futura crearía filas que el grafo interno muestra y la exportación descarta sin aviso al usuario.
- Acción recomendada: Llamar a `ric_o.uso_valido()` desde `_relacionar()` y `autoridad.vincular()` (resolviendo la clase con el subtipo) y rechazar la escritura. Fijar una sola categoría por código.

### CM-20 · Transversal: catálogo de relaciones y enumerados declarados que no se implementan
- Rama: RiC-CM
- Módulo(s): descripcion, vocabularios
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/enums.py:72-134` — 47 códigos en el `Enum` de PostgreSQL `codigo_relacion_ric`. 20 de ellos no tienen mapeo en `app/servicios/ric_o.py` (`PROPIEDADES`) ni ruta de escritura: `has_author`, `has_accumulator`, `has_receiver`, `has_collector`, `is_or_was_holder_of`, `is_or_was_manager_of`, `is_or_was_owner_of`, `is_or_was_controller_of`, `has_or_had_subdivision`, `exists_or_existed_in`, `has_or_had_member`, `is_or_was_leader_of`, `is_original_of`, `has_copy`, `has_or_had_derived_instantiation`, `is_or_was_expressed_by`, `is_beginning_date_of`, `is_end_date_of`, `is_modification_date_of` e `is_or_was_jurisdiction_of` (comprobado con Python contra `CODIGO_RELACION_RIC` y `PROPIEDADES`). `occupies_or_occupied` está mapeado pero no se escribe.
  - Enumerados muertos o divergentes en `app/models/enums.py`: `NIVEL_DOCUMENTO` (`:8`), `SOPORTE_DOCUMENTO` (`:11`), `TIPO_COPIA` (`:14`), `CONDICION_ACCESO` (`:20`), `TIPO_AGENTE` (`:35`), `ROL_AGENTE_EN_DOCUMENTO` (`:40`, con «firmante», cuando el servicio usa productor, remitente, destinatario, mencionado y custodio en `app/servicios/descripcion.py:364`), `TIPO_FUNCION` (`:43`), `TIPO_NORMA` (`:46`), `TIPO_FECHA` (`:49`), `PRECISION_FECHA` (`:53`) y `TIPO_LUGAR` (`:56`). Grep en `app/`, `alembic/` y `tests/`: sin usos fuera del propio archivo.
- Prueba automatizada: `tests/test_ric_o.py::test_cada_codigo_mapeado_existe_en_el_catalogo_del_sistema` (comprueba solo la dirección mapeo → catálogo, no catálogo → implementación)
- Razonamiento: El catálogo de relaciones da la impresión de que el sistema cubre 47 relaciones RiC-CM, cuando solo escribe unas 25. Este es el patrón de «nombres prestados» que la auditoría debe señalar: los códigos están en la base de datos, y ninguna pantalla, servicio o prueba los produce.
- Acción recomendada: Marcar en `enums.py` cuáles códigos están implementados (o retirar los demás del `Enum`) y añadir una prueba que falle si un código del catálogo no tiene mapeo ni ruta de escritura.

### CM-21 · Transversal: cardinalidades más estrictas que RiC-O
- Rama: RiC-CM
- Módulo(s): descripcion, vocabularios
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - OWL RiC-O 1.1: cero `owl:FunctionalProperty` (comprobado con rdflib)
  - Un solo superior documental: `app/models/recurso_documental.py:33` y `app/servicios/descripcion.py:702-708` (CM-02)
  - Una instanciación pertenece a un solo recurso: `app/servicios/descripcion.py:724-727` (CM-04)
  - Un lugar tiene un solo superior, sin considerar la vigencia: `app/servicios/autoridad.py:338` y `:443-444` (CM-12)
  - Una actividad tiene una sola actividad mayor: `app/servicios/autoridad.py:341` y `app/servicios/descripcion.py:480-483`
  - Un hito afecta a un solo agente: `app/models/descripcion.py:323` (CM-13)
  - Una sola forma documental por documento: `app/servicios/descripcion.py:327-329`
- Prueba automatizada: `tests/test_autoridad.py::test_lugar_con_coordenadas_tipo_superior_y_nombres_historicos` (fija la restricción como correcta)
- Razonamiento: Algunas restricciones son decisiones razonables de un archivo público, como una forma documental por documento o un superior orgánico. Pero RiC-O no las impone, y en varios casos (lugar con vigencia, hito sobre varios agentes, documento en dos conjuntos) impiden representar situaciones que RiC-CM sí admite. Ninguna está documentada como restricción deliberada frente al estándar.
- Acción recomendada: Documentar cada restricción como perfil de aplicación y relajar las que tienen vigencia temporal (lugar) o múltiples afectados (hito).

### CM-22 · Transversal: las acciones técnicas no se modelan como Activity ejercida por un Mechanism
- Rama: RiC-CM (con PREMIS)
- Módulo(s): preservacion, ingesta
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/preservacion.py:45-61` (`VerificacionIntegridad`), `:64-80` (`Migracion`), `:83-100` (`SegundaCopia`) y `:103-115` (`Restauracion`): tablas PREMIS con `mecanismo_id` como clave foránea
  - `app/servicios/preservacion.py:522-524` — la migración solo deja `migrated_into` entre instanciaciones. No hay nodo Activity ni `performs_or_performed` del mecanismo (grep `performs_or_performed` en `app/servicios/preservacion.py`: sin resultado)
- Prueba automatizada: `tests/test_mecanismos.py::test_migracion_automatica_queda_vinculada_a_ghostscript_con_su_version_exacta` (verifica la clave foránea, no una Activity)
- Razonamiento: El anexo introduce el Mechanism justamente para que el actor automático de una acción técnica sea un agente RiC. El sistema registra la acción en PREMIS (lo cual es correcto para la preservación) y apunta al mecanismo, pero en el grafo RiC esa acción no existe como Activity, y el mecanismo tampoco se exporta (CM-11). Desde RiC-CM, el agente mecanismo no ejerce nada.
- Acción recomendada: Proyectar al menos las migraciones aprobadas como `Activity` (con su tipo «migración de formato») ejercida por el mecanismo y documentada por la instanciación resultante, o declarar explícitamente que estas acciones se quedan solo en PREMIS.

---

## Tabla resumen

| ID | Título | Clasificación |
|---|---|---|
| CM-01 | Record Resource: una tabla, y el subtipo se deduce del nivel | Implementado pero incompleto o no conforme |
| CM-02 | Record Set: los niveles intermedios solo nacen de archivos; la sección no se puede crear | Implementado pero incompleto o no conforme |
| CM-03 | Record y parte documental: los documentos de un expediente nunca llegan a ser Records | Implementado pero incompleto o no conforme |
| CM-04 | Instantiation: solo digital, de un único recurso y sin relaciones de copia o derivación | Implementado pero incompleto o no conforme |
| CM-05 | Agent: enumerado de subtipos en Python, sin restricción en la base de datos, y duplicado | Implementado pero incompleto o no conforme |
| CM-06 | Persona: sin ocupación de cargo ni pertenencia a grupo | Implementado pero incompleto o no conforme |
| CM-07 | Grupo: sin miembros ni subdivisiones | Implementado pero incompleto o no conforme |
| CM-08 | Entidad corporativa | Implementado y conforme |
| CM-09 | Familia: solo valor del enumerado, sin prueba | Implementado pero incompleto o no conforme |
| CM-10 | Cargo (Position): sin R054 ni R056 | Implementado pero incompleto o no conforme |
| CM-11 | Mecanismo: profundo en el registro, ausente de la exportación | Implementado pero incompleto o no conforme |
| CM-12 | Lugar: jerarquía de un solo superior sin tiempo; el lugar del documento siempre es tema | Implementado pero incompleto o no conforme |
| CM-13 | Event (hitos) atado a un solo agente | Implementado pero incompleto o no conforme |
| CM-14 | Activity: cadena completa, pero sin vínculo con Event ni con acciones técnicas | Implementado pero incompleto o no conforme |
| CM-15 | ActivityType con jerarquía SKOS | Implementado y conforme |
| CM-16 | Date: entidad propia, pero dispersa en cadenas en otras tablas | Implementado pero incompleto o no conforme |
| CM-17 | Mandate | Implementado y conforme |
| CM-18 | Rule (distinta de Mandate) | No implementado |
| CM-19 | Relaciones polimórficas sin validación de dominio y rango al escribir | Implementado pero incompleto o no conforme |
| CM-20 | Catálogo con 20 códigos y 11 enumerados sin implementar | Implementado pero incompleto o no conforme |
| CM-21 | Cardinalidades más estrictas que RiC-O | Implementado pero incompleto o no conforme |
| CM-22 | Acciones técnicas sin Activity ejercida por el Mechanism | Implementado pero incompleto o no conforme |
