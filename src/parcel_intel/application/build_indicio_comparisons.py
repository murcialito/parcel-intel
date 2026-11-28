"""Imágenes de comparación de los indicios publicables de un municipio -- historia #314,
ADR 0055 (decisión 3).

Lee el informe INTERNO de discrepancias (con las zonas de Catastro, que nunca se publica) y
pide las ortofotos de cada indicio publicable con el trazo `image_axis` (ADR 0054 §5), el
mismo que usará la tabla de convergencia."""

from parcel_intel.application.build_municipal_comparisons import BuildMunicipalComparisonsUseCase
from parcel_intel.domain.comparison_image import StretchComparison, StretchRequest
from parcel_intel.domain.convergence import image_axis, stretch_from_discrepancy
from parcel_intel.domain.published_discrepancy import is_publishable_indicio
from parcel_intel.ports.discrepancy_report_source import DiscrepancyReportSource
from parcel_intel.ports.errors import InternalReportRequiredError


class BuildIndicioComparisonsUseCase:
    def __init__(
        self, reports: DiscrepancyReportSource, comparisons: BuildMunicipalComparisonsUseCase
    ) -> None:
        self._reports = reports
        self._comparisons = comparisons

    def execute(self, municipality_code: str) -> tuple[StretchComparison, ...]:
        """Un tramo por indicio publicable, de id `record_id`. Un municipio sin indicios
        publicables escribe un manifiesto con cero tramos. Propaga
        `DiscrepancyReportUnavailableError`, `MunicipalWindowLimitError`,
        `ComparisonFailuresError`, etc."""
        report = self._reports.get_report(municipality_code)
        if report.redacted:
            raise InternalReportRequiredError(municipality_code)
        requests = tuple(
            StretchRequest(
                record.record_id,
                municipality_code,
                image_axis(stretch_from_discrepancy(record, municipality_code).shape),
            )
            for record in report.records
            if is_publishable_indicio(record.discrepancy)
        )
        return self._comparisons.execute(municipality_code, requests)
