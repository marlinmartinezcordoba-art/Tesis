# Perfil RiC-Col del AGN aplicado a RICORA

**Fuente:** Archivo General de la Nación, *Esquema de Metadatos para las Entidades Públicas Colombianas*, versión 1.4 (31 de octubre de 2025).

- Es una adaptación de RiC-CM 1.0 bajo licencia CC BY 4.0.
- El documento se declara instrumento técnico de referencia, no obligatorio salvo que el AGN lo adopte por acuerdo, y propuesta preliminar sujeta a pilotos (pp. 6-7 y 79).

**Especificación que lo pide:** *RICORA – Especificación integral v3.0*, secciones 7 y 22:

- separar el modelo internacional, la adaptación del AGN y las extensiones propias;
- entregar un catálogo AGN ↔ RiC ↔ RICORA.

## 1. Qué se implementó

| Pieza | Dónde | Prueba |
|---|---|---|
| Catálogo de 57 correspondencias en tres capas (RiC, AGN, RICORA). Cada fila tiene el código tal como lo cita el AGN y la correspondencia correcta | `app/servicios/perfil_agn.py` | `tests/test_perfil_agn.py::test_cada_termino_rico_del_perfil_existe_en_el_owl_oficial`, `::test_cada_codigo_ric_cm_citado_como_correcto_es_real` |
| 13 erratas del esquema del AGN, con página y corrección | `perfil_agn.ERRATAS` | `::test_catalogo_y_excel_por_la_api` |
| Consulta y descarga por API, sin pantalla: `GET /api/calidad/correspondencias` y `/api/calidad/correspondencias.xlsx` | `app/routers/perfil_agn.py` | ídem |
| Calidad de metadatos por descripción y por fondo, en tres niveles de madurez (básico, intermedio, avanzado), con avisos e incoherencias. Rutas: `/api/calidad/descripciones/{id}` y `/api/calidad/fondos/{id}` | `perfil_agn.calidad`, `calidad_fondo` | `::test_productor_heredado_del_nivel_superior_y_kpi_del_fondo` |
| Estado de conservación (bueno, regular, malo, restaurado) y signatura topográfica (depósito, estante, entrepaño) del original físico, con corrección auditada | migración `0031`; `descripcion.registrar_original_fisico`, `actualizar_original_fisico`; `PATCH /api/descripcion/registros/{id}/original-fisico/{inst}` | `::test_original_fisico_con_estado_y_signatura_se_corrige_con_auditoria_y_sale_en_rico` |
| Datos personales (Ley 1581: no contiene, personales, sensibles, de menores) y nota de accesibilidad (Ley 1680) en la descripción | `recursos_documentales.datos_personales`, `nota_accesibilidad`; campo `proteccion` al publicar y al corregir | `::test_datos_sensibles_en_documento_publico_es_incoherencia_y_la_nota_de_accesibilidad_es_publica` |
| ORCID (personas) y ROR (instituciones), con dígito de control y `owl:sameAs` | `autoridad.orcid_normalizado`, `ror_normalizado`, `URI_EXTERNA` | `::test_orcid_y_ror_con_digito_de_control_y_tipo_de_agente` |
| En la interfaz no hay un módulo del AGN: sus reglas viven en el flujo normal. El formulario de descripción (al publicar y al corregir) tiene los datos personales y la versión accesible, y avisa en el mismo formulario si quedarían datos sensibles en público. La ficha de cada descripción muestra el original físico y la tarjeta «Completitud de la descripción». El resumen del fondo, en Instrumentos › Catálogo, muestra la completitud de todas las descripciones | `frontend/src/components/DescripcionV3.tsx`, `frontend/src/components/PerfilAgn.tsx` | `frontend/src/pruebas/navegacion.test.tsx` |

## 2. Decisiones

| Decisión | Alternativas | Selección | Justificación | Riesgo |
|---|---|---|---|---|
| Qué manda en los códigos | Copiar los códigos del AGN; usar los de RiC-CM 1.0 y RiC-O 1.1 | RiC-CM 1.0 y RiC-O 1.1, guardando el código del AGN como dato | El esquema del AGN cita 41 códigos que no corresponden: P del borrador de 2016, relaciones que no existen y propiedades `ric:` inexistentes. Copiarlos rompería la conformidad que ya se valida con OWL y SHACL | Que un evaluador espere ver los códigos del AGN. Se mitiga mostrando ambos, con el del AGN tachado |
| Obligatoriedad | Bloquear la publicación si falta un campo «obligatorio» del AGN; solo medir | Medir y avisar | El AGN dice que su esquema no es obligatorio y que su adopción es gradual por madurez | Que la calidad no mejore. La vista por fondo hace visibles las brechas |
| Formato de identificador `CO-{ENTIDAD}-{SERIE}-{NÚMERO}` | Imponerlo; generarlo; no adoptarlo | No se impone; se avisa si pasa de 50 caracteres | El código obligatorio es el del CCD (Acuerdo 001 de 2024), que RICORA ya compone desde el nivel superior. El formato del AGN es un ejemplo | Sin riesgo legal |
| Título de 255 caracteres | Reducir la columna; avisar | Avisar | ISAD(G) no limita la longitud y hay títulos formales largos | Ninguno |
| Idioma ISO 639-2 con «spa» por defecto | 639-2; 639-3 | Se mantiene ISO 639-3, sin valor por defecto | «spa» coincide en ambos. 639-3 distingue lenguas indígenas colombianas que 639-2 agrupa. El idioma lo confirma una persona, no un valor por defecto | Intercambio con sistemas que solo admitan 639-2. Se mitiga con la equivalencia directa en «spa» |
| Vocabulario COAR | Adoptarlo junto a la TRD; no adoptarlo | No se adopta | COAR clasifica recursos de repositorios académicos (artículo, tesis), no tipos documentales de archivo | Que el AGN lo vuelva obligatorio por acuerdo. Se agregaría como `skos:exactMatch` |
| Estado de conservación en RiC-O | Propiedad propia; nota de características físicas | Dentro de `rico:physicalCharacteristicsNote` (RiC-A31) | RiC-CM define Physical Characteristics como la apariencia y el estado físico. El AGN cita «RiC-A17», que es Documentary Form Type | Ninguno: es RiC-O oficial |
| Signatura topográfica en el RDF | Inventar una propiedad; no exportarla | Se guarda y se muestra, pero no va al RDF | RiC-O 1.1 no tiene una propiedad de dato para la ubicación de una instanciación (Physical Location es del Lugar). Queda en la ficha, el inventario y la ficha ISAD(G) | Pérdida en el intercambio RDF; queda contada en las omisiones de la exportación |
| Datos personales (Ley 1581) | Mezclarlos con la clasificación de la Ley 1712; campo separado | Campo separado, que avisa si el documento es sensible y público | Son dos normas distintas: un documento público puede contener datos personales que se anonimizan al consultarlo | Que se marque «sensibles» y se deje público. Aparece como incoherencia en la ficha y en el fondo |
| Datos personales en el RDF y en la ficha pública | Exportarlos; no | No se exportan ni se publican | Principio de minimización (Ley 1581) que el propio AGN cita | Ninguno |
| Nota de accesibilidad | Interna; pública | Sale en la ficha pública | Ley 1680: quien consulta debe saber si hay versión accesible antes de pedir el documento | Ninguno |
| Dónde vive el perfil | Módulo o vista propia; lógica dentro del flujo | Lógica dentro del flujo: campos en el formulario de descripción, avisos en el formulario, completitud en la ficha y en el resumen del fondo; las correspondencias y las erratas, solo por API y en los anexos | Lo pidió la usuaria: el AGN es una regla del trabajo, no un lugar al que ir. Así no se crea otra base de datos (especificación §21) | Quien consulte el sistema no ve el catálogo de correspondencias. Queda en la documentación y en la matriz |

## 3. Lo que sigue pendiente frente al AGN

| Elemento | Estado | Qué falta |
|---|---|---|
| Perfiles de aplicación por tipología (expediente contractual, judicial, pensional) | Ausente | Plantillas de campos por tipo documental de la TRD |
| Firma digital (Ley 527 de 1999; Decreto 2364 de 2012) | Ausente | Validar firmas PAdES/X.509 y registrar el resultado en la nota de autenticidad |
| Técnica de producción (manuscrito, mecanografiado, impreso) | Parcial | Vocabulario y atributo en la instanciación (RiC-A33) |
| Copia entre documentos descritos (RiC-R012) | Parcial | Relación `has_copy` entre Record Resources |

## 4. Erratas del esquema del AGN

Las 13 erratas, con su página y su corrección, están en `perfil_agn.ERRATAS`. Se consultan por API (`/api/calidad/correspondencias`) y en la hoja «Erratas_AGN» de la matriz auditada. Lo esencial:

- versión de RiC-CM mal fechada y contradictoria;
- códigos de entidad, atributo y relación del borrador de 2016;
- propiedades `ric:` que no existen en RiC-O 1.1;
- Record State usado como vigencia;
- la NTC 4095 confundida con la ISO 23081;
- ejemplos XML que no son RiC;
- comentarios de revisión que quedaron en el texto publicado.
