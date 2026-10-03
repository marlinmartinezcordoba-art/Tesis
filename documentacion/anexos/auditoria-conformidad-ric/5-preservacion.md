# Auditoría · Frente 5 · Normas complementarias de preservación (PREMIS, OAIS, BagIt, NDSA)

Vara de medir: prompt de auditoría §6 (párrafo «En Preservación…») y prompt del Módulo 5 actualizado (`fa5d159f-…_Actualizado_2.md`, §§5–14).
Solo lectura. Todas las citas `ruta:línea` se verificaron con grep o lectura directa sobre `/home/user/Tesis`.

Respuesta corta a las cinco preguntas del §6:
1. **PREMIS**: las cuatro entidades se producen **por cada instanciación**, no como resumen, pero **solo bajo demanda, al exportar el AIP** (no hay un PREMIS persistido ni consultable fuera del paquete). Hay brechas concretas: el agente persona no sale del vocabulario, las fechas de dos eventos son aproximadas y los recortes reciben un evento de ingreso falso.
2. **Segunda copia**: se crea **automáticamente** (ingesta, migración, recorte y relleno por el trabajador) y se verifica **en cada pasada de fijeza** con alerta propia. Opera en producción (servicio `trabajador` + volumen `segunda_copia`), pero está **en el mismo disco, en el mismo servidor, con el mismo usuario con permiso de escritura y el mismo proceso que verifica**. Es independiente de la carpeta primaria, no del equipo.
3. **veraPDF / JHOVE**: **no integrados**. No aparecen en código, Dockerfile, CI ni pruebas; solo se mencionan como pendientes en la documentación. Hoy el «PDF/A» lo produce Ghostscript, y lo único que se comprueba es que Siegfried reconozca un PUID de PDF/A, lo que es identificación y no validación.
4. **Respaldo y simulacro de restauración de la base de datos**: **no existe ninguno de los dos**. El propio código lo declara: `"simulacro_base_de_datos": None` con el comentario «aún no existe en el sistema».
5. **Fijeza periódica**: es real, dentro del bucle del trabajador (30 días por defecto). Tiene dos fallos operativos: una pasada interrumpida no se reanuda y no hay aviso si la verificación se atrasa.

---

### PRE-01 · Las cuatro entidades PREMIS por instanciación: estructura, alcance y validación
- Rama: PREMIS
- Módulo(s): preservacion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/paquete.py:340-355` — `premis_xml()` arma un documento `premis` 3.0 por instanciación con el orden Objeto → Eventos → Agentes (sin duplicados, `:347-352`) → Derechos (`:353-354`, solo si hay declaración).
  - `app/servicios/paquete.py:509-529` — `_carpeta_instanciacion()` escribe `metadatos/premis.xml` **por cada instanciación**, también dentro del paquete de expediente (`:620-622`).
  - **Unidades semánticas del Objeto** (`_objeto_premis`, `app/servicios/paquete.py:212-270`):
    - `xsi:type premis:file` (objectCategory) en `:214`;
    - `objectIdentifier` UUID en `:215`;
    - `compositionLevel` en `:217`;
    - `fixity` con `messageDigestAlgorithm`, `messageDigest` y `messageDigestOriginator` en `:218-221`;
    - `size` en `:222`;
    - `formatDesignation` con `formatName`/`formatVersion` en `:223-227`;
    - `formatRegistry` PRONOM con PUID y rol en `:228-232`;
    - `formatNote` (herramienta de identificación tomada del mecanismo) en `:233-235`;
    - `creatingApplication` (nombre y fecha, solo para derivadas por migración) en `:236-241`;
    - `originalName` en `:242`;
    - `storage` primaria en `:243-247` y `storage` de la segunda copia con su estado en `:250-256`;
    - `relationship` de derivación «has source / is source of» en `:257-266`;
    - `linkingEventIdentifier` en `:267-268`;
    - `linkingRightsStatementIdentifier` en `:269-270`.
  - **Unidades del Evento** (`_evento_premis`, `app/servicios/paquete.py:273-286`): `eventIdentifier` `:275`, `eventType` `:276`, `eventDateTime` `:277`, `eventDetail` `:278`, `eventOutcome` `:280`, `eventOutcomeDetailNote` `:281-282`, `linkingAgentIdentifier` con rol `:283-284`, `linkingObjectIdentifier` con rol `:285-286`. Los tipos de evento salen de `eventos_de()` `:115-186`: ingestion `:121`, message digest calculation `:127`, format identification `:131`, replication `:140`, fixity check `:148`, migration `:168`, recovery `:174`, information package creation `:182`.
  - **Unidades del Agente** (`_agente_premis`, `app/servicios/paquete.py:289-295`): `agentIdentifier` `:291`, `agentName` `:292`, `agentType` `:293`, `agentVersion` `:294-295`.
  - **Unidades de Derechos** (`_derechos_premis`, `app/servicios/paquete.py:298-337`): `rightsStatementIdentifier` `:300`, `rightsBasis` `:301`, `statuteInformation` (jurisdicción, cita, nota) `:302-307`, `licenseInformation` `:308-312`, `copyrightInformation` `:313-317`, `otherRightsInformation` `:318-321`, `rightsGranted` (act disseminate/replicate, restriction, `termOfGrant` start/end, nota) `:324-336`, `linkingObjectIdentifier` `:337`.
  - Datos persistidos que alimentan PREMIS: `alembic/versions/0007_preservacion.py:22,42` (migraciones, verificaciones_integridad); `alembic/versions/0008_preservacion_oais.py:37,57,72` (segundas_copias, restauraciones, declaraciones_derechos); `app/models/preservacion.py:45-134`.
  - Validación contra el XSD oficial de la LoC en CI: `.github/workflows/deploy.yml` (paso «PREMIS contra el esquema oficial…», `scripts/validar_premis.py:14-29`). El anexo es `documentacion/anexos/aip-ejemplo/ricora-aip-062855ac-…/data/metadatos/premis.xml`: 8 eventos y agentes con `agentVersion`.
  - API: `app/routers/preservacion.py:242-253` (instanciación), `:256-269` (expediente).
  - Buscado «premis» en `app/routers` (fuera de preservacion), `app/servicios/exportacion_rico.py` y `frontend/src`: no hay ninguna ruta que entregue PREMIS fuera del AIP zip.
- Prueba automatizada: `tests/test_preservacion_oais.py::test_paquete_de_una_instanciacion_es_bagit_valido_con_premis_y_pdi` (afirma el orden y la presencia de object/event/agent/rights, la fijeza, el PUID, las dos `storage` y los tipos de evento).
- Razonamiento: las cuatro entidades existen como XML PREMIS 3.0 válido por instanciación, generadas con datos persistidos y no como resumen libre. No es un resumen parcial. Sin embargo:
  - PREMIS **no existe como registro propio**: se reconstruye en el momento de exportar, y la entidad Derechos solo aparece si alguien declaró derechos.
  - Las brechas de PRE-02, PRE-04 y PRE-06 hacen que el conjunto no sea completo en todos los casos.
  - `xsi:schemaLocation` apunta a `premis.xsd` (`paquete.py:58`), mientras que CI valida contra `premis-v3-0.xsd` (`scripts/validar_premis.py:14`). Funciona, pero conviene fijar la versión.
  - Solo se produce la categoría `file`. No hay objeto `representation` ni `intellectualEntity`; el prompt pide «archivo o representación», así que es aceptable.
- Acción recomendada: exponer el PREMIS de una instanciación por API (sin zip) y fijar `schemaLocation` a `premis-v3-0.xsd`. Las demás acciones están en PRE-02, PRE-04 y PRE-06.

### PRE-02 · Eventos PREMIS: fechas aproximadas, resultado sin vocabulario y eventos ausentes
- Rama: PREMIS
- Módulo(s): preservacion, ingesta
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/paquete.py:126-138` — «message digest calculation» y «format identification» llevan los dos `fecha_proceso = inst.procesado_en or inst.cargado_en`, es decir, la hora en que **terminó** toda la ingesta y no la de cada paso. El prompt §6 exige «fecha y hora exactas».
  - `app/servicios/paquete.py:121,127,131` — sus identificadores son `uuid5` derivados. Son estables, pero no hay fila de evento propia.
  - `app/servicios/paquete.py:123,151,162,176` — `eventOutcome` toma los valores «éxito», «fallo» o «en espera», en español y sin `authority`/`valueURI`. Los `eventType` sí usan los términos del vocabulario LoC, pero también sin URI.
  - Buscado `virus|clam|validation|jhove|verapdf` en `app/`: no hay eventos «virus check» ni «validation», porque esas capacidades no existen (ver PRE-09).
  - Buscado `OCR|texto` en `paquete.py`: la extracción de texto/OCR de la ingesta no genera ningún evento PREMIS.
  - `app/servicios/paquete.py:180-185` — «information package creation» se lee de `RegistroAuditoria` (`accion == "paquete_exportado"`).
- Prueba automatizada: `tests/test_preservacion_oais.py::test_paquete_de_una_instanciacion_es_bagit_valido_con_premis_y_pdi`. Comprueba que hay fecha y resultado, no que la fecha sea exacta.
- Razonamiento: la cadena de eventos cubre ingreso, huella, identificación, réplica, fijeza, migración, restauración y exportación, con agente y objeto enlazados. Hay tres fallos:
  - dos eventos comparten una fecha aproximada;
  - el resultado es texto libre en español, sin vocabulario controlado: otro sistema que reciba el AIP no podrá interpretar «éxito» como `success`;
  - faltan los pasos técnicos de la ingesta que sí ocurren (OCR) y los que una norma de fijeza/validación esperaría.
- Acción recomendada: guardar marcas de tiempo por paso en la ingesta (`huella_en`, `formato_identificado_en`); usar `eventOutcome` con el vocabulario LoC (`success`/`failure`) y atributos `authority`/`valueURI`; añadir el evento de extracción de texto/OCR y, cuando exista, el de validación.

### PRE-03 · Agente PREMIS de software = Mechanism del vocabulario con su versión
- Rama: PREMIS · RiC-CM (RiC-E13 Mechanism)
- Módulo(s): preservacion, vocabularios
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/mecanismos.py:118-122` — `agente_premis()` toma `id` = id de la `EntidadVocabulario`, `tipo` = «software» y `version` = `e.version`. El `agentIdentifierType` es «RICORA vocabulario».
  - `app/servicios/vocabulario.py:375-403` — `mecanismo()` es el servicio único: reutiliza el mecanismo por nombre normalizado y versión, o lo crea con `crear(... subtipo="mecanismo")` y lo registra en auditoría (`mecanismo_registrado`).
  - `app/servicios/preservacion.py:126` — la versión de Ghostscript se lee en tiempo de ejecución con `gs --version` (`_version`, `:157-161`). Pillow la toma de `PIL.__version__` (`:154`). En la migración, `:566-568` hace `m.mecanismo_id = mecanismos.obtener(..., hecho.programa, hecho.version, ...)`.
  - `app/servicios/mecanismos.py:88-105` — Siegfried va con la versión del programa más la de sus archivos de firmas PRONOM. `:40-43`: el propio sistema es «RICORA 2.0.0».
  - `app/servicios/paquete.py:86-95` — el agente sale del mecanismo vigente, siguiendo las fusiones. El respaldo `_agente_software()` (`:79-83`, `version: None`) solo se usa en filas anteriores a la migración 0013 que el trabajador aún no ha vinculado (`app/servicios/mecanismos.py:139-185`, llamado desde `app/trabajador.py:78`).
  - Columnas: `alembic/versions/0013_mecanismos_reutilizados.py:21-27` (`mecanismo_id` en instanciaciones, migraciones, verificaciones, segundas_copias y restauraciones).
- Prueba automatizada:
  - `tests/test_mecanismos.py::test_migracion_automatica_queda_vinculada_a_ghostscript_con_su_version_exacta` (compara con `gs --version` real);
  - `tests/test_mecanismos.py::test_un_mecanismo_ya_registrado_en_el_vocabulario_se_reutiliza`;
  - `tests/test_mecanismos.py::test_identificacion_verificacion_y_segunda_copia_apuntan_a_su_mecanismo`;
  - `tests/test_preservacion_oais.py::test_paquete_de_una_instanciacion_es_bagit_valido_con_premis_y_pdi`: todo agente `software` tiene `agentIdentifierType == "RICORA vocabulario"` y `agentVersion`.
- Razonamiento: es la prueba de profundidad aprobada. Dos migraciones con Ghostscript 10.02.1 terminan en el mismo registro controlado del vocabulario, no en dos textos libres. El agente PREMIS, la descripción y el RDF comparten identificador. Queda una salvedad menor: el respaldo textual para filas antiguas no tiene versión, pero es transitorio y lo cierra el trabajador.

### PRE-04 · Agente PREMIS de tipo persona: sale de la tabla de usuarios, no del vocabulario del fondo
- Rama: PREMIS · RiC-CM (Person)
- Módulo(s): preservacion, vocabularios, autenticacion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/paquete.py:98-102` — `_agente_persona()` usa `tipo_id = "RICORA usuario"` (`:64`), con id y nombre tomados de `Usuario`.
  - Buscado `agente|vocabulario` en `app/models/usuario.py`: sin resultado. No hay vínculo usuario ↔ agente persona del vocabulario.
  - El prompt del Módulo 5, §6 «Agente», exige que la persona quede «identificada por el agente de tipo persona ya existente en el vocabulario del fondo».
- Prueba automatizada: `tests/test_preservacion_oais.py::test_paquete_de_una_instanciacion_es_bagit_valido_con_premis_y_pdi`. Afirma `roles == {"authorizer": "RICORA usuario", ...}`, es decir, fija el comportamiento no conforme.
- Razonamiento: prueba de profundidad. La archivista que aprueba una migración y la misma persona registrada como agente (Person) en el vocabulario quedan con **dos identificadores distintos**: el UUID de la cuenta y el de la `EntidadVocabulario`. El grafo RiC y el PREMIS no se pueden unir por la persona. Además, el agente persona del AIP es una cuenta de acceso, que puede desactivarse o renombrarse, y no una autoridad archivística.
- Acción recomendada: añadir a `usuarios` un `agente_persona_id` hacia `entidades_vocabulario` (subtipo persona) y crearlo o reutilizarlo con `vocabulario` igual que los mecanismos. Emitir `agentIdentifierType = "RICORA vocabulario"` también para personas y actualizar la prueba.

### PRE-05 · Entidad Derechos de PREMIS (versión mínima, heredable)
- Rama: PREMIS · Ley 1712
- Módulo(s): preservacion
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/models/preservacion.py:118-134` (`declaraciones_derechos`) y `alembic/versions/0008_preservacion_oais.py:72`.
  - `app/servicios/derechos.py:63-77`: la declaración aplicable es la propia o se hereda hacia arriba hasta el fondo. `:80-104`: `declarar()` versiona (la anterior queda `vigente=False`) y audita.
  - `app/servicios/derechos.py:31-34` — el mapeo de `rightsBasis` sigue el vocabulario LoC; el acceso sigue la Ley 1712 (arts. 18 y 19).
  - `app/routers/preservacion.py:227` — `PUT /preservacion/derechos`.
  - `app/servicios/paquete.py:298-337` — se serializa a PREMIS.
- Prueba automatizada: `tests/test_preservacion_oais.py::test_derechos_se_heredan_y_la_declaracion_propia_prevalece` y `tests/test_preservacion_oais.py::test_paquete_de_una_instanciacion_es_bagit_valido_con_premis_y_pdi` (Statute, cita, disseminate/replicate).
- Razonamiento: cumple la «declaración básica» del §6 con base, tipo de restricción y fundamento. Base, acceso y reproducción son enumeraciones y no texto libre, así que dos archivistas terminan en el mismo valor controlado. El fundamento es texto libre, lo que el prompt acepta. Si no hay declaración, el paquete no lleva `rights`; está documentado en el `pdi.json` (`paquete.py:436-437`).

### PRE-06 · Los recortes (partes documentales) reciben un PREMIS falso: evento de «ingreso» y ninguna relación con su origen
- Rama: PREMIS · OAIS (Procedencia)
- Módulo(s): preservacion, descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/servicios/recorte.py:104-143` — el recorte es una `Instanciacion` nueva con `recorte_de_id=origen.id` (`:135`), sin `derivada_de_id` y generada con Pillow (`img.crop`, `:112-115`) sin mecanismo asociado a la operación.
  - `app/servicios/paquete.py:120-125` — si `derivada_de_id is None`, se emite el evento «ingestion» con el detalle «Ingreso del archivo … al fondo por el módulo de ingesta». Para un recorte, esa afirmación es falsa.
  - `app/servicios/paquete.py:257-266` — la `relationship` de derivación solo usa `derivada_de_id`. Buscado `recorte` en `app/servicios/paquete.py` y `app/servicios/preservacion.py`: sin resultado.
  - La segunda copia del recorte sí se crea: `app/routers/descripcion.py:195-203` y `alembic/versions/0012_descripcion_v3.py:28`.
- Prueba automatizada: ninguna encontrada. Buscado `recorte` junto a `premis|paquete|segunda` en `tests/`: sin resultado.
- Razonamiento: la categoría Procedencia del AIP de un recorte afirma un ingreso que no ocurrió y omite que es un derivado de otra instanciación, creado por una persona con un programa concreto. Es justo el tipo de error de procedencia que PREMIS y OAIS buscan evitar.
- Acción recomendada: en `eventos_de`, emitir para los recortes un evento `derivation` (o `creation`) con el autor y el mecanismo Pillow con su versión, y una `relationship` «derivation / has source» hacia `recorte_de_id`. Cubrirlo con una prueba.

### PRE-07 · Segunda copia: automática y verificada, pero no independiente del equipo
- Rama: OAIS (Almacenamiento de Archivo) · NDSA
- Módulo(s): preservacion, ingesta, descripcion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - **Qué la dispara**:
    - ingesta: `app/servicios/procesamiento.py:163-165` (`segunda_copia.asegurar(db, inst, "ingesta")`, dentro del trabajador);
    - migración: `app/servicios/preservacion.py:531`;
    - recorte: `app/routers/descripcion.py:195-203`;
    - relleno cada 60 s por el trabajador: `app/trabajador.py:73-77` → `app/servicios/preservacion.py:699-721`;
    - creación tardía durante una verificación: `app/servicios/preservacion.py:240-242`.
    - Ningún cron. Es el bucle del proceso `trabajador`.
  - **Creación segura**: `app/servicios/segunda_copia.py:101-134` copia a un temporal `.parcial`, calcula el hash, solo renombra si coincide con el de la ingesta y nunca borra (la anterior queda «reemplazada»).
  - **Verificación**: `app/servicios/preservacion.py:226-274` recalcula la primaria (`:233-237`) y la segunda (`:238-239`, `segunda_copia.comprobar` en `app/servicios/segunda_copia.py:89-98`) contra `inst.huella`. Hay alerta distinta `segunda_copia_alterada` (`:263-269`) frente a `integridad_alterada` (`:256-259`).
  - **Producción**: `docker-compose.yml` monta el volumen `segunda_copia` en `web` y `trabajador` (`RICORA_SEGUNDA_COPIA: ${RICORA_SEGUNDA_COPIA:-/data/segunda_copia}`) y declara el volumen con el comentario «en esta primera versión vive en el mismo disco del servidor». `Dockerfile` hace `mkdir -p /data/almacen /data/segunda_copia && chown -R ricora:ricora /data`. `.github/workflows/deploy.yml` hace `docker compose up --build -d --remove-orphans`, que levanta el trabajador; no define otro destino. Valor por defecto: `app/core/config.py:42-43`.
  - **Configurable**: `app/routers/preservacion.py:300-317` (solo administrador). `app/servicios/segunda_copia.py:41-45` excluye lugares dentro de la primaria; `:59-64` informa `mismo_disco_que_primaria`.
  - **Sin destino**: `app/servicios/segunda_copia.py:54-55` lanza un error y `:148-154` deja una alerta. No queda desactivada en silencio.
  - **Restauración desde la copia**: `app/servicios/preservacion.py:617-656` (con aprobación y cuarentena) y `app/routers/preservacion.py:199-211`.
  - Documentación del equipo (afirmación): `documentacion/modulo-5-preservacion.md:347,456`. Reconoce que la copia comparte disco. `:179` dice: «las dos alteradas → ninguna automática: hay que acudir a un respaldo externo», un respaldo que no existe (PRE-10).
- Prueba automatizada:
  - `tests/test_preservacion_oais.py::test_la_segunda_copia_se_crea_sola_en_la_ingesta`;
  - `::test_verificacion_integra_en_las_dos_copias_no_genera_alerta`;
  - `::test_alteracion_solo_de_la_segunda_copia_tiene_alerta_propia_y_se_rehace`;
  - `::test_alteracion_de_la_primaria_se_restaura_desde_la_segunda_copia`;
  - `::test_la_migracion_crea_la_segunda_copia_de_la_nueva`;
  - `::test_cambio_del_lugar_de_la_segunda_copia`.
- Razonamiento: lo que pide el prompt §8 al pie de la letra (creación automática, comparación de la segunda copia y alerta propia, lugar configurable y documentado) está hecho y opera en producción. Pero la independencia es solo lógica:
  - es otro volumen Docker en el mismo disco del mismo Droplet;
  - el mismo usuario `ricora` puede escribir en ambos volumes desde `web` y desde `trabajador`;
  - el mismo proceso verifica las dos copias contra un valor de referencia que vive en la misma base de datos sin respaldo.
  - La pérdida del disco o del servidor, o un error de la aplicación que escriba en ambos lugares, destruye las dos copias.
  - Además, «comparar primaria contra segunda» se hace por transitividad contra `inst.huella`: si ese valor de la BD se corrompe, se informan dos alteraciones en lugar de una discrepancia de metadatos.
- Acción recomendada: montar la segunda copia en un destino de otro equipo o almacenamiento de objetos, con credenciales distintas y, de ser posible, en solo-anexar o inmutable. Montarla en solo lectura en `web`. Guardar fuera de la BD un manifiesto de huellas (por ejemplo, un `manifest-sha256.txt` por fondo dentro de la segunda copia) para tener una referencia independiente.

### PRE-08 · Verificación de fijeza periódica
- Rama: NDSA (Integridad) · PREMIS (fixity check) · OAIS
- Módulo(s): preservacion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia:
  - `app/trabajador.py:69-72` — en cada vuelta del bucle llama a `preservacion.verificacion_periodica(db)`. `docker-compose.yml` define el servicio `trabajador` (`command: ["trabajador"]`, `restart: unless-stopped`). `docker-entrypoint.sh` hace `exec python -m app.trabajador`.
  - `app/servicios/preservacion.py:284-307` — corre si pasó la frecuencia. El valor por defecto es 30 días (`app/servicios/parametros.py:39`), configurable de 1 a 365 por el administrador (`app/routers/preservacion.py:300-317`).
  - `app/servicios/preservacion.py:292-298` — **marca la pasada como hecha antes de recorrer**. Si el trabajador se reinicia a mitad de camino, y `deploy.yml` lo reconstruye y recrea en cada push, las instanciaciones que faltaban **no se verifican hasta el siguiente periodo** (30 días).
  - `app/servicios/preservacion.py:392-394` — el panel solo muestra `ultima_verificacion`. Buscado `vencid|atrasad|overdue` en `app/servicios/preservacion.py` y `app/servicios/alertas.py`: no hay alerta si la verificación se atrasa o si el trabajador está caído.
  - Verificación manual: `app/routers/preservacion.py:128` (`POST …/verificar`).
  - Registro: `verificaciones_integridad` (`app/models/preservacion.py:45-61`).
- Prueba automatizada: `tests/test_preservacion.py::test_verificacion_periodica_respeta_la_frecuencia`, `tests/test_preservacion.py::test_archivo_alterado_queda_en_historial_y_alerta_alta`. No hay prueba del bucle de `app/trabajador.py` ni de la reanudación tras una interrupción.
- Razonamiento: código presente y operando (el servicio corre en producción). Pero la garantía «cada instanciación se verifica cada N días» no se cumple si hay despliegues o reinicios durante una pasada, y nadie se entera si el trabajador deja de correr. Para una tesis que argumenta NDSA nivel 3 de integridad, esto es una brecha real, no cosmética.
- Acción recomendada: verificar por antigüedad (`ultima_verificacion_en < ahora - N días`) en lotes, en lugar de por «pasada global». Crear una alerta «verificación periódica atrasada» cuando `max(ultima_verificacion_en)` supere N + margen. Probar el reinicio.

### PRE-09 · Validación formal de PDF/A (veraPDF) y TIFF (JHOVE)
- Rama: OAIS (Planificación de la Preservación) · PREMIS (evento validation) · NDSA (Contenido)
- Módulo(s): preservacion
- Clasificación: No implementado
- Evidencia:
  - Buscado `verapdf|jhove` (sin distinguir mayúsculas) en `app/`, `tests/`, `scripts/`, `Dockerfile`, `docker-compose.yml`, `.github/`, `frontend/src`, `alembic/`: **sin resultado**. Solo aparece en `documentacion/modulo-5-preservacion.md:343,466` como pendiente («La validación formal con veraPDF sigue pendiente»).
  - `Dockerfile` instala solo `tesseract-ocr tesseract-ocr-spa ghostscript` y Siegfried. No hay Java, veraPDF ni JHOVE.
  - **Lo que «valida» hoy un PDF/A**:
    - `app/servicios/preservacion.py:113-126`: Ghostscript convierte con `-dPDFA=2 -dPDFACompatibilityPolicy=1`. Esa política hace que Ghostscript **ignore lo que no puede cumplir y siga adelante**, no que falle.
    - `app/servicios/preservacion.py:505-508`: el resultado se acepta si Siegfried devuelve un PUID del conjunto `riesgo.PDFA`. Lo mismo en `app/cli.py:128-135` (`probar-preservacion`).
    - `app/servicios/riesgo.py:24,29-31`: cualquier archivo cuyo PUID esté en `{fmt/95, fmt/354, fmt/476…481}` se clasifica como **riesgo bajo**, «Es PDF/A (ISO 19005)…». Siegfried reconoce PDF/A por la declaración `pdfaid` del XMP, no por conformidad.
  - TIFF: `app/servicios/preservacion.py:138-154` (Pillow) y la misma aceptación por PUID en `:506`.
- Prueba automatizada: ninguna de validación. `tests/test_preservacion.py::test_migracion_soportada_crea_nueva_instanciacion_sin_tocar_la_original` solo comprueba la conversión y la identificación.
- Razonamiento: «documentado, no integrado». Un PDF que solo **declara** ser PDF/A en sus metadatos, venga de la ingesta o de una conversión degradada por `PDFACompatibilityPolicy=1`, queda marcado como de bajo riesgo, y su riesgo de obsolescencia se da por resuelto (`app/servicios/preservacion.py:313-323`) sin que nadie haya verificado ISO 19005. Lo mismo ocurre con la buena formación y validez de un TIFF.
- Acción recomendada: instalar veraPDF (CLI, con JRE headless) y JHOVE en la imagen. Invocarlos tras cada migración y en la ingesta de PDF/A y TIFF, y guardar el resultado como evento PREMIS `validation` con su mecanismo y versión. Condicionar el «riesgo bajo» de PDF/A a un informe veraPDF conforme. Usar `PDFACompatibilityPolicy=2` (abortar) o tratar el aviso como fallo.

### PRE-10 · Respaldo de la base de datos y simulacro de restauración
- Rama: OAIS (Gestión de Datos, Almacenamiento) · NDSA (Almacenamiento, Metadatos)
- Módulo(s): preservacion, auditoria
- Clasificación: No implementado
- Evidencia:
  - `app/routers/preservacion.py:118-119` — `# El respaldo probado de la base de datos (con simulacro de restauración) aún no existe en el sistema.` y `"simulacro_base_de_datos": None`. La prueba `tests/test_rediseno.py:157` fija ese `None`.
  - Buscado `pg_dump|pg_restore|pg_basebackup|backup|respaldo|simulacro|crontab|cron` en `app/`, `tests/`, `scripts/`, `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`, `deploy-ricora.sh`, `.github/`, `alembic/` y `Caddyfile`: ningún respaldo ni restauración de la BD. El único cron del repositorio es el que `deploy.yml` **retira** (`crontab -l | grep -v actualizar.sh`).
  - `docker-compose.yml` — la BD vive en el volumen `bd` del mismo servidor, sin servicio de respaldo.
  - `/home/user/Tesis/respaldo/` contiene `RICORA_Django_final_2026-09-30.zip` (la versión anterior de la aplicación) y archivos de prueba. No es un respaldo de la BD.
  - `alembic/versions/0014_hallazgos_y_versiones.py:74-80` — el propio hallazgo del equipo («…ni tenía respaldo verificado») sigue «en_correccion».
  - Documentación (afirmación): `documentacion/modulo-5-preservacion.md:465`: «un respaldo periódico de la base sigue siendo política del Plan, fuera de este módulo».
- Prueba automatizada: ninguna encontrada.
- Razonamiento: no existe ni el respaldo ni, mucho menos, una restauración probada. Es la brecha más grave del frente. Toda la descripción RiC, los vocabularios, la auditoría y **las huellas de referencia contra las que se verifica la fijeza** viven en un único volumen PostgreSQL del mismo disco que las dos copias de archivos. El AIP lleva metadatos consigo, pero solo se genera bajo demanda y se borra del servidor tras la descarga (`app/routers/preservacion.py:236-238`).
- Acción recomendada: añadir un servicio o tarea de `pg_dump -Fc` periódica hacia un destino externo, con su huella. Añadir un simulacro automático periódico que restaure el volcado en una BD efímera (`pg_restore` sobre un contenedor `postgres:16` temporal) y compruebe conteos y huellas de tablas clave, y registrar el resultado como evento visible en `eventos-recientes` (el campo ya existe). Cubrirlo con una prueba en CI.

### PRE-11 · OAIS: AIP en BagIt (instanciación y expediente) con PREMIS y PDI de cinco categorías
- Rama: OAIS · BagIt · PREMIS
- Módulo(s): preservacion, instrumentos
- Clasificación: Implementado y conforme
- Evidencia:
  - `app/servicios/paquete.py:459-470` — `_cerrar_bolsa()` escribe `manifest-sha256.txt` (`:461-462`), `bagit.txt` 1.0 (`:463`), `bag-info.txt` con `Bag-Software-Agent`, `Bagging-Date` y `Payload-Oxum` (`:464-467`) y `tagmanifest-sha256.txt` (`:468-470`).
  - `app/servicios/paquete.py:509-529` — `data/contenido/<archivo>` se verifica contra la huella de la ingesta antes de empaquetar (`:516-518`, un archivo alterado no se empaqueta). Le siguen `data/metadatos/premis.xml` y `data/metadatos/pdi.json`.
  - `app/servicios/paquete.py:374-440` — PDI con `referencia` `:396`, `contexto` (fondo, Record Resources con jerarquía y RiC-R025, derivaciones RiC-R015) `:402`, `procedencia` (cadena de eventos PREMIS) `:415`, `fijeza` (algoritmo, valor, estado de las dos copias, historial) `:425` y `derechos_de_acceso` `:433`, más la información de representación (PRONOM) `:386-393`.
  - Por expediente: `app/servicios/paquete.py:583-600` reúne las instanciaciones a cualquier profundidad, más sus migraciones. `:603-639` arma una carpeta por instanciación y `data/expediente.json`.
  - API y UI: `app/routers/preservacion.py:242-269`; botón en `frontend/src/pages/Instrumentos.tsx:194-196` y en `frontend/src/pages/InstanciacionPreservacion.tsx:488`.
  - Anexo real: `documentacion/anexos/aip-ejemplo/ricora-aip-062855ac-8ac9-4dc3-abca-e675fce6e96e/` (bagit.txt, bag-info.txt, manifest-sha256.txt, tagmanifest-sha256.txt, data/…), generado por `scripts/generar_anexo_aip.py`.
- Prueba automatizada:
  - `tests/test_preservacion_oais.py::test_paquete_de_una_instanciacion_es_bagit_valido_con_premis_y_pdi` (`bagit.Bag(...).validate()` de la LoC; un byte cambiado lo invalida);
  - `::test_paquete_del_expediente_incluye_todas_sus_instanciaciones`;
  - `::test_no_se_empaqueta_un_archivo_alterado`;
  - `::test_permisos_de_las_acciones_nuevas`.
- Razonamiento: la estructura de paquete de información (Contenido + PDI de cinco categorías) está poblada desde datos reales y validada con el validador oficial de BagIt. Salvedad, que no rompe el prompt porque este pide «bajo demanda»: el AIP es **efímero**. Se genera y se borra (`app/routers/preservacion.py:236-238`), así que el Almacenamiento de Archivo guarda archivos sueltos más la BD, no AIPs. Si se pierde la BD (PRE-10), no queda ningún AIP almacenado del que reconstruir.

### PRE-12 · OAIS: paquete de difusión (DIP)
- Rama: OAIS
- Módulo(s): preservacion, instrumentos
- Clasificación: No implementado
- Evidencia: buscado `\bDIP\b|paquete de (difusi|consulta|acceso)|dissemination` en `app/`, `tests/`, `frontend/src` y `documentacion/modulo-5-preservacion.md`: sin resultado, salvo el `act` PREMIS «disseminate» de `app/servicios/paquete.py:325`. La entidad Acceso se asigna al módulo 4 (`documentacion/modulo-5-preservacion.md:321`).
- Prueba automatizada: ninguna encontrada.
- Razonamiento: el prompt del Módulo 5 no exige un DIP, pero la consigna de auditoría sí pregunta por él. El acceso existe (instrumentos, catálogo, RDF, auditados en otro frente), pero no hay un paquete de difusión que derive del AIP ni que filtre la copia de uso según `rightsGranted`. Hoy solo el personal con rol en preservación puede descargar el AIP completo, archivo original incluido.
- Acción recomendada: si la tesis afirma la conformidad OAIS completa, definir el DIP como el producto de Instrumentos (PDF o RDF del catálogo público) más la copia de acceso, derivados del AIP y filtrados por la declaración de derechos, y documentarlo así. El SIP BagIt de la ingesta corresponde al frente de Ingesta.

### PRE-13 · NDSA Levels of Digital Preservation 2.0: nivel alcanzado por área
- Rama: NDSA
- Módulo(s): preservacion, ingesta, autenticacion, auditoria
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia: ver la tabla. Los niveles son acumulativos: un nivel solo cuenta si están cumplidos todos sus requisitos y los de los niveles inferiores.

| Área | Nivel alcanzado (acumulativo) | Cumplido (evidencia) | Lo que bloquea el nivel siguiente |
|---|---|---|---|
| **Almacenamiento** | **0 (nivel 1 parcial)** | Dos copias completas: `app/servicios/segunda_copia.py:101-134`, volumen `segunda_copia` en `docker-compose.yml`. Medios documentados: `documentacion/modulo-5-preservacion.md:347,456`. | N1 exige «dos copias completas **en ubicaciones separadas**»: aquí comparten disco y servidor (`app/servicios/segunda_copia.py:63-64` lo detecta). La BD no tiene ninguna copia (PRE-10). N2 (tres copias, una en otra ubicación geográfica) y N3/N4: no implementados. |
| **Integridad** | **0 (N1 parcial; N3 casi cumplido)** | Huella generada en la ingesta: `app/servicios/procesamiento.py:68-82`. Verificación al copiar: `app/servicios/segunda_copia.py:113-118`, `app/servicios/paquete.py:516-518`, `app/servicios/preservacion.py:638-640`. Verificación a intervalos fijos y a pedido, con registro: `app/servicios/preservacion.py:226-307`, `app/models/preservacion.py:45-61`. Reparación (N4): `app/servicios/preservacion.py:617-677`. | N1 exige antivirus y cuarentena: buscado `clam\|virus\|malware` en `app/`, `Dockerfile` y `docker-compose.yml`, sin resultado. N2 exige respaldar la información de integridad en un lugar separado: las huellas solo están en la BD, sin respaldo. N3: la pasada interrumpida no se reanuda (PRE-08). |
| **Control** | **3 (N4 no)** | Roles y permisos: `app/routers/preservacion.py:296,301` (`solo_administrador`), `Depends(modulo)` en el resto, `tests/test_preservacion.py::test_permisos_del_modulo` y `::test_configuracion_solo_administrador`. Registro de quién hizo qué (personas y mecanismos): `registrar(...)` en cada acción (`app/servicios/preservacion.py:270,551,583,646`), `mecanismo_id` en cada fila técnica. | N4 exige revisión periódica de los registros de acceso y acciones: no hay ninguna tarea ni informe periódico. A nivel de sistema operativo, `web` y `trabajador` escriben con el mismo uid en las dos copias (`Dockerfile`, `chown -R ricora /data`), sin separación de privilegios. |
| **Metadatos** | **0 (N2–N4 sustancialmente cumplidos)** | Inventario con ubicación: tablas `instanciaciones` y `segundas_copias`, `detalle()` `app/servicios/preservacion.py:443-444`. Metadatos administrativos, técnicos, descriptivos y de preservación: PREMIS y PDI (`app/servicios/paquete.py`). Norma elegida e implementada (PREMIS 3.0 validado contra el XSD en CI). Acciones de preservación con fecha (eventos PREMIS). | N1 exige «respaldar el inventario y guardar al menos una copia separada del contenido»: el inventario es la BD, sin respaldo (PRE-10), y los AIP no se guardan. |
| **Contenido** | **1 (N2 no)** | Formatos identificados con herramienta, versión y firmas: `app/servicios/formato.py`, `app/servicios/mecanismos.py:88-105`. Vigilancia de obsolescencia (N3): `app/servicios/riesgo.py`, `app/servicios/preservacion.py:326-349`. Migración (N4): `app/servicios/preservacion.py:535-611`. | N2 exige **verificar** formatos y características esenciales (validación): no hay veraPDF ni JHOVE (PRE-09). La tabla de riesgo es estática, codificada en `riesgo.py`, y no se alimenta de PRONOM ni de ningún registro externo. |

- Prueba automatizada: las citadas en cada fila. No hay ninguna prueba de NDSA como tal.
- Razonamiento: el sistema tiene muchas capacidades de nivel 3–4 (fijeza periódica, reparación desde copia, PREMIS, migración), pero con la regla acumulativa de NDSA se queda **en nivel 0 en Almacenamiento, Integridad y Metadatos**. La causa es la falta de requisitos básicos de nivel 1: ubicaciones separadas, antivirus y respaldo del inventario. No conviene que la tesis afirme «NDSA nivel 3» sin esta salvedad.
- Acción recomendada: priorizar por orden de coste/beneficio:
  1. respaldo externo de la BD con simulacro (PRE-10);
  2. segunda copia en otro equipo (PRE-07);
  3. ClamAV en la ingesta con evento PREMIS «virus check»;
  4. veraPDF/JHOVE (PRE-09);
  5. revisión periódica de la auditoría.

### PRE-14 · Compromisos del prompt de preservación: estado de cumplimiento
- Rama: OAIS · PREMIS
- Módulo(s): preservacion
- Clasificación: Implementado pero incompleto o no conforme
- Evidencia (compromiso → estado):
  - §6 Agente persona «identificado por el agente de tipo persona ya existente en el vocabulario del fondo» → **no cumplido** (PRE-04, `app/servicios/paquete.py:98-102`).
  - §6 Evento «fecha y hora exactas» → **incompleto** (PRE-02, `app/servicios/paquete.py:126-131`).
  - §7 Procedencia: «historia completa de custodia y de eventos técnicos» → **incompleto para recortes** (PRE-06) y para el OCR (PRE-02).
  - §8 La verificación periódica «compara la primaria contra la segunda copia» → cumplido por transitividad contra `inst.huella` (`app/servicios/preservacion.py:235,239`). No hay comparación directa entre las dos copias (PRE-07).
  - §9 «Verificación de integridad. Corre sola según la frecuencia configurable» → cumplido con un fallo de reanudación (PRE-08).
  - §5 tres decisiones con tabla → cumplido como documento (`documentacion/modulo-5-preservacion.md:341-347`; es afirmación del equipo y no se audita su calidad).
  - §10 API completa, incluidos `exportar-paquete` y la configuración de la segunda ubicación → cumplido (`app/routers/preservacion.py:82-317`).
  - §13 pruebas obligatorias → presentes. Migración sin aprobación: `tests/test_preservacion.py::test_ninguna_migracion_sin_aprobacion_explicita_y_auditada`. No soportada: `::test_migracion_no_soportada_espera_el_archivo_y_luego_lo_enlaza`. Configuración: `::test_configuracion_solo_administrador`. Mecanismo Ghostscript: `tests/test_mecanismos.py::test_migracion_automatica_queda_vinculada_a_ghostscript_con_su_version_exacta`. Paquete y expediente: PRE-11.
  - §14 AIP real conservado como anexo → cumplido (`documentacion/anexos/aip-ejemplo/…`, validado contra el XSD en `.github/workflows/deploy.yml`).
  - Fuera del prompt del módulo, pero exigidos por el prompt de auditoría §6: veraPDF/JHOVE (PRE-09) y simulacro de restauración de la BD (PRE-10) → **no implementados**.
- Prueba automatizada: las listadas arriba.
- Razonamiento: el módulo cumple la mayoría de sus compromisos con código y pruebas reales. Los incumplimientos son puntuales (agente persona, fechas exactas, procedencia de recortes), pero afectan precisamente a la «completitud» PREMIS que la auditoría pide verificar.
- Acción recomendada: las de PRE-02, PRE-04, PRE-06, PRE-08, PRE-09 y PRE-10.

---

## Tabla resumen

| ID | Título | Clasificación |
|---|---|---|
| PRE-01 | Las cuatro entidades PREMIS por instanciación: estructura, alcance y validación | Implementado pero incompleto o no conforme |
| PRE-02 | Eventos PREMIS: fechas aproximadas, resultado sin vocabulario y eventos ausentes | Implementado pero incompleto o no conforme |
| PRE-03 | Agente PREMIS de software = Mechanism del vocabulario con su versión | Implementado y conforme |
| PRE-04 | Agente PREMIS persona: sale de usuarios, no del vocabulario del fondo | Implementado pero incompleto o no conforme |
| PRE-05 | Entidad Derechos de PREMIS (mínima, heredable) | Implementado y conforme |
| PRE-06 | Recortes con PREMIS falso (evento de ingreso, sin relación con su origen) | Implementado pero incompleto o no conforme |
| PRE-07 | Segunda copia automática y verificada, pero en el mismo disco, servidor y usuario | Implementado pero incompleto o no conforme |
| PRE-08 | Fijeza periódica: real, pero la pasada interrumpida no se reanuda y no hay alerta de atraso | Implementado pero incompleto o no conforme |
| PRE-09 | Validación formal veraPDF / JHOVE | No implementado |
| PRE-10 | Respaldo de la base de datos y simulacro de restauración | No implementado |
| PRE-11 | AIP BagIt (instanciación y expediente) con PREMIS y PDI de cinco categorías | Implementado y conforme |
| PRE-12 | DIP (paquete de difusión) | No implementado |
| PRE-13 | NDSA 2.0 por área (Almacenamiento 0, Integridad 0, Control 3, Metadatos 0, Contenido 1) | Implementado pero incompleto o no conforme |
| PRE-14 | Compromisos del prompt de preservación: estado de cumplimiento | Implementado pero incompleto o no conforme |
