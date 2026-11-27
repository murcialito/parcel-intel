"""Dobles y fábricas sintéticas de la señal `parcela_no_camino` (historia #127).

Todo es sintético: ninguna referencia catastral ni geometría es real.
"""

from collections.abc import Callable, Sequence
from datetime import date

from parcel_intel.domain.cut_candidate import MunicipalCutCandidateReport
from parcel_intel.domain.discrepancy import Discrepancy, SourceRef, TrailRef
from parcel_intel.domain.discrepancy_criterion import CRITERION, SourceKind
from parcel_intel.domain.discrepancy_report import (
    DiscrepancyRecord,
    MunicipalDiscrepancyReport,
    TrailEvidence,
)
from parcel_intel.domain.geometry import BBox, Geometry, MultiLineGeometry
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.provenance import Provenance
from parcel_intel.ports.errors import DiscrepancyReportUnavailableError

ORDINARY = "28043A99100012"  # rústica, parcela 12 < 9000 (polígono 991 sintético)
INFRASTRUCTURE_VT = "28043A99109001"  # rústica >= 9000 (sintética)
INFRASTRUCTURE_HG = "28043A99109002"
URBAN = "1234567VK1234S"  # 14 caracteres, sector no alfabético: no es rústica
UNREADABLE = "no-es-una-referencia"

CADASTRE = Provenance(
    "Catastro (sintético)", "https://example.invalid/catastro", date(2026, 11, 26)
)


def rect(x0: float, y0: float, x1: float, y1: float) -> Geometry:
    return Geometry(rings=(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)),), srid=25830)


def line(*points: tuple[float, float]) -> MultiLineGeometry:
    return MultiLineGeometry(lines=(tuple(points),), srid=25830)


def parcel(reference: str, geometry: Geometry) -> Parcel:
    return Parcel(reference, "SINTETICO", geometry, 1.0, CADASTRE)


def source(kind: SourceKind) -> SourceRef:
    return SourceRef(
        kind, Provenance(kind, f"https://example.invalid/{kind}", date(2026, 11, 26)), None
    )


def base_record(
    record_id: str,
    shape: MultiLineGeometry,
    trail_id: str = "VP-1",
    kind: SourceKind = "via_pecuaria_oficial",
) -> DiscrepancyRecord:
    subject = TrailRef(trail_id, source(kind))
    discrepancy = Discrepancy(
        "AUSENTE_EN_FUENTE",
        shape,
        subject,
        source("ign_red_transporte"),
        (),
        0.691,
        (),
        CRITERION,
    )
    evidence = TrailEvidence(trail_id, kind, subject.source.provenance, None, shape)
    return DiscrepancyRecord(record_id, discrepancy, (evidence,), False)


def report_of(*records: DiscrepancyRecord) -> MunicipalDiscrepancyReport:
    return MunicipalDiscrepancyReport("28043", "discrepancia_trazados@1", (), records, False)


class ReportSource:
    def __init__(self, report: MunicipalDiscrepancyReport | None) -> None:
        self._report = report
        self.requests: list[str] = []

    def get_report(self, municipality_code: str) -> MunicipalDiscrepancyReport:
        self.requests.append(municipality_code)
        if self._report is None:
            raise DiscrepancyReportUnavailableError(municipality_code, "sin fichero")
        return self._report


class Boundaries:
    def __init__(self, bbox: BBox) -> None:
        self._geometry = rect(*bbox)

    def get_municipal_boundaries(self, ine_codes: Sequence[str]) -> list[MunicipalBoundary]:
        return [
            MunicipalBoundary(code, "Sintético", self._geometry, CADASTRE) for code in ine_codes
        ]


class ParcelsPort:
    """Devuelve las parcelas de `parcels` cuyo bbox toca el de la tesela, o lo que
    diga `fail` (una excepción por tesela)."""

    def __init__(
        self,
        parcels: Sequence[Parcel],
        fail: Callable[[BBox], Exception | None] = lambda _: None,
    ) -> None:
        self._parcels = list(parcels)
        self._fail = fail
        self.requests: list[BBox] = []

    def get_parcels_in_bbox(self, bbox: BBox) -> list[Parcel]:
        self.requests.append(bbox)
        error = self._fail(bbox)
        if error is not None:
            raise error
        found: list[Parcel] = []
        for item in self._parcels:
            xs = [x for ring in item.geometry.rings for x, _ in ring]
            ys = [y for ring in item.geometry.rings for _, y in ring]
            if (
                min(xs) <= bbox[2]
                and bbox[0] <= max(xs)
                and min(ys) <= bbox[3]
                and bbox[1] <= max(ys)
            ):
                found.append(item)
        return found


class Sink:
    def __init__(self) -> None:
        self.written: list[MunicipalCutCandidateReport] = []

    def write(self, report: MunicipalCutCandidateReport) -> None:
        self.written.append(report)
