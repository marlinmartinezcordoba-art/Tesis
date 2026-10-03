# Auditoría RiC: normas complementarias de Ingesta y Descripción (frente 3)

Alcance: sección 6 del prompt de auditoría (BagIt/SIP, procedencia del lote, OAIS aplicado a la ingesta, EDTF, relaciones nuevas entre documentos, historia de custodia) y sección 2 (ISAD-G y cuadro de clasificación documental colombiano / TRD en Descripción). La vara de medir son los prompts actualizados `e7cd10ee-…Modulo_1_Ingesta_1.md` y `725ac5b6-…Modulo_2_Descripcion_Actualizado_3.md`. Solo lectura: no se modificó el repositorio (`git status` vacío al terminar).

Ejecución de verificación (solo lectura):
- `pytest tests/test_descripcion_contexto.py tests/test_descripcion_v3.py tests/test_ingesta.py`: corrió tres veces. La primera dio 75 aprobadas y 1 fallida (`test_ingesta.py::test_ocr_guarda_su_confianza_como_promedio_por_palabra`). Las otras dos dieron 76 aprobadas y 31/31 en ingesta sola. La falla es **intermitente** (ver ING-05).
- El servicio de fechas se ejecutó con 23 expresiones; los resultados están en DES-01 y DES-03.

Hallazgo general previo: **el prompt de ingesta actualizado (`e7cd10ee`) no menciona BagIt, SIP, lote, remitente, dependencia de origen ni acta de transferencia** (lo confirma un grep sobre el archivo). Esas exigencias solo aparecen en el prompt de auditoría (§6). Por eso ING-01 e ING-02 son brechas frente a la norma complementaria (BagIt/OAIS/ISAD-G 3.2.4), no incumplimientos del prompt del módulo.

---

## INGESTA

### ING-01 · SIP conforme a BagIt al confirmar un lote
- Rama: BagIt (RFC 8493) / OAIS (SIP)
- Módulo(s): ingesta, preservacion
- Clasificación: No implementado
- Evidencia:
  - Busqué en app/, alembic/versions, tests, frontend/src, Dockerfile, docker-compose y workflows los términos `bagit|bag-info|manifest-sha|bagit.txt|tagmanifest|SIP|submission`. **Ninguna aparición en la ingesta** (`app/routers/ingesta.py`, `app/servicios/procesamiento.py`, `app/servicios/almacen.py`).
  - `app/servicios/paquete.py:459-471` — `_cerrar_bolsa` escribe `manifest-sha256.txt` (461), `bagit.txt` (463), `bag-info.txt` (467) y `tagmanifest-sha256.txt` (469). Arma un **AIP** de preservación, no un SIP.
  - `app/routers/preservacion.py:241-246` — `POST /instanciacion/{id}/exportar-paquete`, que el usuario invoca **a demanda** desde preservación. No se dispara al cargar ni al confirmar nada en la ingesta.
  - `app/routers/ingesta.py:108-157` — `_cargar` guarda cada archivo por separado y crea su `Instanciacion`. No crea ningún paquete ni bolsa.
  - `.github/workflows/deploy.yml:66` — `bagit==1.8.1` se instala solo para las pruebas.
- Prueba automatizada: ninguna para un SIP. `tests/test_preservacion_oais.py::test_paquete_de_una_instanciacion_es_bagit_valido_con_premis_y_pdi` valida con `bagit.Bag(...).validate()` el AIP de exportación, no un paquete de envío.
- Razonamiento: BagIt existe en el sistema y se valida de verdad con el validador de la Library of Congress, pero solo en la salida (AIP de preservación) y a pedido. En la ingesta no existe un «lote» como unidad que se confirme (ver ING-02), así que no hay sobre qué armar un SIP. El productor nunca entrega un manifiesto con sus propias huellas, por lo que tampoco se puede verificar la integridad de la transferencia (la huella se calcula en el servidor después de recibir el archivo). Afirmar «la ingesta arma un SIP BagIt» sería falso.
- Acción recomendada: decidir si el SIP entra en el alcance. Si entra: crear la entidad `lote_ingesta`, y al confirmarlo escribir una bolsa BagIt (data/ más `manifest-sha256.txt` y `bag-info.txt` con `Source-Organization`, `External-Identifier` = acta, `Bagging-Date`). Opcionalmente, aceptar una bolsa BagIt entrante y validarla con `bagit.Bag.validate()` antes de crear las instanciaciones, con prueba. Si no entra: declararlo como delimitación en la tesis.

### ING-02 · Metadatos de procedencia del lote (remitente, dependencia de origen, acta de transferencia)
- Rama: OAIS (Producer/SIP), ISAD-G 3.2.4 (Forma de ingreso), Ley 594/AGN (transferencias documentales)
- Módulo(s): ingesta
- Clasificación: No implementado
- Evidencia:
  - Busqué `lote_|remitente|acta_transferencia|acta de transferencia|dependencia_origen|dependencia de origen|transferencia|forma_ingreso|adquisici|acquisition` en models, alembic/versions, servicios, routers, schemas, tests y frontend. **No hay tabla, columna ni campo de formulario.**
  - `app/routers/ingesta.py:97-99` — el formulario de carga lee solo `fondo_id`, `expediente_id` y `archivos`.
  - `app/models/instanciacion.py:29-92` — la tabla `instanciaciones` no tiene `lote_id`, remitente, dependencia ni acta. Solo guarda `cargado_por_id` (90) y `cargado_en` (91), que registran quién operó el sistema, no quién transfirió.
  - Las apariciones de «remitente» (`app/servicios/descripcion.py:70`, `app/servicios/motor.py:27`) son el **rol de un agente dentro del documento** (`has_sender`, RiC-R031). No son la procedencia de la transferencia.
  - En auditoría, `app/routers/ingesta.py:147-150` registra el `documento_cargado` con nombre, tamaño, fondo y expediente, sin datos de transferencia.
- Prueba automatizada: ninguna encontrada.
- Razonamiento: «Lote» en el código solo significa «varios archivos en una misma petición» (`tests/test_ingesta.py::test_lote_mixto_cada_archivo_queda_en_su_estado`). No queda ningún registro persistente que agrupe esos archivos. Prueba de profundidad: si dos archivistas reciben la misma transferencia de la «Secretaría de Gobierno», no hay dónde anotarlo, ni como texto libre ni como registro controlado. El dato se pierde.
- Acción recomendada: crear la tabla `lotes_ingesta` (id, fondo, remitente_agente_id hacia el vocabulario de agentes, dependencia_origen_agente_id, número y fecha EDTF del acta de transferencia, instanciación del acta escaneada, observaciones) y `instanciaciones.lote_id`. Ese lote alimentaría ISAD-G 3.2.4 en la descripción y la relación de custodia (DES-05). Exponerlo en `POST /api/ingesta/cargar` y probarlo.

### ING-03 · OAIS: recepción con huella SHA-256 y detección de duplicados
- Rama: OAIS (Receive Submission / Quality Assurance), PREMIS (fixity)
- Módulo(s): ingesta
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/models/instanciacion.py:48-53` — `huella`, `algoritmo_huella` (SHA-256), `duplicado_de_id`, `duplicado_confirmado`; índice `ix_instanciaciones_fondo_huella` (94). Migración: `alembic/versions/0002_ingesta.py:85,110`.
  - `app/servicios/procesamiento.py:68-82` — `_huella` calcula el SHA-256 por bloques. Líneas 85-98: `duplicado_de` busca en el mismo fondo. Líneas 123-133: detiene el proceso en `duplicado_pendiente`.
  - `app/routers/ingesta.py:213-226` — confirmar duplicado. Líneas 229-243: descartar con borrado físico, registrado en auditoría (235).
- Prueba automatizada: `tests/test_ingesta.py::test_duplicado_confirmar_continua_hasta_listo`, `::test_duplicado_cancelar_elimina_documento_y_archivo`, `::test_mismo_archivo_en_otro_fondo_no_es_duplicado`.
- Razonamiento: el control de calidad de la recepción opera de verdad (el trabajador corre como servicio, `docker-compose.yml:52-55`). Los duplicados se detectan por fondo, como pide el prompt. La huella se calcula al recibir y no se contrasta con una huella del productor (esa brecha está en ING-01).

### ING-04 · Identificación de formato contra PRONOM con Siegfried
- Rama: OAIS (Quality Assurance) / PREMIS (format) / PRONOM
- Módulo(s): ingesta
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/formato.py:57-75` — invoca `sf -json -nr`. Una coincidencia «extension only» **no** cuenta como identificada (72-74), así que no hay identificación casera por extensión.
  - `app/models/instanciacion.py:56-64` — `formato_puid`, `formato_nombre`, `formato_version`, `formato_mime`, `formato_base`, `formato_no_identificado`, `herramienta_identificacion` y `mecanismo_identificacion_id` (agente mecanismo del vocabulario).
  - `app/servicios/procesamiento.py:135-145` (formato) y `:162-169` (alerta `formato_no_identificado` sin bloquear).
  - Dependencia externa satisfecha: `Dockerfile:7-11,32-33` compila Siegfried v1.11.9 con `default.sig`. `.github/workflows/deploy.yml:54-60` lo instala en CI. Las pruebas usan `~/go/bin/sf` (`tests/conftest.py:24-27`).
  - Decisión documentada: `documentacion/modulo-1-ingesta.md:234` (tabla DROID / Siegfried / FIDO).
- Prueba automatizada: `tests/test_ingesta.py::test_carga_unica_llega_a_listo_para_descripcion` (verifica `herramienta_identificacion` con PRONOM), `::test_formato_no_identificado_llega_a_listo_y_aparece_en_alertas`, `::test_herramienta_ausente_da_error_legible`.
- Razonamiento: el código está presente y la herramienta se instala en la imagen y en CI. Si el binario falta, el documento queda en `error` con un mensaje legible, nunca identificado a medias. Las firmas PRONOM quedan congeladas en la versión de la imagen, lo que es aceptable y está documentado.

### ING-05 · OCR con confianza por palabra y marca de baja confianza
- Rama: OAIS (Quality Assurance) / requisito propio del prompt de ingesta §3bis
- Módulo(s): ingesta, descripcion
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/texto.py:68-73` — `promedio` (vacío → 0 cuando el OCR no leyó ninguna palabra). Líneas 77-93: confianza por palabra del TSV de Tesseract (nivel 5, se descartan los -1). Línea 155: `tesseract … -l <idioma> txt tsv`.
  - `app/models/instanciacion.py:73-76` — `confianza_ocr` (nullable: vacío = no aplica), `palabras_ocr`, `ocr_baja_confianza`. Migración `alembic/versions/0010_ocr_y_codigos_ric_o.py:26-30`.
  - `app/servicios/procesamiento.py:147-153` — umbral leído de parámetros. `app/servicios/parametros.py:31` — umbral por defecto 70, configurable. `app/routers/ingesta.py:64-76` — solo el administrador lo cambia.
  - Llega a descripción: `app/routers/descripcion.py:52-53,76`, `frontend/src/pages/EspacioTrabajo.tsx:334`, `frontend/src/pages/Descripcion.tsx:159`.
  - Herramienta disponible: `Dockerfile:29-30` (tesseract-ocr y tesseract-ocr-spa); localmente `/usr/bin/tesseract` con `spa`.
- Prueba automatizada: `tests/test_ingesta.py::test_ocr_guarda_su_confianza_como_promedio_por_palabra`, `::test_documento_con_capa_de_texto_deja_la_confianza_vacia_y_no_en_cero`, `::test_confianza_bajo_el_umbral_marca_alerta_sin_bloquear`, `::test_el_umbral_es_configurable_y_solo_lo_cambia_el_administrador`, `::test_reintento_recalcula_la_confianza`; `tests/test_descripcion_v3.py::test_el_espacio_de_trabajo_avisa_la_confianza_baja_del_ocr`.
- Razonamiento: cumple §3bis completo. Dos salvedades. (1) La primera prueba citada **falló una vez de tres** en la corrida combinada y pasó aislada y en las otras dos corridas. Es intermitente, probablemente porque la confianza real de Tesseract roza el umbral (`assert i.confianza_ocr >= 70`). Conviene estabilizarla. (2) La «solución mixta» para manuscritos que sugería el prompt §7 se descartó a conciencia: solo Tesseract, con la limitación documentada en `documentacion/modulo-1-ingesta.md:237`.
- Acción recomendada: estabilizar la prueba (imagen sintética con más contraste o umbral de prueba fijado en el test).

### ING-06 · OAIS aplicado a la ingesta: funciones de la entidad Ingest
- Rama: OAIS (ISO 14721: Receive Submission, Quality Assurance, Generate AIP, Generate Descriptive Info, Coordinate Updates)
- Módulo(s): ingesta, preservacion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - Control de calidad: sí (ING-03, ING-04, ING-05).
  - Segunda copia al terminar la ingesta: `app/servicios/procesamiento.py:158-161` (`segunda_copia.asegurar(db, inst, "ingesta")`).
  - Recepción formal de un SIP, acuse de recibo al productor y validación del paquete recibido: busqué `acuse|recibo|receipt|SIP|submission` en routers, servicios y modelos, **sin resultado**.
  - Generación del AIP: no ocurre en la ingesta. `app/servicios/paquete.py:561` (`exportar_instanciacion`) se invoca solo desde `app/routers/preservacion.py:241`, a demanda.
  - La afirmación del equipo «este módulo cubre la función de Ingesta» (`documentacion/modulo-1-ingesta.md:219`) es una afirmación, no evidencia.
- Prueba automatizada: las de ING-03 a ING-05. Ninguna para recepción de SIP ni para acuse.
- Razonamiento: la parte técnica de la función Ingest (fixity, formato, duplicados, extracción de texto, réplica) es real y probada. La parte de **paquete** de OAIS falta: no hay SIP de entrada, ni acuse, ni información de procedencia del envío (ING-02), y el AIP se genera bajo demanda en otro módulo, no como resultado de la ingesta. Decir «ingesta OAIS» es correcto para el control de calidad y exagerado para el modelo de paquetes.
- Acción recomendada: documentar en la tesis qué funciones de Ingest de OAIS cubre el sistema y cuáles no. Si se implementa ING-01/ING-02, registrar un evento de recepción del lote (acuse) en auditoría y PREMIS.

### ING-07 · Enlace del panel de alertas al espacio de descripción para «formato no identificado»
- Rama: requisito del prompt de ingesta §9
- Módulo(s): ingesta, auditoria
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `frontend/src/pages/Alertas.tsx:105-107` — el botón «Ir a describir» solo aparece cuando `a.tipo === "ocr_baja_confianza"`. Para `formato_no_identificado` (etiqueta en `:29`) no hay enlace.
  - El prompt (§9) exige insignia ámbar y enlace directo al espacio de descripción para ambos casos.
- Prueba automatizada: ninguna de interfaz para el enlace.
- Razonamiento: el impacto es menor. La alerta aparece (backend probado), pero falta la navegación que el prompt pide para el segundo tipo.
- Acción recomendada: mostrar el mismo enlace para `formato_no_identificado` cuando la instanciación esté en `listo_para_descripcion`.

### ING-08 · Roles con acceso a los endpoints de ingesta
- Rama: requisito del prompt de ingesta §5
- Módulo(s): ingesta, autenticacion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/routers/ingesta.py:30-31` — dependencia de router `acceso_modulo("ingesta")`. `app/core/permisos.py:156-170` resuelve lectura o escritura según la tabla de roles.
  - `tests/test_ingesta.py::test_revisor_solo_consulta_la_cola` afirma que **el revisor obtiene 200** en `GET /api/ingesta/cola`.
- Prueba automatizada: `tests/test_ingesta.py::test_sin_sesion_ningun_endpoint_de_ingesta_responde`, `::test_consulta_no_accede_a_ingesta`, `::test_revisor_solo_consulta_la_cola`.
- Razonamiento: el prompt dice «rol de archivista o administrador» para todos los endpoints. La implementación abre la lectura al revisor mediante una tabla de roles configurable. Es una decisión razonable, pero se aparta del texto del prompt y no la encontré justificada en una tabla de decisión.
- Acción recomendada: documentar la desviación (o restringirla).

### ING-09 · Recorrido de los compromisos de verificación del prompt de ingesta
- Rama: prompt del módulo 1 (§3, §3bis, §4-§7, §10, §11)
- Módulo(s): ingesta
- Clasificación: Implementado pero incompleto o no conforme (por ING-07, ING-08 y la prueba intermitente de ING-05; el resto está cumplido)
- Evidencia (compromiso, cita, prueba):

| Compromiso | Evidencia | Prueba |
|---|---|---|
| Cuatro estados en un único campo, sin cola ni traspaso | `app/models/instanciacion.py:10,39` | `test_la_cola_nunca_devuelve_documentos_listos` |
| Formato no identificado no bloquea y va a alertas | `procesamiento.py:140,162-169` | `test_formato_no_identificado_llega_a_listo_y_aparece_en_alertas` |
| Confianza del OCR como promedio, vacía sin OCR | `texto.py:68-93`, `instanciacion.py:73` | `test_ocr_guarda_…`, `test_documento_con_capa_de_texto_…` |
| Umbral configurable (70), marca sin bloqueo | `parametros.py:31`, `procesamiento.py:151-153` | `test_confianza_bajo_el_umbral_…`, `test_el_umbral_es_configurable_…` |
| Validación de tamaño en el frontend, sin bloquear al resto | `frontend/src/pages/Ingesta.tsx:84-97` | `test_archivo_que_excede_el_limite_no_afecta_a_los_demas` (backend) |
| SHA-256, duplicados en el fondo, confirmar o cancelar | ING-03 | ING-03 |
| Error legible y reintento | `procesamiento.py:101-106,180-196`, `ingesta.py:246-259` | `test_reintento_de_un_documento_en_error`, `test_herramienta_ausente_da_error_legible` |
| Límite 500 MB configurable; `DIRECTORIO_ALMACENAMIENTO` reutilizado | `parametros.py:30`, `app/core/config.py:35` | `test_limite_por_defecto_y_solo_el_administrador_lo_cambia` |
| Tabla de decisión PRONOM y OCR | `documentacion/modulo-1-ingesta.md:234,237` | — |
| Auditoría de carga, confirmación y descarte | `ingesta.py:138,147,222,235,253` | — (lo ejercitan las pruebas de auditoría) |
| Estado vacío explícito de la cola | `frontend/src/pages/Ingesta.tsx:385` | — |
| Enlace del panel al espacio de descripción para ambos tipos | **parcial**, ver ING-07 | ninguna |
| Solo archivista o administrador | **desviación**, ver ING-08 | `test_revisor_solo_consulta_la_cola` |
| Prueba de lote mixto | `tests/test_ingesta.py::test_lote_mixto_cada_archivo_queda_en_su_estado` | sí |

- Prueba automatizada: las citadas en la tabla. 31/31 en `tests/test_ingesta.py` en dos de tres corridas.
- Razonamiento: el prompt de ingesta está cumplido casi por completo y con pruebas reales. Las brechas de §6 de la auditoría (ING-01, ING-02, ING-06) **no estaban pedidas en el prompt del módulo**: es una brecha de especificación, no de implementación.
- Acción recomendada: las de ING-05, ING-07 e ING-08.

---

## DESCRIPCIÓN

### DES-01 · Fechas EDTF en tres subtipos con calificador de incertidumbre y aproximación
- Rama: EDTF (ISO 8601-2, niveles 0-1 y conjunto del nivel 2)
- Módulo(s): descripcion
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/models/descripcion.py:129-149` — tabla `fechas`: `expresion` (RiC-A19), `subtipo` (simple / rango / conjunto, 139), `edtf` (141), `inicio`/`fin` (143-144), `normalizada` (solo un día exacto, 145) y `calendario` declarado «gregoriano» (148). Migraciones: `alembic/versions/0009_descripcion_contexto.py:34-39`, `0012_descripcion_v3.py:39`.
  - `app/servicios/fechas.py:33-36` — expresiones regulares del subconjunto (calificadores `?~%`, X sin precisar, extremos abiertos, `{a,b,c}`). Líneas 119-129: confirmación con la librería `edtf==5.0.2` (`requirements.txt:32`). Líneas 132-175: `interpretar` devuelve el subtipo, la forma legible en español y los límites.
  - `app/servicios/descripcion.py:287-305` — toda fecha publicada pasa por `fechas.interpretar`. Una fecha sin EDTF no se publica (293-294).
  - `app/servicios/motor.py:289-301` — una propuesta del motor con EDTF inválida se descarta y la completa la archivista.
  - Interfaz: `frontend/src/components/SelectorFecha.tsx:42-45,79-90` — selector de calificador y precisión; la archivista no escribe el símbolo.
  - Decisión documentada: `documentacion/modulo-2-descripcion.md:349`.
- Ejecución directa de `app.servicios.fechas.interpretar`:

| Entrada | Resultado |
|---|---|
| `1948~` | simple · «c. 1948» · 1948-01-01→1948-12-31 |
| `1948?` | simple · «1948 (incierta)» |
| `1948%` | simple · «c. 1948 (incierta)» |
| `194X` / `19XX` | «década de 1940» / «siglo XX (1900–1999)» |
| `1948-05-12` | simple exacta (`normalizada` = 1948-05-12) |
| `1948?/1950~` | rango · «de 1948 (incierta) a c. 1950» |
| `/1952` · `1948/` | rango abierto · «hasta 1952 (inicio desconocido)» · «desde 1948 (fin desconocido)» |
| `{1948-01-15,1948-03-20,1948-06-10}` | conjunto · límites 1948-01-15→1948-06-10 |
| `1948-02-30`, `1952/1948`, `[1948,1949]`, `1948-21`, `-0500`, `c.1948` | rechazadas |

- Prueba automatizada: `tests/test_descripcion_contexto.py::test_fecha_se_interpreta_y_normaliza` (parametrizada), `::test_fecha_fuera_del_subconjunto_se_rechaza`, `::test_fechas_aproximada_rango_y_conjunto_quedan_en_edtf` (persiste `1948~`, `1948/1952` y `{…}` en BD por la API), `::test_un_evento_de_decision_por_cada_propuesta_…` (`1948~` corregida a `1948?`); `tests/test_descripcion_v3.py::test_la_fecha_declara_su_calendario`.
- Razonamiento: la entidad Date ya no guarda solo un día de calendario. Guarda la cadena EDTF con su calificador y su subtipo, y la fecha exacta queda solo como derivada. El calificador vive dentro de la cadena EDTF (no hay una columna `calificador` aparte), lo que es conforme con EDTF y se puede recuperar. Prueba de profundidad: dos personas que escriben «hacia 1948» y «circa 1948» llegan ambas a `1948~` por el selector, el mismo valor normalizado. Matices menores en DES-03; fechas fuera de la entidad Date en DES-02. Ninguna prueba ejercita `%` (incierta y aproximada) a través de la API.

### DES-02 · Fechas extremas de fondo y expedientes guardadas como texto libre, fuera de EDTF
- Rama: EDTF / ISAD-G 3.1.3
- Módulo(s): descripcion, instrumentos
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/models/recurso_documental.py:30` — `fechas_extremas = Column(String(60))`, con el comentario «p. ej. "1930–1955", tal como se describe».
  - `app/routers/fondos.py:49` — se guarda tal como se escribe al registrar el fondo, sin validar.
  - `app/servicios/grafo.py:139` y `app/servicios/resumen_fondo.py:61` — se interpreta después con una expresión regular de años (`_AÑOS`).
- Prueba automatizada: ninguna encontrada que valide `fechas_extremas` como EDTF.
- Razonamiento: las fechas de los documentos descritos sí son EDTF (DES-01), pero las fechas extremas del fondo, que ISAD-G 3.1.3 exige al nivel más alto, son texto libre. Prueba de profundidad: «1930-1955», «1930 a 1955» y «c. 1930–1955» terminan en tres valores de texto distintos, y la incertidumbre no se puede expresar de forma normalizada.
- Acción recomendada: reemplazar `fechas_extremas` por una relación con un nodo `Fecha` de subtipo rango (o una columna EDTF validada con `fechas.interpretar`) y migrar los valores existentes.

### DES-03 · Desvíos menores del subconjunto EDTF declarado
- Rama: EDTF
- Módulo(s): descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/fechas.py:33` — `_FECHA` permite `XX` en el mes con un día precisado. `interpretar("1948-XX-12")` se **acepta**: la librería lo clasifica como `PartialUnspecified`, que es nivel 2 y queda fuera del subconjunto declarado en `fechas.py:5-13`. La forma legible resulta «1948 (mes sin precisar)», que **pierde el día 12**, y los límites cubren todo el año.
  - `app/servicios/fechas.py:36` — el conjunto no admite calificador por elemento: `{1948~,1949}` se rechaza, aunque la librería lo acepta.
  - Intervalo abierto `../1952` (EDTF «abierto», distinto de «desconocido») se rechaza a propósito (`tests/test_descripcion_contexto.py:82`). El sistema solo modela el extremo «desconocido» (`/1952`).
- Prueba automatizada: no hay prueba para `1948-XX-12` ni para conjuntos con calificador.
- Razonamiento: las tres son delimitaciones o defectos menores, pero la primera es un error real: se admite una expresión fuera del subconjunto y su forma legible distorsiona el dato.
- Acción recomendada: rechazar `YYYY-XX-DD` en la expresión regular, o mostrarlo bien. Documentar la ausencia de calificadores en el conjunto y de «abierto» frente a «desconocido».

### DES-04 · Las relaciones nuevas entre documentos (parte, precede, sigue, documenta) como relaciones tipadas
- Rama: RiC-CM (relaciones) aplicado por el prompt de descripción; complemento a la norma de §6
- Módulo(s): descripcion
- Clasificación: Implementado y conforme
- Identificación en el prompt (`725ac5b6`, §2, §3 y §7): las relaciones nuevas que involucran al documento son (1) **parte documental** dentro de la unidad documental (§2, línea 15), (2) **precede** y (3) **sigue** dentro de la misma serie (§3, punto cuarto; §7 «Validación»), y (4) **custodio distinto del productor** (§3, punto quinto). A eso se suma la relación central «documento **documenta** Actividad» (§2-§3). La custodia se trata aparte en DES-05 porque es la que tiene brecha.
- Evidencia:
  - Tabla única tipada `relaciones`: `app/models/descripcion.py:170-202`, con `codigo_ric` como enumeración controlada (183) y `fecha_edtf` y `nota` (198-199). Códigos en `app/models/enums.py:95` (`has_or_had_constituent`), `:115` (`documents`), `:127` (`has_or_had_holder`), `:128` (`precedes_or_preceded`). Migración `alembic/versions/0010_ocr_y_codigos_ric_o.py:18`.
  - Parte: `app/servicios/descripcion.py:653-698` — crea un `RecursoDocumental` de nivel `parte_documental` (`recurso_documental.py:13`, migración `0012_descripcion_v3.py:24`) unido con `has_or_had_constituent` (683-684) y con su propio recorte o instanciación (686-696).
  - Secuencia: `app/servicios/descripcion.py:623-642` — exige la misma serie y rechaza la contradicción inversa (638-640). Se usa en publicar (750-753) y en reabrir (993-996). Se lee en ambos sentidos con `rico:precedesOrPreceded` / `rico:followsOrFollowed` (809-815).
  - Documenta: `app/servicios/descripcion.py:77,419-421`.
  - API: `app/schemas/descripcion.py:91-92` (`precede_a_id`, `sigue_a_id`).
- Prueba automatizada: `tests/test_descripcion_v3.py::test_parte_documental_con_recorte_queda_unida_a_su_unidad_documental`, `::test_secuencia_y_custodio_se_guardan_y_se_ven_en_el_catalogo`, `::test_secuencia_solo_en_la_misma_serie`; `tests/test_descripcion_contexto.py::test_la_actividad_queda_conectada_a_su_tipo_agente_y_mandato_y_se_ve_en_el_catalogo`.
- Razonamiento: no son columnas ni tablas dedicadas, sino **filas tipadas** con código controlado en una tabla de relaciones polimórfica, recuperables en ambos sentidos y probadas. Eso cumple la intención («no texto libre»). Prueba de profundidad: dos archivistas que declaran «el oficio 115 sigue al 114» producen la misma fila `precedes_or_preceded` del anterior al siguiente; la inversa no se duplica. Desviación respecto al prompt: la parte usa `hasOrHadConstituent` (R003) y no `hasOrHadPart`, como pedía el §3. Es una decisión documentada (`documentacion/modulo-2-descripcion.md:143`) y la tiene que validar el frente RiC-O.

### DES-05 · Relación de custodia: existe, pero sin fechas, sin cadena y solo sobre el Record Resource
- Rama: RiC-CM (custodia, RiC-R039i) / ISAD-G 3.2.3
- Módulo(s): descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/descripcion.py:74` — rol `custodio` → `has_or_had_holder`. Líneas 388-394: se rechaza un custodio igual al productor.
  - La relación se crea siempre con origen en el `recurso_documental`. Busqué `has_or_had_holder` en servicios y routers: no existe ninguna ruta que la cree **desde una Instantiation**, aunque `app/servicios/ric_o.py:144` declara que el dominio la admite.
  - `Relacion.fecha_edtf` (`app/models/descripcion.py:198`) existe, pero **la descripción no la llena** para el custodio. `fecha_edtf` solo se escribe en `app/servicios/autoridad.py:448-455` (relaciones entre agentes).
- Prueba automatizada: `tests/test_descripcion_v3.py::test_secuencia_y_custodio_se_guardan_y_se_ven_en_el_catalogo`, `::test_custodio_igual_al_productor_se_rechaza`.
- Razonamiento: hay un custodio actual o pasado, tipado y distinto del productor, y eso cumple §3/§7. Pero no se puede ordenar una sucesión de custodios ni fecharlos: «tuvo la custodia de 1950 a 1970» no tiene dónde guardarse. Por eso la relación no sostiene la «cadena de custodia» que justifica el anexo de mapeo (`73aeb098`, §3).
- Acción recomendada: permitir `fecha_edtf` (rango) y `nota` en la relación de custodio desde la descripción, y admitir el custodio sobre la instanciación.

### DES-06 · Historia de custodia narrativa (historia archivística)
- Rama: ISAD-G 3.2.3 (Historia archivística) / RiC-CM (atributo History de Record Resource)
- Módulo(s): descripcion
- Clasificación: No implementado
- Evidencia: busqué en models, alembic/versions, servicios, routers, schemas, tests y frontend los términos `historia_custod|custodial|historia archiv|archival_history|historia de custodia|history`. Única aparición: `app/servicios/paquete.py:416`, que es la nota de la PDI del AIP («historia de custodia y de eventos técnicos… tomada de los eventos PREMIS»). Es procedencia **técnica**, no historia archivística narrativa. `app/models/recurso_documental.py:27-73` no tiene ningún campo de historia. `EntidadVocabulario.historia` (`app/models/descripcion.py:105`) es la historia **del agente** (ISAAR 5.2.2), no la del documento.
- Prueba automatizada: ninguna encontrada.
- Razonamiento: no existe ningún campo, ni de texto libre, para narrar cómo llegó el fondo o el documento a su custodio actual. El único dato de custodia es la relación tipada de DES-05, que tampoco tiene fechas.
- Acción recomendada: añadir `recursos_documentales.historia_archivistica` (Text, con origen y confianza en sus columnas propias) y exponerlo en la descripción, el catálogo y los instrumentos (EAD3 `<custodhist>`).

### DES-07 · Cobertura de ISAD-G: 7 áreas, 26 elementos
- Rama: ISAD-G
- Módulo(s): descripcion, vocabularios, instrumentos
- Clasificación: Implementado pero incompleto o no conforme (10 cubiertos, 6 parciales, 10 ausentes)
- Evidencia (tabla elemento por elemento). Para cada «ausente» busqué en models, alembic, schemas, servicios y frontend los términos `forma_ingreso|adquisici|acquisition`, `nuevos_ingresos|accrual`, `organizacion|arrangement`, `escritura|script`, `localizacion_original|existencia_original`, `publicaciones|bibliograf`, `nota_archivero|archivist_note`, `reglas_descripcion|rules_or_conventions`, `instrumentos_descripcion|finding_aid`, `caracteristicas_fisicas|estado_conservacion`, `valoraci|retenci|disposici`: 0 resultados en `recursos_documentales`.

| ISAD-G | Elemento | Campo / columna | Estado |
|---|---|---|---|
| 3.1.1 | Código de referencia | `recursos_documentales.codigo_referencia` (`recurso_documental.py:69`; mig. `0006_instrumentos.py:17`), texto libre de 60 caracteres, no compuesto desde el CCD | Cubierto (ver DES-08) |
| 3.1.2 | Título | `recursos_documentales.titulo` (`:29`) | Cubierto |
| 3.1.3 | Fechas | Nodo `fechas` EDTF + `is_creation_date_of` (`descripcion.py:76`); en el fondo, `fechas_extremas` texto libre (`:30`) | Parcial (DES-02) |
| 3.1.4 | Nivel de descripción | `recursos_documentales.nivel` (`:13,28`), dato propio | Cubierto |
| 3.1.5 | Volumen y soporte | `folios` (`:72`), `soporte` (`:73`, texto libre), `caja`, `carpeta` (`:70-71`) | Cubierto |
| 3.2.1 | Nombre del productor | Relación `has_creator` (`app/servicios/descripcion.py:69`) hacia un agente del vocabulario | Cubierto |
| 3.2.2 | Historia institucional / biográfica | `entidades_vocabulario.historia` (`app/models/descripcion.py:105`), en la ficha del agente | Cubierto (vía agente) |
| 3.2.3 | Historia archivística | — | **Ausente** (DES-06) |
| 3.2.4 | Forma de ingreso | — (no hay lote ni acta, ING-02) | **Ausente** |
| 3.3.1 | Alcance y contenido | `alcance_contenido` (`:41`) | Cubierto |
| 3.3.2 | Valoración, selección y eliminación | — | **Ausente** (DES-09) |
| 3.3.3 | Nuevos ingresos | — | **Ausente** |
| 3.3.4 | Organización | Solo implícita en el árbol `incluido_en_id` (`:33`); ningún campo narrativo | **Ausente** |
| 3.4.1 | Condiciones de acceso | `condiciones_acceso` (`:58`; mig. `0012:33`) | Cubierto |
| 3.4.2 | Condiciones de reproducción | `condiciones_uso` (`:59`) | Cubierto |
| 3.4.3 | Lengua / escritura | `idiomas` ARRAY ISO 639-3 (`:52`); escritura (ISO 15924) ausente | Parcial |
| 3.4.4 | Características físicas y requisitos técnicos | Técnicos en la instanciación (`instanciacion.py:56-61` formato PRONOM); estado físico del original ausente | Parcial |
| 3.4.5 | Instrumentos de descripción | — (el módulo 4 genera instrumentos, pero la unidad no los referencia) | **Ausente** |
| 3.5.1 | Existencia y localización de los originales | — (`is_original_of` declarado en `enums.py:96` pero sin uso: grep sin resultados en servicios) | **Ausente** |
| 3.5.2 | Existencia y localización de copias | — (`has_copy`, `enums.py:97`, sin uso) | **Ausente** |
| 3.5.3 | Unidades de descripción relacionadas | Solo `precedes_or_preceded`, `has_or_had_constituent` (DES-04) e `is_related_to` función↔serie (`app/servicios/autoridad.py:364`); falta un vínculo genérico a material relacionado | Parcial |
| 3.5.4 | Nota de publicaciones | — | **Ausente** |
| 3.6.1 | Notas | `recursos_documentales.nota` (`:31`): solo se escribe al registrar el fondo (`app/routers/fondos.py:50`), no existe en el esquema de publicar o reabrir | Parcial |
| 3.7.1 | Nota del archivero | Solo quién: `publicado_por_id` (`:63`) y la auditoría; ningún texto | Parcial |
| 3.7.2 | Reglas o normas | — en el Record Resource (`entidades_vocabulario.reglas`, `descripcion.py:111`, solo existe para agentes) | **Ausente** |
| 3.7.3 | Fecha(s) de la descripción | `publicado_en` (`:62`), `actualizado_en` (`:64`) | Cubierto |

- Prueba automatizada: cubren campos presentes `tests/test_descripcion_v3.py::test_idioma_y_condiciones_se_guardan_y_sin_ellas_publica` (3.4.1-3.4.3), `tests/test_instrumentos.py::test_inventario_un_renglon_por_unidad_o_expediente_con_columnas_fuid` (3.1.1, 3.1.5) y `tests/test_descripcion.py::test_documento_individual_de_la_cola_a_la_publicacion` (3.1.2, 3.3.1). No hay prueba de conformidad ISAD-G como tal.
- Razonamiento: el prompt de descripción no enumera ISAD-G; los campos se agregaron según RiC. Las áreas 1 (identificación) y 4 (acceso y uso) están casi completas. Las áreas 2 (contexto archivístico: historia archivística y forma de ingreso), 3 (valoración, nuevos ingresos, organización), 5 (documentación asociada) y 7 (reglas, nota del archivero) están mayormente ausentes. Una exportación EAD3 o ISAD-G saldría con huecos sistemáticos.
- Acción recomendada: agregar como columnas de texto del Record Resource 3.2.3, 3.2.4, 3.3.2-3.3.4, 3.4.5, 3.5.1-3.5.4 y 3.7.1-3.7.2, más `nota` en el esquema de publicar o reabrir. Usar `is_original_of` / `has_copy` donde aplique, o bien documentar la delimitación.

### DES-08 · Cuadro de clasificación documental (fondo-sección-subsección-serie-subserie con códigos)
- Rama: CCD/TRD (metodología AGN Colombia)
- Módulo(s): descripcion, vocabularios
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - Niveles: `app/models/recurso_documental.py:13` — `fondo, seccion, serie, subserie, expediente, unidad_documental, parte_documental`. **No existe `subseccion`.**
  - Creación: el fondo se crea solo en `app/routers/fondos.py:48`. Las agrupaciones solo al describir un conjunto con documentos, `NIVELES_CONJUNTO = ("expediente","subserie","serie")` (`app/servicios/descripcion.py:61`; esquema `app/schemas/descripcion.py:26`). Busqué `nivel="seccion"` y `RecursoDocumental(` en routers y servicios: **no hay ninguna ruta que cree una sección** ni una serie vacía de la estructura del CCD.
  - Códigos: `codigo_referencia` es texto libre por registro (`recurso_documental.py:69`), sin composición jerárquica (p. ej. 100.12.03) ni herencia del nivel superior. Busqué `codigo` en models: solo esa columna.
  - Vínculo función↔serie de la TRD: sí existe. `app/servicios/autoridad.py:363-365` (`is_related_to`, tipo de actividad → serie o subserie), `app/routers/vocabulario.py:191-197`, `frontend/src/components/FichaAutoridad.tsx:827`. Jerarquía función/subfunción por SKOS (`concepto_superior_id`, `app/models/descripcion.py:121`).
- Prueba automatizada: `tests/test_autoridad.py::test_tipo_de_actividad_con_su_serie_documental` (vínculo función-serie y rechazo hacia un expediente). Ninguna prueba crea secciones ni valida códigos del CCD.
- Razonamiento: el árbol jerárquico existe y la función se conecta con la serie, que es lo más cercano a la TRD. Pero el CCD como instrumento (estructura previa codificada de secciones, subsecciones, series y subseries a la que se asignan los documentos) no existe. Las series nacen solo de agrupar documentos, la sección no se puede crear y la subsección no existe. Prueba de profundidad: dos archivistas que codifican la misma serie como «CO» y «100.12» terminan con dos textos libres sin validación ni herencia.
- Acción recomendada: agregar el nivel `subseccion`. Permitir crear la estructura del CCD (sección, subsección, serie, subserie) sin documentos, con un código por nivel y el código de referencia compuesto o validado desde el padre.

### DES-09 · TRD: tiempos de retención y disposición final heredados
- Rama: CCD/TRD (Acuerdo AGN 004/2019) / ISAD-G 3.3.2
- Módulo(s): descripcion, vocabularios, preservacion
- Clasificación: No implementado
- Evidencia: busqué `retenci|disposici|TRD|conservacion_total|seleccion|archivo_gestion|archivo_central|valoraci|eliminacion|tiempo` en app/, alembic/versions, tests y frontend/src. Solo aparecen comentarios de «TRD» en el vínculo función-serie (`app/servicios/autoridad.py:363`, `app/servicios/ric_o.py:198`, `frontend/src/pages/Vocabularios.tsx:26,43`) y el comentario de `regulates_or_regulated` «p. ej. retención» (`app/models/enums.py:101`), que en el código solo se usa entre un mandato y una actividad (`app/servicios/autoridad.py:347-357`, `app/servicios/descripcion.py:410,441`). No hay columnas de retención en gestión o central, ni de disposición final (CT / E / S / M), ni lógica de herencia hacia expedientes y unidades.
- Prueba automatizada: ninguna encontrada.
- Razonamiento: el sistema no puede responder «¿cuánto se retiene esta serie y qué pasa al final?». No hay dato que heredar.
- Acción recomendada: tabla `trd_series` (serie o subserie, retención AG y AC en años, disposición final controlada, procedimiento, norma) con herencia calculada hacia los niveles inferiores y exposición en el inventario. Si queda fuera de alcance, declararlo como delimitación.

### DES-10 · Contexto de vocabulario para el motor: léxico (trigramas) en lugar de búsqueda semántica
- Rama: requisito del prompt de descripción §4 (cuarto principio)
- Módulo(s): descripcion, vocabularios
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia: busqué `embedding|incrustaci|pgvector|vector(` en app/: **0 resultados**. `app/servicios/vocabulario.py:9,87-94` usa `pg_trgm similarity`. El contexto se pasa al motor en `app/servicios/motor.py:189,232,380-414`. La desviación está documentada en `documentacion/modulo-2-descripcion.md:356,501`.
- Prueba automatizada: `tests/test_descripcion_v3.py::test_el_motor_recibe_el_vocabulario_del_fondo_y_referencia_la_entidad_existente`, `::test_coincidencia_exacta_con_el_contexto_se_referencia_aunque_el_motor_no_de_codigo`.
- Razonamiento: la función existe y está probada, pero con un mecanismo distinto del que el prompt exige («búsqueda semántica sobre los vectores de incrustación»). Está justificada en una tabla de decisión, y aun así un nombre citado con sigla o apodo no se recupera.
- Acción recomendada: mantener la decisión con su justificación en la tesis, o añadir la forma alternativa del nombre de la ficha de autoridad a la búsqueda.

### DES-11 · Recorrido de los compromisos del prompt de descripción
- Rama: prompt del módulo 2 (§2-§12)
- Módulo(s): descripcion
- Clasificación: Implementado pero incompleto o no conforme (por los compromisos parciales de la tabla)
- Evidencia (solo lo no cumplido o parcial; el resto está verificado arriba o en las pruebas citadas):

| Compromiso del prompt | Estado | Evidencia |
|---|---|---|
| §2 Record Resource «al nivel que el archivista elija, fondo, sección, serie…» | **Parcial**: no se puede crear una sección y el fondo solo lo crea el administrador | `app/servicios/descripcion.py:61`, `app/schemas/descripcion.py:26` |
| §2 Parte documental con `hasOrHadPart` | **Desviación documentada**: usa `hasOrHadConstituent` | `app/servicios/descripcion.py:683` |
| §3 Actividad «está autorizada por» Mandato (`authorizedBy`) | **Desviación documentada**: R063 `regulatesOrRegulated` + R067 `authorizes` | `app/servicios/descripcion.py:17-18,441`; `documentacion/modulo-2-descripcion.md:350` |
| §4 Recuperación semántica por incrustaciones | **No** (léxica), ver DES-10 | — |
| §5 EDTF tres subtipos, calificadores, calendario declarado | Cumple, con matices (DES-01, DES-03) | — |
| §5 Custodio y cadena con fechas | Parcial (DES-05) | — |
| §7 Custodio también para la Instantiation (§3 quinto) | **No** | DES-05 |
| §11 Prueba del calificador `%` y de dígitos sin precisar persistidos por la API | **Parcial**: `%` sin prueba; `194X` solo en la prueba unitaria | `tests/test_descripcion_contexto.py:68-79` |
| §11 Las demás pruebas obligatorias (individual, conjunto, confianza baja, reutilizar y crear los seis tipos, bloqueo, reapertura, parte, grupo, idioma y condiciones, secuencia y custodio, cadena de la actividad, sub-actividad, cola, consulta pública sin procedencia) | Presentes | `tests/test_descripcion.py` (135-513), `tests/test_descripcion_contexto.py` (118-348), `tests/test_descripcion_v3.py` (65-337) |
| §12 Ejemplos documentados para la sustentación | Afirmados por el equipo (`documentacion/modulo-2-descripcion.md:479`). No verificados contra datos reales del fondo de prueba | — |

- Prueba automatizada: las citadas. Las 45 de `test_descripcion_contexto.py` y `test_descripcion_v3.py` pasaron en las tres corridas.
- Razonamiento: el prompt de descripción está implementado con mucha profundidad (procedencia en columnas propias, vocabulario controlado, EDTF real, relaciones tipadas). Los incumplimientos son puntuales y la mayoría son desviaciones documentadas. Las brechas grandes de este frente son las normas complementarias que el prompt no especificó: ISAD-G (DES-07), CCD/TRD (DES-08, DES-09) e historia archivística (DES-06).
- Acción recomendada: las de DES-02, DES-03, DES-05 y DES-08. Añadir una prueba de `%` y `194X` vía `POST /api/descripcion/publicar`.

---

## Tabla resumen

| ID | Título | Clasificación |
|---|---|---|
| ING-01 | SIP conforme a BagIt al confirmar un lote | No implementado |
| ING-02 | Procedencia del lote (remitente, dependencia, acta) en tabla propia | No implementado |
| ING-03 | OAIS: huella SHA-256 y duplicados | Implementado y conforme |
| ING-04 | Formato contra PRONOM con Siegfried | Implementado y conforme |
| ING-05 | OCR con confianza por palabra y marca de baja confianza | Implementado y conforme (prueba intermitente) |
| ING-06 | OAIS Ingest: SIP, acuse y AIP en la ingesta | Implementado pero incompleto o no conforme |
| ING-07 | Enlace de la alerta «formato no identificado» a descripción | Implementado pero incompleto o no conforme |
| ING-08 | Roles: el revisor lee la cola de ingesta | Implementado pero incompleto o no conforme |
| ING-09 | Recorrido de compromisos del prompt de ingesta | Implementado pero incompleto o no conforme |
| DES-01 | Fechas EDTF en tres subtipos con calificador | Implementado y conforme |
| DES-02 | Fechas extremas de fondo y expediente en texto libre | Implementado pero incompleto o no conforme |
| DES-03 | Desvíos menores del subconjunto EDTF (`1948-XX-12`, conjunto sin calificador) | Implementado pero incompleto o no conforme |
| DES-04 | Relaciones nuevas entre documentos (parte, precede, sigue, documenta) tipadas | Implementado y conforme |
| DES-05 | Custodia sin fechas, sin cadena y sin instanciación | Implementado pero incompleto o no conforme |
| DES-06 | Historia de custodia narrativa (ISAD-G 3.2.3) | No implementado |
| DES-07 | ISAD-G: 10 cubiertos, 6 parciales, 10 ausentes de 26 | Implementado pero incompleto o no conforme |
| DES-08 | CCD: sección no creable, sin subsección, códigos libres | Implementado pero incompleto o no conforme |
| DES-09 | TRD: retención y disposición final heredadas | No implementado |
| DES-10 | Contexto del motor léxico, no semántico | Implementado pero incompleto o no conforme |
| DES-11 | Recorrido de compromisos del prompt de descripción | Implementado pero incompleto o no conforme |
