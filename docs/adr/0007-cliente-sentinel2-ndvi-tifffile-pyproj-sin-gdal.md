# ADR 0007 — Cliente Sentinel-2: lectura de COG sin GDAL (`tifffile`+`pyproj`+`numpy`), entidad `NdviGrid`, un solo port, máscara de cambios como función pura de dominio

- Estado: aceptada
- Fecha: 2026-10-15

## Contexto

La historia 0007 (cliente de Sentinel-2: serie de NDVI y máscara de cambios) deja nueve preguntas abiertas para el arquitecto, con una advertencia explícita del fundador: el equipo no tiene margen para introducir `rasterio`/GDAL si eso compromete la instalación fiable con `uv` en el entorno de desarrollo o en el servidor casero (Docker Compose), y hay que considerar en serio una alternativa más ligera que lea COG por rango de bytes sin GDAL — siendo realista sobre cuánto habría que implementar a mano.

Antes de decidir, se verificó contra datos reales (siguiendo la lección registrada tras la historia 0001 — "nunca confiar en autodescripción, solo una petición real cuenta como verificación"):

1. **Metadatos STAC ya traen CRS y transformación afín por asset.** La fixture real (`tests/fixtures/sentinel2/stac_search_colmenar.json`) incluye, en `properties.proj:epsg` (32630 para las tres escenas) y en cada asset de banda, `proj:transform` (p. ej. `[10, 0, 399960, 0, -10, 4500000]`) y `proj:shape` (`[10980, 10980]`). Esto significa que el adapter **no necesita ninguna librería que parsee GeoKeys de GeoTIFF** para saber el CRS nativo ni la georreferenciación de la escena — ya viene en el JSON de búsqueda, antes de leer ningún byte de banda. Esto reduce drásticamente lo que de verdad hace falta de una "librería raster": solo decodificar píxeles de tiles concretos, no resolver georreferenciación.
2. **Cabecera TIFF real del asset `B04.tif`** de la escena `S2B_30TVK_20261014_0_L2A`, leída con un `curl -r 0-65535` real (206 Partial Content, confirma rango de bytes funcional) y parseada a mano con stdlib (`struct`) solo para esta verificación: TIFF clásico (no BigTIFF), `Compression=8` (Adobe Deflate/zlib), `Predictor=2` (diferenciación horizontal), tiles de `1024×1024`, 121 tiles, `uint16`, una sola banda. **Deflate+predictor horizontal son exactamente los códecs que `tifffile` decodifica con stdlib (`zlib`) + `numpy`, sin necesitar `imagecodecs`** (su dependencia C opcional, reservada para JPEG2000/LERC/WebP/CCITT, que Sentinel-2 L2A en el bucket `sentinel-cogs` no usa).
3. **Cobertura real de wheels en PyPI** (consultada vía la API JSON de PyPI, no supuesta): `rasterio` 1.5.2 **no publica wheels `musllinux`** (solo `manylinux_2_28` glibc + macOS + Windows) — si el servidor casero usa alguna vez una imagen base Alpine, `rasterio` exigiría compilar GDAL desde cero, con todo lo que eso implica de superficie de build. `pyproj` 3.8.0, en cambio, **sí publica wheels `musllinux_1_2` para x86_64 y aarch64**, además de manylinux/macOS/Windows. `tifffile` es un wheel `py3-none-any` (puro Python, cero riesgo binario). `numpy` tiene cobertura de wheels prácticamente universal, incluida `musllinux`.
4. Hoy `infra/docker-compose.yml` solo contiene el contenedor de PostGIS; no existe todavía ningún `Dockerfile` para la app Python (corre con `uv run` directamente). El riesgo de GDAL en Docker es real pero **futuro, no bloqueante hoy** — aun así, la decisión de librería debe tomarse ahora pensando en ese futuro, no solo en la comodidad de desarrollo actual.

`domain/geometry.py` ya aporta `bbox_with_margin`/`BBox` (ADR 0006), reutilizable sin cambios. `ports/errors.py` ya tiene el patrón de error de validación-antes-de-red. El ADR 0006 fijó el precedente de "un port con dos métodos cuando no hay asimetría de autoridad" y "no adelantar `Observation`". Las lecciones registradas exigen: `TypedDict` en los bordes de parsing (no `dict[str, object]`), sospecha explícita sobre cualquier lógica numérica/geométrica reimplementada a mano, y verificar contra la red real antes de diseñar.

## Decisión

**1. Librería de lectura raster: `tifffile` + `numpy`, no `rasterio`/GDAL.** `tifffile` decodifica directamente los códecs reales confirmados en el COG (Deflate + predictor horizontal) sin `imagecodecs`. El adapter nunca reimplementa el parseo de IFD/tiles a mano (lo que se hizo en esta validación fue solo una comprobación puntual del arquitecto, no código de producción): se construye un objeto file-like mínimo sobre el seam `RangedHttpGetter` (punto 5) y se le pasa a `tifffile.TiffFile(...)`, que se encarga de IFDs, `dataoffsets`/`databytecounts` por tile y la decodificación de cada tile vía su API pública `TiffPage.decode(data, index)`. Ninguna reproyección ni resolución de CRS depende de esta librería — eso lo cubre el punto 2 con los metadatos que ya trae STAC. Se rechaza `rasterio` explícitamente por el hallazgo del punto 3 (sin wheels `musllinux`) y porque su E/S por rango de bytes (`/vsicurl/`) es opaca a nivel Python: no compone con el patrón de seam inyectable que ya usan Catastro y PNOA, obligando a un mecanismo de test distinto (servidor HTTP local o contadores internos de GDAL) solo para este adapter.

**2. Reproyección: `pyproj.Transformer`, usado solo para transformar coordenadas puntuales, no para "warp" de rejilla vía GDAL.** El flujo es: (a) `bbox_with_margin(geometry, margin_m)` da el bbox en el SRID de la parcela (EPSG:25830); (b) se define la rejilla de salida en ese mismo SRID, a resolución nativa de Sentinel-2 (10 m/celda), alineada al bbox; (c) para cada celda de la rejilla de salida, `pyproj.Transformer.from_crs(geometry.srid, scene_epsg, always_xy=True)` transforma su centro al CRS nativo de la escena; (d) la transformación afín de la escena (ya en `proj:transform` del asset STAC, sin parsear GeoKeys) se invierte con aritmética simple (`col = (x - c) / a`, `row = (y - f) / e`, sin términos de rotación en los datos reales verificados) para obtener la celda fuente más cercana — vecino más próximo, no bilineal: a 10 m nativos entre husos UTM adyacentes la distorsión geométrica sobre una ventana de parcela es mínima, y el AC solo exige una tolerancia documentada, no un remuestreo de máxima fidelidad. El adapter lee únicamente los tiles fuente que cubren el bbox transformado al CRS nativo (no la escena completa), calcula NDVI en esa ventana reducida y después remuestrea a la rejilla de salida en EPSG:25830.

**3. Entidades de dominio nuevas, en `domain/ndvi.py`, sin converger con `observation`:**

```python
from parcel_intel.domain.geometry import BBox
from parcel_intel.domain.provenance import Provenance

Grid = tuple[tuple[float, ...], ...]       # row-major, valores NDVI en [-1, 1]
ChangeGrid = tuple[tuple[bool, ...], ...]  # misma forma que los Grid comparados

class MismatchedNdviGridError(Exception):
    """Dos NdviGrid no comparten bbox/srid/forma: no se puede calcular una máscara."""

@dataclass(frozen=True)
class NdviGrid:
    values: Grid
    bbox: BBox
    srid: int
    scene_date: date
    cloud_cover_percent: float
    provenance: Provenance

@dataclass(frozen=True)
class ChangeMask:
    changed: ChangeGrid
    bbox: BBox
    srid: int
    before: NdviGrid
    after: NdviGrid
    threshold: float

def compute_change_mask(before: NdviGrid, after: NdviGrid, threshold: float) -> ChangeMask: ...
```

Nombres deliberadamente distintos de "Observation": igual que el ADR 0006 evitó adelantar esa entidad para `Orthophoto`, aquí se repite el criterio — no hay todavía un segundo consumidor real que confirme la forma compartida que describe `docs/vision.md` para `observation` (imagen/cambio detectado, confianza, geometría), y `NdviGrid`/`ChangeMask` no tienen "confianza" ni "tipo de cambio" porque esta historia no los calcula (están fuera de alcance explícitamente). `values`/`changed` son tuplas anidadas de `float`/`bool`, **no arrays de `numpy`**: el dominio solo puede importar stdlib, y una celda de `numpy.ndarray` filtrándose a `domain/` rompería esa regla igual que lo haría `pydantic` o `requests`. La conversión numpy↔tupla ocurre en el borde del adapter, igual que `Ring` ya es tupla de tuplas y no un array de `shapely`.

**4. Un solo port, con un solo método — no dos, y la máscara de cambios no es un método de port.**

```python
# ports/ndvi.py
class NdviSeriesPort(Protocol):
    def get_ndvi_series(
        self,
        geometry: Geometry,
        margin_m: float,
        start: date,
        end: date,
        max_cloud_cover_percent: float,
    ) -> list[NdviGrid]: ...
```

La capacidad de "máscara de cambios" se resuelve con `compute_change_mask` en `domain/ndvi.py` (punto 3), **no** con un segundo método de port ni un segundo port. Razón: dados dos `NdviGrid` que vienen de la misma geometría+margen (y por tanto de la misma rejilla de salida, por construcción del punto 2), comparar sus valores celda a celda contra un umbral es aritmética pura sin E/S ni conocimiento de ningún proveedor — exactamente el mismo criterio que llevó `bbox_with_margin` a `domain/` en el ADR 0006 en vez de duplicarlo en cada adapter. Esto resuelve a la vez la pregunta 9 de la historia ("¿fechas calendario o dos resultados NDVI ya obtenidos?"): **se exige pasar dos `NdviGrid` ya obtenidos** de una llamada previa a `get_ndvi_series`, nunca fechas calendario resueltas internamente por el adapter — evita que la máscara dependa de una segunda ronda de búsqueda/filtrado STAC con su propia ambigüedad de "qué escena es la fecha X", y la deja 100% testeable sin fixtures de red.

`compute_change_mask` valida `before.bbox == after.bbox and before.srid == after.srid and shape(before.values) == shape(after.values)`, lanzando `MismatchedNdviGridError` si no — guarda explícita, mismo espíritu que `EmptyGeometryError` en `domain/geometry.py`.

**5. Filtro de nubosidad: parámetro `max_cloud_cover_percent` obligatorio, sin valor por defecto.** Confirma lo que ya exige el AC de la historia ("el umbral es un parámetro explícito... no un valor fijo oculto"); no se introduce la alternativa de "escena menos nublada de la ventana" — un umbral explícito compuesto con el filtrado estricto ya pedido (descartar antes de pedir banda) es más simple y suficiente para esta historia.

**6. Seams de red: dos seams nuevos en `adapters/sentinel2/client.py`, ninguno reutiliza el `HttpGetter` de PNOA.** La forma de la petición es distinta en ambos casos (POST con cuerpo JSON vs. GET con cabecera `Range`), así que extender `HttpGetter` (`url, params -> bytes`, pensado para GET con querystring) sería forzarlo a un contrato que no describe ninguna de las dos peticiones reales:

```python
class JsonPoster(Protocol):
    def __call__(self, url: str, json_body: dict[str, object]) -> dict[str, object]: ...

def default_json_poster(url: str, json_body: dict[str, object]) -> dict[str, object]: ...

class RangedHttpGetter(Protocol):
    def __call__(self, url: str, start: int, length: int) -> bytes: ...

def default_ranged_http_getter(url: str, start: int, length: int) -> bytes: ...
```

`RangedHttpGetter` es el seam clave para el AC de "verificar que se lee significativamente menos que el archivo completo": en los tests se sustituye por un doble que lee de un fichero de fixture local y **cuenta bytes/llamadas exactamente**, sin necesitar un servidor HTTP local ni interceptar el `vsicurl` opaco de GDAL — una ventaja directa de no haber elegido `rasterio`. `tifffile.TiffFile` recibe un objeto file-like minúsculo construido sobre este seam (cada `.read(n)` en la posición `.tell()` se traduce a una llamada de `RangedHttpGetter`); la historia ya deja explícito como fuera de alcance optimizar el número de peticiones (sin buffering de lecturas pequeñas), así que no hace falta resolverlo aquí.

**7. Caché: diferida, mismo criterio que el ADR 0006** (sin consumidor real todavía que repita la misma petición). Se deja escrito, igual que allí, que el gatillo para revisarlo debería ser más sensible en este adapter que en PNOA: aquí el propio AC de "serie temporal" ya implica invocar el cliente repetidamente sobre el mismo rango de fechas/geometría en ejecuciones sucesivas (p. ej. un futuro watcher de riego con revisita de ~5 días), un patrón de acceso repetido más probable y más cercano en el tiempo que el de PNOA.

**8. Margen por defecto: `DEFAULT_MARGIN_M = 20.0` metros, constante documentada en `adapters/sentinel2/`, no compartida con PNOA.** El doble del tamaño de píxel nativo (10 m) evita que el bbox, al convertirse a ventana discreta de píxeles, pueda rendondear a cero celdas extra de margen en algún borde según la alineación fraccionaria exacta de la geometría — un riesgo real a 10 m que no existe a la resolución submétrica de PNOA. `margin_m` sigue siendo parámetro obligatorio del port (igual que en `OrthophotoPort`); la constante es solo para quien instancia el adapter desde `cli/`/`api/`.

## Alternativas consideradas

- **`rasterio`/GDAL** (como sugiere `docs/vision.md`): rechazada. Sin wheels `musllinux` confirmado contra PyPI real; su E/S por rango (`vsicurl`) no compone con el patrón de seam inyectable del resto del proyecto, obligando a un mecanismo de test distinto solo para este adapter; y los metadatos STAC ya resuelven la parte (CRS/georreferenciación) que de verdad justificaría GDAL. `docs/vision.md` es el documento de negocio/visión inicial, no un ADR — se trata aquí igual que la lección ya registrada sobre resolver colisiones `vision.md`/arquitectura con un ADR antes de que el código aterrice, no después.
- **`odc-stac`/`rioxarray`**: rechazadas. Ambas dependen de `rasterio` por debajo (no evitan el problema, lo esconden) y añaden `xarray`/`dask` sin un caso de uso que los necesite — diseño especulativo para una escala que no existe.
- **`pystac-client` para la búsqueda STAC**: rechazada. La respuesta real tiene 4-5 campos útiles por item; escribir ~30 líneas de parsing a `TypedDict` (mismo patrón que Catastro/PNOA) es menos superficie que una librería de catálogo completa, y mantiene la búsqueda detrás de un seam inyectable simple en vez de una sesión HTTP gestionada por la librería.
- **Reimplementar el parseo de IFD/tiles de TIFF a mano, sin `tifffile`** (como se hizo puntualmente en esta validación solo para confirmar compresión/estructura): rechazada para código de producción. Es exactamente el tipo de lógica binaria de bajo nivel que la lección de la historia 0006 señala tratar con sospecha cuando se reimplementa a mano; `tifffile` es una librería madura, ampliamente usada (scikit-image, dask-image, OME), con API pública pensada para lectura remota por segmentos.
- **Dos ports separados (serie NDVI / máscara de cambios)**: rechazada. No hay asimetría de autoridad entre ambas capacidades (mismo criterio del ADR 0006); además la máscara ni siquiera necesita E/S, lo que hace innecesario cualquier port para ella.
- **Máscara de cambios resuelta internamente a partir de dos fechas calendario**: rechazada. Acoplaría la máscara a una segunda búsqueda/filtrado STAC con su propia ambigüedad ("¿qué escena es *la* fecha X si hay varias en la ventana?"), y la haría depender de red para una operación que es aritmética pura sobre resultados ya obtenidos.
- **`numpy` disponible también en `domain/`**: rechazada. El dominio es stdlib puro; `Grid`/`ChangeGrid` son tuplas anidadas, no arrays, exactamente como `Ring` ya es tupla de tuplas en vez de una geometría de `shapely`.
- **Margen por defecto igual al de PNOA (10 m)**: rechazada, mismo razonamiento que el propio ADR 0006 ya anticipó (resoluciones muy distintas no deberían compartir margen); a 10 m nativos, 10 m de margen es insuficiente para garantizar cobertura de una celda completa extra en todos los bordes.

## Consecuencias

- Nuevos ficheros: `domain/ndvi.py` (`NdviGrid`, `ChangeMask`, `Grid`, `ChangeGrid`, `MismatchedNdviGridError`, `compute_change_mask`), `ports/ndvi.py` (`NdviSeriesPort`), `ports/errors.py` gana un error nuevo para "sin escenas tras el filtro de nubosidad" (mismo patrón que `InvalidHistoricalVintageError`, con bbox/rango de fechas/umbral en el mensaje), `adapters/sentinel2/` (`client.py` con los dos seams nuevos, `parsing.py` con `TypedDict` de la respuesta STAC, `adapter.py` con `Sentinel2Adapter`).
- `pyproject.toml`: se añaden `tifffile`, `pyproj` y `numpy` a `[project.dependencies]`, siguiendo el mismo patrón ya usado por `requests`/`psycopg` (el repo no tiene todavía un grupo de dependencias segregado por capa en `pyproject.toml` — "solo en adapters" se cumple hoy por `import-linter`, no por `extras` de empaquetado; la historia 0007 da por hecho un grupo de "dependencias de adapters" que no existe como tal en el repo real, y este ADR resuelve esa discrepancia a favor del patrón ya existente en vez de inventar un mecanismo nuevo de empaquetado sin que lo pidiera ninguna historia anterior).
- `[[tool.importlinter.contracts]]` del contrato "El dominio no importa nada de terceros ni de otras capas" (`forbidden_modules` sobre `parcel_intel.domain`) se amplía con `"numpy"`, `"tifffile"` y `"pyproj"`, igual que ya incluye `requests`/`pydantic`/`psycopg` — cierra en tooling, no solo por convención, el riesgo de que una celda de cálculo numérico se filtre al dominio.
- Riesgo de implementación a vigilar activamente (no bloqueante para esta decisión, pero sí para cerrar la historia sin reabrirla): los valores de banda son `uint16` con `scale=0.0001`/`offset=-0.1` en `raster:bands` de cada asset STAC — el NDVI debe calcularse sobre reflectancia (`dn * scale + offset`), no sobre el entero crudo, y las celdas con `nodata=0` deben excluirse del resultado. Ningún AC de la historia lo menciona explícitamente, pero sin aplicarlo el criterio "NDVI dentro de `[-1, 1]`" puede pasar por casualidad en algunos valores y fallar en otros de forma difícil de depurar — se señala aquí para que la implementación no lo descubra tarde.
- Recomendación operativa para abrir la implementación (no criterio de aceptación nuevo, siguiendo el mismo espíritu que ya aplicó la historia 0001 y la lección de la historia 0003 sobre "ejecutar el ciclo completo antes de fiarse"): antes de construir el adapter completo, hacer un spike corto que lea un solo tile real vía `RangedHttpGetter` + `tifffile.TiffPage.decode` contra la red real y compruebe a ojo que los valores decodificados son sensatos (no solo que el tipo de retorno es correcto) — mismo patrón que ya evitó dos historias de descubrimiento tardío en este proyecto (Catastro, PNOA).
- Si en el futuro se introduce un `Dockerfile` para `api`/`cli` en producción, debe partir de una imagen base glibc (p. ej. `python:3.12-slim`, Debian), no Alpine — aunque esta decisión evita la dependencia que más lo necesitaba (GDAL), `pyproj` también deja de tener wheels si se fuerza una arquitectura no cubierta por PyPI; es más barato fijar esta restricción ahora, por escrito, que descubrirla construyendo la imagen.
- **Coste de salida del proveedor (Earth Search/Element84 + bucket público `sentinel-cogs`):** bajo. Sin autenticación ni facturación; todo el conocimiento específico (URL del catálogo STAC, nombre de colección, bucket S3) vive solo en `adapters/sentinel2/`. El port y las entidades de dominio no mencionan Sentinel, STAC, AWS ni Element84. Sustituir esta fuente por otro catálogo STAC de Sentinel-2 (p. ej. Copernicus Data Space directamente) reutilizaría intacto el diseño de `tifffile`+`pyproj` (ambos agnósticos del proveedor del catálogo) y solo reescribiría `client.py`/`adapter.py`; el principal coste, igual que con PNOA, es de verificación (reconfirmar endpoints y regrabar fixtures), no contractual. `Provenance.license` queda en `asumido`, pendiente de confirmación textual, igual que el resto de fuentes de este registro.
