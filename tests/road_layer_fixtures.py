"""Fixtures compartidas de la capa de camino actual por municipio (historias #27 y #183).

`tests/fixtures/road_network/roadlink_unpaved_recorte_municipio_<ine>.json` son
RECORTES de la respuesta real de roadlink (consulta 2026-11-26, filtro
`surfacecategory='unpaved'`, bbox del término con margen 2 m, EPSG:25830): de las
decenas o miles de tramos que devuelve el servicio por término se conservan
10-12 reales, sin tocar su geometría ni sus propiedades (tramos que cruzan un
límite, ficticios, no ficticios y vecinos que no tocan el término).
`numberMatched`/`numberReturned` se ajustaron al recorte. El paginado real no
cabe en el repo (~60 MB) y se prueba con respuestas SINTÉTICAS y en la
integración `[integración]` de CA8.

`roadlink_paved_recorte_municipio_<ine>.json` (historia #183) son RECORTES de la
consulta real `surfacecategory='paved'` del 2026-11-27, con el mismo bbox: 8 tramos
reales por municipio, sin tocar geometría ni propiedades, elegidos por orden de
`id_tramo` dentro de cada grupo: 2 que cruzan el límite del término, 2 de vecinos que
no lo tocan, 2 no ficticios (`fictitious="false"`) y el resto dentro del término. Se
eligieron pasando la respuesta íntegra por `RoadNetworkAdapter` y `ShapelyLineClipper`
(script de Bloque 0 descrito en REGISTRY.md, sección de #183).
`numberMatched`/`numberReturned` se ajustaron al recorte (8).
"""

from datetime import date
from pathlib import Path

from parcel_intel.cli.main import build_municipal_road_layers
from parcel_intel.domain.geometry import bbox_with_margin
from parcel_intel.domain.municipal_road_layer import MunicipalRoadLayerBatch
from parcel_intel.domain.road_segment import ROAD_SURFACES, RoadSurface
from tests.municipal_layer_fixtures import FakeIgnHttp, municipal_boundaries

ROAD_DIR = Path(__file__).parent / "fixtures" / "road_network"
VACIO_FIXTURE = (
    Path(__file__).parent / "fixtures" / "caminos" / "ign_apifeatures_roadlink_vacio_25830.json"
)
_FILTERS: dict[str, RoadSurface] = {
    f"surfacecategory='{surface}'": surface for surface in ROAD_SURFACES
}


def recorte_for(ine_code: str, surface: RoadSurface = "unpaved") -> Path:
    return ROAD_DIR / f"roadlink_{surface}_recorte_municipio_{ine_code}.json"


class FakeRoadlinkHttp:
    """Sirve el recorte real cuyo bbox municipal (margen 2 m) coincide con la petición,
    según el filtro de superficie (`unpaved` o `paved`); otro filtro es un error.

    `fail_for` simula un fallo de red solo para esos municipios y, si se da
    `fail_surfaces`, solo en esas consultas."""

    def __init__(
        self,
        fail_for: tuple[str, ...] = (),
        fail_surfaces: tuple[RoadSurface, ...] = ROAD_SURFACES,
    ) -> None:
        self.calls: list[dict[str, str]] = []
        self._by_bbox: dict[str, str] = {}
        for boundary in municipal_boundaries():
            minx, miny, maxx, maxy = bbox_with_margin(boundary.geometry, 2.0)
            self._by_bbox[f"{minx},{miny},{maxx},{maxy}"] = boundary.ine_code
        self._fail_for = fail_for
        self._fail_surfaces = fail_surfaces

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        import requests

        self.calls.append(params)
        ine = self._by_bbox[params["bbox"]]
        surface = _FILTERS.get(params.get("filter", ""))
        if surface is None:
            raise AssertionError(f"filtro de roadlink no previsto: {params.get('filter')!r}")
        if ine in self._fail_for and surface in self._fail_surfaces:
            raise requests.ConnectionError(f"sin conexión simulada para {ine} ({surface})")
        return recorte_for(ine, surface).read_bytes()


class NoNetwork:
    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        raise AssertionError("no debe llamarse a la red")


def prepare_road_batches(
    cache_dir: Path,
    today: date,
    fail_for: tuple[str, ...] = (),
    fail_surfaces: tuple[RoadSurface, ...] = ROAD_SURFACES,
) -> dict[RoadSurface, MunicipalRoadLayerBatch]:
    """Rellena la caché cruda desde las fixtures con las dos superficies y devuelve el
    lote de cada una (como las dos pasadas de `camino-actual-municipios`)."""
    return {
        surface: build_municipal_road_layers(
            cache_dir,
            offline=False,
            ign_http_get=FakeIgnHttp(),
            roadlink_http_get=FakeRoadlinkHttp(fail_for, fail_surfaces),
            today=lambda: today,
            sleep=lambda _: None,
            surface=surface,
        )
        for surface in ROAD_SURFACES
    }


def prepare_road_cache(
    cache_dir: Path, today: date, fail_for: tuple[str, ...] = ()
) -> MunicipalRoadLayerBatch:
    """Rellena la caché cruda desde las fixtures (las dos superficies, historia #183) y
    devuelve el lote `unpaved` de esa primera pasada."""
    return prepare_road_batches(cache_dir, today, fail_for)["unpaved"]
