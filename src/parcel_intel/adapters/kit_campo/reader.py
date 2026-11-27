"""Lector de las capas ya publicadas en `site/datos/<capa>/<ine>.geojson` (historia #213)."""

import json
from collections.abc import Mapping
from pathlib import Path

from parcel_intel.domain.kit_campo import (
    Coordinate,
    KitGeometry,
    KitLayerId,
    Polygon,
    PublishedFeature,
    PublishedLayerFile,
    Ring,
)
from parcel_intel.ports.kit_campo import PublishedLayerFileError


def _object(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise PublishedLayerFileError(f"{where}: se esperaba un objeto JSON")
    return value


def _load(path: Path) -> Mapping[str, object]:
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, ValueError) as error:
        if isinstance(error, PublishedLayerFileError):
            raise
        raise PublishedLayerFileError(f"{path}: no se puede leer: {error}") from error


def _coordinate(value: object, where: str) -> Coordinate:
    if (
        not isinstance(value, list)
        or len(value) < 2
        or not all(isinstance(n, int | float) and not isinstance(n, bool) for n in value[:2])
    ):
        raise PublishedLayerFileError(f"{where}: coordenada no válida")
    lon, lat = float(value[0]), float(value[1])
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise PublishedLayerFileError(f"{where}: coordenada fuera de EPSG:4326")
    return (lon, lat)


def _ring(value: object, where: str) -> Ring:
    if not isinstance(value, list) or not value:
        raise PublishedLayerFileError(f"{where}: línea o anillo vacío")
    return tuple(_coordinate(item, where) for item in value)


def _rings(value: object, where: str) -> tuple[Ring, ...]:
    if not isinstance(value, list):
        raise PublishedLayerFileError(f"{where}: geometría no válida")
    return tuple(_ring(item, where) for item in value)


def _geometry(value: object, where: str) -> KitGeometry:
    geometry = _object(value, where)
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "LineString":
        return KitGeometry(lines=(_ring(coordinates, where),))
    if kind == "MultiLineString":
        return KitGeometry(lines=_rings(coordinates, where))
    if kind == "Polygon":
        return KitGeometry(polygons=(_rings(coordinates, where),))
    if kind == "MultiPolygon":
        if not isinstance(coordinates, list):
            raise PublishedLayerFileError(f"{where}: geometría no válida")
        polygons: tuple[Polygon, ...] = tuple(_rings(item, where) for item in coordinates)
        return KitGeometry(polygons=polygons)
    raise PublishedLayerFileError(f"{where}: tipo de geometría no admitido: {kind!r}")


def _attribution(value: object, where: str) -> tuple[str, ...]:
    if isinstance(value, str) and value.strip():
        return (value,)
    if isinstance(value, list) and value and all(isinstance(i, str) and i.strip() for i in value):
        return tuple(str(i) for i in value)
    raise PublishedLayerFileError(f"{where}: procedencia sin atribución")


def _string(document: Mapping[str, object], key: str, where: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PublishedLayerFileError(f"{where}: procedencia sin '{key}'")
    return value


class PublishedLayerFileReader:
    """Lee `<raíz>/<capa>/<ine>.geojson` y su `.procedencia.json`."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def read(self, layer: KitLayerId, municipality_code: str) -> PublishedLayerFile | None:
        path = self._root / layer / f"{municipality_code}.geojson"
        if not path.is_file():
            return None
        sidecar_path = path.with_name(path.name + ".procedencia.json")
        if not sidecar_path.is_file():
            raise PublishedLayerFileError(f"{path}: falta {sidecar_path.name}")
        sidecar = _load(sidecar_path)
        where = str(sidecar_path)
        if sidecar.get("capa") != layer or sidecar.get("municipio") != municipality_code:
            raise PublishedLayerFileError(
                f"{where}: no es la procedencia de {layer}/{municipality_code}"
            )
        redistribution = sidecar.get("redistribucion")
        if redistribution is not None and redistribution != "publicable":
            raise PublishedLayerFileError(f"{where}: redistribución '{redistribution}'")
        document = _load(path)
        raw_features = document.get("features")
        if document.get("type") != "FeatureCollection" or not isinstance(raw_features, list):
            raise PublishedLayerFileError(f"{path}: no es una FeatureCollection")
        features: list[PublishedFeature] = []
        for index, raw in enumerate(raw_features):
            feature_where = f"{path} elemento {index}"
            feature = _object(raw, feature_where)
            identifier = feature.get("id")
            properties = _object(feature.get("properties"), feature_where)
            features.append(
                PublishedFeature(
                    identifier=str(identifier) if identifier is not None else None,
                    geometry=_geometry(feature.get("geometry"), feature_where),
                    properties=properties,
                )
            )
        return PublishedLayerFile(
            layer=layer,
            municipality_code=municipality_code,
            features=tuple(features),
            source=_string(sidecar, "fuente", where),
            license=_string(sidecar, "licencia", where),
            attribution=_attribution(sidecar.get("atribucion"), where),
            notice=_string(sidecar, "aviso", where),
        )
