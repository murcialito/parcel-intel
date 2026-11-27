"""Lector del fichero interno de candidatos a corte (historia #128, ADR 0039 §9).

Reconstruye exactamente el `MunicipalCutCandidateReport` que escribió
`GeoJsonCutCandidateWriter`. Sin fichero: `None` («sin capas»). Fichero con cero
features: informe sin candidatos («municipio evaluable»). Fichero ilegible, con
otro formato o con un CRS distinto de EPSG:25830: `CutCandidateFileError`.
"""

import json
import re
from pathlib import Path

from pydantic import ValidationError

from parcel_intel.adapters.cut_candidate_files.models import (
    CutCandidateFileModel,
    FeatureModel,
    MeasurementModel,
    ProvenanceModel,
    SignalRefModel,
    SignalSummaryModel,
    SupportModel,
)
from parcel_intel.domain.cut_candidate import (
    CutCandidate,
    MunicipalCutCandidateReport,
    SignalRef,
    SignalRunSummary,
    SignalSupport,
)
from parcel_intel.domain.discrepancy import Measurement, SourceRef, TrailRef
from parcel_intel.domain.discrepancy_criterion import METRIC_SRID, CriterionRef
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import CutCandidateFileError

_MUNICIPALITY_RE = re.compile(r"\d{5}")


def _provenance(model: ProvenanceModel) -> Provenance:
    return Provenance(
        source=model.fuente,
        url=model.url,
        retrieved_at=model.fecha_descarga,
        license=model.licencia,
        redistribution=Redistribution(model.redistribucion),
    )


def _criterion(text: str) -> CriterionRef:
    identifier, version = text.split("@")
    return CriterionRef(identifier=identifier, version=int(version))


def _signal(model: SignalRefModel) -> SignalRef:
    return SignalRef(model.identificador, model.version, model.condicion)


def _measure(model: MeasurementModel) -> Measurement:
    return Measurement(model.medida, model.valor, model.unidad)


def _support(model: SupportModel) -> SignalSupport:
    return SignalSupport(
        signal=_signal(model.senal),
        support_fraction=model.fraccion_apoyo,
        no_data_fraction=model.fraccion_sin_dato,
        provenance=tuple(_provenance(p) for p in model.procedencia),
    )


def _summary(model: SignalSummaryModel) -> SignalRunSummary:
    return SignalRunSummary(
        signal=_signal(model.senal),
        status=model.estado,
        reason=model.motivo,
        provenance=tuple(_provenance(p) for p in model.procedencia),
    )


def _candidate(feature: FeatureModel) -> CutCandidate:
    props = feature.properties
    if props.candidate_id != feature.id:
        raise ValueError("el id de la feature no coincide con candidate_id")
    subject = props.trazado
    return CutCandidate(
        candidate_id=props.candidate_id,
        municipality_code=props.municipality_code,
        subject=TrailRef(
            trail_id=subject.id,
            source=SourceRef(
                kind=subject.fuente,
                provenance=_provenance(subject.procedencia),
                data_date=subject.fecha_dato,
            ),
        ),
        discrepancy_ids=tuple(props.registros_base),
        stretch=MultiLineGeometry(
            lines=tuple(tuple((x, y) for x, y in line) for line in feature.geometry.coordinates),
            srid=METRIC_SRID,
        ),
        conditions=tuple(props.condiciones),
        signals=tuple(_support(s) for s in props.senales),
        confidence=props.confianza,
        evidence=tuple(_measure(m) for m in props.evidencia),
        method=_criterion(props.metodo),
    )


def read_report(path: Path) -> MunicipalCutCandidateReport:
    where = str(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise CutCandidateFileError(where, f"JSON ilegible: {error}") from error
    try:
        model = CutCandidateFileModel.model_validate(raw)
    except ValidationError as error:
        first = error.errors()[0]
        location = ".".join(str(part) for part in first["loc"])
        raise CutCandidateFileError(where, f"{location}: {first['msg']}") from error
    if not model.crs.properties.name.endswith(("EPSG::25830", "EPSG:25830")):
        raise CutCandidateFileError(
            where, f"CRS {model.crs.properties.name!r}; solo se admite EPSG:25830"
        )
    candidates: list[CutCandidate] = []
    for feature in model.features:
        try:
            candidates.append(_candidate(feature))
        except ValueError as error:
            raise CutCandidateFileError(where, f"feature {feature.id!r}: {error}") from error
    props = model.properties
    return MunicipalCutCandidateReport(
        municipality_code=props.municipio,
        method=_criterion(props.metodo),
        discrepancy_criterion_id=props.criterio_discrepancias,
        base_record_ids=tuple(props.registros_base),
        signals=tuple(_summary(s) for s in props.senales),
        candidates=tuple(candidates),
    )


class GeoJsonCutCandidateReader:
    """Implementa `CutCandidateSource` sobre `<directory>/<ine>.geojson`."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def get_report(self, municipality_code: str) -> MunicipalCutCandidateReport | None:
        if not _MUNICIPALITY_RE.fullmatch(municipality_code):
            raise ValueError(f"código INE de 5 dígitos esperado: {municipality_code!r}")
        path = self._directory / f"{municipality_code}.geojson"
        if not path.is_file():
            return None
        return read_report(path)
