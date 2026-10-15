from datetime import date, datetime
from typing import TypedDict


class BandInfo(TypedDict):
    href: str
    transform: tuple[float, float, float, float, float, float]
    nodata: float
    scale: float
    offset: float


class SceneCandidate(TypedDict):
    scene_id: str
    scene_date: date
    cloud_cover_percent: float
    epsg: int
    red: BandInfo
    nir: BandInfo


def _band_info(asset: dict[str, object]) -> BandInfo:
    transform = asset["proj:transform"]
    raster_bands = asset["raster:bands"]
    assert isinstance(transform, list)
    assert isinstance(raster_bands, list)
    assert len(transform) == 6
    a, b, c, d, e, f = (float(v) for v in transform)
    band = raster_bands[0]
    return BandInfo(
        href=str(asset["href"]),
        transform=(a, b, c, d, e, f),
        nodata=float(band["nodata"]),
        scale=float(band["scale"]),
        offset=float(band["offset"]),
    )


def parse_stac_search_response(response: dict[str, object]) -> list[SceneCandidate]:
    """Parsea la `FeatureCollection` JSON de la búsqueda STAC a una lista de
    escenas candidatas, con los campos mínimos que necesita el adapter
    (ADR 0007: ni CRS ni georreferenciación requieren parsear GeoTIFF, ya
    vienen en el JSON)."""
    features = response.get("features", [])
    assert isinstance(features, list)
    candidates: list[SceneCandidate] = []
    for feature in features:
        properties = feature["properties"]
        assets = feature["assets"]
        scene_datetime = datetime.fromisoformat(properties["datetime"].replace("Z", "+00:00"))
        candidates.append(
            SceneCandidate(
                scene_id=feature["id"],
                scene_date=scene_datetime.date(),
                cloud_cover_percent=float(properties["eo:cloud_cover"]),
                epsg=int(properties["proj:epsg"]),
                red=_band_info(assets["red"]),
                nir=_band_info(assets["nir"]),
            )
        )
    return candidates
