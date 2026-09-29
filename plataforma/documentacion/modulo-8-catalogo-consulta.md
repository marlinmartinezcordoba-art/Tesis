# Módulo 8 · Catálogo y consulta

Este documento sigue la estructura de 23 puntos de la sección 5 del prompt de desarrollo. El alcance lo fijan la historia de usuario 8 y los requisitos RF-M8-01 a RF-M8-04.

## 1. Propósito
Que cualquier persona autorizada encuentre documentos y entidades por texto libre y por clase, y navegue de una entidad a sus documentos y de un documento a sus entidades. Cada rol ve exactamente lo que le está permitido, y nada más.

## 2. Auditoría (qué se revisó antes de construirlo)
Ya existían la búsqueda, el filtro por clase, las fichas, «Ver en grafo» y las sugerencias. La auditoría encontró **fugas de información para el rol consulta** (RF-M8-04). Todas quedan corregidas:

| # | Fuga encontrada | Qué podía ver el rol consulta |
|---|---|---|
| 1 | «Ver en grafo» y sus datos JSON | Cualquier documento y su vecindario, aunque no estuviera publicado o fuera reservado |
| 2 | Ficha de un expediente o serie | La lista de documentos sin publicar |
| 3 | RDF de un documento y RDF completo del sistema | Contenido que incluía lo no publicado |
| 4 | Endpoint SPARQL | Todo el grafo |
| 5 | Listado, conteos y sugerencias | Entidades (por ejemplo, personas) que solo aparecen en documentos reservados |
| 6 | Vocabularios (M5) | Todas las autoridades, y en cada ficha los documentos sin publicar; también la pantalla interna de duplicados |

Además:
- La búsqueda distinguía tildes: «Bogota» no encontraba «Bogotá».
- La búsqueda no consultaba los nombres alternativos de los agentes.
- No había paginación: solo se mostraban los primeros 20 o 40 resultados.

## 3. Problema que resuelve
Consultar el acervo sin exponer lo reservado (Ley 1712 de 2014, Ley 1581 de 2012) y encontrar lo que se busca aunque se escriba sin tildes o con otra forma del nombre.

## 4. Usuarios
- **Consulta** (rol principal): ve solo lo permitido.
- **Archivista y revisor**: ven todo.

## 5. Casos de uso
- Buscar escribiendo y elegir una sugerencia, con el mouse o con las flechas y Enter.
- Filtrar por clase.
- Abrir la ficha de una entidad.
- Saltar a un documento relacionado.
- Ver la entidad en el grafo.
- Pasar de página.
- Seleccionar documentos para exportar (M9).

## 6. Entidades RiC involucradas
Record (E04) y Record Set (E03), de fondo a expediente. Agentes (E08–E13), Activity, Mandate, Rule, Date y Place.

## 7. Relaciones RiC involucradas
Todas las relaciones validadas. Una relación solo se muestra si el usuario puede ver sus dos extremos.

## 8. Funcionalidades
- **Regla única de visibilidad** (`acceso_documentos.Visibilidad`). Archivista y revisor ven todo. El rol consulta ve:
  - los documentos publicados cuyos archivos son todos de acceso abierto;
  - las entidades que aparecen en al menos uno de esos documentos;
  - las entidades de los instrumentos archivísticos (organigrama y TRD), porque son información pública;
  - los fondos, secciones y series;
  - los expedientes, solo si contienen al menos un documento visible, porque su nombre puede llevar datos de una persona.
- **Dónde se aplica la regla:** catálogo, conteos, sugerencias, fichas, relaciones de la ficha, documentos de un conjunto, grafo, RDF de una entidad, RDF completo, SPARQL, vocabularios (lista y ficha) y duplicados.
- **Qué ve el rol consulta cuando algo no le está permitido:** la ficha le dice «no disponible para consulta». El grafo y el RDF responden 404, sin confirmar siquiera que el elemento existe.
- **Búsqueda sin tildes ni mayúsculas** (PostgreSQL `unaccent`) sobre el nombre, el identificador y los nombres alternativos de los agentes. El texto completo del contenido de los documentos sigue usando el buscador en español de PostgreSQL.
- **Texto libre y clase combinados** (RF-M8-01), con conteos por clase que respetan el rol.
- **Paginación** de 24 resultados por página, con el total de resultados.
- **Sugerencias accesibles:** combobox con navegación por teclado (flechas, Enter y Escape).
- **Navegación:** de la ficha de una entidad a sus documentos, y del documento a sus entidades (RF-M8-02 y RF-M8-03), además de «Ver en grafo» en solo lectura.

## 9. Flujos
Catálogo → escribir o elegir una sugerencia → filtro de clase → tarjeta → ficha → documento relacionado o «Ver en grafo».

## 10. Pantallas
`/catalogo/`, `/catalogo/<tipo>/<id>/`, `/ric/grafo/<tipo>/<id>/` y `/vocabularios/`, con sus filtros de visibilidad.

## 11. UX/UI
- Panel de clases a la izquierda y resultados a pantalla completa.
- Número de resultados y página actual.
- Aviso visible para el rol consulta: «ve únicamente los documentos aprobados, publicados y de acceso abierto».

## 12. Modelo de datos
- Migración 0023: extensión `unaccent` de PostgreSQL. Es una extensión «trusted», así que no requiere superusuario.
- Se agrega `django.contrib.postgres` a las aplicaciones instaladas.
- Sin tablas nuevas.

## 13. API
`GET /catalogo/sugerencias/?q=` devuelve solo nombres visibles para quien consulta. El grafo JSON, el RDF y SPARQL quedan filtrados por rol.

## 14. Uso de IA
No usa IA. Solo se publica en el catálogo lo que una persona revisó (M6).

## 15. Seguridad
RF-M8-04 se verifica en el servidor, en todos los puntos de acceso de la tabla del punto 2. Para quien no tiene permiso, lo oculto responde igual que si no existiera.

## 16. Auditoría (qué queda registrado)
La consulta de un documento en el visor ya queda como «consultar» (M1). Las exportaciones quedan en M9.

## 17. Interoperabilidad
El RDF y el SPARQL que obtiene el rol consulta son un grafo RiC-O coherente: solo incluyen entidades y relaciones visibles, sin aristas colgando.

## 18. Normativa aplicable
- Ley 1712 de 2014: información clasificada y reservada.
- Ley 1581 de 2012: datos personales.
- Ley 594 de 2000.
- ISAD(G) y RiC-CM, para el acceso por entidades.

## 19. Arquitectura
| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Dónde vive la regla de acceso | En cada vista; en una clase única | Clase única `Visibilidad`, calculada una vez por petición | Una sola regla evita que una pantalla nueva vuelva a filtrar mal | Costo de cálculo por petición en acervos muy grandes; se puede llevar a caché si hace falta |
| Qué entidades ve el rol consulta | Todas las autoridades; solo las de documentos visibles; las de documentos visibles más las de instrumentos | Documentos visibles más instrumentos | Una autoridad que solo aparece en un documento reservado revela información reservada; la TRD y el organigrama son públicos | Una autoridad creada a mano, sin documentos, no se ve en consulta hasta que un documento publicado la use |
| Respuesta ante lo no visible | Mensaje de «prohibido»; 404 | Mensaje en fichas y 404 en grafo y RDF | No confirma que exista algo oculto | — |
| Búsqueda sin tildes | Normalizar en Python; columna normalizada; `unaccent` | `unaccent` de PostgreSQL | Estándar, sin columnas nuevas; indexable más adelante | Sin índice, la búsqueda recorre la tabla; suficiente para el volumen actual |

## 20. Código
- `ric/acceso_documentos.py`: `Visibilidad`.
- `ric/busqueda.py`: `filtro_nombre` y `buscar_entidades` con visibilidad.
- `ric/vistas_catalogo.py`: `catalogo`, `catalogo_sugerencias` y `catalogo_ficha`.
- `ric/views.py`: grafo, RDF y SPARQL.
- `ric/grafo.py`, `ric/rdf.py` y `ric/sparql.py`: parámetro `visibilidad`.
- `ric/vistas_vocabularios.py`.
- `ric/templates/ric/catalogo.html`.
- `ric/migrations/0023_busqueda_sin_tildes.py`.

## 21. Pruebas
`tests/test_modulo8_catalogo.py` tiene 11 pruebas:
- Texto libre y clase combinados.
- Búsqueda sin tildes y por nombre alternativo, también en las sugerencias.
- Paginación.
- Navegación entidad ↔ documento.
- Para el rol consulta, que no se vea lo reservado en: catálogo y sugerencias; fichas; grafo, datos JSON, RDF y RDF completo; SPARQL; vocabularios; expedientes (ni el expediente oculto ni el borrador dentro de uno visible).
- Que el archivista vea todo.

Pruebas antiguas ajustadas:
- 4 archivos (grafo, RDF, SPARQL y búsqueda) creaban su usuario sin rol, es decir, como consulta.
- 3 pruebas de vocabularios, 1 de duplicados y 1 del M8 anterior esperaban el comportamiento con fuga.

La suite completa tiene 574 pruebas y todas pasan.

## 22. Criterios de aceptación (historia de usuario 8)
- **Texto libre y filtro de clase combinados (RF-M8-01):** cumplido, además sin tildes y por nombres alternativos.
- **La ficha muestra todos los documentos relacionados y permite saltar a su vista sin repetir la búsqueda (RF-M8-02 y RF-M8-03):** cumplido.
- **El rol consulta solo ve lo que su rol permite (RF-M8-04):** cumplido. Se cerraron seis vías de fuga que antes estaban abiertas.

## 23. Evidencia concreta de aplicación de RiC
Hay dos documentos publicados:
- un acta abierta, relacionada con la Person (E08) «José Acevedo y Gómez», con nombre alternativo «J. Acevedo»;
- una historia clínica reservada, relacionada con «Camilo Torres Tenorio».

El rol consulta encuentra a José Acevedo al buscar «jose acevedo» o «J. Acevedo» y navega a su acta. A Camilo Torres no lo encuentra por ninguna vía: ni en el catálogo, ni en las sugerencias, la ficha, el grafo, el RDF, SPARQL o vocabularios. Su RDF completo es un grafo RiC-O válido sin el documento reservado.

## Qué no hace (y qué pasa en cada error)
- **Búsqueda por significado:** no hay búsqueda semántica por embeddings. Se usa el texto completo en español de PostgreSQL más `unaccent`.
- **Autoridades sin documentos:** una autoridad creada a mano, sin documentos publicados que la usen, no aparece para el rol consulta. Es una decisión de protección de datos, y se puede revisar.
- **Página inexistente:** si se pide una página que no existe, se muestra la última.
