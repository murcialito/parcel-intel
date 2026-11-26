# ADR 0032 — Capa de vías pecuarias por municipio: recorte con shapely tras un port

- Estado: aceptada
- Fecha: 2026-11-26
- Historia: #36 (hija B de #23; la hija A es #35, ADR 0031)

## Contexto

El primer hito (ADR 0021) necesita, para cada uno de los 7 municipios del ámbito, las vías pecuarias oficiales que pasan por su término. IDEM (`Zonas:IDEM_MA_VIAS_PECUARIAS`, ADR 0014) ya parte las vías por municipio con su propio `CD_MUNI`, pero el límite de referencia del proyecto es el del IGN (ADR 0031) y un tramo puede cruzar términos. Hace falta recortar geometría contra geometría, y el dominio solo puede usar la stdlib.

La caché cruda inmutable y los límites del IGN ya existen (#34, #35). Esta historia los reutiliza.

## Decisión

1. **`PolygonClippingPort.clip(subject, boundary) -> Geometry`**, implementado con `shapely` en `adapters/shapely_geometry/`. `shapely` es dependencia nueva, solo la importa ese adapter y se prohíbe en el contrato de dominio (`forbidden_modules`). No es un proveedor de datos sino una librería de cálculo, por eso no exige un ADR de proveedor; este lo deja escrito. Un recorte a mano en `domain/` se descarta (lecciones 0001-0002: la geometría manual es donde aparecen los bugs multi-parte). `types-shapely` entra como dependencia de desarrollo para que `mypy` estricto siga en verde.
2. **Contrato del recorte**: srid distinto → `ValueError`; intersección vacía → `Geometry(rings=(), srid=…)`; se descartan las partes de dimensión < 2 (puntos y líneas de contacto en el borde); un resultado con huecos → `ClippedGeometryHasHolesError`, nunca descartados en silencio porque romperían la suma de áreas. Si la entrada no es válida, `shapely.make_valid` la repara y se registra en el log.
3. **`polygon_area(geometry)`** en `domain/geometry.py` (suma de |Gauss| por anillo; `rings=()` → 0.0). Reutiliza `ring_signed_area`.
4. **La capa guarda el tramo de IDEM intacto** (`ClippedLivestockTrail.source`) junto a la geometría recortada, `area_m2` y `share_of_source`. No se pisan `NM_AREA`/`NM_LONG` de IDEM. No depende de la conversión a `Trail` (#22): se hará al publicar con `replace(livestock_trail_to_trail(piece.source), geometry=piece.geometry, municipality_code=<INE de la pieza>)`.
5. **Un solo literal para el aviso**: `MunicipalLivestockTrailLayer.notice` usa `LIVESTOCK_TRAIL_CHARACTER` de `domain/livestock_trail.py` (#22). No se crea `LIVESTOCK_TRAIL_LAYER_NOTICE`.
6. **`BuildMunicipalLivestockTrailLayersUseCase(boundaries, trails, clipper).execute(ine_codes)`**: límites por el port del IGN; por cada uno, tramos con `LivestockTrailPort` y margen de bbox de 2,0 m (salvaguarda de coma flotante, ADR 0011/0014); recorte por tramo; las piezas vacías se omiten; orden `(trail_code, name, -area_m2)`. Un tramo que cruza dos términos sale en las dos capas, cada una con su parte. Comprueba srid 25830 en límites y tramos y no reproyecta.
7. **`LivestockTrailAdapter` gana `fetcher: CachedRawFetcher | None` y reloj inyectable.** Es la `CachedRawFetcher` de #34 y no la `RawResponseCache` que proponía el diseño de #23 (mismo criterio que el ADR 0031). Sin `fetcher` se comporta como antes. Rellena `license="CC BY 4.0 Comunidad de Madrid"` (`LIVESTOCK_TRAIL_LICENSE`, historia 0021), que ningún consumidor leía; y lanza `IncompleteWfsResponseError` si `numberMatched` no coincide con las features parseadas, también antes de entrar en la caché (`validate`).
8. **Composition root** en `cli/main.py`: subcomando `vias-pecuarias-municipios [--sin-red] [--cache data/raw]`. El ámbito vive en `cli/` (`AMBITO_HITO_INE`, `AMBITO_HITO_BBOX_ETRS89`). `build_municipal_layers` permite inyectar los getters de red y el reloj en los tests. No persiste ni escribe nada publicable.

### Umbrales de producto, a revisar con el fundador (no son arquitectura)

- **Astillas**: no se filtra ninguna pieza por tamaño. Con las 7 respuestas reales (REGISTRY.md, "Capa de vías pecuarias por municipio") hay 79 piezas y 12 son menores de 1 m². Si una pieza así cuenta como "la vía pasa por aquí" es una decisión de publicación, para la historia del visor.
- **Aviso de la capa**: el texto viene de la historia; su redacción pública final es del fundador (#16).

## Alternativas descartadas

- **Asignar cada tramo a su `CD_MUNI` sin recortar**: deja fuera lo que entra en el término según el IGN.
- **PostGIS `ST_Intersection`**: añade un servicio a un proceso por lotes que no lo necesita (ADR 0021).
- **Filtrar astillas por umbral de área ya**: umbral de producto sin datos; se pospone.
- **Depender de la entidad `Trail`**: el recorte no la necesita.

## Consecuencias

- Primera dependencia de geometría computacional. Cualquier operación difícil futura (buffer, unión, diferencia) se añade como método de un port de capacidad implementado en `adapters/shapely_geometry/`, nunca en `domain/`.
- Las capas tienen astillas: nadie debe publicarlas sin decidir antes el umbral.
- Los ficheros de `data/raw/` ya cacheados de IDEM por bbox de parcela no cambian; el campo `license` pasa a valer `CC BY 4.0 Comunidad de Madrid` en toda llamada al adapter.
- Coste recurrente: cero. Dos servicios públicos gratuitos y ~30 MB en `data/raw/`.
