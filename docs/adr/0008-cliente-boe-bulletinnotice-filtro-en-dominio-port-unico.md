# ADR 0008 — Cliente BOE: entidad `BulletinNotice`, filtro por texto como función de dominio, port único de un solo día, sin PDF ni caché

- Estado: aceptada
- Fecha: 2026-10-15

## Contexto

La historia 0008 (ingesta diaria de BOE con filtro por texto configurable) deja seis preguntas abiertas para el arquitecto. Antes de resolverlas, y siguiendo la lección ya registrada tras la historia 0001 ("nunca confiar en autodescripción ni en una verificación superficial anterior — solo una petición real, grabada como fixture, cuenta como verificación"), se volvió a verificar contra la red real el esquema exacto del sumario de BOE, tal como exige el primer bloque de la historia. El detalle completo queda en `src/parcel_intel/sources/REGISTRY.md` (sección BOE, reescrita en esta misma pasada); aquí solo los hallazgos que condicionan el diseño:

1. **El JSON de BOE viene de una conversión XML→JSON que colapsa cualquier elemento repetible a un `dict` suelto (no una lista de un elemento) cuando aparece una sola vez ese día**, en al menos tres niveles de anidamiento (`departamento`, `epigrafe`, `item`), y además `epigrafe` puede estar completamente ausente cuando las disposiciones cuelgan directamente de `departamento`. El día de verificación real (`20261015`) ejercita las tres variantes a la vez: de 164 disposiciones reales, 84 cuelgan directamente de `departamento` sin `epigrafe` intermedio. Un parsing que asuma siempre `list` pierde más de la mitad de las disposiciones reales **sin ningún error visible** — no es un caso de borde teórico, es el caso típico de un día cualquiera.
2. **Falta una cabecera `Accept: application/json` para obtener JSON en absoluto** — sin ella, incluso un día con sumario real devuelve `400` con cuerpo XML. No está documentado en ningún `GetCapabilities` ni autodescripción.
3. **Los errores siempre vienen en XML, nunca en JSON**, con el mismo `Accept: application/json` puesto: un día sin sumario (fin de semana, `20261011`, verificado real) y una fecha futura sin sumario todavía (`20271231`, verificado real) devuelven ambos `404` con idéntico cuerpo XML (`"La información solicitada no existe"`) — un solo tipo de error basta para los dos casos, el servicio no los distingue. Una fecha de formato de calendario inválido (`20261332`, verificado real) devuelve `400` con XML distinto (`"El parámetro fecha no cumple el formato"`), confirmando que el servidor también valida — pero el AC de la historia exige que el cliente nunca llegue a enviar esa petición.
4. **Filtro real sobre el sumario del `20261015`:** "colmenar" → 0 coincidencias, "villaconejos" → 0 coincidencias, "madrid" → 14 coincidencias. Documentado explícitamente, no forzado, cumpliendo el AC correspondiente.

`domain/provenance.py` (ADR 0002) ya es el value object compartido de procedencia. `ports/errors.py` ya tiene el patrón de error de validación-antes-de-red (`InvalidCadastralReferenceError`, `InvalidHistoricalVintageError`). El ADR 0006 fijó el precedente de mover a `domain/` cualquier operación que sea aritmética/lógica pura sin conocimiento de proveedor (`bbox_with_margin`); el ADR 0007 lo repitió con `compute_change_mask`, exigiendo además pasar los dos resultados ya obtenidos en vez de resolver fechas internamente, para no depender de red en una operación que es pura. Esta historia entrega solo el cliente aislado, sin conectar a ningún caso de uso (mismo patrón que 0002→0006→0007).

## Decisión

**1. Entidad `BulletinNotice`, mínima y propia — no se adelanta `bulletin_entry`.** En `domain/bulletin.py`:

```python
@dataclass(frozen=True)
class BulletinNotice:
    identifier: str          # p. ej. "BOE-A-2026-21445"
    title: str
    section_code: str        # p. ej. "1", "5A" — tal cual viene del JSON real
    section_name: str        # p. ej. "I. Disposiciones generales"
    pdf_url: str
    provenance: Provenance
```

Mismo criterio que `Orthophoto` (ADR 0006) y `NdviGrid`/`ChangeMask` (ADR 0007): `bulletin_entry` de `docs/vision.md` incluye geolocalización, entidades extraídas y confianza de resolución que esta historia no calcula ni puede calcular con evidencia real todavía — adelantar esos campos sería diseño especulativo, exactamente lo que el ADR 0004 ya rechazó una vez en este proyecto. `section_code`/`section_name` sí entran porque el AC los exige explícitamente ("cómo se agrupan las disposiciones por sección") y porque, igual que `vintage` en `Orthophoto`, es información que se perdería si no viajara con la entidad una vez que esta se desprende de la llamada que la produjo. No se incluye el departamento (`MINISTERIO DE...`): el AC no lo exige y añadirlo sin un consumidor que lo necesite repetiría el mismo error que el ADR 0004 ya corrigió.

**2. Un solo port, con un solo método — la captura del sumario completo del día, no el filtro.** En `ports/bulletin.py`:

```python
class OfficialBulletinPort(Protocol):
    def get_daily_bulletin(self, day: str) -> list[BulletinNotice]:
        """Sumario completo de un único día (formato AAAAMMDD), sin filtrar.
        Un día por llamada; iterar varios días es responsabilidad de quien llama."""
        ...
```

Ningún nombre menciona "BOE" (cumple el AC explícito). **El filtro por texto NO es un método del port**: es una función pura de dominio, en `domain/bulletin.py`:

```python
def filter_by_title(notices: list[BulletinNotice], search_text: str) -> list[BulletinNotice]: ...
```

Razón, por el mismo criterio que ya fijaron los ADR 0006 (`bbox_with_margin`) y 0007 (`compute_change_mask`): comparar un texto de búsqueda contra un título ya obtenido es una operación sin E/S y sin ningún conocimiento de BOE — exactamente lo que define "función de dominio" en este proyecto, no "capacidad de un adapter". Separar fetch de filtro tiene además una consecuencia práctica directa sobre la pregunta 5 de la historia (caché): si en el futuro un caso de uso necesita comprobar el mismo sumario de un día contra dos municipios distintos (Colmenar de Oreja y Villaconejos, el propio caso previsto por `docs/vision.md`), basta llamar `get_daily_bulletin` **una sola vez** y `filter_by_title` dos veces sobre el resultado ya en memoria — sin ninguna segunda petición de red y sin necesitar ninguna caché para resolver ese patrón de acceso. La caché solo tendría sentido para evitar repetir la petición de red *entre ejecuciones distintas* del proceso (p. ej. reintentos de un cron), que es precisamente el mismo tipo de consumidor-repetido-todavía-inexistente que llevó a diferir la caché en PNOA y Sentinel-2.

**3. Normalización del filtro: `casefold()` + eliminación de marcas diacríticas vía `unicodedata.normalize("NFKD", ...)`, substring simple — sin tokenización por palabras.** Implementación (stdlib puro, en `domain/bulletin.py`):

```python
def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))
```

y `filter_by_title` aplica `_normalize(search_text) in _normalize(notice.title)`. Se rechaza explícitamente cualquier tokenización por palabras: los términos de búsqueda previstos (nombres de municipio como "Colmenar de Oreja", "Villaconejos") son cadenas largas y poco ambiguas — el riesgo de que coincidan como substring dentro de una palabra no relacionada es bajo y no tiene evidencia real que lo respalde todavía. Construir tokenización ahora sería sobre-diseñar un mecanismo complejo para un problema mucho más simple que el resuelto por Sentinel-2 (sin raster, sin reproyección, aquí ni siquiera hay E/S) — exactamente la advertencia explícita de la propia historia. Si en el futuro aparece un falso positivo real, se resuelve entonces, con evidencia, no por adelantado.

**4. Sin PDF del cuerpo — filtrado solo sobre el título, con el riesgo de falso negativo documentado y sin resolver aquí.** Confirma lo que la propia historia ya deja como "Fuera de alcance": introducir parsing de PDF (dependencia nueva, nunca usada en el proyecto) solo para mitigar un riesgo todavía sin evidencia real de materializarse sería el mismo error que el ADR 0007 evitó al no traer `rasterio` sin verificar antes contra la red real si hacía falta. La condición para abrir una historia de seguimiento con parsing de PDF (y su propio ADR de dependencia nueva, mismo peso de decisión que tuvo `tifffile`/`pyproj`) es evidencia real y concreta de que el título no basta — no una posibilidad teórica.

**5. Errores nuevos en `ports/errors.py`, mismo patrón que `InvalidCadastralReferenceError`/`InvalidHistoricalVintageError`:**

```python
class InvalidBulletinDayError(Exception):
    """El día pedido no tiene formato AAAAMMDD válido (longitud, no numérico,
    o fecha de calendario inexistente). Se lanza antes de cualquier petición de red."""
    def __init__(self, day: str) -> None: ...

class BulletinNotPublishedError(Exception):
    """BOE no tiene sumario publicado para el día pedido (fin de semana, festivo,
    o fecha futura todavía sin publicar) — confirmado con HTTP 404 real, distinto
    del caso 'sumario con cero coincidencias de filtro'."""
    def __init__(self, day: str) -> None: ...
```

Un solo tipo de error para "fin de semana/festivo" y "fecha futura": el hallazgo 3 de este ADR confirma que BOE tampoco los distingue (mismo código `404`, mismo mensaje) — inventar dos tipos de excepción para una distinción que ni siquiera el proveedor hace sería, otra vez, diseño especulativo.

**6. Seam de red nuevo y propio de BOE, no reutiliza `HttpGetter` de PNOA/Catastro.** En `adapters/boe/client.py`:

```python
class DailySummaryGetter(Protocol):
    def __call__(self, day: str) -> tuple[int, bytes]: ...

def default_daily_summary_getter(day: str) -> tuple[int, bytes]:
    response = requests.get(
        f"https://boe.es/datosabiertos/api/boe/sumario/{day}",
        headers={"Accept": "application/json"},
        timeout=30,
    )
    return response.status_code, response.content
```

Mismo criterio que llevó al ADR 0007 a definir `JsonPoster`/`RangedHttpGetter` propios en vez de forzar el `HttpGetter` de PNOA (`url, params -> bytes`, pensado para GET con querystring y que asume éxito vía `raise_for_status()`): la petición real de BOE necesita (a) una cabecera fija que ningún otro adapter necesita y (b) el código de estado HTTP como señal de dominio explícita (`404` → "sin sumario publicado", no un error de transporte a dejar reventar) — algo que `HttpGetter` no expone porque su contrato ya asume "falla si no hay 2xx". `adapters/boe/adapter.py` decide con el status: `200` → `json.loads` y parsing; `404` → `BulletinNotPublishedError`; cualquier otro código queda fuera del alcance explícito de esta historia (no hay AC que lo pida) y se señala como riesgo residual más abajo.

**7. `adapters/boe/parsing.py` debe recorrer explícitamente las tres variantes dict-o-lista encontradas (hallazgo 1), con un helper único reutilizado en los tres niveles:**

```python
def _as_list(value: object) -> list[dict[str, object]]: ...  # [] si None, [value] si dict, value si ya es list
```

y un `TypedDict` para el ítem hoja (`RawItem`, con `control` como `NotRequired[str]` dado que está presente en 80 de 164 ítems reales y ausente en 84 — no es un campo fiable como requerido), siguiendo la lección ya registrada tras la historia 0001 de no usar `dict[str, object]` en el borde adapter↔dominio. El recorrido debe cubrir explícitamente el caso "ítem directo bajo `departamento`, sin `epigrafe`" (84 de 164 disposiciones reales el día de verificación) — un test que solo cubra `epigrafe[].item` y no `departamento.item` directo pierde más de la mitad del sumario en silencio, exactamente el tipo de caso que la lección de la historia 0002 pide cubrir explícitamente ("el caso no trivial, no solo lista vacía o un único elemento").

**8. Caché: diferida explícitamente, mismo criterio que PNOA (ADR 0006) y Sentinel-2 (ADR 0007), sin adelantarla por el patrón de acceso "diario".** La pregunta abierta de la historia planteaba si el patrón de acceso diario previsible debía adelantar esta decisión, a diferencia de PNOA/Sentinel-2 donde no había ningún consumidor repetido conocido. Se decide que no, por dos razones: (a) el punto 2 de esta decisión (separar fetch de filtro) ya resuelve sin caché el único patrón de acceso repetido conocido hoy — múltiples municipios sobre el mismo día, dentro de una misma ejecución; (b) seguir sin consumidor real que repita la misma petición *entre* ejecuciones del proceso, igual que PNOA/Sentinel-2. Se deja escrito, igual que en el ADR 0006, que el gatillo para revisar esto es la primera historia que conecte este cliente a un caso de uso con una revisita real entre ejecuciones (p. ej. un worker/cron diario con reintentos, o un backfill de varios días que repita alguno).

## Alternativas consideradas

- **Adelantar `bulletin_entry` de `docs/vision.md` con sus campos de geolocalización/confianza vacíos o `None`**: rechazada. Repite exactamente el error que el ADR 0006/0007 ya evitaron con `Orthophoto`/`NdviGrid` — diseñar para un requisito (geolocalización) que esta historia no resuelve ni puede verificar todavía.
- **Filtro por texto como método del port** (`get_daily_bulletin_filtered(day, search_text) -> list[BulletinNotice]`, sin exponer el sumario completo sin filtrar): rechazada. Acopla la operación de filtrado (pura, sin E/S) a la capacidad de red, obligando a una segunda petición de red por cada municipio distinto consultado sobre el mismo día — justo el problema que resolver con `filter_by_title` como función de dominio evita de raíz, sin necesitar caché para ello.
- **Dos ports separados** ("obtener sumario" / "filtrar"): rechazada. El filtrado no necesita ningún port porque no tiene E/S ni conocimiento de proveedor — ni siquiera amerita una interfaz, igual que `compute_change_mask` del ADR 0007 no la tiene.
- **Tokenización por palabras en el filtro**: rechazada por falta de evidencia real del riesgo (términos de búsqueda previstos son nombres de municipio, largos y poco ambiguos) y por el riesgo explícito de sobre-diseño que la propia historia señala.
- **Parsing de PDF del cuerpo cuando el título no basta**: rechazada para esta historia. Introduciría una dependencia nueva de peso (parsing de PDF) sin evidencia real de que haga falta — mismo criterio que llevó al ADR 0007 a verificar primero contra la red real antes de traer una librería pesada.
- **Reutilizar `HttpGetter` de PNOA/Catastro para el seam de BOE**: rechazada. No expone cabeceras personalizadas ni el código de estado HTTP como señal distinguible de "sin sumario" vs. error de transporte — forzar su contrato obligaría a interpretar una excepción genérica de `requests.HTTPError` para distinguir `404` de cualquier otro fallo, perdiendo la señal de dominio explícita que sí tiene sentido modelar aquí.
- **Dos tipos de error distintos para "fin de semana/festivo" y "fecha futura sin publicar"**: rechazada. El propio BOE no los distingue (mismo código, mismo mensaje, confirmado real) — inventar la distinción en el cliente sería diseño especulativo sin ninguna señal del proveedor que lo sostenga.
- **Adelantar la caché del sumario por el patrón de acceso "diario" previsible**: rechazada por ahora. Separar fetch de filtro ya resuelve el único patrón de acceso repetido conocido (varios municipios, mismo día, misma ejecución) sin caché; seguir sin consumidor real que repita la petición entre ejecuciones, igual que PNOA/Sentinel-2.

## Consecuencias

- Nuevo `domain/bulletin.py` (`BulletinNotice`, `filter_by_title`, `_normalize` privada). Stdlib puro (`dataclasses`, `unicodedata`), sin imports de otras capas — cumple el contrato de `import-linter` sin cambios al contrato.
- Nuevo `ports/bulletin.py` (`OfficialBulletinPort`, un método). `ports/errors.py` gana `InvalidBulletinDayError` y `BulletinNotPublishedError`.
- Nuevo `adapters/boe/` (`client.py` con el seam `DailySummaryGetter`/`default_daily_summary_getter`, `parsing.py` con `RawItem`/`_as_list`/el recorrido de las tres variantes dict-o-lista, `adapter.py` con `BoeAdapter` implementando `OfficialBulletinPort` y la validación de formato de día antes de red).
- `src/parcel_intel/sources/REGISTRY.md` queda actualizado con el esquema exacto confirmado y los tres casos de estado HTTP verificados reales (sumario real, sin sumario, formato inválido); se añaden dos fixtures nuevas en `tests/fixtures/boe/` (`sumario_sin_publicar_20261011.xml`, `fecha_formato_invalido_20261332.xml`) junto a la ya existente `sumario_hoy.json`, cerrando el AC de "verificado con al menos una fixture real de un día sin sumario".
- Riesgo residual señalado explícitamente para no bloquear esta historia pero no perderse: ningún código de estado HTTP distinto de `200`/`404` tiene manejo explícito en el adapter (p. ej. `500` de un fallo transitorio del servicio) — no hay AC que lo exija y no hay evidencia real todavía de que ocurra; se deja como comportamiento no definido hasta que aparezca evidencia real, mismo criterio que otros riesgos menores ya señalados en los ADR 0006/0007 sin bloquear el cierre de esas historias.
- Riesgo residual compartido con el ADR 0006 (no corregido aquí, fuera de alcance): si en el futuro `Provenance.url` necesitara reflejar parámetros con caracteres especiales, seguiría sin pasar por `urlencode` en ningún adapter del proyecto — aquí no aplica porque la URL del sumario no lleva query params, solo el día en el path.
- **Coste de salida del proveedor (BOE, Agencia Estatal Boletín Oficial del Estado):** bajo. Es una API pública sin autenticación ni facturación, sin lock-in contractual. Todo el conocimiento específico de BOE (URL, cabecera `Accept` obligatoria, los tres códigos de estado reales y su significado, el recorrido dict-o-lista del JSON) vive exclusivamente en `adapters/boe/`; `domain/`, `ports/`, `application/` y `cli/`/`api/` no saben que el proveedor es BOE — el port y la entidad están nombrados por capacidad (`OfficialBulletinPort`/`BulletinNotice`), no por proveedor, dejando abierta la puerta a que un futuro adapter de otro boletín (BOCM, historia 0009, u otro autonómico en fase 2) implemente el mismo port si su capacidad resulta ser la misma — decisión que no se toma aquí por adelantado, se revisita cuando 0009 tenga su propio diseño verificado contra la red real de BOCM. El principal coste de sustituir BOE no es contractual sino de verificación: volver a confirmar esquema/cabeceras/códigos de estado contra la red real y regrabar fixtures, igual que ya ha costado dos veces en este proyecto (Catastro en la historia 0001→0002, y esta misma historia).
