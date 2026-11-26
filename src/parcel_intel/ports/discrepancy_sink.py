from typing import Protocol

from parcel_intel.domain.discrepancy_report import MunicipalDiscrepancyReport


class DiscrepancyReportSink(Protocol):
    """Capacidad: guardar el informe de discrepancias de un municipio."""

    def write(self, report: MunicipalDiscrepancyReport) -> None: ...
