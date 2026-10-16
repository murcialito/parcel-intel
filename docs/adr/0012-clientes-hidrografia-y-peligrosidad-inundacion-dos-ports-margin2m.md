# ADR 0012 — Clientes de hidrografía (cauces) y peligrosidad por inundación: dos ports distintos, `LineGeometry` nuevo en dominio, DPH deslindado/servidumbre/policía bloqueado

- Estado: aceptada
- Fecha: 2026-10-16

## Contexto

La historia 0012 partía de territorio completamente nuevo: a diferencia de IDEM (historia 0011, que ya tenía una pasada superficial previa), SNCZI/dominio público hidráulico no tenía ninguna entrada en `REGISTRY.md` antes de esta pasada. El Bloque 1 (descubrimiento y verificación real, detalle completo en `src/parcel_intel/sources/REGISTRY.md`, sección "SNCZI / Dominio Público Hidráulico — MITECO") encontró un resultado mixto, ni un éxito limpio ni un bloqueo limpio:

1. **Cursos de agua (cauces) — `confirmado`, real y rico.** `https://api-features.idee.es/collections/watercourse` (OGC API Features, GeoJSON, soporta `EPSG:25830` explícito) devuelve geometría `LineString` real con atributos de negocio directamente relevantes: `id_demarcd="Tajo"` (la misma demarcación hidrográfica citada textualmente en `docs/vision.md`), `nombre`, anchura, persistencia. Probado con éxito sobre las dos parcelas reales del MVP: Colmenar de Oreja → 0 resultados (sin afección, legítimo); **Villaconejos → 1 resultado real, `"Barranco del Montero"`**, a menos de 2 m de la parcela `REFCAT-RETIRADA` — la misma parcela que IDEM (historia 0011) ya había encontrado en el borde de dos clasificaciones de suelo y dos municipios.
2. **Peligrosidad por inundación (zonas inundables, por periodo de retorno) — `confirmado` como servicio real, pero con una limitación de forma importante.** `https://servicios.idee.es/wms-inspire/riesgos-naturales/inundaciones` (WMS 1.3.0, GeoServer real) tiene capas reales (`NZ.Flood.FluvialT10/T100/T500`, `NZ.Flood.MarinaT100/T500`) y responde con datos reales (confirmado visualmente: imagen real con 175 colores distintos sobre el curso del Manzanares en Madrid). Pero `GetFeatureInfo` devuelve un único valor de **profundidad de agua en metros en un punto/píxel**, no una entidad poligonal con atributos — exactamente el caso que la propia historia 0012 anticipó explícitamente en su Bloque 2 ("salvo que el Bloque 1 documente explícitamente que ningún método disponible devuelve geometría, en cuyo caso se usa el mejor método disponible y esa limitación queda documentada como tal en el adapter"). Sobre las dos parcelas del MVP, ambas devuelven `"NO DATA"` (sin afección, legítimo).
3. **Deslinde legal de DPH, DPH cartográfico, y zonas de servidumbre/policía — `bloqueado`.** Las URLs oficiales citadas por el propio catálogo de datos abiertos de MITECO (`catalogo.datosabiertos.miteco.gob.es`) para estas capas (`wms.mapama.gob.es/sig/Agua/DPHDeslindado`, `.../DPHCartografico`) devuelven un `NullReferenceException` real sin capturar en el backend ASP.NET del Ministerio — confirmado sistémico (no es un nombre de capa equivocado): la misma petición contra una carpeta completamente ajena al dominio hídrico (`Biodiversidad/LIC`) produce idéntico fallo. Ningún servicio alternativo con esta geometría exacta (el deslinde legal, con valor jurídico, distinto del eje del cauce) se encontró funcionando en esta pasada.

`domain/geometry.py` ya tiene `bbox_with_margin`/`BBox`/`EmptyGeometryError` (ADR 0006) y el tipo `Geometry` (superficie cerrada, con anillos). La novedad de esta historia: **ninguna fuente anterior tenía geometría de línea abierta** (todas eran superficies: parcelas, ortofotos, polígonos de clasificación) — mismo patrón de alerta que ya dejó la historia 0011 con los anillos interiores de IDEM, pero esta vez detectado en el diseño (este ADR), no durante la implementación.

## Decisión

**1. Dos ports distintos, no uno — desviación explícita del AC de la historia que pedía "el port nuevo" (singular).** La historia 0012 fue redactada esperando un único cliente combinado para "DPH y zonas inundables", análogo a como IDEM entrega un único `LandClassificationPort`. La evidencia real del Bloque 1 no lo permite sin forzar una entidad artificial: los cursos de agua son una lista de entidades vectoriales reales (geometría de línea, atributos ricos), mientras que la peligrosidad por inundación es una lista de *muestras puntuales* de un raster (sin geometría, un valor numérico por combinación periodo/tipo). Forzarlos al mismo port con una única forma de entidad habría repetido exactamente el error que el ADR 0008 ya señaló para BOE ("no añadir campos sin consumidor real que los necesite") en su forma inversa: aquí el riesgo no es añadir campos de más, es *omitir* la forma real de cada fuente para que ambas encajen en un molde común que ninguna de las dos tiene en la realidad. Se opta por dos ports, cada uno con un único método, mismo criterio de simplicidad que todos los ports anteriores (`LandClassificationPort`, `NdviSeriesPort`, `OfficialBulletinPort`):

```python
# ports/watercourse.py
class WatercoursePort(Protocol):
    """Capacidad: cursos de agua reales (cauces) que intersectan el
    entorno (bbox + margen) de una geometría."""

    def get_nearby_watercourses(
        self, geometry: Geometry, margin_m: float
    ) -> list[Watercourse]:
        """Lista vacía si ningún curso de agua está dentro del bbox+margen
        — resultado esperado y mayoritario, NO una excepción (a diferencia
        de IDEM: aquí "sin cauce cercano" es el caso normal de la mayoría
        de parcelas, confirmado real con Colmenar de Oreja)."""
        ...


# ports/flood_hazard.py
class FloodHazardPort(Protocol):
    """Capacidad: peligrosidad por inundación (profundidad de agua
    estimada) para los periodos de retorno y tipos conocidos, en el
    entorno de una geometría."""

    def get_flood_hazard(
        self, geometry: Geometry, margin_m: float
    ) -> list[FloodHazardSample]:
        """Una muestra por cada combinación conocida de periodo de retorno
        y tipo (5 a fecha de esta historia: fluvial T10/T100/T500, marina
        T100/T500). `water_depth_m=None` si el servicio devuelve "NO DATA"
        en el punto muestreado — resultado esperado y mayoritario, NO una
        excepción. LIMITACIÓN DOCUMENTADA: el servicio real (REGISTRY.md)
        es un raster, no devuelve geometría poligonal — cada muestra se
        toma en el centro del bbox (geometry + margin_m), no en cada punto
        de la geometría real."""
        ...
```

Ninguno de los dos nombres menciona IDEE, SNCZI, MITECO, WMS ni "OGC API Features" — cumple el mismo criterio de nombrado por capacidad que el resto de ports del proyecto.

**2. Entidad `Watercourse`, en `domain/watercourse.py`, con los campos confirmados con significado de negocio claro — mismo criterio selectivo que `LandClassification` (ADR 0011):**

```python
@dataclass(frozen=True)
class Watercourse:
    """Curso de agua real (cauce), con la geometría de su eje/centro —
    NO el deslinde legal del dominio público hidráulico (ver REGISTRY.md,
    sección C: esa geometría no está disponible en ningún servicio en vivo
    verificado). Es la mejor aproximación real disponible para la regla
    `within_distance` a `dph_cauce` citada en docs/vision.md, no un
    sustituto exacto de ella."""

    name: str | None                     # nombre (nilable en el esquema real)
    hydrographic_demarcation_code: str   # id_demarc, p. ej. "ES030"
    hydrographic_demarcation_name: str   # id_demarcd, p. ej. "Tajo"
    course_type: str                     # tipo_cursod, p. ej. "Curso natural"
    persistence: str                     # persistd, p. ej. "Permanente"
    min_width_m: float | None            # ancho_min
    max_width_m: float | None            # ancho_max
    length_m: float | None               # longitud, metros
    geometry: LineGeometry
    provenance: Provenance
```

Se excluyen explícitamente (mismo criterio que ADR 0011 con `CDID`/`CD_UNI`/`CD_REUR` de IDEM): `canaliza`, `marea`, `nativeness`, `drainsbasin`, `condicion`/`condiciond`, `fuente`/`fuented`, `situacion`/`situaciond`, `jerarquia`/`jerarquiad`, `origen`/`origend`, `origen_z`/`origen_zd`, `orden`/`orden_esq`/`orden_esqd`, `hydroid_localid`/`inspireid_localid` — todos confirmados reales y poblados en al menos un feature del Bloque 1, pero sin consumidor identificado ni significado de negocio claro para la regla de distancia a cauce que motiva esta historia. Documentados en `REGISTRY.md` con el mismo nivel de detalle que si se hubieran modelado, para que una futura historia que los necesite no repita la verificación de red.

**3. Tipo de dominio nuevo, `LineGeometry`, en `domain/geometry.py` (mismo módulo que `Geometry`, no uno nuevo) — responde a un riesgo real detectado en el diseño, no durante la implementación (a diferencia de los anillos interiores de IDEM, historia 0011):**

```python
Line = tuple[tuple[float, float], ...]

@dataclass(frozen=True)
class LineGeometry:
    """Geometría de línea abierta (curva), p. ej. el eje de un curso de
    agua. A diferencia de `Geometry` (superficie cerrada, con anillos
    exterior/interior), no tiene noción de interior/exterior — solo una
    secuencia ordenada de puntos. Nueva en la historia 0012: ninguna
    fuente anterior (Catastro, PNOA, IDEM, Sentinel-2) tenía geometría de
    línea — todas eran superficies."""

    points: Line
    srid: int
```

`Geometry.rings` (una tupla de anillos CERRADOS) no es la forma correcta para una polilínea abierta: tratar los puntos de un curso de agua como un único "anillo" mentiría sobre la forma (un consumidor podría asumir que el primer y el último punto están conectados, cerrando una superficie que no existe). Se añade `LineGeometry` como tipo hermano, no sustituto, en el mismo módulo — sigue siendo stdlib puro (`dataclasses`), sin romper el contrato de `import-linter`. **Decisión explícita para evitar repetir el patrón de la lección de la historia 0011** ("un tipo de dominio con una restricción documentada en su docstring deja de ser cierta en cuanto llega una fuente nueva que sí la tiene"): en vez de forzar `Watercourse.geometry` a usar `Geometry` y descubrir el problema al escribir el parser (como pasó con los anillos interiores de IDEM), se señala aquí, en el ADR, antes de que exista una sola línea de parser. La elevación (coordenada Z) real que trae la geometría de origen (confirmado real: `LineString` 3D con cota) se descarta explícitamente al parsear — ningún consumidor actual necesita elevación, documentado como simplificación conocida, no como omisión accidental.

**4. Entidad `FloodHazardSample`, en `domain/flood_hazard.py`:**

```python
@dataclass(frozen=True)
class FloodHazardSample:
    """Profundidad de agua estimada (metros) para un periodo de retorno y
    tipo de inundación, en el punto muestreado del raster real de
    peligrosidad (REGISTRY.md, sección B) — NO en toda la geometría de la
    parcela: el servicio no devuelve un polígono de zona inundable, solo
    un valor en un punto."""

    kind: Literal["fluvial", "marina"]
    return_period_years: int        # 10, 100 o 500 (los 5 reales conocidos)
    water_depth_m: float | None     # None = "NO DATA" confirmado real
    provenance: Provenance
```

Sin campo de geometría (ninguna disponible, documentado explícitamente tanto aquí como en el port). Responde a la pregunta abierta de la historia sobre "¿se modelan todos los periodos de retorno?": sí, los 5 confirmados reales (`FluvialT10/T100/T500`, `MarinaT100/T500`) — ninguno se difiere, porque los 5 están confirmados reales y accesibles con el mismo método (`GetFeatureInfo`), sin coste adicional de verificación.

**5. Adapters en dos carpetas nuevas, cada una con su propio seam de red (nunca importado de otro adapter, mismo precedente que todos los anteriores):**

- `adapters/hydrography/` (implementa `WatercoursePort` contra `api-features.idee.es`):
  - `client.py`: seam `HttpGetter` con la MISMA forma que PNOA/Catastro/IDEM (`(url, params) -> bytes`, GET con querystring) — el contrato HTTP real (confirmado en el Bloque 1) es GET+KVP igual que los anteriores, solo cambia el formato de respuesta (JSON en vez de XML/GML).
  - `parsing.py`: parsea GeoJSON (`json.loads`, no XML) a `RawWatercourse` (`TypedDict`), incluyendo la conversión de los campos numéricos (que llegan como `string` en el JSON real, p. ej. `"ancho_min": "5"`) a `float | None`, y el descarte explícito de la cota Z de cada punto de la geometría.
  - `adapter.py`: `HydrographyAdapter`, `DEFAULT_MARGIN_M = 2.0` (ver punto 6), guarda `EmptyGeometryError` antes de cualquier petición (vía `bbox_with_margin`), `bbox-crs`/`crs` siempre fijados a `EPSG:{geometry.srid}` explícito (confirmado real que el servicio reproyecta correctamente sin que el cliente lo haga).
- `adapters/flood_hazard/` (implementa `FloodHazardPort` contra `servicios.idee.es`):
  - `client.py`: seam propio, mismo contrato `(url, params) -> bytes` (GET+KVP, WMS clásico).
  - `parsing.py`: parsea la respuesta `text/html` de `GetFeatureInfo` (confirmado en el Bloque 1 como la más legible: la etiqueta literal `"NO DATA"` es más fiable de detectar que el valor crudo `GRAY_INDEX=999.0`, que es un código específico de esta capa, no un sentinel genérico — ver REGISTRY.md hallazgo 4) con una expresión regular simple sobre la celda de la tabla, a un `float | None`.
  - `adapter.py`: `FloodHazardAdapter`, consulta las 5 capas conocidas (constante `_KNOWN_LAYERS: tuple[tuple[str, Literal["fluvial","marina"], int], ...]`) con una petición `GetFeatureInfo` por capa, `WIDTH=HEIGHT=256`, `I=J=128` (centro exacto del bbox), mismo patrón que el usado para verificar en el Bloque 1.

**6. Margen por defecto: `2.0 m` para `HydrographyAdapter` (mismo criterio que IDEM, ADR 0011) — explícitamente NO `100.0 m` (el umbral citado en la regla de negocio de `docs/vision.md`).** Responde la pregunta abierta de la historia sobre si reutilizar el criterio de IDEM o inventar uno distinto: se reutiliza, pero con una precisión importante — el margen de este cliente es una salvaguarda de punto flotante en el borde exacto de una geometría de alta precisión, igual que IDEM, **no** una codificación del umbral de negocio de 100 m. Ese umbral pertenece al motor de reglas futuro (`within_distance`, fuera de alcance de este cliente), que deberá pasar `margin_m=100.0` explícitamente cuando implemente esa regla concreta — si el valor de negocio se hubiera puesto como *default* del adapter, un cambio futuro en la regla (p. ej. una demarcación con un umbral distinto) obligaría a tocar el adapter en vez de solo el motor de reglas, acoplando una decisión de negocio a una capa que no debería conocerla. Para `FloodHazardAdapter` el margen no tiene efecto práctico sobre el resultado (siempre se muestrea el centro exacto del bbox, que no cambia con el margen) — se mantiene el mismo parámetro y el mismo default por consistencia de interfaz entre los dos ports nuevos de esta historia, documentado explícitamente como "sin efecto observable" en el docstring del adapter.

**7. Sin excepciones nuevas en `ports/errors.py` para estas dos fuentes — "sin afección" se modela como lista vacía o como `water_depth_m=None`, nunca como excepción.** Responde el AC explícito de la historia (distinto del criterio ya fijado para IDEM/BOE/BOCM): aquí "sin cauce cercano" y "sin profundidad de agua estimada" son el resultado esperado y mayoritario para la gran mayoría de parcelas de España, no un caso excepcional — modelarlo como excepción obligaría a todo consumidor futuro a envolver la llamada en `try/except` para el caso común, exactamente lo que el AC pide evitar.

**8. `Watercourse` como aproximación documentada para "cauce" — nunca presentada como equivalente al deslinde legal del DPH.** Dado el hallazgo de bloqueo de la sección C de `REGISTRY.md`, el docstring de la entidad (punto 2 arriba) deja explícito que la geometría es el eje del curso de agua, no la línea de deslinde con valor jurídico. Cualquier futuro motor de reglas que implemente `within_distance` a `dph_cauce` citando la autorización de la Confederación Hidrográfica debe leer esta distinción antes de asumir que la distancia medida desde `Watercourse.geometry` es jurídicamente equivalente a la distancia medida desde el deslinde real.

**9. Deslinde legal de DPH, DPH cartográfico, y zonas de servidumbre (5 m)/policía (100 m) como capas propias: quedan explícitamente SIN cliente en esta historia.** No se diseña ningún port ni adapter para estas capas — el Bloque 1 confirmó que el único servicio citado oficialmente para ellas (`wms.mapama.gob.es/sig/Agua/DPHDeslindado`/`DPHCartografico`) está roto en producción, con evidencia reproducible (mismo fallo en una carpeta ajena al dominio hídrico). Se deja como candidata explícita para una historia futura la investigación del geoportal propio de la Confederación Hidrográfica del Tajo (no probado en esta pasada) como fuente alternativa — decisión explícitamente abierta, no resuelta aquí, siguiendo el mismo criterio que la historia 0012 pedía para el caso de bloqueo parcial.

**10. Caché: diferida, mismo criterio que las seis fuentes anteriores.** Ningún caso de uso real conectado todavía a ninguno de los dos clientes.

## Alternativas consideradas

- **Un único port combinado (`HydrologicalFeaturePort` o similar), con una entidad `union` o un campo `kind: Literal["cauce", "zona_inundable"]` que distinga las dos formas**: rechazada. Las dos fuentes reales no solo tienen "tipo" distinto, tienen **forma de retorno** distinta (lista de entidades vectoriales con geometría real vs. lista de muestras puntuales de un raster sin geometría) — forzar una única entidad habría necesitado campos opcionales que son `None` según el `kind` (p. ej. `geometry: LineGeometry | None`, `water_depth_m: float | None` ambos a la vez en la misma clase), exactamente el tipo de diseño que las lecciones de este proyecto ya han señalado como señal de "la abstracción no es real, es una coincidencia de nombre" (mismo criterio que el ADR 0011 usó para rechazar reutilizar el parser GML de Catastro en IDEM).
- **Tratar la geometría de `Watercourse` como `Geometry` (anillos), metiendo la polilínea como un único anillo "abierto" con una nota de que no debe tratarse como cerrado**: rechazada. Depender de una nota en un comentario para que un consumidor no cierre accidentalmente una forma que no es cerrada es exactamente el tipo de riesgo silencioso que la lección de la historia 0011 (anillos interiores de IDEM) ya advirtió sobre `Geometry` — más barato y más seguro introducir `LineGeometry` como tipo distinto ahora, en el diseño, que descubrir el malentendido durante la implementación de un consumidor futuro (p. ej. un cálculo de distancia punto-a-polígono aplicado por error a lo que en realidad es una polilínea).
- **Diferir por completo el cliente de peligrosidad por inundación a una historia futura, dado que su forma (raster, sin geometría) no encaja con el patrón "lista de entidades con geometría" del resto del proyecto**: considerada seriamente, rechazada. El propio AC de la historia 0012 anticipa explícitamente el caso "ningún método disponible devuelve geometría" y pide usar el mejor método disponible documentando la limitación — diferirlo habría ignorado esa instrucción explícita sin una razón de peso distinta de "no encaja perfectamente con el patrón visual de los ports anteriores", que no es razón suficiente dado que el servicio es real, verificado, y relevante para el negocio (peligrosidad de inundación es, junto con la distancia a cauce, la otra mitad del concepto "afección hidráulica" que motiva esta historia).
- **Muestrear varios puntos de la geometría real (p. ej. las cuatro esquinas del bbox, o el perímetro completo) en vez de solo el centro, para `FloodHazardPort`**: rechazada por ahora. Multiplicaría las peticiones de red (4-8× por capa, 5 capas) sin que ninguna pregunta de negocio actual (la regla citada en `docs/vision.md` es sobre distancia a cauce, no sobre fracción de parcela inundable) lo necesite — mismo criterio de "no diseñar para una necesidad hipotética" ya aplicado repetidamente en este proyecto. Documentado como limitación explícita, revisitable si una historia futura necesita "¿qué fracción de la parcela está en zona inundable?" en vez de "¿hay riesgo de inundación cerca de esta parcela?".
- **Margen por defecto de `100.0 m` para `HydrographyAdapter`, igual al umbral citado en `docs/vision.md`**: rechazada (ver punto 6 de la Decisión) — acoplaría un valor de negocio al adapter, exactamente el tipo de fuga de capa que la arquitectura hexagonal de este proyecto existe para evitar.
- **Reintentar el gateway roto de MITECO (`wms.mapama.gob.es`) con más variantes de parámetros, con la esperanza de encontrar la combinación exacta que lo hace funcionar**: rechazada. La evidencia del Bloque 1 (mismo `NullReferenceException`, misma línea de código, en una carpeta completamente ajena al dominio hídrico) confirma que el fallo es un bug de producción del lado del servidor, no un parámetro mal puesto del lado del cliente — seguir intentando variantes de querystring no es un uso razonable del tiempo de verificación frente a una excepción no capturada real en el código del servidor.

## Consecuencias

- Nuevo `domain/watercourse.py` (`Watercourse`), nuevo `domain/flood_hazard.py` (`FloodHazardSample`), y `domain/geometry.py` gana `LineGeometry`/`Line` (sin tocar `Geometry` existente, sin romper ningún consumidor actual). Todos stdlib puro — cumple `import-linter` sin cambios al contrato.
- Nuevo `ports/watercourse.py` (`WatercoursePort`, un método) y `ports/flood_hazard.py` (`FloodHazardPort`, un método). `ports/errors.py` **no** gana ninguna excepción nueva (punto 7 de la Decisión) — primera vez en este proyecto que un par de ports nuevos no necesita ningún error de dominio nuevo.
- Nuevo `adapters/hydrography/` (`client.py`, `parsing.py`, `adapter.py` con `HydrographyAdapter`, `DEFAULT_MARGIN_M = 2.0`) y `adapters/flood_hazard/` (`client.py`, `parsing.py`, `adapter.py` con `FloodHazardAdapter`, la constante `_KNOWN_LAYERS` con las 5 combinaciones reales confirmadas).
- `src/parcel_intel/sources/REGISTRY.md` queda actualizado con la sección completa "SNCZI / Dominio Público Hidráulico — MITECO" (tres subsecciones: A cursos de agua `confirmado`, B peligrosidad por inundación `confirmado` con limitación, C DPH deslindado/cartográfico `bloqueado`), con fixtures nuevas en `tests/fixtures/dph/` (11 ficheros: `GetCapabilities` del WMS, `GetFeatureInfo` en HTML y GML para las dos parcelas del MVP, una imagen `GetMap` real con zona de riesgo visible sobre el Manzanares como prueba positiva, tres respuestas `items` de la colección `watercourse` — incluyendo el hallazgo positivo real de Villaconejos y el muestreo amplio de Aranjuez —, el esquema de la colección, y tres respuestas rotas del gateway de MITECO más un control en una carpeta ajena al dominio hídrico).
- Riesgo residual explícito, señalado para no perderse: `Watercourse.geometry` (eje del cauce) y el deslinde legal real del DPH **no son la misma línea** — cualquier motor de reglas futuro que implemente la distancia de 100 m citada en `docs/vision.md` debe decidir explícitamente si acepta esta aproximación o invierte en encontrar/verificar el deslinde legal real (p. ej. vía el geoportal de la Confederación Hidrográfica del Tajo, no probado en esta pasada) antes de usarla para una decisión con consecuencia legal real (`requires_authorization`).
- Riesgo residual compartido con el resto de adapters de este proyecto (no corregido aquí): `Provenance.url` se construye concatenando parámetros sin `urlencode`.
- **Coste de salida del proveedor (IDEE/IGN, ambos servicios nuevos de esta historia):** bajo, mismo patrón que PNOA/IDEM/Sentinel-2. Son servicios públicos sin autenticación ni facturación, sin lock-in contractual. Todo el conocimiento específico de IDEE (URLs, nombre de la colección `watercourse`, el esquema completo de ~30 campos, el hallazgo de que `GetFeatureInfo` da profundidad en un punto no geometría, los 5 nombres de capa de peligrosidad) vive exclusivamente en `adapters/hydrography/` y `adapters/flood_hazard/`; `domain/`, `ports/`, `application/` y `cli/`/`api/` no saben que el proveedor es IDEE — los ports y entidades están nombrados por capacidad, dejando abierta la puerta a que un futuro adapter de otra fuente de hidrografía (p. ej. si se encuentra el deslinde legal real de la CHT) implemente el mismo `WatercoursePort` o uno análogo. El coste principal de sustituir cualquiera de los dos es, como siempre en este proyecto, de verificación (volver a confirmar esquema/CRS/comportamiento contra la red real), no de dinero ni de contrato. No aplica coste de licencia todavía: `Provenance.license` para ambas fuentes queda `asumido` (el de hidrografía tiene al menos una URL de licencia citada y confirmada como existente, aunque no leída textualmente; el de peligrosidad por inundación no tiene ninguna cita todavía) — no se resuelve aquí.
