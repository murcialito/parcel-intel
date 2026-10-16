# ADR 0011 — Cliente IDEM: entidad `LandClassification`, port único `LandClassificationPort`, `BBOX` en vez de `CQL_FILTER`, campos confirmados modelados selectivamente, margen por defecto de 2 m

- Estado: aceptada
- Fecha: 2026-10-16

## Contexto

La historia 0011 (cliente de clasificación de suelo sobre IDEM) deja siete preguntas abiertas para el arquitecto, todas condicionadas a una re-verificación real contra la red — mismo criterio que ya forzó re-verificaciones completas en Sentinel-2 (ADR 0007), BOE (ADR 0008) y BOCM (ADR 0009), todas las cuales encontraron que la pasada superficial original de la historia 0001 estaba incompleta o, en más de un caso, directamente equivocada. Esta re-verificación (detalle completo en `src/parcel_intel/sources/REGISTRY.md`, sección IDEM, reescrita en esta misma pasada) confirma que el patrón se repite una cuarta vez:

1. **Hallazgo 0 (nuevo tipo de discrepancia, no visto en 0007/0008/0009):** la fixture grabada en la historia 0001 (`wfs_getfeature_colmenar_clasificacion.xml`) no coincidía con lo que el propio `REGISTRY.md` afirmaba sobre ella — el texto decía "52 polígonos reales devueltos", pero el archivo grabado solo tenía 1 `<wfs:member>` (`numberMatched="52" numberReturned="1"`). Repetir la misma petición en esta pasada confirma que la prosa era correcta (el servicio sí devuelve 52/52 reales sin paginar por defecto); solo la fixture grabada estaba truncada. Corregida y sustituida por `wfs_getfeature_cql_colmenar_municipio_completo.xml`.
2. **`GetFeature` con filtro espacial `BBOX`** (KVP plano, `bbox=minx,miny,maxx,maxy,EPSG:25830`, GET, sin `CQL_FILTER`) funciona exactamente con el mismo contrato de red que ya usan Catastro y PNOA — confirmado real sobre el bbox de una parcela real de Colmenar de Oreja (`REFCAT-RETIRADA`, geometría tomada de la fixture ya existente de Catastro) y de Villaconejos (`REFCAT-RETIRADA`).
3. **Esquema completo de campos confirmado con `DescribeFeatureType` real**, cruzado contra 56 features reales observadas: además de `DS_CLASIF_GEN`/`DS_MUNICIPIO`/`CD_MUNICIPIO`, existen y están siempre poblados `FC_REF` (fecha de vigencia, tipo `date`), `CD_SIGLAS` (código corto de clasificación), `DS_CLASIF_DET` (clasificación más granular), `NM_AREA` (superficie real del polígono completo, en m²), `NM_LONGITUD` (perímetro), y tres identificadores internos sin significado de negocio confirmado (`CDID`, `CD_UNI`, `CD_REUR`). **No existe ningún campo de identificador de norma/ordenanza** (PGOU, Normas Subsidiarias, con nombre o fecha de aprobación) — los tres campos de texto libre del esquema (`DS_NOTAS`, `DS_ADJUNTO`, `DS_NOTAS_REF`) existen pero están vacíos en las 56 features reales observadas, sin una sola excepción.
4. **Caso real de solape confirmado**, sin necesidad de forzarlo: el bbox de la parcela rústica `REFCAT-RETIRADA` de Villaconejos (margen 2 m, y también con margen 0) devuelve 3 features reales — dos clasificaciones generales distintas (`Suelo No Urbanizable Común` y `Suelo No Urbanizable Protegido`) **y dos municipios distintos** (Villaconejos y Chinchón, colindante, también de la Comunidad de Madrid).
5. **Bbox sin cobertura devuelve `200 OK` con `FeatureCollection` vacía**, idéntico tanto fuera de la Comunidad de Madrid (probado en Toledo) como fuera de España continental (probado en el Atlántico) — no hay ninguna distinción observable entre "fuera de cobertura del servicio" y "hueco real dentro de la cobertura de la Comunidad de Madrid".

`domain/geometry.py` ya tiene `bbox_with_margin`/`BBox`/`EmptyGeometryError` (ADR 0006), reutilizado sin cambios. `domain/provenance.py` (ADR 0002) ya es el value object compartido de procedencia. `ports/errors.py` ya tiene el patrón de "un solo tipo de error cuando el proveedor tampoco distingue las causas" (`BulletinNotPublishedError`, ADR 0008/0009). Esta historia entrega solo el cliente aislado, sin conectar a ningún caso de uso (mismo patrón que 0002→0006→0007→0008→0009).

## Decisión

**1. Entidad `LandClassification`, en `domain/land_classification.py`, con los campos confirmados que tienen significado de negocio claro — no los tres identificadores internos sin significado confirmado:**

```python
@dataclass(frozen=True)
class LandClassification:
    """Clasificación de suelo que aplica sobre un polígono real de
    planeamiento urbanístico vigente (ver REGISTRY.md, sección IDEM).

    `area_m2` es la superficie del polígono de clasificación COMPLETO, no de
    la intersección con ninguna parcela concreta — calcular esa intersección
    es tarea de una capa de reglas futura (ver "Fuera de alcance" de la
    historia 0011), no de este cliente."""

    general_category: str      # DS_CLASIF_GEN, p. ej. "Suelo No Urbanizable Común"
    detailed_category: str     # DS_CLASIF_DET, más granular
    short_code: str            # CD_SIGLAS, p. ej. "SUBNS", "SNUP"
    reference_date: date       # FC_REF, fecha de vigencia del dato
    municipality_code: str     # CD_MUNICIPIO
    municipality_name: str     # DS_MUNICIPIO
    area_m2: float             # NM_AREA, superficie del polígono completo
    geometry: Geometry
    provenance: Provenance
```

Se excluyen explícitamente `CDID`, `CD_UNI`, `CD_REUR` y `NM_LONGITUD`: los tres primeros son identificadores internos del sistema IDEM confirmados reales pero sin significado de negocio verificado más allá de su composición (ver REGISTRY.md, hallazgo 2), y `NM_LONGITUD` (perímetro) no tiene ningún consumidor previsto ni pregunta del Bloque 1 que lo requiera. Esta decisión responde a la pregunta abierta 2 de la historia de un modo distinto al precedente de `Orthophoto`/`BulletinNotice` (ADR 0006/0008, "diferir campos especulativos hasta un segundo consumidor real"): aquí no se difieren por falta de evidencia de que existan (sí existen, confirmados reales), sino que se excluyen selectivamente por falta de significado de negocio confirmado — es la misma lógica de fondo ("no modelar lo que no tiene un uso claro todavía") aplicada a un caso distinto (campo real pero opaco, en vez de campo todavía no verificado). `reference_date`, `short_code`, `detailed_category` y `area_m2` sí entran porque el propio contexto de la historia 0011 pregunta explícitamente por "fecha de vigencia", "código corto de clasificación" y "superficie del polígono" — a diferencia de BOE/BOCM, aquí la propia historia ya señalaba estos campos como de interés antes de confirmar si existían, así que, confirmados, se modelan sin necesitar un segundo consumidor adicional que lo justifique.

**2. Un solo port, con un solo método, en `ports/land_classification.py`:**

```python
class LandClassificationPort(Protocol):
    """Capacidad: clasificaciones de suelo de planeamiento urbanístico
    vigente que intersectan el entorno (bbox + margen) de una geometría."""

    def get_land_classifications(
        self, geometry: Geometry, margin_m: float
    ) -> list[LandClassification]:
        """Devuelve TODAS las clasificaciones encontradas para el bbox
        calculado (geometry + margin_m) — nunca colapsadas a una sola.
        Lanza NoLandClassificationFoundError si ninguna clasificación
        intersecta ese bbox."""
        ...
```

Ningún nombre menciona IDEM, WFS, WMS ni Comunidad de Madrid (cumple el AC explícito). El tipo de retorno es siempre `list[...]`, nunca un resultado único opcional con una lista aparte de "solapes": responde la pregunta abierta 3 de la historia en el mismo sentido que ya decidieron `OfficialBulletinPort.get_daily_bulletin` (ADR 0008) y `NdviSeriesPort.get_ndvi_series` (ADR 0007) — ambos devuelven `list[...]` incluso cuando el caso típico es "un solo resultado", porque una lista no fuerza a nadie a interpretar el caso N=1 como distinto del caso N≥2, y el hallazgo 3 de esta historia confirma con evidencia real que N≥2 no es un caso de laboratorio sino un resultado real del primer municipio probado fuera de la parcela de referencia de Colmenar. Decidir cuál de las clasificaciones devueltas "aplica de verdad" a la parcela (p. ej. por mayor área de intersección con la geometría exacta, no con el bbox envolvente) sigue fuera de alcance de este cliente, tal como ya fijaba la propia historia.

**3. `GetFeature` con filtro espacial `BBOX`, nunca `CQL_FILTER` por municipio.** Responde la pregunta 3 del Bloque 1 de la historia con evidencia real (`REGISTRY.md`, hallazgo 1): `bbox=minx,miny,maxx,maxy,EPSG:25830` sobre la capa `VPLA_V_CLASIFICACION_REF_25` devuelve exactamente los polígonos que intersectan ese bbox, calculado con `domain.geometry.bbox_with_margin` a partir de la `Geometry` real de la parcela — a diferencia de `CQL_FILTER=DS_MUNICIPIO='...'`, que sí funciona (confirmado otra vez en esta pasada, corrigiendo la fixture truncada del hallazgo 0) pero devuelve los 52 polígonos de todo el municipio, sin aislar cuál(es) cubren la parcela concreta. `CQL_FILTER` queda descartado como método de consulta de este cliente, no por no funcionar, sino por ser la herramienta equivocada para el caso de uso real (una geometría de parcela, no un nombre de municipio completo).

**4. Seam de red propio en `adapters/idem/client.py`, con el mismo contrato que `HttpGetter` de PNOA/Catastro — redefinido localmente, no importado de esos adapters.** Responde la pregunta abierta 4:

```python
class HttpGetter(Protocol):
    def __call__(self, url: str, params: dict[str, str]) -> bytes: ...

def default_http_getter(url: str, params: dict[str, str]) -> bytes:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.content
```

El contrato real de IDEM (confirmado en esta pasada) es GET con querystring, siempre `200 OK` incluso en el caso de "sin resultados" (a diferencia de BOE, que sí necesita el código de estado como señal de dominio explícita — ver ADR 0008). Por eso no hace falta ningún seam nuevo con forma distinta (como `DailySummaryGetter` de BOE o `UrlGetter` de BOCM): el contrato es idéntico al de PNOA/Catastro, así que se redefine literalmente la misma forma en `adapters/idem/`, siguiendo el precedente de que cada adapter define su propia copia en vez de importar de otro adapter (ningún adapter de este proyecto importa de otro adapter hasta ahora; mantenerlo evita acoplar dos proveedores entre sí por un seam compartido que podría divergir en el futuro sin que ambos adapters se enteren a la vez).

**5. Parsing propio en `adapters/idem/parsing.py`, reutilizando el *patrón* GML de `adapters/catastro/parsing.py` (recorrido por nombre local de elemento, `TypedDict` de salida) sin importar código de `adapters/catastro/`.** Responde la pregunta abierta 6: el esquema real de IDEM (namespace `UsoDelSuelo`, elemento `VPLA_V_CLASIFICACION_REF_25`, geometría en `GEOMETRY1` como `gml:MultiSurface`) es suficientemente distinto del de Catastro (`cp:CadastralParcel`/`bu-ext2d:Building`, geometría en `gml:Polygon`/`gml:MultiSurface` directamente bajo el feature, sin un elemento intermedio nombrado) como para justificar un parser propio, aunque ambos comparten la misma técnica general (`xml.etree.ElementTree`, recorrido por nombre local sin fijar prefijo de namespace, `TypedDict` para el borde adapter↔dominio — lección ya registrada tras la historia 0001). Se define `RawLandClassification` (`TypedDict`) con los mismos campos que `LandClassification` menos `geometry`/`provenance`, siguiendo el patrón ya usado por `RawParcel`/`RawBuilding` (Catastro) y `RawItem`/`RawDisposicionMetadata` (BOE/BOCM).

**6. Error nuevo, único, en `ports/errors.py` — mismo criterio que `BulletinNotPublishedError` (ADR 0008/0009):**

```python
class NoLandClassificationFoundError(Exception):
    """Ningún polígono de clasificación de suelo intersecta el bbox pedido.
    El servicio no distingue "fuera de cobertura de la Comunidad de Madrid"
    de "hueco real dentro de la cobertura" — confirmado real en
    REGISTRY.md (ambos casos devuelven una FeatureCollection vacía
    idéntica, 200 OK, 0 features) — así que tampoco este cliente los
    distingue."""

    def __init__(self, bbox: tuple[float, float, float, float]) -> None:
        super().__init__(f"Ninguna clasificación de suelo encontrada para el bbox: {bbox}")
        self.bbox = bbox
```

Responde la pregunta abierta 5: un único tipo de error, no dos, porque el hallazgo 4 de `REGISTRY.md` confirma con evidencia real (Toledo fuera de la Comunidad de Madrid, Atlántico fuera de España) que el servicio no distingue las dos causas en ninguna señal observable — inventar la distinción en el cliente repetiría exactamente el error que el ADR 0008 ya evitó para BOE.

**7. Margen por defecto: `2.0` metros, constante nombrada en `adapters/idem/adapter.py` (`DEFAULT_MARGIN_M = 2.0`), propia de este adapter — no comparte valor con PNOA (`10.0 m`, ADR 0006) ni con Sentinel-2.** Responde la pregunta abierta 7. A diferencia de PNOA/Sentinel-2 (donde el margen da contexto visual o cubre el tamaño de píxel de una imagen raster), aquí la geometría de clasificación es vectorial de alta precisión — el margen no sirve para dar contexto visual, sirve únicamente como salvaguarda frente a imprecisión de punto flotante y a la semántica de "intersecta" del filtro `BBOX` del servicio en el borde exacto de un polígono. Evidencia real de esta pasada: el caso de solape de Villaconejos (hallazgo 3 de `REGISTRY.md`) da el mismo resultado exacto (3 features, mismas clasificaciones) con margen `0` y con margen `2 m` — el solape es real y ya está presente en el bbox exacto de la parcela, el margen no lo induce. Se elige `2.0 m` (no `0.0 m`) como salvaguarda barata contra el caso no probado de una parcela cuyo borde coincide pixel-perfecto con el borde de una clasificación en el dato de origen, donde una comparación de punto flotante sin ningún margen podría, en el peor caso, no considerar "intersectante" un polígono que a efectos prácticos sí lo es. No se comparte este valor con ningún otro adapter, siguiendo el mismo criterio ya fijado por el ADR 0006 (cada adapter decide su propia constante).

**8. Caché: diferida explícitamente, mismo criterio que PNOA/Sentinel-2/BOE/BOCM.** Responde la pregunta abierta 6 (caché) de la historia: no hay ningún caso de uso real conectado todavía que repita la misma consulta de clasificación más de una vez, ni entre ejecuciones ni dentro de la misma ejecución — el disparador para revisarlo sigue siendo el mismo ya fijado en los ADR 0006-0009: la primera historia que conecte este cliente a un caso de uso con una revisita real.

## Alternativas consideradas

- **Modelar también `CDID`/`CD_UNI`/`CD_REUR` en `LandClassification`, por lectura estricta del AC de la historia ("incluyendo... cualquier campo adicional que el Bloque 1 haya confirmado que existe")**: considerada y rechazada. Los tres campos existen y están poblados (no son especulativos), pero ninguno tiene significado de negocio confirmado más allá de ser un identificador interno sin documentación fiable — añadirlos sería ruido en la entidad sin ningún consumidor que los necesite, contrario al criterio ya fijado por el ADR 0008 ("no se incluye el departamento: el AC no lo exige y añadirlo sin un consumidor que lo necesite repetiría el mismo error [que el ADR 0004 corrigió]"). Se documentan en `REGISTRY.md` con el mismo nivel de detalle que si se hubieran modelado, para que una futura historia que sí los necesite (p. ej. si `CD_UNI`/`CD_REUR` resultan ser la clave para cruzar con un registro de instrumentos de planeamiento todavía no descubierto) no tenga que repetir la verificación de red, solo añadir el campo.
- **Devolver un tipo "resultado único + lista de solapes" explícito** (p. ej. `ClassificationResult(primary: LandClassification | None, overlaps: list[LandClassification])`) en vez de `list[LandClassification]` siempre: rechazada. Fuerza una semántica de "cuál es la principal" que este cliente no puede decidir con la información que tiene (decidir por área de intersección exacta es tarea de la capa de reglas futura, fuera de alcance explícito de esta historia) — inventar un "primary" arbitrario (p. ej. el primer feature devuelto) sería peor que no decidir nada, y el precedente de `list[...]` siempre (BOE, Sentinel-2) ya resuelve esto sin ambigüedad.
- **Reutilizar `HttpGetter` de `adapters/pnoa/client.py` o `adapters/catastro/client.py` mediante import directo entre adapters**: rechazada. Ningún adapter de este proyecto importa de otro adapter; hacerlo aquí acoplaría dos proveedores sin beneficio real (el contrato es trivial, tres líneas) y rompería la independencia de que cada directorio de adapter se pueda sustituir sin tocar ningún otro.
- **Reutilizar el parser GML de `adapters/catastro/parsing.py` (`_rings_from_feature`, `_local_name`) importándolo directamente**: rechazada por la misma razón que el punto anterior, agravada porque el esquema real de IDEM (namespace `UsoDelSuelo`, elemento con 14 campos propios) es suficientemente distinto del de Catastro como para que una función compartida necesitara parámetros o condicionales específicos de cada proveedor — exactamente la señal de que no es, todavía, una abstracción real compartida, solo una coincidencia de técnica.
- **`CQL_FILTER` por municipio como método de consulta del cliente, filtrando del lado del cliente qué polígono(s) intersectan la parcela entre los 52 devueltos**: rechazada. Funciona (confirmado real, dos veces), pero descarga 52 polígonos completos de un municipio para encontrar como mucho 1-3 relevantes — coste de red y de parsing innecesario frente a `BBOX`, que ya filtra del lado del servidor con precisión de parcela. No hay ninguna ventaja de `CQL_FILTER` sobre `BBOX` para este caso de uso.
- **Dos tipos de error distintos para "fuera de la Comunidad de Madrid" y "hueco real dentro de la cobertura"**: rechazada. El hallazgo 4 de `REGISTRY.md` confirma con dos peticiones reales (Toledo, Atlántico) que el servicio no distingue ninguna de las dos causas en ninguna señal observable — inventar la distinción sería diseño especulativo sin base real, mismo criterio ya aplicado a BOE/BOCM.
- **Margen por defecto igual al de PNOA (`10.0 m`) "por si acaso"**: rechazada. No hay ninguna razón técnica para ese valor en datos vectoriales de alta precisión — el margen aquí no cubre resolución de píxel ni contexto visual, solo imprecisión de punto flotante; `2.0 m` ya es generoso para ese propósito y la evidencia real (hallazgo 3) muestra que ni siquiera hace falta margen para detectar el solape real encontrado.
- **Adelantar caché por el riesgo de que una futura capa de reglas consulte la misma parcela varias veces (una por cada módulo que necesite su clasificación)**: rechazada por ahora, mismo criterio que PNOA/Sentinel-2/BOE/BOCM — sin consumidor real todavía, cachear sería adivinar la forma de la clave de caché.

## Consecuencias

- Nuevo `domain/land_classification.py` (`LandClassification`). Stdlib puro (`dataclasses`, `datetime.date`), sin imports de otras capas — cumple el contrato de `import-linter` sin cambios al contrato.
- Nuevo `ports/land_classification.py` (`LandClassificationPort`, un método). `ports/errors.py` gana `NoLandClassificationFoundError`.
- Nuevo `adapters/idem/` (`client.py` con `HttpGetter`/`default_http_getter`, redefinidos localmente; `parsing.py` con `RawLandClassification`/el recorrido GML propio; `adapter.py` con `IdemAdapter` implementando `LandClassificationPort`, la constante `DEFAULT_MARGIN_M = 2.0`, y la guarda explícita de `EmptyGeometryError` antes de cualquier petición de red, mismo patrón ya exigido tras la historia 0006).
- `src/parcel_intel/sources/REGISTRY.md` (sección IDEM) queda reescrito en esta misma pasada con el esquema exacto confirmado, el caso real de solape, el caso real sin cobertura, y la corrección de la fixture truncada de la historia 0001 (hallazgo 0); se añaden cinco fixtures nuevas en `tests/fixtures/idem/` (`wfs_describefeaturetype_clasificacion_ref25.xml`, `wfs_getfeature_bbox_colmenar_rustica_margin2m.xml`, `wfs_getfeature_bbox_villaconejos_rustica_margin2m_solape.xml`, `wfs_getfeature_bbox_fuera_cobertura_toledo.xml`, `wfs_getfeature_cql_colmenar_municipio_completo.xml`), y se elimina la fixture truncada (`wfs_getfeature_colmenar_clasificacion.xml`).
- Riesgo residual señalado explícitamente para no bloquear esta historia pero no perderse: el significado exacto de `CD_UNI`/`CD_REUR` queda sin confirmar más allá de su composición observada — si una historia futura necesita cruzar la clasificación de suelo con un registro de instrumentos de planeamiento (PGOU, Normas Subsidiarias) con nombre/fecha de aprobación, la evidencia de esta pasada confirma que **esta capa no lo tiene**; haría falta investigar otra capa de IDEM o una fuente distinta (otra historia de investigación, fuera de alcance aquí).
- Riesgo residual compartido con BOE/BOCM/PNOA (no corregido aquí): `Provenance.url` se construye concatenando parámetros sin `urlencode`, igual que en el resto de adapters de este proyecto — sin impacto real porque ningún valor de parámetro de IDEM contiene `&`/`=`.
- **Coste de salida del proveedor (IDEM, Comunidad de Madrid):** bajo. Es un WFS/WMS público sin autenticación ni facturación, sin lock-in contractual. Todo el conocimiento específico de IDEM (URLs, nombre de capa `VPLA_V_CLASIFICACION_REF_25`, el esquema completo de 14 campos, el hallazgo de que `CQL_FILTER` funciona pero `BBOX` es el método correcto para este caso de uso, el hallazgo de que no hay distinción observable entre "fuera de cobertura" y "hueco real") vive exclusivamente en `adapters/idem/`; `domain/`, `ports/`, `application/` y `cli/`/`api/` no saben que el proveedor es IDEM — el port y la entidad están nombrados por capacidad (`LandClassificationPort`/`LandClassification`), no por proveedor, dejando abierta la puerta a que un futuro adapter de otra fuente de planeamiento (otro IDEM autonómico, un WFS municipal, o un proveedor comercial de datos urbanísticos) implemente el mismo port. El principal coste de sustituir IDEM no es contractual sino de verificación: volver a confirmar esquema/CRS/comportamiento de filtro espacial contra la red real y regrabar fixtures, igual que ya ha costado cuatro veces en este proyecto (Catastro, Sentinel-2, BOE, BOCM, y ahora IDEM). No aplica coste de licencia todavía: `Provenance.license` para IDEM sigue en `asumido` (pendiente de confirmación textual, igual que ya estaba antes de esta historia) — no se resuelve aquí, tal como la propia historia deja explícito en su "Fuera de alcance".
