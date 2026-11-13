# Asistente RICORA con los documentos de la entidad (RAG)

Solicitud de la autora (13-11-2026): que el asistente responda con los documentos, leyes y manuales de la
entidad, sin inventar datos, y conectarlo a Google Colab o a servidores de Google Cloud con tarjeta gráfica.

## Cómo funciona

1. **Biblioteca del asistente** (Usuarios y permisos › Biblioteca del asistente, solo administración): se cargan
   leyes, decretos, acuerdos del AGN, manuales y procedimientos. Cada archivo queda con su huella SHA-256; el
   trabajador le extrae el texto con el lector de la ingesta (capa de texto, o imagen limpia y OCR si viene
   escaneado). Nada se borra: un documento derogado se anula y deja de consultarse.
2. **Recuperación** (`app/servicios/rag.py`): la pregunta se busca en el índice de texto completo de PostgreSQL
   (español, sin tildes, migraciones 0035 y 0057) en tres fuentes: la biblioteca, el texto de los documentos
   cargados al fondo y las descripciones publicadas. De cada documento se toman los pasajes donde aparecen las
   palabras de la pregunta (`ts_headline`) y se ordenan por pertinencia (`ts_rank_cd`). Hasta 8 pasajes.
3. **Generación**: el motor (Gemini) recibe solo esos pasajes, numerados, con la instrucción de responder
   únicamente con ellos y citar cada afirmación con el número del pasaje. Sin Google Search.
4. **Sin pasajes, no hay respuesta inventada**: si nada coincide, no se consulta al motor y la pantalla lo dice.
5. La pantalla muestra los pasajes consultados y marca los que la respuesta citó.

El modo «Internet» (Google Search, como antes) sigue disponible en el mismo panel.

## Protección

- **Reserva (Ley 1712, arts. 18 y 19):** nunca se recupera un archivo ni una descripción clasificada o reservada,
  propia o heredada, ni lo que no está publicado: su texto saldría hacia el motor. Vale también para el equipo de
  archivo.
- **Datos personales (Ley 1581):** los pasajes pasan por el filtro de identificadores antes de salir.
- **Auditoría:** se registra la consulta, el modo, cuántos pasajes se recuperaron y cuántos se citaron; el texto
  de la pregunta no se guarda.

## Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo recuperar los pasajes | (a) índice de texto completo de PostgreSQL, que ya usa el buscador; (b) vectores (embeddings de Gemini y pgvector); (c) LangChain o LlamaIndex con una base de vectores aparte | **(a)** | Ya está en el servidor, en español y sin tildes, y respeta la reserva con las mismas reglas del buscador. No suma servicios ni costos. En normas y documentos de archivo las preguntas usan las mismas palabras que el texto («tabla de retención», «transferencia»). LangChain y LlamaIndex son bibliotecas que orquestan este mismo patrón: el RAG es la técnica, no la biblioteca | Una pregunta con sinónimos que no están en el texto («plazo» frente a «tiempo de retención») puede no recuperar el pasaje. Si la evaluación lo muestra, la opción (b) se suma sin cambiar el resto |
| Qué motor redacta | Gemini (actual), IA local (Ollama, apagada), otro proveedor | **Gemini** | Ya configurado y gratuito dentro de su cuota; responde en segundos | El límite diario de la cuenta gratuita: al agotarse, el asistente lo dice |
| Google Colab o Google Cloud con tarjeta gráfica | (a) no conectar; (b) Colab como servidor de la IA local; (c) una máquina con GPU en Google Cloud | **(a) No conectar** | Colab no es un servidor: la sesión se cierra sola (a los 90 minutos sin uso, a las 12 horas como máximo), cambia de dirección en cada sesión, y sus condiciones de uso no permiten usarlo como servicio web permanente. Una máquina con GPU en Google Cloud (la más pequeña, T4) cuesta del orden de 250 a 400 dólares al mes encendida todo el día: va contra la regla de no usar recursos pagados. Gemini ya corre en las tarjetas gráficas de Google, sin costo dentro de la cuota | Si en el futuro se necesitara que ningún texto salga del servidor, la IA local queda conservada (apagada) y podría correr en una máquina con GPU propia o de la entidad |
