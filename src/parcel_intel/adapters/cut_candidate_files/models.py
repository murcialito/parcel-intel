"""Modelos pydantic del fichero interno de candidatos a corte (historia #128, ADR 0039 §8).

Borde de validación del lector. El nivel superior lleva el metadato del informe
como «foreign members» (`properties`), igual que el fichero de discrepancias.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_Position = tuple[float, float]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProvenanceModel(_Model):
    fuente: str = Field(min_length=1)
    url: str = Field(min_length=1)
    fecha_descarga: date
    licencia: str | None
    redistribucion: Literal["publicable", "solo_uso_interno"]


class MeasurementModel(_Model):
    medida: str = Field(min_length=1)
    unidad: Literal["m", "fraccion"]
    valor: float


class SignalRefModel(_Model):
    identificador: str = Field(min_length=1)
    version: int = Field(ge=1)
    condicion: Literal["no_se_distingue", "dentro_de_cierre"]


class SupportModel(_Model):
    senal: SignalRefModel
    fraccion_apoyo: float = Field(ge=0.0, le=1.0)
    fraccion_sin_dato: float = Field(ge=0.0, le=1.0)
    procedencia: list[ProvenanceModel]


class SubjectModel(_Model):
    id: str = Field(min_length=1)
    fuente: Literal[
        "via_pecuaria_oficial",
        "catastro_vt",
        "ign_red_transporte",
        "planimetria_historica",
        "mtn50_historico",
    ]
    procedencia: ProvenanceModel
    fecha_dato: date | None


class CandidatePropertiesModel(_Model):
    candidate_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    municipality_code: str = Field(pattern=r"^\d{5}$")
    trazado: SubjectModel
    registros_base: list[str] = Field(min_length=1)
    condiciones: list[Literal["no_se_distingue", "dentro_de_cierre"]] = Field(min_length=1)
    senales: list[SupportModel]
    confianza: float = Field(ge=0.0, le=1.0)
    evidencia: list[MeasurementModel]
    metodo: str = Field(pattern=r"^[a-z_]+@\d+$")


class MultiLineStringModel(_Model):
    type: Literal["MultiLineString"]
    coordinates: list[list[_Position]] = Field(min_length=1)


class FeatureModel(_Model):
    type: Literal["Feature"]
    id: str = Field(min_length=1)
    geometry: MultiLineStringModel
    properties: CandidatePropertiesModel


class SignalSummaryModel(_Model):
    senal: SignalRefModel
    estado: Literal["ejecutada", "sin_datos"]
    motivo: str | None
    procedencia: list[ProvenanceModel]


class CollectionPropertiesModel(_Model):
    municipio: str = Field(pattern=r"^\d{5}$")
    metodo: str = Field(pattern=r"^[a-z_]+@\d+$")
    criterio_discrepancias: str
    registros_base: list[str]
    senales: list[SignalSummaryModel]
    aviso: str


class CrsPropertiesModel(_Model):
    name: str


class CrsModel(_Model):
    type: Literal["name"]
    properties: CrsPropertiesModel


class CutCandidateFileModel(_Model):
    type: Literal["FeatureCollection"]
    crs: CrsModel
    properties: CollectionPropertiesModel
    features: list[FeatureModel]
