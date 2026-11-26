# ADR 0026 — Trazado histórico: entidad con revisión, repositorio PostGIS y conversión (no composición) al trazado común

- Estado: aceptada
- Fecha: 2026-11-25
- Historia: #19 (feature #11). Relacionadas: #18 (método de georreferenciación), #20 (carga del piloto), #22 (trazado común)

## Contexto

Los caminos de las planimetrías del IGN (1870-1880) y del MTN50 de 1881 se digitalizan a mano sobre imágenes georreferenciadas, con revisión humana antes de usarse (principio del proyecto). Hace falta guardarlos con su fecha, documento fuente, procedencia, error de georreferenciación y estado de revisión, y consultarlos para publicar sin que se escape ninguno sin aprobar. En paralelo, #22 introduce `domain/trail.py`, un modelo común de trazado para vías pecuarias, Catastro, histórico y red del IGN.

Hechos que condicionan el modelo: las planimetrías son por municipio (código INE); al menos una fecha real (Chinchón, `1870-01-01`) es genérica de la serie y no del documento; la licencia es CC BY 4.0 y exige la atribución "Obra derivada de <producto> <fecha> CC-BY 4.0 <atribución>" junto a los datos; el error posicional es del documento georreferenciado, no de cada vértice.

## Decisión

1. Entidad `HistoricTrail` en `domain/historic_trail.py`: dataclass congelada con identificador, municipio INE, tipo y número de documento, fecha del documento con precisión (`day`/`year`), `LineGeometry` en EPSG:25830, error de georreferenciación del documento en metros, `Provenance` con licencia obligatoria y revisión (`status`, `reviewer`, `reviewed_at`). Valida sus invariantes en `__post_init__` y lanza `InvalidHistoricTrailError`.
2. Estado de revisión `proposed → approved | rejected`, solo mediante `approve`/`reject`, que devuelven un trazado nuevo. Mismos valores que `RuleStatus`, tipo propio para no acoplar con el motor de reglas.
3. **Conversión, no composición, con el trazado común de #22.** `HistoricTrail` no contiene un `Trail`. El estado de revisión, el documento fuente y el error de georreferenciación son propios del ciclo de digitalización; el trazado común es lo que se publica y compara. Solo los `approved` se convierten a `Trail` con una función pura (`historic_trail_to_trail`), que se escribe en la primera historia que necesite ambos modelos a la vez (publicación o comparación), no en #19 ni en #22.
4. Port `HistoricTrailRepositoryPort` en `ports/historic_trail.py` con escrituras separadas (`save_proposal`, `record_review`) y consultas de publicación que solo devuelven aprobados (`list_approved_by_municipality`, `list_approved_in_bbox`), más `get` y la cola `list_pending`. Mismo criterio de un único port compuesto que `RuleRepositoryPort` (ADR 0019).
5. Adapter `PostgisHistoricTrailRepository` y migración `0005_create_historic_trail`: columna `geometry(LineString, 25830)`, `Provenance` aplanada (ADR 0004), error en `DOUBLE PRECISION`, `CHECK` de coherencia estado/revisor, índice GIST. El upsert de propuestas no toca filas ya revisadas. La consulta por bbox usa `ST_Intersects` sobre la línea real.
6. Atribución CC BY con `derived_work_attribution(trail)`, a partir de `Provenance.source`, el año del documento y `Provenance.license`. Las cadenas exactas por producto las fija el ADR de #18.
7. (Añadido en la implementación; **pendiente de aplicar por el fundador**.) CI debe levantar un servicio PostGIS efímero y aplicar las migraciones antes de `pytest -m acceptance`, porque `-m acceptance` sustituye al `-m 'not integration'` por defecto y selecciona también los criterios `[integración: PostGIS local]`. Sin coste: contenedor del runner de GitHub Actions. El agente no puede modificar `.github/workflows/` (la GitHub App no tiene permiso `workflows`); el cambio propuesto está en la PR de la historia.

## Alternativas consideradas

- **Componer `HistoricTrail` con `Trail` (campo `trail: Trail`)**: rechazada. Obliga a que #19 espere a #22, mete en el modelo común campos que solo tiene sentido revisar en el histórico, y deja al `Trail` dentro de un `HistoricTrail` rechazado con apariencia de publicable.
- **Un único `save` que persiste cualquier estado**: rechazada. Una recarga de propuestas desde ficheros podría devolver a `proposed` un trazado ya aprobado, o aprobar uno sin pasar por la transición.
- **Consultas con parámetro de estado (`list_by_bbox(bbox, status)`)**: rechazada para publicación. Un argumento equivocado publicaría propuestas; el nombre del método hace imposible ese error.
- **`MultiLineString`**: rechazada por ahora. Cada camino digitalizado es una polilínea; un camino partido se guarda como varios trazados con su propio identificador. Revisar si #18 o #20 piden otra cosa.
- **`NUMERIC` para el error**: rechazada. Devuelve `Decimal` y redondea el `float`; rompe la igualdad de ida y vuelta.
- **Fecha como `date | None` o como cadena libre**: rechazada. La fecha es obligatoria; su imprecisión real se expresa con `document_date_precision`.
- **Guardar los puntos de control y la transformación en la misma tabla**: rechazada. Son metadatos del documento, no del trazado, y su formato lo fija #18. Si hace falta persistirlos, irán en una entidad y tabla de documento georreferenciado (#20), enlazadas por `document_id`.
- **Saltar en CI los tests `[integración]` si no hay base de datos**: rechazada. Los criterios CA4–CA6, CA9 y CA10 quedarían sin ejecutar nunca antes del merge.

## Consecuencias

- Tabla nueva `historic_trail`; `tests/conftest.py` la añade al `TRUNCATE`.
- `adapters/postgis/mapping.py` gana el mapeo de `LineGeometry` (`LINESTRING`), reutilizable por otras capas de línea (red del IGN, #12).
- #20 usa `save_proposal`, `list_pending` y `record_review`, y no necesita SQL propio. Si #18 decide que la revisión ocurre en ficheros versionados, #20 carga cada trazado con `save_proposal` seguido de `record_review`, y la procedencia de la aprobación queda igualmente en la base.
- Si el ADR de #18 fija una métrica de error distinta a un único valor en metros por documento, o nuevos campos por trazado, hará falta una migración nueva y un cambio en la entidad. Es el principal riesgo de hacer #19 antes de cerrar #18, y se acepta porque el modelo es pequeño.
- La conversión a `Trail` (#22) queda pendiente hasta la primera historia que publique o compare trazados históricos.
- Coste: ninguno recurrente. PostGIS local (y efímero en CI), sin dependencias nuevas ni red.
