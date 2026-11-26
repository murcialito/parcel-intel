from collections.abc import Sequence

from parcel_intel.application.detect_discrepancies import DetectDiscrepanciesUseCase
from parcel_intel.domain.discrepancy_report import MunicipalDiscrepancyReport, TrailLayer
from parcel_intel.domain.trail import SourceKind
from parcel_intel.ports.errors import TrailLayerUnavailableError
from tests.trail_factories import MUNICIPALITY, line_shape, make_layer, make_trail


class _Port:
    def __init__(self, layers: Sequence[TrailLayer]) -> None:
        self._layers = {layer.source: layer for layer in layers}
        self.requests: list[tuple[SourceKind, str]] = []

    def get_layer(self, source: SourceKind, municipality_code: str) -> TrailLayer:
        self.requests.append((source, municipality_code))
        if source not in self._layers:
            raise TrailLayerUnavailableError(source, municipality_code, f"sin fichero de {source}")
        return self._layers[source]


class _Sink:
    def __init__(self, order: list[str], name: str) -> None:
        self.written: list[MunicipalDiscrepancyReport] = []
        self._order = order
        self._name = name

    def write(self, report: MunicipalDiscrepancyReport) -> None:
        self.written.append(report)
        self._order.append(self._name)


def test_escribe_completo_en_interno_y_redactado_en_publico() -> None:
    layers = [
        make_layer("catastro_vt", [make_trail("C1", "catastro_vt", line_shape((0, 0), (200, 0)))]),
        make_layer(
            "ign_red_transporte",
            [make_trail("R1", "ign_red_transporte", line_shape((0, 12.5), (200, 12.5)))],
        ),
    ]
    order: list[str] = []
    internal, public = _Sink(order, "interno"), _Sink(order, "publico")

    report = DetectDiscrepanciesUseCase(_Port(layers), internal, public).execute(MUNICIPALITY)

    assert internal.written == [report] and report.redacted is False
    [published] = public.written
    assert published.redacted is True
    assert published.records[0].trails[0].geometry is None
    assert report.records[0].trails[0].geometry is not None
    assert order == ["interno", "publico"]


def test_motivo_de_la_ausencia_viene_del_error_del_port() -> None:
    port = _Port([])
    report = DetectDiscrepanciesUseCase(port, _Sink([], "i"), _Sink([], "p")).execute(MUNICIPALITY)

    assert report.records == ()
    assert {s.missing_reason for s in report.layers} == {
        f"sin fichero de {s.source}" for s in report.layers
    }
    assert len(port.requests) == 5
