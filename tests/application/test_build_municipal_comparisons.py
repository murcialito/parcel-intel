from collections.abc import Sequence
from datetime import date

import pytest

from parcel_intel.application.build_comparison_images import BuildComparisonImagesUseCase
from parcel_intel.application.build_municipal_comparisons import (
    BuildMunicipalComparisonsUseCase,
    ComparisonFailuresError,
    MunicipalWindowLimitError,
)
from parcel_intel.domain.comparison_image import (
    DegenerateStretchError,
    StretchComparison,
    StretchRequest,
)
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.orthophoto import HistoricalVintage, Orthophoto, OrthophotoWindow
from parcel_intel.domain.provenance import Provenance
from parcel_intel.ports.errors import OrthophotoNotCoveredError


class _Orthophotos:
    def __init__(self, failing: bool = False, uncovered: bool = False) -> None:
        self.calls = 0
        self._failing = failing
        self._uncovered = uncovered

    def get_orthophoto_window(
        self, window: OrthophotoWindow, vintage: HistoricalVintage
    ) -> Orthophoto:
        self.calls += 1
        if self._failing:
            raise ConnectionError("sin red")
        if self._uncovered:
            raise OrthophotoNotCoveredError(vintage)
        return Orthophoto(
            b"\xff\xd8x", vintage, Provenance("pnoa-historico", "u", date(2026, 1, 1))
        )


class _Sink:
    def __init__(self) -> None:
        self.written: list[tuple[str, Sequence[StretchComparison]]] = []

    def write(self, municipality_code: str, comparisons: Sequence[StretchComparison]) -> None:
        self.written.append((municipality_code, comparisons))


def _request(stretch_id: str, x: float = 470000.0, length: float = 80.0) -> StretchRequest:
    line = MultiLineGeometry((((x, 4440000.0), (x + length, 4440000.0)),), 25830)
    return StretchRequest(stretch_id, "28043", line)


def _use_case(orthophotos: _Orthophotos, sink: _Sink) -> BuildMunicipalComparisonsUseCase:
    return BuildMunicipalComparisonsUseCase(BuildComparisonImagesUseCase(orthophotos), sink)


def test_escribe_los_tramos_ordenados_por_id() -> None:
    sink = _Sink()
    results = _use_case(_Orthophotos(), sink).execute(
        "28043", [_request("b" * 16), _request("a" * 16)]
    )
    assert [r.stretch_id for r in results] == ["a" * 16, "b" * 16]
    assert sink.written == [("28043", results)]


def test_el_tope_corta_antes_de_pedir() -> None:
    orthophotos, sink = _Orthophotos(), _Sink()
    requests = [_request(f"{i:016x}", x=470000.0 + 1000 * i) for i in range(401)]
    with pytest.raises(MunicipalWindowLimitError) as error:
        _use_case(orthophotos, sink).execute("28043", requests)
    assert error.value.windows == 401
    assert orthophotos.calls == 0 and sink.written == []


def test_400_ventanas_justas_pasan() -> None:
    sink = _Sink()
    requests = [_request(f"{i:016x}", x=470000.0 + 1000 * i) for i in range(400)]
    _use_case(_Orthophotos(), sink).execute("28043", requests)
    assert len(sink.written) == 1


def test_un_fallo_no_llama_al_sink() -> None:
    sink = _Sink()
    with pytest.raises(ComparisonFailuresError) as error:
        _use_case(_Orthophotos(failing=True), sink).execute("28043", [_request("a" * 16)])
    assert len(error.value.failures) == 5
    assert error.value.failures[0] == ("a" * 16, "1956-1957", "ConnectionError")
    assert sink.written == []


def test_sin_cobertura_y_tramo_largo_no_son_fallo() -> None:
    sink = _Sink()
    largo = _request("b" * 16, length=2000.0)
    results = _use_case(_Orthophotos(uncovered=True), sink).execute(
        "28043", [_request("a" * 16), largo]
    )
    assert results[1].status == "tramo_demasiado_largo"
    assert all(o.reason == "sin_cobertura" for o in results[0].windows[0].omitted)
    assert len(sink.written) == 1


def test_tramo_degenerado_no_pide_nada() -> None:
    orthophotos, sink = _Orthophotos(), _Sink()
    punto = StretchRequest("a" * 16, "28043", MultiLineGeometry((((1.0, 1.0),),), 25830))
    with pytest.raises(DegenerateStretchError):
        _use_case(orthophotos, sink).execute("28043", [_request("b" * 16), punto])
    assert orthophotos.calls == 0 and sink.written == []


def test_ids_repetidos_y_municipio_ajeno_se_rechazan() -> None:
    sink = _Sink()
    with pytest.raises(ValueError, match="repetidos"):
        _use_case(_Orthophotos(), sink).execute("28043", [_request("a" * 16), _request("a" * 16)])
    with pytest.raises(ValueError, match="municipio"):
        _use_case(_Orthophotos(), sink).execute("28013", [_request("a" * 16)])
    assert sink.written == []
