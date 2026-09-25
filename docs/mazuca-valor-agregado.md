# MAZUCA como valor agregado de la tesis

> Documento de trabajo del equipo investigador. MAZUCA **no cambia** el enfoque,
> la pregunta, los objetivos ni el producto de la tesis: es un prototipo
> demostrativo que acompaña a los lineamientos.

## 1. El nombre

**MAZUCA · Automatización archivística asistida por inteligencia artificial para archivos históricos**

**MA**rlín · **ZU**lly · **CA**talina: tres autoras, tres sílabas y tres
atributos del patrimonio documental: **autenticidad, integridad y
accesibilidad**.

El subtítulo retoma el título de la tesis: *Incorporación de inteligencia
artificial en la automatización asistida de procesos archivísticos en archivos
históricos del orden nacional en Colombia*.

## 2. Qué se mantiene en la tesis

- Enfoque cualitativo, descriptivo y de alcance propositivo.
- Método hermenéutico, análisis de contenido y estudio de casos.
- Pregunta, objetivos, fases y cronograma sin cambios.
- Producto: lineamientos técnicos para clasificación, descripción, valoración,
  gestión de metadatos y acceso, con criterios de verificación.

MAZUCA no agrega objetivos ni se presenta como un resultado validado.

## 3. Dónde aparece MAZUCA en la tesis

| Lugar | Contenido |
|---|---|
| Capítulo V, apartado final "Proyección de los lineamientos" | Dos o tres páginas que muestran cómo los lineamientos pueden llevarse a una herramienta: tabla lineamiento → funcionalidad y algunas capturas. Se presenta como prototipo demostrativo. |
| Anexo | Descripción breve de MAZUCA y enlace al repositorio. |
| Recomendaciones y trabajo futuro | Desarrollar y evaluar MAZUCA en un archivo histórico con archivistas e investigadores, incluido el portal de consulta. |
| Declaratoria de uso de IA | Declarar que el prototipo se desarrolló con asistencia de IA. |

**Texto sugerido:**

> Como valor agregado, se presenta MAZUCA, un prototipo demostrativo que ilustra
> cómo los lineamientos propuestos pueden aplicarse en un entorno tecnológico.
> Su desarrollo completo y su evaluación se plantean como línea de
> investigación futura.

## 4. Cómo MAZUCA aplica los lineamientos

| Lineamiento | Funcionalidad del prototipo |
|---|---|
| La IA propone, la persona archivista decide | Las sugerencias no modifican el documento hasta que alguien las valida; el rechazo exige motivo. |
| Trazabilidad del uso de IA | Cada sugerencia guarda modelo, versión, confianza, justificación y decisión humana. |
| Integridad (ISO 14721, OAIS) | Hash SHA-256 al ingresar y verificación periódica de fijeza. |
| Autenticidad (ISO 15489) | Bitácora de eventos encadenada con hashes: cualquier alteración se detecta. |
| Procedencia del texto (OCR) | El texto extraído registra herramienta, versión y confianza; por debajo de 75 % exige revisión humana. |
| Protección de datos personales (Ley 1581 de 2012) | El detector señala identificación, contacto y datos sensibles; la persona archivista decide publicar, anonimizar o restringir, con motivo. El texto original nunca se altera. |
| Publicación controlada (Ley 1712 de 2014) | Solo se aprueba para el portal un documento con descripción completa, integridad verificada, datos personales revisados y sin sugerencias de IA pendientes. Si el texto cambia, sale del portal. |
| Criterios de verificación | Informe por documento: cumple, no cumple o revisión manual, con la fuente normativa. |

## 5. Alcance y cronograma

La tesis tiene prioridad. MAZUCA avanza en paralelo, sin presión.

| Periodo | Tesis | MAZUCA |
|---|---|---|
| Oct–nov 2026 | Fases 2 y 3 | Avance ligero |
| Ene–feb 2027 | Fase 4: lineamientos | Cargar los criterios definitivos |
| Mar 2027 | Redacción final | Capturas y tabla para el capítulo V y el anexo |
| Abr 2027 | Sustentación | Demostración opcional |
| Después | — | Portal de consulta para investigadores (difusión como parte del proceso de acceso), como proyecto del SENA o línea de investigación futura |

## 6. Pendientes del equipo

- Contarle al tutor que la tesis tendrá un anexo con un prototipo demostrativo.
- Acordar con Zully y Catalina la inclusión del anexo.
- Usar solo documentos de dominio público o con autorización expresa.
- Mantener el repositorio privado hasta la sustentación.

## 7. Descripción asistida: dos proveedores de IA

MAZUCA usa un proveedor de IA intercambiable, según el lineamiento de que la
entidad decide qué solución de IA usar:

| | Proveedor en la nube (Claude) | Proveedor local (spaCy) |
|---|---|---|
| Qué propone | Título, fechas, productor, resumen, personas, lugares e instituciones | Fechas, personas, lugares e instituciones (sin título ni resumen) |
| Dónde corre | Servicio de Anthropic, por API | En el propio servidor de la entidad, sin conexión a internet |
| Cuándo se usa | Documento con revisión de datos personales decidida y no restringido | Documento restringido, o cuando la entidad no puede enviar texto a la nube |
| Costo | Por uso (según el modelo elegido) | Sin costo |

**Controles aplicados (lineamientos DES-03 y ACC-04):**
- **Evidencia verificable:** cada dato propuesto debe citar un fragmento
  literal del documento. MAZUCA comprueba esa cita contra el texto antes de
  mostrar la sugerencia; si no la encuentra, baja la confianza y advierte
  "⚠ evidencia no encontrada".
- **Privacidad ante todo (Ley 1581 de 2012, art. 26):** el proveedor en la
  nube nunca recibe el texto de un documento sin la revisión de datos
  personales decidida. Si se decidió anonimizar, recibe el texto
  anonimizado; si el documento está restringido, se usa solo el proveedor
  local.
- **Trazabilidad:** la sugerencia guarda el modelo que respondió realmente
  (incluido un modelo de respaldo, si el servicio de IA declinó la
  solicitud original).

## 8. Clasificación asistida

La entidad carga su propio **cuadro de clasificación** (fondo, sección,
serie, subserie) en MAZUCA. La IA nunca crea niveles nuevos: solo propone
en cuál serie o subserie **ya existente** ubicar el documento, siempre con
evidencia textual.

| | Proveedor en la nube (Claude) | Proveedor local (palabras clave) |
|---|---|---|
| Cómo decide | Compara el texto contra el nombre y la descripción de cada serie | Compara el texto contra las palabras clave que la entidad asignó a cada serie |
| Si ninguna serie encaja | No propone nada (mejor no proponer que adivinar) | No propone nada |
| Si la IA inventa un código que no está en el cuadro | MAZUCA lo descarta antes de crear la sugerencia | No aplica (solo usa códigos reales) |

**Nuevo criterio CLA-03:** el documento clasificado por IA queda vinculado a
una unidad real del cuadro y con una validación humana registrada; una
sugerencia pendiente o sin evidencia verificada marca el criterio como no
cumplido.

Hay un cuadro de clasificación de ejemplo (`cuadro_demo`) para pruebas; en la
Fase 4 se reemplaza por el cuadro real de la entidad.

## 9. Valoración asistida: cierre de los cinco procesos

Con este módulo MAZUCA cubre los cinco procesos archivísticos de la tesis
(clasificación, descripción, valoración, gestión de metadatos y acceso). La
IA solo **señala indicios** de valor secundario, nunca decide ni ejecuta
ninguna disposición documental:

| | Proveedor en la nube (Claude) | Proveedor local (palabras clave) |
|---|---|---|
| Qué señala | Indicios de valor histórico, cultural o científico, con evidencia textual | Los mismos tres tipos, por coincidencia de palabras clave genéricas |
| Cuántos a la vez | Uno por tipo como máximo; no son excluyentes entre sí (un documento puede tener valor histórico y cultural a la vez) | Igual |
| Si no hay indicios claros | No propone nada | No propone nada |

**Dos salvaguardas, más allá de la evidencia verificable (criterio VAL-02,
igual patrón que DES-03 y CLA-03):**
- El texto de las instrucciones a la IA prohíbe explícitamente recomendar
  eliminación, descarte o disposición final.
- **La plataforma misma no ofrece ninguna acción de eliminar un documento**,
  ni desde la IA ni desde la interfaz humana: se quitó el permiso de borrado
  en el panel de administración. Cualquier disposición real de un documento
  histórico de conservación total queda, por diseño, fuera del alcance de
  MAZUCA. Esto hace que el criterio **VAL-01** ("la herramienta no ofrece
  acciones de eliminación derivadas de la IA") se cumpla siempre, para todo
  documento.

## 10. Lo que faltaba en el capítulo IV, ya construido

Después de escribir el capítulo IV (`docs/lineamientos-tesis.md`), cinco
lineamientos habían quedado marcados como "trabajo futuro". Se construyeron
cuatro:

| Lineamiento | Qué se agregó |
|---|---|
| **DES-04** (relaciones tipadas) | Las personas, lugares e instituciones ya no solo "se mencionan": el proveedor en la nube indica si son productor, destinatario o mencionado del documento (Records in Context). El proveedor local (spaCy) no distingue el papel, así que propone siempre "mencionado" por defecto — limitación documentada, no oculta. |
| **MET-04** (exportación estándar) | Cada documento se puede exportar a **Dublin Core** (oai_dc) y a **PREMIS 3** (fijeza y eventos de la bitácora), desde la lista de documentos. La entidad no queda atada al formato propio de MAZUCA. |
| **CLA-04 y VAL-03** (auditoría por muestreo) | Comando `python manage.py auditoria_muestra clasificacion` (o `valoracion`) `--tamano N`: elige al azar sugerencias ya aceptadas para que una persona confirme si la IA acertó. Con `--reporte` da el porcentaje de exactitud, y para valoración lo desglosa por tipo de indicio (histórico, cultural, científico), para detectar sesgos. |

**ACC-05** (texto alternativo para lectores de pantalla) queda pendiente
**a propósito**: depende del portal público de consulta, que el equipo
decidió dejar fuera del alcance de la tesis. No tiene sentido construirlo
antes de tener dónde mostrarlo.

Con esto, MAZUCA implementa **19 de los 20 lineamientos** del capítulo IV
(el único pendiente es ACC-05, por la razón de alcance ya explicada).

## 11. Despliegue

MAZUCA se desplegará en **DigitalOcean**. Consideraciones:

- El modelo de spaCy (`es_core_news_md`, ~40 MB) se instala en el servidor;
  no requiere GPU.
- La clave de Anthropic se configura como variable de entorno
  (`ANTHROPIC_API_KEY`), nunca en el código ni en el repositorio.
- Variables de entorno relevantes: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0` en
  producción, `ANTHROPIC_API_KEY`, `MAZUCA_MODELO_IA` (por defecto
  `claude-opus-5`).
- MAZUCA usa siempre PostgreSQL (en desarrollo, en Docker y en producción),
  para probar contra la misma base de datos en todos los entornos. Los
  documentos subidos no van al repositorio (`.gitignore`); en producción
  conviene además almacenamiento de objetos (Spaces) para los archivos.
