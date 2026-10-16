# ADR 0014 — Cliente de vías pecuarias: `LivestockTrailPort`, reutiliza `Geometry` sin cambios, sin campo de anchura legal

- Estado: aceptada
- Fecha: 2026-10-16

## Contexto

La historia 0014 partía de territorio sin ninguna verificación previa (como DPH antes de la historia 0012), pero con un punto de partida más vago que éste: ninguna pista textual concreta en `docs/vision.md` más allá de "cartografía autonómica, cobertura desigual". El Bloque 1 (detalle completo en `src/parcel_intel/sources/REGISTRY.md`, sección "Vías pecuarias — IDEM, Comunidad de Madrid") encontró un resultado limpio y positivo en la primera de las tres pistas propuestas por la historia, sin necesidad de probar las otras dos (MITECO CKAN, `datos.comunidad.madrid`):

1. **No existe ningún workspace llamado `ViasPecuarias` o `VP`** (los dos nombres plausibles que la historia proponía probar) bajo el GeoServer de IDEM. El nombre real del workspace es `Zonas` — encontrado pidiendo el `GetCapabilities` **global** del servidor (`.../geoidem/ows?service=wfs&request=GetCapabilities`, sin fijar workspace en la ruta), que lista las capas de todos los workspaces a la vez, y filtrando por patrón de texto. Confirma, una vez más en este proyecto, la lección ya registrada tras la historia 0001: nunca adivinar un nombre de recurso sin una petición real que lo confirme — aquí ni siquiera el nombre del *workspace* (no solo el de la capa) coincidía con lo anticipado.
2. **La capa real, `Zonas:IDEM_MA_VIAS_PECUARIAS`, modela cada tramo/elemento como un polígono real (franja con área), nunca como una línea de eje.** Geometría `gml:Polygon` (o `gml:MultiSurface` en el único caso real multi-parte encontrado, `"Vereda de la Mesa"`), siempre con `gml:exterior` únicamente — **cero anillos interiores observados**, a diferencia de IDEM/`UsoDelSuelo` (historia 0011, que sí tiene huecos reales). Esto es justo el caso contrario al de los cursos de agua (historia 0012, `LineString`, llevó a crear `LineGeometry`): aquí la geometría real encaja exactamente con `domain.geometry.Geometry` tal como ya existe, sin ningún cambio.
3. **No existe ningún campo de "anchura legal" en el esquema real.** `DescribeFeatureType` confirma 8 campos (`CD_MUNI`, `DS_MUNI`, `DS_NOMBRE`, `CD_VP`, `DS_TRAMO`, `DS_TIPO`, `NM_LONG`, `NM_AREA`) + geometría — ninguno es una anchura legal en metros. `NM_AREA`/`NM_LONG` permiten derivar una anchura media real del polígono cartografiado, que además resulta sistemáticamente **menor** que los mínimos legales de referencia citados por la propia historia (p. ej. veredas reales ~9-12 m frente al mínimo legal de 20,89 m) — hallazgo documentado, no resuelto, en `REGISTRY.md`.
4. **El campo `DS_TIPO` (tipo de vía) tiene más valores reales que los cuatro tipos legales anticipados por la historia.** Confirmado: `"Cañada"`, `"Vereda"`, `"Colada"` (en Colmenar/Villaconejos) y `"Cordel"` (confirmado real en otros municipios de la Comunidad de Madrid, 301 features). Pero también `"Abrevadero"`, `"Descansadero"` y `"Descansadero-Abrevadero"` — elementos anejos a la red (puntos de descanso/abrevado de ganado), no un tipo de vía pecuaria en sí, geolocalizados con la misma estructura de campos.
5. **Las dos parcelas de referencia del MVP no tienen ninguna vía pecuaria cerca** (bbox real, margen 2 m, `numberMatched=0` en ambas) — confirmado como resultado real y no un artefacto de margen insuficiente (el tramo más cercano a cada una está a ≈2,2-2,4 km). El servicio sí tiene datos reales ricos en los municipios completos (15 tramos en Colmenar de Oreja, 2 en Villaconejos, 1694 en toda la Comunidad de Madrid).

`domain/geometry.py` ya tiene `Geometry` (anillos exteriores, multi-parte, sin huecos, srid), `LineGeometry` (línea abierta, ADR 0012) y `bbox_with_margin`/`EmptyGeometryError`. Ninguno de los dos necesita cambios para esta fuente.

## Decisión

**1. Un único port, `LivestockTrailPort`, en `ports/livestock_trail.py` — no hace falta dividir en dos como pasó con DPH (ADR 0012).** A diferencia de cauces/inundación (dos formas de dato incompatibles: lista de líneas con atributos vs. muestras puntuales de un raster), aquí toda la fuente real es una única forma de dato (lista de polígonos con atributos) para un único concepto de negocio. Traducción elegida para "vía pecuaria": **"livestock trail"** (término administrativo claro en inglés, preferido sobre "drove road" por ser menos dialectal/británico y más reconocible fuera del Reino Unido) — responde la pregunta abierta de la historia sobre el nombre final.

```python
# ports/livestock_trail.py
class LivestockTrailPort(Protocol):
    """Capacidad: tramos de vía pecuaria (y elementos anejos reales como
    abrevaderos/descansaderos — ver domain.livestock_trail) que intersectan
    el entorno (bbox + margen) de una geometría."""

    def get_nearby_livestock_trails(
        self, geometry: Geometry, margin_m: float
    ) -> list[LivestockTrail]:
        """Lista vacía si ningún tramo está dentro del bbox+margen —
        resultado esperado y mayoritario, NO una excepción (mismo criterio
        que WatercoursePort, ADR 0012 — confirmado real que las dos
        parcelas del MVP, a ~2,2-2,4 km de la vía pecuaria más cercana, no
        son un caso aislado sino el caso normal de la mayoría de parcelas).
        Si el bbox intersecta varios tramos (p. ej. una cañada y una
        colada en el mismo entorno), se devuelven TODOS — decidir cuál
        aplica a una regla de negocio futura no es tarea de este cliente."""
        ...
```

**2. Entidad `LivestockTrail`, en `domain/livestock_trail.py`, sin campo de anchura legal — se expone `area_m2`/`length_m` en bruto, nunca una anchura derivada ni asumida.**

```python
@dataclass(frozen=True)
class LivestockTrail:
    """Tramo real de vía pecuaria o elemento anejo (abrevadero,
    descansadero), con la geometría de la franja/polígono ya cartografiada
    por IDEM (Comunidad de Madrid) — a diferencia de un curso de agua
    (historia 0012, línea de eje), esta fuente SÍ modela la anchura como
    área real, no como un valor escalar: `area_m2 / length_m` da una
    anchura media aproximada, pero NO es la anchura legal citada por la
    Ley 8/1998 de Vías Pecuarias (confirmado real: sistemáticamente menor
    que los mínimos legales — ver REGISTRY.md, hallazgo 2). No existe
    ningún campo de anchura legal en la fuente real; este tipo no inventa
    uno."""

    trail_type: str  # DS_TIPO: "Cañada"/"Cordel"/"Vereda"/"Colada", pero
                      # también "Abrevadero"/"Descansadero"/
                      # "Descansadero-Abrevadero" (confirmado real, no son
                      # vías pecuarias en sí — ver punto 3). Cadena libre,
                      # no enum: la fuente real ya tiene más valores que
                      # los cuatro anticipados por la historia, y no hay
                      # garantía de que la lista esté cerrada.
    name: str  # DS_NOMBRE, siempre poblado en los 17 features observados
    municipality_code: str  # CD_MUNI
    municipality_name: str  # DS_MUNI
    trail_code: str  # CD_VP
    length_m: float  # NM_LONG
    area_m2: float  # NM_AREA
    geometry: Geometry  # reutilizada sin cambios — ver punto 4
    provenance: Provenance
```

Se excluye `DS_TRAMO` (confirmado siempre `0` en los 17 features observados y en toda la Comunidad de Madrid — `CQL_FILTER=DS_TRAMO>0` da `numberMatched=0`; sin ningún uso real observado, mismo criterio selectivo que IDEM/ADR 0011 con campos poblados pero sin significado de negocio confirmado).

**3. `trail_type` no se filtra ni se restringe a los cuatro tipos legales — se incluyen `"Abrevadero"`/`"Descansadero"`/`"Descansadero-Abrevadero"` tal como vienen de la fuente real.** Alternativa rechazada: filtrar estos tres valores en el adapter para que el cliente "solo devuelva vías pecuarias de verdad". Se rechaza porque (a) decidir qué es y qué no es una vía pecuaria a efectos de una regla de afección futura es una decisión de negocio, no de este cliente de datos — el mismo criterio que ya fijó la historia en su "Fuera de alcance" para la anchura legal; (b) estos elementos siguen siendo del dominio público pecuario real, relevantes para cualquier regla futura sobre esa categoría más amplia; (c) filtrar en el adapter sin que el port lo documente explícitamente escondería una decisión de negocio dentro de una capa que no debería tomarlas, repitiendo el tipo de fuga que el ADR 0012 ya evitó para el margen por defecto. El docstring de `trail_type` deja la distinción explícita para que un consumidor futuro decida con conocimiento, no por descubrimiento accidental.

**4. `LivestockTrail.geometry` reutiliza `domain.geometry.Geometry` sin ningún cambio — no se crea ningún tipo de dominio nuevo.** Responde la pregunta abierta de la historia sobre la forma de la geometría: es un polígono real (franja con área, confirmado con `NM_AREA` poblado y geometría `gml:Polygon`/`gml:MultiSurface` real, nunca `LineString`), y además sin anillos interiores observados — el caso más simple de los tres ya vistos en este proyecto (Catastro: sin huecos, simple; IDEM/`UsoDelSuelo`: con huecos reales, ADR 0011; cauces: línea abierta, requirió `LineGeometry`, ADR 0012). El parser puede reutilizar literalmente el mismo patrón de `adapters/idem/parsing.py` (`feature.iter(f"{{{GML_NS}}}exterior")`, que ya recoge correctamente múltiples `gml:exterior` bajo un único `gml:MultiSurface`, como el caso real de `"Vereda de la Mesa"`), sin necesidad de descartar ningún anillo interior porque no existe ninguno en esta fuente — simplificación real, no asumida de antemano.

**5. Sin excepción nueva en `ports/errors.py` — "sin vía pecuaria cerca" es una lista vacía, nunca una excepción, mismo criterio que `WatercoursePort` (ADR 0012), no el de `LandClassificationPort` (ADR 0011).** Confirmado real con las dos parcelas del MVP: el caso "sin afección" es el resultado mayoritario esperado (tramo más cercano a ~2,2-2,4 km), no una anomalía — a diferencia de la clasificación de suelo de IDEM, donde toda parcela tiene necesariamente alguna clasificación.

**6. Adapter en `adapters/livestock_trails/` (`client.py`, `parsing.py`, `adapter.py`), seam de red propio (mismo contrato `(url, params) -> bytes` GET+KVP que IDEM/Catastro/PNOA, redefinido aquí y no importado de `adapters/idem/`, mismo precedente ya fijado en ADR 0011/0012).** `WFS_URL = "https://idem.comunidad.madrid/geoidem/Zonas/wfs"`, `_LAYER_NAME = "IDEM_MA_VIAS_PECUARIAS"`. `DEFAULT_MARGIN_M = 2.0` (mismo criterio que IDEM/`UsoDelSuelo` y cursos de agua: salvaguarda de punto flotante en el borde de una geometría vectorial de alta precisión, explícitamente **no** un umbral de negocio — cualquier regla futura de "a menos de N metros de una vía pecuaria" debe pasar su propio `margin_m`, no depender del default del adapter).

**7. `Provenance.source = "idem"` (no `"idem_vias_pecuarias"` ni similar) — mismo organismo y mismo servidor que `LandClassificationPort`, solo workspace distinto.** Si una futura historia necesita distinguir en el informe de dónde viene cada dato de IDEM, puede hacerlo por el campo `url` de `Provenance` (que sí difiere: `.../UsoDelSuelo/wfs` vs. `.../Zonas/wfs`), no por el nombre de la fuente.

## Alternativas consideradas

- **Derivar y exponer una `average_width_m: float` calculada (`area_m2 / length_m`) como campo de la entidad, en vez de solo `area_m2`/`length_m` en bruto**: rechazada. Aunque el cálculo es trivial y ya se hizo para el hallazgo de `REGISTRY.md`, exponerlo como campo de la entidad sugeriría al consumidor que es "la anchura" de la vía pecuaria, cuando el propio hallazgo real confirma que diverge sistemáticamente de la anchura legal — el riesgo de que un futuro motor de reglas use este valor derivado como si fuera la anchura legal (p. ej. para decidir si una construcción invade la vía pecuaria) es mayor que la comodidad de no tener que calcularlo en el consumidor. Se deja `area_m2`/`length_m` en bruto, exactamente como vienen del servidor, y el cálculo (si se necesita) queda para quien lo use, con el hallazgo ya documentado en `REGISTRY.md` para que no lo descubra de cero.
- **Filtrar `trail_type` en el adapter para excluir `"Abrevadero"`/`"Descansadero"`/`"Descansadero-Abrevadero"`**: rechazada (ver punto 3 de la Decisión) — decisión de negocio que no corresponde a este cliente.
- **Modelar `trail_type` como `Literal["Cañada", "Cordel", "Vereda", "Colada"]` o un `Enum` cerrado**: rechazada. La fuente real ya tiene siete valores distintos confirmados (cuatro legales + tres anejos), y no hay garantía de que sean los únicos — mismo criterio ya aplicado a `Watercourse.course_type`/`persistence` (cadenas libres, ADR 0012) en vez de enums cerrados sobre un campo de texto libre del proveedor.
- **Añadir el campo `DS_TRAMO` a la entidad "por si acaso se puebla en el futuro"**: rechazada, mismo criterio selectivo de siempre (ADR 0008, "no añadir campos sin consumidor real que los necesite") — confirmado explícitamente que está siempre a `0` en las 1694 features de toda la Comunidad de Madrid, no solo en las dos muestras del MVP.
- **Reutilizar el adapter de IDEM/`UsoDelSuelo` directamente (mismo `client.py`), ya que es literalmente el mismo servidor**: rechazada, mismo precedente que ADR 0011/0012 — ningún adapter de este proyecto importa de otro adapter, aunque el contrato HTTP sea idéntico; la duplicación del seam (unas pocas líneas) es preferible a crear un acoplamiento entre dos adapters que hoy coinciden por casualidad de infraestructura pero podrían divergir (p. ej. si IDEM migra `Zonas` a otro servidor y deja `UsoDelSuelo` donde está).

## Consecuencias

- Nuevo `domain/livestock_trail.py` (`LivestockTrail`). Sin cambios a `domain/geometry.py` — primera vez en este proyecto que una fuente geoespacial nueva no requiere ningún cambio ni verificación adicional sobre el tipo de geometría existente (a diferencia de IDEM/`UsoDelSuelo`, que forzó documentar la exclusión de huecos, y de cauces, que requirió `LineGeometry`).
- Nuevo `ports/livestock_trail.py` (`LivestockTrailPort`, un método). `ports/errors.py` no gana ninguna excepción nueva.
- Nuevo `adapters/livestock_trails/` (`client.py`, `parsing.py`, `adapter.py` con `LivestockTrailAdapter`, `DEFAULT_MARGIN_M = 2.0`).
- `src/parcel_intel/sources/REGISTRY.md` actualizado con la sección "Vías pecuarias — IDEM, Comunidad de Madrid", y fixtures reales nuevas en `tests/fixtures/livestock_trails/` (9 ficheros: `GetCapabilities` global del GeoServer que reveló el workspace `Zonas`, `DescribeFeatureType`, dos `GetFeature` por bbox de las parcelas del MVP sin afección, uno sin cobertura en Toledo, dos `GetFeature` por `CQL_FILTER` de municipio completo con los 17 tramos reales, una muestra de `DS_TIPO='Cordel'` de otro municipio, `GetCapabilities` del WMS del workspace `Zonas` con el `Abstract` que cita la Ley 8/1998).
- Riesgo residual explícito, señalado para no perderse: la anchura real derivable (`area_m2/length_m`) **no** es la anchura legal de referencia (Ley de Vías Pecuarias estatal/autonómica) — cualquier motor de reglas futuro que necesite comparar "¿esta construcción invade la anchura legal de la cañada?" debe decidir explícitamente si usa la anchura legal de referencia (un valor fijo por tipo, externo a esta fuente) o la anchura real cartografiada (`area_m2/length_m`, sistemáticamente menor, ya ocupada/reducida de facto) — no son intercambiables sin una decisión consciente, documentada aquí para que esa decisión futura no se tome por descubrimiento accidental.
- Riesgo residual compartido con el resto de adapters de este proyecto (no corregido aquí): `Provenance.url` se construye concatenando parámetros sin `urlencode`.
- Candidata explícita para una historia futura de descubrimiento, encontrada de pasada en esta misma pesquisa (igual que la historia 0011 encontró de pasada el patrón `VPLA_V_*` con versiones): `Zonas:IDEM_MA_RED_NATURA_PLAN` (Red Natura 2000), en el mismo workspace `Zonas`, mismo servidor — probablemente el mismo patrón de verificación de esta historia aplicaría casi sin cambios, pero no se investiga aquí (fuera de alcance explícito de la historia 0014).
- **Coste de salida del proveedor (IDEM / Comunidad de Madrid, mismo proveedor que `LandClassificationPort`):** bajo, mismo patrón ya documentado en ADR 0011. Servicio público sin autenticación ni facturación. Todo el conocimiento específico de esta capa (URL del workspace `Zonas`, nombre de la capa `IDEM_MA_VIAS_PECUARIAS`, el esquema de 8 campos, la ausencia de anchura legal, los tres valores anejos de `DS_TIPO`) vive exclusivamente en `adapters/livestock_trails/`; `domain/`, `ports/`, `application/` y `cli/`/`api/` no saben que el proveedor es IDEM — el port y la entidad están nombrados por capacidad (`LivestockTrailPort`/`LivestockTrail`), dejando abierta la puerta a que un futuro adapter de otra fuente (p. ej. si el Ministerio publica su propio inventario de vías pecuarias estatales de la red general) implemente el mismo port. El coste principal de sustituir el proveedor es, como siempre en este proyecto, de verificación (volver a confirmar esquema/CRS/comportamiento contra la red real), no de dinero ni de contrato. `Provenance.license` queda `asumido` (ninguna licencia citada textualmente para esta capa concreta, a diferencia de cursos de agua/IDEE que sí citan una URL de licencia) — no se resuelve aquí.
