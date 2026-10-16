# ADR 0018 — Condición de solape polígono↔polígono (`geometries_overlap`), unión discriminada `SpatialCondition`, `Evidence` opcional, y hallazgo crítico: el filtro BBOX de WFS de Red Natura 2000 es laxo (envolvente, no geometría real)

- Estado: aceptada
- Fecha: 2026-10-16

## Contexto

La historia 0018 (`docs/stories/0018-ampliar-catalogo-de-reglas-vias-pecuarias-red-natura.md`) deja cinco preguntas abiertas para el arquitecto, con una exigencia explícita adicional: **verificar manualmente, contra las fixtures reales ya grabadas y sin red nueva, el resultado exacto que debe producir la regla de Red Natura 2000 antes de implementar** — mismo rigor que el ADR 0017 aplicó a la distancia de `8.535301066249467` m.

Esa verificación (detallada abajo, sección "Resultado real verificado") **contradice la premisa de la propia historia y de `REGISTRY.md` (hallazgo 3 de Red Natura 2000)**: el feature real `CD_PLAN="SE"`/`CD_ZONA="X"` que el WFS de IDEM devuelve para las tres bboxes de prueba (Villaconejos rústica, Colmenar rústica, Colmenar urbana) **no contiene geométricamente ninguna de las dos parcelas reales verificables** — están a 1.36 km y 8.33 km de distancia real del polígono, no dentro de él. Este es el hallazgo central de este ADR y determina casi todas las decisiones siguientes.

Antes de decidir se leyó/ejecutó el código real (no solo `REGISTRY.md`):

- `domain/rule.py` (historia 0017, cerrada): `SpatialOperation = Literal["within_distance"]`, `SpatialLayer = Literal["dph_cauce"]`, `SpatialCondition(operation, layer, meters)` como única forma. `evaluate_rules` solo soporta esta condición.
- `domain/geometry.py`: `Geometry`/`LineGeometry`/`distance_polygon_to_line`/`_segments_intersect`/`_on_segment`/`_point_segment_distance` ya existen (ADR 0017), stdlib puro. No existe ninguna función de solape polígono↔polígono.
- `adapters/catastro/geometry_ops.py`: `point_in_ring`/`point_in_any_ring` (ray-casting estándar) y `ring_centroid` — la única lógica de "punto dentro de polígono" del repositorio, en un **adapter**, que `domain/rule.py` no puede importar (regla hexagonal, `CLAUDE.md`). Solo se usa hoy desde `adapters/catastro/adapter.py` (emparejar edificio↔parcela); ningún test dedicado la cubre directamente.
- `domain/livestock_trail.py`/`domain/protected_area.py`: ambos con `geometry: Geometry`. `LivestockTrail` tiene `area_m2`/`length_m` (reales, del proveedor); `ProtectedArea` **no tiene ningún campo numérico** — solo `plan_code`/`plan_name`/`zone_code`/`zone_name`/`geometry`/`provenance`.
- `adapters/protected_areas/parsing.py`: `_rings_from_feature` ya descarta `gml:interior` (solo toma `gml:exterior`) — confirmado real: el feature `SE`/`X` tiene 5 `gml:exterior` (18220, 5414, 11453, 1550 y 90 puntos) y 2 `gml:interior` descartados (`REGISTRY.md`, hallazgo 4).

**Verificación real ejecutada (sin red nueva, reutilizando parsers + fixtures ya grabadas, cruzada con `shapely` como control independiente — instalado solo en el entorno de verificación, no añadido a `pyproject.toml`/`uv.lock`, confirmado con `git status` antes y después):**

```
Villaconejos (REFCAT-RETIRADA, tests/fixtures/catastro/wfsCP_villaconejos_rustica_por_centroide.xml)
  vs. zona SE/X (tests/fixtures/protected_areas/wfs_getfeature_bbox_villaconejos_rustica_margin2m.xml)
  → NO solapan. Distancia real (shapely): 1363.16 m. Vértice más cercano del
    anillo 0 de la zona (18220 pts) al centroide de la parcela: 1447.67 m.

Colmenar rústica (REFCAT-RETIRADA, tests/fixtures/catastro/wfsCP_colmenar_rustica_por_centroide.xml)
  vs. la MISMA zona SE/X (tests/fixtures/protected_areas/wfs_getfeature_bbox_colmenar_rustica_margin2m.xml,
  contenido de feature byte-idéntico al de Villaconejos, confirmado)
  → NO solapan. Distancia real (shapely): 8329.95 m.
```

**Causa raíz, confirmada, no especulada:** el filtro espacial `BBOX` de OGC Filter Encoding que usa `ProtectedAreaAdapter` (ADR 0015) evalúa, en este WFS/GeoServer, la **envolvente (bounding box) de la geometría completa del feature**, no su geometría real — comportamiento estándar y documentado del operador `BBOX` (distinto de `Intersects`), que aquí se manifiesta porque el feature `SE`/`X` es un `MultiSurface` de 5 polígonos reales dispersos en un área de ~46×41 km: la envolvente combinada de esos 5 polígonos cubre trivialmente cualquier bbox pequeño dentro de esa región, aunque el polígono real más cercano esté a más de 1 km. **Esto NO ocurre con vías pecuarias** (confirmado: las dos fixtures `_sin_afeccion` devuelven `0` features, no un falso positivo) porque cada tramo de vía pecuaria es un único polígono compacto — su envolvente y su geometría real casi coinciden. La diferencia de comportamiento es del **tamaño/dispersión de la geometría del feature**, no del proveedor ni del protocolo.

Esto invalida, con evidencia real, la afirmación de `REGISTRY.md` (hallazgo 3, historia 0015) *"confirma que todo el territorio de los dos municipios del MVP... está dentro del área de gestión Red Natura 2000 regional"* — esa afirmación se basó en "el WFS devolvió el mismo feature para las tres bboxes", una inferencia razonable en su momento (la historia 0015 no tenía ninguna función de solape real que pudiera contradecirla) pero que resulta falsa al medirla con geometría real. Se corrige con una nota explícita en `REGISTRY.md` (ver Consecuencias) — no se reescribe el hallazgo original, se añade un hallazgo 3.1 que lo corrige, mismo patrón ya usado por la historia 0011 (hallazgo 2.1).

**Consecuencia directa para `_evaluate_spatial`/`_evaluate_overlaps`: el principio que ya fijó el ADR 0017 ("el margen de bbox usado para la consulta de red... nunca afirma nada sobre la distancia/solape real") no era solo una precaución teórica — es exactamente el bug que esta verificación encontró.** Si el evaluador tratara "`report.protected_areas` no está vacío" como sinónimo de "solapa", el hallazgo de Red Natura 2000 sería un **falso positivo real** en Villaconejos y Colmenar rústica. La función de solape nueva es, por tanto, no solo "la forma correcta de implementarlo" sino la única forma que evita este falso positivo ya demostrado.

## Decisión

**1. `geometries_overlap(a: Geometry, b: Geometry) -> bool` nueva en `domain/geometry.py`, con poda por *bounding box* — la única función de este ADR donde la poda SÍ se justifica con medición real (a diferencia de `distance_polygon_to_line`, ADR 0017, donde se rechazó explícitamente por falta de evidencia).**

   Algoritmo exacto (no aproximado): dos anillos solapan si (a) algún borde de uno cruza algún borde del otro (reutiliza `_segments_intersect`, ADR 0017), **o** (b) sin ningún cruce de bordes, un anillo está íntegramente contenido en el otro — caso real y obligatorio de cubrir, confirmado en esta misma verificación: una parcela sintética construida dentro del anillo 4 de la zona `SE`/`X` (90 puntos, área real 35828.36 m²) solapa sin que ningún borde se toque. Si no hay cruce de bordes, todos los vértices de un anillo comparten el mismo resultado dentro/fuera respecto al otro anillo (son disjuntos, o uno contiene al otro) — basta comprobar un único vértice de cada lado:

   ```python
   def _ring_overlaps_ring(ring_a: Ring, ring_b: Ring) -> bool:
       if not _bboxes_overlap(_ring_bbox(ring_a), _ring_bbox(ring_b)):
           return False
       n_a, n_b = len(ring_a), len(ring_b)
       for i in range(n_a):
           a1, a2 = ring_a[i], ring_a[(i + 1) % n_a]
           for j in range(n_b):
               b1, b2 = ring_b[j], ring_b[(j + 1) % n_b]
               if _segments_intersect(a1, a2, b1, b2):
                   return True
       return point_in_ring(ring_a[0], ring_b) or point_in_ring(ring_b[0], ring_a)

   def geometries_overlap(a: Geometry, b: Geometry) -> bool:
       if not a.rings or not b.rings:
           raise EmptyGeometryError
       return any(
           _ring_overlaps_ring(ring_a, ring_b) for ring_a in a.rings for ring_b in b.rings
       )
   ```

   **La poda por bbox (`_bboxes_overlap`) sí se incluye, con medición real que la justifica** (a diferencia del rechazo explícito de poda en el ADR 0017 para `distance_polygon_to_line`, donde no había evidencia de que hiciera falta): evaluar `geometries_overlap` entre la parcela real de Villaconejos (72 puntos) y los 5 anillos reales de la zona `SE`/`X` (36727 puntos en total) tarda **2.35 s** sin poda y **1.15 s** con poda (la poda elimina 4 de los 5 anillos sin recorrerlos; el anillo 0 no se puede descartar por bbox porque su envolvente sí contiene la parcela — es la misma causa raíz documentada arriba). `distance_polygon_to_line` nunca se enfrentó a una geometría de este tamaño (el cauce de Villaconejos tiene 138 puntos); esta historia es exactamente el caso que el ADR 0017 ya marcó como condición para revisitar la poda ("revisitar si una geometría futura... hace que el coste deje de ser trivial").

   stdlib puro (`math` ya importado). `EmptyGeometryError` se reutiliza sin cambios (ya existe, ADR 0017).

**2. `point_in_ring`/`point_in_any_ring` se mueven de `adapters/catastro/geometry_ops.py` a `domain/geometry.py`** (opción (a) de la pregunta abierta 2, rechazando duplicar la lógica — opción (b) — porque ya hay una lección registrada en este proyecto, historia 0001/0002, sobre el riesgo concreto de que dos implementaciones del mismo ray-casting diverjan). Es geometría pura (ray-casting con `Point`/`Ring`, cero SDKs, cero HTTP) que nunca debió depender de pertenecer a un adapter concreto — su ubicación en `adapters/catastro/` fue un accidente histórico de qué historia la necesitó primero (0001/0002, antes de que `domain/geometry.py` tuviera ninguna función de punto-en-polígono), no una decisión de diseño. `adapters/catastro/geometry_ops.py` se reduce a `ring_centroid` (sin cambios); `adapters/catastro/adapter.py` cambia su import de `point_in_any_ring` de `adapters.catastro.geometry_ops` a `domain.geometry` (una línea, cero cambio de comportamiento — `ring_centroid` sigue viniendo del adapter). Entre adapter→domain es la única dirección que `import-linter` permite; moverla hacia abajo no rompe el contrato, confirmado ejecutando `uv run lint-imports` tras el cambio (ver Consecuencias).

**3. `SpatialCondition` deja de ser un único dataclass: se convierte en una unión discriminada de dos dataclasses — resuelve a la vez las preguntas abiertas 1 y 4.** `meters: float` no tiene sentido para una condición de solape (pregunta 1); forzar el `Literal` de `operation`/`layer` a aceptar cualquier combinación (p. ej. `within_distance` + `via_pecuaria`) sería un error silencioso solo detectable en tiempo de ejecución (pregunta 4). Ambas se resuelven de una vez con un único cambio de tipos, verificado por `mypy --strict`, no por un test:

   ```python
   WatercourseLayer = Literal["dph_cauce"]
   OverlapLayer = Literal["via_pecuaria", "red_natura_plan"]

   @dataclass(frozen=True)
   class WithinDistanceCondition:
       operation: Literal["within_distance"]
       layer: WatercourseLayer
       meters: float

   @dataclass(frozen=True)
   class OverlapsCondition:
       operation: Literal["overlaps"]
       layer: OverlapLayer

   SpatialCondition = WithinDistanceCondition | OverlapsCondition
   ```

   `Rule.spatial: SpatialCondition` **no cambia de forma textual** (sigue siendo ese mismo tipo con ese mismo nombre) — solo cambia qué es `SpatialCondition` por debajo (de una clase concreta a una unión). `evaluate_rules`/`_evaluate_spatial` pasan a despachar por `isinstance`:

   ```python
   def _evaluate_spatial(report: EnrichedParcelReport, spatial: SpatialCondition) -> Evidence | None:
       if isinstance(spatial, WithinDistanceCondition):
           return _evaluate_within_distance(report, spatial)
       return _evaluate_overlaps(report, spatial)
   ```

   **Coste real, explícito, de este cambio sobre la regla ya aprobada de cauces (historia 0017) — "debe seguir funcionando igual, con los mismos tests en verde":** tres sitios literalmente instancian `SpatialCondition(operation="within_distance", layer="dph_cauce", meters=100.0)` y deben renombrar la clase a `WithinDistanceCondition` (mecánico, cero cambio de comportamiento ni de valores): `src/parcel_intel/api/main.py:48`, `tests/adapters/reports/test_html.py:385`, `tests/domain/test_rule.py:42`. "Mismos tests en verde" se entiende como paridad de comportamiento/aserciones (igual que ya se entendió así en el ADR 0017 para la condición espacial), no como cero bytes modificados — el propio ADR 0017 ya advirtió de este tipo de coste al dejar `SpatialOperation`/`SpatialLayer` deliberadamente cerrados: *"cualquier regla futura... obliga a ampliar el tipo, visible en el diff de revisión"*. Este ADR amplía esa idea un paso más: no solo el `Literal`, también la forma del dataclass, cuando los parámetros de la nueva condición no coinciden con los de la anterior.

   **Alternativa rechazada**: mantener un único `SpatialCondition(operation, layer, meters)` con `meters` ignorado para `"overlaps"` (p. ej. `meters=0.0`). Rechazada por dejar un campo estructuralmente sin sentido en la mitad de las instancias reales — exactamente el tipo de "campo opcional que solo tiene sentido para una de las dos fuentes" que la lección de la historia 0012 ya señaló como señal de abstracción forzada, aplicada aquí a una condición en vez de a una entidad.

**4. `Evidence.measured_value`/`unit` pasan a `float | None = None`/`str | None = None` — resuelve la pregunta abierta 3, eligiendo la opción que la propia historia dejaba como candidata ("ampliar `Evidence`"), no una de las dos que forzaban un valor numérico sin sentido de negocio.** Verificado contra el modelo de dominio real antes de decidir: `LivestockTrail` sí tiene un campo numérico real reutilizable (`area_m2`, confirmado real en `REGISTRY.md` — p. ej. 122148.09 m² para "Vereda del Cristo"); `ProtectedArea` **no tiene ningún campo numérico** (`plan_code`/`plan_name`/`zone_code`/`zone_name`/`geometry`/`provenance` — confirmado leyendo `domain/protected_area.py` y el `DescribeFeatureType` real citado en `REGISTRY.md`, 5 campos sin ninguno de magnitud). Inventar un valor convencional (`1.0`/`"solape"`, la otra candidata de la historia) para Red Natura 2000 habría sido un número sin ningún significado verificable contra la fuente — justo lo que `Evidence` fue diseñada para evitar (ADR 0017: *"para que un consumidor pueda verificarla contra la fuente"*). `None` es honesto: no hay magnitud real que citar, solo identidad textual (`plan_name`, `zone_code`, `zone_name`), que sí va en `source_name`/`description`.

   - Vías pecuarias: `Evidence(description="Solape con vía pecuaria", source_name=trail.name or "tramo de vía pecuaria sin nombre", measured_value=trail.area_m2, unit="m2")` — reutiliza un campo real ya existente, exactamente como permite la propia historia en "Fuera de alcance" (*"usa, como mucho, campos ya existentes de la entidad que solapa"*).
   - Red Natura 2000: `Evidence(description="Solape con plan de gestión Red Natura 2000", source_name=f"{area.plan_name} ({area.zone_code} — {area.zone_name})", measured_value=None, unit=None)`.

   **Consecuencia obligatoria en el adapter de render** (no en `domain/`, pero debe señalarse porque si no la implementación rompe en caliente): `adapters/reports/html.py::_render_evidence_item` hace hoy `f"{evidence.measured_value:.2f} {escape(evidence.unit)}"` — con `measured_value=None` esto lanza `TypeError` en formato. Debe cambiar a una rama condicional (sin número si `measured_value is None`). Documentado aquí como consecuencia de este ADR, no una decisión nueva — es la implicación mecánica de hacer `Evidence` opcional.

**5. Dos reglas nuevas, `status: approved`, construidas en `api/main.py` junto a `_APPROVED_RULES` (sin cambios al patrón del composition root, ADR 0017):**

   ```python
   Rule(
       identifier="madrid-solape-via-pecuaria",
       scope=RuleScope(region="madrid", soil_classes=()),
       spatial=OverlapsCondition(operation="overlaps", layer="via_pecuaria"),
       attributes=AttributeCondition(building_origin=("catastro", "detected")),
       outcome="requires_authorization",
       authority="Comunidad de Madrid — Consejería de Medio Ambiente, Agricultura e Interior",
       citation=Provision(
           norm=Norm(
               title="Ley 8/1998, de 15 de junio, de Vías Pecuarias de la Comunidad de Madrid",
               url="https://www.bocm.es/boletin/CM_Orden_BOCM/1998/06/24/1998062400.pdf",
           ),
           article="art. 17 — régimen de autorizaciones de uso y ocupación",
           in_force_since=date(1998, 6, 25),
       ),
       status="approved",
   ),
   Rule(
       identifier="madrid-solape-red-natura",
       scope=RuleScope(region="madrid", soil_classes=()),
       spatial=OverlapsCondition(operation="overlaps", layer="red_natura_plan"),
       attributes=AttributeCondition(building_origin=("catastro", "detected")),
       outcome="requires_environmental_assessment",
       authority="Comunidad de Madrid — Dirección General de Biodiversidad y Recursos Naturales",
       citation=Provision(
           norm=Norm(
               title="Ley 42/2007, de 13 de diciembre, del Patrimonio Natural y de la Biodiversidad",
               url="https://www.boe.es/buscar/act.php?id=BOE-A-2007-21490",
           ),
           article="art. 45 — evaluación de planes y proyectos con posible afección a la Red Natura 2000",
           in_force_since=date(2007, 12, 14),
       ),
       status="approved",
   ),
   ```

   `scope.soil_classes=()` en ambas, tal como ya fijaba la historia (sin restricción de suelo — afecta igual a urbano y no urbanizable). **Cita normativa razonable para la demostración técnica, no verificación legal cerrada** — mismo nivel exacto que el RD 849/1986 del ADR 0017: el artículo/fecha de vías pecuarias y, sobre todo, el instrumento autonómico concreto que aprobó el plan de gestión real `"SE"` (un Decreto específico de la Comunidad de Madrid, no identificado aquí por falta de verificación legal, fuera de alcance explícito de la historia) quedan como limitación conocida, documentada, no resuelta por este ADR.

**6. Severidad y confianza — umbrales de producto, marcados explícitamente para revisión del fundador, no decisiones de arquitectura (mismo criterio que el ADR 0017, Decisión 8):**

   - `severity="actionable"` para ambos `outcome` nuevos (ambos exigen una acción —autorización o evaluación— antes de construir, igual criterio que cauces).
   - `_VIA_PECUARIA_OVERLAP_CONFIDENCE = 0.85`: la franja cartografiada es real, pero `REGISTRY.md` (hallazgo 2, historia 0014) ya confirmó que la anchura derivada (`area_m2/length_m`) es sistemáticamente **menor** que la anchura legal mínima (p. ej. vereda: ~11.64 m real vs. ≥20.89 m legal) — un resultado de **no solape** contra la franja cartografiada no descarta con certeza un solape contra el ancho legal completo. Descontada ligeramente por debajo del `0.9` de cauces, en la dirección opuesta (riesgo de falso negativo, no de falso positivo).
   - `_RED_NATURA_OVERLAP_CONFIDENCE = 0.9`: igual que cauces, descontada solo por la limitación ya aceptada en todo el proyecto desde ADR 0011 (geometría IDEM sin anillos interiores reales, 2 huecos descartados en este plan concreto — riesgo acotado de falso positivo cerca de un hueco, no verificado contra ningún caso real porque ninguna de las dos parcelas reales cae ahí).
   - **A revisar con el fundador**, igual que el ADR 0017 ya marcó para `0.9`: ninguno de los tres valores (`0.85`/`0.9`/`0.9`) está calibrado contra un caso de desacuerdo real conocido, solo razonado.

## Resultado real verificado

**Ejecutado reutilizando los parsers reales ya existentes sobre las fixtures reales ya grabadas — sin red nueva, sin asumir el resultado de antemano, cruzado con `shapely` (instalado solo en el entorno de verificación, nunca en `pyproject.toml`/`uv.lock`) como control independiente del algoritmo propio:**

- **Red Natura 2000 — Villaconejos (`REFCAT-RETIRADA`)**: geometría real de la parcela (72 puntos, `tests/fixtures/catastro/wfsCP_villaconejos_rustica_por_centroide.xml`) vs. geometría real de la zona `SE`/`X` (5 anillos reales, 36727 puntos, `tests/fixtures/protected_areas/wfs_getfeature_bbox_villaconejos_rustica_margin2m.xml`) → **`geometries_overlap` da `False`** (confirmado con `_ring_overlaps_ring` propio y con `shapely.distance` = `1363.16` m). **La regla `madrid-solape-red-natura` evaluada contra el `EnrichedParcelReport` real de Villaconejos produce CERO `Finding`** — contradice la expectativa original de la historia 0018, confirma el hallazgo de este ADR.
- **Red Natura 2000 — Colmenar rústica (`REFCAT-RETIRADA`)**: mismo resultado, `False`, `shapely.distance` = `8329.95` m (más lejos aún). **Cero `Finding`.**
- **Red Natura 2000 — Colmenar urbana (`REFCAT-RETIRADA`, vivienda real del fundador)**: **no verificable con fixtures existentes** — ninguna fixture del repositorio contiene la geometría catastral real de esta referencia (confirmado con `grep -r "REFCAT-RETIRADA" tests/` y `grep -r "REFCAT-RETIRADA" tests/fixtures/catastro/`, cero resultados). El ADR 0016 (historia 0016) ya documentó que su verificación end-to-end se hizo contra el servidor real, no con fixture — este ADR no puede, sin red nueva, confirmar ni descartar el solape para esta parcela. **Queda explícitamente diferido a la verificación en vivo del cierre de la implementación** (mismo patrón que la propia historia 0017 usó en su "Verificación de cierre": `GET /reports/colmenar-de-oreja/REFCAT-RETIRADA` contra el servidor real), sin resultado pre-comprometido.
- **Vías pecuarias — Villaconejos y Colmenar rústica**: confirmado real, `0` features en ambas fixtures `_sin_afeccion` (`parse_wfs_livestock_trails` devuelve lista vacía) → `report.livestock_trails == ()` → `_evaluate_overlaps` devuelve `None` sin necesidad de calcular ningún solape. **Cero `Finding` en ambos casos, consistente con la distancia real ya documentada por la historia (≈1.36-8.33 km los parcelas reales a la zona Red Natura, ≈2.25-2.39 km a la vía pecuaria más próxima).** A diferencia de Red Natura 2000, aquí el filtro BBOX del WFS **sí** se comporta como un filtro ajustado (no devuelve falsos candidatos) — consistente con la causa raíz explicada arriba (features individuales compactos, no un `MultiSurface` disperso).
- **Caso positivo sintético-documentado-como-tal — vías pecuarias**: anillo real de "Vereda del Cristo" (384 puntos, `tests/fixtures/livestock_trails/wfs_cql_colmenar_municipio_completo_15_tramos.xml`) + parcela sintética (cuadrado de 4×4 m centrado en `(468484.75, 4438002.64)`, EPSG:25830, punto interior garantizado del polígono real vía `shapely.representative_point`) → `geometries_overlap` da `True` (confirmado con algoritmo propio y `shapely.intersects`).
- **Caso positivo sintético-documentado-como-tal — Red Natura 2000**: anillo real nº 4 de la zona `SE`/`X` (90 puntos, área real 35828.36 m², el más pequeño de los 5, el único donde es práctico construir un caso a mano) + parcela sintética (cuadrado de 6×6 m centrado en `(446993.04, 4435015.90)`, EPSG:25830, punto interior garantizado) → `geometries_overlap` da `True`, **con cero cruces de borde entre los dos anillos** (confirmado explícitamente) — demuestra el caso de contención total sin intersección de bordes que la propia historia marcó como obligatorio de cubrir.

## Alternativas consideradas

- **Tratar `report.protected_areas`/`report.livestock_trails` no vacío como evidencia suficiente de solape, sin calcular geometría real** (equivalente a confiar en que el WFS ya filtró por proximidad real): rechazada de forma concluyente por la propia verificación de este ADR — habría producido un **falso positivo real y demostrado** en Villaconejos y Colmenar rústica para Red Natura 2000. Es exactamente el atajo que el ADR 0017 ya advertía evitar para cauces (*"nunca el margen de bbox... que solo sirve para decidir qué pedir a la fuente"*), confirmado aquí con un caso real, no hipotético.
- **Mantener `SpatialCondition` como un único dataclass con `meters: float` ignorado para `"overlaps"`**: rechazada — campo sin sentido de negocio en la mitad de las instancias reales (ver Decisión 3).
- **`SpatialLayer` como un único `Literal` plano con los tres valores (`dph_cauce`, `via_pecuaria`, `red_natura_plan`) sin atar `operation`**: rechazada frente a la unión discriminada — habría permitido en tiempo de compilación (sin que `mypy` lo señalara) una combinación sin sentido como `within_distance` + `via_pecuaria`.
- **Calcular un área de solape real (recorte/clipping) para dar siempre un `measured_value` numérico, incluso para Red Natura 2000**: rechazada explícitamente por la propia historia (Fuera de alcance) y por este ADR — algoritmo sustancialmente más complejo (Sutherland-Hodgman o similar) que no aporta nada verificable que `plan_name`/`zone_code`/`zone_name` ya no den como evidencia textual.
- **Mover la verificación de Colmenar urbana al cierre con una nueva fixture capturada ahora**: rechazada para este ADR por instrucción explícita de verificar "sin red nueva" — queda como tarea pendiente, explícita, de la implementación (mismo patrón que la historia 0017 cerró con una verificación en vivo, no con una fixture).
- **No corregir `REGISTRY.md`, dejar el hallazgo 3 tal cual**: rechazada — un hallazgo de verificación de fuente real que resulta falso al medirlo con geometría real no debe quedar como única referencia para futuras decisiones (p. ej. si la historia 0019 de autoría por LLM propusiera una regla nueva de Red Natura 2000, heredaría el mismo error sin la corrección).

## Consecuencias

- `domain/geometry.py` gana `geometries_overlap`, `_ring_overlaps_ring`, `_ring_bbox`, `_bboxes_overlap`, y gana `point_in_ring`/`point_in_any_ring` (movidas desde el adapter de Catastro, mismas firmas y comportamiento). Sigue siendo stdlib puro.
- `adapters/catastro/geometry_ops.py` se reduce a `ring_centroid`; `adapters/catastro/adapter.py` cambia una línea de import (`point_in_any_ring` pasa a venir de `domain.geometry`). `uv run lint-imports` debe ejecutarse tras el cambio para confirmar que mover lógica de adapter→domain no rompe el contrato (se espera que no: es la dirección permitida).
- `domain/rule.py`: `SpatialOperation`/`SpatialLayer` se sustituyen por `WatercourseLayer`/`OverlapLayer` y dos dataclasses (`WithinDistanceCondition`/`OverlapsCondition`) con `SpatialCondition` como alias de unión; `Evidence.measured_value`/`unit` pasan a opcionales; `evaluate_rules`/`_evaluate_spatial` ganan un despacho por `isinstance` y una función nueva `_evaluate_overlaps`.
- `adapters/reports/html.py::_render_evidence_item` debe manejar `measured_value=None` (cambio obligatorio, no opcional, o la implementación rompe en caliente con el primer `Finding` de Red Natura 2000).
- `api/main.py`: dos `Rule` nuevas en `_APPROVED_RULES`, import de `OverlapsCondition`/`WithinDistanceCondition` en vez de `SpatialCondition` como constructor.
- Tres sitios renombran `SpatialCondition(...)` a `WithinDistanceCondition(...)` como cambio mecánico sobre la regla de cauces ya aprobada (historia 0017): `api/main.py`, `tests/adapters/reports/test_html.py`, `tests/domain/test_rule.py` — comportamiento y aserciones sin cambios.
- **Corrección documental recomendada, no bloqueante para el código**: añadir un "Hallazgo 3.1" a `src/parcel_intel/sources/REGISTRY.md` (sección Red Natura 2000) documentando que el hallazgo 3 original confundió "mismo feature devuelto por un filtro BBOX" con "solape geométrico real" — con los números exactos de este ADR (1363.16 m y 8329.95 m de distancia real). Se recomienda a la primera implementación que toque esta historia, igual que la historia 0011 corrigió su propio hallazgo 2 con un hallazgo 2.1.
- **Riesgos residuales, no bloqueantes, señalados explícitamente para revisitar:**
  - El resultado real de Red Natura 2000 para la vivienda del fundador (`REFCAT-RETIRADA`) es desconocido hasta la verificación en vivo del cierre de la implementación — puede ser `0` o `1` `Finding`; ninguno de los dos invalida el diseño de este ADR.
  - `_VIA_PECUARIA_OVERLAP_CONFIDENCE=0.85`/`_RED_NATURA_OVERLAP_CONFIDENCE=0.9`/`severity="actionable"` (ambas reglas): umbrales de producto razonados, no calibrados — a revisar con el fundador, igual que `0.9` de cauces ya quedó señalado en el ADR 0017.
  - `geometries_overlap` sin poda espacial más allá de bbox (sin R-tree): con el peor caso real medido (~1.15 s con poda), aceptable para el flujo actual de una petición HTTP sin caché del MVP; revisitar si una geometría futura de Red Natura 2000 (otro plan, con más anillos o más puntos) empuja el coste por encima de varios segundos, o si aparece un consumidor con más de una petición concurrente.
  - La cita normativa exacta de ambas reglas (artículo preciso, vigencia, y en particular el Decreto autonómico real que aprobó el plan de gestión `"SE"`) sigue sin verificación legal cerrada — mismo límite ya aceptado para RD 849/1986 en el ADR 0017, ahora extendido a dos normas más.
- **No aplica coste de salida de proveedor nuevo**: esta historia no introduce ningún proveedor third-party nuevo — reutiliza IDEM (ya con ADR de entrada, 0011/0014/0015) y el evaluador 100% determinista y local ya existente (ADR 0017).
