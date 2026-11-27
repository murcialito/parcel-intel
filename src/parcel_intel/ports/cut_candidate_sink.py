from typing import Protocol

from parcel_intel.domain.cut_candidate import MunicipalCutCandidateReport


class CutCandidateSink(Protocol):
    """Capacidad: escribir el informe de candidatos a corte de un municipio (#127)."""

    def write(self, report: MunicipalCutCandidateReport) -> None: ...
