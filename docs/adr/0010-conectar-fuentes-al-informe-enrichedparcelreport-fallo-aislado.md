# ADR 0010 — Conectar PNOA/Sentinel-2/BOE/BOCM al informe: `EnrichedParcelReport` nunca cacheado, aislamiento de fallos con `except Exception` explícito, día real sin orquestación, resumen NDVI de un punto en el tiempo

- Estado: aceptada
- Fecha: 2026-10-15

## Contexto

La historia 0010 conecta los cuatro adapters ya aislados y verificados en historias previas (`PnoaAdapter`/`OrthophotoPort`, ADR 0006; `Sentinel2Adapter`/`NdviSeriesPort`, ADR 0007; `BoeAdapter`/`BocmAdapter`, ambos `OfficialBulletinPort`, ADR 0008/0009) al informe HTML existente (`GenerateParcelReportUseCase`, `adapters/reports/html.py`, `api/main.py`). Deja siete preguntas abiertas para el arquitecto. Esta sesión las resuelve todas — el fundador está dormido, modo autónomo, sin preguntas bloqueantes pendientes.

Puntos de partida verificados en el código real antes de decidir (no asumidos):

- Los cuatro adapters HTTP ya fijan `timeout=30` en sus respectivas funciones por defecto (`adapters/pnoa/client.py`, `adapters/sentinel2/client.py` ×3, `adapters/boe/client.py`, `adapters/bocm/client.py`): el timeout por fuente que la historia preguntaba si hacía falta introducir **ya existe, homogéneo, desde que cada adapter se implementó**. No hace falta tocar nada para satisfacer esa parte del AC.
- `GenerateParcelReportUseCase.execute()` devuelve antes de tocar red si hay cache-hit en PostGIS (`ParcelRepositoryPort.get_report`). Cualquier diseño que extendiera `ParcelReport` (la entidad cacheada) con los campos nuevos heredaría ese cortocircuito: en cache-hit, las cuatro fuentes nuevas nunca se consultarían, incumpliendo la métrica de éxito de la historia ("ver, en una sola carga, evidencia... de las cuatro fuentes nuevas"). Esto descarta extender `ParcelReport` directamente, independientemente de cualquier otra consideración.
- `Parcel.municipality` (en `domain/parcel.py`) ya contiene el nombre exacto con el que `api/main.py` instanció `CatastroAdapter` (`adapters/catastro/adapter.py:66`, `municipality=self._municipio`) — es decir, `report.parcel.municipality == "COLMENAR DE OREJA"` para ese municipio, el mismo valor de `_MUNICIPIOS` en `api/main.py`. No hace falta ningún parámetro nuevo para el término de búsqueda de `filter_by_title`: ya viaja dentro del propio `ParcelReport` obtenido de Catastro.
- `Sentinel2Adapter.get_ndvi_series` ya ordena sus resultados por fecha ascendente (`candidates.sort(key=lambda s: s["scene_date"])`) y ya lanza `NoScenesAfterCloudFilterError` si ninguna escena pasa el filtro de nubosidad — ningún cambio de adapter necesario.
- `domain/ndvi.py` ya establece el patrón "aritmética pura sobre datos ya obtenidos vive en `domain/`, no en el adapter ni en el caso de uso" (`compute_change_mask`, ADR 0007); `domain/bulletin.py` establece el mismo patrón para `filter_by_title` (ADR 0008). Un resumen NDVI de un `NdviGrid` ya obtenido es exactamente ese tipo de operación.

## Decisión

**1. Día consultado para BOE/BOCM: siempre la fecha real de la petición HTTP (`date.today()`), nunca un parámetro de endpoint ni una fecha fija hardcodeada.** No hay orquestación periódica (0008/0009 lo dejaron fuera de alcance) ni la necesita este MVP: el fundador abre el informe y ve lo que haya publicado el boletín *hoy* para ese municipio. Si no hay sumario ese día (fin de semana, festivo, o — solo en BOCM — fuera de la ventana rodante de 20 boletines de `sumarios.rss`, ADR 0009), `BulletinNotPublishedError` se captura igual que cualquier otro fallo de fuente (decisión 3) y la sección se muestra como "no disponible" — **no** como "0 disposiciones", que es un resultado distinto y legítimo (ver decisión 4). No se añade parámetro `?dia=AAAAMMDD` al endpoint: ningún AC de la historia lo pide y sería superficie nueva sin un consumidor real que la necesite (mismo criterio de no diseñar para lo hipotético que ya fijaron los ADR 0004/0006). Para que esto sea determinista en tests sin red ni reloj real, el nuevo caso de uso (decisión 5) recibe la función de reloj por inyección (`today: Callable[[], date] = date.today`), mismo patrón de *seam* que ya usan todos los adapters HTTP de este proyecto para su propio `_today()` interno, extendido aquí por primera vez a `application/` porque aquí sí determina una rama de control (qué día se pide), no solo metadato de `Provenance`.

**2. Alcance de PNOA/Sentinel-2: solo ortofoto actual (no histórica); resumen NDVI de un único punto en el tiempo (no serie, no máscara de cambios).** `OrthophotoPort.get_current_orthophoto(geometry, margin_m)` con `ORTHOPHOTO_MARGIN_M = 10.0` (mismo valor que `PnoaAdapter.DEFAULT_MARGIN_M`, ADR 0006 — constante propia del caso de uso, duplicada deliberadamente porque `application/` no puede importar el adapter concreto para reutilizar la suya; si el adapter concreto cambia de proveedor, este valor se revisita por separado, documentado así para que no se confunda con acoplamiento accidental). Para NDVI: se pide `NdviSeriesPort.get_ndvi_series(geometry, margin_m=NDVI_MARGIN_M, start=today-90d, end=today, max_cloud_cover_percent=40.0)` — tres constantes nuevas, documentadas como "número no mágico" en el caso de uso (mismo criterio que el AC de la historia 0006 exigió para el margen de PNOA):
   - `NDVI_MARGIN_M = 20.0`: mismo valor que `Sentinel2Adapter.DEFAULT_MARGIN_M` (ADR 0007), mismo criterio de duplicación deliberada que el punto anterior.
   - `NDVI_LOOKBACK_DAYS = 90`: suficientemente amplio para cubrir varias revisitas de Sentinel-2 (~5 días) incluso en temporada nubosa, sin ser tan amplio que el "resumen de un punto en el tiempo" deje de representar el estado reciente del terreno.
   - `NDVI_MAX_CLOUD_COVER_PERCENT = 40.0`: umbral permisivo a propósito — el objetivo es tener *alguna* evidencia visible la mayoría de los días del año, no la escena de máxima calidad; un umbral estricto (p. ej. 10%) dejaría la sección vacía con demasiada frecuencia en el MVP, que no tiene reintento ni serie para compensarlo.
   De la lista devuelta (ya ordenada ascendente por fecha), se toma la **última** (más reciente que pasa el filtro) — no la de menor nubosidad: para un vistazo de verificación manual, "lo más actual posible, con calidad aceptable" es más útil que "lo más nítido, sea de cuando sea". Se calcula un resumen agregado — media del NDVI de la rejilla, ignorando celdas `nan` (nodata) — con una función nueva y pura en `domain/ndvi.py` (decisión 6), no en el adapter ni en el caso de uso. Ni histórico de PNOA ni serie/máscara de NDVI entran en el AC de esta historia (ya excluidos explícitamente en "Fuera de alcance"); esta decisión solo fija los valores por defecto necesarios para "un punto en el tiempo" con evidencia real.

**3. Aislamiento de fallos: `except Exception` explícito y documentado por cada una de las cuatro llamadas, dentro del nuevo caso de uso — no un tipo `SourceResult[T]` genérico ni una lista de excepciones conocidas.** Se rechaza enumerar tipos conocidos (`NoScenesAfterCloudFilterError`, `BulletinNotPublishedError`, más cualquier excepción de red de `requests` que `adapters/pnoa`, `adapters/sentinel2`, `adapters/boe`, `adapters/bocm` puedan dejar escapar sin envolver) porque **`application/` no puede importar ningún módulo de adapter concreto** (regla de capas de `CLAUDE.md`) y las excepciones de red (`requests.exceptions.*`) solo existen ahí — no hay forma de nombrarlas desde `application/` sin romper la frontera hexagonal. La única alternativa compatible con el hexágono es un `except Exception` genérico alrededor de cada llamada a un port nuevo, documentado explícitamente con el motivo (no es descuido, es la consecuencia correcta de que `application/` no conoce qué puede fallar dentro de un adapter que no importa). El mensaje de la excepción se descarta siempre, nunca se adjunta a la entidad de dominio ni llega al HTML — satisface directamente el AC "sin exponer el mensaje técnico" sin necesitar ningún campo de "razón" en el dominio.

**4. Representación de "fuente no disponible": campo opcional (`None`) por fuente en una entidad nueva — no una unión explícita de éxito/error ni una excepción que se filtre hasta el render.** Nueva entidad en `domain/report.py`:

```python
@dataclass(frozen=True)
class EnrichedParcelReport:
    """Envuelve ParcelReport (cacheado, historia 0005) con evidencia de
    cuatro fuentes nunca cacheadas (historia 0010, ver ADR). Cada campo es
    None cuando la fuente correspondiente falló o no tuvo evidencia
    disponible ese día/rango -- nunca el mensaje técnico de la excepción,
    que application/ descarta antes de construir esta entidad. Una tupla
    vacía (no None) en boe_notices/bocm_notices es un resultado válido y
    distinto: la fuente respondió pero ninguna disposición mencionaba el
    municipio ese día (mismo matiz ya confirmado real en ADR 0008/0009 para
    BOE, "0 coincidencias" es un resultado, no un fallo)."""
    report: ParcelReport
    orthophoto: Orthophoto | None
    ndvi_summary: NdviSummary | None
    boe_notices: tuple[BulletinNotice, ...] | None
    bocm_notices: tuple[BulletinNotice, ...] | None
```

`None` significa "falló o no hay evidencia" (incluye `NoScenesAfterCloudFilterError`, `BulletinNotPublishedError`, y cualquier error de red); una tupla vacía en los dos campos de boletín significa "la fuente respondió, cero disposiciones mencionaban el municipio ese día" — una distinción de negocio real, no un detalle interno, que el render debe mostrar con textos distintos ("no disponible" vs. "sin disposiciones de \<municipio\> hoy"). No se necesita esta distinción para `orthophoto`/`ndvi_summary` porque ninguna de las dos tiene un "resultado vacío pero válido" equivalente — o hay una ortofoto/escena, o no la hay.

**5. `ParcelReport` no se toca.** Se compone un caso de uso nuevo que *envuelve* al existente, no se amplía `GenerateParcelReportUseCase`:

```python
class GenerateEnrichedParcelReportUseCase:
    def __init__(
        self,
        base_use_case: GenerateParcelReportUseCase,
        orthophoto_port: OrthophotoPort,
        ndvi_port: NdviSeriesPort,
        boe_port: OfficialBulletinPort,
        bocm_port: OfficialBulletinPort,
        today: Callable[[], date] = date.today,
    ) -> None: ...

    def execute(self, cadastral_reference: str) -> EnrichedParcelReport:
        report = self._base_use_case.execute(cadastral_reference)  # cacheado, sin cambios
        geometry = report.parcel.geometry
        orthophoto = self._safe(lambda: self._orthophoto_port.get_current_orthophoto(
            geometry, ORTHOPHOTO_MARGIN_M))
        ndvi_summary = self._safe(lambda: summarize_ndvi_grid(self._latest_ndvi_grid(geometry)))
        day = self._today().strftime("%Y%m%d")
        term = report.parcel.municipality
        boe_notices = self._safe_notices(lambda: self._boe_port.get_daily_bulletin(day), term)
        bocm_notices = self._safe_notices(lambda: self._bocm_port.get_daily_bulletin(day), term)
        return EnrichedParcelReport(report, orthophoto, ndvi_summary, boe_notices, bocm_notices)
```

(`_safe`/`_safe_notices` son helpers privados que aplican el `except Exception` de la decisión 3; `_safe_notices` aplica además `domain.bulletin.filter_by_title(notices, term)` y envuelve el resultado en `tuple(...)`, devolviendo `None` solo si la llamada de red falla, nunca si el filtro da cero resultados.) Esto mantiene `GenerateParcelReportUseCase` sin cambios (cero riesgo de regresión sobre su comportamiento ya probado) y hace explícito, en la propia firma del caso de uso nuevo, que la ampliación es una capa sobre la pieza cacheada, no una modificación de ella. `application/` sigue sin importar ningún adapter concreto: recibe los cinco colaboradores (el caso de uso base + cuatro ports) por inyección.

Las dos instancias de `OfficialBulletinPort` se inyectan como **dos parámetros nombrados** (`boe_port`, `bocm_port`), no como lista ni diccionario. Con solo dos fuentes reales hoy, una colección indexada por string sería indirección sin beneficio (mismo criterio de no diseñar para lo hipotético ya aplicado en los ADR 0004/0006/0007 de este proyecto); el disparador explícito para revisar esto es la llegada real de un tercer boletín (BORM/BOP, fase de entrada comercial de `docs/vision.md`) — ese día, cambiar la firma de este caso de uso (no de `OfficialBulletinPort`, que no cambia) es un coste conocido y aceptado, no una sorpresa.

**6. Nueva función y entidad puras en `domain/ndvi.py`: `NdviSummary`/`summarize_ndvi_grid`.** Mismo patrón que `compute_change_mask` (ADR 0007): aritmética sobre un `NdviGrid` ya obtenido, sin E/S, así que vive en `domain/`, no en el adapter ni en `application/`.

```python
@dataclass(frozen=True)
class NdviSummary:
    mean: float  # nan si todas las celdas de la rejilla eran nan (nodata)
    scene_date: date
    cloud_cover_percent: float
    provenance: Provenance

def summarize_ndvi_grid(grid: NdviGrid) -> NdviSummary:
    values = [v for row in grid.values for v in row if not math.isnan(v)]
    mean = sum(values) / len(values) if values else math.nan
    return NdviSummary(mean, grid.scene_date, grid.cloud_cover_percent, grid.provenance)
```

**7. Composition root (`api/main.py`): instancia los cuatro adapters nuevos por petición, igual que ya hace con `CatastroAdapter`.** `PnoaAdapter()`, `Sentinel2Adapter()`, `BoeAdapter()`, `BocmAdapter()` se construyen dentro de `get_parcel_report`, se inyectan en `GenerateEnrichedParcelReportUseCase` junto al `GenerateParcelReportUseCase` ya existente, y el resultado (`EnrichedParcelReport`) se pasa a `render_parcel_report_html` (su firma cambia de `ParcelReport` a `EnrichedParcelReport`; internamente accede a `report.report.parcel`/`report.report.buildings` para la parte ya existente). Ninguna de las cuatro clases concretas se instancia fuera de `api/main.py`, cumpliendo el ADR 0003 sin necesidad de un ADR nuevo sobre composition roots.

**8. Imagen de ortofoto embebida en base64, sin endpoint nuevo.** `render_parcel_report_html` codifica `orthophoto.image` (bytes JPEG, confirmado el formato en `adapters/pnoa/adapter.py`) con `base64.b64encode` (stdlib) y lo incrusta como `<img src="data:image/jpeg;base64,...">`. Coherente con el criterio ya escrito en el docstring de `adapters/reports/html.py` ("página autocontenida... sin plantillas de terceros"): un endpoint de imagen aparte introduciría una segunda petición HTTP y estado compartido entre dos rutas sin ningún beneficio para el MVP (no hay CDN, no hay caché de imagen, es una sola carga manual del fundador).

**9. Timeouts: ya satisfechos, sin cambios.** Los cuatro adapters HTTP ya fijan `timeout=30` en cada función de red por defecto. No se introduce ningún timeout agregado para el conjunto de las cuatro llamadas (ni para las N+1 de BOCM): el AC de la historia solo exige que un fallo o tardanza de una fuente no tumbe el informe entero, no que el informe cargue rápido — "Fuera de alcance" de la propia historia excluye explícitamente optimizar latencia. La decisión 3 (`except Exception`) ya cubre el caso de un timeout real disparando una excepción de `requests`.

## Alternativas consideradas

- **Extender `ParcelReport` con los cuatro campos nuevos**: rechazada. Rompería la métrica de éxito de la historia en el camino de cache-hit (`GenerateParcelReportUseCase.execute()` devuelve antes de tocar las cuatro fuentes nuevas si hay caché), y mezclaría en una sola entidad datos cacheados permanentemente con datos que la propia historia prohíbe cachear — cualquier futuro cambio de `ParcelRepositoryPort`/esquema SQL correría el riesgo real de arrastrar persistencia accidental de ortofoto/NDVI/boletines, justo lo que el AC de "cero tablas nuevas" pide evitar por diseño, no solo por disciplina.
- **`SourceResult[T]`/`Result` genérico (éxito/error tipado) en `domain/`**: rechazada por sobre-diseño para el tamaño real del problema — con cuatro fuentes y una sola distinción observable ("no disponible" vs. valor), un tipo genérico con `Generic[T]` añadiría una abstracción reutilizable sin un segundo caso de uso real que la necesite hoy (mismo criterio de los ADR 0004/0006 contra diseñar para lo hipotético). Si aparece una quinta fuente con una tercera distinción de estado (p. ej. "parcialmente disponible"), ese es el momento de revisitar esta decisión, no antes.
- **Enumerar los tipos de excepción conocidos (`NoScenesAfterCloudFilterError`, `BulletinNotPublishedError`, ...) en el `except` de `application/`**: rechazada. Exigiría o bien importar esos tipos desde `ports/errors.py` (posible, están en `ports/`, no en `adapters/`) y además capturar por separado cualquier excepción de red de `requests` que los adapters no envuelven hoy en un tipo de dominio — y los cuatro adapters, revisados, no envuelven errores de red en ningún tipo propio (`default_http_getter`, `default_json_poster`, etc. dejan propagar `requests.exceptions.*` o `response.raise_for_status()` sin capturar). Sin esa garantía del lado del adapter, cualquier lista de tipos conocidos en `application/` sería incompleta por construcción; `except Exception` es la única opción que de verdad aísla todos los fallos posibles sin inventar una promesa que los adapters no cumplen hoy.
- **Mostrar la serie NDVI completa o la máscara de cambios en vez de un resumen de un punto**: rechazada, ya excluida explícitamente en "Fuera de alcance" de la propia historia — exigiría decidir una segunda fecha, no solo un rango, y el AC solo pide "un resumen NDVI... con al menos el valor/estadístico agregado y la fecha de la escena usada".
- **Selector de ortofoto histórica además de la actual**: rechazada para esta historia por la misma razón — "Fuera de alcance" ya la excluye, y añadirla duplicaría el número de llamadas de red (actual + histórica) sin ningún AC que la pida.
- **Parámetro `?dia=AAAAMMDD` en el endpoint**: rechazada. Ningún AC lo pide; añadir un parámetro de query sin un consumidor real (nadie necesita ver el boletín de un día distinto al de hoy en el MVP) es superficie nueva especulativa, mismo criterio rechazado repetidamente en este proyecto.
- **Endpoint de imagen aparte (`GET /reports/.../orthophoto.jpg`) en vez de base64 embebido**: rechazada para esta historia. Introduce una segunda ruta HTTP, una segunda petición al cargar la página y la necesidad de recalcular o cachear la ortofoto entre ambas peticiones — ningún beneficio real para una carga manual única sin CDN ni caché de imagen.
- **Tomar la escena de menor nubosidad del rango en vez de la más reciente que pasa el filtro**: rechazada. Con un umbral de 40% ya permisivo, la diferencia de nubosidad entre candidatas suele ser secundaria frente a cuán reciente es la imagen para el propósito de verificación manual del fundador; ordenar por nubosidad en vez de por fecha también exigiría un segundo criterio de ordenación en el caso de uso en vez de confiar en el orden ya garantizado por el adapter (`candidates.sort(key=... scene_date)`).
- **Colección (lista o diccionario) de `OfficialBulletinPort` en vez de dos parámetros nombrados**: rechazada por ahora. Con exactamente dos fuentes reales, indexar por string o iterar una lista no aporta nada sobre dos parámetros con nombre y tipo explícitos; se revisita el día que aparezca una tercera fuente real de boletín (BORM/BOP), no antes.

## Consecuencias

- `domain/report.py` gana `EnrichedParcelReport` (importa `Orthophoto`, `NdviSummary`, `BulletinNotice` — todo `domain/`, sin romper el contrato de `import-linter`). `ParcelReport` no cambia.
- `domain/ndvi.py` gana `NdviSummary`/`summarize_ndvi_grid`, mismo patrón que `compute_change_mask` — stdlib puro (`math.isnan`), sin dependencia nueva.
- Nuevo módulo en `application/` (p. ej. `application/generate_enriched_report.py`) con `GenerateEnrichedParcelReportUseCase`, constantes documentadas (`ORTHOPHOTO_MARGIN_M`, `NDVI_MARGIN_M`, `NDVI_LOOKBACK_DAYS`, `NDVI_MAX_CLOUD_COVER_PERCENT`) y el seam `today: Callable[[], date]`. Importa solo `ports/` y `domain/` — ningún adapter concreto.
- `adapters/reports/html.py` cambia su firma de entrada (`ParcelReport` → `EnrichedParcelReport`), añade el render de ortofoto (base64 inline), resumen NDVI y listas de BOE/BOCM con sus tres estados posibles (valor, vacío, no disponible).
- `api/main.py` instancia los cuatro adapters nuevos por petición y los inyecta en el nuevo caso de uso, que envuelve al existente sin modificarlo.
- Riesgo residual señalado explícitamente: el `except Exception` genérico de la decisión 3, aunque es la única opción compatible con el hexágono, también silenciaría un error de programación real dentro de uno de los cuatro adapters (p. ej. un `AttributeError` por un cambio de forma de respuesta no capturado por ningún test) de la misma manera que silenciaría un fallo de red esperado — el AC de "un test por fuente que falla" mitiga esto parcialmente (fuerza a verificar que el aislamiento funciona) pero no distingue "fallo esperado de red" de "bug nuevo"; si en el futuro esto esconde un bug real durante demasiado tiempo, la señal para revisarlo es un log explícito de la excepción capturada (sin exponerla al HTML) en vez de descartarla en silencio — no se añade ese logging en esta historia porque no hay AC que lo pida, pero queda anotado aquí para no perder la idea.
- No se introduce ningún proveedor third-party nuevo en esta historia (los cuatro ya tenían su propio ADR de entrada: 0006/0007/0008/0009); el coste de salida de cada uno no cambia respecto a lo ya documentado en esos ADR. Lo que cambia es el coste de salida de la *composición*: hoy, desconectar cualquiera de las cuatro fuentes del informe (p. ej. si PNOA deja de estar disponible) es tan barato como dejar de instanciar su adapter en `api/main.py` y que el caso de uso reciba un port cuyo único método siempre lance — el resto del informe sigue funcionando sin cambios, exactamente la propiedad que esta historia existe para garantizar.
