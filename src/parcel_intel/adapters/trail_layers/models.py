"""Modelos pydantic del formato común de capa derivada (historia #32, ADR 0030).

Son el borde de validación: lo que no cumple el formato no llega al dominio.
La geometría se valida por tipo GeoJSON; la conversión a las formas del dominio
(solo anillos exteriores, sin Z) está en `geojson_reader`.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    # Los extras libres de los productores (`longitud_m`, `fictitious`...) se ignoran.
    model_config = ConfigDict(extra="ignore")


class ProvenanceModel(_Model):
    fuente: str = Field(min_length=1)
    url: str = Field(min_length=1)
    fecha_descarga: date
    licencia: str = Field(min_length=1)
    # Ausente = solo uso interno (denegar por defecto, #84); otro valor es error de formato.
    redistribucion: Literal["publicable", "solo_uso_interno"] | None = None


# Un punto puede llevar Z (LineString 3D del IGN); el lector la descarta.
_Position = list[float]


class PolygonModel(_Model):
    type: Literal["Polygon"]
    coordinates: list[list[_Position]]


class MultiPolygonModel(_Model):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[_Position]]]


class LineStringModel(_Model):
    type: Literal["LineString"]
    coordinates: list[_Position]


class MultiLineStringModel(_Model):
    type: Literal["MultiLineString"]
    coordinates: list[list[_Position]]


GeometryModel = Annotated[
    PolygonModel | MultiPolygonModel | LineStringModel | MultiLineStringModel,
    Field(discriminator="type"),
]


class FeaturePropertiesModel(_Model):
    procedencia: ProvenanceModel | None = None
    fecha_dato: date | None = None
    papel: Literal["via", "anejo"] = "via"
    nombre: str | None = None
    tipo: str | None = None
    superficie: Literal["unpaved", "paved"] | None = None  # red del IGN (#183)


class FeatureModel(_Model):
    type: Literal["Feature"]
    id: str | int
    geometry: GeometryModel
    properties: FeaturePropertiesModel = FeaturePropertiesModel()


class CrsPropertiesModel(_Model):
    name: str


class CrsModel(_Model):
    type: Literal["name"]
    properties: CrsPropertiesModel


class CollectionPropertiesModel(_Model):
    fuente: str
    municipio: str
    procedencia: ProvenanceModel
    aviso: str | None = None
    nombre_municipio: str | None = None
    procedencia_limite: ProvenanceModel | None = None
    # Red del IGN (historia #183): ausente en las capas que no son de `roadlink`.
    superficie: Literal["unpaved", "paved"] | None = None


class LayerFileModel(_Model):
    type: Literal["FeatureCollection"]
    crs: CrsModel
    properties: CollectionPropertiesModel
    features: list[FeatureModel]
