# ADR 0028 — Capa interna de caminos de Catastro: marca de redistribución en Provenance, caché cruda inmutable y teselado del término

- Estado: aceptada
- Fecha: 2026-11-25
- Historia: #29 (hijas #33, #34 y #37)

## Contexto

La feature #10 necesita, por municipio, los caminos que Catastro marca como parcela propia con número ≥ 9000 y subparcela de clase `VT` ("vía de comunicación de dominio público"), para compararlos con las demás fuentes (#13). Tres condiciones de partida, todas en `REGISTRY.md`:

1. La licencia INSPIRE de Catastro (v1.0, julio de 2016) prohíbe difundir la información original sin transformarla. La capa solo puede ser interna, y ese carácter tiene que ir en el dato, no en la memoria de quien lo usa.
2. El WFS de parcelas no filtra por atributo y limita cada `GetFeature` a cerca de 1 km² (1000×1000 m funciona, 1200×1200 m no). Un término municipal necesita cientos de peticiones.
3. El WFS no trae el uso. La clase `VT` sale de `Consulta_DNPPP`, una petición por parcela.

Hasta ahora ningún dato del proyecto se publicaba, así que nada distinguía lo publicable de lo interno. Tampoco había caché: cada fuente se consultaba bajo petición (lecciones del ciclo 0006-0010: caché diferida hasta que haya un consumidor entre ejecuciones). El procesamiento por lotes del ADR 0021 es ese consumidor.

## Decisión

1. **Marca de redistribución en `Provenance`.** `domain.provenance.Redistribution` (`INTERNAL_ONLY`, `PUBLIC`) y el campo `Provenance.redistribution`, con valor por defecto `INTERNAL_ONLY`. Publicar exige marcar `PUBLIC` explícitamente en el adapter, junto a la licencia citada en `REGISTRY.md`. La redistribución es una propiedad de la fuente y su licencia, igual que el resto de `Provenance`.
2. **Una sola puerta hacia lo público.** `domain.publication.PublishableLayer` valida al construirse que todos sus elementos tienen `provenance.redistribution == PUBLIC` y, si no, lanza `NotRedistributableError`. Todo port de exportación pública futuro (visor, épica #6) recibe `PublishableLayer` y nada más. Una entidad que combine fuentes pone en `provenance` la más restrictiva.
3. **Entidad `CadastralRoad`** (`domain/cadastral_road.py`), que **impide** en `__post_init__` una procedencia distinta de `INTERNAL_ONLY` y un `srid` distinto de 25830. Agregado `CadastralRoadLayer`, con contadores (teselas, parcelas vistas, candidatas, excluidas con su clase, sin clasificar) para que la capa explique qué dejó fuera.
4. **Dos ports por capacidad**, de un método cada uno (mismo criterio que el ADR 0002): `ParcelsInAreaPort.get_parcels_in_bbox(bbox) -> list[Parcel]` y `RuralParcelLandUsePort.get_land_use(reference) -> RuralParcelLandUse`. Teselado, deduplicación, filtro por municipio, filtro ≥ 9000 y regla `VT` van en dominio y aplicación (`BuildCadastralRoadLayerUseCase`). El adapter solo habla con Catastro.
5. **Teselado en dominio**: `domain.geometry.tile_bbox(bbox, side_m)`, teselas contiguas sin solape. El lado (900 m) es una constante del adapter de Catastro que inyecta el composition root. La deduplicación es por referencia catastral y gana la primera tesela, porque el WFS devuelve la geometría completa de toda parcela que toca el bbox (verificado con dos teselas reales en #37).
6. **Fallar en voz alta ante respuestas incompletas**: `AreaQueryLimitExceededError` y `TruncatedAreaQueryError` (`numberReturned < numberMatched`) en vez de devolver una lista parcial. Una DNPPP sin datos (`ParcelNotFoundError`) no aborta el lote: la parcela queda en `unclassified`.
7. **Caché cruda genérica e inmutable** en `adapters/raw_cache/` (`CachedRawFetcher`): una entrada por petición en `data/raw/<proveedor>/`, con cuerpo y sidecar (URL, parámetros, fecha de descarga real, sha256). Nunca se sobrescribe. Se valida antes de escribir para no cachear errores. Pausa de cortesía entre peticiones reales. Modo sin red que falla ante un fallo de caché. La fecha de `Provenance` sale del sidecar, así que repetir no cambia el resultado.
8. **Solo anillos exteriores** en el parser GML de Catastro, igual que IDEM (ADR 0011) y Red Natura 2000 (ADR 0015). Corrige que `_rings_from_feature` convirtiera los huecos en anillos exteriores.
9. **No se persiste la capa derivada** ni se toca PostGIS: se regenera desde la caché sin red cuando la necesite la comparación (#13).
10. **Punto de entrada**: subcomando `catastro-caminos` de la CLI, que recibe el bbox del término. Nada en `api/`.

### Umbrales y criterios de producto (a revisar con el fundador si hace falta)

- Una parcela ≥ 9000 cuenta como camino si **al menos una** de sus subparcelas es `VT`. Las clases de todas sus subparcelas se guardan en `land_use_classes` para que la comparación vea los casos mixtos (p. ej. `VT` + `HG`).
- `area_m2` es el `areaValue` del WFS, no la superficie de la subparcela de DNPPP (difieren: 8595 frente a 8604 m² en `REFCAT-RETIRADA`).
- Teselas de 900 m y 1 s de pausa entre peticiones reales.

## Consecuencias

- Toda `Provenance` existente pasa a ser `INTERNAL_ONLY` por defecto. Hoy no hay ningún exportador público, así que no cambia nada visible. #22 (vías pecuarias) e IGN tendrán que marcar `PUBLIC` explícitamente.
- La regla de `CLAUDE.md` "una capa solo se publica en el mapa si su licencia permite redistribución" pasa a cumplirse por tipo (`PublishableLayer`), no solo por revisión.
- `adapters/raw_cache/` está disponible para IDEM (#23) y las demás fuentes por lotes.
- La primera pasada de un municipio cuesta cientos de peticiones, de 10 a 20 minutos con la pausa de 1 s; las siguientes, ninguna. Coste monetario cero.
- El código de municipio de la referencia es el de Catastro, que no siempre coincide con el INE. Solo Colmenar (28043) está verificado.
- Publicar algo derivado de esta capa sigue siendo una decisión abierta del fundador (`docs/vision.md`): si un trazado inferido cuenta como "transformación" según la licencia. Esta decisión no la toma.
- Los casos con varias partes y huecos se cubren con un test explícito (lecciones 0002, 0011, 0015).
