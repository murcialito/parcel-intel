# ADR 0017 — Motor de reglas: `Norm`/`Provision`/`Rule`/`Finding` en `domain/`, distancia real polígono↔polilínea, filtro de edificios "forall" (vacuamente verdadero sin edificios)

- Estado: aceptada
- Fecha: 2026-10-16

## Contexto

La historia 0017 (`docs/stories/0017-motor-de-reglas-evaluador-deterministico.md`) deja cuatro preguntas abiertas para el arquitecto y, a diferencia de las historias 0006-0016, no depende de verificar ningún proveedor contra la red real: es la primera pieza puramente de diseño sobre entidades y lógica nuevas, apoyada en evidencia ya conectada (historias 0010-0016). El fundador está en sesión autónoma; este ADR resuelve las cuatro preguntas con criterio razonado, sin bloquear.

Antes de decidir se leyó el código real (no solo `docs/vision.md`):

- `domain/geometry.py` tiene hoy `Geometry` (polígono, uno o más anillos, **sin huecos** a nivel de tipo), `LineGeometry` (polilínea abierta, ADR 0012), `bbox_with_margin`/`EmptyGeometryError` (ADR 0006). Ninguna función calcula distancia entre ambos tipos.
- `domain/building.py`: `Building.origin: BuildingOrigin = Literal["catastro", "detected"]` ya existe desde la historia 0002 — el filtro de atributos de la regla de ejemplo no necesita ningún campo nuevo.
- `domain/land_classification.py`: `LandClassification.general_category` es un `str` libre (dato real del proveedor IDEM, confirmado con valores reales `"Suelo No Urbanizable Común"`/`"Suelo No Urbanizable Protegido"`/`"Suelo Urbanizable..."`). `Parcel` no tiene (ni debe tener) ningún campo `soil_class`.
- `domain/report.py` (`EnrichedParcelReport`): la semántica `None`/tupla vacía varía por campo y está documentada campo a campo — el evaluador debe respetarla, no asumir uniformidad.
- `domain/bulletin.py` (`filter_by_title`) y `domain/ndvi.py` (`summarize_ndvi_grid`, `compute_change_mask`) son el precedente ya establecido (reafirmado en la lección del ciclo 0006-0010 de `LESSONS.md`) de **función pura de dominio sobre datos ya obtenidos, sin ningún port** — mismo criterio que debe aplicarse al evaluador de esta historia.
- `adapters/reports/html.py` importa `domain/report.py` y varios tipos de dominio **directamente**, sin pasar por `ports`/`application` — confirma que una capa superior puede saltar capas intermedias hacia `domain/` cuando no hay colaborador que inyectar (regla `type = "layers"` de `import-linter`, no exige adyacencia estricta).
- `api/main.py` es hoy el único composition root real en uso (`cli/` solo tiene `__init__.py` vacío); instancia los adapters y ejecuta los casos de uso.
- Fixtures reales ya grabadas: `tests/fixtures/catastro/wfsCP_villaconejos_rustica_por_centroide.xml` (geometría real de `99170A90100001`, 1 anillo, 72 puntos) y `tests/fixtures/dph/features_watercourse_villaconejos_rustica_margin2m_barranco_montero.json` (geometría real de "Barranco del Montero", 138 puntos). Se reutilizaron los parsers ya existentes (`adapters/catastro/parsing.parse_wfs_parcels`, `adapters/hydrography/parsing.parse_watercourse_features`) para extraer ambas geometrías reales y calcular la distancia real **antes** de fijar ningún número en este ADR (ver "Decisión 1" y "Resultado real").
- `tests/adapters/catastro/test_catastro_adapter.py::test_get_buildings_parcela_rustica_sin_edificios` confirma el patrón ya conocido: una parcela rústica (como `99170A90100001`) no tiene edificios en el WFS de Catastro. Ninguna fixture de Villaconejos en el repo trae edificios — el `EnrichedParcelReport` real de esta parcela tiene `report.report.buildings == ()`. **Esto es la razón material de la Decisión 4**: cualquier diseño del filtro `attributes.building.origin` que exija "al menos un edificio presente" habría hecho que el caso de demostración exigido por la propia historia (Villaconejos, hallazgo real) produjera **cero** `Finding`, contradiciendo el criterio de aceptación explícito.

## Decisión

**1. Nueva función `distance_polygon_to_line(geometry: Geometry, line: LineGeometry) -> float` en `domain/geometry.py`.** Algoritmo real (no aproximación por centroides): el mínimo, sobre **todos** los pares (segmento de cada anillo de `geometry`, segmento de `line`), de `0.0` si los dos segmentos se cruzan o se tocan (test de orientación con producto cruzado, incluido el caso colineal con solape de *bounding box*), o la menor distancia punto-segmento entre cualquiera de los cuatro extremos y el segmento opuesto en caso contrario. Cada anillo se cierra con índice módulo (`ring[(i+1) % len(ring)]`) **con independencia de si el dato real ya trae el primer punto repetido al final** (confirmado real: los anillos de Catastro sí lo traen, 72 puntos con `ring[0] == ring[-1]`) — mismo criterio de no asumir una única convención que ya usa `adapters/reports/html.py` al cerrar el `path` SVG con `Z` sin mirar si el anillo viene cerrado. Un anillo ya cerrado produce como mucho un segmento de longitud cero adicional, inocuo. `line.points` **no** se cierra (es una polilínea abierta, ADR 0012): los segmentos son solo pares consecutivos `(points[j], points[j+1])`.

   Nueva excepción `EmptyLineGeometryError` en `domain/geometry.py`, hermana de `EmptyGeometryError` (misma motivación: la lección ya registrada sobre no confiar en que `Geometry`/`LineGeometry` garanticen "al menos N puntos" a nivel de tipo) — se lanza si `len(line.points) < 2` (no hay ningún segmento que medir). `EmptyGeometryError` se reutiliza sin cambios para `geometry.rings` vacío.

   Complejidad `O(n_anillo × n_línea)` por cada par anillo/línea — sin poda por *bounding box* ni estructura espacial (R-tree, *sweep line*): a los tamaños reales de este proyecto (72 × 138 puntos en el caso de Villaconejos, cientos como máximo en cualquier geometría observada hasta ahora) el coste es trivial (~10k comparaciones de segmento, microsegundos); no hay evidencia de que haga falta optimizar, y `CLAUDE.md`/el criterio de "simplicidad primero" de este proyecto piden no diseñar para una escala que no existe.

   stdlib puro (`math` únicamente) — cumple la regla de `domain/`.

**2. El evaluador vive en `domain/rule.py`, como función pura, no en `application/` ni envuelto en una clase de caso de uso.** Mismo criterio que `bbox_with_margin` (ADR 0006), `filter_by_title` (ADR 0008) y `summarize_ndvi_grid`/`compute_change_mask` (ADR 0007): es aritmética/lógica sobre datos **ya obtenidos** (`EnrichedParcelReport` + `list[Rule]`), sin E/S, sin reloj, sin ningún port que inyectar — literalmente el caso que ese precedente define. La diferencia con esos tres precedentes es que ellos se invocan desde dentro de `application/generate_enriched_report.py` (son sub-pasos de *componer* el propio `EnrichedParcelReport`), mientras que `evaluate_rules` se invoca **desde el composition root** (`api/main.py`), no desde `application/`, por tres razones concretas:
   - La propia historia fija explícitamente que la lista de reglas `approved` vive "en el composition root (`cli/` o `api/`)" — si el evaluador viviera dentro de un caso de uso de `application/`, ese caso de uso tendría que recibir la lista de reglas por constructor desde el composition root igual, sin ganar ninguna capacidad de intercambio de proveedor (no hay ningún "proveedor" de reglas en esta historia, son datos literales).
   - `EnrichedParcelReport` **no** gana un campo `findings` en esta historia (fuera de alcance explícito: ni persistencia, ni versionado). Envolver `evaluate_rules` en un caso de uso de `application/` solo para inmediatamente descartar su resultado fuera de ese objeto sería ceremonia sin beneficio.
   - `api/main.py` ya importa `adapters/reports/html.py`, que a su vez ya importa `domain/report.py` directamente — el precedente de "capa superior salta a `domain/` sin colaborador que inyectar" ya existe en este mismo flujo de petición.

   Composición exacta en `api/main.py` (análoga en un futuro `cli/`):
   ```python
   report = enriched_use_case.execute(referencia)
   findings = evaluate_rules(report, _APPROVED_RULES)
   return render_parcel_report_html(report, findings)
   ```
   con `_APPROVED_RULES: tuple[Rule, ...]` como constante a nivel de módulo en `api/main.py`, construida con `Rule`/`Provision`/`Norm` de `domain/`, nunca cargada desde YAML/PostGIS (fuera de alcance de esta historia, reafirmado).

**3. Entidades nuevas — ubicación y forma exacta:**

   `domain/norm.py` (nuevo):
   ```python
   @dataclass(frozen=True)
   class Norm:
       title: str
       url: str

   @dataclass(frozen=True)
   class Provision:
       norm: Norm
       article: str
       in_force_since: date
       url: str | None = None  # None = usa la de `norm`; se rellena solo si el artículo tiene URL propia distinta

   def effective_url(provision: Provision) -> str:
       """`provision.url` si existe, si no la de `provision.norm` — función
       pura, mismo criterio que el resto de `domain/` de no añadir métodos
       a los dataclasses (ninguna entidad del proyecto los tiene)."""
       return provision.url or provision.norm.url
   ```

   `domain/rule.py` (nuevo):
   ```python
   SoilClass = Literal["no_urbanizable"]
   SpatialOperation = Literal["within_distance"]
   SpatialLayer = Literal["dph_cauce"]
   RuleStatus = Literal["proposed", "approved", "rejected"]
   Severity = Literal["informational", "actionable"]

   @dataclass(frozen=True)
   class RuleScope:
       region: str           # NO se evalúa en esta historia (ver Decisión 5) — se conserva
                              # tal cual para que `Rule` coincida con el YAML de docs/vision.md
       soil_classes: tuple[SoilClass, ...]

   @dataclass(frozen=True)
   class SpatialCondition:
       operation: SpatialOperation
       layer: SpatialLayer
       meters: float

   @dataclass(frozen=True)
   class AttributeCondition:
       building_origin: tuple[BuildingOrigin, ...]   # reutiliza el tipo ya existente de domain/building.py

   @dataclass(frozen=True)
   class Rule:
       identifier: str
       scope: RuleScope
       spatial: SpatialCondition
       attributes: AttributeCondition
       outcome: str       # texto libre deliberadamente (ver Alternativas) — no un Literal cerrado
       authority: str
       citation: Provision
       status: RuleStatus

   @dataclass(frozen=True)
   class Evidence:
       description: str      # p. ej. "Distancia a curso de agua"
       source_name: str      # p. ej. "Barranco del Montero" — nombre real de la entidad que produjo la evidencia
       measured_value: float # p. ej. 8.535301066249467 — valor real medido, sin redondear (el render formatea)
       unit: str              # p. ej. "m"

   @dataclass(frozen=True)
   class Finding:
       rule: Rule                      # Rule.outcome recuperable vía finding.rule.outcome — sin duplicar el campo
       severity: Severity
       confidence: float                # [0.0, 1.0]
       evidence: tuple[Evidence, ...]

   def evaluate_rules(
       report: EnrichedParcelReport, rules: Sequence[Rule]
   ) -> tuple[Finding, ...]: ...
   ```

   `SpatialOperation`/`SpatialLayer`/`SoilClass` son `Literal` de un único valor **a propósito** (mismo criterio que `BuildingOrigin`/`RuleStatus`, vocabulario que controla el propio proyecto, no un proveedor externo): cualquier regla futura con un `op`/`layer`/`soil_class` distinto (vías pecuarias, Red Natura 2000, inundación — ya conectadas al informe pero fuera de alcance de esta historia) obliga a **ampliar el tipo**, visible en el diff de revisión — se prefiere este coste frente a aceptar `str` libre y fallar en silencio ante un valor no soportado todavía, dado que las consecuencias de una regla mal evaluada son legales reales. `Rule.outcome`/`Rule.authority` sí son `str` libres: a diferencia de los anteriores, su vocabulario lo propondrá un LLM en la historia futura de autoría (revisado por una persona) — cerrarlos en un `Literal` hoy sería diseñar contra un vocabulario que todavía no existe.

**4. `attributes.building.origin`: semántica "ningún edificio presente viola el filtro" (`all(...)`), no "existe un edificio que lo cumple" (`any(...)`) — decisión con consecuencia real verificada, no cosmética.** Con `any()`, una parcela sin ningún edificio (el caso real de Villaconejos, `99170A90100001`, confirmado arriba) haría que la condición de atributos **nunca se cumpliera**, y el hallazgo de demostración exigido por la historia **no se produciría** — se comprobó explícitamente este riesgo antes de fijar la decisión, no después. Con `all()` sobre `report.report.buildings` (vacuamente `True` para una tupla vacía, semántica estándar de Python para un cuantificador universal sobre el conjunto vacío), la condición se interpreta correctamente como "el filtro **excluye** edificios de un origen no listado; no **exige** que exista al menos uno" — coincide con la lectura más razonable de `attributes: { building.origin: [detected, catastro] }` en `docs/vision.md` (una restricción sobre qué construcciones cuentan para la regla, no un requisito de que haya construcción). Con los dos únicos valores reales de `BuildingOrigin` hoy y la regla de ejemplo listando ambos, el filtro es un no-op para **toda** parcela existente — documentado explícitamente en el docstring de `evaluate_rules`, y ejercitado con un test que usa una `Rule` con `building_origin=("catastro",)` (excluyendo `"detected"`) contra un `Building` sintético con `origin="detected"`, confirmando que el filtro sí excluye cuando corresponde.

**5. `scope.region`: campo conservado en el tipo, no evaluado en esta historia — no-op explícito, igual que el filtro de atributos pero sin ningún dato real que lo respalde hoy.** Ninguna entidad del proyecto (`Parcel`, `Provenance`, `EnrichedParcelReport`) tiene un campo "comunidad autónoma"/"provincia" contra el que comparar `scope.region`. Añadirlo ahora sería diseño especulativo (la regla ya la cumplen por construcción las dos únicas parcelas soportadas por el MVP, ambas en Madrid) sin un segundo valor real de `region` que lo justifique — mismo criterio ya usado por el ADR 0004 para rechazar diseño especulativo. Documentado explícitamente en el docstring de `evaluate_rules` como limitación conocida, con la condición de revisitarlo: la primera regla `approved` real con `region` distinta de `"madrid"` (o la primera vez que el MVP soporte un municipio fuera de Madrid) debe decidir entonces de dónde sale el dato de región, no asumir que sigue sin hacer falta.

**6. `scope.soil_class`: "al menos una coincide" contra `LandClassification.general_category`, con prefijo exacto `"Suelo No Urbanizable"` confirmado con dato real.** `_matches_soil_class` devuelve `True` si `soil_classes` está vacío (sin restricción); si no, y `report.land_classifications` es `None` o vacío (sin evidencia — el port de IDEM nunca devuelve una lista vacía como resultado válido, ADR 0011, así que en la práctica solo puede ser `None`), devuelve `False` — **sin evidencia no se afirma el hallazgo**, mismo criterio conservador que el resto de esta decisión (más vale un falso negativo que un falso positivo con consecuencia legal). Si hay evidencia, `any(c.general_category.startswith("Suelo No Urbanizable") for c in classifications)` — confirmado real contra la fixture de Villaconejos (`tests/fixtures/idem/wfs_getfeature_bbox_villaconejos_rustica_margin2m_solape.xml`, parseada con `adapters/idem/parsing.parse_wfs_land_classifications`): de las 3 clasificaciones reales que solapan esa parcela, dos empiezan exactamente por `"Suelo No Urbanizable"` (`"Suelo No Urbanizable Común"`, `"Suelo No Urbanizable Protegido"`) y una no (`"Suelo No Urbanizable Común"` de Chinchón — en realidad las tres empiezan por ese prefijo en este caso concreto, confirmado al ejecutar el parser real). El caso de solape contradictorio (alguna urbanizable, alguna no) sigue sin desambiguarse, mismo límite ya fijado en la historia 0013.

**7. Condición espacial `within_distance` sobre `dph_cauce`:** `_evaluate_spatial` busca, entre `report.watercourses` (si `None` o vacío, sin evidencia → sin hallazgo), el `Watercourse` de menor `distance_polygon_to_line(report.report.parcel.geometry, watercourse.geometry)`; si esa distancia mínima es `<= spatial.meters`, produce una `Evidence` con `source_name=watercourse.name` (o `"curso de agua sin nombre"` si `None`, mismo patrón ya usado por `_render_watercourse_section` del HTML) y `measured_value=` la distancia real medida — nunca el margen de bbox usado para la consulta de red (2 m, `WATERCOURSE_MARGIN_M` de `application/generate_enriched_report.py`), que solo sirve para decidir qué cauces pedir a la fuente, no para afirmar nada sobre la distancia real al polígono.

**8. Severidad y confianza — valores concretos para esta primera regla, marcados explícitamente como umbral de producto, no decisión de arquitectura pura** (ver lección del ciclo 0006-0010 sobre separar ambos tipos de decisión en una sesión autónoma):
   - `severity = "actionable"` para todo `Finding` producido por esta regla (su `outcome` es `requires_authorization`, exige acción del propietario antes de construir). `"informational"` queda sin ningún productor real todavía — reservado para una regla futura cuyo `outcome` sea puramente descriptivo (p. ej. un cambio de NDVI detectado, sin exigir autorización). **A revisar con el fundador**: el vocabulario exacto de dos niveles es una elección razonada pero no la única posible (p. ej. una escala de 3-4 niveles, o una jerarquía por organismo competente).
   - `confidence = 0.9` (constante nombrada, p. ej. `_WITHIN_DISTANCE_CONFIDENCE`), no `1.0`: la distancia en sí es exacta y determinista (no es una estimación de modelo), pero se descuenta porque `Watercourse.geometry` es el eje del cauce, no el deslinde legal del dominio público hidráulico (limitación ya documentada en el ADR 0012) — una distancia real medida de 8.54 m contra el eje puede diferir en unos metros de la distancia real contra el deslinde legal, que es la que de verdad importa para la "zona de policía" de 100 m. **A revisar con el fundador**: `0.9` es una elección razonada pero arbitraria, no calibrada contra ningún caso de desacuerdo conocido entre eje y deslinde.

## Resultado real (Villaconejos, `99170A90100001`)

Calculado reutilizando los parsers reales ya existentes (`adapters/catastro/parsing.parse_wfs_parcels` sobre `tests/fixtures/catastro/wfsCP_villaconejos_rustica_por_centroide.xml`; `adapters/hydrography/parsing.parse_watercourse_features` sobre `tests/fixtures/dph/features_watercourse_villaconejos_rustica_margin2m_barranco_montero.json`) y el algoritmo de la Decisión 1, **sin asumir el resultado por adelantado**:

- Parcela real: 1 anillo, 72 puntos (vértices ya cerrados, `ring[0] == ring[-1]`).
- Cauce real ("Barranco del Montero", demarcación del Tajo): 138 puntos.
- **Distancia mínima real polígono↔polilínea: `8.535301066249467` m** (≈ `8.54` m), muy por debajo del margen de bbox de 2 m usado para la consulta de red (confirma, de paso, que ese margen de 2 m nunca garantizó que la distancia real fuera ≤ 2 m — el bbox es un rectángulo envolvente, no un círculo de radio = margen) y muy por debajo del umbral de la regla (100 m).
- Verificado también contra casos sintéticos de control: línea que cruza el polígono → `0.0`; línea que solo toca un vértice → `0.0`; polígono de 2 anillos con la línea cerca del segundo anillo → distancia correcta medida desde ese anillo, no desde el primero; polilínea de 3 puntos (2 segmentos reales) donde el segmento intermedio es el más cercano → distancia correcta medida desde ese segmento, no desde los extremos.
- `report.report.buildings` para esta parcela real es `()` (parcela rústica, confirmado por el precedente `test_get_buildings_parcela_rustica_sin_edificios` — ninguna fixture de Villaconejos en el repo trae edificios). El filtro `all(b.origin in allowed for b in ())` es vacuamente `True` (Decisión 4) — **sin este diseño, el `Finding` de demostración exigido por la historia no existiría**.
- `land_classifications` reales de esta parcela (3 features, 2 municipios): `"Suelo No Urbanizable Común"` (Villaconejos), `"Suelo No Urbanizable Protegido"` (Villaconejos), `"Suelo No Urbanizable Común"` (Chinchón) — las tres cumplen `soil_class: ["no_urbanizable"]`.
- **Conclusión verificada, no asumida**: la regla `madrid-colmenar-distancia-cauce` (`status: approved`, `meters: 100`) evaluada contra el `EnrichedParcelReport` real de `99170A90100001` produce exactamente **un** `Finding`: `outcome="requires_authorization"`, `severity="actionable"`, `confidence=0.9`, `evidence=(Evidence(description="Distancia a curso de agua", source_name="Barranco del Montero", measured_value=8.535301066249467, unit="m"),)`.

Cita normativa usada para la demostración técnica (no sustituye la revisión legal ya señalada como pendiente en la propia historia): `Norm(title="Reglamento del Dominio Público Hidráulico (Real Decreto 849/1986, de 11 de abril)", url="https://www.boe.es/buscar/act.php?id=BOE-A-1986-10638")`, `Provision(article="art. 9 — zona de policía", in_force_since=date(1986, 4, 30))`, `authority="Confederación Hidrográfica del Tajo"`. El artículo 9 del RD 849/1986 (desarrollo reglamentario de la zona de policía de 100 m definida en el art. 6 del TRLA, RDL 1/2001) es la base real más próxima al concepto citado en `docs/vision.md`; **la fecha de vigencia exacta y si el artículo ha sido modificado desde 1986 no se han confirmado contra el texto consolidado real del BOE** — igual que ya advertía la historia, esto es razonable para la demostración técnica, no una verificación legal cerrada.

## Alternativas consideradas

- **Aproximar la distancia parcela↔cauce con centroide a centroide, o con el punto más cercano de un único anillo (sin recorrer todos los anillos/segmentos)**: rechazada explícitamente por la propia historia (AC de la función de distancia) y por este ADR — para una regla con consecuencia legal real, una aproximación que pueda dar una distancia mayor o menor que la real (p. ej. el centroide de un polígono alargado puede estar a decenas de metros del borde real) es exactamente el tipo de atajo que ya costó un bug de producción en este proyecto (lección de la historia 0001/0002 sobre anillos múltiples, y de la historia 0006 sobre el mismo patrón reapareciendo).
- **Optimizar `distance_polygon_to_line` con poda por *bounding box* o una estructura espacial (R-tree)**: rechazada por ahora. A los tamaños reales observados (decenas-cientos de puntos), el coste `O(n×m)` es microsegundos; optimizar sin evidencia de un caso lento real sería diseñar para una escala que no existe (regla explícita de "simplicidad primero" de este proyecto). Revisitar si una geometría futura con miles de puntos (p. ej. un cauce principal completo sin recortar, o un polígono de clasificación de suelo muy complejo) hace que el coste deje de ser trivial.
- **Evaluador como caso de uso en `application/`, inyectando la lista de reglas por constructor**: rechazada. No hay ningún port que inyectar (cero colaboradores) ni ninguna razón de intercambiabilidad que justifique la ceremonia de una clase — la propia historia ya fija que las reglas viven como constante en el composition root, no detrás de un port.
- **`attributes.building.origin` con semántica "existe un edificio que lo cumple" (`any()`)**: rechazada tras verificar explícitamente que rompía el caso de demostración real exigido por la historia (parcela de Villaconejos sin edificios). Se prefirió la semántica "ningún edificio lo viola" (`all()`, vacuamente verdadera sin edificios) precisamente porque sí sostiene ese caso real y es la lectura más razonable del campo como filtro de exclusión, no de existencia.
- **`scope.region` resuelto contra un valor hardcodeado (p. ej. "siempre madrid" porque hoy solo hay dos municipios soportados, ambos en Madrid)**: rechazada frente a dejarlo explícitamente como no-op. Codificar "siempre true" de forma oculta dentro de una comparación que aparenta evaluar algo real sería peor que no evaluarlo en absoluto y decirlo — la primera opción es más fácil de pasar por alto en una revisión futura.
- **`Rule.outcome`/`authority` como `Literal` cerrado con el único valor conocido hoy (`requires_authorization`)**: rechazada. Esta historia explícitamente no autoriza más reglas, pero la historia *siguiente* (autoría asistida por LLM, ya anticipada en `docs/vision.md`) necesitará outcomes que hoy no existen — cerrar el tipo ahora solo para reabrirlo en la próxima historia no aporta nada, a diferencia de `SpatialOperation`/`SpatialLayer`/`SoilClass`, que sí controla enteramente este proyecto (no un LLM) y donde el coste de ampliar el `Literal` es una señal de revisión deseable.
- **Confianza como enumeración (`"alta"`/`"media"`/`"baja"`) en vez de `float`**: rechazada. El AC de la historia pide explícitamente "un valor de confianza numérico en `[0.0, 1.0]`" — una enumeración perdería la capacidad de comparar/ordenar hallazgos por confianza en un futuro consumidor (p. ej. ordenar la sección de hallazgos de mayor a menor confianza).

## Consecuencias

- Nuevos `domain/norm.py` (`Norm`, `Provision`, `effective_url`) y `domain/rule.py` (`RuleScope`, `SpatialCondition`, `AttributeCondition`, `Rule`, `Evidence`, `Finding`, `evaluate_rules`, tipos `SoilClass`/`SpatialOperation`/`SpatialLayer`/`RuleStatus`/`Severity`). Ninguno importa nada de terceros ni de otras capas salvo otros módulos de `domain/` (`domain.building.BuildingOrigin`, `domain.report.EnrichedParcelReport`, `domain.geometry`) — cumple el contrato de `import-linter` sin cambios al contrato.
- `domain/geometry.py` gana `distance_polygon_to_line` y `EmptyLineGeometryError`; stdlib puro (`math`), sin dependencias nuevas.
- `adapters/reports/html.py` cambia la firma de `render_parcel_report_html` para aceptar `findings: tuple[Finding, ...]` además de `report`, y añade `_render_findings_section` siguiendo el patrón visual ya existente (lista con `outcome`, `severity`, `authority`, cita norma+artículo+URL vía `effective_url`, y cada `Evidence` con su `description`/`source_name`/`measured_value`/`unit`) — importa `domain.rule.Finding` directamente, mismo patrón ya usado para el resto de tipos de dominio en este módulo.
- `api/main.py` gana una constante `_APPROVED_RULES: tuple[Rule, ...]` (la regla de ejemplo, con la cita normativa documentada arriba) y una llamada a `evaluate_rules(report, _APPROVED_RULES)` entre generar el informe y renderizarlo. Ningún cambio a `application/generate_enriched_report.py` ni a `EnrichedParcelReport` (cero campos nuevos, confirmando el AC "composición explícita, sin persistencia").
- Riesgos residuales señalados explícitamente para revisitar, no bloqueantes hoy:
  - **Umbrales de producto, no arquitectura** (marcados aparte, como pide la lección del ciclo 0006-0010): `severity="actionable"`/`"informational"` como único vocabulario de dos niveles, y `confidence=0.9` para esta regla — ambos razonados pero no calibrados ni discutidos con el fundador.
  - `scope.region` no evaluado contra ningún dato real (Decisión 5): revisitar en cuanto exista una regla `approved` real con `region` distinta de `"madrid"`, o el MVP soporte un municipio fuera de Madrid.
  - La cita normativa exacta (artículo literal, vigencia, URL consolidada) sigue pendiente de revisión legal real contra el BOE — ya señalado como pregunta abierta por la propia historia, no resuelto por este ADR, solo documentado con un valor razonable para la demostración técnica.
  - `distance_polygon_to_line` sin poda espacial: revisitar si una geometría futura (cauce principal sin recortar, polígono de clasificación muy complejo) hace que `O(n×m)` deje de ser trivial.
- **No aplica coste de salida de proveedor**: esta historia no introduce ningún proveedor third-party nuevo — el evaluador es 100% determinista, local y stdlib puro. Es precisamente la condición que la propia historia marca como necesaria antes de que la historia futura de autoría de reglas vía LLM pueda apoyarse en un evaluador ya confiable.
