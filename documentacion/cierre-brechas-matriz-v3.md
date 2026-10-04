# Cierre de brechas de la matriz maestra v3.0

Base: la auditoría del 4 de octubre de 2026 (`RICORA_MATRIZ_MAESTRA_REQUISITOS_v3_0_auditada.xlsx`). En esa fecha, de los 51 requisitos, 30 cumplían, 18 eran parciales, 1 no cumplía y 2 no existían.

## Cómo se trabaja

1. **Se cierra por lotes**, del riesgo más alto al más bajo, y cada brecha con su prueba automatizada.
2. **Un requisito pasa a CUMPLE solo con evidencia**: el archivo y la prueba que lo demuestra. Lo que queda pendiente se dice; no se presenta como cerrado.
3. **Cada lote actualiza la matriz**: estado, evidencia y riesgo residual, en la hoja «Cierres».
4. **Cada lote se despliega con el CI en verde.**

## Lote 1 · Seguridad y operación

| Requisito | Antes | Después | Qué se hizo | Evidencia |
|---|---|---|---|---|
| RF-SEC-003 Segundo factor | No existe | Cumple | TOTP (RFC 6238) sin dependencias nuevas, con 8 códigos de respaldo de un solo uso (solo se guardan sus huellas). Un código usado no vuelve a servir. Ingreso en dos pasos con un desafío de 5 minutos que no sirve como token de acceso. Obligatoriedad por rol desde **Usuarios › Roles**; si el rol lo exige, la persona solo entra a Mi perfil hasta configurarlo. El administrador lo restablece si alguien pierde el teléfono, con auditoría | `app/core/doble_factor.py`, `app/routers/auth.py`, migración `0033`, `tests/test_brechas_lote1.py` (vectores del RFC 6238, ingreso en dos pasos, rol obligatorio, restablecimiento) |
| RF-AUD-002 Proteger la auditoría | Parcial | Cumple | Cada evento guarda la huella SHA-256 de su contenido unida a la del anterior, calculada por la base de datos al insertar y bajo un candado. Si alguien desactiva el disparador y altera o borra un evento, la cadena se rompe desde ahí. Ruta `GET /api/auditoria/cadena`. La revisión semanal guarda el sello (último eslabón) y Auditoría muestra si la cadena está íntegra | migración `0032`, `app/servicios/auditoria.py::verificar_cadena`, `tests/test_brechas_lote1.py` (alterar y borrar con el disparador desactivado) |
| RF-OPS-001 Salud, respaldos, métricas | Parcial | Parcial (avanza) | `/api/salud` revisa de verdad la base de datos (con la migración vigente), el almacén (existe, se escribe, espacio libre), el latido del trabajador y el último respaldo probado. Solo la caída de la base da 503; lo demás marca «degradado» con el motivo y no expone datos | `app/servicios/salud.py`, `app/trabajador.py`, `tests/test_brechas_lote1.py::test_salud_dice_que_falta_y_solo_la_base_tumba_el_servicio` |
| NFR-10 Observabilidad | Parcial | Parcial (avanza) | Un monitor externo gratuito puede consultar `/api/salud` sin sesión | ídem |
| NFR-01 Seguridad | Parcial | Parcial (avanza) | Segundo factor y auditoría encadenada | ídem |

### Decisiones del lote 1

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Tipo de segundo factor | SMS; correo; TOTP; llaves físicas (WebAuthn) | TOTP | Gratis, funciona sin red en el teléfono, tiene aplicaciones libres (Aegis, FreeOTP) y no depende de un operador. El SMS es inseguro y cuesta; WebAuthn exige HTTPS y llaves | Perder el teléfono: se resuelve con los códigos de respaldo o con el restablecimiento del administrador |
| Biblioteca para TOTP | pyotp; implementación propia | Implementación propia (unas 40 líneas con `hmac`) | No agrega dependencias a la imagen. Se prueba contra los vectores oficiales del RFC 6238 | Un error de implementación; lo cubren los vectores del RFC |
| Secreto TOTP en la base | Cifrado; en claro | En claro en la columna, nunca devuelto ni auditado | No hay biblioteca de cifrado en la imagen y cifrar con una clave del mismo servidor protege poco: quien lee la base suele leer también la configuración | Robo de la base: el atacante podría generar códigos. Mitigación pendiente: cifrar con una clave externa |
| Obligatoriedad | Fija para administradores; parámetro por rol | Parámetro por rol, vacío por defecto | Cada entidad decide. Encenderlo para el administrador obliga a configurarlo en el siguiente ingreso | Que nadie lo encienda: **recomendación: exigirlo al rol administrador en producción** |
| Quién calcula la cadena | La aplicación; la base de datos | La base de datos (disparador) | Ningún módulo puede olvidarse de encadenar ni hacerlo distinto. El orden se asigna bajo un candado, así que transacciones simultáneas no bifurcan la cadena | Las escrituras de auditoría se hacen de una en una: aceptable para el volumen de un archivo |
| Anclaje externo | Ninguno; servicio de sellado de tiempo; sello en la revisión semanal | Sello en la revisión semanal y visible en Auditoría | Sin costo. Quien revisa anota el sello y queda en la exportación a Excel. Si alguien rehace toda la cadena, el sello anotado deja de coincidir | El dueño de la base podría rehacer la cadena entera entre dos revisiones; el sello anotado fuera lo delata |
| Código HTTP de la salud | 503 ante cualquier falla; solo ante la base | Solo ante la base | Un trabajador detenido o un respaldo atrasado no impiden consultar ni describir. Tumbar el servicio por eso haría más daño | Un monitor que solo mire el código no verá lo «degradado»: debe leer `estado` |

## Pendiente (lotes siguientes)

| Lote | Requisitos | Qué falta |
|---|---|---|
| 2 · Recuperación | NFR-04, NFR-07, RF-OPS-001 | RPO/RTO por escenario; respaldo del almacén de archivos fuera del servidor; simulacro completo (base + archivos + configuración) en un entorno nuevo; métricas |
| 3 · Endurecimiento | NFR-01 | Quitar la caída a HTTP; cabeceras CSP y HSTS; no restablecer la contraseña del administrador en cada despliegue |
| 4 · Búsqueda | RF-SEARCH-001/002 | Buscador de texto completo (PostgreSQL) sobre texto, metadatos e identificadores, que respete la Ley 1712 |
| 5 · Evidencia de la IA | RF-AI-002, RF-OCR-001 | Propuesta del motor como registro propio con fecha y versión; página y bloque de cada fragmento |
| 6 · Versiones y API | RF-RIC-001/002, RF-INT-003 | Versiones consultables de cada descripción; esquemas de respuesta en OpenAPI con prueba |
| Fuera de alcance (propuesto) | RF-GOV-001, NFR-05 | Varias organizaciones en un solo sistema y escalado horizontal: decisiones propias, no del AGN, sin valor para el piloto de la tesis |
