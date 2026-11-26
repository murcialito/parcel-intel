import json
from datetime import datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from parcel_intel.domain.geometry import Line


class RawRoadSegment(TypedDict):
    segment_id: int
    registered_at: datetime | None
    surface_category: str
    fictitious: bool
    points: Line


class _Properties(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id_tramo: int
    surfacecategory: str
    fecha_alta: datetime | None = None
    fictitious: bool = False

    @field_validator("fictitious", mode="before")
    @classmethod
    def _fictitious_from_text(cls, value: object) -> object:
        # Confirmado real (fixture): el servicio manda "true"/"false" como texto.
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "false"):
                return lowered == "true"
        return value


class _LineString(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["LineString"]
    coordinates: list[list[float]]

    @field_validator("coordinates")
    @classmethod
    def _at_least_two_points(cls, value: list[list[float]]) -> list[list[float]]:
        if len(value) < 2 or any(len(p) < 2 for p in value):
            raise ValueError("un LineString necesita al menos 2 puntos con x, y")
        return value


class _Feature(BaseModel):
    model_config = ConfigDict(extra="ignore")

    properties: _Properties
    geometry: _LineString


class _FeatureCollection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    features: list[_Feature]
    numberMatched: int | None = None  # noqa: N815 -- nombre del proveedor
    numberReturned: int | None = None  # noqa: N815


class RoadNetworkParseError(Exception):
    """El cuerpo no es una `FeatureCollection` de `roadlink` válida."""


def parse_road_segments(body: bytes) -> list[RawRoadSegment]:
    """Parsea una respuesta GeoJSON de `.../collections/roadlink/items`.
    Devuelve TODOS los tramos (filtrar por superficie es decisión del
    adapter). La elevación (tercer valor de cada coordenada) se descarta.
    Lanza `RoadNetworkParseError` si el JSON o su estructura no son válidos
    o si el resultado está truncado (`numberMatched > numberReturned`)."""
    try:
        collection = _FeatureCollection.model_validate(json.loads(body))
    except (ValueError, ValidationError) as exc:
        raise RoadNetworkParseError(str(exc)) from exc
    if (
        collection.numberMatched is not None
        and collection.numberReturned is not None
        and collection.numberMatched > collection.numberReturned
    ):
        raise RoadNetworkParseError(
            f"resultado truncado: {collection.numberReturned} de {collection.numberMatched} tramos"
        )
    return [
        {
            "segment_id": feature.properties.id_tramo,
            "registered_at": feature.properties.fecha_alta,
            "surface_category": feature.properties.surfacecategory,
            "fictitious": feature.properties.fictitious,
            "points": tuple((p[0], p[1]) for p in feature.geometry.coordinates),
        }
        for feature in collection.features
    ]
