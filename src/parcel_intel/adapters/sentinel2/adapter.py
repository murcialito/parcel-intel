import math
from datetime import UTC, date
from datetime import datetime as _datetime

import numpy as np
from pyproj import Transformer

from parcel_intel.adapters.sentinel2.client import (
    COLLECTION,
    STAC_SEARCH_URL,
    ContentLengthGetter,
    JsonPoster,
    RangedHttpGetter,
    default_content_length_getter,
    default_json_poster,
    default_ranged_http_getter,
)
from parcel_intel.adapters.sentinel2.parsing import (
    BandInfo,
    SceneCandidate,
    parse_stac_search_response,
)
from parcel_intel.adapters.sentinel2.raster import open_band, read_pixel_window
from parcel_intel.domain.geometry import BBox, Geometry, bbox_with_margin
from parcel_intel.domain.ndvi import Grid, NdviGrid
from parcel_intel.domain.provenance import Provenance
from parcel_intel.ports.errors import NoScenesAfterCloudFilterError

DEFAULT_MARGIN_M = 20.0
"""El doble del píxel nativo de Sentinel-2 (10 m): evita que el bbox, al
discretizarse a una rejilla de 10 m, redondee a cero celdas de margen extra
en algún borde según la alineación exacta de la geometría (ver ADR 0007).
No se comparte con PNOA (10 m, resolución submétrica)."""

_RESOLUTION_M = 10.0


def _today() -> date:
    return _datetime.now(tz=UTC).date()


def _bbox_to_wgs84(bbox: BBox, srid: int) -> tuple[float, float, float, float]:
    """La búsqueda STAC espera `bbox` en WGS84 (EPSG:4326), no en el CRS de
    almacenamiento del proyecto."""
    transformer = Transformer.from_crs(srid, 4326, always_xy=True)
    minx, miny, maxx, maxy = bbox
    lon1, lat1 = transformer.transform(minx, miny)
    lon2, lat2 = transformer.transform(maxx, maxy)
    return (min(lon1, lon2), min(lat1, lat2), max(lon1, lon2), max(lat1, lat2))


def _invert_affine(
    transform: tuple[float, float, float, float, float, float], x: float, y: float
) -> tuple[int, int]:
    """Invierte la transformación afín `proj:transform` de STAC (sin
    términos de rotación en los datos reales verificados en REGISTRY.md:
    `transform = [a, 0, c, 0, e, f]`) para obtener la celda de píxel
    (columna, fila) más cercana a un punto `(x, y)` del CRS nativo."""
    a, _b, c, _d, e, f = transform
    col = (x - c) / a
    row = (y - f) / e
    return round(col), round(row)


def _reflectance(dn: int, band: BandInfo) -> float | None:
    """`dn*scale + offset` puede salir negativo en píxeles oscuros (sombra,
    agua): ruido de la corrección atmosférica, no reflectancia real. Se
    acota a `[0, 1]` (único rango físicamente válido) antes de usarla en
    NDVI — sin esto, la fórmula deja de estar garantizada en `[-1, 1]`
    (verificado contra datos reales: sin acotar, aparecían NDVI de 7.6 y
    -4.8 en píxeles con reflectancia negativa)."""
    if dn == band["nodata"]:
        return None
    reflectance = dn * band["scale"] + band["offset"]
    return max(0.0, min(1.0, reflectance))


def _ndvi(red_refl: float | None, nir_refl: float | None) -> float:
    """`nan` si cualquiera de las dos bandas es `nodata` en ese píxel (ADR
    0007: las celdas sin dato deben excluirse del resultado, no confundirse
    con un NDVI real de 0.0 — `Grid` lo documenta explícitamente)."""
    if red_refl is None or nir_refl is None:
        return math.nan
    denom = nir_refl + red_refl
    if denom == 0:
        return math.nan
    return (nir_refl - red_refl) / denom


class Sentinel2Adapter:
    """Implementa `NdviSeriesPort` contra el catálogo STAC Earth Search
    (Element84) confirmado en `sources/REGISTRY.md`. Cliente aislado (ADR
    0007): no se conecta todavía a ningún caso de uso ni cachea resultados."""

    def __init__(
        self,
        json_poster: JsonPoster = default_json_poster,
        ranged_get: RangedHttpGetter = default_ranged_http_getter,
        content_length: ContentLengthGetter = default_content_length_getter,
    ) -> None:
        self._json_poster = json_poster
        self._ranged_get = ranged_get
        self._content_length = content_length

    def get_ndvi_series(
        self,
        geometry: Geometry,
        margin_m: float,
        start: date,
        end: date,
        max_cloud_cover_percent: float,
    ) -> list[NdviGrid]:
        bbox = bbox_with_margin(geometry, margin_m)  # EmptyGeometryError si no hay puntos
        wgs84_bbox = _bbox_to_wgs84(bbox, geometry.srid)
        response = self._json_poster(
            STAC_SEARCH_URL,
            {
                "collections": [COLLECTION],
                "bbox": list(wgs84_bbox),
                "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
                "limit": 10,
            },
        )
        scenes = parse_stac_search_response(response)
        candidates = [s for s in scenes if s["cloud_cover_percent"] <= max_cloud_cover_percent]
        if not candidates:
            raise NoScenesAfterCloudFilterError(bbox, start, end, max_cloud_cover_percent)
        candidates.sort(key=lambda s: s["scene_date"])
        return [self._ndvi_grid_for_scene(scene, geometry.srid, bbox) for scene in candidates]

    def _ndvi_grid_for_scene(self, scene: SceneCandidate, srid: int, bbox: BBox) -> NdviGrid:
        minx, miny, maxx, maxy = bbox
        n_cols = max(1, round((maxx - minx) / _RESOLUTION_M))
        n_rows = max(1, round((maxy - miny) / _RESOLUTION_M))
        cell_w = (maxx - minx) / n_cols
        cell_h = (maxy - miny) / n_rows

        transformer = Transformer.from_crs(srid, scene["epsg"], always_xy=True)

        cell_centers_native: list[list[tuple[float, float]]] = []
        for row in range(n_rows):
            cy = maxy - (row + 0.5) * cell_h
            row_centers = []
            for col in range(n_cols):
                cx = minx + (col + 0.5) * cell_w
                row_centers.append(transformer.transform(cx, cy))
            cell_centers_native.append(row_centers)

        red_pixels = self._pixel_grid(scene["red"], cell_centers_native)
        nir_pixels = self._pixel_grid(scene["nir"], cell_centers_native)

        red_window, red_origin = self._read_window(scene["red"], red_pixels)
        nir_window, nir_origin = self._read_window(scene["nir"], nir_pixels)

        values: list[tuple[float, ...]] = []
        for row in range(n_rows):
            row_values = []
            for col in range(n_cols):
                rcol, rrow = red_pixels[row][col]
                ncol, nrow = nir_pixels[row][col]
                red_dn = int(red_window[rrow - red_origin[1], rcol - red_origin[0]])
                nir_dn = int(nir_window[nrow - nir_origin[1], ncol - nir_origin[0]])
                red_refl = _reflectance(red_dn, scene["red"])
                nir_refl = _reflectance(nir_dn, scene["nir"])
                row_values.append(_ndvi(red_refl, nir_refl))
            values.append(tuple(row_values))

        grid: Grid = tuple(values)
        return NdviGrid(
            values=grid,
            bbox=bbox,
            srid=srid,
            scene_date=scene["scene_date"],
            cloud_cover_percent=scene["cloud_cover_percent"],
            provenance=Provenance(
                source="sentinel-2-l2a",
                url=f"{scene['red']['href']} + {scene['nir']['href']} (escena {scene['scene_id']})",
                retrieved_at=_today(),
                license=None,
            ),
        )

    @staticmethod
    def _pixel_grid(
        band: BandInfo, cell_centers_native: list[list[tuple[float, float]]]
    ) -> list[list[tuple[int, int]]]:
        return [
            [_invert_affine(band["transform"], x, y) for x, y in row]
            for row in cell_centers_native
        ]

    def _read_window(
        self, band: BandInfo, pixel_grid: list[list[tuple[int, int]]]
    ) -> tuple[np.ndarray, tuple[int, int]]:
        cols = [c for row in pixel_grid for c, _ in row]
        rows = [r for row in pixel_grid for _, r in row]
        min_col, max_col = min(cols), max(cols)
        min_row, max_row = min(rows), max(rows)
        tiff = open_band(band["href"], self._ranged_get, self._content_length)
        # El origen que devuelve read_pixel_window puede no coincidir con
        # (min_col, min_row) si la ventana pedida cae parcial o totalmente
        # fuera del raster nativo: usar siempre el origen que devuelve la
        # función, nunca recalcularlo aquí (bug real corregido en revisión).
        return read_pixel_window(tiff, min_col, min_row, max_col, max_row)
