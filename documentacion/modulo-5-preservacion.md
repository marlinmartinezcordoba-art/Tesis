# Módulo 5 · Preservación digital

**Versión:** 2 (actualizada según el prompt «Módulo 5, versión actualizada, profunda» y el Plan de Preservación Digital del sistema).
**Estado:** entregado, pendiente de validación.

**Qué cambió frente a la versión 1:**
- segunda copia automática de cada archivo, verificada aparte, con su alerta propia;
- restauración de la copia primaria desde la segunda copia (contingencia del plan);
- declaración básica de derechos (PREMIS Derechos), heredable por niveles;
- paquete de información de archivo (AIP) conforme a OAIS, en BagIt, con PREMIS 3.0 en XML y las cinco categorías de la PDI;
- exportación del paquete por archivo o por expediente completo;
- un AIP real conservado como anexo de la tesis.

---

## 1. Propósito

Vigilar el estado técnico de cada archivo del fondo, actuar cuando haga falta y dejar evidencia exportable de todo, sin tocar nunca la descripción archivística. Concretamente, el módulo:

- **Vigila la integridad.** Recalcula la huella SHA-256 de la copia primaria **y de la segunda copia**, y las compara con la registrada en la ingesta. Lo hace solo (cada mes por defecto) y a pedido.
- **Mantiene una segunda copia** de cada archivo en un segundo lugar de almacenamiento. Se crea sola al ingresar o al migrar.
- **Clasifica el riesgo de obsolescencia** de cada formato.
- **Migra formatos**, siempre con aprobación de una persona y sin tocar el original.
- **Produce bajo demanda el paquete de información de archivo (AIP)** de un archivo o de un expediente, conforme a OAIS y con sus metadatos PREMIS completos.

## 2. Auditoría (qué se revisó antes de construirlo)

**Documentos revisados:**
- el prompt actualizado del módulo 5 (secciones 1 a 14), que reemplaza las dos versiones anteriores;
- el *Plan de Preservación Digital del Sistema RiC* (docx): formatos, verificación mensual contra el valor de ingreso **y contra la segunda copia**, migración aprobada, segunda copia en ubicación independiente configurable, AIP con PDI y PREMIS, contingencia por restauración desde la segunda copia con auditoría, roles y revisión anual;
- lo construido en la versión 1 de este módulo y en los módulos 1 a 4.

**Brechas encontradas en la versión 1** (son las que el prompt pide cerrar):

1. **No había segunda copia.** Un archivo alterado se detectaba, pero no había de dónde recuperarlo. El Plan (Parte 8) exige restaurar desde la segunda copia.
2. **No se producía ningún paquete conforme a OAIS.** Los eventos PREMIS existían en tablas, pero no se exportaban.
3. **No había entidad Derechos.**
4. **La versión 1 documentó «PREMIS XML o METS» como mejora pendiente.** Ahora es obligatorio.

**Una corrección de códigos RiC hecha durante este trabajo:** el expediente es **Record Set = RiC-E03**, no E04 (E04 es Record). Se verificó contra el PDF oficial de RiC-CM 1.0 antes de escribirlo en el paquete.

## 3. Problema que resuelve

Un archivo digital se puede corromper o perder sin que nadie lo note. Saberlo no basta: hace falta poder **recuperarlo**, y poder **demostrar ante un tercero** qué se custodia, desde cuándo, qué se le hizo, quién lo hizo y con qué herramienta.

Esa demostración no puede depender de que alguien abra el sistema. Tiene que viajar con el archivo, en un formato que cualquier archivo digital del mundo pueda leer. Eso es el paquete de información de archivo (AIP) con PREMIS.

## 4. Usuarios

| Rol | Qué hace |
|---|---|
| Archivista, responsable de preservación digital, administrador | Ve el panel, verifica, aprueba migraciones, carga convertidos, restaura, rehace segundas copias, declara derechos y exporta paquetes |
| Revisor, auditor, coordinador (solo lectura) | Ve el panel y las fichas técnicas. No exporta ni modifica |
| Administrador | Además, configura la frecuencia, la tabla de formatos y **el lugar de la segunda copia** |
| Consulta | No accede al módulo |

## 5. Casos de uso

1. Ver el estado técnico del fondo: buen estado, alerta de integridad, **alerta de segunda copia**, riesgo de formato.
2. Abrir la ficha técnica de un archivo con todos los campos del Objeto PREMIS, incluida la fila de estado de la segunda copia.
3. Verificar a mano la integridad de la primaria y de la segunda copia.
4. Migrar un formato (automática o con carga manual).
5. **Restaurar** la copia primaria alterada o perdida desde la segunda copia.
6. **Rehacer** la segunda copia alterada o perdida desde la primaria.
7. **Declarar derechos** sobre un archivo o sobre cualquier nivel (documento, expediente… fondo).
8. **Exportar el paquete de preservación** de un archivo (desde su ficha) o de un expediente completo (desde el catálogo de Instrumentos).
9. (Administrador) Cambiar la frecuencia, la tabla de formatos y el lugar de la segunda copia.

## 6. Entidades RiC involucradas

Solo **Instantiation** (RiC-E06): toda la metadata de preservación es PREMIS anclada en ella.

El Record Resource se **lee** para dos cosas:
- armar el **Contexto** del paquete: qué Record (RiC-E04) describe el archivo, en qué Record Set (RiC-E03) está y en qué fondo;
- aplicar los **derechos** heredados.

Nunca se modifica.

**Correspondencia PREMIS 3.0 ↔ sistema:**

| Conjunto PREMIS | Unidad semántica | De dónde sale |
|---|---|---|
| **Objeto** | objectIdentifier | UUID de la instanciación |
| | categoría | `premis:file` |
| | fixity (algoritmo declarado y valor) | `instanciaciones.algoritmo_huella`, `huella` |
| | size | `tamano_bytes` |
| | format (nombre, versión, registro PRONOM) | `formato_*` (Siegfried, en la ingesta) |
| | creatingApplication | la herramienta de la migración que lo produjo, si la hubo |
| | originalName | `nombre_original` |
| | storage ×2 | ruta de la copia primaria y de la segunda copia, con su estado |
| | relationship | *derivation*: *has source* / *is source of* (migraciones) |
| **Evento** | ingestion, message digest calculation, format identification | datos de la ingesta |
| | replication | tabla `segundas_copias` |
| | fixity check | `verificaciones_integridad` (primaria y segunda copia) |
| | migration | `migraciones` |
| | recovery | `restauraciones` |
| | information package creation | registro de auditoría `paquete_exportado` |
| **Agente** | person | el usuario que actuó |
| | software | RICORA, Siegfried con su versión de firmas, Ghostscript, Pillow |
| **Derechos** | rightsStatement | `declaraciones_derechos`: base, fundamento, actos permitidos o negados |

Los roles de agente quedan explícitos: *implementer*, *authorizer* (quien aprueba una migración o una restauración) y *executing program*. Así se lee en el registro **cuándo actuó una persona y cuándo el sistema solo**.

## 7. Relaciones RiC involucradas

- **RiC-R015 *migrated into*** (`rico:migratedInto`): original → migrada. Va en la PDI (Contexto) y en PREMIS (*derivation*).
- **RiC-R025 *has or had instantiation*** (`rico:hasOrHadInstantiation`): Record → instanciación. Es la base del Contexto del paquete.
- **RiC-R024 *includes*** (jerarquía `incluido_en_id`): fondo › serie › expediente › documento. Sirve para el Contexto y para heredar los derechos.

## 8. Funcionalidades

**Panel:**
- cinco cifras: buen estado, alerta de integridad, **alerta de segunda copia**, riesgo de obsolescencia y total;
- lista «Requieren atención», lo más grave primero;
- aviso de cuántos archivos esperan todavía su segunda copia.

**Ficha técnica (PREMIS · Objeto):**
- identificador, categoría, nombre original, formato PRONOM, tipo MIME, herramienta de identificación, tamaño, huella;
- **aplicación creadora**;
- **ruta de la copia primaria**;
- **fila de la segunda copia** con insignia (sincronizada, alterada, perdida o pendiente), ruta y fecha de su última verificación;
- **historial de verificaciones con dos columnas**: copia primaria y segunda copia;
- **tarjeta Derechos**: declaración vigente, de dónde se hereda, y formulario para declarar una nueva;
- **tarjeta de contingencia** (solo cuando aplica): «Restaurar desde la segunda copia» o «Rehacer la segunda copia», con un segundo clic de aprobación;
- historial de restauraciones y de migraciones;
- botones **Verificar integridad ahora**, **Exportar paquete de preservación** y **Migrar formato**.

**Catálogo de Instrumentos:** en un expediente, botón **«Exportar paquete de preservación»**. Solo lo ve quien tiene permiso de trabajar en Preservación.

**Configuración (administrador), tres tarjetas:**
- frecuencia de verificación;
- formatos soportados;
- **segundo lugar de almacenamiento**: lugares declarados en el servidor, espacio libre, si comparte disco con la primaria, el que está en uso y el botón «Cambiar el lugar».

**Trabajador en segundo plano:**
- cada minuto crea las segundas copias que falten, de a 20: archivos anteriores a esta versión, o un cambio del lugar configurado;
- cada mes, la verificación periódica de las dos copias.

## 9. Flujos

**Ingesta → segunda copia (automática):**
1. Al terminar el procesamiento (huella, PRONOM, texto), el sistema copia el archivo al segundo lugar.
2. La copia se escribe con un nombre temporal y se le calcula la huella.
3. **Solo si la huella coincide con la de la ingesta**, recibe su nombre definitivo. Queda el evento *replication*.
4. Si no se puede crear, queda la alerta «segunda copia» y la ingesta termina igual.

**Migración → segunda copia de la nueva:** la instanciación nueva recibe su propia segunda copia de la misma forma. La de la original no cambia.

**Verificación (periódica o manual):**
1. El sistema recalcula la huella de la primaria y la de la segunda copia, y compara las dos con la de la ingesta (y, por tanto, entre sí).
2. Según lo que encuentre:

| Copia primaria | Segunda copia | Alerta | Acción disponible |
|---|---|---|---|
| íntegra | íntegra | ninguna | — |
| alterada o ausente | íntegra | **integridad_alterada** (alta), que dice que se puede restaurar | Restaurar |
| íntegra | alterada o ausente | **segunda_copia_alterada** (alta), distinta de la anterior | Rehacer la segunda copia |
| alterada | alterada | las dos | Ninguna automática: hay que acudir a un respaldo externo |

3. Si aún no hay segunda copia y la primaria está íntegra, la crea en ese momento.
4. No corrige nada sin una persona.

**Restauración (contingencia, Plan Parte 8):**
1. La tarjeta roja ofrece «Restaurar desde la segunda copia». Pide un segundo clic: «Sí, apruebo…».
2. El servidor vuelve a comprobar que la segunda copia esté íntegra.
3. **Aparta** el archivo dañado a `.cuarentena/` (no lo borra).
4. Copia la segunda copia a la ruta primaria y comprueba la huella.
5. Registra el evento *recovery* y la auditoría `copia_primaria_restaurada`.
6. Verifica de nuevo y cierra la alerta.

**Rehacer la segunda copia:** la copia dañada queda «reemplazada», con su archivo intacto. Se crea una nueva desde la primaria íntegra y se cierra la alerta.

**Exportación del paquete:**
1. Se registra la auditoría `paquete_exportado`. Ese registro se convierte en el evento PREMIS *information package creation* **dentro del mismo paquete**.
2. Se copia el archivo a una carpeta de trabajo y **se comprueba su huella**. Un archivo alterado no se empaqueta: el sistema responde 409 y pide restaurarlo primero.
3. Se escriben `premis.xml`, `pdi.json` y `LEEME.txt`, más los manifiestos BagIt.
4. Se comprime y se entrega. Al terminar la descarga, la carpeta temporal se borra.
5. **Expediente:** una carpeta por instanciación (de todos sus documentos, a cualquier profundidad, más las migraciones de cada uno) y un `expediente.json` de índice.

## 10. Pantallas

| Pantalla | Ruta |
|---|---|
| Panel de preservación | `/preservacion` |
| Ficha técnica, contingencia, derechos, migración y exportación | `/preservacion/instanciacion/:id` |
| Configuración (tres tarjetas, solo administrador) | `/preservacion/configuracion` |
| Exportación por expediente | `/instrumentos?nodo=<expediente>` |

## 11. UX/UI

- **Verde** íntegra o sincronizada; **ámbar** riesgo o pendiente; **rojo** alerta de integridad o de segunda copia; azul grisáceo sin verificar o reemplazada.
- **Las dos alertas no se confunden.** Tienen textos distintos («Alerta de integridad» y «Alerta de segunda copia»), cifras separadas en el panel y una explicación distinta en la ficha.
- **Las acciones irreversibles piden dos clics**: el botón y luego «Sí, apruebo…». Antes de pulsar, la tarjeta dice qué pasará con el archivo dañado: se aparta, no se borra.
- **El aviso de una verificación cambia de color** si la segunda copia falló aunque la primaria esté bien.
- **La configuración no permite escribir rutas.** Solo se elige entre los lugares declarados en el servidor, y se dice con claridad si un lugar comparte disco con la primaria.
- Verificado en navegador real a 1280 px y a 390 px de ancho, sin desplazamiento horizontal.

## 12. Modelo de datos

**Migración 0008** (reversible; probada subir, bajar y subir otra vez):

- Tabla `segundas_copias`:
  - `instanciacion_id`, `ubicacion` (raíz en el momento de crearla), `ruta`;
  - `algoritmo`, `huella` (calculada sobre la copia ya escrita), `tamano_bytes`;
  - `motivo`: ingesta / migración / reposición / cambio de ubicación / pendiente;
  - `estado`: sincronizada / alterada / ausente / reemplazada;
  - `creada_en`, `creada_por_id` (vacío: la creó el sistema), `ultima_verificacion_en`, `reemplazada_en`.
- Tabla `restauraciones`:
  - `instanciacion_id`, `segunda_copia_id`, `fecha`, `usuario_id`;
  - `estado_previo`, `huella_previa`, `ruta_cuarentena`.
- Tabla `declaraciones_derechos`:
  - `fondo_id`, `entidad_tipo` (instanciación o Record Resource), `entidad_id`;
  - `base`: estatuto / licencia / derecho de autor / política institucional / otra;
  - `acceso`: público / clasificado / reservado (Ley 1712 de 2014, arts. 18 y 19);
  - `reproduccion`: permitida / condicionada / no permitida;
  - `fundamento`, `nota`, `vigente_hasta`;
  - `vigente`, `creada_en`, `creada_por_id`, `reemplazada_en`.
- En `verificaciones_integridad`: `segunda_copia_id`, `segunda_copia_resultado` (íntegra / alterada / ausente / sin copia), `segunda_copia_huella`.
- En `parametros`: `preservacion_segunda_ubicacion`, validado contra los lugares declarados.
- Tipo de alerta nuevo: `segunda_copia_alterada`.

**Nada se borra:**
- una segunda copia reemplazada conserva su archivo;
- una declaración de derechos reemplazada queda con `vigente = false`;
- un archivo primario dañado se aparta a la cuarentena.

## 13. API

| Método y ruta | Permiso | Qué hace |
|---|---|---|
| `GET /api/preservacion/panel?fondo_id` | preservación: consultar | Resumen (con alerta de segunda copia) y lista de atención |
| `GET /api/preservacion/instanciacion/{id}` | preservación: consultar | Ficha PREMIS, **estado de la segunda copia**, derechos, verificaciones, restauraciones y migraciones |
| `POST …/instanciacion/{id}/verificar` | preservación: trabajar | Verifica la primaria y la segunda copia; devuelve los dos resultados |
| `POST …/instanciacion/{id}/migrar` | preservación: trabajar | Sin cambios de contrato. Ahora la nueva instanciación también recibe su segunda copia |
| `POST …/instanciacion/{id}/migrar/cargar` | preservación: trabajar | Sin cambios de contrato |
| `POST …/instanciacion/{id}/restaurar` | preservación: trabajar | `{aprobada: true}`. Restaura la primaria desde la segunda copia |
| `POST …/instanciacion/{id}/segunda-copia/reponer` | preservación: trabajar | `{aprobada: true}`. Rehace la segunda copia |
| `PUT /api/preservacion/derechos` | preservación: trabajar | Declara derechos sobre una instanciación o un Record Resource |
| **`POST …/instanciacion/{id}/exportar-paquete`** | preservación: trabajar | AIP de una instanciación (`.zip` con la bolsa BagIt) |
| **`POST /api/preservacion/expediente/{record_resource_id}/exportar-paquete`** | preservación: trabajar | AIP consolidado del expediente. 422 si no es un expediente, 404 si no existe o no tiene archivos |
| `GET` / `PUT /api/preservacion/configuracion` | **solo administrador** | Ahora también `segunda_copia` (lugar en uso, lugares declarados, espacio, pendientes) y `segunda_ubicacion` en el PUT |

## 14. Uso de IA

**Ninguno en este módulo.** El riesgo se clasifica con la tabla de reglas de la versión 1. El paquete se arma con datos que el sistema ya registró. No se envía nada a ningún servicio externo.

## 15. Seguridad

- **Nada sin aprobación.** Migrar, restaurar y rehacer exigen `aprobada: true`, permiso de escritura y quedan en la auditoría. La verificación periódica y el trabajador no restauran ni rehacen nada.
- **Nunca se replica un archivo alterado.** La segunda copia solo se acepta si su huella coincide con la de la ingesta.
- **Nunca se empaqueta un archivo alterado.** La huella se comprueba sobre la copia que entra al paquete. Si no coincide: 409 y ningún evento de exportación.
- **El administrador no puede escribir rutas desde la web.** Elige entre los lugares que declaró quien opera el servidor (`RICORA_SEGUNDA_COPIA`). Los que caen dentro del almacenamiento primario se descartan, porque no serían una segunda copia. Así nadie puede usar la configuración para escribir en cualquier parte del disco.
- **Las rutas de las copias se validan** para que no salgan de su raíz, igual que en la ingesta.
- **El ZIP no lleva rutas absolutas ni `..`** (lo comprueba una prueba). Los nombres de archivo se sanean.
- **Los temporales del paquete se borran** al terminar la descarga (lo comprueba una prueba).
- **El paquete incluye el archivo completo.** Es una exportación para custodia, no para consulta pública, y por eso exige permiso de trabajar en Preservación. Hay que tenerlo en cuenta con documentos clasificados o reservados.
- **Se mantiene la advertencia general:** no cargar documentos con reserva legal mientras el servidor no tenga HTTPS.

## 16. Auditoría (qué queda registrado)

| Acción | Qué guarda |
|---|---|
| `integridad_verificada` | Resultado de la primaria **y de la segunda copia**, periódica o manual, quién |
| `segunda_copia_creada` | Lugar, motivo, a cuál reemplaza. Vacío en `usuario_id` cuando la creó el sistema |
| `copia_primaria_restaurada` | Antes (estado y huella del dañado) y después (de qué copia, dónde quedó la cuarentena) |
| `derechos_declarados` | Antes y después (acceso y fundamento) |
| `paquete_exportado` | Alcance (instanciación o expediente), convención y versión PREMIS. Uno por cada instanciación incluida |
| `migracion_aprobada`, `migracion_completada`, `migracion_fallida` | Como en la versión 1 |
| `parametro_cambiado` | Frecuencia, tabla de formatos o lugar de la segunda copia, antes y después |

Las acciones nuevas tienen nombre legible en el panel de Auditoría. Dos de ellas suman grupos nuevos al consolidado semanal: «Restauraciones» y «Paquetes de preservación».

## 17. Interoperabilidad

- **BagIt 1.0 (RFC 8493).** Cualquier herramienta lo valida. Las pruebas usan el validador de la Library of Congress (`bagit-python`). Archivematica, Preservica, APTrust y DPN aceptan bolsas BagIt.
- **PREMIS 3.0 en XML**, con el espacio de nombres oficial. **La integración continua valida en cada cambio el PREMIS producido, y el del anexo, contra el esquema oficial de la Library of Congress** (`scripts/validar_premis.py`, que descarga `premis-v3-0.xsd`).
- **PRONOM** (PUID) con enlace a su ficha en el registro, como Información de Representación.
- **RiC-O** en la PDI (`rico:hasOrHadInstantiation`, `rico:migratedInto`, `rico:RecordSet`). La exportación RDF completa sigue fuera de este módulo, como dice el prompt (§11).

## 18. Normativa aplicable

**ISO 14721:2012 (OAIS).** Así cubre el sistema completo sus seis entidades funcionales (prompt §2):

| Entidad funcional OAIS | Dónde la cubre el sistema |
|---|---|
| **Ingesta** | Módulo 1: recepción, primer registro del formato (PRONOM), primera huella; aquí se suma la segunda copia |
| **Almacenamiento de Archivo** | Este módulo: copia primaria + **segunda copia** verificadas, restauración, AIP |
| **Gestión de Datos** | La base de datos completa: descripción y vocabularios (módulos 2 y 3) y metadatos técnicos PREMIS (este módulo) |
| **Administración** | Autenticación y autorización, configuración de este módulo y del de instrumentos, auditoría |
| **Planificación de la Preservación** | Tabla de formatos soportados y tabla de riesgo de este módulo; fuera del sistema, el Plan de Preservación Digital como política |
| **Acceso** | Módulo 4 (instrumentos, catálogo, grafo) y, en el futuro, la exportación RDF |

**Otras normas:**
- **PREMIS 3.0:** los cuatro conjuntos de información.
- **BagIt (RFC 8493).**
- **Ley 594 de 2000** (art. 27, acceso a documentos) y **Ley 1712 de 2014** (arts. 18 y 19, información clasificada y reservada): base del acceso en la declaración de derechos.
- **Acuerdo 006 de 2014 del AGN** (Sistema Integrado de Conservación, componente de preservación digital).

## 19. Arquitectura

- `servicios/segunda_copia.py`: lugares, copia con verificación previa, estado.
- `servicios/preservacion.py`: verificación dual, restauración, reposición, copias pendientes.
- `servicios/derechos.py`: declaración y herencia.
- `servicios/paquete.py`: eventos y agentes, PREMIS XML, PDI, BagIt, exportación individual y por expediente.

### Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| **Herramienta de identificación de formato** (prompt §5, primera) | **DROID** 6.x (The National Archives, Java, interfaz gráfica y línea de órdenes); **Siegfried** (Go, mismas firmas PRONOM de DROID, incluidas las de contenedor); FIDO (Python, firmas propias derivadas de PRONOM) | **Siegfried 1.11.9**, firmas DROID V125 y de contenedor 2026-01 | Da el **mismo resultado PRONOM que DROID**, porque usa sus mismos archivos de firmas. No exige una máquina Java, que pesa 200–400 MB de memoria en un servidor de 2 GB. Es un binario de 12 MB con salida JSON, fácil de invocar desde Python y de fijar en la imagen. Deja en cada identificación su versión y la de las firmas: es el agente *software* del evento PREMIS *format identification*. Además **valida el resultado de cada migración** (por ejemplo, que el PDF/A salga como `fmt/477`). DROID es la referencia institucional, pero su peso no se justifica en un sistema académico de un solo fondo | Es un binario externo: si falta, la ingesta deja el documento en error con un mensaje claro y la migración falla sin tocar nada. Las firmas quedan fijas en la versión de la imagen y se actualizan al reconstruirla. Siegfried no tiene interfaz gráfica, pero aquí no hace falta |
| **Empaquetado del AIP** (prompt §5, segunda) | **BagIt 1.0** (RFC 8493): carpeta `data/` + manifiestos de huellas + `bag-info.txt`; **METS** (Library of Congress): un XML que describe la estructura, con PREMIS embebido en `amdSec`; METS dentro de BagIt (como hace Archivematica) | **BagIt 1.0**, con PREMIS 3.0 en XML y la PDI en JSON dentro de `data/metadatos/` | Para **un solo fondo académico**, BagIt da lo esencial: fijeza verificable de cada archivo con cualquier validador, estándar IETF, implementación de unas 40 líneas sin dependencias nuevas y validación automática en las pruebas con la herramienta de la Library of Congress. METS es más expresivo (mapas estructurales, varias representaciones, perfiles), pero su valor aparece con objetos complejos (libros digitalizados página a página, colecciones de miles de objetos) y exige elegir o redactar un perfil, más un validador de esquema y de perfil. Aquí cada instanciación es un solo archivo: METS describiría con mucha más complejidad lo mismo que el manifiesto BagIt. La estructura OAIS (Información de Contenido + PDI con sus cinco categorías) se respeta explícitamente en las carpetas y en `pdi.json` | Un sistema de destino que exija METS (por ejemplo, un archivo nacional con perfil propio) necesitaría una transformación. La mitigación natural es la de Archivematica: un `METS.xml` dentro de la misma bolsa. Es aditivo y no rompe lo que hay |
| **Segundo lugar de almacenamiento** (prompt §8 y §14) | Otra carpeta del mismo volumen; **volumen Docker propio** en el mismo servidor; un Volume de bloques de DigitalOcean (pago); almacenamiento de objetos S3 o Spaces (pago); un segundo servidor | **Volumen Docker propio `segunda_copia`** montado en `/data/segunda_copia`, declarado con `RICORA_SEGUNDA_COPIA` y elegido por el administrador entre los lugares declarados | Sin costo, como exige el proyecto. Separa la segunda copia del almacenamiento primario a nivel de volumen: protege de **borrados accidentales, corrupción de archivos y errores de software** sobre la carpeta primaria, que son los incidentes más comunes. Queda **configurable**: en producción se monta otro disco o un servidor de archivos (NFS, SMB) en una ruta, se declara en `RICORA_SEGUNDA_COPIA` y se elige en la pantalla. Las copias se crean solas en el lugar nuevo y las del anterior se conservan | **En esta primera versión vive en el mismo disco físico del Droplet.** No protege de la pérdida del disco ni del servidor. La pantalla de configuración lo dice («mismo disco que la primaria»). El Plan de Preservación debe exigir, para producción real, un lugar en otro equipo, más un respaldo externo periódico de la base de datos |
| Serialización de la PDI | XML propio; PREMIS para todo; **JSON con las cinco categorías como claves** | **JSON** (`pdi.json`) junto a `premis.xml` | La PDI de OAIS no tiene esquema normativo propio: es un modelo de información. Lo verificable de procedencia y fijeza ya va en PREMIS XML validado. El JSON hace explícitas las cinco categorías con sus nombres (lo pide el prompt §7), es legible por personas y por programas, y lleva el contexto RiC (jerarquía, R025, R015) que PREMIS no modela | No es un estándar de intercambio. Si un destino lo exige, el contexto RiC saldrá de la exportación RDF (fuera de este módulo) |
| Alcance de los derechos | Solo por instanciación; solo por fondo; **por instanciación o por cualquier nivel, heredado hacia abajo** | **Herencia por niveles**: aplica la declaración propia o la del nivel más cercano hacia arriba | Es como trabaja el archivista: el acceso se decide por fondo o por serie y se exceptúa un expediente o un documento. Con una declaración en el fondo, todos los paquetes tienen su entidad Derechos | No es un gestor de derechos de autor (el prompt §11 lo excluye). Las fechas de vigencia se registran pero no se hacen cumplir solas |
| Restauración | Automática al detectar la alteración; **con aprobación de una persona** | **Con aprobación** y cuarentena del dañado | Coherente con «no corrige nada sola». Una alteración puede ser legítima (por ejemplo, una restauración externa) y merece una mirada humana. El dañado se conserva como evidencia | Entre la alerta y la aprobación, la primaria sigue alterada. Mitigación: la alerta es de severidad alta y aparece primera en el panel |
| Momento del AIP | Generarlo y guardarlo en cada cambio; **bajo demanda**; exportación periódica programada | **Bajo demanda** (por archivo o expediente), siempre desde el estado actual | Un AIP guardado en el servidor quedaría viejo en el siguiente evento y duplicaría el almacenamiento. Generado al pedirlo, siempre está al día y lleva su propio evento de creación | El Plan (Parte 8) puede fijar como política una **exportación periódica** a un medio externo. Se haría con el mismo código, y se deja como mejora |
| Validación de PREMIS | Ninguna; comprobación estructural propia; **esquema oficial XSD** | **Las dos**: estructural en las pruebas (sin red) y **XSD oficial en la integración continua** | El entorno de desarrollo no tiene acceso a loc.gov; GitHub Actions sí. Así cada cambio que llega al servidor produce un PREMIS válido según la Library of Congress | Si loc.gov no responde, ese paso falla y detiene el despliegue. Es preferible a desplegar sin validar |

## 20. Código (dónde vive, cómo se organiza)

```
alembic/versions/0008_preservacion_oais.py      segundas copias, restauraciones, derechos
app/models/preservacion.py                      + SegundaCopia, Restauracion, DeclaracionDerechos
app/servicios/segunda_copia.py                  lugares, copia verificada, estado
app/servicios/preservacion.py                   verificación dual, restaurar, reponer, pendientes
app/servicios/derechos.py                       declaración y herencia
app/servicios/paquete.py                        PREMIS XML, PDI, BagIt, exportaciones
app/servicios/procesamiento.py                  segunda copia al terminar la ingesta
app/servicios/parametros.py                     preservacion_segunda_ubicacion (validado)
app/servicios/trazabilidad.py                   nombres de las acciones nuevas
app/routers/preservacion.py                     restaurar, reponer, derechos, exportar, configuración
app/trabajador.py                               segundas copias pendientes cada minuto
frontend/src/pages/InstanciacionPreservacion.tsx   ficha PREMIS, contingencia, derechos, exportar
frontend/src/pages/Preservacion.tsx             panel (cinco cifras) y tercera tarjeta de configuración
frontend/src/pages/Instrumentos.tsx             exportar paquete del expediente
Dockerfile, docker-compose.yml                  volumen segunda_copia
scripts/validar_premis.py                       PREMIS contra el XSD oficial (integración continua)
scripts/generar_anexo_aip.py                    produce el anexo de la tesis
tests/test_preservacion_oais.py                 11 pruebas nuevas
documentacion/anexos/aip-ejemplo/               el AIP real (zip y carpeta)
```

## 21. Pruebas

**158 pruebas en el proyecto, todas pasan.** Son 11 nuevas en `tests/test_preservacion_oais.py` y las 11 de la versión 1 siguen pasando. Usan archivos reales, la ingesta real (Siegfried), migraciones reales (Ghostscript) y el validador BagIt de la Library of Congress.

**Prueba por prueba, según el prompt §13:**

| Prueba | Qué comprueba |
|---|---|
| La segunda copia se crea sola en la ingesta | Está en el lugar configurado, fuera del almacenamiento primario, es igual byte a byte, tiene su evento y fue creada por el sistema |
| Verificación íntegra en las dos copias | Ninguna alerta |
| Alteración solo de la segunda copia | Primaria íntegra; segunda alterada; **solo** la alerta `segunda_copia_alterada`; cifra propia en el panel. Rehacer sin aprobación responde 422; con aprobación la copia dañada queda reemplazada y conservada, y la alerta se cierra. Una segunda copia borrada sale «ausente» con su alerta |
| Alteración de la primaria | Alerta `integridad_alterada` que ofrece restaurar, y ninguna de segunda copia. Restaurar sin aprobación responde 422; con aprobación la primaria vuelve byte a byte y **el dañado está en la cuarentena con su contenido alterado**. Alerta cerrada, auditoría registrada. Restaurar sin alerta responde 409 |
| La migración crea la segunda copia de la nueva | La de la original no cambia |
| Cambio del lugar | Rechaza `/tmp` y la carpeta primaria (422). El trabajador crea la copia en el lugar nuevo; la anterior queda reemplazada **y su archivo existe** |
| Derechos | Herencia del fondo; prevalece el expediente; la declaración propia prevalece sobre todas; la reemplazada no se borra; una entidad inexistente da 404 |
| **Paquete de una instanciación** | **BagIt válido según `bagit-python`**. Contenido igual byte a byte. PREMIS en el orden objeto → eventos → agentes → derechos. Objeto con identificador, SHA-256, tamaño, PUID, nombre original, **dos almacenamientos** y relación de derivación. Siete tipos de evento, cada uno con fecha, resultado, agente y objeto; la migración con *authorizer* (persona) y *executing program* (software) y con los objetos *source* y *outcome*. Los eventos enlazados por el objeto son exactamente los presentes. Agentes persona y software (Siegfried, Ghostscript). Derechos *Statute* con su cita y sus actos. PDI con las **cinco categorías en orden**, jerarquía fondo → serie → expediente → documento, R025, migrada a, procedencia igual a los eventos PREMIS, fijeza con la segunda copia. **Un byte cambiado invalida la bolsa**, y no quedan temporales |
| Paquete del expediente | Incluye las instanciaciones de sus documentos **y la migración aún no publicada**, pero no la de otro expediente. Cada carpeta tiene contenido, PREMIS y PDI; la huella de cada archivo coincide con el índice; un evento de auditoría por instanciación. Un fondo responde 422 y un id inexistente 404 |
| No se empaqueta un archivo alterado | 409 y ningún evento de exportación |
| Permisos de las acciones nuevas | El revisor recibe 403 en exportar (las dos), restaurar, reponer y derechos; sin sesión, 401. La configuración del lugar da 403 al archivista |

**Pruebas de mutación** (se rompe el código a propósito y se comprueba que alguna prueba falle):

| Mutación | Resultado |
|---|---|
| No crear la segunda copia en la ingesta | Detectada |
| No alertar la segunda copia alterada | Detectada |
| No crear la segunda copia en la migración | Detectada |
| Omitir los Derechos en PREMIS | Detectada |
| Omitir una instanciación del expediente | Detectada |
| Borrar el archivo dañado al restaurar (en vez de apartarlo) | Detectada |

**Verificación visual** en navegador real:
- ficha con la segunda copia alterada: insignia roja, aviso rojo, tarjeta de contingencia;
- «Rehacer» con doble clic: la insignia vuelve a «sincronizada»;
- descarga del paquete individual y del expediente desde el catálogo;
- configuración con la tercera tarjeta;
- móvil a 390 px sin desplazamiento horizontal.

## 22. Criterios de aceptación

| Criterio (prompt §13–14) | Cumple |
|---|---|
| Verificación sin alteración: íntegra y sin alerta | ✓ |
| Primaria alterada: su alerta. Solo la segunda copia alterada: alerta distinta y específica | ✓ |
| Segunda copia automática al registrar una instanciación, por ingesta y por migración | ✓ |
| Migración soportada: conversión, nueva enlazada, su propia segunda copia, original intacta | ✓ |
| No soportada: solo registra hasta la carga | ✓ (sin cambios, sigue pasando) |
| Ninguna migración sin aprobación registrada en la auditoría | ✓ |
| AIP de una instanciación válido según la convención, con el original, los 4 conjuntos PREMIS y las 5 categorías de la PDI | ✓ |
| AIP del expediente con todas sus instanciaciones, sin omitir ninguna | ✓ |
| Configuración: error de permisos a quien no es administrador | ✓ |
| Las dos decisiones de §5 documentadas con tabla completa | ✓ (§19) |
| Segundo lugar de almacenamiento documentado en la Definición de Terminado | ✓ (§19 y abajo) |
| Un AIP real del fondo de prueba conservado como anexo | ✓ (§23) |

**Definición de Terminado: el segundo lugar de almacenamiento.** En esta primera versión es el **volumen Docker `segunda_copia`**, montado en `/data/segunda_copia` en los contenedores `web` y `trabajador`. Está separado del volumen `almacen` de la copia primaria, pero en el mismo disco del servidor. Es configurable sin tocar código:
1. quien opera el servidor monta otro disco o un servidor de archivos;
2. lo declara en `RICORA_SEGUNDA_COPIA` (varios lugares, separados por «:»);
3. el administrador lo elige en Preservación › Configuración;
4. el trabajador crea allí las copias de todo el fondo.

**Pendiente honesto:**

- **La segunda copia no es todavía independiente del disco.** Para la sustentación, conviene decirlo así: «protege de la alteración y del borrado de archivos, no de la pérdida del servidor». La independencia física es una decisión de infraestructura, con costo, que el sistema ya soporta.
- **La base de datos no tiene segunda copia.** Los metadatos viven en PostgreSQL. El AIP los lleva consigo, pero un respaldo periódico de la base sigue siendo política del Plan, fuera de este módulo.
- **PDF/A sin validación formal con veraPDF** (como en la versión 1).
- **Anexo generado en el entorno de desarrollo.** Tiene el mismo código, la misma versión de Siegfried y la misma estructura de carpetas que el servidor. Ghostscript es 10.02.1 aquí y 10.05.1 en el servidor. En el servidor se obtiene uno igual con un clic en «Exportar paquete de preservación».
- **Validación contra el esquema PREMIS oficial: hecha.** En el entorno de desarrollo loc.gov está bloqueado, así que corre en GitHub Actions. En la ejecución del commit 40ea1e6, el PREMIS producido por las pruebas y el del anexo salieron **válidos** contra `premis-v3-0.xsd`. El despliegue confirmó Ghostscript 10.05.1 → `fmt/477` en el servidor.

## 23. Evidencia concreta de aplicación de RiC

**El anexo** está en `documentacion/anexos/aip-ejemplo/`. Contiene el `.zip` tal como lo entrega el sistema y la carpeta descomprimida para leerlo en GitHub. Lo produjo `scripts/generar_anexo_aip.py` sobre el fondo de prueba, recorriendo el ciclo completo:

1. ingesta real (SHA-256, Siegfried/PRONOM y texto);
2. segunda copia automática;
3. descripción: fondo › serie › expediente › documento;
4. derechos declarados en el fondo;
5. verificación manual;
6. migración aprobada a PDF/A-2b con Ghostscript;
7. verificación periódica;
8. exportación.

Estructura del paquete:

```
ricora-aip-<uuid>/                                  BagIt 1.0 válido (bagit-python, Library of Congress)
├── bagit.txt · bag-info.txt (Payload-Oxum, External-Identifier urn:uuid:…)
├── manifest-sha256.txt · tagmanifest-sha256.txt
└── data/
    ├── LEEME.txt
    ├── contenido/Oficio 114 de 1948.pdf             Información de Contenido (fmt/18, SHA-256 6b4cac35…450ecb)
    └── metadatos/
        ├── premis.xml                               1 Objeto · 8 Eventos · 4 Agentes · 1 Derechos
        └── pdi.json                                 Referencia · Contexto · Procedencia · Fijeza · Derechos de acceso
```

**Lo que dicen los metadatos del anexo:**

```
Objeto      urn:uuid:…  premis:file  fmt/18 «Acrobat PDF 1.4»  71 071 bytes  SHA-256 6b4cac35…450ecb
            storage: copia primaria /data/almacen/…  ·  segunda copia /data/segunda_copia/… (sincronizada)
            relationship: derivation / is source of → la versión PDF/A-2b (fmt/477)
Eventos     ingestion → message digest calculation → format identification → replication
            → fixity check (manual: primaria íntegra, segunda copia íntegra) → migration (authorizer: persona;
              executing program: Ghostscript; source → outcome) → fixity check (periódica) → information package creation
Agentes     person «Archivista del fondo de prueba» · software RICORA · software siegfried 1.11.9 (firmas V125)
            · software Ghostscript (pdfwrite, PDF/A-2b, perfil sRGB)
Derechos    Statute · co · «Ley 594 de 2000, art. 27; Ley 1712 de 2014, art. 4» · disseminate Allow · replicate Allow
Contexto    Fondo CO.AM › Serie CO.AM.01 › Expediente CO.AM.01.003 (Record Set, RiC-E03)
            › Documento CO.AM.01.003.114 (Record, RiC-E04) ─ rico:hasOrHadInstantiation (R025) → esta Instantiation (RiC-E06)
            ─ rico:migratedInto (R015) → «Oficio 114 de 1948 (PDF/A-2b).pdf»
```

**Cómo usarlo en la sustentación:**
- se puede validar en vivo con `bagit.py --validate` sobre la carpeta;
- se puede abrir `premis.xml` y seguir la cadena de custodia de un archivo, desde su ingreso hasta su paquete, sin abrir el sistema.

Ese es el argumento de conformidad OAIS: **la evidencia viaja con el objeto**.
