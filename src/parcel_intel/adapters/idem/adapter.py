from datetime import UTC, date
from datetime import datetime as _datetime

from parcel_intel.adapters.idem.client import WFS_URL, HttpGetter, default_http_getter
from parcel_intel.adapters.idem.parsing import parse_wfs_land_classifications
from parcel_intel.domain.geometry import Geometry, bbox_with_margin
from parcel_intel.domain.land_classification import LandClassification
from parcel_intel.domain.provenance import Provenance
from parcel_intel.ports.errors import NoLandClassificationFoundError

DEFAULT_MARGIN_M = 2.0
"""Margen por defecto en metros. A diferencia de PNOA/Sentinel-2 (donde el
margen da contexto visual o cubre el tamaño de píxel de una imagen raster),
aquí la geometría de clasificación es vectorial de alta precisión: el
margen solo es una salvaguarda frente a imprecisión de punto flotante en el
borde exacto de un polígono, no un margen de contexto (ADR 0011). No se
comparte con ningún otro adapter."""

_LAYER_NAME = "VPLA_V_CLASIFICACION_REF_25"


def _today() -> date:
    return _datetime.now(tz=UTC).date()


class IdemAdapter:
    """Implementa `LandClassificationPort` contra el WFS de IDEM
    (Comunidad de Madrid) confirmado en `sources/REGISTRY.md` (ADR 0011).
    Cliente aislado: no se conecta todavía a ningún caso de uso ni cachea
    resultados."""

    def __init__(self, http_get: HttpGetter = default_http_getter) -> None:
        self._http_get = http_get

    def get_land_classifications(
        self, geometry: Geometry, margin_m: float
    ) -> list[LandClassification]:
        bbox = bbox_with_margin(geometry, margin_m)
        minx, miny, maxx, maxy = bbox
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typenames": _LAYER_NAME,
            "bbox": f"{minx},{miny},{maxx},{maxy},EPSG:{geometry.srid}",
        }
        body = self._http_get(WFS_URL, params)
        raw_classifications = parse_wfs_land_classifications(body)
        if not raw_classifications:
            raise NoLandClassificationFoundError(bbox)

        query = "&".join(f"{key}={value}" for key, value in params.items())
        provenance = Provenance(
            source="idem",
            url=f"{WFS_URL}?{query}",
            retrieved_at=_today(),
            license=None,
        )
        return [
            LandClassification(
                general_category=raw["general_category"],
                detailed_category=raw["detailed_category"],
                short_code=raw["short_code"],
                reference_date=raw["reference_date"],
                municipality_code=raw["municipality_code"],
                municipality_name=raw["municipality_name"],
                area_m2=raw["area_m2"],
                geometry=Geometry(rings=raw["rings"], srid=geometry.srid),
                provenance=provenance,
            )
            for raw in raw_classifications
        ]
