# 0002 — Cliente de Catastro: de referencia catastral a geometría de parcela y edificios

## Historia

Como motor de Parcel Intel que necesita construir un informe a partir de una referencia catastral, quiero un cliente que, dada esa referencia (urbana o rústica), devuelva la geometría de la parcela y la de sus edificios asociados con sus atributos básicos, para que el resto de pipelines (imagen, reglas, informe) tengan la unidad espacial de partida sin depender de coordenadas ya conocidas de antemano.

## Contexto

La historia 0001 dejó documentado en `src/parcel_intel/sources/REGISTRY.md` un **bloqueante sin resolver**: ninguno de los métodos probados contra el WFS INSPIRE de Catastro (`https://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx`) resuelve de forma fiable "referencia catastral rústica de 20 caracteres (`99043A901000010000AQ`) → geometría de esa parcela".

- `GetFeature` con `CQL_FILTER=nationalCadastralReference='<refcat>'` no filtra: devuelve resultados sin filtrar y en `EPSG:4326` por defecto, ignorando el `srsname` pedido (fixture `wfsCP_getfeature_by_refcat.xml`).
- El REST `Consulta_CPMRC` (coordenadas por referencia catastral) solo acepta el formato urbano compacto de 14 caracteres, no el rústico de 20 — falla con error explícito (fixture `cpmrc_colmenar.xml`).
- Lo único confirmado que funciona es `GetFeature` con bbox espacial ya conocido (fixture `wfsCP_getfeature_colmenar_bbox.xml`) y el REST `Consulta_DNPPP`, que da referencia catastral y atributos por polígono/parcela pero no geometría (fixture `dnppp_colmenar_pol1_parc1.xml`).

Sin resolver esto, no hay cliente de Catastro posible: toda la cadena de la vision ("Catastro → capas → reglas → informe") depende de poder entrar por referencia catastral, no por coordenadas. Esta historia es, por tanto, en primer lugar una historia de investigación acotada y, solo si esa investigación tiene éxito, una historia de código según el ADR 0001 (adapter en `adapters/catastro/`, port en `ports/`).

Si la investigación agota los candidatos conocidos sin encontrar un método fiable, esta historia se cierra igualmente (con el resultado documentado y el bloqueante escalado), y el arquitecto decide si se busca una vía alternativa (p. ej. combinar `Consulta_DNPPP` con búsqueda espacial aproximada, o un soporte/canal distinto de Catastro) antes de reabrir el alcance funcional.

## Criterios de aceptación

### Bloque 1 — Resolver el método refcat → geometría (previo e inexcusable) — CERRADO 2026-10-15

- [x] `REGISTRY.md` documenta los tres candidatos con evidencia real: (a) `resourceId` con `localId` de 14 caracteres — no funciona, ignorado sin bbox; (b) `Filter` OGC por POST — no funciona, el servicio ignora el cuerpo POST por completo; (c), en su variante real, combina `Consulta_CPMRC` (centroide por refcat de 14 caracteres) con `GetFeature` de bbox pequeño — **sí funciona** y es mejor que la búsqueda espacial aproximada originalmente prevista.
- [x] Método confirmado: normalizar la referencia a 14 caracteres (`pc1+pc2`) → `Consulta_CPMRC` para el centroide → `GetFeature` con bbox ±100-200 m centrado en ese punto → match por `nationalCadastralReference`. Verificado con dos referencias rústicas distintas: Colmenar de Oreja `99043A90100001` (área 901 m²) y Villaconejos `99170A90100001`.
- [x] El mismo método confirmado también para una referencia adicional del núcleo "urbano" de Colmenar de Oreja (`99043A93700001` — nota: en este municipio, incluso las parcelas del núcleo urbano usan el formato de numeración por polígono, no el formato alfanumérico de manzana que se ve en ciudades grandes; la distinción urbano/rústico la da el atributo `cn` de `Consulta_DNPPP` o `DS_CLASIF_GEN` de IDEM, no el patrón de la referencia).
- [x] Peticiones y respuestas reales grabadas en `tests/fixtures/catastro/`: `cpmrc_colmenar_14char.xml`, `cpmrc_villaconejos_14char.xml`, `cpmrc_colmenar_urbano_14char.xml`, `wfsCP_colmenar_rustica_por_centroide.xml`, `wfsCP_villaconejos_rustica_por_centroide.xml`, más la evidencia de los candidatos fallidos (`wfsCP_getfeature_by_resourceid.xml`, `wfsCP_getfeature_post_filter2.xml`, `wfsCP_colmenar_sin_filtro.xml`, `wfsCP_colmenar_bbox_cql_narrow.xml`).
- [x] No aplica la cláusula de bloqueo — el Bloque 1 tuvo éxito.

### Bloque 2 — Puertos y dominio (solo si el Bloque 1 tiene éxito, al menos para un tipo de referencia)

Conforme al [ADR 0002](../adr/0002-dos-ports-de-geometria-y-provenance-como-value-object.md):

- [x] Existe `src/parcel_intel/ports/geometry.py` con **dos** `Protocol` separados, sin SDK, cliente HTTP ni pydantic:
  - `ParcelGeometryPort.get_parcel(cadastral_reference: str) -> Parcel`.
  - `BuildingGeometryPort.get_buildings(cadastral_reference: str) -> list[Building]`. Nota: implementado solo con `str`, no `str | Parcel` como sugería el ejemplo del ADR 0002 — simplificación válida porque ningún caller actual llega a tener ya una `Parcel` sin su referencia; si surge ese caso, se amplía la firma entonces.
- [x] Ninguno de los dos ports menciona "Catastro" en su nombre ni interfaz. `CatastroAdapter` implementa ambos compartiendo cliente HTTP.
- [x] `src/parcel_intel/domain/provenance.py` (`Provenance`), `domain/geometry.py` (`Geometry`, tipo adicional no previsto explícitamente en el ADR pero necesario para representar geometría en stdlib puro — rings de tuplas `(x, y)`, sin shapely), `domain/parcel.py`, `domain/building.py`: todas dataclasses `frozen=True`, solo stdlib.
- [x] Sin imports de terceros en `domain/` — verificado por el segundo contrato de `import-linter`.
- [x] `pyproject.toml` creado con contrato de 5 capas (`cli`, `adapters`, `application`, `ports`, `domain`) y configuración de `mypy` (strict) y `ruff`.
- [x] `uv run lint-imports` → `Contracts: 2 kept, 0 broken`.

### Bloque 3 — Adapter de Catastro (solo si el Bloque 1 tiene éxito) — CERRADO 2026-10-15

- [x] `src/parcel_intel/adapters/catastro/` implementa ambos ports (`adapter.py`), con módulos de apoyo `client.py` (HTTP, seam inyectable para tests), `parsing.py` (XML con `xml.etree.ElementTree`, stdlib — no hizo falta pydantic en absoluto: las respuestas son XML, no JSON, y la validación manual con errores explícitos fue más natural), `reference.py` (normalización 20→14 car.) y `geometry_ops.py` (point-in-ring para asociar edificios a su parcela, ray casting puro, sin shapely).
- [x] Verificado con dos rústicas reales: Colmenar de Oreja `99043A90100001` (901 m², sin edificios — parcela agrícola) y Villaconejos `99170A90100001` (29069 m²). Edificios: cuando existen, se asocian a la parcela comprobando que el centroide del edificio cae dentro del anillo exterior de la parcela (no basta con "estar en el mismo bbox" — bboxes pequeños pueden rozar la parcela vecina).
- [x] Verificado con una referencia del núcleo urbano de Colmenar de Oreja (`99043A93700001`, 239854 m² — nota: incluso el núcleo urbano de este municipio usa numeración por polígono, no el formato alfanumérico de manzana).
- [x] Referencia inexistente (formato válido, sin resultado en Catastro) → `ParcelNotFoundError` explícito, con la referencia en el mensaje. Referencia con longitud inválida → `InvalidCadastralReferenceError`, lanzado antes de tocar la red.
- [x] Toda `Parcel`/`Building` lleva `provenance` con `source="catastro"`, la URL exacta (incluye bbox y parámetros usados) y `retrieved_at`.
- [x] No se usó pydantic (ver nota arriba) — no aplica el criterio de aislarlo en el adapter porque no hay modelos pydantic en ningún punto del código.
- [x] `uv run pytest` → 11 passed, cero llamadas de red (fixtures de `tests/fixtures/catastro/`, incluida una fixture sintética explícitamente marcada como tal para el caso "no encontrada", ya que no se capturó ese error real contra la red en esta pasada).
- [x] `uv run mypy src tests` → `Success: no issues found in 23 source files`.
- [x] `uv run ruff check .` → `All checks passed!`.
- [x] `uv run lint-imports` → en verde (ver Bloque 2).

## Fuera de alcance

- Esquema PostGIS, persistencia o almacenamiento de las entidades `parcel`/`building` (historia 0003).
- Cualquier otra fuente (Sentinel-2, PNOA, LiDAR, BOE, BOCM, IDEM) — esta historia es exclusivamente Catastro.
- Resolver geometría de **caminos o cauces** que figuren como parcela propia en Catastro (mencionado como nota a verificar en `REGISTRY.md`): se trata como una parcela más si el método del Bloque 1 la devuelve, sin tratamiento especial; la clasificación de qué representa cada parcela es tarea de las reglas (historia 0007), no de este cliente.
- Resolver referencias catastrales de municipios distintos de Colmenar de Oreja y Villaconejos.
- Caché persistente de las respuestas de Catastro en `data/` (política de caché/TTL es diseño del arquitecto); esta historia solo exige que las fixtures de test no llamen a red, no que el adapter tenga caché en producción.
- Reintentos, rate-limiting o circuito de resiliencia ante caídas del servicio de Catastro.
- Geolocalización de boletines (BOE/BOCM) aunque internamente también resuelva "referencia catastral → geometría": esa es la historia 0006 y reutilizará este adapter, no lo reimplementará.

## Preguntas abiertas

- Si el Bloque 1 falla para los tres candidatos: ¿se busca soporte directo de Catastro (hay un canal de soporte técnico documentado para desarrolladores), se prueba una librería de terceros ya existente que resuelva este problema, o se acepta una limitación del MVP (p. ej. exigir que el usuario aporte también coordenadas aproximadas junto con la referencia rústica)? Decisión para el arquitecto o el fundador, no para esta historia.
- ¿Qué se hace cuando una parcela rústica no tiene ningún edificio asociado en Catastro? Se asume que el cliente debe devolver la parcela con una lista de edificios vacía (no un error), pero conviene que el arquitecto lo confirme como contrato del port.
- El nombre exacto del/los port(s) (`ParcelGeometryPort` es un ejemplo de `docs/adr/0001...md`, no una decisión cerrada) queda a criterio del arquitecto al diseñar el Bloque 2.

## Métricas de éxito

- El bloqueante de la historia 0001 queda cerrado (resuelto o explícitamente escalado como bloqueado) sin reabrir la historia 0001 ni modificar su alcance ya cerrado.
- Tiempo invertido en el Bloque 1 (investigación) registrado y comparado contra el resto de la historia, para que `lessons-learned` pueda valorar si el riesgo de "endpoint no verificado" de Catastro era mayor o menor que el de las otras fuentes.
- Cero llamadas de red reales en la suite de tests (`uv run pytest`) una vez cerrada la historia — condición necesaria para que el resto del equipo pueda ejecutar los tests sin depender de la disponibilidad del servicio de Catastro.
- Al menos 2 referencias catastrales rústicas y 1 urbana, de parcelas reales en Colmenar de Oreja o Villaconejos verificables en persona por el fundador, resueltas correctamente end-to-end por el cliente — sienta la base empírica para el "golden set" de `tests/golden/` que usarán historias posteriores.
