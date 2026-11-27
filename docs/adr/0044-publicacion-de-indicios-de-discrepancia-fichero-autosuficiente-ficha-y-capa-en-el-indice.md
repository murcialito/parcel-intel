# ADR 0044 — Publicación de indicios de discrepancia: fichero de #32 autosuficiente, ficha de #16 y capa `discrepancias` en el índice

- Estado: aceptada
- Fecha: 2026-11-26
- Historia: #94 (feature #87); consumidores: #95 (visor) y #96 (ámbito completo). Amplía ADR 0030 y ADR 0036. Aplica el ADR 0041.
- Numeración: el diseño de la issue lo proponía como 0038, pero ese número (y hasta el 0043) ya estaban ocupados al desarrollar (lección #43). Es el siguiente libre.

## Contexto

El primer hito publica el mapa de trazados y sus indicios de discrepancia como ficheros estáticos (ADR 0021). #32 escribe un fichero publicable por municipio en EPSG:25830 (ADR 0030) y #16 define la ficha pública (`build_card`) con textos aprobados por el fundador. Faltaba decidir cómo llega la ficha al sitio, qué se publica de cada indicio y cómo entra la capa en el índice de ADR 0036.

El fichero publicable de #32 no basta para reconstruir la ficha. No guarda la fecha común de la capa contraparte (en un `AUSENTE_EN_FUENTE` no hay ningún trazado B del que deducirla), ni la marca de redistribución, ni el nombre del municipio. Además lleva identificadores de trazado y un `record_id` cuyo hash incluye referencias de Catastro.

Antes de desarrollar, el fundador corrigió el §3 del ADR 0035 con el ADR 0041: los indicios con Catastro como contraparte sí se publican, sin la geometría de Catastro, citando a la Dirección General del Catastro con la fecha de consulta y con aviso de no fehaciencia. El diseño de la issue los dejaba fuera; este ADR recoge la corrección.

## Decisión

1. **El fichero de #32 se hace autosuficiente.** Se añaden `nombre_municipio` en la colección, `procedencia_b` y `fecha_dato_b` en cada feature y `redistribucion` en toda procedencia. Solo se añaden claves. Un lector nuevo (`GeoJsonDiscrepancyReportReader`, port `DiscrepancyReportSource`) reconstruye el informe exacto. Escribir, leer y volver a escribir da los mismos bytes. Un fichero anterior se rechaza y hay que regenerarlo. Se descarta volver a detectar en memoria al publicar: se publicaría algo distinto de lo revisado en `data/`.
2. **La ficha sale de `build_card` sin cambios** y es lo único que se publica de cada indicio, junto con la zona del lado A reproyectada a EPSG:4326. Lista blanca cerrada: tipo, etiqueta, texto, aviso, confianza en palabras, evidencia (papel, fuente, año, origen, URL, fecha de descarga, licencia, atribución), criterio con versión, su descripción y aviso de omisión. No se publican medidas, confianza numérica, identificadores de trazado, `record_id` ni fechas por trazado.
3. **Identificador público propio**: hash de criterio, tipo, fuentes y zona redondeada (datos ya públicos), con sufijo `-2`, `-3`… si colisiona. `record_id` no se publica porque su hash contiene referencias de Catastro y es invertible por fuerza bruta.
4. **Qué indicios se publican.** La zona sale del lado A, así que su fuente debe estar en `REDISTRIBUTABLE_SOURCES` y su trazado pasa la puerta `PublishableLayer` (ADR 0028). Con Catastro en el lado A (zona redactada) se omite y se cuenta. La contraparte puede ser una fuente redistribuible o Catastro (`PUBLISHABLE_COUNTERPART_SOURCES`, ADR 0041 §1): la ficha cita su evidencia derivada, nunca su geometría (la del lado B no se publica) ni sus referencias. Un registro sin redactar con fuente A no redistribuible hace fallar la publicación.
5. **La red de transporte del IGN pasa a verificada en `SOURCE_POLICY`**, con la atribución de `NOTICE`. Su licencia está confirmada en #24 y ADR 0036 ya publica la capa. No cambia ningún texto aprobado: la marca de #16 no cubre `SOURCE_POLICY`.
6. **Atribución de Catastro (ADR 0041 §2)** en `SOURCE_POLICY["catastro_vt"]` y en `NOTICE`: cita a la Dirección General del Catastro y la licencia INSPIRE v1.0, remite a la fecha de consulta (la `fecha_descarga` de la evidencia), dice que no es un producto oficial del Catastro ni reproduce su dato original, que carece de fehaciencia y que puede haber cambiado. No usa las expresiones «cartografía catastral» ni «información catastral». Tampoco es un texto de la marca de #16.
7. **Capa `discrepancias` fuera de `PUBLISHED_LAYERS`.** Ese catálogo es de capas de trazados de una sola fuente. `IndexedLayerId`/`INDEXED_LAYER_IDS` es la única lista de directorios que entran en el índice, y los dos sinks reconstruyen el índice con ella (`read_existing_entries`). Así ningún comando borra la capa del otro.
8. **Port y sink propios** (`PublishedDiscrepancySink`, `GeoJsonPublishedDiscrepancySink`). Todo o nada y sin borrar lo publicado, como ADR 0036. Reutilizan reproyección, geometría (`shape_to_geojson`), índice, procedencia y escritura atómica. Sin simplificación. Como última barrera, el sink rechaza cualquier texto que case con la forma de una referencia catastral (`CADASTRAL_REFERENCE_RE`) o con un parámetro de URL que localice una parcela (`PARCEL_LOCATOR_RE`, ADR 0041 §4).
9. **CLI** `publicar-discrepancias [--municipio … | --ambito]`, sin red ni LLM. Informa de los indicios publicados por tipo y de los omitidos por licencia (lado A y contraparte).

### Umbrales y decisiones de producto a revisar con el fundador

- El texto de atribución de Catastro de la decisión 6. Es una redacción del desarrollador a partir de las condiciones del ADR 0041; no forma parte de los textos validados en #16.
- El rótulo de Catastro en el texto aprobado sale como «… que no aparece en trazado derivado de datos del Catastro, 2026.» (etiqueta de #16 dentro de la plantilla de #16). Se lee forzado; cambiarlo exige nueva validación.
- Mostrar la evidencia de la red del IGN con la variante 2 de atribución («Instituto Geográfico Nacional»), igual que la capa.
- La lista blanca de la ficha publicada: en concreto, no publicar medidas (longitud sin equivalente, desplazamiento mínimo y máximo) aunque son deterministas y no sensibles.
- Un municipio que se queda sin indicios conserva su fichero anterior, con un aviso en la salida, en lugar de borrarlo.
- En los datos reales las capas derivadas no declaran fecha del dato (vías pecuarias no tiene fecha por tramo y la red del IGN mezcla `fecha_alta`), así que los `AUSENTE_EN_FUENTE` reales dicen «año no declarado». Es el comportamiento aprobado de #16; poner un año exige una decisión sobre qué fecha representa a cada capa.

## Consecuencias

- Los ficheros de `data/derived/discrepancias/` escritos antes de #94 hay que regenerarlos con `discrepancias` (sin red).
- `MunicipalDiscrepancyReport` gana `municipality_name`, y la detección exige que las capas no den nombres distintos.
- Las tablas de los tests de #16 (CA6), #32 (CA3 y CA5) y #85 (CA4 y CA8) se actualizan: el IGN ya no sirve de ejemplo de fuente no verificada, la procedencia lleva `redistribucion`, la colección lleva `nombre_municipio` y la lista blanca de propiedades y de atribuciones depende de la capa.
- El visor (#95) lee la ficha ya redactada y la muestra como texto. No redacta ni calcula nada. Debe mostrar la atribución de cada evidencia (la de Catastro incluida) junto a la ficha.
- Si la Dirección General del Catastro discrepa, se retiran los indicios con Catastro como contraparte quitando `catastro_vt` de `PUBLISHABLE_COUNTERPART_SOURCES` y volviendo a publicar (ADR 0041, riesgo). Hoy no hay ninguno en los datos reales: ningún comando escribe todavía `data/derived/catastro_caminos/` (#29).
- Sin coste recurrente: ficheros estáticos en GitHub Pages.
