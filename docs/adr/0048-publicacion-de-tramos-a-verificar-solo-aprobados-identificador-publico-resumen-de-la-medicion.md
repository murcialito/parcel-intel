# ADR 0048 — Publicación de los tramos a verificar: solo aprobados, identificador público, resumen de la medición y capa `candidatos` en el índice

- Estado: aceptada
- Fecha: 2026-11-27
- Historia: #170 (feature #103). Consumidores: #171 (visor) y #172 (imágenes en la ficha). Amplía los ADR 0044 y 0047. Aplica los ADR 0039 §7 y §9, 0041 y 0036.

## Contexto

El fundador decidió en #103 (2026-11-27) publicar los candidatos a corte de Colmenar de Oreja sin umbral numérico:
- solo los aprobados a mano (#168, ADR 0047);
- con la ficha validada de #169;
- con el resumen de la medición de #111 tal cual, más «revisado a mano»;
- y negándose a publicar sin un informe de medición de la misma versión del método.

Faltaba decidir el formato del fichero, el identificador público, qué es un informe de medición válido, dónde vive la lista de municipios publicables y cómo entra la capa en el índice.

Con los datos reales, `medir-candidatos` no leía el fichero de Colmenar. El conjunto de validación no tiene casos allí: los dos del ámbito son de Aranjuez. Su `metodo_candidatos` salía vacío y la regla del fundador habría impedido publicar siempre.

## Decisión

1. **Solo aprobados vigentes.** `publicar-candidatos` reconcilia candidatos y revisiones (`reconcile`) y ejecuta `check_candidate_approvals_current` antes de nada. Una aprobación caducada o una revisión huérfana hacen fallar el municipio. Sin ningún aprobado también falla: no se escribe un fichero vacío.
2. **Informe de medición válido**, decidido en el dominio (`summarize_measurement`). Debe ser de un conjunto congelado, con etiqueta, con `metodo_candidatos` exactamente igual a `[<método>@<versión>]` de los candidatos del municipio, `cota: inferior` y recuentos coherentes con sus cocientes. Un informe no congelado se rechaza (lado seguro). Un informe que mezcla versiones también.
3. **Resumen redactado en el fichero.** La colección lleva `medicion` con fecha, conjunto, método, recuentos enteros (casos en el ámbito = `casos_total` − `fuera_del_ambito`; evaluables; señalados; candidatos evaluables; que casan), los dos porcentajes como texto («N %» redondeado a entero desde los recuentos, o «no calculable» si el denominador es 0; nunca un decimal) y cuatro frases fijas:
   - «Casos de validación señalados: {senalados} de {evaluables} evaluables ({cobertura}).»
   - «Tramos que casan con un caso: {aciertos} de {evaluables} evaluables; precisión como cota inferior: {precision}.»
   - «Solo {casos} casos en el ámbito, no es una estadística.» (con 1: «Solo 1 caso en el ámbito, no es una estadística.»)
   - «Medición del {fecha} con el conjunto {conjunto} y el método {metodo}.» (fecha `dd/mm/aaaa`; método `<identificador> v<versión>`)

   Y `revisado_a_mano`: «Revisado a mano: cada tramo publicado lo ha aprobado una persona tras mirarlo.» El visor lo muestra tal cual y no calcula nada.
4. **Identificador público**: los 16 primeros hex del sha256 del JSON canónico de método y versión, municipio, fuente del trazado A y tramo redondeado a 0,1 m en EPSG:25830, con sufijo `-2`, `-3`… por orden de `candidate_id` si colisiona. No usa `trail_id`, `candidate_id` ni la huella: solo datos que ya se publican.
5. **Lista blanca cerrada.** De cada tramo salen el id público, la geometría del tramo del trazado A en EPSG:4326 y la ficha de #169: `etiqueta`, `texto`, `aviso`, `confianza` en palabras, `evidencia` con el formato de #94 y `aviso_omision`. No salen la huella, el `candidate_id`, la confianza numérica, las fracciones, las condiciones, los registros base, los datos de revisión ni nada de parcelas. La geometría sale con `shape_to_geojson`, como los indicios de #94: `LineString` si el tramo tiene una pieza y `MultiLineString` si tiene varias.
6. **Licencia del trazado A.** Su fuente debe estar en `REDISTRIBUTABLE_SOURCES`, la ficha no puede llevar aviso de omisión y su procedencia debe pasar `PublishableLayer`. Si no, **falla el municipio** (no se omite en silencio): un aprobado no publicable es un error de revisión que debe verse.
7. **Municipios publicables**: `CANDIDATE_PUBLISHABLE_MUNICIPALITIES = {"28043": "Colmenar de Oreja"}` en `domain/published_candidate.py`, con el nombre del límite del IGN. Otro código falla. Añadir uno exige verificar su código de Catastro y un ADR. No hay `--ambito`.
8. **Capa `candidatos` en el índice** vía `IndexedLayerId`/`INDEXED_LAYER_IDS`, fuera de `PUBLISHED_LAYERS` (ADR 0044 §7). Port y sink propios (`PublishedCandidateSink`, `GeoJsonPublishedCandidateSink`). Todo o nada, sin borrar lo publicado, sin simplificación. Última barrera: `CADASTRAL_REFERENCE_RE`, `PARCEL_LOCATOR_RE` y `BANNED_WORDS` sobre el fichero, su procedencia y el índice.
9. **`medir-candidatos` lee también los ficheros de los 7 municipios del ámbito**, además de los de los casos. Sus candidatos sin casos cuentan como no evaluables. Así `metodo_candidatos` registra lo que de verdad se midió (ADR 0039 §9) sin cambiar cobertura ni precisión.
10. **CLI** `publicar-candidatos --municipio <ine> [--medicion] [--entrada] [--curated] [--salida]`, sin red, base de datos ni LLM. Sin `--municipio` sale con 1. Se ejecuta en local. La PR con `site/datos/candidatos/` la revisa el fundador.

### Umbrales y decisiones de producto a revisar con el fundador

No bloquean. Cambiarlos solo exige tocar este ADR y sus tests.

- La redacción exacta de las cuatro frases de la medición y de «revisado a mano». El fundador aprobó el contenido en #103; las frases son del arquitecto.
- Los porcentajes redondeados a entero.
- El rechazo de un informe de medición no congelado.
- Que un aprobado con trazado no redistribuible haga fallar todo el municipio en lugar de omitirse.
- Publicar, como evidencia de Catastro, la URL de la tesela WFS consultada (viene de la ficha de #169).

## Consecuencias

- Hasta que el fundador ejecute la cadena en local no hay datos reales. El visor (#171) ignora la capa mientras no esté en `CONFIG.capas`.
- La medición no se liga al contenido del fichero de candidatos, solo a la versión del método. Regenerar los candidatos con la misma versión no obliga a volver a medir, pero sí a revisar de nuevo si cambia su huella (ADR 0047).
- Subir `CUT_METHOD.version` obliga a volver a medir y a revisar antes de publicar.
- Si la Dirección General del Catastro discrepa, se retira la capa volviendo a publicar sin ella o borrando `site/datos/candidatos/` (ADR 0041, riesgo).
- `NOTICE` gana la sección de la capa y extiende la de Catastro a los tramos a verificar.
- Sin coste recurrente.
