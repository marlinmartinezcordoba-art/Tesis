# Ajuste metodológico: de lineamientos a lineamientos aplicados en software

> Documento de trabajo para discutir con la dirección de la tesis. Un cambio de
> enfoque en una maestría suele requerir aval de la dirección y, según el
> reglamento de la Universidad de La Salle, del comité del programa.

## 1. Qué cambia y qué se conserva

| Elemento | Antes | Propuesta |
|---|---|---|
| Enfoque | Cualitativo | Cualitativo con componente de desarrollo tecnológico |
| Alcance | Descriptivo y propositivo | Propositivo y aplicado |
| Método | Hermenéutico, análisis de contenido y estudio de casos | **Investigación en Ciencia del Diseño** (*Design Science Research*), que integra el análisis hermenéutico y el estudio de casos como fases |
| Producto | Lineamientos técnicos para cinco procesos | Lineamientos técnicos **y** un prototipo de software que los aplica y permite verificarlos |

Se conservan la pregunta central, el marco normativo, el análisis de contenido
(Fase 2) y el diagnóstico normativo (Fase 3). El desarrollo **no reemplaza** el
trabajo cualitativo: lo usa como insumo y lo pone a prueba.

## 2. Por qué Ciencia del Diseño

La Investigación en Ciencia del Diseño (Hevner et al., 2004; Peffers et al.,
2007) es un método reconocido en ciencias de la información para producir
**artefactos** —modelos, métodos, lineamientos e instanciaciones de software—
que resuelven un problema real, y para evaluarlos con rigor. En esta tesis hay
dos artefactos:

1. **Los lineamientos** (artefacto de tipo método): criterios por proceso y
   atributo, cada uno con su fuente normativa.
2. **La plataforma** (artefacto de tipo instanciación): demuestra que los
   lineamientos se pueden aplicar y verificar en la práctica.

## 3. Pregunta y objetivos ajustados

**Pregunta (sin cambios de fondo):** ¿Cómo incide la inteligencia artificial en
la automatización de los procesos archivísticos de los archivos históricos del
orden nacional, en relación con la autenticidad, la integridad y la
accesibilidad del patrimonio documental?

**Objetivo general propuesto:** Formular lineamientos técnicos para la
incorporación de inteligencia artificial en la automatización asistida de los
procesos de clasificación, descripción, valoración, gestión de metadatos y
acceso en archivos históricos del orden nacional, y validarlos mediante un
prototipo de software que los aplica.

**Objetivos específicos propuestos:**

1. Analizar la producción académica y técnica sobre IA aplicada a procesos
   archivísticos (Fase 2).
2. Diagnosticar el marco normativo colombiano e internacional aplicable (Fase 3).
3. Formular lineamientos técnicos con criterios de verificación por proceso y
   atributo (Fase 4).
4. **Nuevo:** Desarrollar un prototipo de plataforma que aplique los
   lineamientos en un flujo de automatización asistida, con validación humana
   y trazabilidad.
5. **Nuevo:** Evaluar el prototipo con profesionales en archivística mediante
   un estudio de caso con documentos de dominio público.

## 4. Correspondencia con el cronograma

| Actividad de Ciencia del Diseño | Fase de la tesis | Fechas | Relación con la plataforma |
|---|---|---|---|
| Identificar el problema | Fase 2, análisis de contenido | hasta 13/10/2026 | Riesgos (sesgo, pérdida de contexto, trazabilidad) |
| Definir objetivos de la solución | Fase 3, diagnóstico normativo | 16/10–16/11/2026 | Fuentes normativas de cada criterio |
| Diseñar y desarrollar | Fase 3 y receso | nov 2026–ene 2027 | Base: acervo, hash, bitácora, sugerencias con validación |
| Demostrar | Fase 4, lineamientos | 12/01–28/02/2027 | Criterios validados cargados como reglas del informe |
| Evaluar | Nueva: evaluación | mar 2027 | Sesiones con archivistas; guía de evaluación |
| Comunicar | Sustentación | abr 2027 | Demostración y capítulos IV y V |

## 5. Estructura sugerida para los capítulos IV y V

- **Capítulo IV. Lineamientos técnicos.** Un apartado por proceso; en cada
  criterio: enunciado, atributo que protege, forma de verificación, fuente
  normativa y riesgo que mitiga.
- **Capítulo V. Aplicación y evaluación de los lineamientos.** Arquitectura
  del prototipo, cómo cada lineamiento se convierte en una regla o en un
  control (tabla de trazabilidad lineamiento → funcionalidad), resultados del
  estudio de caso y limitaciones.

## 6. Cómo la plataforma aplica los lineamientos

| Lineamiento | Funcionalidad del prototipo |
|---|---|
| La IA propone, la persona archivista decide | Las sugerencias no modifican el documento hasta que alguien las valida; el rechazo exige motivo |
| Trazabilidad del uso de IA | Cada sugerencia guarda modelo, versión, confianza, justificación y decisión humana |
| Integridad (OAIS, fijeza) | SHA-256 al ingresar y verificación periódica de fijeza |
| Autenticidad (ISO 15489) | Bitácora de eventos encadenada con hashes: cualquier alteración se detecta |
| Procedencia del texto (OCR) | El texto extraído registra herramienta, versión y confianza; por debajo de 75 % exige revisión humana |
| Criterios de verificación | Informe por documento: cumple, no cumple o revisión manual, con la fuente normativa |

## 7. Precauciones éticas y de datos

- Usar solo documentos de dominio público o con autorización expresa; no usar
  datos ni código de proyectos o contratos de la empresa.
- Declarar el uso de IA en la sección "Declaratoria de uso de IA".
- Mantener el repositorio privado mientras la tesis no esté sustentada.
