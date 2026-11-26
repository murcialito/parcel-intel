"""Reproyección de EPSG:25830 a EPSG:4326 para el GeoJSON publicado (historia #84).

Salida `[lon, lat]` (RFC 7946, `always_xy=True`), sin Z. El redondeo a 6 decimales
(≈0,1 m) se hace solo al serializar. Es el único sitio que conoce EPSG:4326.
"""

from pyproj import Transformer

SOURCE_CRS = "EPSG:25830"
TARGET_CRS = "EPSG:4326"
DECIMALS = 6

_TRANSFORMER = Transformer.from_crs(SOURCE_CRS, TARGET_CRS, always_xy=True)


def to_lonlat(points: tuple[tuple[float, float], ...]) -> list[list[float]]:
    """Puntos EPSG:25830 → `[[lon, lat], …]` redondeados a `DECIMALS`."""
    if not points:
        return []
    xs, ys = zip(*points, strict=True)
    lons, lats = _TRANSFORMER.transform(xs, ys)
    return [
        [round(float(lon), DECIMALS), round(float(lat), DECIMALS)]
        for lon, lat in zip(lons, lats, strict=True)
    ]
