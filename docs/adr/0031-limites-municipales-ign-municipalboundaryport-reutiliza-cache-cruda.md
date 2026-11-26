# ADR 0031 — Límites municipales del IGN tras un port y reutilización de la caché cruda

- Estado: aceptada
- Fecha: 2026-11-26
- Historia: #35 (hija A de #23; la hija B es #36)

## Contexto

La capa de vías pecuarias por municipio (#23) necesita el término de cada uno de los 7 municipios del ámbito. El límite de referencia del proyecto es el del IGN (unidades administrativas INSPIRE, `CC BY 4.0 ign.es`, ya usado para fijar el ámbito). Hace falta tenerlo en EPSG:25830, con procedencia, y poder regenerarlo sin red con el mismo resultado.

El diseño de #23 proponía una `RawResponseCache` nueva. Antes de que esta historia se desarrollara, la historia #34 fusionó `adapters/raw_cache/` (`CachedRawFetcher`), que cubre lo mismo: caché inmutable en `data/raw/`, modo sin red, `retrieved_at` de la descarga original y un hook `validate` previo a escribir.

## Decisión

1. **`MunicipalBoundaryPort.get_municipal_boundaries(ine_codes) -> list[MunicipalBoundary]`** (`ports/municipal_boundary.py`). Devuelve uno por código, en el orden pedido, en EPSG:25830. Si falta alguno lanza `MunicipalBoundaryNotFoundError` con los que faltan; nunca una lista parcial. `MunicipalBoundary` (`domain/municipality.py`): `ine_code`, `name`, `geometry`, `provenance`.
2. **Adapter `adapters/ign_admin_units/`** (`client.py`, `parsing.py`, `adapter.py`). Pide por bbox en EPSG:4258 (inyectado por constructor, orden lat, lon) y filtra en el cliente: no se ha verificado que el servicio filtre por atributo (lección de Catastro). Nivel `4thOrder`; INE = 5 últimos dígitos de `nationalCode`. Un `gml:interior` en un municipio pedido es un error (`MunicipalBoundaryUnusableError`), no se descarta: un enclave cambiaría la asignación.
3. **Reproyección con `pyproj`** (ya dependencia, ADR 0007): `Transformer.from_crs("EPSG:4258", "EPSG:25830")` **sin** `always_xy`, alimentado con `(lat, lon)`, un único transformer por llamada. Así los vértices que dos términos comparten en 4258 siguen siendo idénticos en 25830 y la partición no deja huecos ni solapes.
4. **Se reutiliza `CachedRawFetcher` de #34**; no se crea otra caché. El adapter lo recibe opcional por constructor. Sin él, descarga directamente y fecha con un reloj inyectable. La guarda de truncado se pasa como `validate`, de modo que una respuesta incompleta no llega a la caché inmutable.
5. **Guarda de truncado**: `numberMatched` distinto del número de features parseadas (todas, de cualquier nivel) → `IncompleteWfsResponseError`. Si el atributo no existe o no es numérico, no se exige.
6. **Procedencia**: `Provenance(source="ign_unidades_administrativas", url=<URL completa con query, la de la caché>, retrieved_at=<fecha de la descarga original>, license="CC BY 4.0 ign.es")`. `redistribution` queda en su valor por defecto (`INTERNAL_ONLY`): publicar es de la historia del visor, no de esta.
7. **Errores**: `MunicipalBoundaryNotFoundError`, `IncompleteWfsResponseError` y `MunicipalBoundaryUnusableError` en `ports/errors.py`. `RawCacheMissError` ya existe en `adapters/raw_cache` (#34) y no se duplica: lo captura el composition root, que puede importar adapters.

## Alternativas descartadas

- **Una `RawResponseCache` propia** (el diseño original de #23): duplicaría #34.
- **Filtrar por atributo en el servidor** (`CQL_FILTER`/`Filter`): no verificado para este WFS; la lección de Catastro obliga a verificarlo antes de fiarse.
- **`always_xy=True` con `(lon, lat)`**: equivalente, pero el orden de autoridad evita invertirlo a mano y deja claro el contrato con `posList`.

## Consecuencias

- Los límites son oficiales del IGN, no linde catastral: ambos no coinciden (REGISTRY.md, 7 de 72 vértices de una parcela de Villaconejos caen fuera de su término). Nadie debe usar el bbox de una parcela como prueba de pertenencia a un término.
- La respuesta completa pesa ~27 MB y se cachea una vez en `data/raw/` (fuera de git).
- Coste recurrente: cero. Un servicio público gratuito.
