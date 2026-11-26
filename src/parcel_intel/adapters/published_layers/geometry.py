"""Forma del dominio (EPSG:25830) → geometría GeoJSON publicada en EPSG:4326
(historias #84 y #94). La comparten el sink de trazados y el de indicios."""

from parcel_intel.adapters.published_layers.index import PublishedLayerError
from parcel_intel.adapters.published_layers.projection import to_lonlat
from parcel_intel.domain.geometry import Geometry, Ring, TrailShape


def _closed(ring: Ring) -> Ring:
    return ring if ring[0] == ring[-1] else (*ring, ring[0])


def shape_to_geojson(shape: TrailShape, label: str) -> dict[str, object]:
    """`[lon, lat]` a 6 decimales, anillos cerrados. `PublishedLayerError` si la forma
    no tiene ninguna parte (`label` nombra el elemento en el mensaje)."""
    if isinstance(shape, Geometry):
        rings = [to_lonlat(_closed(ring)) for ring in shape.rings if ring]
        if not rings:
            raise PublishedLayerError(f"{label} sin geometría")
        if len(rings) == 1:
            return {"type": "Polygon", "coordinates": [rings[0]]}
        return {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]}
    lines = [to_lonlat(line) for line in shape.lines if line]
    if not lines:
        raise PublishedLayerError(f"{label} sin geometría")
    if len(lines) == 1:
        return {"type": "LineString", "coordinates": lines[0]}
    return {"type": "MultiLineString", "coordinates": lines}
