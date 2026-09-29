# Módulo 2 · Preprocesamiento y OCR en segundo plano

Estructura de 23 puntos (sección 5 del prompt de desarrollo). Alcance fijado por la hoja de ruta (sección 8 del prompt: «preprocesamiento/OCR con Celery, Redis y Tesseract»), la auditoría de arquitectura (procesamiento asíncrono) y la historia de usuario 2.

## 1. Propósito
Que el OCR, la detección de idioma, la marca de calidad y la entrega al motor de análisis ocurran fuera de la petición web. Así la persona archivista envía los archivos, sigue trabajando y ve el avance real de cada uno.

## 2. Auditoría (qué se revisó antes de construirlo)
El preprocesamiento corría dentro de la petición: con varios PDF escaneados, «Enviar a preprocesamiento» dejaba la pantalla colgada durante minutos y podía cortarse por tiempo de espera. El estado «en cola» se deducía de si existía un evento de extracción, así que no distinguía entre «nunca enviado», «procesando» y «falló». Un error dejaba el archivo en «en cola» para siempre y no había manera de reintentar.

## 3. Problema que resuelve
Archivos de cientos de páginas que bloqueaban el servidor y la pantalla, falta de visibilidad sobre qué pasaba con cada archivo, y fallas silenciosas.

## 4. Usuarios
Archivista: envía, ve el avance, reintenta y decide sobre la calidad baja. Revisor y consulta no tienen acceso al módulo.

## 5. Casos de uso
- Enviar uno o varios archivos a preprocesamiento.
- Enviar de una vez todos los que no se han enviado.
- Ver el avance por archivo: en cola → leyendo página n de m → idioma y calidad → motor → listo.
- Ver el resultado en lenguaje claro.
- Reintentar un archivo con error o un trabajo perdido.
- Decidir sobre las páginas de calidad baja; «aceptar igual» envía el documento al motor por la cola.

## 6. Entidades RiC involucradas
Instantiation (E06), que guarda el estado del trabajo. Record (E04), al que se le asigna el idioma. Mechanism (E13), que es el motor de análisis que recibe el documento al terminar.

## 7. Relaciones RiC involucradas
- R025 (documento → instanciación).
- Las relaciones que propone el motor al final del flujo (módulo 3).

Este módulo no crea relaciones por sí mismo.

## 8. Funcionalidades
- **Cola Celery con Redis.** Sin `REDIS_URL` (pruebas y desarrollo) las tareas corren en el mismo proceso, con el mismo código.
- **Estados del archivo:** sin enviar, en cola, procesando, listo, calidad baja y error. Cada archivo guarda además su progreso (0–100), la etapa, el mensaje, las fechas de encolado, inicio y fin, el resultado en JSON y el número de intentos.
- **Avance real por página:** la extracción avisa después de cada página del PDF o TIFF, y la barra nunca retrocede.
- **Sin duplicados en la cola:** el envío usa una actualización condicional sobre `intentos`, así que si dos personas pulsan a la vez solo una encola. Cada trabajo lleva su número de intento, y una entrega vieja del broker se descarta sola.
- **Trabajo perdido:** si un trabajo lleva más de 35 minutos (configurable) en cola o procesando, se ofrece «Reintentar».
- **Broker caído:** el archivo pasa a «error» con la causa y aparece un aviso en la pantalla; no hay error 500.
- **Tiempo límite por tarea:** 1.700 s (suave) y 1.800 s (duro). Si se supera, el archivo queda en error con una explicación.
- **Aviso sin trabajador:** si hay archivos en cola y ningún trabajador responde, la pantalla muestra un aviso (la consulta al trabajador se guarda en caché 15 s).
- **Pantalla viva:** consulta el estado cada 2 s solo mientras haya archivos activos.
- **«Aceptar igual»:** cuando se aceptan las páginas de calidad baja, el envío al motor también va por la cola.

## 9. Flujos
1. Ingesta.
2. «Enviar a preprocesamiento» vuelve de inmediato a la pantalla de preprocesamiento.
3. La fila avanza: en cola → leyendo página n de m → detectando idioma y calidad → enviando al motor.
4. Termina en uno de tres estados:
   - **Listo**, con el enlace «Ver propuesta de entidades» o el botón «Enviar al motor».
   - **Calidad baja**, con los enlaces a las páginas por decidir.
   - **Error**, con el motivo y el botón «Reintentar».

## 10. Pantallas
- `/ingesta/preproceso/` (reescrita, con avance en vivo).
- `/ingesta/preproceso/<id>/pagina/<n>/` (sin cambios de interfaz).

## 11. UX/UI
- La barra de avance muestra el porcentaje real y la etapa debajo.
- El mensaje de resultado o de error aparece en la fila, bajo el nombre del archivo.
- La persona puede cerrar la pantalla: el trabajo continúa y al volver ve el estado actual.

## 12. Modelo de datos
- Nuevos campos en `Instantiation`: `estado_proceso`, `progreso`, `etapa`, `mensaje_proceso`, `proceso_encolado`, `proceso_iniciado`, `proceso_terminado`, `resultado_proceso` e `intentos`. Todos son no editables: solo los escribe el sistema.
- La migración 0020 llena los datos existentes: lo ya procesado queda en listo o calidad baja, y el resto en sin enviar.

## 13. API
`GET /ingesta/preproceso/estado.json?ids=1,2` responde con, por cada archivo:
- `id`, `estado`, `etiqueta`, `progreso`, `etapa`, `mensaje`, `paginas`, `idioma`
- `perdido`, `reintentar`
- `accion`: una de `decidir`, `propuestas` o `motor`, con sus URL

La respuesta incluye además `trabajadores` y `sin_trabajador`. Responde 401 sin sesión y 403 sin rol archivista.

`POST /ingesta/preproceso/enviar/` recibe uno o varios `instanciacion` y encola.

## 14. Uso de IA
No hay IA en este módulo: el OCR es Tesseract. Al terminar, el documento pasa al motor de análisis (módulo 3). Si no hay proveedor de IA activo, el archivo queda listo y lo dice.

## 15. Seguridad
- Rol archivista en la pantalla, el envío y el JSON de estado.
- El trabajador no publica puertos.
- Redis solo es accesible en la red interna de Docker.
- Los errores se muestran sin volcar trazas a la persona.

## 16. Auditoría (qué queda registrado)
- Cada envío a la cola queda como «modificar» en `RegistroAuditoria`, con el tipo de cola y el número de intento.
- Los cambios que hace el trabajador se auditan a nombre de quien envió el archivo (`actuando_como`), no como anónimos.
- Cada falla queda como evento de extracción fallido en la bitácora encadenada.
- Las actualizaciones de progreso no inundan la auditoría: se escriben sin señales, y los campos de progreso se ignoran en las diferencias.

## 17. Interoperabilidad
El resultado queda en la bitácora de eventos (EventoRiC), lista para PREMIS (evento de extracción, agente, resultado).

## 18. Normativa aplicable
- Acuerdo 003 de 2015 y Ley 594 de 2000: el original nunca se modifica y el reintento no toca la huella.
- ISO 15489: trazabilidad del proceso.

## 19. Arquitectura
| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Ejecución asíncrona | Hilos en gunicorn; django-q / RQ; Celery | Celery 5 + Redis 7 | Es lo que fija el prompt. Es estándar, con reintentos, tiempo límite y `acks_late` | Dos servicios más que operar (redis y worker) |
| Dónde vive el estado | Resultados de Celery en Redis; campos en la base | Campos en `Instantiation` | Sobrevive a Redis, se consulta con SQL y lo ven la pantalla y la auditoría | Una escritura por página (barata; solo cuando cambia el porcentaje) |
| Avance en pantalla | WebSocket/SSE; consulta periódica | Consulta cada 2 s, solo con archivos activos | Sin infraestructura nueva (Channels), funciona detrás de cualquier proxy | Hasta 2 s de retraso en la barra |
| Pruebas y desarrollo | Redis obligatorio; modo inmediato | `CELERY_TASK_ALWAYS_EAGER` sin `REDIS_URL` | La misma ruta de código, sin servicios extra para probar | El modo inmediato no prueba el broker; por eso hubo una prueba integrada real con redis-server y un trabajador |
| Concurrencia del trabajador | 1; 2; número de CPU | 1 por defecto (`RICORA_TRABAJADORES_OCR`) | El OCR consume CPU y memoria; el Droplet es pequeño | Los archivos esperan en cola uno tras otro; se sube con una variable |
| Trabajos duplicados | Bloqueo en Redis; número de intento | Número de intento y actualización condicional | No depende de Redis y cubre la reentrega del broker | — |

## 20. Código
- `config/celery.py`, `config/__init__.py`, y en `config/settings.py` el bloque `CELERY_*` y `RICORA_MINUTOS_TRABAJO_PERDIDO`.
- `ric/cola.py`: `encolar`, `perdido` y `trabajadores_activos`.
- `ric/tasks.py`: `preprocesar_instanciacion`, `analizar_instanciacion` y `resumen`.
- Avisos de avance en `acervo/extraccion.py`, `ric/extraccion.py` y `ric/ingesta.py`.
- `ric/auditoria_acciones.py`: `actuando_como`.
- `ric/vistas_ingesta.py`: `preproceso`, `preproceso_estado`, `preproceso_enviar` y `preproceso_pagina_decidir`.
- `ric/templates/ric/preproceso.html`.
- `docker-compose.yml`: servicios `redis` y `worker`.
- `docker-entrypoint.sh`: modo `worker`.
- `.github/workflows/deploy.yml`: recrea también `worker`.
- `requirements.txt`: `celery[redis]`.

## 21. Pruebas
`tests/test_modulo2_cola.py` tiene 19 pruebas:
- Estado inicial.
- Recorrido de estados.
- Avance por página en un PDF de 3 páginas.
- Calidad baja que no pasa al motor.
- Falla con evento fallido y el original intacto.
- Tiempo límite superado.
- Broker caído, tanto en el servicio como en la pantalla.
- Reintento.
- Sin doble cola.
- Trabajo perdido.
- Entrega vieja descartada.
- Auditoría del envío.
- Envío múltiple.
- JSON de estado.
- Acción «ver propuestas».
- Permisos 401/403.
- Revisor sin acceso.
- Aviso sin trabajador.
- «Aceptar igual» por la cola.

`tests/test_m2_preproceso.py` se ajustó al nuevo estado «sin enviar».

Además hubo una prueba integrada real con redis-server, un trabajador Celery, runserver y Chromium: un PDF escaneado de 12 páginas pasó de en cola a leyendo página 1…11 de 12 y luego a listo (12 páginas, confianza OCR 95,7 %, idioma español), con la pantalla actualizándose sola.

## 22. Criterios de aceptación (historia de usuario 2)
- Archivo enviado → estado en cola, luego procesando con avance, luego listo: cumplido.
- Texto extraído, idioma detectado y páginas de calidad baja marcadas (RF-M2-02 a RF-M2-04): cumplido.
- Calidad baja → la persona decide antes de que el archivo pase al motor: cumplido.
- Al quedar listo → entrega automática al motor de análisis: cumplido, por la cola.

## 23. Evidencia concreta de aplicación de RiC
- El estado del proceso vive en la Instantiation (E06), no en el Record: una misma unidad documental puede tener un máster y una copia de acceso, cada una con su propio procesamiento.
- El idioma detectado se asigna al Record (atributo de idioma de RiC-CM).
- La entrega al motor la registra el Mechanism (E13) en cada propuesta.

## Qué no hace (y qué pasa en cada error)
- No hay prioridades de cola ni cancelación de un trabajo en curso.
- Reintentar vuelve a leer todo el archivo. Las páginas de texto extraído se regeneran, así que las decisiones de calidad anteriores de ese archivo se pierden. El original y la bitácora se conservan.
- Si el trabajador muere a mitad, `acks_late` devuelve el trabajo a la cola. Si no vuelve, a los 35 minutos se ofrece «Reintentar».
- Si Redis se cae, los envíos nuevos quedan en error con la causa. Los trabajos que ya estaban en Redis sobreviven gracias al AOF.
