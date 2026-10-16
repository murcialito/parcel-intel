from datetime import UTC, date
from datetime import datetime as _datetime

from parcel_intel.adapters.protected_areas.client import WFS_URL, HttpGetter, default_http_getter
from parcel_intel.adapters.protected_areas.parsing import parse_wfs_protected_areas
from parcel_intel.domain.geometry import Geometry, bbox_with_margin
from parcel_intel.domain.protected_area import ProtectedArea
from parcel_intel.domain.provenance import Provenance

DEFAULT_MARGIN_M = 2.0
"""Margen por defecto en metros. Mismo criterio que el resto de fuentes
vectoriales de alta precisión de este proyecto (IDEM, cauces, vías
pecuarias): salvaguarda de punto flotante, explícitamente NO un umbral de
negocio. No se comparte con ningún otro adapter."""

_LAYER_NAME = "IDEM_MA_RED_NATURA_PLAN"


def _today() -> date:
    return _datetime.now(tz=UTC).date()


class ProtectedAreaAdapter:
    """Implementa `ProtectedAreaPort` contra el WFS de IDEM (workspace
    `Zonas`, Comunidad de Madrid), confirmado en `sources/REGISTRY.md`
    (ADR 0015). Cliente aislado: no se conecta todavía a ningún caso de
    uso ni cachea resultados."""

    def __init__(self, http_get: HttpGetter = default_http_getter) -> None:
        self._http_get = http_get

    def get_nearby_protected_areas(
        self, geometry: Geometry, margin_m: float
    ) -> list[ProtectedArea]:
        minx, miny, maxx, maxy = bbox_with_margin(geometry, margin_m)
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typenames": f"Zonas:{_LAYER_NAME}",
            "bbox": f"{minx},{miny},{maxx},{maxy},EPSG:{geometry.srid}",
        }
        body = self._http_get(WFS_URL, params)
        raw_areas = parse_wfs_protected_areas(body)
        if not raw_areas:
            return []

        query = "&".join(f"{key}={value}" for key, value in params.items())
        provenance = Provenance(
            source="idem",
            url=f"{WFS_URL}?{query}",
            retrieved_at=_today(),
            license=None,
        )
        return [
            ProtectedArea(
                plan_code=raw["plan_code"],
                plan_name=raw["plan_name"],
                zone_code=raw["zone_code"],
                zone_name=raw["zone_name"],
                geometry=Geometry(rings=raw["rings"], srid=geometry.srid),
                provenance=provenance,
            )
            for raw in raw_areas
        ]
