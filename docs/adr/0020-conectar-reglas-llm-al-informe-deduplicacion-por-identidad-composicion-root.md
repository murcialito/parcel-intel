# ADR 0020 — Conectar las reglas aprobadas por el flujo de autoría al informe real: lectura por petición sin caché, `RuleRepositoryPort.list_approved() -> list[Rule]`, deduplicación por identidad estructural en el composition root (nunca en `domain/`), degradación narrow por `psycopg.errors.UndefinedTable`

- Estado: aceptada
- Fecha: 2026-10-17

## Contexto

La historia 0020 (`docs/stories/0020-conectar-reglas-aprobadas-por-llm-al-informe.md`) deja seis preguntas abiertas para el arquitecto. A diferencia de 0017/0018/0019, esta historia no introduce ningún proveedor third-party nuevo ni ningún tipo de dominio nuevo — conecta dos piezas ya construidas y cerradas (el evaluador determinista de 0017/0018 y el flujo de autoría de 0019) sin tocar ninguna de las dos por dentro. Aun así, se decide emitir ADR (no dejarlo como "pura composición sin decisión") porque aparece un mecanismo nuevo — deduplicación de reglas `approved` por identidad estructural — con una decisión de frontera real (¿vive en `domain/` o en el composition root?) y un desempate con consecuencias visibles para el usuario (qué autoridad/cita se le muestra cuando dos reglas describen lo mismo).

**Verificación real ejecutada antes de decidir (no asumida):**

- Estado de la tabla `rule`: confirmado vacía (`SELECT count(*) FROM rule` → `0`) al empezar, tal como ya corrigió el "Contexto" de la propia historia 0020 (truncada por `tests/conftest.py` en ejecuciones de la suite de integración posteriores al cierre de la historia 0019).
- Esquema real de `rule` (`\d rule` contra PostGIS local): coincide exactamente con el SQL documentado en el ADR 0019 — 22 columnas, `CHECK` de `status`/`spatial_operation`/`spatial_layer`, `CHECK` cruzado `spatial_meters`, índice `idx_rule_status`. Sin cambios de esquema necesarios para esta historia.
- Código real leído: `ports/repository.py::RuleRepositoryPort` (hoy `save_proposal`/`list_proposed`/`approve`/`reject`, sin `list_approved`), `adapters/postgis/rule_repository.py::PostgisRuleRepository` (patrón `try/except`+`rollback` explícito por operación, ya establecido), `api/main.py` (`_APPROVED_RULES` como tupla a nivel de módulo, `evaluate_rules(report, _APPROVED_RULES)` invocado desde el composition root, nunca desde `application/` — ADR 0017, decisión 2), `adapters/reports/html.py::_render_findings_section` (confirmado: renderiza cualquier `Finding` por `rule.outcome`/`authority`/`citation`/`evidence`, sin ningún campo que distinga su procedencia — la afirmación de la historia en "Fuera de alcance" es cierta, verificada leyendo el código, no solo citada).
- **Caso real de duplicación, reproducido de nuevo (no solo citado de la historia 0019, que truncó su propia evidencia):** `uv run python -m parcel_intel.cli.main author --layer dph_cauce --text <art. 9 del RD 849/1986, texto real completo>` contra DeepSeek real (`DEEPSEEK_API_KEY` real, PostGIS local real) produjo la propuesta `madrid-proposed-dph_cauce-30680099`, dejada deliberadamente en `status="proposed"` (sin aprobar, para no contaminar el cierre real de la implementación de esta historia — ver "Consecuencias"). Confirmado contra la fila real en PostGIS:

  | campo | regla a mano (`madrid-colmenar-distancia-cauce`, `api/main.py`) | propuesta LLM real (`madrid-proposed-dph_cauce-30680099`) |
  |---|---|---|
  | `spatial.operation` | `within_distance` | `within_distance` |
  | `spatial.layer` | `dph_cauce` | `dph_cauce` |
  | `spatial.meters` | `100.0` | `100` |
  | `scope.soil_classes` | `("no_urbanizable",)` | `{no_urbanizable}` |
  | `attributes.building_origin` | `("catastro","detected")` | `{catastro,detected}` |
  | `outcome` | `"requires_authorization"` | `"requires_authorization"` |
  | `authority` | `"Confederación Hidrográfica del Tajo"` | `"organismo de cuenca"` (genérico — el texto de entrada no nombra la cuenca del Tajo) |
  | `citation.norm.url` | `boe.es/.../BOE-A-1986-10638` | idéntica (mismo BOE) |
  | `citation.article` | `"art. 9 — zona de policía"` | `"Artículo 9, apartados 1 y 2"` (mismo artículo, granularidad distinta) |
  | `citation.in_force_since` | `1986-04-30` | `1986-05-01` (el LLM infiere la fecha de publicación +1 día de vacatio legis típica, sin que el texto de entrada la contenga literalmente) |

  **Siete de los ocho campos que determinan si la regla se activa para una parcela real (`spatial`, `scope.soil_classes`, `attributes.building_origin`) y qué consecuencia produce (`outcome`) son idénticos.** Solo `authority`/`citation` difieren, y solo en precisión/redacción, no en sustancia: ambas se refieren al mismo RD 849/1986, art. 9, y a la misma autoridad real (la Confederación Hidrográfica del Tajo *es* "el organismo de cuenca" competente para esta zona). Si ambas `Rule` llegaran `approved` a `evaluate_rules`, producirían **dos `Finding` casi idénticos** sobre el mismo hecho real (la misma distancia real al mismo cauce), sin que nada en el HTML renderizado explique por qué hay dos. Esto confirma, con evidencia real (no hipotética), exactamente el riesgo que el criterio de aceptación 3 de la historia exige resolver.

## Decisión

**1. Carga de reglas `approved` de la tabla `rule`: en cada petición HTTP, sin caché en memoria, reutilizando la misma conexión que ya se abre para `PostgisParcelRepository`.** La tabla `rule` tiene, por diseño del propio MVP, un número de filas trivial (decenas, no miles) y ya tiene un índice sobre `status` — el coste de un `SELECT ... WHERE status = 'approved'` adicional por petición es equivalente al resto de consultas ya existentes en el mismo flujo (ninguna de las cuales está cacheada salvo `ParcelRepositoryPort`, que cachea por razón de **red externa**, no de PostGIS). Sin caché no hay que diseñar invalidación ni TTL: el criterio de aceptación ("una aprobación tiene efecto en una petición posterior sin reiniciar el proceso") se cumple de la forma más fuerte posible — en la siguiente petición, sin ningún margen de staleness, no "como mucho N segundos después". Mismo criterio de simplicidad ya aplicado por el ADR 0004 (rechazar SQLAlchemy/Alembic) y por el ADR 0019 (rechazar precio de LLM configurable): no se construye un mecanismo nuevo (invalidación de caché) para un problema que no existe todavía (ninguna medición real sugiere que esta consulta sea lenta).

**2. `RuleRepositoryPort` gana un método nuevo, `list_approved(self) -> list[Rule]`** (no `list[ProposedRule]`). `evaluate_rules` (`domain/rule.py`) acepta `Sequence[Rule]`, no `ProposedRule` — devolver `ProposedRule` obligaría a `api/main.py` a desempaquetar `.rule` de cada elemento en el borde, sin ningún beneficio: `explanation`/`LlmUsage` (los dos campos que diferencian `ProposedRule` de `Rule`) no tienen ningún consumidor en el camino de generación del informe, exactamente la misma razón por la que el ADR 0019 rechazó fundir `explanation` dentro de `Rule` en primer lugar — aquí se aplica el argumento simétrico: no sacar `explanation` de donde vive (la tabla, vía `ProposedRule`) hacia un sitio que no la necesita. `PostgisRuleRepository.list_approved()` ejecuta `SELECT ... FROM rule WHERE status = 'approved' ORDER BY created_at` (mismo patrón de query que `list_proposed`, solo cambia el filtro de `status` y las columnas seleccionadas, que se reducen a las que construyen `Rule` — sin las columnas `llm_*`/`explanation`) y construye `Rule` reutilizando la misma lógica de reconstrucción de `SpatialCondition` por `isinstance`/valor de `spatial_operation` ya escrita para `_row_to_proposed_rule` (extraída a un helper compartido `_row_to_rule`, sin duplicar el `if/else` de `within_distance`/`overlaps`). `ORDER BY created_at` importa para el desempate determinista de la Decisión 4: si dos filas `approved` de la tabla describen la misma condición real (caso hoy no observado, pero no descartable a medida que el catálogo crezca), se conserva la más antigua.

**3. `_APPROVED_RULES` se queda exactamente igual, sin recortar ninguna regla — convive con la tabla sin cambios.** Rechazado explícitamente retirar la regla hardcoded de cauces (`madrid-colmenar-distancia-cauce`) aunque el caso real verificado arriba la hace redundante con una propuesta LLM concreta: hacerlo ataría el código a una coincidencia de **hoy** (esta propuesta concreta, con este `identifier` concreto, que ni siquiera está aprobada) en vez de resolver el problema general y recurrente que el catálogo de reglas va a tener en cuanto crezca por el flujo de autoría — cualquier regla nueva aprobada por LLM en el futuro puede volver a coincidir con cualquiera de las tres reglas a mano, no solo con la de cauces. La Decisión 4 (deduplicación genérica) resuelve el problema para **todas** las coincidencias presentes y futuras sin tener que anticipar cuál; retirar una regla a mano por anticipado sería, además, exactamente el riesgo que la propia historia señala en "Fuera de alcance" ("que no se lea como borrar trabajo de las historias 0017/0018") sin ganar nada que la deduplicación no dé ya.

**4. Mecanismo de no-duplicación: comparación por valor de un subconjunto de campos de `Rule` (identidad estructural), ejecutada en el composition root (`api/main.py`), nunca dentro de `domain/rule.py` — deduplicar antes de evaluar, la primera de las tres opciones que la propia historia ofrecía.**

```python
def _deduplicate_approved_rules(rules: tuple[Rule, ...]) -> tuple[Rule, ...]:
    """Dos `Rule` `approved` que comparten la misma condición espacial
    exacta (`spatial`, incluye `meters` cuando aplica), el mismo filtro de
    suelo (`scope.soil_classes`) y de edificios (`attributes`), y la misma
    consecuencia (`outcome`), describen -- a efectos de lo que ve el
    usuario -- el mismo hallazgo real sobre la misma evidencia real:
    evaluarlas por separado produciría dos Finding casi idénticos sin
    ninguna señal de que son la misma cosa (verificado con un caso real,
    ADR 0020). `outcome` SÍ entra en la clave de identidad -- si dos reglas
    exigen la misma condición espacial pero imponen consecuencias legales
    distintas (p. ej. una autorización y una evaluación ambiental por
    normas distintas), no son "la misma cosa" y ambas deben llegar al
    usuario sin fundirse.

    Se conserva solo la primera aparición de cada combinación, en el orden
    en que `rules` llega -- las reglas escritas a mano van primero por
    construcción (ver `api/main.py`), así que ganan el desempate sobre
    cualquier regla equivalente aprobada por el flujo de autoría: ya
    pasaron revisión de arquitecto con cita/autoridad verificadas
    (ADR 0017/0018), mientras una regla equivalente aprobada por LLM trae,
    en el único caso real observado hasta hoy, una autoridad más genérica
    ("organismo de cuenca" vs. "Confederación Hidrográfica del Tajo").
    Entre dos reglas aprobadas por el flujo de autoría que coincidan entre
    sí, gana la más antigua (`list_approved` ya ordena por `created_at`)."""
    seen: set[tuple[object, ...]] = set()
    deduplicated: list[Rule] = []
    for rule in rules:
        key = (rule.spatial, rule.scope.soil_classes, rule.attributes, rule.outcome)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(rule)
    return tuple(deduplicated)
```

Vive en `api/main.py` (o un módulo de composición nuevo bajo `api/`, a discreción de quien implemente, nunca bajo `domain/`), por una razón de alcance explícita, no solo porque la historia lo pida: `rule.spatial`/`rule.scope.soil_classes`/`rule.attributes` son ya `dataclass(frozen=True)` con igualdad y `hash` estructural generados por Python — no hace falta ninguna función nueva de dominio para compararlos, solo construir una tupla de ellos como clave. Es, literalmente, composición (ensamblar y filtrar datos ya existentes), no una regla de negocio nueva que mereciera vivir junto a `evaluate_rules`. **Esto satisface, a la letra, el criterio de aceptación "el evaluador determinista no se toca"**: `evaluate_rules` recibe la lista ya deduplicada exactamente como hoy recibe `_APPROVED_RULES`, sin ningún cambio de firma ni de comportamiento propio.

**Rechazado explícitamente — mover `_deduplicate_approved_rules` a `domain/rule.py` como función hermana de `evaluate_rules`:** sería la ubicación "naturalmente más pura" (lógica sin E/S sobre tipos de dominio, mismo criterio que `distance_polygon_to_line`/`geometries_overlap`), y es una alternativa legítima que un ADR futuro podría revisitar si un segundo composition root (p. ej. `cli/` sirviendo informes algún día) necesitara la misma lógica y duplicarla fuera aceptable. Se rechaza **para esta historia** porque (a) la propia historia fija explícitamente "nunca dentro de `domain/`" como parte de su criterio de aceptación, y no hay today ningún segundo consumidor real que justifique pagar el coste de ampliar `domain/rule.py` por una necesidad de duplicación que hoy tiene un único llamador; (b) moverlo a `domain/` sin necesidad real sería el mismo tipo de diseño especulativo que el ADR 0004 y el ADR 0017 (decisión 5, `scope.region`) ya rechazaron explícitamente. Si `cli/` gana algún día un comando que sirva el mismo informe, extraer esta función a `domain/rule.py` en ese momento es un cambio de una función, sin tocar su lógica.

**5. Degradación ante fallo parcial — se captura `psycopg.errors.UndefinedTable` (y, por la misma causa raíz de "esquema desalineado con el código", `psycopg.errors.UndefinedColumn`), absorbido en `api/main.py`, alrededor exclusivamente de la llamada a `rule_repository.list_approved()` — nunca envolviendo la generación del informe completo.** Ambas son subclases de `psycopg.errors.ProgrammingError` (hermana de `psycopg.OperationalError`, ya capturada aparte para la caída total de PostGIS → 503) — distintas en la jerarquía real de `psycopg` 3, lo que permite distinguir sin ambigüedad "la tabla `rule` no existe en este despliegue" (caso real cubierto: una instalación sin la migración `0004` aplicada) de "PostGIS no responde en absoluto" (caso ya cubierto por el 503 existente). `PostgisRuleRepository.list_approved()` no cambia su patrón ya establecido (`try/except Exception: rollback(); raise`) — el error sigue propagándose tal cual hasta `api/main.py`, que es quien decide si absorberlo, exactamente el mismo reparto de responsabilidad que ya separa "el repositorio nunca decide la política de error HTTP" de "el composition root sí la decide" (ADR 0003/0004).

```python
try:
    db_approved_rules: tuple[Rule, ...] = tuple(rule_repository.list_approved())
    rule_catalog_warning: str | None = None
except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
    db_approved_rules = ()
    rule_catalog_warning = (
        "Catálogo de reglas de autoría no disponible en esta generación "
        "del informe; se muestran solo las reglas revisadas a mano."
    )
all_approved_rules = _deduplicate_approved_rules(_APPROVED_RULES + db_approved_rules)
findings = evaluate_rules(report, all_approved_rules)
return render_parcel_report_html(report, findings, rule_catalog_warning=rule_catalog_warning)
```

Caso (a) de la historia ("la tabla `rule` no tiene ninguna fila `approved` todavía") **no** es un error: `list_approved()` devuelve una lista vacía real, sin lanzar nada — ningún `except` nuevo se dispara, `db_approved_rules = ()`, cero diferencia visible respecto a hoy. Caso (b) (la tabla no existe o el esquema difiere) sí dispara la rama de arriba.

**`render_parcel_report_html` gana un parámetro nuevo, `rule_catalog_warning: str | None = None`**, que `_render_findings_section` muestra como una frase adicional dentro de la sección "Hallazgos" ya existente (`<p><em>{escape(rule_catalog_warning)}</em></p>` antes o después de la lista de `Finding`) — no una sección nueva, no un campo nuevo en `Finding`/`Rule`, consistente con "Fuera de alcance" de la historia (que prohíbe exactamente eso): la nota no describe un hallazgo, describe el estado del catálogo que se evaluó, y vive en el único sitio del HTML donde ese catálogo es relevante.

**6. Salvaguarda adicional ante una regla aprobada con parámetros erróneos: ninguna, más allá de la revisión humana ya existente (`review approve`, historia 0019) — decisión explícita, no omisión.** Dos razones concretas, no solo "simplicidad primero": (a) `review list` ya muestra, desde la corrección documentada en `LESSONS.md` (historia 0016/0019), **todos** los campos estructurados de una propuesta antes de aprobarla — incluido `spatial.meters`, el campo más crítico para detectar un valor absurdo (p. ej. `meters=1` o `meters=100000` en vez de `100`) — la persona que aprueba ya tiene, hoy, la información completa para rechazar un valor erróneo; (b) ningún caso real observado hasta ahora (incluida la verificación de esta historia) ha producido un valor fuera de rango — diseñar una validación de cotas (`meters` entre X e Y) sin ningún caso real que la motive sería el mismo diseño especulativo que el ADR 0017 ya rechazó para `scope.region`. La deduplicación de la Decisión 4 **no** es una salvaguarda de este tipo: solo fusiona condiciones *idénticas*, nunca corrige ni detecta una condición *distinta pero errónea* (p. ej. una propuesta con `meters=10` en vez de `100` no coincidiría con la regla a mano y pasaría intacta) — esto se señala explícitamente como riesgo residual, no resuelto por esta historia.

## Caso real de verificación dejado tras este ADR

La propuesta real `madrid-proposed-dph_cauce-30680099` (tabla `rule`, PostGIS local de este entorno) queda **deliberadamente en `status="proposed"`, sin aprobar** — instrucción explícita para no contaminar el cierre real de la implementación de esta historia, que debe generar su propia evidencia de cierre (aprobar esta propuesta u otra equivalente, pedir el informe real de Villaconejos, y documentar cuántos `Finding` de cauce aparecen y con qué `identifier`, tal como ya exige el criterio de aceptación 2 de la historia). La implementación puede reutilizar esta misma fila (aprobándola con `review approve madrid-proposed-dph_cauce-30680099`) o generar una nueva — cualquiera de las dos reproduce el mismo caso real ya verificado aquí.

## Alternativas consideradas

- **Caché en memoria de las reglas `approved` con TTL** (p. ej. 30 s, invalidada por tiempo): rechazada — introduce un parámetro de producto (el TTL) sin ningún caso real de que la consulta sea lenta, y complica el criterio de aceptación ("efecto en una petición posterior") al obligar a definir qué significa "posterior" en presencia de una caché. La lectura sin caché ya cumple el AC de la forma más fuerte posible sin ningún mecanismo nuevo.
- **`RuleRepositoryPort.list_approved() -> list[ProposedRule]`**: rechazada — obligaría a desempaquetar `.rule` en el borde sin que ningún consumidor real necesite `explanation`/`LlmUsage` en el camino del informe, repitiendo en sentido inverso el argumento que ya usó el ADR 0019 para no fundir `explanation` dentro de `Rule`.
- **Retirar `madrid-colmenar-distancia-cauce` de `_APPROVED_RULES` ahora que existe una propuesta LLM real equivalente**: rechazada — ataría el código a una coincidencia de hoy con una propuesta concreta ni siquiera aprobada, en vez de resolver el problema general (cualquier regla futura puede coincidir con cualquiera de las tres reglas a mano) que la deduplicación genérica ya resuelve sin necesidad de anticipar cuál.
- **Deduplicación por igualdad completa de `Rule` (incluido `identifier`/`authority`/`citation`/`status`)**: rechazada — con `identifier` siempre distinto (generado aleatoriamente, ADR 0019) y `authority`/`citation` casi nunca idénticos carácter por carácter (confirmado con el caso real: `"art. 9 — zona de policía"` vs. `"Artículo 9, apartados 1 y 2"`), una igualdad completa nunca detectaría el caso real que motiva esta decisión — habría sido una "deduplicación" que nunca deduplica nada real.
- **Mostrar ambas reglas con una distinción visual** (p. ej. "(regla revisada por IA)" junto al `Finding` de origen LLM): rechazada por instrucción explícita de "Fuera de alcance" de la historia (ningún campo/etiqueta de origen nuevo en `Finding`); también habría exigido que `Finding`/`ProposedRule` conservaran el origen de la `Rule` tras `approve`, dato que `PostgisRuleRepository.approve()` hoy no distingue de ningún otro campo (todas las filas de `rule`, vengan de donde vengan, son indistinguibles por esquema salvo por tener `llm_*` siempre poblado — incluso una regla a mano insertada a futuro en la tabla tendría que rellenarlos con algún valor convencional, ensuciando el esquema sin necesidad).
- **Validación automática de cotas de `meters` (p. ej. entre 1 y 500) antes de `approve` o antes de evaluar**: rechazada por falta de un caso real que la motive (ver Decisión 6) — revisitar si alguna vez se observa una aprobación real con un valor absurdo que la revisión humana no detectó.
- **Envolver la composición de reglas (unión + dedup + `evaluate_rules`) en un caso de uso de `application/`**: rechazada por el mismo razonamiento ya usado por el ADR 0017 (decisión 2) para no envolver `evaluate_rules` solo: no hay ningún port nuevo que inyectar (el `RuleRepositoryPort` ya se inyecta donde ya vivía, en el composition root) ni ninguna razón de intercambiabilidad — sería ceremonia sin beneficio sobre las ~4 líneas reales que requiere.

## Consecuencias

- `ports/repository.py::RuleRepositoryPort` gana `list_approved(self) -> list[Rule]`. `adapters/postgis/rule_repository.py::PostgisRuleRepository` implementa el método nuevo, con un helper `_row_to_rule` extraído y reutilizado por `_row_to_proposed_rule` (refactor sin cambio de comportamiento en los métodos existentes).
- `api/main.py` gana: la llamada a `rule_repository.list_approved()` (misma conexión ya abierta, misma `with get_connection()`), la función `_deduplicate_approved_rules`, el `try/except` narrow sobre `psycopg.errors.UndefinedTable | psycopg.errors.UndefinedColumn`, y el paso de `rule_catalog_warning` a `render_parcel_report_html`. `_APPROVED_RULES` no cambia.
- `adapters/reports/html.py::render_parcel_report_html`/`_render_findings_section` ganan el parámetro `rule_catalog_warning: str | None = None` — compatible hacia atrás (valor por defecto), ningún test existente que no lo pase necesita cambiar su aserción salvo que verifique explícitamente la ausencia del mensaje.
- `domain/rule.py` y `evaluate_rules`: **cero cambios**, confirmando el criterio de aceptación explícito de la historia. `uv run lint-imports` no necesita ningún cambio de contrato — toda la composición nueva vive en `api/main.py`, ya en la capa superior del contrato de capas existente.
- Riesgos residuales señalados explícitamente, no bloqueantes:
  - La deduplicación por identidad estructural solo detecta condiciones **idénticas** — una regla LLM con un valor erróneo pero distinto (p. ej. `meters=10` en vez de `100`) no se funde con la regla a mano y llega intacta a `evaluate_rules`; la única salvaguarda es la revisión humana ya existente (Decisión 6).
  - Si el catálogo crece lo bastante para que dos reglas aprobadas por el flujo de autoría (no una a mano y una LLM) coincidan entre sí, el desempate por `created_at` (la más antigua gana) no se ha ejercitado con un caso real todavía — revisitar si aparece evidencia de que el desempate "más antigua gana" no es el criterio correcto en la práctica (p. ej. si una revisión posterior corrige una autoridad/cita imprecisa de una propuesta más antigua con una propuesta nueva más precisa, este mecanismo preferiría la vieja, menos precisa).
  - La propuesta real usada para verificar este ADR (`madrid-proposed-dph_cauce-30680099`) queda sin aprobar a propósito — la implementación debe generar su propio caso de cierre (ver sección anterior), no asumir que esta fila sigue en el estado que la implementación necesita.
- **No aplica coste de salida de proveedor nuevo**: esta historia no introduce ningún proveedor third-party — reutiliza PostGIS (ya con coste de salida documentado en ADR 0004/0019) y el evaluador 100% determinista y local ya existente (ADR 0017/0018).
