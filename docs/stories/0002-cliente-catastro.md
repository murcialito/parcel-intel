# 0002 — Cliente de Catastro: de referencia catastral a geometría de parcela y edificios

## Historia

Como motor de Parcel Intel que necesita construir un informe a partir de una referencia catastral, quiero un cliente que, dada esa referencia (urbana o rústica), devuelva la geometría de la parcela y la de sus edificios asociados con sus atributos básicos, para que el resto de pipelines (imagen, reglas, informe) tengan la unidad espacial de partida sin depender de coordenadas ya conocidas de antemano.

## Contexto

La historia 0001 dejó documentado en `src/parcel_intel/sources/REGISTRY.md` un **bloqueante sin resolver**: ninguno de los métodos probados contra el WFS INSPIRE de Catastro (`https://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx`) resuelve de forma fiable "referencia catastral rústica de 20 caracteres (`REFCAT-RETIRADA`) → geometría de esa parcela".

- `GetFeature` con `CQL_FILTER=nationalCadastralReference='<refcat>'` no filtra: devuelve resultados sin filtrar y en `EPSG:4326` por defecto, ignorando el `srsname` pedido (fixture `wfsCP_getfeature_by_refcat.xml`).
- El REST `Consulta_CPMRC` (coordenadas por referencia catastral) solo acepta el formato urbano compacto de 14 caracteres, no el rústico de 20 — falla con error explícito (fixture `cpmrc_colmenar.xml`).
- Lo único confirmado que funciona es `GetFeature` con bbox espacial ya conocido (fixture `wfsCP_getfeature_colmenar_bbox.xml`) y el REST `Consulta_DNPPP`, que da referencia catastral y atributos por polígono/parcela pero no geometría (fixture `dnppp_colmenar_pol1_parc1.xml`).

Sin resolver esto, no hay cliente de Catastro posible: toda la cadena de la vision ("Catastro → capas → reglas → informe") depende de poder entrar por referencia catastral, no por coordenadas. Esta historia es, por tanto, en primer lugar una historia de investigación acotada y, solo si esa investigación tiene éxito, una historia de código según el ADR 0001 (adapter en `adapters/catastro/`, port en `ports/`).

Si la investigación agota los candidatos conocidos sin encontrar un método fiable, esta historia se cierra igualmente (con el resultado documentado y el bloqueante escalado), y el arquitecto decide si se busca una vía alternativa (p. ej. combinar `Consulta_DNPPP` con búsqueda espacial aproximada, o un soporte/canal distinto de Catastro) antes de reabrir el alcance funcional.

## Criterios de aceptación

### Bloque 1 — Resolver el método refcat → geometría (previo e inexcusable)

- [ ] `REGISTRY.md` incorpora una nueva sección "Hallazgo pendiente — RESUELTO en la historia 0002" (o se actualiza la existente) que documenta, para cada uno de los tres candidatos anotados en la historia 0001, si funcionó o no, con la petición real y la respuesta real (o el error real) como evidencia:
  - (a) `GetFeature` con `resourceId=ES.SDGC.CP.<localId>` usando el `gml:id` / `inspireId.localId` INSPIRE de 14 caracteres, incluyendo el mapeo explícito probado entre la referencia rústica de 20 caracteres y ese `localId` de 14.
  - (b) `Filter` OGC estándar (XML) enviado por POST, en vez de `CQL_FILTER` por GET.
  - (c) Combinar el resultado de `Consulta_DNPPP` (polígono/parcela, superficie, paraje) con una búsqueda espacial aproximada sobre el WFS.
- [ ] Existe al menos un método confirmado (no asumido) que, dada una referencia catastral rústica de 20 caracteres de Colmenar de Oreja o Villaconejos, devuelve una única geometría de parcela en el CRS correcto (`EPSG:25830` o reproyectable a él de forma determinista), verificado con al menos dos referencias catastrales rústicas distintas de los dos municipios del MVP.
- [ ] El mismo método (o uno adicional si el formato urbano de 14 caracteres requiere una vía distinta) queda confirmado también para al menos una referencia catastral **urbana** de uno de los dos municipios.
- [ ] Las peticiones y respuestas reales de este bloque quedan grabadas como ficheros nuevos en `tests/fixtures/catastro/` (no solo descritas en markdown), reutilizables sin llamar a la red.
- [ ] Si, tras agotar los tres candidatos y cualquier variante razonable de cada uno, ninguno resuelve el caso rústico de forma fiable, el resto de los criterios de este bloque se sustituye por: `REGISTRY.md` documenta el intento de cada candidato con su fallo concreto, y la historia se cierra como bloqueada, sin avanzar al Bloque 2 ni al 3 en lo que dependa de la referencia rústica. En ese caso, la pregunta "¿cómo resolver refcat rústica → geometría?" pasa a "Preguntas abiertas" para decisión del arquitecto o el fundador.

### Bloque 2 — Puertos y dominio (solo si el Bloque 1 tiene éxito, al menos para un tipo de referencia)

Conforme al [ADR 0002](../adr/0002-dos-ports-de-geometria-y-provenance-como-value-object.md):

- [ ] Existe `src/parcel_intel/ports/` con **dos** `Protocol` separados, sin ningún tipo de SDK, cliente HTTP ni pydantic en este módulo:
  - `ParcelGeometryPort`: recibe una referencia catastral (string) y devuelve una `Parcel`.
  - `BuildingGeometryPort`: recibe una referencia catastral o una `Parcel` y devuelve `list[Building]`.
- [ ] Ninguno de los dos ports menciona "Catastro" ni ningún proveedor concreto en su nombre ni en su interfaz pública (se nombran por la capacidad que ofrecen, no por el proveedor), conforme al ADR 0001. El corte en dos ports (no uno combinado) existe para que un futuro adapter de detección de imagen pueda implementar solo `BuildingGeometryPort` sin simular autoridad sobre geometría de parcela.
- [ ] Existe `src/parcel_intel/domain/provenance.py` con una dataclass `frozen=True` `Provenance` (`source: str`, `url: str`, `retrieved_at: date`, `license: str | None`), y las entidades `Parcel` y `Building` (en `domain/parcel.py` / `domain/building.py`) incluyen un campo `provenance: Provenance` por composición.
- [ ] Las entidades de dominio (`Parcel`, `Building`, `Provenance`) son dataclasses congeladas (`frozen=True`), sin imports de pydantic, requests, geopandas/shapely ni ningún paquete de terceros — solo stdlib.
- [ ] Existe `pyproject.toml` con el contrato de `import-linter` para las cinco capas (`domain`, `ports`, `application`, `adapters`, `cli`/`api`) y configuración mínima de `mypy` y `ruff`, ya que no existen todavía en el repo y son condición previa para que los criterios de verificación del Bloque 3 sean comprobables.
- [ ] `uv run lint-imports` pasa en verde tras añadir estos módulos.

### Bloque 3 — Adapter de Catastro (solo si el Bloque 1 tiene éxito)

- [ ] Existe `src/parcel_intel/adapters/catastro/` que implementa los dos ports del Bloque 2 (puede compartir un único cliente HTTP internamente, dado que el WFS de Catastro resuelve parcela y edificios en la misma llamada), usando el o los métodos confirmados en el Bloque 1.
- [ ] Dado el método confirmado para referencia rústica, el adapter devuelve para al menos dos referencias rústicas distintas de Colmenar de Oreja o Villaconejos: la geometría de la parcela en `EPSG:25830` y, si Catastro tiene edificios asociados a esa parcela, la geometría de cada edificio también en `EPSG:25830`, con superficie y, si está disponible en la respuesta de Catastro, año de construcción.
- [ ] Dado el método confirmado para referencia urbana, el adapter devuelve el mismo tipo de resultado para al menos una referencia urbana de uno de los dos municipios.
- [ ] Dada una referencia catastral que no existe o está mal formada, el adapter señala el error de forma explícita (no devuelve una geometría vacía silenciosa ni lanza una excepción genérica sin contexto) — verificable con un caso de prueba concreto.
- [ ] Cada parcela y cada edificio devueltos llevan procedencia: fuente (`catastro`), URL exacta de la petición realizada y fecha de la consulta, conforme a la convención de `CLAUDE.md` ("todo dato lleva procedencia").
- [ ] La validación de la respuesta cruda de Catastro (XML/GML) con pydantic, si se usa, vive únicamente dentro de `adapters/catastro/` — no se filtran modelos pydantic hacia `ports/` ni `domain/`.
- [ ] Los tests del adapter (`tests/`) no hacen ninguna llamada de red real: usan como fixtures los ficheros ya grabados en `tests/fixtures/catastro/` de la historia 0001 más los nuevos del Bloque 1 de esta historia. Se verifica ejecutando `uv run pytest` con la red deshabilitada (o comprobando que ningún test está marcado como `integration`/de red) y que la suite pasa igual.
- [ ] `uv run mypy` pasa en verde sobre los módulos nuevos.
- [ ] `uv run ruff check .` pasa en verde.
- [ ] `uv run lint-imports` sigue en verde tras añadir el adapter.

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
