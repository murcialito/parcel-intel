"""Fixtures compartidas de la capa de camino actual por municipio (historia #27).

`tests/fixtures/road_network/roadlink_unpaved_recorte_municipio_<ine>.json` son
RECORTES de la respuesta real de roadlink (consulta 2026-11-26, filtro
`surfacecategory='unpaved'`, bbox del término con margen 2 m, EPSG:25830): de las
decenas o miles de tramos que devuelve el servicio por término se conservan
10-12 reales, sin tocar su geometría ni sus propiedades (tramos que cruzan un
límite, ficticios, no ficticios y vecinos que no tocan el término).
`numberMatched`/`numberReturned` se ajustaron al recorte. El paginado real no
cabe en el repo (~60 MB) y se prueba con respuestas SINTÉTICAS y en la
integración `[integración]` de CA8.
"""

from datetime import date
from pathlib import Path

from parcel_intel.cli.main import build_municipal_road_layers
from parcel_intel.domain.geometry import bbox_with_margin
from parcel_intel.domain.municipal_road_layer import MunicipalRoadLayerBatch
from tests.municipal_layer_fixtures import FakeIgnHttp, municipal_boundaries

ROAD_DIR = Path(__file__).parent / "fixtures" / "road_network"
VACIO_FIXTURE = (
    Path(__file__).parent / "fixtures" / "caminos" / "ign_apifeatures_roadlink_vacio_25830.json"
)


def recorte_for(ine_code: str) -> Path:
    return ROAD_DIR / f"roadlink_unpaved_recorte_municipio_{ine_code}.json"


class FakeRoadlinkHttp:
    """Sirve el recorte real cuyo bbox municipal (margen 2 m) coincide con la petición.

    `fail_for` simula un fallo de red solo para esos municipios."""

    def __init__(self, fail_for: tuple[str, ...] = ()) -> None:
        self.calls: list[dict[str, str]] = []
        self._by_bbox: dict[str, str] = {}
        for boundary in municipal_boundaries():
            minx, miny, maxx, maxy = bbox_with_margin(boundary.geometry, 2.0)
            self._by_bbox[f"{minx},{miny},{maxx},{maxy}"] = boundary.ine_code
        self._fail_for = fail_for

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        import requests

        self.calls.append(params)
        ine = self._by_bbox[params["bbox"]]
        if ine in self._fail_for:
            raise requests.ConnectionError(f"sin conexión simulada para {ine}")
        return recorte_for(ine).read_bytes()


class NoNetwork:
    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        raise AssertionError("no debe llamarse a la red")


def prepare_road_cache(
    cache_dir: Path, today: date, fail_for: tuple[str, ...] = ()
) -> MunicipalRoadLayerBatch:
    """Rellena la caché cruda desde las fixtures y devuelve el lote de esa primera pasada."""
    return build_municipal_road_layers(
        cache_dir,
        offline=False,
        ign_http_get=FakeIgnHttp(),
        roadlink_http_get=FakeRoadlinkHttp(fail_for),
        today=lambda: today,
        sleep=lambda _: None,
    )
