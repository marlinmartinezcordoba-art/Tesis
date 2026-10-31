# Puesta en marcha del sistema y expertas participantes

Dos funciones para cerrar la fase de pruebas y empezar el uso real y la evaluación del objetivo 3.

## 1. Puesta en marcha: dejar RICORA en blanco

**Dónde:** Usuarios y permisos → Puesta en marcha. Solo la administración.
**Código:** `app/servicios/reinicio.py`, `app/routers/sistema.py`, `frontend/src/components/PuestaEnMarcha.tsx`.

### Qué hace, en orden

1. Muestra qué se va a borrar (con cantidades) y qué se conserva. Ver la pantalla no cambia nada.
2. Pide la contraseña de quien administra y la frase **BORRAR TODO EL CONTENIDO**.
3. Hace un **respaldo completo de la base de datos** (`pg_dump`, con su huella SHA-256). Si el respaldo falla, se
   detiene y no borra nada.
4. Vacía, en una sola orden, las tablas de contenido:
   - documentos y archivos;
   - descripciones, autoridades, relaciones y fechas;
   - CCD y TRD;
   - evaluaciones, propuestas del motor, grafos RiC-O, alertas y verificaciones.
   La orden se da sin `CASCADE`: si una tabla que se conserva dependiera de una que se borra, PostgreSQL la rechaza y
   no se borra nada.
5. Quita los parámetros que apuntaban a contenido borrado (`mecanismos_motor` y fechas de última ejecución).
6. Registra en la auditoría el evento `sistema_reiniciado`, con qué se borró y el respaldo que lo guarda.
7. Vacía los grafos en el almacén RDF y aparta los archivos en `<almacenamiento>/_retirado/<fecha>/`.

### Qué se conserva

- Usuarios y roles.
- Parámetros y datos de la institución.
- Respaldos de la base de datos.
- El **registro de auditoría completo**: la base de datos impide borrarlo, y así debe ser.
- Los tesauros cargados, salvo que se marque la casilla para borrarlos.

### Verificación

| Dónde | Qué se comprobó |
|---|---|
| Pruebas automáticas (`tests/test_reinicio.py`) | Contraseña y frase exigidas; sin respaldo correcto no se borra; queda en blanco; usuarios, parámetros y auditoría intactos; archivos apartados; solo la administración puede ejecutarlo; los tesauros, solo si se piden; toda tabla clasificada. |
| Base real de demostración, con `pg_dump` real | El respaldo pasó la verificación de su huella y contiene los datos borrados. Recuperar el contenido es posible con `pg_restore`. |

### Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo dejar el sistema en blanco | (a) Comando en el servidor; (b) función en pantalla para la administración | (b), con contraseña, frase y respaldo previo | Quien administra no tiene acceso al servidor y necesita hacerlo sin ayuda técnica. | Un uso por error. Se mitiga con la frase, la contraseña, el respaldo previo y el evento en la auditoría. |
| Principio «nada se borra, se anula» | (a) Prohibir el borrado; (b) excepción única y controlada | (b) | Lo cargado durante las pruebas no es patrimonio documental: es material de ensayo. El contenido no se pierde: queda en el respaldo y los archivos quedan apartados. | Que se use con documentos reales. La pantalla dice qué se borra y exige el respaldo. |
| Registro de auditoría | (a) Vaciarlo también; (b) conservarlo | (b) | Es inalterable por diseño (disparadores de la base y cadena de huellas). Borrarlo rompería la cadena y la afirmación de la tesis sobre trazabilidad. | La auditoría conserva eventos de la fase de pruebas. Se distinguen porque son anteriores al evento `sistema_reiniciado`. |
| Archivos | (a) Eliminarlos; (b) apartarlos | (b) | No se destruye nada sin decisión de quien opera el servidor. | Ocupan disco. Quien opera el servidor decide cuándo eliminar `_retirado`. |
| Qué tablas se borran | (a) Todas las que no se conservan; (b) lista explícita | (b) | Una tabla nueva sin clasificar hace fallar una prueba y bloquea el reinicio: nunca se borra por omisión. | Hay que clasificar cada tabla nueva. |

### Antes de presentar o de empezar el uso real

1. Ejecute la puesta en marcha **antes** de cargar los documentos de la evaluación.
2. Pida a quien opera el servidor que copie el respaldo indicado en pantalla a un lugar seguro.
3. Después cargue el CCD y la TRD, y luego los documentos.

## 2. Expertas participantes de la evaluación

**Dónde:** Evaluación → abrir una evaluación → Administración → Expertas participantes.
**Código:** `app/servicios/evaluacion_participantes.py`, modelo `Participante` (tabla `evaluacion_participantes`,
migración 0056), rutas `GET/POST /api/evaluacion/{id}/participantes` y `PUT …/participantes/{pid}`.

La pregunta problema compara la descripción del motor con la de expertas. Para que esa comparación sea válida, la
tesis debe poder decir quiénes describieron y por qué su descripción sirve de referencia.

### Qué se registra de cada experta

- La cuenta con que describe. Es la que firma sus anotaciones.
- Nombre completo.
- Profesión y máximo nivel de formación.
- Años de experiencia en archivos y años describiendo documentos históricos.
- Cargo e institución.
- Rol en la evaluación: describe, califica la propuesta, o ambas.
- Consentimiento informado, con fecha.

Cada experta recibe un código en el orden de registro: E1, E2…

### Reglas

- La evaluación no se inicia sin al menos una experta con consentimiento. La pantalla advierte que con una sola no
  se mide el acuerdo entre personas, que es el techo de la comparación.
- Solo describe quien está registrada, activa, con consentimiento y con rol de descriptora. Solo califica la
  propuesta quien tiene rol de calificadora.
- Quien anota ve solo las evaluaciones en curso en que está registrada.
- Retirar a una experta no la borra: queda la fecha de retiro y sus anotaciones enviadas siguen contando.
- Todo registro y todo cambio queda en la auditoría.

### Resultados: humano frente a máquina

- Los resultados traen la sección **«Humano frente a máquina, experta por experta»**. Para cada experta muestran:
  - su perfil;
  - los documentos que describió;
  - la F1 del motor frente a su descripción a ciegas, en entidades y en relaciones RiC;
  - la mediana de minutos, a ciegas y asistida.
- La hoja de cálculo trae la pestaña **«Expertas»**, con los mismos datos.
- En los resultados y en la hoja de cálculo las expertas aparecen **por su código, nunca por su nombre** (Ley 1581
  de 2012). El nombre solo lo ve la administración en la lista de participantes.

### Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Cómo identificar a quien describe | (a) Solo la cuenta de usuario; (b) cuenta más perfil de experta | (b) | La validez de la referencia humana depende de la formación y la experiencia, que la cuenta no registra. | Hay que registrar el perfil antes de iniciar. |
| Nombre en los resultados | (a) Nombre; (b) código | (b) | Protección de datos personales y práctica habitual de reporte en investigación. | Ninguno: la administración puede ver la correspondencia. |
| Experta sin registro | (a) Puede describir; (b) no puede | (b) | Una descripción de alguien sin perfil ni consentimiento no puede usarse como evidencia en la tesis. | Hay que registrar a todas antes de que describan. |
| Consentimiento | (a) Nota libre; (b) campo obligatorio para participar | (b) | Requisito ético de la investigación con personas. | El sistema registra la declaración; el documento firmado se guarda fuera del sistema. |
