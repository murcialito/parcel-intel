# ADR 0038 — Arnés de evaluación de candidatos: casamiento por fracción del tramo del caso, motivos de no evaluable y métricas no calculables

- Estado: aceptada
- Fecha: 2026-11-26
- Historia: #110 (feature #100, épica #5)

## Contexto

`docs/vision.md` pide medir el detector de candidatos a corte con cobertura (casos
documentados que aparecen como candidatos) y revisar a mano el resto, con un conjunto
congelado antes de ajustar umbrales. El conjunto `validacion-v1` (#54) tiene 6 casos: 2 del
ámbito y 4 de la Comunidad, y ninguno trae `tramo_linea`. La señal del detector (#99, #109)
aún no existe. Hace falta un arnés que no dependa de ella y que fije **antes de medir** cuándo
un candidato "es" un caso.

## Decisión

1. **Entrada mínima propia**: `ValidationCase` (id, ámbito, INE, línea opcional) y
   `EvaluableCandidate` (id opaco, INE, `MultiLineGeometry`) en
   `domain/candidate_evaluation.py`. Cualquier entidad de candidato (#109, ADR 0039) se
   convierte a ella en el composition root. El caso no lleva descripción ni fuente.
2. **Casamiento**: un candidato casa con un caso de su mismo municipio si la fracción de la
   longitud del `tramo_linea` del caso que queda a ≤ `max_distance_m` del candidato es
   ≥ `min_overlap`. La fracción se mide muestreando el tramo en piezas de 1 m (punto medio,
   peso = longitud) con `distance_point_to_shape`. Se mide sobre el caso, no sobre el
   candidato, porque la pregunta es "¿el sistema señala el tramo documentado?".
3. **Criterio v1**: `casamiento_candidato_caso`, versión 1, `max_distance_m = 30`,
   `min_overlap = 0,5`. 30 m: semianchura de la vía pecuaria más ancha observada (38 m → 19 m)
   más unos 10 m de error al dibujar `tramo_linea` sobre cartografía pública; está en el orden
   del radio de búsqueda de ADR 0025 para vía pecuaria frente a red IGN (3 · hypot(10, 5) ≈ 33,5 m).
   0,5: al menos la mitad del tramo documentado; con 30 m impide que un camino que cruza
   perpendicularmente case con un tramo de 120 m o más. Se fijan hoy, con 0 casos evaluables,
   así que no se han elegido mirando los casos.
4. **No evaluables, un solo motivo** por orden fijo: `fuera_del_ambito` (ámbito `comunidad`),
   `sin_geometria` (sin `tramo_linea` o sin segmento medible), `sin_capas` (municipio sin
   candidatos calculados, declarado explícitamente con `municipalities_with_candidates`). Un
   municipio declarado con cero candidatos que casan es evaluable.
5. **Precisión** = candidatos únicos que casan con ≥ 1 caso / candidatos evaluables. Un
   candidato que casa con varios casos cuenta una vez; un caso con varios candidatos cuenta
   como un señalado y todos esos candidatos son aciertos. Candidato evaluable = con segmento
   medible y de un municipio con ≥ 1 caso evaluable. Los candidatos sin segmento se descartan y
   se cuentan aparte.
6. **Métrica no calculable** = `None` cuando su denominador es 0; nunca 0.
7. **Determinismo**: resultado ordenado por ids, independiente del orden de entrada. Entrada
   incoherente (ids repetidos, municipio no declarado, CRS distinto de EPSG:25830, id de
   candidato con forma de referencia catastral) es un error, no un resultado.
8. **Capas**: dominio puro; caso de uso fino `EvaluateCandidatesUseCase` sin ports; la lectura
   de `casos.json` a `ValidationCase` en `adapters/validation_cases/` (nombre → INE con la
   tabla del registro). El validador del formato sigue en `tests/validacion/` hasta #111.

**A revisar con el fundador (umbrales de producto):** los 30 m, el 0,5 y el paso de 1 m deciden
qué cuenta como acierto. Están razonados, no calibrados. Cambiarlos sube la versión del
criterio y exige un ADR nuevo; nunca se ajustan a la vista de un resultado.

## Notas de implementación

- La "forma de referencia catastral" de un id de candidato es un bloque alfanumérico de 14 o
  20 caracteres con letras y dígitos (rústica y urbana). El id de ADR 0039 (16 hex de sha256)
  no la tiene.
- Un caso del hito necesita su INE; uno de la Comunidad puede no traerlo.

## Consecuencias

- #111 compone el arnés en `cli/main.py` con `MATCH_CRITERION_V1`, sin exponer los umbrales.
- Con `validacion-v1` el resultado es 0 evaluables y métricas `None` hasta que #112 añada
  `tramo_linea`.
- La precisión es una cota inferior: un candidato que no casa con un caso conocido no es por
  eso un falso positivo; se revisa a mano.
- Con 2 casos evaluables la métrica es indicativa, no estadística; el resultado siempre lleva
  los recuentos junto a cada métrica.
- Límites conocidos: un candidato corto y bien situado sobre un caso largo puede no casar
  (por eso `tramo_linea` debe ser el tramo afectado, no el camino entero), y en tramos de menos
  de 120 m un camino que cruza puede casar.
- Coste: O(muestras del caso × segmentos de candidatos del municipio), con poda por bbox;
  trivial con decenas de casos.
