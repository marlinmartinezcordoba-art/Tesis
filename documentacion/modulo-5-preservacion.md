# Módulo 5 · Preservación digital

**Estado:** entregado, pendiente de validación.

---

## 1. Propósito

Vigilar el estado técnico de cada archivo del fondo y actuar cuando haga falta, sin tocar nunca la descripción archivística. El módulo cubre tres tareas:

- **Integridad:** recalcula la huella SHA-256 de cada archivo y la compara con la registrada en la ingesta. Lo hace sola, cada mes por defecto, y también cuando se le pide.
- **Riesgo de obsolescencia:** clasifica cada formato como bajo, medio o alto, con la razón y una recomendación.
- **Migración de formato:** siempre la aprueba una persona. Cada migración crea un archivo nuevo, enlazado al original, y el original no se toca.

## 2. Auditoría (qué se revisó antes de construirlo)

**Documentos revisados:**
- el prompt del módulo 5 (secciones 1 a 10);
- el diseño consolidado, Parte 6: OAIS, PREMIS, clasificación de riesgo, verificación mensual y migración a PDF/A y TIFF;
- lo que ya existía: huella SHA-256 y formato PRONOM con Siegfried desde la ingesta (módulo 1), el panel central de alertas y el catálogo del módulo 4, que ya mostraba «sin evaluar».

**Hallazgos:**

1. **La herramienta de identificación ya se había decidido en el módulo 1** (Siegfried frente a DROID y FIDO), con su tabla completa. Este módulo la **reutiliza**: el prompt prohíbe identificar otra vez desde cero. La tabla se repite en §19, ampliada con el uso nuevo: comprobar que el resultado de una migración es de verdad el formato pedido.
2. **La relación de migración ya estaba en el catálogo curado:** `migrated_into` (RiC-R015). Se verificó contra el catálogo oficial de RiC-CM 1.0.
3. **Contradicción entre documentos.** El diseño consolidado dice que la clasificación de riesgo «la ejecuta la inteligencia artificial». El prompt del módulo 5, que es más reciente y más concreto, no lo pide. **Se decidió no usar IA para esto** (ver §14 y §19). Queda a su validación.
4. **Faltaba dónde guardar el origen de una instanciación migrada.** Se agregó `instanciaciones.derivada_de_id`. Sin ese campo, el archivo convertido aparecería en «Por describir» como si fuera un documento nuevo.

## 3. Problema que resuelve

Un archivo digital se puede corromper sin que nadie lo note: fallas de disco, copias mal hechas, manipulación. Además, su formato puede quedar sin programas que lo lean. Un fondo histórico de valor permanente necesita saber, de forma verificable, que cada archivo sigue siendo el que ingresó, y tener una ruta para llevarlo a formatos de conservación.

## 4. Usuarios

| Rol | Qué hace |
|---|---|
| Archivista, responsable de preservación digital, administrador | Ve el panel, verifica la integridad, aprueba migraciones y carga archivos convertidos |
| Revisor, auditor, coordinador (solo lectura) | Ve el panel y las fichas técnicas |
| Administrador | Además, configura la frecuencia y la tabla de formatos soportados |
| Consulta | No accede al módulo. En el catálogo ve el estado de preservación como insignia de solo lectura |

## 5. Casos de uso

1. Ver el estado técnico del fondo: cuántos archivos están en buen estado, cuántos con alerta de integridad y cuántos con riesgo de formato.
2. Revisar la lista de archivos que requieren atención, lo más grave primero.
3. Abrir la ficha técnica de un archivo: formato PRONOM, tamaño, huella, ingreso, historial de verificaciones y de migraciones.
4. Verificar la integridad de un archivo en el momento.
5. Migrar un PDF a PDF/A-2b, o una imagen a TIFF, de forma automática, tras aprobarlo.
6. Pedir una migración a un formato no soportado, convertir el archivo por fuera y cargarlo.
7. (Administrador) Cambiar la frecuencia de verificación y ampliar la tabla de formatos soportados.
8. Ver en el catálogo (módulo 4) el estado de preservación de los archivos de una descripción.

## 6. Entidades RiC involucradas

Solo **Instantiation** (RiC-E06). El Record Resource no se lee para escribir, ni se modifica.

**Metadatos PREMIS anclados en la instanciación o en tablas relacionadas con ella:**

| PREMIS | Dónde |
|---|---|
| Formato (nombre, versión, registro PRONOM) | `instanciaciones.formato_*`, desde la ingesta |
| Tamaño | `instanciaciones.tamano_bytes` |
| Fixity (huella y algoritmo) | `instanciaciones.huella`, `algoritmo_huella` |
| Evento *fixity check* | tabla `verificaciones_integridad` (una fila por verificación) |
| Evento *migration* | tabla `migraciones` (aprobación, herramienta, resultado) |
| Agente del evento (persona o software) | `usuario_id` / `aprobada_por_id` y `herramienta` (por ejemplo «Ghostscript 10.02.1 (pdfwrite, PDF/A-2b, perfil sRGB)») |

## 7. Relaciones RiC involucradas

- **RiC-R015 *migrated into*** (`rico:migratedInto`): de la instanciación original a la nueva. Verificada en el catálogo oficial.
- **RiC-R025 *has or had instantiation***: del Record Resource de la original a la nueva. La descripción queda asociada a las dos versiones, **sin duplicarse ni alterarse**.

Si la original todavía no está descrita, la nueva queda enlazada solo por R015. Cuando se describa la original, **la publicación enlaza también sus versiones migradas** (ampliación en `servicios/descripcion.py`).

## 8. Funcionalidades

**Panel:**
- cuatro cifras (buen estado, alerta de integridad, riesgo de obsolescencia, total);
- lista «Requieren atención» con ícono de archivo, nombre, contexto archivístico, formato e insignia por tipo de riesgo, **ordenada por severidad**;
- fecha de la última verificación periódica y frecuencia vigente.

**Ficha técnica:**
- migas de pan hasta el Record Resource, que llevan al catálogo;
- pares clave–valor PREMIS;
- tarjeta de riesgo con razón y recomendación, o «mitigado» con enlace a la versión de conservación;
- tabla de verificaciones (fecha, resultado, periódica o manual y quién);
- historial de migraciones con enlace a cada resultado;
- botones «Verificar integridad ahora» y «Migrar formato».

**Migración:**
- selector de formato destino que muestra en vivo un panel **verde** (automática: qué herramienta, que se comprueba con PRONOM, que la original no se toca) o **ámbar** (solo se registra la solicitud);
- en el caso ámbar, después de aprobar aparece una zona de carga para el archivo convertido.

**Configuración (administrador):**
- frecuencia (semanal, quincenal, **mensual por defecto**, trimestral, semestral, anual);
- tabla de formatos soportados (origen, tipos MIME, destino, herramienta, activo o inactivo);
- «Agregar formato».

**Verificación periódica:** la hace el trabajador en segundo plano que ya existía.

**Autocomprobación en cada despliegue:** `python -m app.cli probar-preservacion` convierte un PDF de prueba a PDF/A y lo identifica. El registro de GitHub Actions dice si funciona en el servidor.

## 9. Flujos

**Verificación periódica:**
1. En cada vuelta, el trabajador revisa si ya pasó la frecuencia configurada.
2. Si pasó, marca el inicio y recalcula la huella de cada instanciación.
3. Registra cada resultado en el historial y en la auditoría.
4. Si una huella no coincide o falta el archivo, crea una **alerta de severidad alta** en el panel central.
5. No corrige nada por su cuenta.

**Migración automática (formato en la tabla):**
1. Ficha → «Migrar formato».
2. Se elige el destino y se ve el panel verde.
3. Se pulsa **«Aprobar migración»**, lo que queda en la auditoría como `migracion_aprobada`.
4. El sistema convierte **una copia** del archivo.
5. Siegfried comprueba que el resultado sea el formato pedido (por ejemplo `fmt/477`, PDF/A-2b).
6. Se crea la instanciación nueva, con sus enlaces R015 y R025.
7. Se registra `migracion_completada` y la alerta de riesgo de la original se cierra sola.

Si la conversión falla o el resultado no es el formato pedido, se registra `migracion_fallida` con el motivo. No queda ningún archivo a medias y la original sigue igual.

**Migración manual (formato no soportado):**
1. Se aprueba la migración, que queda registrada como «esperando el archivo convertido».
2. **No se crea ninguna instanciación todavía.**
3. La archivista convierte el archivo por fuera y lo sube en el historial.
4. Se identifica con PRONOM y se crea la instanciación enlazada.

## 10. Pantallas

| Pantalla | Ruta |
|---|---|
| Panel de preservación | `/preservacion` |
| Ficha técnica y migración | `/preservacion/instanciacion/:id` |
| Configuración (solo administrador) | `/preservacion/configuracion` |
| Insignia en la ficha del catálogo (módulo 4) | `/instrumentos?ficha=…` |

## 11. UX/UI

- **Colores con significado:**
  - verde: correcto o conversión automática;
  - ámbar: riesgo o solicitud manual;
  - rojo: alerta de integridad;
  - azul grisáceo: sin verificar.
- Las cifras del panel usan la tipografía serif.
- **Aprobar es un botón aparte y explícito.** Antes de pulsarlo, el panel dice qué va a pasar y repite que la original no cambia.
- **No se puede migrar un archivo con alerta de integridad:** el botón se desactiva y el servidor lo rechaza. Así no se «preserva» una versión corrupta.
- La huella se muestra completa, en letra de ancho fijo, para compararla a mano si hace falta.
- En móvil las cifras quedan en dos columnas y no hay desplazamiento horizontal (verificado a 390 px).

## 12. Modelo de datos

**Migración 0007:**

- Tabla `verificaciones_integridad`:
  - `instanciacion_id`, `fecha`;
  - `resultado`: íntegra / alterada / ausente;
  - `algoritmo`, `huella_registrada`, `huella_calculada`;
  - `origen`: periódica / manual;
  - `usuario_id`.
- Tabla `migraciones`:
  - `instanciacion_origen_id`, `destino`, `destino_nombre`;
  - `modo`: automática / manual;
  - `estado`: en curso / completada / fallida / esperando archivo;
  - `herramienta`, `mensaje`;
  - `aprobada_por_id`, `aprobada_en`, `terminada_en`;
  - `instanciacion_resultado_id`.
- En `instanciaciones`:
  - `estado_integridad`: sin verificar / íntegra / alterada / ausente;
  - `ultima_verificacion_en`;
  - `derivada_de_id`.
- En `parametros`:
  - `preservacion_frecuencia_dias` (30);
  - `preservacion_formatos` (la tabla de formatos soportados, validada);
  - `preservacion_ultima_verificacion` (uso interno).

**Nada se borra.** No hay ninguna ruta que elimine instanciaciones, verificaciones ni migraciones.

## 13. API

| Método y ruta | Permiso | Qué hace |
|---|---|---|
| `GET /api/preservacion/panel?fondo_id` | preservación: consultar | Resumen por riesgo y lista de atención |
| `GET /api/preservacion/instanciacion/{id}` | preservación: consultar | Ficha técnica, verificaciones, migraciones y destinos posibles |
| `POST /api/preservacion/instanciacion/{id}/verificar` | preservación: trabajar | Verificación manual |
| `POST /api/preservacion/instanciacion/{id}/migrar` | preservación: trabajar | `{destino, aprobada: true}`. Automática: devuelve la nueva instanciación. Manual: registra la solicitud |
| `POST /api/preservacion/instanciacion/{id}/migrar/cargar` | preservación: trabajar | Multipart `{migracion_id, archivo}` |
| `GET` / `PUT /api/preservacion/configuracion` | solo administrador | Frecuencia y tabla de formatos |

`aprobada: true` es obligatorio. Sin esa marca, la API responde 422 y no crea nada.

## 14. Uso de IA

**Ninguno.** La clasificación de riesgo es una **tabla de reglas** sobre el PUID y el tipo MIME (`servicios/riesgo.py`). Cada formato tiene su nivel, su razón escrita en lenguaje natural y su recomendación.

**Por qué no IA, aunque el diseño consolidado la menciona:**
- una clasificación de riesgo de conservación tiene que ser **reproducible y auditable**: el mismo formato debe dar siempre el mismo resultado, con una razón que se pueda citar;
- un modelo de lenguaje puede variar entre consultas y **no conoce mejor que PRONOM** el estado de un formato;
- además, enviar a un servicio externo la lista de archivos de un fondo no aporta nada.

La razón «legible, nunca una etiqueta sin argumento» que pide el diseño se cumple con el texto de la tabla. Si usted quiere la redacción por IA, se puede agregar encima **como explicación**, sin que decida el nivel.

## 15. Seguridad

- **Ninguna migración sin aprobación explícita.** El servidor exige `aprobada: true`, el usuario con permiso de escritura y su registro en la auditoría. La verificación periódica y el panel nunca migran nada (hay prueba de ello).
- **La original no se modifica ni se borra:**
  - se convierte una **copia** en una carpeta temporal;
  - después de migrar, el servidor comprueba que la huella de la original no cambió;
  - la prueba explícita compara la original **byte a byte** antes y después, incluso cuando la migración falla.
- **El resultado se comprueba:** si el conversor produce algo que Siegfried no reconoce como el formato pedido, la migración se marca fallida y el archivo se descarta. Lo mismo aplica a la carga manual.
- **Ghostscript con `-dSAFER`:** el PDF no puede leer ni escribir archivos del servidor, salvo el perfil de color permitido.
- El archivo cargado a mano pasa por el mismo almacenamiento seguro de la ingesta: nombre propio, sin rutas externas y límite de tamaño.
- La configuración es solo del administrador y cada cambio queda en la auditoría con el antes y el después.

## 16. Auditoría (qué queda registrado)

Todo se registra en el mismo registro de auditoría del sistema, que es de solo anexar.

| Acción | Qué guarda |
|---|---|
| `integridad_verificada` | Instanciación, resultado, periódica o manual, quién (o el sistema) |
| `migracion_aprobada` | Quién, cuándo, destino, modo e id de la migración |
| `migracion_completada` | Resultado, herramienta y formato PRONOM obtenido |
| `migracion_fallida` | Motivo |
| `parametro_cambiado` | Frecuencia o tabla de formatos, antes y después |
| Alertas `integridad_alterada` (alta) y `riesgo_obsolescencia` (media/baja) | En el panel central, el mismo del resto del sistema |

## 17. Interoperabilidad

- **PRONOM** (PUID) para formato origen y destino: lo entienden Archivematica, Preservica y DROID.
- **Destinos de conservación reconocidos:**
  - PDF/A-2b (ISO 19005-2);
  - TIFF sin pérdida;
  - PNG;
  - JPEG 2000;
  - ODT;
  - texto plano, CSV y XML.
- **La estructura sigue PREMIS** (objetos, eventos, agentes). La exportación en PREMIS XML o METS no la pide este prompt y queda como mejora.

## 18. Normativa aplicable

- **ISO 14721 (OAIS).** Este módulo cubre la Planificación de la Preservación (riesgo y migración) y la Gestión de Datos (historial de eventos). Se apoya en la Ingesta y el Almacenamiento del módulo 1.
- **PREMIS 3.0:** eventos *fixity check* y *migration*, con su agente.
- **ISO 19005-2 (PDF/A-2).**
- **Acuerdo 006 de 2014 del AGN** (Sistema Integrado de Conservación, componente de preservación digital) e **ISO 14641** (archivo electrónico).
- **Principio de no destructividad** del sistema.

## 19. Arquitectura

- **Servicios:**
  - `servicios/preservacion.py`: integridad, riesgo en alertas, panel, detalle y migración;
  - `servicios/riesgo.py`: tabla de riesgo.
- **Conversores en el código:** Ghostscript (PDF → PDF/A-2b con perfil sRGB incrustado) y Pillow (imagen → TIFF LZW sin pérdida).
- **Tabla de formatos en la base de datos:** qué origen se convierte con qué herramienta. Así se amplía sin tocar código.
- **Periodicidad:** el trabajador en segundo plano existente, igual que la detección del módulo 3.

### Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| **Herramienta de identificación de formato** (exigida por el prompt, §4; tomada en el módulo 1 y **reutilizada** aquí) | **DROID** 6.x (TNA, Java); **Siegfried** (Go, mismas firmas PRONOM, incluidas las de contenedor); FIDO (Python) | **Siegfried 1.11.9**, firmas DROID V125 | Mismo resultado PRONOM que DROID sin exigir Java (200–400 MB de memoria en un servidor de 2 GB). Un binario de 12 MB con salida JSON, fácil de invocar desde Python. Aquí además **valida el resultado de cada migración** (por ejemplo, que el PDF/A salga como `fmt/477`) | Es un binario externo, no una librería de Python: si falta, la migración falla con un mensaje claro y la ingesta deja el documento en error. Las firmas quedan fijas en la versión de la imagen |
| Conversión texto → PDF/A | **Ghostscript**; LibreOffice sin pantalla; ocrmypdf; conversor propio | **Ghostscript 10 (pdfwrite, PDF/A-2b, sRGB)** | Herramienta madura de código abierto, ~30 MB. El resultado se identifica como PDF/A-2b (`fmt/477`). LibreOffice suma ~500 MB a la imagen. El prompt pide no construir un conversor propio | Solo convierte PDF y PostScript. Los .doc o .docx a PDF/A van por la ruta manual. Ghostscript no valida PDF/A formalmente como veraPDF: la comprobación es la identificación PRONOM |
| Conversión imagen → TIFF | **Pillow**; ImageMagick; libvips | **Pillow** (ya instalado para el OCR) | Cero dependencias nuevas. TIFF con compresión LZW sin pérdida, todas las páginas, conservando la resolución | Formatos raros de cámara (RAW) no los lee; van por la ruta manual |
| Mecanismo periódico | Celery + Redis; cron; **trabajador existente** | **Trabajador existente**, marca de tiempo en `parametros` | La misma razón del módulo 3: no hace falta sumar Redis para una tarea mensual. Sobrevive a reinicios (la marca se guarda antes de recorrer) | Si el trabajador está detenido, no se verifica. Se nota porque la ingesta tampoco avanza, y el panel muestra la fecha de la última verificación |
| Clasificación de riesgo | IA (según el diseño consolidado); **tabla de reglas** | **Tabla de reglas** por PUID y MIME | Reproducible, auditable y con razón escrita. Ver §14 | Un formato nuevo sin regla sale «medio» con la razón «sin evaluación en la tabla». Se agrega en `riesgo.py` |
| Alertas de riesgo | Tabla propia; **panel central de alertas** | **Panel central** (el mismo de los módulos 1 y 4, como pide el prompt) | Un solo lugar para todo lo que requiere revisión humana. Se cierran solas cuando el riesgo queda mitigado | Un fondo con muchos PDF comunes genera muchas alertas de severidad baja. Es real: son archivos que conviene migrar |
| Archivo migrado de un documento aún sin describir | Mostrarlo en «Por describir»; **ocultarlo y enlazarlo al describir la original** | **`derivada_de_id`**: no aparece en la cola y hereda la descripción de su original | No se describen dos veces el mismo documento en dos formatos | Ninguno relevante |

## 20. Código (dónde vive, cómo se organiza)

```
alembic/versions/0007_preservacion.py          tablas y columnas nuevas
app/models/preservacion.py                     VerificacionIntegridad, Migracion
app/models/instanciacion.py                    estado_integridad, ultima_verificacion_en, derivada_de_id
app/servicios/riesgo.py                        tabla de riesgo de obsolescencia
app/servicios/preservacion.py                  integridad, periodicidad, alertas, panel, detalle, migración
app/servicios/parametros.py                    frecuencia y tabla de formatos (validada)
app/servicios/descripcion.py                   cola sin derivadas; publicar enlaza derivadas
app/servicios/instrumentos.py                  estado real de preservación en la ficha del catálogo
app/routers/preservacion.py                    /api/preservacion
app/trabajador.py                              verificación periódica
app/cli.py                                     probar-preservacion
frontend/src/pages/Preservacion.tsx            panel y configuración
frontend/src/pages/InstanciacionPreservacion.tsx   ficha técnica y migración
Dockerfile, .github/workflows/deploy.yml       Ghostscript en la imagen y en las pruebas
tests/test_preservacion.py
```

## 21. Pruebas

11 pruebas en `tests/test_preservacion.py` (132 en total en el proyecto, todas pasan). Usan **archivos reales pasados por la ingesta de verdad**, con Siegfried, Ghostscript y Pillow reales. Si falta una herramienta, las pruebas fallan: no se saltan.

- **Íntegra:** resultado íntegra, sin alerta, en el historial con quién la hizo.
- **Alterada:**
  - se agregan bytes al archivo en el disco y el resultado sale alterado, con las dos huellas distintas;
  - queda en el historial;
  - crea una alerta de severidad **alta**, primera en la lista del panel;
  - un archivo borrado sale como «ausente».
- **Periodicidad:**
  - corre la primera vez;
  - no corre si se acaba de hacer, ni a los 29 días y 23 horas con la frecuencia mensual;
  - sí corre a los 30 días y 1 minuto;
  - con frecuencia semanal no corre a los 6 días y sí a los 8.
- **Riesgo:**
  - un PDF 1.4 sale medio, con razón y destino sugerido;
  - un PNG sale bajo;
  - las cifras del panel son correctas;
  - la alerta aparece en `/api/alertas`, el mismo mecanismo del sistema.
- **Migración soportada (PDF → PDF/A-2b):**
  - el resultado es `fmt/477` según Siegfried;
  - está enlazado por R015 a la original y por R025 al mismo Record Resource, cuyo título no cambia;
  - la original sigue **igual byte a byte**;
  - el historial y el «riesgo mitigado» se ven;
  - la versión nueva no aparece en «Por describir»;
  - la alerta de riesgo se cierra sola.
- **Imagen → TIFF:** resultado TIFF y original intacta.
- **Migración no soportada:**
  - solo registra la solicitud, sin crear instanciación;
  - al cargar el archivo, se crea enlazada por R015 y R025;
  - la original está intacta;
  - una segunda carga para la misma solicitud responde 409.
- **Migración fallida** (conversor que produce algo que no es PDF/A):
  - estado fallida con motivo;
  - la original intacta;
  - ninguna instanciación nueva;
  - **ningún archivo huérfano** en el almacenamiento.
- **Sin aprobación, nada:**
  - `aprobada: false` responde 422 y no deja ninguna migración;
  - la verificación periódica y el panel no migran;
  - con aprobación, quedan en la auditoría `migracion_aprobada` (con el mismo usuario que la migración) y `migracion_completada`.
- **Configuración:**
  - archivista y revisor reciben 403 en GET y PUT;
  - el administrador cambia la frecuencia y agrega un formato;
  - un conversor que no produce ese destino se rechaza (422);
  - al desactivar PDF → PDF/A, esa migración pasa a ser manual.
- **Permisos:** sin sesión, 401; consulta, 403 en el panel; el revisor ve el panel pero recibe 403 al verificar y al migrar.

**Pruebas de mutación:**
- al quitar la exigencia de aprobación, falla la prueba de aprobación;
- al hacer que la conversión escriba sobre el archivo original, fallan tres pruebas.

**Verificación visual** en navegador real:
- panel;
- ficha;
- verificación manual;
- panel verde y ámbar;
- migración real a PDF/A;
- migración manual en espera con su zona de carga;
- configuración;
- insignia en el catálogo;
- móvil a 390 px;
- sin errores de JavaScript.

## 22. Criterios de aceptación

| Criterio (prompt §9–10) | Cumple |
|---|---|
| Verificación sin alteración: íntegra y sin alerta | ✓ |
| Alterada: queda en el historial y genera alerta de severidad alta | ✓ |
| La periódica corre según la frecuencia y no con otra | ✓ |
| Migración soportada: convierte, crea la nueva enlazada por migración y al mismo Record Resource, sin tocar la original | ✓ |
| No soportada: solo registra; sin instanciación hasta la carga; al cargar, bien enlazada | ✓ |
| Ninguna migración sin aprobación explícita registrada en la auditoría | ✓ |
| Los dos endpoints de configuración: error de permisos a quien no es administrador | ✓ |
| Prueba explícita de que ninguna original queda eliminada o modificada, cualquiera que sea el resultado | ✓ (byte a byte, también en migración fallida) |
| La decisión de §4 documentada con tabla completa | ✓ (§19) |

**Pendiente honesto:**

- **PDF/A sin validación formal.** El resultado se comprueba con la identificación PRONOM, no con un validador PDF/A como veraPDF, que es Java y pesado. Para la tesis, conviene validar con veraPDF una muestra de los PDF/A generados.
- **Archivos recién ingresados.** Quedan «sin verificar» hasta la siguiente pasada periódica, que puede tardar hasta un mes. La huella de referencia ya existe desde la ingesta. Se pueden verificar a mano en cualquier momento.
- **Ghostscript en el servidor.** Se instala en la imagen Docker. El despliegue imprime su versión y ejecuta `probar-preservacion`. Aquí se comprobó fuera de Docker.

## 23. Evidencia concreta de aplicación de RiC

Migración real hecha en la verificación visual:

```
Record «Oficio 114 de 1948 sobre el archivo municipal» (unidad documental)
  ─ rico:hasOrHadInstantiation (R025) → Instantiation «Oficio_114_1948.pdf»
  │      fmt/18 Acrobat PDF 1.4 · SHA-256 6b4cac35…450ecb · íntegra · riesgo medio (mitigado)
  │      ─ rico:migratedInto (R015) ↓
  └ rico:hasOrHadInstantiation (R025) → Instantiation «Oficio_114_1948 (PDF/A-2b).pdf»
         fmt/477 Acrobat PDF/A-2b · riesgo bajo · derivada_de = la original

Evento PREMIS (tabla migraciones): migración automática aprobada por Marlín Martínez,
  agente de software «Ghostscript 10.02.1 (pdfwrite, PDF/A-2b, perfil sRGB)», resultado completada.
```

La descripción del Record no cambió: ni una columna ni una relación suya se tocó. La original sigue en su lugar, con su huella intacta, y ahora tiene una versión de conservación enlazada. Eso es el principio de no destructividad aplicado a la preservación.
