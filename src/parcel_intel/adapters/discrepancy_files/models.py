"""Modelos pydantic del fichero de discrepancias de un municipio (historias #32 y #94,
ADR 0030 y ADR 0044).

Borde de validación del lector: lo que no cumple el formato no llega al dominio.
Las claves que añadió #94 (`nombre_municipio`, `procedencia_b`, `fecha_dato_b`,
`redistribucion`) son **obligatorias**, para que un fichero escrito antes se
rechace y se regenere con `discrepancias` en vez de leerse a medias.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from parcel_intel.adapters.trail_layers.models import (
    LineStringModel,
    MultiLineStringModel,
    MultiPolygonModel,
    PolygonModel,
)

SourceKindModel = Literal[
    "via_pecuaria_oficial",
    "catastro_vt",
    "ign_red_transporte",
    "planimetria_historica",
    "mtn50_historico",
]
KindModel = Literal["AUSENTE_EN_FUENTE", "DESPLAZAMIENTO", "SOLAPE"]

GeometryModel = Annotated[
    PolygonModel | MultiPolygonModel | LineStringModel | MultiLineStringModel,
    Field(discriminator="type"),
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProvenanceModel(_Model):
    fuente: str = Field(min_length=1)
    url: str = Field(min_length=1)
    fecha_descarga: date
    licencia: str | None
    redistribucion: Literal["publicable", "solo_uso_interno"]


class EvidenceModel(_Model):
    medida: str = Field(min_length=1)
    unidad: Literal["m", "fraccion"]
    valor: float


class TrailModel(_Model):
    id: str = Field(min_length=1)
    lado: Literal["A", "B"]
    fuente: SourceKindModel
    procedencia: ProvenanceModel
    fecha_dato: date | None
    geometria: GeometryModel | None
    geometria_omitida: Literal["licencia"] | None = None


class FeaturePropertiesModel(_Model):
    tipo: KindModel
    fuente_a: SourceKindModel
    fuente_b: SourceKindModel
    procedencia_b: ProvenanceModel
    fecha_dato_b: date | None
    medidas: dict[str, float]
    confianza: float = Field(ge=0.0, le=1.0)
    evidencia: list[EvidenceModel]
    criterio: str = Field(pattern=r"^[a-z_]+@\d+$")
    zona_omitida_por_licencia: bool
    trazados: list[TrailModel] = Field(min_length=1)


class FeatureModel(_Model):
    type: Literal["Feature"]
    id: str = Field(min_length=1)
    geometry: GeometryModel | None
    properties: FeaturePropertiesModel


class LayerModel(_Model):
    fuente: SourceKindModel
    estado: Literal["disponible", "ausente"]
    procedencia: ProvenanceModel | None
    trazados: int = Field(ge=0)
    ids_sin_geometria: list[str]
    motivo_ausencia: str | None


class CollectionPropertiesModel(_Model):
    municipio: str = Field(pattern=r"^\d{5}$")
    nombre_municipio: str | None
    criterio: str = Field(pattern=r"^[a-z_]+@\d+$")
    publicable: bool
    aviso: str
    capas: list[LayerModel]


class CrsPropertiesModel(_Model):
    name: str


class CrsModel(_Model):
    type: Literal["name"]
    properties: CrsPropertiesModel


class DiscrepancyFileModel(_Model):
    type: Literal["FeatureCollection"]
    crs: CrsModel
    properties: CollectionPropertiesModel
    features: list[FeatureModel]
