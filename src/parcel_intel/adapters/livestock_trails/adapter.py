from datetime import UTC, date
from datetime import datetime as _datetime

from parcel_intel.adapters.livestock_trails.client import WFS_URL, HttpGetter, default_http_getter
from parcel_intel.adapters.livestock_trails.parsing import parse_wfs_livestock_trails
from parcel_intel.domain.geometry import Geometry, bbox_with_margin
from parcel_intel.domain.livestock_trail import LivestockTrail
from parcel_intel.domain.provenance import Provenance

DEFAULT_MARGIN_M = 2.0
"""Margen por defecto en metros. Mismo criterio que IDEM/`UsoDelSuelo`
(ADR 0011) y cursos de agua (ADR 0012): salvaguarda de punto flotante en
el borde de una geometría vectorial de alta precisión, explícitamente NO
un umbral de negocio — cualquier regla futura de "a menos de N metros de
una vía pecuaria" debe pasar su propio `margin_m`, no depender de este
valor por defecto. No se comparte con ningún otro adapter."""

_LAYER_NAME = "IDEM_MA_VIAS_PECUARIAS"


def _today() -> date:
    return _datetime.now(tz=UTC).date()


class LivestockTrailAdapter:
    """Implementa `LivestockTrailPort` contra el WFS de IDEM (workspace
    `Zonas`, Comunidad de Madrid), confirmado en `sources/REGISTRY.md`
    (ADR 0014). Cliente aislado: no se conecta todavía a ningún caso de
    uso ni cachea resultados."""

    def __init__(self, http_get: HttpGetter = default_http_getter) -> None:
        self._http_get = http_get

    def get_nearby_livestock_trails(
        self, geometry: Geometry, margin_m: float
    ) -> list[LivestockTrail]:
        minx, miny, maxx, maxy = bbox_with_margin(geometry, margin_m)
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typenames": f"Zonas:{_LAYER_NAME}",
            "bbox": f"{minx},{miny},{maxx},{maxy},EPSG:{geometry.srid}",
        }
        body = self._http_get(WFS_URL, params)
        raw_trails = parse_wfs_livestock_trails(body)
        if not raw_trails:
            return []

        query = "&".join(f"{key}={value}" for key, value in params.items())
        provenance = Provenance(
            source="idem",
            url=f"{WFS_URL}?{query}",
            retrieved_at=_today(),
            license=None,
        )
        return [
            LivestockTrail(
                trail_type=raw["trail_type"],
                name=raw["name"],
                municipality_code=raw["municipality_code"],
                municipality_name=raw["municipality_name"],
                trail_code=raw["trail_code"],
                length_m=raw["length_m"],
                area_m2=raw["area_m2"],
                geometry=Geometry(rings=raw["rings"], srid=geometry.srid),
                provenance=provenance,
            )
            for raw in raw_trails
        ]
