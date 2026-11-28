"""Caso de uso de #314. Datos SINTÉTICOS (`tests/indicio_comparison_support.py`)."""

from collections.abc import Sequence

import pytest

from parcel_intel.application.build_comparison_images import BuildComparisonImagesUseCase
from parcel_intel.application.build_indicio_comparisons import BuildIndicioComparisonsUseCase
from parcel_intel.application.build_municipal_comparisons import BuildMunicipalComparisonsUseCase
from parcel_intel.domain.comparison_image import StretchComparison
from parcel_intel.domain.convergence import image_axis
from parcel_intel.domain.discrepancy_policy import redact_for_publication
from parcel_intel.domain.discrepancy_report import MunicipalDiscrepancyReport
from parcel_intel.domain.orthophoto import HistoricalVintage, Orthophoto, OrthophotoWindow
from parcel_intel.ports.errors import (
    DiscrepancyReportUnavailableError,
    InternalReportRequiredError,
)
from tests.indicio_comparison_support import INE, X0, Y0, line, record, report, strip


class _Reports:
    def __init__(self, rep: MunicipalDiscrepancyReport | None) -> None:
        self._rep = rep

    def get_report(self, municipality_code: str) -> MunicipalDiscrepancyReport:
        if self._rep is None:
            raise DiscrepancyReportUnavailableError(municipality_code, "no hay")
        return self._rep


class _Orthophotos:
    def __init__(self) -> None:
        self.calls = 0

    def get_orthophoto_window(
        self, window: OrthophotoWindow, vintage: HistoricalVintage
    ) -> Orthophoto:
        self.calls += 1
        raise AssertionError("no se debe pedir ninguna imagen en estas pruebas")


class _Sink:
    def __init__(self) -> None:
        self.written: list[tuple[str, Sequence[StretchComparison]]] = []

    def write(self, municipality_code: str, comparisons: Sequence[StretchComparison]) -> None:
        self.written.append((municipality_code, comparisons))


def _use_case(
    rep: MunicipalDiscrepancyReport | None, sink: _Sink
) -> BuildIndicioComparisonsUseCase:
    comparisons = BuildMunicipalComparisonsUseCase(
        BuildComparisonImagesUseCase(_Orthophotos()), sink
    )
    return BuildIndicioComparisonsUseCase(_Reports(rep), comparisons)


def test_municipio_sin_indicios_publicables_escribe_manifiesto_vacio() -> None:
    sink = _Sink()
    rep = report(record("a" * 16, line(X0, Y0), subject_kind="catastro_vt"))
    assert _use_case(rep, sink).execute(INE) == ()
    assert sink.written == [(INE, ())]


def test_informe_redactado_se_rechaza_sin_escribir() -> None:
    sink = _Sink()
    rep = redact_for_publication(report(record("a" * 16, strip(X0, Y0))))
    with pytest.raises(InternalReportRequiredError):
        _use_case(rep, sink).execute(INE)
    assert sink.written == []


def test_sin_informe_propaga_el_error() -> None:
    with pytest.raises(DiscrepancyReportUnavailableError):
        _use_case(None, _Sink()).execute(INE)


def test_el_trazo_de_una_franja_es_su_pseudo_eje_y_no_la_franja() -> None:
    zone = strip(X0, Y0)
    assert image_axis(zone).lines != zone.rings
