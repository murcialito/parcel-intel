# ADR 0019 — Autoría de reglas asistida por LLM: adapter DeepSeek (`RuleAuthoringPort`), persistencia PostGIS (tabla `rule`, `RuleRepositoryPort`), `ProposedRule` en dominio y primer comando real de `cli/`

- Estado: aceptada
- Fecha: 2026-10-16

## Contexto

La historia 0019 (`docs/stories/0019-autoria-de-reglas-asistida-por-llm.md`) deja seis preguntas abiertas para el arquitecto y marca explícitamente que introducir DeepSeek **requiere ADR** (`CLAUDE.md`: "Dependencias nuevas de terceros: solo en adapters, y requieren ADR si introduce un proveedor nuevo"). El fundador ya resolvió dos preguntas de producto (sin techo de coste por ahora; sí un segundo caso real de verificación al cierre, además de cauces) — quedan para este ADR las seis de diseño.

Se decide **un único ADR**, no dos o tres, con el mismo criterio ya aplicado en ADR 0012 (dos ports nuevos para una historia, un solo documento) y en ADR 0017/0018 (varias decisiones de diseño grandes para una sola historia, un solo documento): las tres piezas de esta historia (adapter LLM nuevo, persistencia nueva, primer comando real de `cli/`) no son reutilizables de forma independiente hoy — las tres existen única y exclusivamente para que `AuthorRuleProposalUseCase` funcione de punta a punta, y se diseñan y se leen mejor como una sola decisión coherente ("cómo entra la autoría de reglas por LLM al hexágono") que como tres documentos que se citarían constantemente entre sí.

Antes de decidir se leyó el código real, no solo `docs/vision.md`:

- `domain/rule.py` (historias 0017/0018, cerradas): `Rule`, `RuleScope`, `WithinDistanceCondition`, `OverlapsCondition` (unión discriminada `SpatialCondition`), `AttributeCondition`, `Evidence`, `Finding`, `evaluate_rules`. `WatercourseLayer = Literal["dph_cauce"]`, `OverlapLayer = Literal["via_pecuaria", "red_natura_plan"]`. `Rule.outcome`/`Rule.authority` son `str` libres **a propósito** (ADR 0017, decisión 3: *"su vocabulario lo propondrá un LLM en la historia futura de autoría... cerrarlos en un `Literal` hoy sería diseñar contra un vocabulario que todavía no existe"*) — esta historia es exactamente esa historia futura.
- `domain/norm.py`: `Norm(title, url)`, `Provision(norm, article, in_force_since, url=None)`, `effective_url`.
- `domain/provenance.py`: `Provenance(source, url, retrieved_at, license)` — value object de **metadatos de cómo se obtuvo un dato**, compuesto dentro de `Parcel`/`Building`/`Watercourse`/etc. Precedente directo para `LlmUsage` (ver Decisión 3): la metadata de una llamada a un proveedor externo ya tiene un hogar natural en `domain/`, no en el adapter.
- `ports/repository.py`: un único `ParcelRepositoryPort` compuesto (ADR 0005), con la justificación explícita de preferir un port por **unidad de consumo real**, no por tabla. `ports/errors.py`: todo error que puede salir de una llamada a un port vive aquí, exista o no un `except` explícito en `application/` (p. ej. `NoScenesAfterCloudFilterError`, `BulletinNotPublishedError` — ninguno de los dos se captura en `application/`, solo se propagan, y aun así viven en `ports/errors.py`).
- `adapters/*/client.py` + `adapters/*/parsing.py` + `adapters/*/adapter.py`: patrón idéntico en las 9 fuentes existentes (Catastro, PNOA, Sentinel-2, BOE, BOCM, IDEM, hidrografía, vías pecuarias, Red Natura 2000) — un `Protocol` de seam de red (`HttpGetter`/equivalente) redefinido en cada adapter (nunca importado de otro), parsing a `TypedDict`/dataclass propio, cero SDK de terceros en ningún caso. **Ninguno de los 9 adapters usa `pydantic`** pese a que `CLAUDE.md` ya lo permite "solo en los bordes" — hasta hoy ninguna fuente lo necesitaba porque todas son XML/JSON con esquema fijo de un proveedor gubernamental conocido. El contrato de `import-linter` (`pyproject.toml`) **ya** incluye `"pydantic"` en `forbidden_modules` de `domain` desde el primer día del proyecto, anticipando exactamente este momento.
- `adapters/postgis/`: `connection.py` (lee `POSTGRES_*` de `os.environ` **dentro del propio módulo adapter**, no en el composition root — precedente directo para cómo `DeepSeekAdapter` debe leer `DEEPSEEK_API_KEY`), `migrate.py` (runner SQL plano, `0001`-`0003` ya aplicadas), `repository.py` (`PostgisParcelRepository`, patrón `try/except`+`rollback` explícito por operación, `connection.transaction()` para atomicidad multi-tabla — ADR 0003/0004/0005).
- `cli/__init__.py`: vacío. Ningún comando real existe hoy; `api/main.py` es el único composition root en uso. `CLAUDE.md` ya declara `cli/` y `api/` como el mismo nivel de capa en el contrato de `import-linter` (`"parcel_intel.cli | parcel_intel.api"`), así que `cli/` puede instanciar adapters exactamente igual que `api/main.py` sin ningún cambio de contrato.
- `grep -r DEEPSEEK . --include="*"`: cero resultados en código; solo mencionado en `CLAUDE.md`/`docs/vision.md` como decisión de producto ya cerrada. No existe `.env.example` en el repositorio. Esta historia es la primera en tocar esta pieza de verdad.
- `docs/vision.md` ("Modelo de datos y motor de normativa"): nombra la entidad `rule` en PostGIS y la forma YAML de ejemplo de una regla — ya usada como referencia de forma por ADR 0017 (`Rule` real coincide con ese YAML salvo nombres de campo). La estructura de directorios sugerida por `vision.md` (`rules/` con "CLI de revisión") es documentación de producto, no capa de código — resuelto ya por ADR 0001 ("`sources/` es documentación, no una capa de código"); el mismo criterio aplica aquí: el código real va en `domain/ports/application/adapters/cli`, no en un directorio `rules/` literal.

**Investigación sobre DeepSeek (sin llamada real a la red, por restricción explícita de esta fase — la verificación real es un criterio de cierre ya fijado por la propia historia, no una tarea del arquitecto):** la documentación pública de DeepSeek afirma que su API de chat es compatible con el formato de peticiones/respuestas de OpenAI (`POST /chat/completions` sobre `https://api.deepseek.com`, autenticación `Authorization: Bearer <api_key>`, mismo esquema `messages`/`choices`/`usage`, soporte de modo "JSON Output" vía `response_format: {"type": "json_object"}`), y no publican ningún paquete PyPI propio — recomiendan reutilizar el SDK `openai` apuntando su `base_url` al dominio de DeepSeek. **Esto es una afirmación de documentación de terceros, no una verificación** — aplica literalmente la lección ya registrada en este proyecto sobre `GetCapabilities` de Catastro (`LESSONS.md`, ciclo 0001-0002): *"nunca confiar en un documento de autodescripción... solo una petición real... cuenta como verificación"*. Este ADR diseña **asumiendo** ese contrato (es razonable partir de él, igual que las historias 0006-0016 partían de un `GetCapabilities` real como primera pista, nunca como verificación final), pero **la implementación debe confirmar el contrato HTTP exacto con la primera llamada real de la "Verificación real end-to-end" que la propia historia ya exige antes de dar este diseño por cerrado** — si el contrato real difiere (nombre de campo distinto, ausencia de `response_format`, límites de tokens distintos), el diseño de `adapters/deepseek/parsing.py` se ajusta sin tocar `ports/`, `application/` ni `domain/` (la frontera hexagonal es precisamente la que absorbe esa sorpresa).

## Decisión

**1. `RuleAuthoringPort` nuevo en `ports/rule_authoring.py`, un único método nombrado por capacidad — mismo patrón que los 9 ports existentes, no un método genérico de "chat completion".**

```python
class RuleAuthoringPort(Protocol):
    """Capacidad: proponer los campos estructurados y la explicación de una
    `Rule` candidata a partir de texto normativo real y la capa de evidencia
    ya elegida por la persona que invoca el comando (nunca por el LLM)."""

    def propose_rule(
        self, article_text: str, layer: RuleLayer
    ) -> RuleProposalDraft: ...
```

Rechazado explícitamente un método tipo `complete(prompt: str) -> str` (envoltorio genérico de "LLM de propósito general"): repetiría, para el único consumidor real de este proyecto, el mismo error que ya evitaron los 9 ports anteriores — un port genérico por transporte, no por capacidad de negocio, obliga a `application/` a conocer la forma del prompt/JSON, violando que el adapter (no el caso de uso) es quien sabe cómo pedir y parsear la respuesta de **este** proveedor concreto.

`RuleLayer = WatercourseLayer | OverlapLayer` (alias nuevo, aditivo, en `domain/rule.py`) — el port solo acepta uno de los tres valores ya cerrados, nunca `str` libre: si se añade una capa nueva en el futuro (p. ej. `flood_hazard`), el tipo del port se amplía a la vez que `domain/rule.py`, visible en el diff, mismo criterio ya fijado por ADR 0017/0018 para `SpatialLayer`.

**Adapter `DeepSeekAdapter` en `adapters/deepseek/` (paquete nuevo), mismo trío de módulos que los 9 adapters existentes:**

- `client.py`: seam de red propio (nunca importado de otro adapter, mismo criterio que `hydrography/client.py` declara explícitamente), pero de **POST JSON con cabecera de autenticación**, forma nueva en este proyecto (los 9 adapters anteriores son todos GET sin autenticación):

  ```python
  class LlmHttpPoster(Protocol):
      def __call__(
          self, url: str, headers: dict[str, str], json_body: dict[str, object]
      ) -> dict[str, object]: ...

  _TIMEOUT_SECONDS = 60.0          # más alto que el GET de 30 s de los otros 9
                                    # adapters (hydrography, idem, pnoa...): una
                                    # generación de LLM puede tardar decenas de
                                    # segundos, no es una consulta WFS puntual.
  _RETRYABLE_STATUS = {429, 500, 502, 503, 504}
  _MAX_ATTEMPTS = 2                # como mucho 1 reintento
  _RETRY_BACKOFF_SECONDS = 2.0

  def default_llm_http_poster(url, headers, json_body) -> dict[str, object]:
      for attempt in range(_MAX_ATTEMPTS):
          try:
              response = requests.post(url, headers=headers, json=json_body, timeout=_TIMEOUT_SECONDS)
          except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
              if attempt < _MAX_ATTEMPTS - 1:
                  time.sleep(_RETRY_BACKOFF_SECONDS)
                  continue
              raise
          if response.status_code in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS - 1:
              time.sleep(_RETRY_BACKOFF_SECONDS)
              continue
          if response.status_code >= 400:
              raise DeepSeekApiError(response.status_code, response.text[:500])
          return response.json()
      raise AssertionError("inalcanzable")  # _MAX_ATTEMPTS siempre termina por return o raise
  ```

  **Reintentos — razonado explícitamente, no copiado de los otros adapters (que no manejan dinero real):** se reintenta como mucho **una vez** solo ante fallo de conexión/timeout de cliente o un 5xx/429 del servidor — nunca ante 4xx (400/401/402/403/404), que señalan un problema que repetir no arregla (API key inválida, saldo insuficiente, petición mal formada) y que, a diferencia de un timeout, **sabemos con certeza que no generó tokens de salida que cobrar**. El riesgo real y explícito, aceptado para el MVP: un timeout de **cliente** no garantiza que el servidor no haya terminado de generar y cobrado la respuesta — reintentar en ese caso tiene un riesgo pequeño y no eliminado de doble coste. Se acepta este riesgo con tres mitigaciones: (a) volumen bajísimo en este MVP (una llamada por invocación manual del comando, no un proceso automático en bucle), (b) sin techo de coste todavía (decisión ya tomada por el fundador), y (c) el coste de cada llamada que sí se registra queda siempre visible en la tabla `rule` — un doble cobro invisible al cliente seguiría siendo visible como "coste más alto de lo esperado para este texto" al revisar los datos reales, justo la razón de ser del propio criterio de aceptación de registro de coste.

- `parsing.py`: **primer uso de `pydantic` en este proyecto**, exactamente donde `CLAUDE.md` ya lo prevé ("solo en los bordes"). Valida la respuesta del LLM contra un esquema estricto y la convierte a un dataclass de dominio antes de que cruce la frontera del adapter — nunca un `pydantic.BaseModel` ni un `dict[str, object]` sin tipar llega a `application/`:

  ```python
  class _RuleProposalSchema(BaseModel):
      model_config = ConfigDict(extra="forbid")
      soil_classes: list[Literal["no_urbanizable"]]
      meters: float | None = None
      outcome: str = Field(min_length=1, max_length=100)
      authority: str = Field(min_length=1, max_length=200)
      norm_title: str = Field(min_length=1, max_length=300)
      norm_url: str
      article: str = Field(min_length=1, max_length=200)
      in_force_since: date
      provision_url: str | None = None
      explanation: str = Field(min_length=20, max_length=2000)

      @field_validator("norm_url", "provision_url")
      @classmethod
      def _looks_like_url(cls, value: str | None) -> str | None:
          if value is not None and not value.startswith(("http://", "https://")):
              raise ValueError("debe empezar por http:// o https://")
          return value

  def parse_rule_proposal(content: str, layer: RuleLayer, usage: LlmUsage) -> RuleProposalDraft:
      try:
          schema = _RuleProposalSchema.model_validate_json(content)
      except (ValidationError, ValueError) as error:
          raise InvalidLlmProposalError(content) from error
      requires_meters = layer == "dph_cauce"
      if requires_meters != (schema.meters is not None) or (requires_meters and schema.meters <= 0):
          raise InvalidLlmProposalError(content)
      return RuleProposalDraft(
          soil_classes=tuple(schema.soil_classes), meters=schema.meters,
          outcome=schema.outcome, authority=schema.authority,
          norm_title=schema.norm_title, norm_url=schema.norm_url,
          article=schema.article, in_force_since=schema.in_force_since,
          provision_url=schema.provision_url, explanation=schema.explanation,
          usage=usage,
      )
  ```

  El esquema **nunca** incluye `layer`, `operation`, `status`, `region` ni `building_origin` — exactamente la restricción que pide el criterio de aceptación ("el LLM nunca decide a qué capa se dirige... ni aprueba sus propias reglas"): esos campos no están en el JSON que se le pide al LLM en absoluto, así que es estructuralmente imposible que el LLM los proponga, no solo que se ignoren si los propone (`extra="forbid"` further rechaza cualquier campo no declarado, incluido si el LLM intentara colar un `"status": "approved"`). `meters` es condicional al `layer` ya elegido por el comando: para `dph_cauce` se exige positivo; para `via_pecuaria`/`red_natura_plan` se exige ausente — validado explícitamente en código, no en el esquema de `pydantic` (una unión condicional de este tipo en `pydantic` es más frágil de leer que una comprobación explícita de dos líneas).

- `adapter.py`: `DeepSeekAdapter` implementa `RuleAuthoringPort`. Construye los dos mensajes (`system`: instrucciones fijas + el JSON Schema exacto esperado + los tres valores de capa cerrados con su significado; `user`: el texto del artículo tal cual, sin recortar), llama al seam con `response_format: {"type": "json_object"}` y `temperature: 0.0` (**umbral de producto, no arquitectura, a revisar con el fundador** — mismo criterio de separación que ADR 0017/0018: temperatura baja reduce varianza pero no la elimina, un LLM no es determinista pese a ello, como la propia historia ya reconoce), lee `DEEPSEEK_API_KEY` de `os.environ` en `__init__` (fail-fast, mismo patrón que `adapters/postgis/connection.py` leyendo `POSTGRES_*` dentro del propio adapter, no en el composition root) y calcula `LlmUsage.cost_usd` con la constante de precio documentada abajo (Decisión 4).

  ```python
  class MissingDeepSeekApiKeyError(Exception):
      """DEEPSEEK_API_KEY no está en el entorno. Error de configuración del
      proceso, no de una llamada a un port — vive en el adapter (como
      EmptyGeometryError en adapters/reports/html.py), no en ports/errors.py:
      ningún caso de uso en application/ necesita capturarlo, solo cli/ al
      arrancar."""
  ```

  **Rechazado**: dependencia del SDK `openai` apuntando a `base_url=https://api.deepseek.com`. Es la opción que la propia documentación de DeepSeek recomienda, pero (a) sería la **primera** dependencia de SDK de todo el proyecto — los 9 adapters existentes son unánimes en HTTP a mano, incluidos protocolos mucho más complejos que un POST JSON (OGC WFS/Filter, STAC); (b) el contrato real a usar es, según la propia documentación, "igual que OpenAI" — una única llamada POST con JSON de entrada/salida bien definido no justifica adoptar un SDK completo (con su propio ciclo de vida de cliente, reintentos internos no auditables, y acoplamiento a la semántica de tipos de otro proveedor) solo para una forma de petición trivial de reproducir a mano. Mismo criterio que ADR 0004 rechazando SQLAlchemy/Alembic para dos tablas: no adoptar una dependencia pesada para una necesidad fina.

**2. `ProposedRule`/`RuleProposalDraft`/`LlmUsage` nuevos en `domain/rule.py` — no un campo nuevo en `Rule`.**

```python
@dataclass(frozen=True)
class LlmUsage:
    """Metadatos de una llamada real a un proveedor de LLM — análogo a
    `Provenance` (domain/provenance.py), que ya documenta "cómo se obtuvo
    un dato" para toda fuente externa del proyecto. No se funde con
    `Provenance`: sus campos (modelo/tokens/coste) no tienen sentido para
    las demás fuentes (WFS/WMS sin coste por llamada), y `Provenance` ya
    se usa por composición en toda entidad existente — añadirle campos
    opcionales solo significativos para un productor repetiría la señal
    de abstracción forzada ya señalada en la lección de la historia 0012."""
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float

@dataclass(frozen=True)
class RuleProposalDraft:
    """Lo que el LLM propuso, ya parseado y validado contra los tipos
    cerrados de este módulo (adapters/deepseek/parsing.py construye esto,
    nunca application/). No incluye layer/operation/status/region/
    building_origin: esos los fija AuthorRuleProposalUseCase, nunca el LLM."""
    soil_classes: tuple[SoilClass, ...]
    meters: float | None
    outcome: str
    authority: str
    norm_title: str
    norm_url: str
    article: str
    in_force_since: date
    provision_url: str | None
    explanation: str
    usage: LlmUsage

@dataclass(frozen=True)
class ProposedRule:
    """`Rule` candidata ya ensamblada (status="proposed" siempre) junto a
    su explicación y el coste de la llamada que la produjo. Mismo patrón
    que `Finding` (rule + severity + confidence + evidence): envolver, no
    mezclar campos ajenos dentro de `Rule`."""
    rule: Rule
    explanation: str
    usage: LlmUsage
    created_at: datetime

def spatial_condition_for_layer(layer: RuleLayer, meters: float | None) -> SpatialCondition:
    """Pura: la capa ya determina la operación (dph_cauce -> within_distance,
    las otras dos -> overlaps) — el LLM nunca propone `operation`."""
    if layer == "dph_cauce":
        if meters is None:
            raise ValueError("meters es obligatorio para layer='dph_cauce'")
        return WithinDistanceCondition(operation="within_distance", layer=layer, meters=meters)
    if meters is not None:
        raise ValueError(f"meters no aplica para layer={layer!r}")
    return OverlapsCondition(operation="overlaps", layer=layer)
```

**Rechazado explícitamente — campo `explanation: str | None = None` directo en `Rule`.** `Rule` es la entidad que `evaluate_rules` consume (criterio de aceptación: "cero referencias a LLM en domain/ salvo tipos de datos") y que construyen a mano las tres reglas de `_APPROVED_RULES` en `api/main.py` — añadirle un campo solo significativo para las reglas nacidas de un LLM habría obligado a esos tres sitios ya existentes a pasar `explanation=None` sin ningún motivo de negocio, y habría abierto la puerta, sin necesidad, a que `evaluate_rules`/`Finding` dependieran algún día de un campo que puede no existir. Con `ProposedRule` como envoltorio, `Rule` no cambia en absoluto — ni de forma ni de comportamiento — y los tres sitios existentes (`api/main.py`, dos tests citados en ADR 0018) no se tocan. **La puerta a que `Finding` incorpore la explicación en el futuro (pregunta explícita de la historia) no se cierra**: `Finding.rule.citation`/`outcome` ya son accesibles sin duplicar campos (mismo patrón ya usado por `Finding` desde ADR 0017); un `Finding` futuro que quiera mostrar la explicación de su regla solo necesitaría que esa regla, una vez `approved`, conservara su explicación en algún sitio accesible desde `Rule` o desde donde se construye `_APPROVED_RULES` — decisión de una historia futura, no de esta, y ninguna opción aquí lo impide.

**3. `RuleRepositoryPort` nuevo, añadido a `ports/repository.py` (no un fichero nuevo) junto a `ParcelRepositoryPort` — agrupa los ports con forma de repositorio, en vez de seguir la convención de "un fichero por sustantivo de dominio" que ya rompía `repository.py` desde el ADR 0005.**

```python
class RuleRepositoryPort(Protocol):
    """Capacidad: persistir y revisar propuestas de `Rule`. Un único port
    compuesto (mismo criterio que ParcelRepositoryPort, ADR 0005): los dos
    consumidores reales de esta historia (comando de autoría, comando de
    revisión) comparten la misma tabla y la misma unidad de trabajo, sin
    asimetría de autoridad que justifique partirlo en dos."""

    def save_proposal(self, proposal: ProposedRule) -> None: ...
    def list_proposed(self) -> list[ProposedRule]: ...
    def approve(self, identifier: str) -> None: ...
    def reject(self, identifier: str) -> None: ...
```

`RuleProposalNotFoundError` nueva en `ports/errors.py` (mismo criterio que `ParcelNotCachedError`): `approve`/`reject` la lanzan si el `UPDATE ... WHERE identifier = %s AND status = 'proposed'` afecta cero filas (identificador inexistente **o** ya revisado — la ambigüedad entre ambos casos se acepta explícitamente para el MVP, documentada, mismo nivel de rigor que `NoLandClassificationFoundError` ya acepta no poder distinguir "fuera de cobertura" de "hueco real").

**Tabla nueva `rule`, migración `0004_create_rule` (SQL plano, mismo patrón que `0001`-`0003`, ADR 0004) — el nombre literal que ya usa `docs/vision.md` para esta entidad, sin necesidad de pluralizar ni prefijar.** `RULE` es palabra clave *no reservada* de PostgreSQL (solo relevante para `CREATE RULE`, la característica de reglas de reescritura de consultas, no usada en este proyecto) — usable sin comillas como nombre de tabla; **a confirmar explícitamente en la implementación ejecutando `CREATE TABLE rule (...)` real contra PostGIS**, mismo rigor que la lección ya registrada sobre no asumir comportamiento de `psycopg`/SQL sin ejecutarlo.

```sql
CREATE TABLE rule (
    identifier TEXT PRIMARY KEY,
    region TEXT NOT NULL,
    soil_classes TEXT[] NOT NULL DEFAULT '{}',
    spatial_operation TEXT NOT NULL CHECK (spatial_operation IN ('within_distance', 'overlaps')),
    spatial_layer TEXT NOT NULL CHECK (spatial_layer IN ('dph_cauce', 'via_pecuaria', 'red_natura_plan')),
    spatial_meters NUMERIC,
    building_origins TEXT[] NOT NULL,
    outcome TEXT NOT NULL,
    authority TEXT NOT NULL,
    norm_title TEXT NOT NULL,
    norm_url TEXT NOT NULL,
    provision_article TEXT NOT NULL,
    provision_in_force_since DATE NOT NULL,
    provision_url TEXT,
    status TEXT NOT NULL CHECK (status IN ('proposed', 'approved', 'rejected')),
    explanation TEXT NOT NULL,
    llm_model TEXT NOT NULL,
    llm_prompt_tokens INTEGER NOT NULL,
    llm_completion_tokens INTEGER NOT NULL,
    llm_cost_usd NUMERIC NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    reviewed_at TIMESTAMPTZ,
    CHECK (
        (spatial_operation = 'within_distance' AND spatial_meters IS NOT NULL)
        OR (spatial_operation = 'overlaps' AND spatial_meters IS NULL)
    )
);
CREATE INDEX idx_rule_status ON rule (status);
```

Igual criterio que `building.origin` (ADR 0004): los `CHECK` duplican en SQL los `Literal` de `domain/rule.py` — riesgo de sincronización menor pero real, ya aceptado en este proyecto, documentado aquí otra vez. `identifier` como clave primaria natural (texto), no un `BIGSERIAL` — mismo patrón que `parcel.cadastral_reference` (ADR 0004): el identificador se genera en `AuthorRuleProposalUseCase` (ver Decisión 5, no en la tabla), y es también la referencia legible que usa el comando de revisión (`review approve <identifier>`), evitando una vuelta adicional para que la persona averigüe un ID numérico tras listar. `soil_classes`/`building_origins` como `TEXT[]` de PostgreSQL, confiando en el mapeo automático lista↔array de `psycopg` 3 (adaptación nativa documentada) — **a verificar con un test de integración real antes de dar la implementación por cerrada**, mismo rigor que la lección ya registrada sobre semántica de `psycopg` nunca asumida sin ejecutar.

`PostgisRuleRepository` en fichero nuevo `adapters/postgis/rule_repository.py` (no añadido a `repository.py`): a diferencia de los ports (donde agrupar por "forma de repositorio" ya es el patrón existente), `docs/vision.md` anticipa más entidades PostGIS futuras (`observation`, `layer_feature`, `bulletin_entry`) que tendrán cada una su propio repositorio concreto — seguir añadiéndolas todas al mismo `repository.py` lo convertiría en un módulo cada vez más grande sin ninguna cohesión real entre `Parcel`/`Building` y `Rule` (geometría vs. sin geometría, transacción simple vs. revisión de estado). Un fichero de adapter por familia de entidad es más escalable que uno por port — igual que cada fuente ya tiene su propio directorio de adapter aunque el `Protocol` que implementa viva agrupado en `ports/`.

**4. Precio del modelo DeepSeek: constante documentada en `adapters/deepseek/adapter.py`, marcada explícitamente como no verificada en esta fase de diseño.**

```python
# Precio público por 1M tokens, modelo "deepseek-chat" — fuente:
# https://api-docs.deepseek.com/quick_start/pricing (consultado de memoria,
# NO verificado contra la página real en esta fase de diseño: ninguna
# llamada de red se hizo al escribir este ADR, por restricción explícita
# de la historia). *** LA IMPLEMENTACIÓN DEBE CONFIRMAR ESTE NÚMERO CONTRA
# LA PÁGINA PÚBLICA DE PRECIOS VIGENTE EN LA FECHA DE CIERRE Y ACTUALIZAR
# ESTE COMENTARIO CON LA FECHA DE VERIFICACIÓN REAL. *** Los precios de
# los proveedores de LLM cambian con frecuencia; tratar este valor como un
# hecho ya confirmado sin volver a mirarlo sería repetir, con dinero real,
# el mismo error que la lección de GetCapabilities ya advierte para datos.
_PRICE_PER_MILLION_TOKENS_USD: dict[str, tuple[float, float]] = {
    "deepseek-chat": (0.27, 1.10),  # (entrada, salida) -- A VERIFICAR
}

def _cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    input_price, output_price = _PRICE_PER_MILLION_TOKENS_USD[model]
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
```

**Rechazado**: hacer el precio configurable por variable de entorno o fichero externo. Con un único modelo usado y sin ningún caso real de necesitar cambiarlo en caliente, una constante nombrada con su fuente y la obligación explícita de revisarla es más simple y más auditable en el diff de cada cambio futuro (mismo criterio de simplicidad primero que ya rechazó una tabla de precios en base de datos para dos municipios en ADR 0004).

**Registro de coste/tokens: campo persistido junto a la propuesta (columnas `llm_*` de la tabla `rule`), sin log estructurado aparte.** Cada propuesta nace de exactamente una llamada real al LLM (una propuesta inválida no se persiste en absoluto, AC2) — la relación es 1:1, así que un log aparte para agregar múltiples llamadas por propuesta no tiene ningún caso real que lo justifique hoy. Si una historia futura permite reintentar una autoría fallida sin cerrar el proceso (hoy no existe: cada invocación del comando es una llamada), ese sería el momento de revisitar esta decisión.

**5. `cli/main.py` — primer comando real de `cli/`, composition root igual que `api/main.py` (mismo contrato de capas, sin cambio en `pyproject.toml`).**

```
uv run python -m parcel_intel.cli.main author --layer dph_cauce --text ruta/articulo.txt
uv run python -m parcel_intel.cli.main review list
uv run python -m parcel_intel.cli.main review approve <identifier>
uv run python -m parcel_intel.cli.main review reject <identifier>
```

`region` no es un argumento del comando — se fija como constante `"madrid"` dentro de `cli/main.py` al construir el caso de uso, tal como la propia historia fija "región fijo, no la elige quien invoca el comando" (no hay nada que validar ni testear aparte: es un valor literal, igual que `_FIXED_BUILDING_ORIGINS`). `--layer` usa `choices=["dph_cauce", "via_pecuaria", "red_natura_plan"]` de `argparse` para una UX inmediata, **pero `AuthorRuleProposalUseCase.execute()` repite la misma validación de forma independiente** (comprobando contra `typing.get_args(WatercourseLayer) + typing.get_args(OverlapLayer)`) antes de invocar el port — la barrera real de arquitectura es el caso de uso, no la conveniencia de `argparse`; un futuro segundo composition root (p. ej. si `api/` expusiera este flujo) debe tener la misma garantía sin depender de `argparse`.

- `author`: composition root instancia `DeepSeekAdapter()` + `PostgisRuleRepository(conn)` + `AuthorRuleProposalUseCase(llm=..., repository=...)`, lee el fichero de texto, llama a `execute(article_text, layer)`, imprime el `identifier` generado y un resumen (outcome, authority, explicación) — o el error (`InvalidRuleLayerError`/`InvalidLlmProposalError`/`DeepSeekApiError`/`MissingDeepSeekApiKeyError`) con salida no-cero.
- `review list/approve/reject`: **llaman a `PostgisRuleRepository` directamente, sin envolverlo en un caso de uso de `application/`.** Mismo razonamiento que ADR 0017 usó para no envolver `evaluate_rules` en un caso de uso: cero lógica de negocio propia más allá de delegar a un único método de un único port (`list_proposed`/`approve`/`reject`), sin ningún segundo colaborador que combinar ni ninguna transformación de dato — envolverlo en `application/` sería ceremonia sin beneficio. A diferencia de `author` (que sí coordina dos ports + genera un identificador + ensambla una `Rule` desde piezas sueltas — lógica real, candidata legítima a `application/`), `review` es composición pura de wiring, que `CLAUDE.md` ya reserva al composition root.

**Generación del identificador — decisión 5.5, dentro de `AuthorRuleProposalUseCase`, no del LLM ni de la tabla:** `f"{region}-proposed-{layer}-{uuid4().hex[:8]}"` (p. ej. `"madrid-proposed-dph_cauce-a1b2c3d4"`). Mismo principio ya aplicado a `layer`/`status`/`building_origin`: cualquier dato que el proyecto controla por completo (aquí, un identificador arbitrario sin significado legal) no se le pide al LLM — pedírselo arriesgaría colisiones o formatos inconsistentes sin ganar nada. Colisión del sufijo aleatorio de 4 bytes: ~1 entre 4 300 millones, aceptado como riesgo despreciable sin lógica de reintento ante colisión (mismo nivel de rigor que ADR 0017 aceptando el coste `O(n×m)` de `distance_polygon_to_line` sin poda, por falta de evidencia de que haga falta más).

**`AuthorRuleProposalUseCase` en `application/author_rule_proposal.py` — único caso de uso nuevo, con reloj inyectado capturado una sola vez (lección del ciclo 0006-0010: nunca volver a invocarlo dentro del mismo `execute()`):**

```python
class AuthorRuleProposalUseCase:
    def __init__(
        self,
        llm: RuleAuthoringPort,
        repository: RuleRepositoryPort,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._llm = llm
        self._repository = repository
        self._clock = clock

    def execute(self, article_text: str, layer: str) -> ProposedRule:
        if layer not in (*get_args(WatercourseLayer), *get_args(OverlapLayer)):
            raise InvalidRuleLayerError(layer)
        validated_layer = cast("RuleLayer", layer)

        draft = self._llm.propose_rule(article_text, validated_layer)
        now = self._clock()
        identifier = f"madrid-proposed-{validated_layer}-{uuid4().hex[:8]}"

        rule = Rule(
            identifier=identifier,
            scope=RuleScope(region="madrid", soil_classes=draft.soil_classes),
            spatial=spatial_condition_for_layer(validated_layer, draft.meters),
            attributes=AttributeCondition(building_origin=("catastro", "detected")),
            outcome=draft.outcome,
            authority=draft.authority,
            citation=Provision(
                norm=Norm(title=draft.norm_title, url=draft.norm_url),
                article=draft.article,
                in_force_since=draft.in_force_since,
                url=draft.provision_url,
            ),
            status="proposed",
        )
        proposal = ProposedRule(rule=rule, explanation=draft.explanation, usage=draft.usage, created_at=now)
        self._repository.save_proposal(proposal)
        return proposal
```

`InvalidRuleLayerError` nueva en `ports/errors.py` (no en `adapters/deepseek/`): la lanza `application/`, que solo puede importar `ports`/`domain` — mismo criterio exacto que `InvalidCadastralReferenceError`/`InvalidBulletinDayError`, ambos "formato de entrada rechazado antes de cualquier llamada de red", ya en ese fichero.

## Alternativas consideradas

- **SDK `openai` apuntando a `base_url` de DeepSeek**: rechazada (ver Decisión 1) — primera dependencia de SDK del proyecto para una necesidad que un POST JSON a mano ya cubre, rompiendo la uniformidad de los 9 adapters existentes sin ganancia real.
- **`RuleAuthoringPort` genérico tipo `complete(prompt: str) -> str`**: rechazada — repite el antipatrón que los 9 ports existentes ya evitan (nombrar por transporte, no por capacidad); obligaría a `application/` a conocer la forma del JSON pedido/parseado, filtrando un detalle de proveedor a través de la frontera hexagonal.
- **Explicación como campo nuevo en `Rule` (`explanation: str | None = None`)**: rechazada (ver Decisión 2) — ensucia la entidad que ya consumen `evaluate_rules` y las tres reglas aprobadas a mano con un campo solo significativo para una fuente, repitiendo la señal de abstracción forzada ya evitada por ADR 0018 para `Evidence`.
- **Un solo `RuleRepositoryPort` por cada capacidad (`RuleProposalReader`/`RuleProposalWriter`) en vez de un único port compuesto**: rechazada por la misma razón que ADR 0005 rechazó partir `ParcelRepositoryPort` en dos — no hay asimetría de autoridad entre los dos consumidores reales (`author`/`review`) que lo justifique.
- **Tabla `rule_proposal` en vez de `rule`**: rechazada — `docs/vision.md` ya nombra la entidad como `rule` sin más; introducir un nombre distinto solo porque hoy solo existen filas `proposed` sería una complicación sin beneficio (la tabla también almacenará `approved`/`rejected` tras la revisión, por diseño).
- **Log estructurado aparte para coste/tokens, además de o en vez de la columna en `rule`**: rechazada por ahora (ver Decisión 4) — relación 1:1 entre llamada y propuesta en esta historia, sin ningún caso real de agregación que un log resolviera y la columna no.
- **`AuthorRuleProposalUseCase` también para `review list/approve/reject`** (un único caso de uso "de reglas" con varios métodos): rechazada (ver Decisión 5) — mezclaría una operación con lógica real (ensamblar una `Rule` desde piezas sueltas + generar un identificador + coordinar dos ports) con operaciones de wiring puro (delegar un método a un port), sin beneficio de cohesión real.
- **Identificador de propuesta provisto por quien invoca el comando** (en vez de autogenerado): rechazada — obligaría a la persona a inventar un identificador único a mano cada vez, con riesgo real de colisión con `_APPROVED_RULES` o con otra propuesta, sin ningún beneficio sobre un sufijo aleatorio corto generado por el propio comando.
- **Techo de coste máximo por propuesta, rechazando la llamada si se estima por encima de un umbral**: rechazada para esta historia por decisión explícita ya tomada por el fundador (ver historia, "Resueltas por el fundador") — el diseño no la impide: añadirla después sería una comprobación dentro de `AuthorRuleProposalUseCase.execute()`, antes o después de `propose_rule`, sin rediseño.

## Consecuencias

- **Nuevo en `domain/rule.py`**: `RuleLayer`, `spatial_condition_for_layer`, `RuleProposalDraft`, `LlmUsage`, `ProposedRule`. Cero imports de terceros ni de otras capas (solo `datetime`/`date` de stdlib, ya usados en el módulo) — `uv run lint-imports` no necesita ningún cambio de contrato.
- **Nuevo `ports/rule_authoring.py`** (`RuleAuthoringPort`). **`ports/repository.py`** gana `RuleRepositoryPort`. **`ports/errors.py`** gana `InvalidRuleLayerError`, `InvalidLlmProposalError`, `RuleProposalNotFoundError`.
- **Nuevo paquete `adapters/deepseek/`**: `client.py` (`LlmHttpPoster`, `default_llm_http_poster`, `DeepSeekApiError`), `parsing.py` (`_RuleProposalSchema` de `pydantic`, `parse_rule_proposal`), `adapter.py` (`DeepSeekAdapter`, `MissingDeepSeekApiKeyError`, constante de precio). **Primera dependencia nueva de runtime desde el ADR 0004**: `pydantic>=2.0` en `pyproject.toml` — el contrato de `import-linter` **ya** prohíbe `pydantic` en `domain` desde el inicio del proyecto, sin cambios necesarios.
- **Nuevo `adapters/postgis/migrations/0004_create_rule.{up,down}.sql`** y **`adapters/postgis/rule_repository.py`** (`PostgisRuleRepository`).
- **Nuevo `application/author_rule_proposal.py`** (`AuthorRuleProposalUseCase`).
- **Nuevo `cli/main.py`** — primer código real en `cli/` (hasta ahora solo `__init__.py` vacío); composition root paralelo a `api/main.py`, mismo nivel de capa ya declarado en el contrato de `import-linter`, sin cambio de contrato necesario.
- **Cero cambios** en `domain/rule.py::evaluate_rules`, `api/main.py`, `application/generate_enriched_report.py` — confirmando el criterio de aceptación explícito de esta historia.
- `CLAUDE.md` debe ganar, en su sección "Comandos", las cuatro invocaciones literales de `cli/main.py` de la Decisión 5 y la variable de entorno `DEEPSEEK_API_KEY` — pendiente de que la implementación las añada y las ejecute tal cual están escritas, mismo rigor que la lección ya registrada sobre comandos documentados que deben funcionar literalmente.
- **Riesgos residuales señalados explícitamente, no bloqueantes, para la implementación:**
  - **El contrato HTTP exacto de DeepSeek (forma de `response_format`, nombres de campo de `usage`, límites de tokens) es una asunción de documentación, no una verificación** — debe confirmarse con la primera de las dos llamadas reales que la propia historia ya exige antes del cierre; si difiere, el ajuste queda contenido en `adapters/deepseek/`.
  - **El precio por millón de tokens de `deepseek-chat` es un valor no verificado en esta fase de diseño** — debe confirmarse contra la página pública de precios vigente antes de que cualquier coste calculado se trate como un dato real, y el comentario junto a la constante debe actualizarse con la fecha de verificación real.
  - **El mapeo lista↔`TEXT[]` de `psycopg` 3 para `soil_classes`/`building_origins` se asume, no se verifica en este ADR** — exige un test de integración real contra PostGIS antes del cierre, mismo rigor que la lección ya registrada sobre la semántica de transacciones de `psycopg`.
  - **`rule` como nombre de tabla sin comillas** se asume válido por ser palabra clave no reservada de PostgreSQL — a confirmar con la migración real ejecutada, no solo con la documentación de PostgreSQL.
  - **Riesgo de doble coste ante un timeout de cliente seguido de reintento** (Decisión 1): aceptado explícitamente para el volumen de este MVP, mitigado por la ausencia de techo de coste y por quedar siempre visible en los datos reales de `llm_cost_usd`.
  - **Umbrales de producto, no arquitectura, marcados aparte para revisión del fundador** (mismo criterio que la lección del ciclo 0006-0010): `temperature=0.0` en la llamada a DeepSeek, `_MAX_ATTEMPTS=2`/`_RETRY_BACKOFF_SECONDS=2.0` del adapter, y la ausencia de techo de coste (ya decidida explícitamente, no una omisión).
  - **La cita normativa (`norm_title`/`norm_url`/`article`/`in_force_since`) la produce el LLM a partir únicamente del texto de entrada, sin ninguna URL ni fecha de referencia provista por quien invoca el comando** — riesgo real de alucinación en la URL/fecha exacta, mayor que el ya aceptado para las tres reglas escritas a mano (ADR 0017/0018, donde el arquitecto elegía la cita). La validación de `pydantic` solo filtra que la URL tenga forma de URL, nunca que sea la URL real — la salvaguarda real es la revisión humana obligatoria antes de `approve`, exactamente el punto que esta historia existe para demostrar.
- **Coste de salida de proveedor — DeepSeek:** bajo. Todo el conocimiento específico del proveedor (forma del prompt, endpoint, autenticación, parseo de la respuesta, precio por token) vive exclusivamente en `adapters/deepseek/`. Cambiar de proveedor (otra API en la nube, o un modelo local) significa escribir un nuevo paquete `adapters/<proveedor>/` que implemente `RuleAuthoringPort` devolviendo el mismo `RuleProposalDraft`, y cambiar una línea de instanciación en `cli/main.py` — cero cambios en `domain/`, `ports/`, `application/`. El coste real no absorbido por el hexágono es la re-validación cualitativa de los prompts contra el nuevo proveedor (cada proveedor responde distinto a la misma instrucción) — inherente a cualquier cambio de LLM, no una fuga de la frontera arquitectónica.
- **Coste de salida de proveedor — PostGIS (tabla `rule`):** sin cambios respecto al ya documentado en ADR 0004 — la tabla nueva vive en el mismo directorio ya contenido (`adapters/postgis/`), con la misma migración SQL plano y el mismo driver `psycopg`; no añade ninguna superficie nueva de acoplamiento más allá de la ya aceptada para `parcel`/`building`.
