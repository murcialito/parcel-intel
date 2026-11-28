# ADR 0054 — Tabla de convergencia de fuentes: valores cerrados, una fila por fuente en orden fijo, «Aparece» con el criterio del ADR 0025 y «Sin cobertura» solo si la fuente no cubre

- Estado: aceptada
- Fecha: 2026-11-28 (diseño del 2026-11-27)
- Historia: #240 (feature #198, épica #4)
- Relacionados: ADR 0025, 0030, 0041, 0042, 0043, 0044, 0048, 0049, 0052
- Número: el diseño lo dejaba como «el siguiente libre»; al crearlo, el último era el 0053.

## Contexto

La prueba de un camino público sale de que varias fuentes independientes coincidan. La ficha de un indicio
(ADR 0044) o de un tramo a verificar (ADR 0048) solo cita las dos fuentes que se compararon. La #198 pide,
para cada tramo, una tabla con lo que dice cada fuente, sin emitir ningún dictamen. El fundador decidió el
2026-11-27 (#198):

1. Las ortofotos solo dicen «Imagen disponible» o «Sin cobertura», con el enlace de #172. «Aparece» o
   «No aparece» sobre una imagen lo dirá una persona, más adelante.
2. El texto público: título, cuatro valores, aviso y rótulo de Catastro.
3. La tabla va en los indicios y en los tramos a verificar.

Ya existen el criterio de coincidencia y las tolerancias por fuente (ADR 0025), las capas municipales, las
unidades históricas con su afín (ADR 0043) y las imágenes de comparación validadas (ADR 0049). El
dominio solo puede usar stdlib.

Después del diseño, el fundador pidió en #240 que el umbral del 50 % quede documentado y sea configurable
«de alguna forma»; se recoge en la decisión 3.

## Decisión

1. **Entidad** `ConvergenceTable` en `domain/convergence.py`, con filas `ConvergenceRow`. Son dataclasses
   congeladas con una lista blanca cerrada de campos:
   - fila: `source_key`, `label`, `evidence_kind`, `value`, `years`, `consulted_on`, `links`, `attributions`;
   - tabla: `stretch_id`, `municipality_code`, `title`, `rows`, `warning`, `method`, `criterion`,
     `appears_min_fraction`.

   No llevan geometría, objetos de procedencia ni identificadores de trazado o de parcela.
2. **Valores cerrados**: `aparece`, `no_aparece`, `sin_cobertura` e `imagen_disponible`, con los textos
   validados por el fundador.
   - Las filas de trazado solo admiten los tres primeros.
   - Las de imagen, solo `imagen_disponible` y `sin_cobertura`.
   - Una fila `sin_cobertura` no lleva año, fecha, enlaces ni atribución.
3. **«Aparece»** reutiliza `compare_trail` sin cambiarlo. El tramo es el sujeto, con la fuente de la que
   sale. Los trazados de la fuente de la fila son las contrapartes, con el prefiltro exacto de rejilla del
   ADR 0030. Aparece si `compare_trail` no ve discrepancia, o si ve un `SOLAPE` con
   `fraccion_solapada ≥ APPEARS_MIN_FRACTION` (0,5). Es decir: al menos la mitad del tramo tiene un trazado
   de esa fuente a menos de la tolerancia del par. Un `DESPLAZAMIENTO` o una `AUSENCIA` dan «No aparece».
   - **Configurable** (petición del fundador): `APPEARS_MIN_FRACTION` es el valor por defecto del
     parámetro `appears_min_fraction` de `appears`, `layer_row`, `historic_row`,
     `build_convergence_table` y del constructor de `BuildConvergenceTablesUseCase`. Admite cualquier
     número en (0, 1]. Cada tabla anota en `appears_min_fraction` el umbral con el que se calculó, para
     que un resultado con otro umbral se pueda rastrear. Cambiar el valor por defecto sube
     `CONVERGENCE_METHOD`.
4. **«Sin cobertura» solo cuando la fuente no cubre el tramo**, nunca por un fallo nuestro:
   - Capas municipales (vía pecuaria, camino actual, Catastro): una capa cargada cubre todo el término. Si
     no hay capa (`TrailLayerUnavailableError`), «Sin cobertura».
   - Históricas: cubre la envolvente convexa de los puntos de control retenidos de cada unidad aceptada,
     transformada con su afín (`unit_footprint`). Fuera de ella el ADR 0043 no admite trazados. Hay
     «No aparece» solo si todas las muestras del tramo (paso del ADR 0025) caen dentro de alguna envolvente.
     «Aparece» por un trazado aprobado vale aunque el tramo salga en parte de la envolvente. Los trazados
     propuestos o rechazados nunca cuentan: `HistoricCoverage` rechaza construirse con ellos, y también
     con un trazado que no pertenece a ninguna de sus unidades (id `<unit_id>-<trazado>`).
   - Ortofotos: «Sin cobertura» solo si la franja figura en el manifiesto como omitida `sin_cobertura`,
     incluida la imagen en blanco. Un tramo ausente del manifiesto, demasiado largo o incoherente con él, o
     una franja omitida por `fallo`, deja al tramo **sin tabla** con un motivo fijo. Un manifiesto de otro
     municipio, de otra política o con otros huecos hace fallar el municipio entero
     (`ConvergenceNotComputableError`).
5. **Ortofotos: una fila por franja de `COMPARISON_SLOTS`** (orden cronológico de #172). Muestra el año o
   los años de los vuelos que se ven en las ventanas del tramo y sus enlaces, sacados de
   `build_published_comparison` con todas sus comprobaciones. Cada franja ya es «el vuelo que hay» en ese
   periodo (ADR 0042), así que se cumple la «fila por vuelo» de #198 sin inventar filas para vuelos que no
   se pidieron. Las atribuciones de la fila son las de sus imágenes y, detrás, el aviso obligatorio de la
   fuente cuando lo tiene (IDEM, ADR 0052), sin repetir. El trazo de las imágenes de un tramo lo define
   solo `image_axis`: la multilínea tal cual o, en una franja, su pseudo-eje del ADR 0025.
6. **Año** («de qué año»):
   - Capas municipales: el intervalo de `data_date` de todos sus trazados, o «año no declarado» si
     ninguno la tiene.
   - Históricas: el intervalo de `document_date` de las unidades que contienen el tramo.
   - Ortofotos: el periodo de los vuelos mostrados.

   La fecha de consulta va aparte y es obligatoria en Catastro (ADR 0041 §2.1).
7. **Catastro**: rótulo «Catastro: vía de comunicación» y siempre la atribución
   `public_card.CATASTRO_ATTRIBUTION`, que avisa de que no es fehaciente. Un «Aparece» dice que el tramo
   coincide con parcelas que Catastro clasifica como vía de comunicación, sin alterar su sentido
   (ADR 0041 §2.4). No sale nada de la parcela (ADR 0041 §3-§4).
8. **Orden fijo de filas** (`CONVERGENCE_ROW_SOURCES`):
   1. vía pecuaria oficial;
   2. camino actual (IGN);
   3. Catastro;
   4. planimetría del IGN;
   5. MTN50, primera edición;
   6. una fila por franja de ortofoto, en el orden de `COMPARISON_SLOTS`.

   Una fuente nueva se añade a la lista sin cambiar ninguna fila existente:
   - un tipo histórico nuevo (#221) va tras el MTN50;
   - una franja nueva de #208 entra en su sitio cronológico.

   Un test obliga a que cada `HistoricDocumentKind` tenga su fila.
9. **Texto**: título, valores, aviso y rótulo de Catastro llevan una huella SHA-256 con la fecha y el
   enlace de la validación del fundador, igual que #16 (`CONVERGENCE_TEXT_VALIDATION`). Ningún texto de la
   tabla puede contener:
   - las palabras vetadas de `public_card`;
   - «es público»;
   - la palabra «corte» (entera: «recorte» no cuenta).

   Se exceptúa el aviso fijo, que el fundador redactó con «si el camino es público». La tabla siempre lleva
   título y aviso.
10. **Versionado**: `CONVERGENCE_METHOD = ("convergencia_fuentes", 1)`. Cualquier cambio de regla, umbral
    por defecto u orden sube la versión. Cada tabla lleva además el criterio del ADR 0025 que usó.
11. **Capas**:
    - Las entidades y funciones puras viven en `domain/convergence.py`, `domain/historic_coverage.py` y
      `unit_footprint` en `domain/georeferencing.py`.
    - Hay un port nuevo, `HistoricCoverageSource` (`ports/historic_coverage.py`). Las capas municipales y
      el manifiesto usan los ports que ya existen.
    - El caso de uso `BuildConvergenceTablesUseCase` (`application/build_convergence_tables.py`) carga
      cada fuente una vez por municipio y devuelve, por tramo, una tabla o un motivo fijo (`NO_MANIFEST`
      si falta el manifiesto).

    No se escribe nada, no hay LLM y no hay red.

**A revisar con el fundador (umbrales de producto, no decisiones técnicas):**
- El 50 % del tramo que exige «Aparece» en un solape parcial (`APPEARS_MIN_FRACTION`). Ya es configurable
  (decisión 3); falta decidir si 0,5 es el valor por defecto que se publica.
- Que una unidad histórica aceptada cuente como cobertura completa de su envolvente. Así, un «No aparece»
  histórico da por hecho que quien digitalizó dibujó todos los caminos visibles dentro de ella. Si no es
  así, hay dos salidas:
  - exigir en `unidad.json` una marca de «digitalización completa»;
  - dejar las históricas en «Aparece» / «Sin cobertura».
- Los rótulos que no validó (`Vía pecuaria oficial`, `Camino actual (IGN)`, `Planimetría del IGN`,
  `MTN50, primera edición (IGN)`, `Ortofoto <franja>`) se le proponen antes de publicar en #246.

## Consecuencias

- #246 publica la tabla en la ficha de indicios y de tramos a verificar. Para eso:
  - implementa `HistoricCoverageSource`, preferiblemente desde `curated/historico/` y sin PostGIS;
  - convierte cada tramo con `stretch_from_discrepancy` (informe interno; los registros redactados no
    valen) o `stretch_from_candidate`;
  - genera las imágenes de los indicios con `image_axis`. El manifiesto es hoy un único fichero por
    municipio, el de los candidatos, así que #246 debe decidir cómo convive con el de los indicios para no
    pisarlo;
  - decide si publica `appears_min_fraction` en la ficha.
- El lector de capas de #31 añade a la red del IGN los tramos asfaltados como solo contraparte (ADR 0050).
  En esta tabla cuentan como trazado del IGN: la fila «Camino actual (IGN)» dice «Aparece» también sobre
  una carretera. #246 debe decidir si el rótulo lo explica.
- Un tramo sin manifiesto, demasiado largo o con un fallo de descarga no tiene tabla. #246 decide si eso
  bloquea la publicación (como en #172) o solo omite la tabla.
- Coste: `compare_trail` por tramo y fuente, con prefiltro de rejilla (ADR 0030). Las capas se cargan y
  se indexan una vez por municipio.
- Mientras no haya unidades históricas reales cargadas (REGISTRY.md: hoy ninguna), las filas históricas
  saldrán «Sin cobertura» en todos los tramos.
