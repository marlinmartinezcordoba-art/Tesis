# Módulo 4 · Generación de instrumentos de descripción

**Estado:** entregado, pendiente de validación.

---

## 1. Propósito

Ofrecer la consulta del fondo ya descrito, navegable por su jerarquía y por el grafo de entidades. Desde ahí se generan los instrumentos archivísticos derivados, sin construir nada a mano:

- **inventario documental** sobre el Formato Único de Inventario Documental (FUID) del AGN, en hoja de cálculo;
- **guía del fondo**, con nota de presentación redactada por el motor y editable, en documento de texto;
- **índice de términos**, en pantalla.

## 2. Auditoría (qué se revisó antes de construirlo)

**Documentos revisados:**

- el prompt del módulo 4 (secciones 1 a 10);
- el diseño consolidado, Parte 5 (catálogo, inventario, guía, índice);
- el mockup «Sistema RIC · Instrumentos»: pestañas Catálogo / Inventario / Guía / Índice; tabla con N.º, Código, Unidad documental, Fechas extremas, Folios, Caja, Soporte; celdas «pendiente · falta dato»;
- lo construido en los módulos 2 y 3: la ficha pública con lista cerrada de campos, el vocabulario con conteo de conexiones y el panel central de alertas del módulo 1.

**Hallazgo que obligó a ampliar el módulo 2:** el FUID exige código, caja, carpeta, folios y soporte, y **en la base de datos no había dónde guardar esos datos.** Sin ese cambio, el inventario habría salido con todas esas columnas pendientes para siempre. Se agregaron cinco campos de control a la descripción (migración 0006) y se hicieron editables en «Descripción › Corregir». El módulo 4 sigue sin escribir sobre el grafo: esos datos los escribe una persona en descripción.

**Hallazgo sobre las fechas:** el FUID pide fecha inicial y final. No se agregó un campo nuevo: se **calculan** a partir de las fechas de creación (RiC-R080) ya validadas en cada descripción. En un expediente o una serie, las fechas extremas son la más antigua y la más reciente de lo que contiene.

**Dependencia pendiente:** el prompt pide mostrar el estado de preservación «tal como lo mantiene el módulo 5», que todavía no existe. La ficha muestra hoy **«Preservación: sin evaluar»** junto con lo que dejó la ingesta: formato PRONOM y huella SHA-256. Cuando exista el módulo 5, el estado lo pondrá él.

**Colores:** se mantiene la paleta de tonos medios de RICORA, por decisión de la autora, en lugar del terracota del prompt.

## 3. Problema que resuelve

Un inventario FUID o una guía de fondo se elaboran hoy a mano, copiando datos que ya existen en la descripción. Eso cuesta semanas y produce errores de transcripción. Aquí los instrumentos salen de la misma fuente validada. Si la descripción está incompleta, el instrumento sale igual, marcando exactamente qué falta.

## 4. Usuarios

| Rol | Qué hace |
|---|---|
| Consulta (investigador), revisor, auditor | Navega el catálogo, abre fichas y consulta el índice |
| Archivista, coordinador, descriptor, administrador | Todo lo anterior, y además genera y exporta el inventario y la guía |

**Permisos:**

- la consulta exige «catálogo: consultar», que tienen todos los roles base;
- la generación exige «instrumentos: trabajar».

## 5. Casos de uso

1. Recorrer el fondo nivel por nivel, con migas de pan: fondo › sección › serie › subserie › expediente › unidad documental.
2. Abrir la ficha de una unidad o expediente y saltar a cualquier entidad relacionada (vocabulario), viendo cuántos documentos del fondo la comparten.
3. Ver el estado de preservación de la instanciación (solo lectura).
4. Generar el inventario FUID desde el nivel donde se está (fondo, serie, expediente…), revisar los pendientes y exportarlo a Excel.
5. Pedir al motor el borrador de la nota de presentación de la guía, corregirlo y exportarlo a Word.
6. Consultar el índice de agentes, lugares y formas documentales, en orden alfabético.
7. Completar los datos que faltan (caja, folios…) desde la descripción y volver a generar. La alerta se cierra sola.

## 6. Entidades RiC involucradas

**Record Resource** (RiC-E02):

- Record Set en fondo, sección, serie, subserie y expediente;
- Record en la unidad documental.

**Instantiation** (RiC-E06), con su formato (identificado con PRONOM) y su huella.

**Del vocabulario:**

- Agent (E07) y subtipos;
- Place (E22);
- Documentary form type (A17);
- Date (E18), para las fechas extremas.

**Atributos nuevos en el Record Resource (datos de control):**

| Campo | ISAD(G) | RiC-CM |
|---|---|---|
| Código de referencia | 3.1.1 | RiC-A22 Identifier |
| Folios | 3.1.5 Volumen | RiC-A35 Record Resource Extent |
| Soporte | 3.1.5 Soporte | RiC-A05 Carrier Type, que en RiC es atributo de la instanciación física (el original en papel). Se guarda en la descripción como dato de control del FUID, porque esa instanciación física no se modela todavía |
| Caja, carpeta | — | Ubicación física de la unidad de conservación (datos de control del FUID) |

## 7. Relaciones RiC involucradas

Este módulo **no crea ni modifica relaciones**. Las recorre:

- **includes / is included in** (RiC-R024): arma el árbol y las migas de pan;
- **is creation date of** (RiC-R080): da las fechas extremas;
- **has creator** (R027), **has sender** (R031), **has addressee** (R032), **has or had subject** (R019): se muestran en la ficha como «Producido por», «Remitido por», «Dirigido a», «Trata de»;
- **has or had instantiation** (R025): lleva a la instanciación y su preservación.

## 8. Funcionalidades

**Catálogo:**

- migas de pan;
- listado del nivel actual con tipo de nivel, título, código, fechas extremas y número de unidades documentales;
- ficha en panel superpuesto con:
  - encabezado e insignia de preservación en la esquina;
  - pares clave–valor;
  - cada entidad como enlace vivo con «· N documentos de esta entidad».

**Inventario:**

- vista previa de la tabla FUID;
- celdas pendientes en ámbar, en cursiva, con la insignia «falta dato»;
- barra inferior con el conteo de pendientes, el aviso de alerta y «Exportar a Excel»;
- el título de cada renglón enlaza a su descripción para completarla.

**Guía:**

- borrador del motor a partir solo de datos validados;
- área de texto de ancho completo;
- «Exportar a Word» arriba a la derecha;
- sin motor, arma un borrador básico con los mismos datos y avisa.

**Índice:**

- agrupado por tipo (Agentes, Lugares, Formas documentales);
- con letra inicial en serif;
- orden alfabético que ignora tildes y mayúsculas;
- cada entrada enlaza a su detalle en vocabularios.

**Alerta de pendientes:** una por nivel inventariado, con el conteo de la última generación. Se actualiza al regenerar y se cierra sola cuando ya no hay pendientes.

## 9. Flujos

**Inventario:**

1. Catálogo → navegar hasta el nivel deseado.
2. Pestaña Inventario: «Armar inventario de «…»».
3. El servidor arma los renglones y cuenta los pendientes. Si hay, crea o actualiza la alerta **antes** de mostrar la tabla.
4. La barra dice «2 campos pendientes · se generó una alerta en el panel central».
5. «Exportar a Excel»: el archivo sale igual, con las celdas marcadas. Queda en auditoría.

**Regla de renglones:**

- **un renglón por unidad documental**;
- **un renglón por expediente** solo cuando el expediente se describió como un todo, sin unidades documentales publicadas dentro, como pide el prompt.

**Guía:**

1. Pestaña Guía: «Redactar borrador».
2. El motor recibe solo datos validados: títulos, alcance de los niveles superiores, conteos, fechas extremas y los agentes, lugares y formas más citados.
3. La archivista edita libremente.
4. «Exportar a Word» envía **el texto tal como está en pantalla**. El servidor no lo vuelve a pedir al motor.

## 10. Pantallas

| Pantalla | Ruta |
|---|---|
| Catálogo (con ficha superpuesta) | `/instrumentos`, `?nodo=…`, `?ficha=…` |
| Inventario | `/instrumentos?vista=inventario&nodo=…` |
| Guía | `/instrumentos?vista=guia` |
| Índice | `/instrumentos?vista=indice` |
| Datos de control (ampliación del módulo 2) | `/descripcion/registro/:id` › Corregir |

El nivel y la ficha abiertos quedan en la dirección: se pueden compartir o volver a abrir. Para el rol consulta, Instrumentos es la pantalla de inicio.

## 11. UX/UI

- **El inventario nunca es una pantalla sin contexto:** dice desde qué nivel se genera y remite al catálogo para cambiarlo.
- **Los pendientes no bloquean:** se ven, se cuentan y se explica dónde completarlos.
- **La guía avisa si el borrador lo armó el motor o el sistema** (sin motor), para que la archivista sepa cuánto revisar.
- **Lenguaje de consulta:** «Producido por», «Dirigido a», «Trata de». No aparecen códigos RiC en la ficha de consulta.
- **Móvil:** la tabla FUID se desplaza dentro de su tarjeta y la página no se sale del ancho (verificado a 390 px). La ficha ocupa toda la pantalla.

## 12. Modelo de datos

**Migración 0006:** cinco columnas nuevas, opcionales, en `recursos_documentales`:

- `codigo_referencia`;
- `caja`;
- `carpeta`;
- `folios`;
- `soporte`.

**Nada más cambia.**

- Las alertas usan la tabla `alertas` que ya existía, con el tipo nuevo `inventario_campos_pendientes`.
- Las exportaciones quedan en `registro_auditoria` (`inventario_exportado`, `guia_exportada`).

## 13. API

| Método y ruta | Permiso | Qué hace |
|---|---|---|
| `GET /api/instrumentos/catalogo?fondo_id&nodo_id` | catálogo | Un nivel del árbol: migas, nivel actual, hijos |
| `GET /api/instrumentos/catalogo/{id}` | catálogo | Ficha: descripción, entidades con conteo, preservación, datos de control |
| `GET /api/instrumentos/indice?fondo_id` | catálogo | Vocabulario por tipo y letra |
| `POST /api/instrumentos/inventario/vista-previa` | instrumentos: trabajar | Renglones FUID y pendientes; crea o actualiza la alerta |
| `POST /api/instrumentos/inventario` | instrumentos: trabajar | Descarga `.xlsx`; cabeceras `X-Campos-Pendientes` y `X-Alerta` |
| `POST /api/instrumentos/guia` | instrumentos: trabajar | Borrador de la nota de presentación |
| `POST /api/instrumentos/guia/exportar` | instrumentos: trabajar | Descarga `.docx` con el texto recibido |

La vista previa es un agregado a la API del prompt. Hace falta para mostrar la tabla y el aviso de alerta **antes** de descargar, como pide el flujo (§5 del prompt).

## 14. Uso de IA

**Solo en la guía.** El motor de análisis (Gemini, el mismo del módulo 2) redacta la nota de presentación con una instrucción estricta:

- usar únicamente los datos entregados;
- no inventar fechas, cifras, instituciones ni alcance documental;
- prosa formal, sin viñetas.

**Lo que recibe es una lista cerrada de datos validados. Nunca recibe:**

- el texto de los documentos;
- los datos de procedencia (origen, confianza, motor).

Si el motor no está o falla, el sistema arma un borrador básico con los mismos datos y lo avisa. La archivista siempre decide el texto final.

El inventario y el índice **no usan IA**: son agregación determinista.

## 15. Seguridad

- **Regla de procedencia, con dos defensas en el backend:**
  - cada respuesta se arma con listas cerradas de campos permitidos;
  - antes de salir pasa por `sin_campos_internos()`, que **falla** si encuentra una clave interna (origen, confianza, motor, estado de revisión, fragmento). Se comprobó metiendo a propósito «motor» en la ficha: la respuesta se bloquea y las pruebas fallan.
- Las descripciones sin publicar (borradores) no aparecen en el catálogo ni en ningún instrumento.
- Permisos por rol en el backend, en cada petición.
- El nombre del archivo descargado se limpia (solo letras, números y guiones bajos).
- El texto de la guía tiene un límite de 50 000 caracteres.

## 16. Auditoría (qué queda registrado)

| Acción | Qué guarda |
|---|---|
| `inventario_exportado` | Quién, cuándo, nivel, renglones y pendientes |
| `guia_exportada` | Quién, cuándo, fondo y longitud del texto exportado |
| `descripcion_editada` (módulo 2) | Ahora también el antes y el después de los datos de control |
| Alerta `inventario_campos_pendientes` | Conteo total y por campo; cierre automático con nota cuando ya no hay pendientes |

La **vista previa** no se audita, porque no produce ningún archivo. Sí actualiza la alerta.

## 17. Interoperabilidad

- **Inventario en `.xlsx`** (Office Open XML): abre en Excel, LibreOffice y Google Sheets. Trae encabezado del formato, fila de títulos fija, orientación horizontal para imprimir y comentarios en las celdas pendientes.
- **Guía en `.docx`:** abre en Word y LibreOffice.
- **Pendiente para más adelante:** exportar a RiC-O (RDF), EAD o CSV. El prompt no lo pide en esta versión. El índice tampoco tiene exportación propia, como dice el prompt.

## 18. Normativa aplicable

- **Acuerdo 042 de 2002 del AGN:** Formato Único de Inventario Documental. De ahí salen las columnas y el encabezado.
- **Acuerdo 027 de 2006 (AGN)**, glosario: inventario, guía, índice como instrumentos de descripción.
- **ISAD(G):** 3.1.1 código de referencia, 3.1.3 fechas, 3.1.5 volumen y soporte, 3.3.1 alcance y contenido.
- **NTC 4095**, norma general para la descripción archivística.
- **RiC-CM 1.0**, para las entidades y relaciones recorridas.

## 19. Arquitectura

- **Servicio:** `app/servicios/instrumentos.py`, de solo lectura.
  - Carga el árbol publicado del fondo **una vez por petición**, con las fechas propagadas hacia arriba.
  - Arma a partir de él el nivel, la ficha, los renglones, la guía y el índice.
- **Motor:** `motor.MotorGemini` gana el método `redactar()` para texto libre, compartiendo la llamada HTTP con `analizar()`.
- **Rutas:** `app/routers/instrumentos.py`.

### Decisiones

Las dos que exige el prompt (§4) están primero.

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| **Librería del inventario (hoja de cálculo)** | **openpyxl**; XlsxWriter; pandas + motor de Excel; CSV plano | **openpyxl 3.1** | Control completo de estilos, celdas combinadas del encabezado, fila de títulos fija, orientación de impresión, **relleno y cursiva por celda y comentarios** para marcar pendientes. A diferencia de XlsxWriter, que solo escribe, **también lee**: las pruebas abren el archivo generado y comprueban celda por celda. Pandas suma ~40 MB solo para esto. El CSV no puede marcar pendientes | Un fondo muy grande (decenas de miles de renglones) usa más memoria que XlsxWriter en modo de flujo. Si llega a pasar, se cambia a su modo de solo escritura, sin tocar el resto |
| **Librería de la guía (documento de texto)** | **python-docx**; docxtpl (plantillas); odfpy (ODT); ReportLab (PDF) | **python-docx 1.1** | Madura, sin dependencias pesadas. Da títulos con estilos reales de Word (navegables), párrafos y una tabla de datos. El archivista sigue editando en Word. Un PDF no se puede editar, y el prompt dice «documento de texto» | El diseño es sobrio (estilos por defecto de Word). Si la institución quiere su plantilla con logo, docxtpl se agrega encima sin cambiar el flujo |
| **Mecanismo de alertas de pendientes** | Entidad propia de alerta del módulo; eventos de auditoría con un tipo propio; **la tabla central `alertas` que ya existe** | **Tabla central `alertas`**, tipo `inventario_campos_pendientes` | Ya tiene lo que el prompt enumera: tipo, referencia a la entidad (el nivel inventariado), detalle (conteo por campo) y estado atendida/pendiente. Además, ya se muestra en el panel central y en la insignia de la barra superior, **para todos los módulos**. La auditoría es de solo anexar: no puede marcar algo como atendido sin inventar un segundo mecanismo | Una alerta por nivel: si se generan inventarios de la serie y del expediente, hay dos alertas que se solapan. Es deliberado, porque cada una dice qué instrumento concreto quedó incompleto |
| Dónde viven los datos de control del FUID | Pedirlos al exportar; tabla aparte; **columnas en la descripción** | **Columnas en `recursos_documentales`**, editables en «Corregir» | Son atributos del recurso (ISAD 3.1.1 y 3.1.5), no del instrumento. Se escriben una vez y sirven a todo inventario futuro | Hay que completarlos en cada unidad. Por eso se muestran como «Sin dato: saldrá pendiente» en la descripción |
| Fechas extremas | Campo de texto a mano; **calcularlas** | **Calcularlas** desde las fechas RiC-R080 validadas, propagadas hacia arriba | Evita contradicciones entre el inventario y la descripción | Una unidad sin fecha normalizada sale con fecha pendiente. Es correcto: falta el dato |
| Folios de un expediente sin folios propios | Dejarlo pendiente; sumar lo que haya; **sumar solo si todas las unidades tienen** | **Suma solo si todas las unidades tienen folios** | Una suma parcial sería un dato falso en un instrumento oficial | Si falta una sola unidad, el expediente queda pendiente |
| Estado de preservación antes del módulo 5 | Ocultarlo; inventar «buen estado»; **«sin evaluar» con lo que dejó la ingesta** | **«Sin evaluar»** con formato y huella | No afirma algo que ningún proceso verificó todavía | Ninguno: el módulo 5 lo reemplaza |

## 20. Código (dónde vive, cómo se organiza)

```
alembic/versions/0006_instrumentos.py      datos de control del FUID
app/models/recurso_documental.py           codigo_referencia, caja, carpeta, folios, soporte
app/servicios/instrumentos.py              árbol, ficha, inventario (+xlsx), guía (+docx), índice, alerta
app/servicios/motor.py                     redactar() para texto libre
app/servicios/descripcion.py, schemas      edición de los datos de control (módulo 2)
app/routers/instrumentos.py                /api/instrumentos
frontend/src/pages/Instrumentos.tsx        Catálogo, Inventario, Guía, Índice y ficha
frontend/src/lib/instrumentos.ts           tipos y etiquetas de relación
frontend/src/lib/api.ts                    descargar() con sesión
frontend/src/pages/Registro.tsx            tarjeta «Datos de control para el inventario»
tests/test_instrumentos.py
```

## 21. Pruebas

10 pruebas en `tests/test_instrumentos.py` (121 en total en el proyecto, todas pasan). Los datos internos se siembran con marcas únicas (`motor-interno-XYZ`, `fragmento-citado-XYZ`, confianzas 0,93 / 0,97 / 0,41). Si alguna aparece en una salida, hay una filtración.

- **Catálogo:**
  - árbol correcto en el fondo, la serie y el expediente;
  - migas de pan;
  - fechas extremas propagadas;
  - el borrador sin publicar no aparece;
  - sin claves ni marcas internas.
- **Ficha:**
  - entidades como enlace con su conteo (Alcaldía: 3 documentos);
  - forma documental;
  - migas;
  - preservación «sin evaluar» con PUID;
  - sin nada interno.
- **Inventario:**
  - las 10 columnas FUID en orden;
  - un renglón por unidad documental (expediente 1948) y uno por el expediente descrito como un todo (1949);
  - valores correctos, incluidas fechas y folios.
- **Pendiente sin bloquear:** la caja vacía sale «Pendiente», en cursiva y con comentario, y el archivo se genera.
- **Alerta:**
  - con pendientes, una alerta con el conteo exacto y por campo;
  - al regenerar no se duplica;
  - sin pendientes, ninguna alerta;
  - al completar el dato, la alerta se cierra sola.
- **Guía:**
  - el motor recibe solo datos validados (sin marcas internas);
  - el `.docx` contiene **exactamente** el texto editado, incluido un párrafo agregado a mano;
  - queda auditada.
- **Guía sin motor:** borrador básico con aviso.
- **Índice:** agrupado por tipo, letras A–C–G–Z, orden que ignora tildes y mayúsculas («Ábrego» antes de «Alcaldía»).
- **Ningún archivo exportado lleva campos internos:** se abren el `.xlsx` y el `.docx` y se busca cada marca (Definición de Terminado §10).
- **Permisos:**
  - sin sesión, 401;
  - revisor y consulta, 403 en inventario, vista previa, guía y exportar guía;
  - los mismos roles, 200 en catálogo, ficha e índice.

**Prueba de mutación:** al meter «motor» en la ficha pública, dos pruebas fallan de inmediato.

**Verificación visual** en navegador real:

- fondo, serie, expediente;
- ficha;
- inventario con pendientes y alerta en la barra superior;
- descarga real del `.xlsx`;
- guía editada y descarga del `.docx`;
- índice;
- móvil a 390 px sin desplazamiento horizontal;
- sin errores de JavaScript.

## 22. Criterios de aceptación

| Criterio (prompt §9–10) | Cumple |
|---|---|
| Árbol correcto en cada nivel; la ficha nunca incluye origen, confianza ni estado de revisión | ✓ |
| Un renglón por unidad documental o expediente, con las columnas FUID completas | ✓ |
| Campo obligatorio vacío = pendiente en el archivo, sin impedir la generación | ✓ |
| Con pendientes, alerta con el conteo correcto; sin pendientes, ninguna | ✓ |
| Guía con el texto del motor; lo exportado es exactamente lo que dejó el archivista | ✓ |
| Índice agrupado por tipo y alfabético dentro de cada grupo | ✓ |
| Generar exige el rol; consultar el catálogo, cualquier rol autenticado | ✓ |
| Prueba explícita de que ningún archivo ni respuesta lleva campos internos | ✓ |
| Las dos decisiones de §4 documentadas con tabla completa | ✓ (§19) |

**Pendiente honesto:**

- **Los datos de control hay que escribirlos a mano en cada unidad.** Hoy solo se pueden completar en «Corregir», después de publicar. Si en su flujo real la caja y la carpeta se conocen desde la ingesta (porque se digitaliza caja por caja), convendría pedirlos allí, o permitir completarlos en lote para varias unidades. Queda a su decisión.
- **La redacción real de Gemini para la guía** se verá en el servidor. Aquí se probó con un motor de prueba.
- ~~**La preservación** dice «sin evaluar» hasta el módulo 5.~~ Resuelto en el módulo 5: la ficha muestra el estado real (integridad, riesgo, versión de conservación).

## 23. Evidencia concreta de aplicación de RiC

El inventario del expediente «Correspondencia 1948» sale de recorrer el grafo, no de una tabla aparte:

```
Record Set «Correspondencia 1948» (expediente, CO-48)
  ─ rico:includesOrIncluded (R024) → Record «Oficio 114…» (CO-AM-114, caja 1, carpeta 3, 2 folios, papel)
        ← rico:isCreationDateOf (R080) ─ Date 1948-03-15
  ─ rico:includesOrIncluded → Record «Oficio 115…» (CO-AM-115, caja: —)
        ← rico:isCreationDateOf ─ Date 1948-03-18
  ─ rico:includesOrIncluded → Record «Acta del concejo…» (folios: —)
        ← rico:isCreationDateOf ─ Date 1948-03-22
```

**FUID generado:**

| N.º | Código | Nombre | F. inicial | F. final | Caja | Carpeta | Folios | Soporte |
|---|---|---|---|---|---|---|---|---|
| 1 | CO-AM-114 | Correspondencia / Oficio 114… | 15/03/1948 | 15/03/1948 | 1 | 3 | 2 | Papel |
| 2 | CO-AM-115 | Correspondencia / Oficio 115… | 18/03/1948 | 18/03/1948 | *Pendiente* | 3 | 1 | Papel |
| 3 | CO-AM-116 | Correspondencia / Acta del concejo… | 22/03/1948 | 22/03/1948 | 1 | 3 | *Pendiente* | Papel |

**Alerta:** «Inventario de «Correspondencia 1948»: 2 campos obligatorios del FUID sin dato.»

El índice es el vocabulario consolidado del módulo 3, sin copias. Por ejemplo, «Alcaldía Municipal de Tunja · 4 documentos» ya incluye los que venían de la forma «Alcaldia Mpal. de Tunja» fusionada.


---

## Ampliación · Grafo visual (a pedido de la autora)

**Por qué.** La autora no encontraba el grafo en el sistema. Lo había: cada publicación lo guarda en la base de datos, y la ficha lo recorre por enlaces. Pero no había un dibujo.

La Especificación funcional y las Historias de usuario piden un «lienzo de grafo interactivo, navegable con arrastre y zoom» y un botón «Ver en grafo». El diseño consolidado y los prompts por módulo no lo piden. Esa contradicción no se le consultó a tiempo; ahora queda resuelta a su favor.

**Dónde está.**
- **Instrumentos › pestaña «Grafo»**, junto a Catálogo, Inventario, Guía e Índice. Es un lugar visible para todos los roles que consultan el catálogo, incluido el rol consulta.
- **Botón «Ver en grafo»** en la ficha de cada documento del catálogo y en el detalle de cada entidad del vocabulario.
- No se hizo un módulo nuevo en la barra lateral, por dos razones: el grafo es una forma de consultar el fondo (como el catálogo), y así no se rompe la estructura de los siete módulos.

**Qué hace.**
- Dibuja el vecindario de un nodo central:
  - por defecto, el fondo con su jerarquía hasta 3 saltos;
  - desde un documento, sus agentes, lugares, fechas, actividades, forma documental, archivos y el expediente que lo incluye;
  - desde una entidad, todos los documentos que la comparten.
- **Navegación:**
  - arrastrar nodos y fondo;
  - zoom con la rueda o con los botones;
  - «Reencuadrar» ajusta todo a la pantalla;
  - clic en un nodo: panel con sus relaciones (con su URI de RiC-O, por ejemplo `rico:hasCreator`) y acciones «Centrar aquí», «Abrir ficha», «Ver en vocabulario» y «Ver en preservación».
- **Colores por tipo de entidad RiC**, con leyenda: documento o agrupación (Record / Record Set), agente, lugar, forma documental, fecha, actividad, archivo (Instantiation).
- **Accesible:** los nodos se pueden recorrer con el teclado, y el panel lista en texto las mismas relaciones del dibujo.
- **Solo lectura:** no edita nada.

**Datos.** `GET /api/instrumentos/grafo?fondo_id&centro=tipo:id&profundidad=1..3`, con permiso de consulta del catálogo.
- Lee las mismas relaciones RiC vigentes que guardó la descripción, más la forma documental (RiC-A17) y la jerarquía del árbol.
- **Nunca muestra:** borradores, entidades fusionadas, ni campos de procedencia (origen, confianza, motor). Pasa por la misma comprobación final `sin_campos_internos()`, que de hecho detectó durante el desarrollo una clave mal nombrada.
- **Límite:** 150 nodos por vista, con aviso si se corta.

**Librería.** `d3-force` (~30 kB, solo calcula posiciones). El dibujo es SVG propio, con los colores del sistema en claro y oscuro.

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Librería del lienzo | Cytoscape.js (completa, ~400 kB); vis-network; **d3-force + SVG propio** | **d3-force + SVG** | Liviana, sin estilos ajenos: usa la paleta y la tipografía de RICORA. Solo hace falta ubicar nodos; el resto es SVG simple y accesible | Funciones avanzadas (agrupar, exportar imagen) habría que hacerlas a mano |
| Ubicación | Módulo nuevo en la barra lateral; **pestaña en Instrumentos + botones «Ver en grafo»** | **Pestaña + botones** | El grafo es una forma de consultar el fondo, como el catálogo. Queda a la vista sin romper la estructura de siete módulos | Quien no entra a Instrumentos no lo ve. Por eso también está el botón en el vocabulario |

**Pruebas** (2 nuevas en `tests/test_instrumentos.py`):
- el grafo de un documento trae sus relaciones RiC con su URI y ningún dato interno;
- desde una entidad aparecen solo los documentos publicados que la comparten;
- por defecto se dibuja el fondo;
- sin sesión, 401; nodo inexistente, 404.

Verificación visual en navegador real, también en móvil.
