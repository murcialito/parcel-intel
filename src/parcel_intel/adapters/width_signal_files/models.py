"""Esquema pydantic del fichero interno de estrechamiento (historia #243).

Borde de validación: `extra="forbid"` hace que cualquier propiedad fuera de la lista
blanca (titularidad, referencia catastral) invalide el fichero."""

import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProvenanceModel(_Model):
    fuente: str = Field(min_length=1)
    url: str = Field(min_length=1)
    fecha_descarga: date
    licencia: str | None
    redistribucion: Literal["publicable", "solo_uso_interno"]


class EvidenceModel(_Model):
    tipo_via: str
    anchura_oficial_m: float = Field(gt=0)
    anchura_catastral_m: float = Field(ge=0)
    parcelas_de_camino: int = Field(ge=1)


class PiecePropertiesModel(_Model):
    codigo_via: str
    nombre: str
    resultado: Literal["indicio", "sin_indicio", "sin_parcela_camino", "sin_datos"]
    ratio: float | None
    confianza: float | None
    motivo: str | None
    evidencia: EvidenceModel | None


class PieceModel(_Model):
    type: Literal["Feature"]
    id: str
    geometry: dict[str, object]
    properties: PiecePropertiesModel


class CollectionPropertiesModel(_Model):
    municipio: str = Field(pattern=r"^\d{5}$")
    metodo: str
    procedencia_vias: list[ProvenanceModel]
    procedencia_catastro: list[ProvenanceModel]
    aviso: str


class WidthFileModel(_Model):
    type: Literal["FeatureCollection"]
    crs: dict[str, object]
    properties: CollectionPropertiesModel
    features: list[PieceModel]


def parse_width_file(text: str) -> WidthFileModel:
    """Valida el texto del fichero; `pydantic.ValidationError` si no cumple el esquema."""
    return WidthFileModel.model_validate(json.loads(text))
