# Cierre de dos riesgos antes del piloto (22 de octubre de 2026)

Antes de usar RICORA con datos de una entidad quedaban dos riesgos abiertos:

1. La clave del segundo factor estaba guardada en claro en la base de datos.
2. El inventario FUID, la guía y el índice se generaban cada vez que se
   consultaban: ninguno quedaba como documento aprobado, con fecha y
   responsable.

## 1. Clave del segundo factor cifrada

| Antes | Ahora |
|---|---|
| La clave TOTP en claro en `usuarios.mfa_secreto`. Quien tuviera un volcado de la base, un respaldo o el paquete de recuperación podía generar los códigos de cualquier cuenta. | La clave se guarda cifrada con AES-256-GCM (`app/core/cifrado.py`). La clave de cifrado (`RICORA_CLAVE_CIFRADO`) vive solo en el `.env` del servidor: no está en la base, ni en los respaldos, ni en el paquete de recuperación. |

Cómo funciona:

- **Cifrado autenticado.** Si alguien altera el valor guardado, el descifrado
  falla; no devuelve una clave distinta en silencio.
- **Atado a la cuenta.** El dato asociado es la columna y el identificador de
  la cuenta: copiar la clave cifrada de una persona a otra no sirve.
- **Falla cerrado.** Si la clave no se puede leer (otra clave de cifrado, valor
  alterado o sin cifrar), ningún código de la aplicación sirve. La persona entra
  con un código de respaldo, que se guarda como huella y no depende de la clave,
  o pide el restablecimiento al administrador.
- **Migración 0045.** Cifra las claves que había en claro. El despliegue genera
  `RICORA_CLAVE_CIFRADO` una sola vez, antes de la migración.

Evidencia: `tests/test_cifrado_e_instrumentos.py` (cifrada y atada a la
cuenta, otra clave falla cerrado y el respaldo sigue sirviendo, la migración
cifra lo que estaba en claro). En el servidor visual, la cuenta con segundo
factor siguió entrando después de migrar.

## 2. FUID, guía e índice aprobados como documentos

| Antes | Ahora |
|---|---|
| El FUID, la guía y el índice se armaban al vuelo. Lo descargado era una consulta del momento; nada quedaba como documento del archivo ni en el grafo. | **Aprobar como documento…** guarda el archivo tal como está, con su huella SHA-256, la fecha, quién lo aprobó y el acta (opcional). Una versión nueva reemplaza a la anterior, que se conserva. Anular exige motivo y no borra nada. |

Reglas:

- Un FUID con campos obligatorios sin dato no se aprueba (Acuerdo 042 de
  2002). Se puede exportar igual, con las celdas marcadas, pero no aprobar.
- La guía y el índice se aprueban para el fondo completo; el inventario, para
  cualquier nivel.
- El índice aprobado es el de consulta pública: sin lo clasificado ni lo
  reservado.
- Descargar comprueba la huella. Si el archivo cambió en el disco, lo dice en
  lugar de entregarlo como si fuera el aprobado.
- Anular la versión vigente devuelve la vigencia a la que había reemplazado.

En RiC-O, cada instrumento aprobado (no anulado) es un `rico:Record` con:

- su forma documental (inventario, guía o índice);
- `rico:describesOrDescribed` hacia el nivel que describe (RiC-R021);
- su fecha de aprobación;
- su archivo como `rico:Instantiation`, con la huella en `rico:authenticityNote`;
- `rico:precedesOrPreceded` de cada versión a la siguiente (RiC-R008).

Así el sistema describe también su propia descripción, como ya hacía con el
cuadro de clasificación y la TRD. Si el nivel descrito es reservado, el
instrumento no sale en la exportación pública.

Evidencia: `tests/test_cifrado_e_instrumentos.py` (FUID incompleto rechazado,
archivo con huella y acta, archivo alterado detectado, versiones y anulación,
guía e índice, permisos, exportación conforme a OWL y SHACL).

## Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Biblioteca de cifrado | Implementación propia; `cryptography` | `cryptography` (AES-GCM y HKDF) | Ya estaba en la imagen como dependencia de `pdfminer.six`; la decisión anterior suponía que no había ninguna. Cifrar a mano es un error clásico. Se fija la versión en `requirements.txt`. | Una vulnerabilidad de la biblioteca: se actualiza con el resto de dependencias. |
| Dónde vive la clave de cifrado | La base; la misma clave de sesiones; una variable propia | Variable propia `RICORA_CLAVE_CIFRADO` en el `.env` | Separarla de la base protege los volcados y los respaldos, que es el riesgo real. Separarla de la de sesiones permite rotar la de sesiones sin perder el segundo factor. | Quien tenga el servidor completo (base y `.env`) puede descifrar: es el límite de cifrar en la aplicación. Perder la clave obliga a reconfigurar el segundo factor; los códigos de respaldo siguen sirviendo. |
| Clave en desarrollo y pruebas | Exigirla siempre; derivarla de la de sesiones si falta | Derivarla de la de sesiones si falta | En producción el despliegue la genera siempre; en desarrollo evita un paso más. | Un servidor instalado a mano sin la variable usa la derivada. Se documenta en `.env.example`. |
| Si no se puede descifrar | Error 500; tratar el código como inválido | Inválido (falla cerrado) | Un error de configuración no debe dejar entrar a nadie ni tumbar el ingreso. Los códigos de respaldo y el restablecimiento siguen disponibles. | La persona no sabe por qué falla su código; queda en el registro del servidor para el administrador. |
| Bajar la versión (downgrade) | Volver a guardar en claro; dejarla cifrada | Dejarla cifrada | Deshacer una medida de seguridad no es una reversión válida. | Quien baje de versión debe restablecer el segundo factor de las cuentas. |
| FUID con pendientes | Aprobar igual; no aprobar | No aprobar | Un inventario aprobado es un instrumento oficial: con campos obligatorios vacíos no cumple el Acuerdo 042. | Un fondo con datos que nunca se van a conocer (caja perdida) no se puede aprobar hasta anotarlo en Notas o en Otro. |
| Formato del índice aprobado | JSON; hoja de cálculo; PDF | Hoja de cálculo | Se lee sin herramientas especiales y es el mismo formato del FUID. PDF/A exigiría otra dependencia. | Una hoja de cálculo se puede editar fuera del sistema; la huella delata cualquier cambio frente al aprobado. |
| Quién aprueba | Solo administración; quien escribe en Instrumentos | Quien escribe en Instrumentos, con el acta del comité | La aprobación formal la da el comité de la entidad; el sistema registra quién la ingresó y con qué acta. | Que alguien apruebe sin acta. El acta es opcional para no bloquear el piloto; la auditoría registra quién lo hizo. |
| Vista del índice para el equipo interno | Seguir ocultándola; mostrarla a quien aprueba | Mostrarla a quien genera instrumentos | Para aprobar el índice hay que verlo. | Ninguno relevante. |
