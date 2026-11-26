from parcel_intel.domain.discrepancy_detection import (
    CANONICAL_SOURCES,
    detect_municipal_discrepancies,
)
from parcel_intel.domain.discrepancy_policy import redact_for_publication
from parcel_intel.domain.discrepancy_report import (
    LayerStatus,
    LayerSummary,
    MunicipalDiscrepancyReport,
    TrailLayer,
)
from parcel_intel.ports.discrepancy_sink import DiscrepancyReportSink
from parcel_intel.ports.errors import TrailLayerUnavailableError
from parcel_intel.ports.trail_layer import MunicipalTrailLayerPort


class DetectDiscrepanciesUseCase:
    """Detecta las discrepancias entre las capas de trazados de un municipio.

    Indicios a verificar, no dictámenes. Escribe el informe completo en el sink
    interno y el redactado (sin geometría de fuentes no redistribuibles) en el
    público. Una capa ausente se registra con su motivo y no hace fallar el
    caso de uso; cualquier otro error del port sí lo hace."""

    def __init__(
        self,
        layers: MunicipalTrailLayerPort,
        internal_sink: DiscrepancyReportSink,
        public_sink: DiscrepancyReportSink,
    ) -> None:
        self._layers = layers
        self._internal_sink = internal_sink
        self._public_sink = public_sink

    def execute(self, municipality_code: str) -> MunicipalDiscrepancyReport:
        available: list[TrailLayer] = []
        missing: list[LayerSummary] = []
        for source in CANONICAL_SOURCES:
            try:
                available.append(self._layers.get_layer(source, municipality_code))
            except TrailLayerUnavailableError as error:
                missing.append(
                    LayerSummary(
                        source=source,
                        status=LayerStatus.AUSENTE,
                        provenance=None,
                        trail_count=0,
                        empty_geometry_ids=(),
                        missing_reason=error.reason,
                    )
                )
        report = detect_municipal_discrepancies(municipality_code, available, missing)
        self._internal_sink.write(report)
        self._public_sink.write(redact_for_publication(report))
        return report
