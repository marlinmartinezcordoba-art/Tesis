# MAZUCA como eje central de la tesis

> Documento de trabajo del equipo investigador. **Reemplaza** al enfoque
> anterior ("MAZUCA como valor agregado"). Registra el ajuste metodológico
> **aprobado por la dirección de la tesis**: el desarrollo de software deja
> de ser un anexo demostrativo y pasa a ser el punto de partida desde el
> cual se ajustan los demás elementos de la tesis.

## 0. El ajuste metodológico aprobado

**Decisión:** la tesis parte de la solución de software (MAZUCA) ya
construida, y los capítulos y el marco metodológico se ajustan a partir de
ella — no al revés, como se había planteado originalmente (lineamientos
primero, prototipo como anexo después).

**Aprobación:** la dirección de la tesis aprobó este ajuste. Queda
pendiente, si el reglamento de la Universidad de La Salle lo exige,
formalizarlo también ante el comité del programa; conviene que el equipo lo
confirme directamente con la dirección.

### Qué cambia respecto al planteamiento anterior

| Elemento | Antes ("valor agregado") | Ahora (aprobado) |
|---|---|---|
| Punto de partida | Los lineamientos (Fases 2 y 3) primero; MAZUCA los aplica después, como anexo | **MAZUCA ya construida**; los lineamientos se documentan, contrastan y ajustan a partir de lo que el software ya implementa y de lo que falta por implementar |
| Método | Cualitativo (hermenéutico, análisis de contenido, estudio de casos) | **Investigación en Ciencia del Diseño** (*Design Science Research*; Hevner et al., 2004; Peffers et al., 2007), que integra el análisis de contenido y el estudio de casos como actividades del método, no como el método completo |
| Producto de la tesis | Lineamientos técnicos, con MAZUCA como ilustración opcional | **Dos artefactos:** los lineamientos técnicos (artefacto de tipo método) y MAZUCA (artefacto de tipo instanciación), evaluados juntos |
| Capítulo V | "Proyección de los lineamientos" en unas páginas, con MAZUCA como demostración breve | Capítulo completo: arquitectura de MAZUCA, tabla de trazabilidad lineamiento → funcionalidad, y evaluación del prototipo |

### Qué se mantiene sin cambios

- La pregunta de investigación: cómo incide la IA en la automatización de
  los procesos archivísticos, en relación con la autenticidad, la
  integridad y la accesibilidad del patrimonio documental.
- El marco normativo (Ley 594 de 2000, Decreto 1080 de 2015, Acuerdo 001 de
  2024 del AGN, ISO 15489, ISO 14721/OAIS, ISAD(G), Records in Contexts,
  CONPES 4144 de 2025, Recomendación de la UNESCO sobre ética de la IA).
- Los cinco procesos archivísticos como eje de análisis: clasificación,
  descripción, valoración, gestión de metadatos y acceso.

### Objetivos ajustados (propuesta para validar con la dirección)

**Objetivo general:** Formular lineamientos técnicos para la incorporación
de inteligencia artificial en la automatización asistida de los procesos de
clasificación, descripción, valoración, gestión de metadatos y acceso en
archivos históricos del orden nacional, **a partir del desarrollo y la
evaluación de MAZUCA**, un prototipo de software que los instancia.

**Objetivos específicos propuestos:**
1. Desarrollar y documentar la arquitectura de MAZUCA, con sus salvaguardas
   de autenticidad, integridad y accesibilidad (ya en curso, ver secciones
   7–11).
2. Contrastar el marco normativo y la literatura académica (Fases 2 y 3)
   con las decisiones de diseño ya tomadas en el prototipo, para
   confirmarlas, ajustarlas o señalar vacíos.
3. Formular los lineamientos técnicos definitivos, con criterios de
   verificación, a partir de esa validación.
4. Evaluar MAZUCA con profesionales en archivística (y, si el alcance lo
   permite, con investigadores) mediante un estudio de caso.

## 1. El nombre

**MAZUCA · Automatización archivística asistida por inteligencia artificial para archivos históricos**

**MA**rlín · **ZU**lly · **CA**talina: tres autoras, tres sílabas y tres
atributos del patrimonio documental: **autenticidad, integridad y
accesibilidad**.

El subtítulo retoma el título de la tesis: *Incorporación de inteligencia
artificial en la automatización asistida de procesos archivísticos en archivos
históricos del orden nacional en Colombia*.

## 2. Dónde aparece MAZUCA en la tesis

| Lugar | Contenido |
|---|---|
| Capítulo III (Metodología) | El apartado 0 de este documento, ajustado a la estructura formal de la tesis. |
| Capítulo IV (Lineamientos) | `docs/lineamientos-tesis.md`, contrastado con las Fases 2 y 3. |
| Capítulo V (Aplicación y evaluación) | Arquitectura de MAZUCA, tabla lineamiento → funcionalidad (secciones 7–11 de este documento), y los resultados de la evaluación con archivistas. |
| Declaratoria de uso de IA | Declarar que el prototipo se desarrolló con asistencia de IA. |

## 3. Cómo MAZUCA aplica los lineamientos (tabla base para el capítulo V)

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

## 4. Cronograma ajustado

| Periodo | Actividad |
|---|---|
| Ya en curso | Desarrollo de MAZUCA (clasificación, descripción, valoración, metadatos, acceso — los cinco procesos ya implementados) |
| Oct–nov 2026 | Fases 2 y 3, ahora usadas para **contrastar** las decisiones ya tomadas en el software, no para partir de cero |
| Ene–feb 2027 | Ajuste de los lineamientos definitivos a partir de ese contraste; ajustes al software si el contraste señala algo que corregir |
| Mar 2027 | Estudio de caso: evaluación de MAZUCA con archivistas; redacción final |
| Abr 2027 | Sustentación |

## 5. Pendientes del equipo

- Confirmar con la dirección si el ajuste requiere aval adicional del
  comité del programa, según el reglamento de la Universidad de La Salle.
- Acordar con Zully y Catalina la redacción final de los objetivos y del
  capítulo de metodología a partir de la propuesta de la sección 0.
- Diseñar el instrumento de evaluación del estudio de caso (marzo de 2027).
- Usar solo documentos de dominio público o con autorización expresa.
- Mantener el repositorio privado hasta la sustentación.

## 6. Descripción asistida: dos proveedores de IA

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

## 7. Clasificación asistida

La entidad carga su propio **cuadro de clasificación** (fondo, sección,
serie, subserie) en MAZUCA. La IA nunca crea niveles nuevos: solo propone
en cuál serie o subserie **ya existente** ubicar el documento, siempre con
evidencia textual.

| | Proveedor en la nube (Claude) | Proveedor local (palabras clave) |
|---|---|---|
| Cómo decide | Compara el texto contra el nombre y la descripción de cada serie | Compara el texto contra las palabras clave que la entidad asignó a cada serie |
| Si ninguna serie encaja | No propone nada (mejor no proponer que adivinar) | No propone nada |
| Si la IA inventa un código que no está en el cuadro | MAZUCA lo descarta antes de crear la sugerencia | No aplica (solo usa códigos reales) |

**Criterio CLA-03:** el documento clasificado por IA queda vinculado a
una unidad real del cuadro y con una validación humana registrada; una
sugerencia pendiente o sin evidencia verificada marca el criterio como no
cumplido.

Hay un cuadro de clasificación de ejemplo (`cuadro_demo`) para pruebas; en la
Fase 4 se reemplaza por el cuadro real de la entidad.

## 8. Valoración asistida: cierre de los cinco procesos

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

## 9. Lo que faltaba en el capítulo IV, ya construido

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

## 10. Alineación con Records in Context (en curso)

Se está ampliando el modelo de datos de MAZUCA para que las relaciones entre
documentos y entidades (personas, lugares, instituciones) sigan más de
cerca la estructura real de **RiC-CM** (*Records in Contexts – Conceptual
Model*, ICA-EGAD, versión 1.0, publicada el 30 de noviembre de 2023), que
reemplaza a ISAD(G), ISAAR(CPF), ISDF e ISDIAH.

Punto clave verificado contra la norma: RiC-CM **no** tiene una entidad de
tipo "Concepto" o "Tema" separada. El "de qué trata" un documento se modela
como una **relación asociativa** hacia una entidad que ya existe en el
modelo (una persona, un lugar, una actividad), no como un tipo de entidad
nuevo. Esta sección se actualizará cuando el desarrollo esté terminado.

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
