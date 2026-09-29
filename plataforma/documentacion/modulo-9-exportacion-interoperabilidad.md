# Módulo 9 · Exportación e interoperabilidad

Este documento sigue la estructura de 23 puntos de la sección 5 del prompt de desarrollo. El alcance lo fijan la historia de usuario 9 y los requisitos RF-M9-01 a RF-M9-03.

## 1. Propósito
Entregar la descripción de los documentos a otros sistemas: el sistema de gestión documental electrónico, un portal de datos abiertos o un repositorio de preservación. Hay tres formatos: RiC-O 1.1, JSON-LD y CSV. Antes de entregar un archivo se verifica que sea válido, y cada entrega queda registrada.

## 2. Auditoría (qué se revisó antes de construirlo)
Ya existían:
- la selección desde el catálogo;
- los tres formatos;
- el registro de exportaciones.

Faltaba o fallaba lo siguiente:
- **Sin barra de avance.** La exportación se generaba dentro de la petición, así que un lote grande dejaba la pantalla congelada y podía cortarse.
- **JSON-LD sin contexto.** Cada propiedad salía como URI completa, lo que lo hacía ilegible.
- **CSV sin marca UTF-8.** Excel mostraba mal las tildes.
- **Ninguna verificación.** Nada comprobaba que el archivo fuera válido antes de entregarlo.
- **Alcance oculto.** RF-M9-03 pide registrar qué documentos se exportaron; ese dato se guardaba pero no se mostraba.
- **Sin rastro de auditoría.** La exportación no quedaba en la auditoría ni en el historial de cada documento.
- **Relaciones sin filtrar.** Las relaciones del RDF del lote no pasaban por la regla de visibilidad del M8.

## 3. Problema que resuelve
Interoperar sin copiar datos a mano, con archivos que otro sistema pueda leer de verdad y con evidencia de qué se entregó, cuándo y a quién.

## 4. Usuarios
| Rol | Alcance |
|---|---|
| Archivista (rol principal) | Exporta cualquier documento visible para su rol |
| Revisor | Igual que el archivista |
| Consulta | Exporta solo lo publicado y abierto; ve solo sus propias exportaciones |

## 5. Casos de uso
1. Marcar documentos en el catálogo y pulsar «Exportar selección»; llegan precargados.
2. Agregar o quitar documentos, con filtro y «Marcar visibles».
3. Elegir el formato.
4. Generar la exportación y ver el avance.
5. Descargar el archivo.
6. Consultar el registro de exportaciones.

## 6. Entidades RiC involucradas
- Record (E04) e Instantiation (E06).
- Todas las entidades relacionadas.
- DocumentaryFormType.
- Name, para los nombres alternativos de los agentes.

## 7. Relaciones RiC involucradas
- Todas las relaciones validadas del documento, con su propiedad RiC-O verificada.
- La propiedad inversa materializada. Ejemplo: `hasCreator` / `isCreatorOf`.

## 8. Funcionalidades
- **Generación en segundo plano.** Usa la misma cola del M2, con barra de avance y actualización automática. Si la cola no está disponible, la exportación se genera igual en el momento: no se pierde.
- **Verificación antes de entregar.** El archivo se vuelve a leer con el mismo lector que usaría quien lo recibe:
  - Turtle y JSON-LD con rdflib: deben describir al menos los documentos pedidos como `rico:Record`.
  - CSV: encabezado exacto y todos los documentos presentes.
  - Si la verificación falla, el archivo **no se entrega**. La exportación queda en error y dice por qué.
- **JSON-LD con contexto.** Incluye `@context` (`rico`, `rdf`, `rdfs` y `xsd`) y es legible: `rico:hasCreator`.
- **CSV para Excel.** Lleva marca UTF-8, así que abre bien en Excel. Tiene columnas nuevas: identificador, idioma, publicación y fecha, estado del análisis, estado de la **revisión** (M6), quién revisó y cuándo. Incluye también los documentos sin relaciones.
- **Registro (RF-M9-03).** Cada exportación guarda:
  - fecha, formato y quién la pidió;
  - alcance en lenguaje claro: «2 documento(s): Acta…, Oficio 12»;
  - estado, tamaño y huella SHA-256 del archivo entregado.
- **Trazabilidad.** Cada exportación queda como acción «exportar» en la auditoría, y como evento «Exportación (M9)» en el historial (M7) de cada documento incluido, con la huella del archivo.
- **Visibilidad (RF-M8-04).** La regla se aplica también al generar el archivo.

## 9. Flujos
Catálogo → marcar tarjetas → «Exportar selección» → /exportar con los documentos precargados → formato → «Generar exportación» → barra de avance → «Descargar» + fila nueva en el registro.

## 10. Pantallas
- `/exportar/` (rediseñada).
- `/exportar/<id>/estado.json` (nueva).
- `/exportar/<id>/descargar/`.

## 11. UX/UI
- **Pasos numerados:** 1 Formato y 2 Documentos.
- **Formatos como tarjetas,** cada una con su descripción en lenguaje claro.
- **Lista de documentos filtrable sin tildes,** con los precargados marcados «desde el catálogo».
- **Contador de seleccionados;** el botón queda deshabilitado si no hay ninguno.
- **Tarjeta de estado** con barra de avance, mensaje de verificación y botón «Descargar».

## 12. Modelo de datos
- Campos nuevos en `Exportacion`: `estado`, `progreso`, `mensaje`, `alcance`, `tamano_bytes` y `sha256`.
- `archivo` ahora puede quedar vacío mientras la exportación se genera.
- Acción de auditoría nueva: «exportar».
- Migración 0024.

## 13. API
| Ruta | Parámetros | Respuesta |
|---|---|---|
| `POST /exportar/` | `formato`, `doc`… | Redirige a `?listo=<id>` |
| `GET /exportar/<id>/estado.json` | — | Estado, progreso, mensaje y enlace de descarga |
| `GET /exportar/<id>/descargar/` | — | El archivo; si todavía no está lista, avisa |

## 14. Uso de IA
No usa IA. Se exporta solo lo validado por personas; el CSV dice además si cada relación fue revisada (M6).

## 15. Seguridad
- **Rol consulta:** solo exporta y ve sus propias exportaciones; lo ajeno responde 404.
- **Doble verificación de visibilidad:** la regla se aplica al pedir y al generar la exportación.
- **Huella SHA-256:** permite verificar que la copia entregada no se alteró.

## 16. Auditoría (qué queda registrado)
- **Acción «exportar»:** registra quién, cuándo, el formato, los documentos y el alcance.
- **Evento en la bitácora de cada documento:** la exportación queda con la huella del archivo.

## 17. Interoperabilidad
| Formato | Estándar | Detalle |
|---|---|---|
| RDF/Turtle | RiC-O 1.1 | URIs verificadas contra `RiC-O_1-1.rdf`, con inversas materializadas para SPARQL sin razonador |
| JSON-LD | JSON-LD 1.1 | Con contexto |
| CSV | RFC 4180 | UTF-8 con BOM |

Los tres formatos están listos para intercambio con un SGDEA, un portal de datos abiertos o un paquete de preservación.

## 18. Normativa aplicable
- RiC-CM 1.0 y RiC-O 1.1 (ICA).
- Acuerdo 003 de 2015 del AGN: interoperabilidad del documento electrónico.
- Ley 1712 de 2014: datos abiertos y reserva.
- Ley 1581 de 2012.
- Guía de interoperabilidad del Estado colombiano (Gobierno Digital).

## 19. Arquitectura
| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Dónde se genera | En la petición; en la cola | En la cola, con respaldo en la petición si la cola falla | Avance visible y sin cortes por tiempo de espera, sin perder la exportación si Redis falla | Con la cola caída, un lote grande vuelve a depender del tiempo de espera web (600 s) |
| Validez del archivo | Confiar en el serializador; volver a leerlo | Volver a leerlo antes de entregar | RF-M9-01 exige un archivo válido; es lo mismo que hará el sistema receptor | El costo de leer dos veces; despreciable frente a la generación |
| JSON-LD | Expandido; con contexto | Con contexto | Legible para personas y equivalente para máquinas | — |
| CSV y Excel | UTF-8 sin BOM; con BOM | Con BOM | Excel en Windows abre bien las tildes sin configurar nada | Algunos lectores muy estrictos ven el BOM; el lector de Python lo maneja |

## 20. Código
- `ric/exportacion.py`: `solicitar`, `generar`, `validar`, `alcance_de`, `_csv_lote` y `_grafo_lote`.
- `ric/tasks.py`: tarea `generar_exportacion`.
- `ric/vistas_catalogo.py`: `exportar`, `exportar_estado` y `exportar_descargar`.
- `ric/templates/ric/exportar.html`.
- `ric/models.py`: modelo `Exportacion` y acción EXPORTAR.
- Migración 0024.

## 21. Pruebas
`tests/test_modulo9_exportacion.py` tiene 11 pruebas:
1. Precarga desde el catálogo.
2. RDF válido, releído con rdflib, con `rico:Record`, `hasCreator` y huella.
3. JSON-LD con contexto y releíble.
4. CSV con BOM, columnas de revisión y documentos sin relaciones.
5. Registro con formato, alcance y quién la pidió.
6. Auditoría e historial de cada documento.
7. Estado JSON y descarga.
8. Exportación en curso: muestra la barra y no se descarga.
9. Archivo inválido: no se entrega y queda en error.
10. Sin cola disponible: se genera igual.
11. Rol consulta: solo lo visible y solo sus propias exportaciones.

`tests/test_m9_exportar.py` se ajustó al CSV ampliado. Además se verificó el flujo completo en Chromium: catálogo → 2 precargados → CSV → lista y verificada → descarga.

## 22. Criterios de aceptación (historia de usuario 9)
- **Documentos precargados desde el catálogo sin volver a buscarlos (RF-M9-02):** cumplido.
- **Archivo válido en RiC-O, JSON-LD o tabular según lo elegido (RF-M9-01):** cumplido y **verificado antes de entregarlo**.
- **Registro de formato, alcance y quién la pidió, visible en el registro inferior (RF-M9-03):** cumplido, con huella SHA-256 y trazabilidad en la auditoría y en el M7.

## 23. Evidencia concreta de aplicación de RiC
Al exportar el acta del Cabildo en Turtle se obtiene:
- `rico:Record` con `rico:name`;
- `rico:hasCreator` hacia el `rico:CorporateBody` «Cabildo de Santafé», y su inversa `rico:isCreatorOf`;
- el `rico:DocumentaryFormType` enlazado con `rico:hasDocumentaryFormType`;
- los nombres alternativos del agente como individuos `rico:Name`.

El mismo grafo en JSON-LD se lee como `rico:hasCreator` gracias al contexto.

## Qué no hace (y qué pasa en cada error)
- **Formatos no incluidos:** no exporta EAD3 ni METS/PREMIS completos. El RDF RiC-O es el formato de intercambio definido por la especificación; hay módulos heredados de Dublin Core y PREMIS pendientes de decidir.
- **Exportaciones sin plazo de retiro:** no hay borrado automático. Siguen disponibles en el registro.
- **Si la generación falla:** la exportación queda en «Error» con la causa y se puede volver a pedir.
