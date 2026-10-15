# ADR 0006 — Cliente PNOA: entidad `Orthophoto`, port único con dos capacidades, bbox-con-margen en `domain/`, caché diferida

- Estado: aceptada
- Fecha: 2026-10-15

## Contexto

La historia 0006 (cliente de PNOA) deja cinco preguntas abiertas para el arquitecto: forma del resultado de dominio, uno o dos ports, dónde cachear las imágenes, valor por defecto del margen en metros, y forma del parámetro de año/vuelo histórico. A esto se añade un riesgo señalado explícitamente al revisar la historia: `adapters/catastro/adapter.py` ya calcula un bbox ad-hoc (`_bbox()`, centrado en un punto con semi-ancho fijo, para encuadrar una petición WFS), y esta historia necesita un cálculo distinto pero relacionado — bbox del rectángulo envolvente de una `Geometry` completa más un margen en las cuatro direcciones. El siguiente cliente ya en la cola (Sentinel-2, historia 0007) necesitará la misma operación ("bbox desde geometría con margen") y probablemente otra entidad de "observación sobre imagen" propia. Si esta historia resuelve "bbox + margen" como código propio de `adapters/pnoa/`, Sentinel-2 lo duplicaría una tercera vez.

`domain/geometry.py` fija `Geometry(rings: tuple[Ring, ...], srid: int)` sin ninguna función asociada todavía — es solo el dataclass. `domain/provenance.py` (ADR 0002) ya es el value object compartido de procedencia, incluido por composición en toda entidad que lo requiera. `ports/errors.py` ya tiene el patrón de error de validación-antes-de-red (`InvalidCadastralReferenceError`) que el AC de esta historia pide replicar para un año/vuelo histórico no confirmado. `CLAUDE.md` fija como regla general ya escrita "datos crudos cacheados e inmutables en `data/` (fuera de git)"; el ADR 0004 ya estableció el precedente de diferir una pieza de infraestructura (`ParcelRepositoryPort`/PostGIS) hasta que hubiera un caso de uso real que la necesitara, aunque en aquel caso el coste de entrada era levantar un contenedor nuevo — aquí escribir en `data/pnoa/` no tiene ese coste.

No hay todavía ningún caso de uso en `application/` que consuma ortofotos: esta historia entrega solo el cliente aislado, igual que 0002 entregó Catastro aislado antes de conectarlo al informe en 0004.

## Decisión

**1. Bbox-con-margen es una función pura de `domain/geometry.py`, no código del adapter.** Se añade:

```python
BBox = tuple[float, float, float, float]  # (minx, miny, maxx, maxy)

def bbox_with_margin(geometry: Geometry, margin_m: float) -> BBox: ...
```

Calcula el rectángulo envolvente de todos los puntos de todos los anillos de `geometry` y lo expande `margin_m` en las cuatro direcciones. Es aritmética sobre floats, stdlib puro, igual que el resto de `domain/`. `adapters/pnoa/` la usa para construir el parámetro `bbox` de `GetMap`; `adapters/catastro/adapter.py` **no se toca** (su `_bbox()` resuelve un problema distinto — bbox fijo alrededor de un centroide para encuadrar una query WFS, no el envolvente de una geometría con margen configurable) y queda fuera de alcance de esta historia. Cuando llegue Sentinel-2 (0007), su adapter reutiliza esta misma función de dominio en vez de reimplementarla.

**2. Nueva entidad de dominio `Orthophoto`**, en `domain/orthophoto.py`:

```python
Vintage = Literal["actual"] | HistoricalVintage
HistoricalVintage = int | Literal["AMS_1956-1957", "Interministerial_1973-1986", "Nacional_1981-1986"]

@dataclass(frozen=True)
class Orthophoto:
    image: bytes
    vintage: Vintage
    provenance: Provenance
```

No se adelanta ninguna forma de `Observation` (tipo de cambio, confianza): esos campos no aplican aquí y el AC de esta historia excluye explícitamente cualquier análisis sobre la imagen. `vintage` no es especulativo — es la única forma de distinguir, una vez que el `Orthophoto` circula desuncido de la llamada que lo produjo (p. ej. guardado en una lista para comparar visualmente años distintos, el caso de uso previsto por `docs/vision.md` para el módulo de datación), cuál de las dos capacidades lo generó; parsear la URL de `Provenance` para saberlo sería un antipatrón. Es el mismo criterio que llevó a que `Parcel`/`Building` incluyan su propia referencia catastral (ADR 0002): una entidad que se desprende de su contexto de llamada necesita poder describirse a sí misma.

**3. Un solo port, `OrthophotoPort` en `ports/orthophoto.py`, con dos métodos** (no dos ports):

```python
class OrthophotoPort(Protocol):
    def get_current_orthophoto(self, geometry: Geometry, margin_m: float) -> Orthophoto: ...
    def get_historical_orthophoto(
        self, geometry: Geometry, margin_m: float, vintage: HistoricalVintage
    ) -> Orthophoto: ...
```

Ningún nombre menciona PNOA ni IGN (cumple el AC explícito). La razón para no partir en dos ports es la misma que fijó el ADR 0005 para `ParcelRepositoryPort` (y la inversa de la razón que sí llevó a partir `ParcelGeometryPort`/`BuildingGeometryPort` en el ADR 0002): el ADR 0002 separó por una asimetría real de *autoridad* entre proveedores (un adapter de detección de imagen nunca tendría autoridad sobre parcela). Aquí no existe ninguna asimetría equivalente — "actual" e "histórico" son el mismo proveedor, la misma autoridad, el mismo consumidor futuro (el módulo de datación necesita ambos juntos para comparar), diferenciados solo por un parámetro. Partir en dos ports sería diseño especulativo sin un segundo consumidor real que lo justifique, exactamente lo que el ADR 0004 ya rechazó una vez en este proyecto.

**4. Parámetro de año/vuelo histórico: tipo unificado `HistoricalVintage = int | Literal[tres vuelos nombrados]`**, definido en `domain/orthophoto.py` (no en `ports/`, porque el `Vintage` de la entidad lo reutiliza y `ports/` solo puede importar `domain`). El tipo no puede restringir en tiempo de compilación el rango `2004`–`2024` del `int` ni qué literales son válidos más allá de los tres nombrados a la vez que acepta cualquier `int`: la validación completa contra la lista confirmada de `REGISTRY.md` ocurre en tiempo de ejecución, en `adapters/pnoa/`, antes de cualquier petición de red, lanzando `InvalidHistoricalVintageError` (nueva, en `ports/errors.py`, mismo patrón que `InvalidCadastralReferenceError`). Se prefiere un único parámetro de tipo unificado frente a dos parámetros opcionales (`year: int | None`, `flight: str | None`) porque dos opcionales permiten estados inválidos por construcción (ambos a la vez, ninguno de los dos) que el propio tipo del parámetro único excluye.

**5. Margen por defecto: `10.0` metros, como constante nombrada y documentada en `adapters/pnoa/`** (p. ej. `DEFAULT_MARGIN_M = 10.0`), no en `domain/geometry.py` ni compartida con Sentinel-2. La función de dominio `bbox_with_margin` no fija ningún valor por defecto — recibe `margin_m` como parámetro obligatorio; cada adapter decide su propia constante según la resolución y el caso de uso de su proveedor. Se elige `10.0 m` (frente a replicar el criterio, todavía no implementado, de Sentinel-2) porque la resolución submétrica de PNOA hace que ese margen ya cubra un borde de contexto visual útil (accesos, linderos) sin arrastrar una porción significativa de parcelas vecinas en parcelas urbanas pequeñas; es un valor de partida, no una medición exhaustiva, y cualquier caso de uso real (datación) puede pasar un `margin_m` distinto por parámetro sin tocar el adapter.

**6. Caché de las imágenes: diferida explícitamente, no implementada en esta historia.** El cliente no escribe en `data/pnoa/` todavía. Esto es una extensión deliberada del precedente del ADR 0004 (`ParcelRepositoryPort`/PostGIS diferido hasta que hubo un consumidor real), con una diferencia material que hay que dejar escrita porque, a diferencia de PostGIS, cachear en filesystem no tiene coste de entrada (no hay infraestructura nueva que levantar) y `CLAUDE.md` ya fija "datos crudos cacheados e inmutables en `data/`" como regla general, no como algo a decidir caso por caso. Se difiere aun así porque, igual que con PostGIS en 0004, **no hay ningún caso de uso real todavía** que vuelva a pedir la misma ortofoto más de una vez (el cliente se entrega aislado, sin conectar al informe); cachear sin un patrón de acceso repetido real que lo justifique sería adivinar la forma de la clave de caché (¿por geometría+margen+vintage? ¿por bbox exacto?) antes de tiempo. La condición explícita para revisitarlo: la primera historia que conecte este cliente a un caso de uso que pida la misma ortofoto más de una vez (el informe mostrando la imagen junto a la parcela, o el módulo de datación comparando varios años de la misma parcela en ejecuciones sucesivas) debe decidir la caché en ese momento, no asumir que sigue sin hacer falta.

## Alternativas consideradas

- **Reimplementar bbox-con-margen dentro de `adapters/pnoa/`** (como hace hoy Catastro con `_bbox()`): rechazada. Duplicaría la misma lógica una tercera vez en cuanto llegue Sentinel-2 (0007), que necesita exactamente la misma operación; moverla a `domain/geometry.py` ahora cuesta lo mismo que escribirla una vez en el adapter y evita la duplicación conocida de antemano.
- **`Orthophoto` como versión reducida de una futura `Observation`** (anticipando sus campos aunque algunos no se usen): rechazada. Repetiría el patrón de diseño especulativo ya rechazado en el ADR 0004 ("no diseñar para requisitos hipotéticos"); `Observation` no tiene forma decidida todavía y esta historia no la necesita.
- **Tupla `(bytes, Provenance)` sin entidad de dominio nueva**: rechazada. Rompe el patrón ya establecido por `Parcel`/`Building`/`ParcelReport` (toda entidad lleva su procedencia por composición, con nombre, no en una tupla posicional); además no tiene ningún campo para distinguir "actual" de "histórico" una vez que el valor se desprende de la llamada que lo produjo, forzando a los consumidores futuros a parsear `Provenance.url`.
- **Dos ports separados (`CurrentOrthophotoPort`/`HistoricalOrthophotoPort`)**: rechazada. No existe ninguna asimetría de autoridad entre "actual" e "histórico" (mismo proveedor, mismo consumidor futuro) que lo justifique, a diferencia del caso real que motivó la separación del ADR 0002.
- **Dos parámetros opcionales (`year: int | None`, `flight: str | None`) en vez de un tipo unificado**: rechazada. Permite combinaciones inválidas por construcción (los dos a la vez, ninguno) que un único parámetro con tipo unión no permite.
- **Cachear ya en `data/pnoa/` en esta historia**, cumpliendo la regla general de `CLAUDE.md` de inmediato: rechazada por ahora. Ningún caso de uso real pide la misma imagen dos veces todavía (el cliente no está conectado a nada); decidir la clave de caché sin un patrón de acceso real sería adivinar. Se deja explícito aquí, como pide la propia historia, para que no se confunda con una omisión.
- **Margen por defecto igual al de Sentinel-2** (aún no implementado, previsiblemente mayor por su resolución de 10 m/píxel): rechazada. PNOA tiene resolución submétrica; forzar el mismo margen que un proveedor de resolución muy distinta no tiene justificación técnica y acopla un valor de un adapter al de otro sin necesidad — `bbox_with_margin` ya deja a cada adapter decidir el suyo sin tocar `domain/`.

## Consecuencias

- Nuevo `domain/orthophoto.py` (entidad `Orthophoto`, tipos `Vintage`/`HistoricalVintage`) y función nueva `bbox_with_margin`/`BBox` en `domain/geometry.py`. Ninguno importa nada de terceros ni de otras capas — cumple el contrato de `import-linter` ya existente sin cambios al contrato.
- Nuevo `ports/orthophoto.py` con `OrthophotoPort` (dos métodos, no dos ports). `ports/errors.py` gana `InvalidHistoricalVintageError`, mismo patrón que `InvalidCadastralReferenceError`.
- Nuevo `adapters/pnoa/` con el cliente HTTP (seam `HttpGetter` inyectable, igual que `adapters/catastro/client.py`), la constante `DEFAULT_MARGIN_M = 10.0` documentada, y la validación de `HistoricalVintage` contra `REGISTRY.md` antes de cualquier petición de red.
- `adapters/catastro/adapter.py` no se modifica; su `_bbox()` ad-hoc queda como está, documentado aquí como un problema distinto (bbox fijo centrado en punto para encuadrar WFS) del que resuelve `bbox_with_margin` (envolvente de geometría + margen configurable), para que una futura limpieza no confunda ambos.
- Riesgo residual señalado explícitamente para revisitar, no para esta historia: la caché diferida (punto 6) es la decisión de este ADR con mayor probabilidad de necesitar revisión a corto plazo, precisamente porque su coste de entrada es bajo — a diferencia de PostGIS, no hace falta levantar nada nuevo para implementarla, así que el umbral para reabrirla debería ser más bajo que el que tuvo `ParcelRepositoryPort`.
- Dos riesgos menores señalados por el code-reviewer al cerrar la historia, no bloqueantes hoy pero a vigilar si Sentinel-2 (0007) reutiliza `bbox_with_margin`/el patrón de `Provenance.url`: (a) `bbox_with_margin` con un `margin_m` negativo de magnitud mayor que medio ancho/alto produce un bbox degenerado (`minx > maxx`) sin error — ningún llamador actual usa un margen negativo; (b) `Provenance.url` en los adapters de Catastro y PNOA se construye concatenando parámetros sin `urlencode` — hoy produce bytes idénticos a la petición real (ningún valor actual contiene `&`/`=`), pero un futuro proveedor con un valor de parámetro con esos caracteres rompería la reproducibilidad exacta de la URL. Ninguno de los dos justifica una decisión nueva todavía; quedan aquí para no perderse.
- **Coste de salida del proveedor (PNOA/IGN):** bajo. Es un WMS público sin autenticación ni facturación (sin lock-in contractual); todo el conocimiento específico de PNOA (URLs, nombres de capa, formato) vive exclusivamente en `adapters/pnoa/`. `domain/`, `ports/`, `application/` y `cli/`/`api/` no saben que el proveedor es PNOA — el port y la entidad están nombrados por capacidad, no por proveedor. Sustituir PNOA por otra fuente de ortofoto (p. ej. un WMS autonómico tipo IDEM, o una API comercial de imagen aérea) exige reescribir solo ese directorio y, por la propia regla de `CLAUDE.md`, un ADR nuevo para el proveedor entrante; el principal coste no es contractual sino de verificación (volver a confirmar bbox/CRS/resolución contra la red real y regrabar fixtures, exactamente el mismo tipo de coste ya pagado una vez con el descubrimiento del filtrado de Catastro). No aplica coste de licencia todavía: `Provenance.license` para PNOA sigue en `asumido` (pendiente de confirmación textual en `REGISTRY.md`), tal como ya exige el AC de la historia.
