"""Fixtures compartidas de la capa de vías pecuarias por municipio (historia #36).

Las respuestas del IGN (recortada de la real, 2026-11-25) y de IDEM (7 reales por bbox
municipal, 2026-11-26) se sirven por un getter falso que no toca la red.
"""

from datetime import date
from pathlib import Path

from parcel_intel.adapters.ign_admin_units import IgnAdministrativeUnitsAdapter
from parcel_intel.cli.main import AMBITO_HITO_BBOX_ETRS89, AMBITO_HITO_INE, build_municipal_layers
from parcel_intel.domain.geometry import bbox_with_margin
from parcel_intel.domain.municipal_livestock_trails import MunicipalLivestockTrailLayer
from parcel_intel.domain.municipality import MunicipalBoundary

FIXTURES = Path(__file__).parent / "fixtures"
IGN_FIXTURE = FIXTURES / "caminos" / "ign_au_ambito_7_municipios.xml"
IDEM_DIR = FIXTURES / "livestock_trails"


def municipal_boundaries() -> list[MunicipalBoundary]:
    adapter = IgnAdministrativeUnitsAdapter(
        AMBITO_HITO_BBOX_ETRS89, http_get=lambda url, params: IGN_FIXTURE.read_bytes()
    )
    return adapter.get_municipal_boundaries(AMBITO_HITO_INE)


def idem_fixture_for(ine_code: str) -> Path:
    return IDEM_DIR / f"wfs_getfeature_bbox_municipio_{ine_code}.xml"


class FakeIgnHttp:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls += 1
        return IGN_FIXTURE.read_bytes()


class FakeIdemHttp:
    """Sirve la fixture real cuyo bbox municipal (margen 2 m) coincide con la petición."""

    def __init__(self) -> None:
        self.calls = 0
        self._by_bbox = {}
        for boundary in municipal_boundaries():
            minx, miny, maxx, maxy = bbox_with_margin(boundary.geometry, 2.0)
            self._by_bbox[f"{minx},{miny},{maxx},{maxy},EPSG:25830"] = idem_fixture_for(
                boundary.ine_code
            )

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls += 1
        return self._by_bbox[params["bbox"]].read_bytes()


class NoNetwork:
    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        raise AssertionError("no debe llamarse a la red")


def prepare_cache(
    cache_dir: Path, today: date
) -> tuple[MunicipalLivestockTrailLayer, ...]:
    """Rellena la caché cruda desde las fixtures y devuelve las capas de esa primera pasada."""
    return build_municipal_layers(
        cache_dir,
        offline=False,
        ign_http_get=FakeIgnHttp(),
        idem_http_get=FakeIdemHttp(),
        today=lambda: today,
        sleep=lambda _: None,
    )
