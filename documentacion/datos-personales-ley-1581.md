# Datos personales (Ley 1581 de 2012): detección y revisión

Fase A de los requerimientos funcionales. Antes había un campo manual («no contiene, personales, sensibles, de
menores») que dependía de que alguien leyera todo el documento. Ahora el sistema busca posibles datos personales
en el texto de cada archivo, avisa, y una persona decide hallazgo por hallazgo.

## Cómo funciona

1. **Al cargar el archivo** (después de leer su texto o hacer el OCR), el sistema busca posibles datos personales.
   Si encuentra datos sensibles o de menores, crea una alerta de severidad alta en el panel. La alerta no incluye
   el dato: solo dice el tipo y el documento.
2. **Al describir**, la pantalla de trabajo muestra cada hallazgo con su tipo, su categoría, en qué páginas
   aparece, cuántas veces, la confianza, el fragmento resaltado y qué hacer.
3. **La persona decide**: confirmar, corregir (otra categoría) o descartar. Para descartar tiene que dar un
   motivo. Cada decisión queda en la auditoría con el antes y el después.
4. **Al publicar o corregir**:
   - Si queda algún hallazgo pendiente, no se publica.
   - Si la persona no declaró el nivel de datos personales, se toma el de los hallazgos confirmados.
   - Si declaró menos de lo confirmado (por ejemplo, «personales» con un dato de menores confirmado), no se
     publica.
5. **Lo ya cargado**: en el panel de alertas, la administración tiene el botón «Buscar datos personales en lo
   ya cargado». Además, cada documento se revisa solo la primera vez que se abre para describirlo.

## Qué busca

| Categoría (Ley 1581) | Tipo | Confianza | Cómo lo reconoce |
|---|---|---|---|
| Personal (art. 3 c) | Cédula de ciudadanía o de extranjería | 95 | El número con su rótulo («C.C.», «cédula», «identificado con») |
| Personal | Pasaporte | 90 | El número con su rótulo |
| Personal | Fecha de nacimiento | 90 | La fecha con su rótulo |
| Personal | Cuenta bancaria | 90 | «Cuenta de ahorros/corriente» y el número |
| Personal | Tarjeta | 85 | Con su rótulo y la verificación de Luhn |
| Personal | Celular | 80 | Número colombiano de 10 dígitos que empieza por 3, con o sin +57 |
| Personal | Correo | 75 | Cualquier correo, menos buzones institucionales (contacto@, notificaciones@…) |
| Personal | Dirección | 60 | Nomenclatura urbana (Calle 45 # 12-30) |
| Sensible (art. 5) | Salud | 70 a 90 | Historia clínica, diagnóstico con código CIE-10, incapacidad médica, VIH… |
| Sensible | Origen étnico, opinión política, religión, sindicato, vida sexual, biométricos | 60 a 70 | Expresiones que se refieren a una persona («afiliado al sindicato», «huella dactilar»…) |
| Menores (art. 7) | Tarjeta de identidad | 95 | El número con su rótulo («T.I.») |
| Menores | NUIP o registro civil de nacimiento | 70 | Con su rótulo |
| Menores | Mención de un menor | 70 | «menor de edad», «el menor Juan» (con nombre propio) |

La confianza es fija por regla: un número con su rótulo es más seguro que una palabra suelta.

Las reglas evitan a propósito expresiones frecuentes en documentos ambientales que no son datos personales, y
hay una prueba para cada una:
- «el menor impacto ambiental»;
- «el fenómeno de El Niño»;
- «diagnóstico ambiental de alternativas»;
- números de radicado largos;
- valores en pesos.

## Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Con qué se detecta | Motor de IA externo / reglas en el servidor | Reglas en el servidor | Enviar el texto a un servicio externo para buscar datos personales sería una transferencia de esos datos (Ley 1581, art. 26). Las reglas son explicables: cada hallazgo dice qué regla lo encontró | Las reglas no entienden el contexto: no saben si un nombre suelto es de una persona. Por eso no buscan nombres: eso lo hace la descripción |
| Si se buscan nombres de personas | Sí / no | No | Un archivo está lleno de nombres de servidores públicos que firman en ejercicio de su cargo, y eso no es un dato reservado. Marcar cada nombre volvería la revisión inmanejable | Un nombre ligado a un dato sensible solo se detecta por el dato sensible |
| Qué se guarda del dato | El dato / su posición, una muestra enmascarada y una huella con clave | Posición, muestra y huella | No se crea una segunda copia de los datos personales fuera del archivo. La huella con clave del servidor sirve para reconocerlo al volver a revisar, y no se puede revertir probando números | Si cambia la clave secreta del servidor (RICORA_SECRET_KEY) y el texto se vuelve a revisar, los hallazgos ya decididos no se reconocen y reaparecen como pendientes; los anteriores no se pierden |
| Hallazgos repetidos | Uno por aparición / uno por dato | Uno por dato, con todas sus apariciones | La misma cédula diez veces es una sola decisión | — |
| Qué pasa con lo pendiente | Solo avisar / no dejar publicar | No dejar publicar | El requerimiento pide que cada hallazgo se confirme, corrija o descarte. Un aviso se ignora | Más pasos al describir. Se mitiga con reglas estrictas y motivos de descarte ya escritos |
| Nivel de la descripción | Lo fija el sistema / lo declara la persona | La persona, con un mínimo | Lo confirmado fija el mínimo: no se puede declarar menos. La persona puede declarar más (lo que las reglas no ven) | — |
| Alerta en el panel | Por cualquier hallazgo / solo sensibles o de menores | Solo sensibles o de menores | Los datos personales comunes son frecuentes y se revisan al describir. Los sensibles y de menores necesitan atención antes | — |
| Contenido de la alerta | Con el dato / sin el dato | Sin el dato | El panel de alertas lo ve más gente que la pantalla de descripción | — |
| Descartar | Sin motivo / con motivo | Con motivo | Lo que no se publica por una decisión humana tiene que poder explicarse en una auditoría | — |

## Lo que esta fase no hace (y queda pendiente)

- **Anonimizar la versión de consulta.** Si un documento público tiene datos personales confirmados, hoy se
  advierte y se exige clasificarlo; el sistema todavía no tacha el dato en la imagen de la página ni en el texto
  público. Es lo que sigue naturalmente: ya se sabe en qué página y en qué posición está cada dato confirmado.
- **El motor de descripción (Gemini) recibe el texto completo del documento.** Esto es independiente de esta
  detección, pero tiene que estar en la política de tratamiento de datos de la entidad: es una transmisión a un
  encargado fuera del país. Si la entidad no lo autoriza, la descripción de documentos con datos sensibles o de
  menores debe hacerse sin el motor.
- **Documentos sin texto** (una foto sin OCR útil): la pantalla lo dice y la revisión es manual.
- **El OCR también se equivoca**: un número mal leído no se detecta. Con confianza de OCR baja, la revisión
  humana del documento sigue siendo necesaria.

No cargue documentos con reserva legal mientras el servidor no tenga HTTPS.
