# Auditoría experta de RICORA (5 de noviembre de 2026)

Revisión de solo lectura en cuatro frentes, hecha en paralelo:
1. Conformidad archivística y RiC.
2. Seguridad y datos personales.
3. Diseño y accesibilidad.
4. Arquitectura y operación.

Antes de darlos por ciertos, se verificaron en el código o con una prueba los hallazgos críticos.

## Corregido el mismo día

| Hallazgo | Severidad | Verificación | Corrección |
|---|---|---|---|
| El SPARQL público podía leer con `GRAPH ?g` los grafos «completo», con lo clasificado o reservado (Ley 1712) | Crítica | Reproducido con Oxigraph: devolvía el literal reservado | `named_graphs` acotado a los grafos públicos (`grafo_rdf.py`). Prueba de regresión: `tests/test_sparql_grafos_reservados.py` |
| Los respaldos automáticos de la base estaban apagados en producción: dependían del interruptor de preservación | Alta | `trabajador.py`: el respaldo solo corría con `RICORA_PRESERVACION=1` | El respaldo de la base corre siempre; preservación sigue apagada |
| El modo oscuro del equipo dejaba texto claro sobre fondos blancos (≈1,15:1) | Alta | Fondos fijos en `app.css` | La interfaz queda fija en modo claro (`data-theme="light"`) |
| Contraste insuficiente: estado «hecho» 2,86:1, blanco sobre turquesa 2,13:1, botón primario y enlaces 4,33:1 y foco casi invisible | Alta | Ratios calculados según WCAG 2.x | Tokens oscurecidos (`--ok`, `--accent`, `--line-fuerte`), texto oscuro sobre turquesa y foco con contorno |
| Los avisos flotantes ocultaban pistas informativas (`role="status"`) que deben quedarse en la página | Alta | `AvisosFlotantes.tsx` | Solo pasan a flotante las confirmaciones y los errores |
| El asistente mostraba a la usuaria el nombre de una variable técnica (`GEMINI_API_KEY`) | Media | `Asistente.tsx`, `asistente.py` | Mensaje en lenguaje sencillo |

## Lo que la tesis debe decir con exactitud

| Afirmación actual | Hallazgo | Cómo escribirla |
|---|---|---|
| «Cobertura total de RiC-CM: 85 de 85 relaciones» | Algunas relaciones (R018, R048, R049 y otras) cuentan por la clase de relación que cita el código en el OWL. La tripleta binaria es la genérica (`hasFamilyAssociationWith`), aunque RiC-O 1.1 tiene `hasChild` y `hasOrHadSpouse` | «Cobertura de RiC-CM medida por los términos de RiC-O que el sistema escribe, incluidas las clases de relación (n-arias); en las relaciones familiares, la propiedad binaria es la general» |
| «Sistema nativo en RiC: nivel 3» | La escala de niveles 0 a 3 es propia de la investigación, no del ICA | «Según la escala de adopción definida en esta investigación» |
| «Prueba de interoperabilidad» | La reimportación usa el importador del propio sistema | Ya se complementa con Oxigraph y xmllint (anexo de interoperabilidad); falta un sistema de otro proveedor |
| Certeza de cada relación | `relationCertainty` es la que declara el motor sobre sí mismo, sin calibrar, y se publica después de que la archivista confirma | «Certeza declarada por el motor, no calibrada; la validación es de la archivista» |

## Pendiente: recomendado antes de un uso real (no antes de la defensa)

### Archivística y normativa colombiana
- **Ley 1712, art. 22:** exigir que toda reserva tenga plazo, con un máximo de 15 años. Advertir de los documentos de más de 30 años (Ley 594, art. 28).
- **Disposición final:** verificar que la TRD esté convalidada y registrar la publicación previa del inventario de eliminación (Acuerdo 004 de 2019, compilado en el Acuerdo 001 de 2024).
- **Perfil SHACL:** exigir los elementos esenciales de ISAD(G) en el fondo (código de referencia, fechas, extensión y productor), con severidad de advertencia en los niveles inferiores.
- **EAD3:** distinguir persona, familia y entidad (`persname`, `famname`, `corpname`) y exportar las fechas normalizadas y `controlaccess`.
- **EDTF:** distinguir «abierto» (`..`) de «desconocido» (fin vacío).
- **CCD:** unir las dependencias a la entidad productora (`hasOrHadSubdivision`).

### Seguridad y datos personales (Ley 1581)
- **Transferencia internacional (art. 26):** no enviar a Gemini documentos reservados o con datos sensibles sin confirmación expresa. Usar una clave de pago o Vertex para que los datos no se usen en el entrenamiento.
- **Inicio de sesión:** límite de intentos por IP. Segundo factor obligatorio para la administración y en el borrado total.
- **Dependencias:** actualizar FastAPI/Starlette, python-multipart y pdfminer.six, que tienen fallas conocidas (CVE).
- **Tokens:** sacar de la ruta los tokens de invitación y recuperación, y filtrar los registros que el despliegue imprime.
- **HTTPS:** que el despliegue nunca quede en HTTP cuando falla HTTPS.
- **Datos personales:** aviso de privacidad y canal para consultas, reclamos y supresión.

### Operación
- **Despliegue sin el error 502:** healthcheck en la web, migraciones como paso previo y reintento en Caddy (`lb_try_duration`).
- **Respaldos:** copia diaria fuera del droplet y monitor externo sobre `/api/salud`.
- **Servidor:** límites de memoria y rotación de registros en docker-compose.
- **Imagen:** compilarla en GitHub Actions y no en el droplet; imagen «ligera» sin las herramientas de preservación.

### Diseño
- **Navegación por teclado:** enlace «Saltar al contenido».
- **Asistente:** que atrape el foco como las demás ventanas.
- **Formularios:** etiquetas en los campos que solo tienen texto de ejemplo.
- **Código:** quitar el CSS sin uso y consolidar las capas repetidas de `app.css`.
- **Carga inicial:** dividir el paquete de JavaScript por ruta.

## Lo que sobra

| Elemento | Por qué |
|---|---|
| Relaciones de RiC poco pertinentes para un fondo institucional (`knows`, `knowsOf`, `hasOrHadStudent`, adyacencias de lugares, relaciones derivadas entre fechas) | Se agregaron para completar la cobertura; conviene ocultarlas por defecto y presentarlas como capacidad opcional |
| Herramientas de preservación en la imagen (ClamAV, JRE, veraPDF, JHOVE) | El módulo está apagado; alargan la compilación y gastan memoria |
| Validación OWL+SHACL en cada petición | El trabajador ya la guarda en `GrafoRdf` |
| Tipos documentales copiados como texto en el alcance de la serie | Ya existen como relación (`hasOrHadSomeMembersWithDocumentaryFormType`) |
| CSS y exportaciones sin uso (`.asistente-*`, `abrirBuscador`, `ACCIONES_RAPIDAS`) | Restos del rediseño |

## Lo que está bien (según los cuatro revisores)

- Mapeo de niveles a RiC-O (RecordSet, Record, RecordPart) con los tipos oficiales y `skos:broadMatch` para sección y subserie.
- Cada término se comprueba contra el OWL oficial.
- Filtro de lo reservado y de los datos sensibles en lo público.
- Permisos en todas las rutas; el revisor queda en solo lectura.
- Sesiones bien hechas; XML leído sin entidades externas; sin inyección SQL.
- Tiempos límite en todos los servicios externos.
- Pruebas automáticas para las funciones nuevas.
