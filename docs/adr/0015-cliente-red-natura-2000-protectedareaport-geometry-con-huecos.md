# ADR 0015 — Cliente de Red Natura 2000: `ProtectedAreaPort`, reutiliza `Geometry` descartando anillos interiores (mismo patrón que IDEM/`UsoDelSuelo`, no el de vías pecuarias)

- Estado: aceptada
- Fecha: 2026-10-16

## Contexto

La historia 0015 partía de un hallazgo de pasada de la historia 0014 (`Zonas:IDEM_MA_RED_NATURA_PLAN`, mismo workspace `Zonas` del GeoServer de IDEM ya usado para vías pecuarias), sin verificar en profundidad. El Bloque 1 (detalle completo en `src/parcel_intel/sources/REGISTRY.md`, sección "Red Natura 2000 y espacios protegidos — IDEM, Comunidad de Madrid") confirma:

1. **Es de verdad la Red Natura 2000 oficial, con evidencia textual real, no solo por el nombre de la capa.** El `Title` del `GetCapabilities` del WMS dice literalmente *"Planes de Gestión de Espacios Protegidos Red Natura 2000 de la Comunidad de Madrid"*; los valores reales del campo `DS_PLAN` citan explícitamente ZEC y ZEPA (p. ej. *"Plan de Gestión de las Cuencas de los ríos Jarama y Henares (ZEC) y de las Estepas Cerealistas de los ríos Jarama y Henares (ZEPA)"*).
2. **Alcance real: zonificación de planes de gestión regionales, no el límite oficial de cada sitio Natura 2000 individual con su código EU (`ES3XXXXXX`).** El esquema (`CD_PLAN`/`DS_PLAN`/`CD_ZONA`/`DS_ZONA`) modela el plan y su sub-zonificación interna, no el sitio protegido individual — mismo tipo de distinción de alcance ya documentada para cauces (eje real vs. deslinde legal del DPH, ADR 0012) y vías pecuarias (anchura real vs. anchura legal, ADR 0014).
3. **Las tres geometrías de prueba (dos parcelas rústicas del MVP y la vivienda real del fundador, `9900204ZZ0000S0001OK`) caen dentro del mismo plan (`CD_PLAN="SE"`), en su zona de menor restricción (`CD_ZONA="X"`, "sin zonificación específica necesaria")** — resultado real, no forzado: todo el territorio de referencia del MVP está dentro del área de gestión Red Natura 2000 regional, pero no en una zona de conservación prioritaria.
4. **La geometría real SÍ tiene anillos interiores (huecos): 5 `gml:Polygon`/`gml:surfaceMember` y 2 `gml:interior` reales en el único feature de prueba**, confirmado contando explícitamente las etiquetas (no solo "líneas que las contienen" — el XML real viene minificado en una sola línea; un primer conteo con `grep -c` sin `-o` dio un falso "sin huecos", corregido con `grep -o ... | wc -l`, la misma disciplina que ya exigió la lección de la historia 0011). **Esto contradice la expectativa inicial** (fijada por analogía con vías pecuarias, el "vecino" más reciente del mismo workspace, que resultó no tener huecos) — confirma la lección ya registrada tras la historia 0014: cada fuente geoespacial se verifica por sí misma, ni siquiera compartir servidor y workspace garantiza la misma forma de geometría.
5. **Fuente complementaria del Ministerio: inconclusa, no descartada ni confirmada.** El gateway legacy de MITECO (`wms.mapama.gob.es`) repite el mismo `NullReferenceException` sistémico ya confirmado en la historia 0012 (bloqueado). El catálogo CKAN de MITECO, que sí funcionó en la historia 0012, dio un fallo de conexión TLS real en esta sesión (3 intentos) — documentado honestamente como intento sin resultado concluyente, no como servicio roto.

`domain/geometry.py` ya tiene `Geometry` (anillos exteriores, multi-parte, descarta huecos — patrón ya usado por IDEM/`UsoDelSuelo`, ADR 0011) y `bbox_with_margin`/`EmptyGeometryError`. No hace falta ningún tipo nuevo.

## Decisión

**1. Un único port, `ProtectedAreaPort`, en `ports/protected_area.py`.** Mismo criterio que `LivestockTrailPort` (ADR 0014): toda la fuente real es una única forma de dato (lista de polígonos con atributos de plan/zona) para un único concepto de negocio — no hace falta dividir como DPH (ADR 0012).

```python
# ports/protected_area.py
class ProtectedAreaPort(Protocol):
    """Capacidad: zonas de planes de gestión de espacios protegidos Red
    Natura 2000 que intersectan el entorno (bbox + margen) de una
    geometría."""

    def get_nearby_protected_areas(
        self, geometry: Geometry, margin_m: float
    ) -> list[ProtectedArea]:
        """Lista vacía si ningún plan está dentro del bbox+margen. Si el
        bbox intersecta varias zonas de planes distintos, se devuelven
        TODAS — decidir cuál aplica a una regla de negocio futura no es
        tarea de este cliente."""
        ...
```

**2. Entidad `ProtectedArea`, en `domain/protected_area.py`, con los campos reales confirmados — sin inventar un código de sitio EU que la fuente no tiene:**

```python
@dataclass(frozen=True)
class ProtectedArea:
    """Zona de un plan de gestión de espacios protegidos Red Natura 2000
    (Comunidad de Madrid) — NO el límite oficial de un sitio Natura 2000
    individual con su código EU (ES3XXXXXX): esta fuente modela la
    zonificación de planes de gestión regionales, que pueden agrupar
    varios sitios ZEC/ZEPA distintos bajo un único plan territorial (ver
    REGISTRY.md, hallazgo 2)."""

    plan_code: str  # CD_PLAN, p. ej. "SE"
    plan_name: str  # DS_PLAN, texto libre real que cita ZEC/ZEPA
    zone_code: str  # CD_ZONA, p. ej. "X", "A"
    zone_name: str  # DS_ZONA, p. ej. "Zona A: Conservación Prioritaria"
    geometry: Geometry
    provenance: Provenance
```

**3. `ProtectedArea.geometry` reutiliza `domain.geometry.Geometry`, pero el parser descarta anillos interiores — mismo patrón que `adapters/idem/parsing.py` (ADR 0011), NO el de `adapters/livestock_trails/parsing.py` (ADR 0014, que no necesitó la guarda porque esa fuente no tiene huecos reales).** Confirmado real (REGISTRY.md, hallazgo 4): 2 `gml:interior` reales en el feature de prueba. El parser toma solo `gml:exterior` (técnica ya establecida: `feature.iter(f"{{{GML_NS}}}exterior")`, cada uno con su propio `.//posList`), descartando los huecos — mismo criterio exacto que IDEM/`UsoDelSuelo`: tratar cada `posList` (exterior o interior) como un anillo exterior más rellenaría visualmente los huecos reales.

**4. Sin excepción nueva en `ports/errors.py` — "sin plan de gestión cerca" es una lista vacía, nunca una excepción.** A diferencia de `LandClassificationPort` (ADR 0011, donde toda parcela de la Comunidad de Madrid tiene alguna clasificación de suelo), no hay garantía de que toda parcela esté dentro de un plan de gestión Red Natura 2000 — de hecho el Bloque 1 no probó ninguna geometría fuera de esa cobertura, así que no hay evidencia de que sea el caso mayoritario ni el minoritario. Se aplica el mismo criterio por defecto que `WatercoursePort`/`LivestockTrailPort` (lista vacía, no excepción): es la opción más segura cuando la fuente no garantiza cobertura universal, documentado así para revisar si una futura verificación confirma que "sin plan cerca" es raro o común.

**5. Adapter en `adapters/protected_areas/` (`client.py`, `parsing.py`, `adapter.py`), seam de red propio (mismo contrato `(url, params) -> bytes` GET+KVP que IDEM/vías pecuarias, redefinido, no importado de otro adapter).** `WFS_URL = "https://idem.comunidad.madrid/geoidem/Zonas/wfs"` (mismo servidor y workspace que vías pecuarias, pero seam propio — mismo precedente ya fijado en ADR 0011/0012/0014: ningún adapter de este proyecto importa de otro, aunque compartan servidor). `_LAYER_NAME = "IDEM_MA_RED_NATURA_PLAN"`. `DEFAULT_MARGIN_M = 2.0` (mismo criterio que el resto de fuentes vectoriales de alta precisión de este proyecto: salvaguarda de punto flotante, no un umbral de negocio).

**6. `Provenance.source = "idem"` (mismo organismo que `LandClassificationPort`/`LivestockTrailPort`, workspace/capa distintos reflejados en `url`).**

## Alternativas consideradas

- **Asumir que, como vías pecuarias (mismo workspace, mismo patrón de descubrimiento), esta fuente tampoco tiene anillos interiores y usar el parser simple sin guarda de huecos**: rechazada con evidencia real en contra (2 `gml:interior` reales confirmados) — habría repetido, de forma evitable, la misma lección ya aprendida y documentada tras la historia 0011. Verificado explícitamente antes de escribir el parser, no después.
- **Modelar un código de sitio Natura 2000 oficial (`ES3XXXXXX`) en la entidad, derivándolo o inventándolo a partir de `CD_PLAN`/`DS_PLAN`**: rechazada. La fuente real no tiene ese campo; derivarlo sería afirmar una precisión que el dato no tiene (mismo criterio que vías pecuarias rechazó derivar una "anchura legal" del área/longitud real, ADR 0014).
- **Dos ports separados para "plan" y "zona dentro del plan"**: rechazada. Son parte del mismo feature real (un único `wfs:member` trae ambos pares de campos a la vez) — no hay dos formas de dato incompatibles como sí las hubo entre cauces y peligrosidad por inundación (ADR 0012).
- **Excepción `NoProtectedAreaFoundError` para "sin plan cerca", igual que `LandClassificationPort`**: rechazada por falta de evidencia de que sea el caso excepcional — a diferencia de la clasificación de suelo (donde se confirmó que *toda* parcela de la Comunidad de Madrid tiene alguna), el Bloque 1 de esta historia no probó ninguna geometría sin resultado, así que no hay base para asumir cobertura universal.

## Consecuencias

- Nuevo `domain/protected_area.py` (`ProtectedArea`). Sin cambios a `domain/geometry.py`.
- Nuevo `ports/protected_area.py` (`ProtectedAreaPort`, un método). `ports/errors.py` no gana ninguna excepción nueva.
- Nuevo `adapters/protected_areas/` (`client.py`, `parsing.py` con guarda de anillos interiores, `adapter.py` con `ProtectedAreaAdapter`, `DEFAULT_MARGIN_M = 2.0`).
- Riesgo residual explícito: esta fuente identifica el plan de gestión aplicable y su zonificación interna, no el sitio Natura 2000 individual con su código EU oficial — cualquier motor de reglas futuro que necesite citar el código EU de un sitio concreto debe decidir si esto es suficiente o si hace falta una fuente complementaria (candidata: resolver el fallo TLS del catálogo CKAN de MITECO en una sesión futura, o el propio Ministerio con otro método).
- Riesgo residual compartido con el resto de adapters del proyecto (no corregido aquí): `Provenance.url` se construye concatenando parámetros sin `urlencode`.
- **Coste de salida del proveedor:** bajo, mismo proveedor (IDEM) ya documentado en ADR 0011/0014. El port/entidad nombrados por capacidad dejan abierta la puerta a un adapter futuro de otra fuente (p. ej. límites oficiales de sitios Natura 2000 si se resuelve la fuente complementaria del Ministerio).
