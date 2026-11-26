from typing import Protocol

from parcel_intel.domain.discrepancy_report import MunicipalDiscrepancyReport


class DiscrepancyReportSource(Protocol):
    """Capacidad: leer el informe de discrepancias ya escrito de un municipio (#94).

    Sin informe: `DiscrepancyReportUnavailableError`. Un informe ilegible o con un
    formato que no se reconoce es un fallo real y no se convierte en "sin informe"."""

    def get_report(self, municipality_code: str) -> MunicipalDiscrepancyReport: ...
