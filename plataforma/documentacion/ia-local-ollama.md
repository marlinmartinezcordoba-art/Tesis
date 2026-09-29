# IA local con Ollama (respaldo del motor de análisis, M3)

## Problema
El motor de análisis dependía de un único servicio en la nube (Gemini). Cuando ese servicio se saturaba (error 503, «alta demanda»), el documento quedaba sin propuestas y la persona archivista veía un error.

## Qué se hizo
- **Nuevo proveedor:** «IA local con Ollama» (`ric/proveedor_ollama.py`). Es un modelo de lenguaje que corre en el mismo servidor, así que el texto no sale a internet.
  - Usa las mismas instrucciones y el mismo esquema de salida que Gemini y Claude (`ric/ia_prompt.py`).
  - La respuesta sale en JSON restringido a ese esquema (parámetro `format` de Ollama).
  - Pasa por la misma verificación de evidencia (CC-01) y el mismo motor de reglas RiC-CM.
- **Respaldo automático:** si el proveedor principal falla (saturado, sin conexión o límite de uso), el motor usa el respaldo y lo dice en pantalla. Si no hay proveedor principal activo, usa el respaldo directamente.
- **Configuración desde Administración:** en Administración → Proveedores de IA hay dos botones nuevos, «Usar como respaldo» (exige una prueba de conexión exitosa) y «Quitar como respaldo».
- **Análisis en la cola:** «Generar propuesta de entidades» ahora trabaja en segundo plano (tarea `analizar_instanciacion`). La página muestra «el motor está trabajando…» y se recarga sola al terminar.
- **Servidor:** docker-compose tiene un servicio `ollama`, sin puertos publicados. Descarga el modelo la primera vez y libera la memoria tras 10 minutos sin uso.
  - Al arrancar, `configurar_inicial` registra la IA local como respaldo y prueba la conexión.
  - Los procesos web pasan de 3 a 2 para dejar memoria libre.

## Decisión
| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Qué hacer cuando la nube falla | Solo reintentar más tarde; cambiar a otro proveedor en la nube; IA local | IA local como respaldo automático | No cuesta dinero, funciona sin internet y el texto no sale del servidor | Calidad y velocidad menores (ver abajo) |
| Modelo local | llama3.2:1b; qwen2.5:0.5b; qwen2.5:1.5b; modelos de 7B | qwen2.5:1.5b (≈1 GB) | Es el más capaz que cabe en 2 GB de RAM, con buen español y buen apego a JSON | Menos preciso que Gemini: propone menos entidades y con más errores de tipo |
| Principal o respaldo | Ollama como principal; como respaldo | Respaldo (se puede volver principal desde Administración) | Gemini propone mejor; Ollama evita que el trabajo se detenga | — |
| Espera | Petición web síncrona; cola | Cola | En 1 CPU un documento tarda minutos: la persona no debe esperar con la página congelada | — |

## Límites (dichos claramente)
- **Tiempo:** en el servidor actual (2 GB de RAM, 1 CPU), un acta de 2–3 páginas puede tardar entre 3 y 10 minutos. Los documentos muy extensos pueden superar el contexto (8.192 tokens); en ese caso se muestra «respuesta incompleta».
- **Calidad:** la calidad es menor que con Gemini. Por eso toda propuesta pasa, como siempre, por la decisión de la persona archivista.
- **Primer despliegue:** la descarga del modelo tarda unos minutos. Mientras tanto, la prueba de conexión dice «el modelo todavía no está descargado».
- **Alcance de la prueba:** en el entorno de desarrollo no hay acceso al registro de Ollama. Las pruebas automáticas simulan su interfaz HTTP; la prueba real se hace con «Probar conexión» en el servidor.

## Pruebas
`tests/test_ia_local_ollama.py` tiene 12 pruebas:
- Salida estructurada que pasa por las reglas.
- Evidencia inventada, que se descarta.
- Errores en lenguaje claro: sin conexión, modelo no descargado, JSON inválido y falta de `OLLAMA_URL`.
- Prueba de conexión.
- Respaldo usado y anunciado.
- Error sin respaldo.
- Fallan los dos proveedores.
- Configuración del respaldo en Administración, que exige la prueba de conexión.
- «Generar propuesta» por la cola.
- Página «trabajando» con recarga automática.
