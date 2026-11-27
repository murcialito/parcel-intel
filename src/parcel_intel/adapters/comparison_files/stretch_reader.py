"""Lector de los tramos de entrada de `imagenes-comparacion` (historia #122).

`FeatureCollection` en EPSG:25830 con el miembro `crs` de los ficheros derivados
(ADR 0030; sin él, error), `properties.id` de 16 hexadecimales y geometría
`LineString` o `MultiLineString`. Cualquier otra cosa es `StretchFileFormatError`.

Si falta `properties.id`, vale el `id` de la feature: así el fichero interno de
candidatos (#128) entra tal cual y el id del manifiesto es el `candidate_id`
(historia #168, ADR 0047 §5). Con los dos presentes y distintos, error."""

import json
import re
from pathlib import Path
from typing import TypedDict, cast

from parcel_intel.domain.comparison_image import StretchRequest
from parcel_intel.domain.geometry import MultiLineGeometry

_ID = re.compile(r"[0-9a-f]{16}")
_SRID = 25830
# Cota de UTM 30N (este 100.000–900.000 m): unas coordenadas en grados no pasan.
_X_RANGE = (100_000.0, 900_000.0)
_Y_RANGE = (1_000_000.0, 10_000_000.0)


class StretchFileFormatError(Exception):
    def __init__(self, path: Path, detail: str) -> None:
        super().__init__(f"Fichero de tramos no válido {path}: {detail}")
        self.path = path
        self.detail = detail


class RawProperties(TypedDict, total=False):
    id: str


class RawGeometry(TypedDict, total=False):
    type: str
    coordinates: list[object]


class RawFeature(TypedDict, total=False):
    id: str
    properties: RawProperties
    geometry: RawGeometry


class RawCollection(TypedDict, total=False):
    type: str
    crs: dict[str, object]
    features: list[RawFeature]


def _line(path: Path, label: str, coordinates: object) -> tuple[tuple[float, float], ...]:
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise StretchFileFormatError(path, f"{label}: una línea necesita al menos 2 puntos")
    points: list[tuple[float, float]] = []
    for position in coordinates:
        if (
            not isinstance(position, list)
            or len(position) < 2
            or not all(isinstance(v, int | float) and not isinstance(v, bool) for v in position)
        ):
            raise StretchFileFormatError(path, f"{label}: punto no válido")
        x, y = float(position[0]), float(position[1])
        if not (_X_RANGE[0] <= x <= _X_RANGE[1] and _Y_RANGE[0] <= y <= _Y_RANGE[1]):
            raise StretchFileFormatError(
                path, f"{label}: coordenadas fuera del rango de EPSG:{_SRID}"
            )
        points.append((x, y))
    return tuple(points)


def _crs_name(raw: RawCollection) -> str:
    crs = raw.get("crs")
    properties = crs.get("properties") if isinstance(crs, dict) else None
    name = properties.get("name") if isinstance(properties, dict) else None
    return name if isinstance(name, str) else ""


def read_stretches(path: Path, municipality_code: str) -> tuple[StretchRequest, ...]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise StretchFileFormatError(path, f"JSON ilegible: {error}") from error
    if not isinstance(loaded, dict) or loaded.get("type") != "FeatureCollection":
        raise StretchFileFormatError(path, "se esperaba una FeatureCollection")
    raw = cast(RawCollection, loaded)
    if not _crs_name(raw).endswith(("EPSG::25830", "EPSG:25830")):
        raise StretchFileFormatError(path, f"falta el crs o no es EPSG:{_SRID}")
    features = raw.get("features")
    if not isinstance(features, list):
        raise StretchFileFormatError(path, "falta la lista de features")
    requests: list[StretchRequest] = []
    for index, feature in enumerate(features):
        label = f"feature {index}"
        properties = feature.get("properties") if isinstance(feature, dict) else None
        stretch_id = properties.get("id") if isinstance(properties, dict) else None
        feature_id = feature.get("id") if isinstance(feature, dict) else None
        if stretch_id is None:
            # El fichero interno de candidatos (#128) lleva el id en la feature (#168, CA9).
            stretch_id = feature_id
        elif feature_id is not None and feature_id != stretch_id:
            raise StretchFileFormatError(
                path, f"{label}: properties.id y el id de la feature no coinciden"
            )
        if not isinstance(stretch_id, str) or not _ID.fullmatch(stretch_id):
            raise StretchFileFormatError(
                path, f"{label}: properties.id debe ser un id de 16 hexadecimales en minúscula"
            )
        geometry = feature.get("geometry")
        kind = geometry.get("type") if isinstance(geometry, dict) else None
        coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
        lines: tuple[tuple[tuple[float, float], ...], ...]
        if kind == "LineString":
            lines = (_line(path, label, coordinates),)
        elif kind == "MultiLineString" and isinstance(coordinates, list) and coordinates:
            lines = tuple(_line(path, label, part) for part in coordinates)
        else:
            raise StretchFileFormatError(path, f"{label}: se esperaba LineString o MultiLineString")
        requests.append(
            StretchRequest(stretch_id, municipality_code, MultiLineGeometry(lines, _SRID))
        )
    ids = [request.stretch_id for request in requests]
    if len(set(ids)) != len(ids):
        raise StretchFileFormatError(path, "hay ids de tramo repetidos")
    return tuple(requests)
