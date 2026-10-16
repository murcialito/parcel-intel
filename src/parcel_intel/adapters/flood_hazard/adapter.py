from datetime import UTC, date
from datetime import datetime as _datetime
from typing import Literal

from parcel_intel.adapters.flood_hazard.client import WMS_URL, HttpGetter, default_http_getter
from parcel_intel.adapters.flood_hazard.parsing import parse_water_depth
from parcel_intel.domain.flood_hazard import FloodHazardSample
from parcel_intel.domain.geometry import Geometry, bbox_with_margin
from parcel_intel.domain.provenance import Provenance

DEFAULT_MARGIN_M = 2.0
"""Mismo valor que `HydrographyAdapter`, por consistencia de interfaz entre
los dos ports nuevos de la historia 0012 — SIN efecto observable aquí: el
servicio siempre muestrea el centro exacto del bbox (I=J=128 de una imagen
256x256), que no cambia con el margen (ADR 0012, decisión 6)."""

_IMAGE_SIZE_PX = 256
_CENTER_PX = 128

# Las 5 combinaciones reales confirmadas en REGISTRY.md (GetCapabilities +
# GetFeatureInfo reales) -- ninguna se difiere, las 5 están confirmadas
# reales y accesibles con el mismo método, sin coste adicional.
_KNOWN_LAYERS: tuple[tuple[str, Literal["fluvial", "marina"], int], ...] = (
    ("NZ.Flood.FluvialT10", "fluvial", 10),
    ("NZ.Flood.FluvialT100", "fluvial", 100),
    ("NZ.Flood.FluvialT500", "fluvial", 500),
    ("NZ.Flood.MarinaT100", "marina", 100),
    ("NZ.Flood.MarinaT500", "marina", 500),
)


def _today() -> date:
    return _datetime.now(tz=UTC).date()


class FloodHazardAdapter:
    """Implementa `FloodHazardPort` contra el WMS de peligrosidad por
    inundación de IDEE, confirmado en `sources/REGISTRY.md` (ADR 0012).

    LIMITACIÓN DOCUMENTADA: el servicio real es un raster de profundidad de
    agua, no una colección vectorial con geometría — cada muestra se toma
    en el centro del bbox (geometry + margin_m), no en cada punto de la
    geometría real de la parcela (ver REGISTRY.md hallazgo 4 y ADR 0012).
    Cliente aislado: no se conecta todavía a ningún caso de uso ni cachea
    resultados."""

    def __init__(self, http_get: HttpGetter = default_http_getter) -> None:
        self._http_get = http_get

    def get_flood_hazard(self, geometry: Geometry, margin_m: float) -> list[FloodHazardSample]:
        minx, miny, maxx, maxy = bbox_with_margin(geometry, margin_m)
        samples: list[FloodHazardSample] = []
        for layer, kind, return_period_years in _KNOWN_LAYERS:
            params = {
                "service": "WMS",
                "version": "1.3.0",
                "request": "GetFeatureInfo",
                "layers": layer,
                "query_layers": layer,
                "styles": "",
                "crs": f"EPSG:{geometry.srid}",
                "bbox": f"{minx},{miny},{maxx},{maxy}",
                "width": str(_IMAGE_SIZE_PX),
                "height": str(_IMAGE_SIZE_PX),
                "i": str(_CENTER_PX),
                "j": str(_CENTER_PX),
                "info_format": "text/html",
            }
            body = self._http_get(WMS_URL, params)
            water_depth_m = parse_water_depth(body)
            query = "&".join(f"{key}={value}" for key, value in params.items())
            samples.append(
                FloodHazardSample(
                    kind=kind,
                    return_period_years=return_period_years,
                    water_depth_m=water_depth_m,
                    provenance=Provenance(
                        source="idee-flood-hazard",
                        url=f"{WMS_URL}?{query}",
                        retrieved_at=_today(),
                        license=None,
                    ),
                )
            )
        return samples
