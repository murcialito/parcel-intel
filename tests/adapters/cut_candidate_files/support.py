"""Informes de candidatos sintéticos para los tests de #128. Nada es real."""

import dataclasses
from datetime import date

from parcel_intel.application.cut_signals import CadastralParcelSignalProvider
from parcel_intel.application.detect_cut_candidates import DetectCutCandidatesUseCase
from parcel_intel.domain.cut_candidate import CutCandidate, MunicipalCutCandidateReport
from parcel_intel.domain.discrepancy_report import MunicipalDiscrepancyReport
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Provenance, Redistribution
from tests.cut_signal_support import (
    ORDINARY,
    Boundaries,
    ParcelsPort,
    ReportSource,
    Sink,
    base_record,
    line,
    parcel,
    rect,
    report_of,
)


def discrepancy_report(code: str = "28043") -> MunicipalDiscrepancyReport:
    record = base_record("r1", line((0.0, 0.0), (200.0, 0.0)))
    return dataclasses.replace(report_of(record), municipality_code=code)


class PerMunicipalityReports:
    """`DiscrepancyReportSource` que sirve el mismo informe sintético para cualquier INE."""

    def __init__(self, missing: tuple[str, ...] = (), broken: tuple[str, ...] = ()) -> None:
        self._missing = missing
        self._broken = broken
        self._inner = ReportSource(None)

    def get_report(self, municipality_code: str) -> MunicipalDiscrepancyReport:
        if municipality_code in self._broken:
            raise RuntimeError("fallo simulado")
        if municipality_code in self._missing:
            return ReportSource(None).get_report(municipality_code)
        return discrepancy_report(municipality_code)


def use_case_over(
    reports: PerMunicipalityReports | ReportSource, sink: Sink, port: ParcelsPort
) -> DetectCutCandidatesUseCase:
    provider = CadastralParcelSignalProvider(
        lambda _code: port, Boundaries((-100, -100, 300, 100)), 900.0
    )
    return DetectCutCandidatesUseCase(reports, [provider], sink)


def sample_report(code: str = "28043") -> MunicipalCutCandidateReport:
    """Informe real del caso de uso sobre el ejemplo sintético del ADR 0039 §4
    (una parcela ordinaria cubre el centro del trazado)."""
    sink = Sink()
    port = ParcelsPort([parcel(ORDINARY, rect(50, -50, 150, 50))])
    result = use_case_over(ReportSource(discrepancy_report(code)), sink, port).execute(code)
    assert result.candidates, "el ejemplo sintético debe producir al menos un candidato"
    return dataclasses.replace(
        result, candidates=tuple(_on_centimetre_grid(c) for c in result.candidates)
    )


def _on_centimetre_grid(candidate: CutCandidate) -> CutCandidate:
    """El fichero guarda las coordenadas a 0,01 m: el original ya está en esa rejilla."""
    lines = tuple(
        tuple((round(x, 2), round(y, 2)) for x, y in part) for part in candidate.stretch.lines
    )
    return dataclasses.replace(
        candidate, stretch=MultiLineGeometry(lines=lines, srid=candidate.stretch.srid)
    )


CADASTRE_INTERNAL = Provenance(
    "Catastro (sintético)",
    "https://example.invalid/catastro",
    date(2026, 11, 26),
    "licencia sintética",
    Redistribution.INTERNAL_ONLY,
)
