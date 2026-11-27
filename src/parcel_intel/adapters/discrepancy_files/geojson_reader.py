"""Lector del fichero de discrepancias de un municipio (historia #94, ADR 0044).

Lee `<directorio>/<ine>.geojson` (el interno o el publicable de #32), lo valida con
pydantic y reconstruye exactamente el `MunicipalDiscrepancyReport` que lo escribió:
escribir, leer y volver a escribir da los mismos bytes. Sin fichero:
`DiscrepancyReportUnavailableError`. Fichero ilegible, con otro formato (también
uno escrito antes de #94) o incoherente: `DiscrepancyFileFormatError`.
"""

import json
import re
from pathlib import Path

from pydantic import ValidationError

from parcel_intel.adapters.discrepancy_files.models import (
    DiscrepancyFileModel,
    FeatureModel,
    GeometryModel,
    LayerModel,
    ProvenanceModel,
    TrailModel,
)
from parcel_intel.adapters.trail_layers.geojson_reader import geometry_to_shape
from parcel_intel.domain.discrepancy import (
    Discrepancy,
    Measurement,
    SourceRef,
    TrailRef,
)
from parcel_intel.domain.discrepancy_criterion import CriterionRef
from parcel_intel.domain.discrepancy_report import (
    DiscrepancyRecord,
    LayerStatus,
    LayerSummary,
    MunicipalDiscrepancyReport,
    TrailEvidence,
)
from parcel_intel.domain.geometry import Geometry, TrailShape
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.trail import METRIC_SRID
from parcel_intel.ports.errors import DiscrepancyReportUnavailableError

_MUNICIPALITY_RE = re.compile(r"\d{5}")
_REGENERATE = "regenéralo con `discrepancias --municipio <ine>`"


class DiscrepancyFileFormatError(Exception):
    """El fichero de discrepancias existe pero no cumple el formato de ADR 0044."""

    def __init__(self, path: Path, detail: str) -> None:
        super().__init__(f"Fichero de discrepancias no válido {path}: {detail}")
        self.path = path
        self.detail = detail


def _provenance(model: ProvenanceModel) -> Provenance:
    return Provenance(
        source=model.fuente,
        url=model.url,
        retrieved_at=model.fecha_descarga,
        license=model.licencia,
        redistribution=Redistribution(model.redistribucion),
    )


def _shape(model: GeometryModel | None) -> TrailShape:
    if model is None:
        return Geometry(rings=(), srid=METRIC_SRID)
    return geometry_to_shape(model)


def _criterion(text: str) -> CriterionRef:
    identifier, version = text.split("@")
    return CriterionRef(identifier=identifier, version=int(version))


def _evidence(trail: TrailModel) -> TrailEvidence:
    geometry: TrailShape | None
    if trail.geometria is None and trail.geometria_omitida == "licencia":
        geometry = None
    else:
        geometry = _shape(trail.geometria)
    return TrailEvidence(
        trail_id=trail.id,
        source=trail.fuente,
        provenance=_provenance(trail.procedencia),
        data_date=trail.fecha_dato,
        geometry=geometry,
    )


def _record(feature: FeatureModel) -> DiscrepancyRecord:
    props = feature.properties
    subject, *others = props.trazados
    if subject.lado != "A" or subject.fuente != props.fuente_a:
        raise ValueError("el primer trazado debe ser el lado A, de la fuente A")
    if any(t.lado != "B" or t.fuente != props.fuente_b for t in others):
        raise ValueError("los trazados tras el primero deben ser del lado B, de la fuente B")
    counterpart_source = SourceRef(
        kind=props.fuente_b,
        provenance=_provenance(props.procedencia_b),
        data_date=props.fecha_dato_b,
    )
    discrepancy = Discrepancy(
        kind=props.tipo,
        zone=_shape(feature.geometry),
        subject=TrailRef(
            trail_id=subject.id,
            source=SourceRef(
                kind=props.fuente_a,
                provenance=_provenance(subject.procedencia),
                data_date=subject.fecha_dato,
            ),
        ),
        counterpart_source=counterpart_source,
        counterpart_trails=tuple(TrailRef(t.id, counterpart_source) for t in others),
        confidence=props.confianza,
        evidence=tuple(Measurement(m.medida, m.valor, m.unidad) for m in props.evidencia),
        criterion=_criterion(props.criterio),
    )
    return DiscrepancyRecord(
        record_id=feature.id,
        discrepancy=discrepancy,
        trails=tuple(_evidence(trail) for trail in props.trazados),
        zone_redacted=props.zona_omitida_por_licencia,
    )


def _layer(model: LayerModel) -> LayerSummary:
    return LayerSummary(
        source=model.fuente,
        status=LayerStatus(model.estado),
        provenance=_provenance(model.procedencia) if model.procedencia is not None else None,
        trail_count=model.trazados,
        empty_geometry_ids=tuple(model.ids_sin_geometria),
        missing_reason=model.motivo_ausencia,
    )


class GeoJsonDiscrepancyReportReader:
    """Implementa `DiscrepancyReportSource` sobre `<directory>/<ine>.geojson`."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def get_report(self, municipality_code: str) -> MunicipalDiscrepancyReport:
        if not _MUNICIPALITY_RE.fullmatch(municipality_code):
            raise ValueError(f"código INE de 5 dígitos esperado: {municipality_code!r}")
        path = self._directory / f"{municipality_code}.geojson"
        if not path.is_file():
            raise DiscrepancyReportUnavailableError(
                municipality_code, f"no existe {path}; {_REGENERATE}"
            )
        return read_report(path)


def read_report(path: Path) -> MunicipalDiscrepancyReport:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise DiscrepancyFileFormatError(path, f"JSON ilegible: {error}") from error
    try:
        model = DiscrepancyFileModel.model_validate(raw)
    except ValidationError as error:
        first = error.errors()[0]
        location = ".".join(str(part) for part in first["loc"])
        raise DiscrepancyFileFormatError(
            path,
            f"{location}: {first['msg']}. Si se escribió antes de la historia #94, {_REGENERATE}",
        ) from error
    if not model.crs.properties.name.endswith(("EPSG::25830", "EPSG:25830")):
        raise DiscrepancyFileFormatError(
            path, f"CRS {model.crs.properties.name!r}; solo se admite EPSG:25830"
        )
    records: list[DiscrepancyRecord] = []
    for feature in model.features:
        try:
            records.append(_record(feature))
        except ValueError as error:
            raise DiscrepancyFileFormatError(path, f"feature {feature.id!r}: {error}") from error
    props = model.properties
    return MunicipalDiscrepancyReport(
        municipality_code=props.municipio,
        criterion_id=props.criterio,
        layers=tuple(_layer(layer) for layer in props.capas),
        records=tuple(records),
        redacted=props.publicable,
        municipality_name=props.nombre_municipio,
    )
