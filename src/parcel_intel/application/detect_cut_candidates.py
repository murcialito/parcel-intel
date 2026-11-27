"""Candidatos a corte de un municipio (historia #127, ADR 0039 §6 y §8).

Combina el informe interno de discrepancias (#94) con las señales por muestra y
devuelve **indicios a verificar**, nunca dictámenes. Sin LLM, sin titularidad.
"""

import logging
from collections.abc import Sequence

from parcel_intel.application.cut_signals import CutSignalProvider
from parcel_intel.domain.cut_candidate import MunicipalCutCandidateReport, SignalReading
from parcel_intel.domain.cut_method import CUT_METHOD, build_cut_candidates, eligible_base_records
from parcel_intel.domain.discrepancy import TrailRef, trail_samples
from parcel_intel.domain.discrepancy_criterion import SourceKind
from parcel_intel.domain.discrepancy_report import DiscrepancyRecord
from parcel_intel.domain.geometry import TrailShape
from parcel_intel.ports.cut_candidate_sink import CutCandidateSink
from parcel_intel.ports.discrepancy_report_source import DiscrepancyReportSource
from parcel_intel.ports.errors import DiscrepancyReportUnavailableError

logger = logging.getLogger(__name__)


class DetectCutCandidatesUseCase:
    """Sin informe de discrepancias del municipio: se registra «municipio sin
    capas», no se escribe nada y no se llama a ningún proveedor. Que una señal no
    tenga datos produce `SignalRunSummary(status="sin_datos")` y veredictos
    `sin_dato`. Cualquier otro error se propaga (ADR 0030 §3)."""

    def __init__(
        self,
        reports: DiscrepancyReportSource,
        providers: Sequence[CutSignalProvider],
        sink: CutCandidateSink,
    ) -> None:
        self._reports = reports
        self._providers = tuple(providers)
        self._sink = sink

    def execute(self, municipality_code: str) -> MunicipalCutCandidateReport:
        try:
            report = self._reports.get_report(municipality_code)
        except DiscrepancyReportUnavailableError as error:
            logger.info("municipio sin capas: %s", error)
            return MunicipalCutCandidateReport(
                municipality_code=municipality_code,
                method=CUT_METHOD,
                discrepancy_criterion_id="",
                base_record_ids=(),
                signals=(),
                candidates=(),
            )

        by_trail: dict[tuple[SourceKind, str], list[DiscrepancyRecord]] = {}
        for record in eligible_base_records(report):
            subject = record.discrepancy.subject
            by_trail.setdefault((subject.source.kind, subject.trail_id), []).append(record)

        readings: dict[tuple[SourceKind, str], list[SignalReading]] = {}
        for provider in self._providers:
            applicable = {key: rs for key, rs in by_trail.items() if provider.applies_to(key[0])}
            zones: list[TrailShape] = [r.discrepancy.zone for rs in applicable.values() for r in rs]
            provider.prepare(municipality_code, zones)
            for key, records in applicable.items():
                shape = records[0].trails[0].geometry if records[0].trails else None
                if shape is None:
                    raise ValueError(
                        f"El registro base de {key[1]!r} no trae la geometría del trazado."
                    )
                subject_ref: TrailRef = records[0].discrepancy.subject
                reading = provider.read(municipality_code, subject_ref, trail_samples(shape))
                readings.setdefault(key, []).append(reading)

        candidates = build_cut_candidates(report, readings)
        result = MunicipalCutCandidateReport(
            municipality_code=report.municipality_code,
            method=CUT_METHOD,
            discrepancy_criterion_id=report.criterion_id,
            base_record_ids=tuple(sorted(r.record_id for rs in by_trail.values() for r in rs)),
            signals=tuple(provider.run_summary() for provider in self._providers),
            candidates=candidates,
        )
        self._sink.write(result)
        return result
