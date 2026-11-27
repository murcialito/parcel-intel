"""Fixtures compartidas de la capa de montes de utilidad pública por municipio (historia #220).

Las respuestas del IGN (las de vías pecuarias) y de IDEM (7 reales por bbox municipal, 2026-11-27,
con los campos de titularidad sustituidos por valores ficticios) se sirven por un getter falso.
"""

from datetime import date
from pathlib import Path

from parcel_intel.cli.main import build_municipal_forest_layers
from parcel_intel.domain.geometry import bbox_with_margin
from parcel_intel.domain.municipal_public_utility_forests import MunicipalPublicUtilityForestLayer
from tests.municipal_layer_fixtures import FakeIgnHttp, municipal_boundaries

FOREST_FIXTURES = Path(__file__).parent / "fixtures" / "public_utility_forests"


def forest_fixture_for(ine_code: str) -> Path:
    return FOREST_FIXTURES / f"wfs_getfeature_bbox_municipio_{ine_code}.xml"


class FakeForestIdemHttp:
    """Sirve la fixture real cuyo bbox municipal (margen 2 m) coincide con la petición."""

    def __init__(self) -> None:
        self.calls = 0
        self._by_bbox = {}
        for boundary in municipal_boundaries():
            minx, miny, maxx, maxy = bbox_with_margin(boundary.geometry, 2.0)
            self._by_bbox[f"{minx},{miny},{maxx},{maxy},EPSG:25830"] = forest_fixture_for(
                boundary.ine_code
            )

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls += 1
        return self._by_bbox[params["bbox"]].read_bytes()


def prepare_forest_cache(
    cache_dir: Path, today: date
) -> tuple[MunicipalPublicUtilityForestLayer, ...]:
    """Rellena la caché cruda desde las fixtures y devuelve las capas de esa primera pasada."""
    return build_municipal_forest_layers(
        cache_dir,
        offline=False,
        ign_http_get=FakeIgnHttp(),
        idem_http_get=FakeForestIdemHttp(),
        today=lambda: today,
        sleep=lambda _: None,
    )
