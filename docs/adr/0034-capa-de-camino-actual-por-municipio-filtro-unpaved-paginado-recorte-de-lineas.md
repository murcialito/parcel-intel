# ADR 0034 — Capa de camino actual por municipio: filtro `unpaved` en el servidor, paginado y recorte de líneas

- Estado: aceptada
- Fecha: 2026-11-26
- Historia: #27 (feature #12; sigue el patrón de #36, ADR 0032)

## Contexto

La comparación de trazados (#15, ADR 0030) necesita, por municipio, el "camino actual": los tramos sin asfaltar de la red de transporte del IGN (`roadlink`, adapter de #25) recortados al término. Los límites (#35, ADR 0031), la caché cruda (#34) y el recorte de polígonos con `shapely` (#36, ADR 0032) ya existen. La historia no traía decisión nueva, pero al pedir un término entero apareció un problema que el diseño no veía: `roadlink` devuelve **miles** de tramos por término, casi todos asfaltados, y la consulta del adapter de #25 (una página de 500) los truncaba.

## Decisión

1. **El adapter pide solo `unpaved` al servidor y pagina.** `filter=surfacecategory='unpaved'` (CQL por defecto, verificado el 2026-11-26) más `offset` hasta reunir `numberMatched`. Sin filtro, la primera página de 500 de Valdelaguna traía 98 caminos de los 552 reales. El filtro por superficie en el cliente se conserva como segunda barrera. `get_nearby_unpaved_roads` mantiene su contrato; la consulta de una ventana pequeña sigue siendo una sola petición. Tope de 200 páginas por consulta como salvaguarda.
2. **`RoadSegmentPort.query_unpaved_roads -> RoadQueryResult(segments, provenance)`.** La procedencia de la consulta existe aunque no haya tramos: un municipio sin caminos (CA3) debe producir un fichero válido con su procedencia. `get_nearby_unpaved_roads` delega en él.
3. **`RoadNetworkAdapter` gana `fetcher: CachedRawFetcher | None` y reloj inyectable**, igual que `LivestockTrailAdapter` (ADR 0031/0032). Cada página se cachea de forma inmutable; `retrieved_at` es el de la primera descarga y la URL de procedencia es la de la primera página. Una respuesta ilegible no entra en la caché (`validate`). La `Provenance` del adapter pasa a `Redistribution.PUBLIC`: la licencia CC BY 4.0 la confirmó #24.
4. **`LineClippingPort.clip(LineGeometry, Geometry) -> MultiLineGeometry`** con `ShapelyLineClipper` en `adapters/shapely_geometry/`. Una línea que sale y vuelve a entrar da varias partes; los contactos de dimensión 0 se descartan. No se reutiliza `PolygonClippingPort`: la forma de entrada y de salida es otra (ADR 0012: no forzar líneas en tipos de superficie).
5. **`BuildMunicipalRoadLayersUseCase(boundaries, roads, clipper)`** devuelve un `MunicipalRoadLayerBatch(layers, failures)`. Cada municipio se genera aparte; cualquier excepción de uno (red, caché, srid) queda en `failures` con su INE, nombre y motivo, y los demás se generan (CA7). Se captura `Exception` a propósito: `application/` no puede importar los errores de la caché (viven en adapters) y lo que importa aquí es que el lote no se pare ni calle. El fallo de los límites (todos o ninguno, ADR 0031) sí aborta el lote.
6. **La pieza guarda el tramo del IGN intacto** (`ClippedRoadSegment.source`, con `fictitious` y `registered_at`) más la geometría recortada, `length_m` y `share_of_source`. Un tramo que cruza dos términos sale en las dos capas, cada una con su parte.
7. **Fichero por municipio** `data/derived/camino_actual/<ine>.geojson` en el formato común de #15: `FeatureCollection` con `crs` EPSG:25830; en la colección `fuente = "ign_red_transporte"`, `municipio`, `procedencia`, `atribucion` («Obra derivada de red de transporte IGN CC-BY 4.0 ign.es», texto del criterio CA4) y `aviso` («cartografía informativa»); por feature `id`, `geometry` (`LineString`, o `MultiLineString` si hay varias partes) y `properties` con `id_tramo`, `fecha_alta`, `fecha_dato`, `fictitious`, `longitud_m`, `parte_del_tramo` y `procedencia`. Serialización determinista (claves ordenadas, redondeo a 2 decimales solo al escribir, sin fecha de generación) y escritura atómica, en `adapters/road_layer_files/`.
8. **Composition root**: `cli/main.py`, subcomando `camino-actual-municipios [--sin-red] [--cache data/raw] [--salida data/derived/camino_actual]`. Sale con 1 si algún municipio falló, tras escribir los demás.

### Umbrales de producto, a revisar con el fundador

- **Texto de atribución**: el criterio fija la forma «Obra derivada de red de transporte IGN CC-BY 4.0 ign.es»; REGISTRY.md (#24) recomienda «Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional». Hay que unificarlas antes de publicar.
- **Ficticios**: casi todo el camino sin asfaltar del ámbito es `fictitious="true"` (REGISTRY.md, "Capa de camino actual por municipio"). Se conservan todos, con el indicador; si el visor los distingue o los oculta es decisión de publicación.
- **Astillas**: no se filtra ninguna pieza por tamaño (como en ADR 0032).

## Alternativas descartadas

- **Subir `limit` a 1000 o más**: el servidor lo admite, pero un término como Aranjuez trae 5.522 tramos sin asfaltar; el paginado es correcto para cualquier tamaño.
- **Pedir la red entera sin filtro y filtrar en el cliente**: 60 MB por pasada y, con el límite de página, perdería caminos sin avisar.
- **Reutilizar `PolygonClippingPort` envolviendo la línea en un polígono**: pierde la longitud y confunde superficie con eje.
- **Que el caso de uso escriba los ficheros**: la escritura es de adapter/composition root; el caso de uso queda sin E/S.

## Consecuencias

- Una pasada real (7 municipios) son ~30 peticiones de 1-2 MB; la caché cruda las guarda en `data/raw/` (fuera de git) y el resto se regenera sin red.
- Los fixtures de `tests/fixtures/road_network/` son recortes de respuestas reales (10-12 tramos por municipio, sin tocar su geometría); la respuesta completa pesa ~60 MB y no se versiona. El paginado real se cubre con respuestas sintéticas y con el criterio `[integración]` CA8.
- #15/#32 leen estos ficheros con su lector común; el campo `fuente` ya es el `SourceKind` de #22.
