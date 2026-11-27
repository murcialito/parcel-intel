"""Tests unitarios de `DetectCutCandidatesUseCase` (historia #127)."""

import dataclasses

import pytest

from parcel_intel.application.cut_signals import CadastralParcelSignalProvider
from parcel_intel.application.detect_cut_candidates import DetectCutCandidatesUseCase
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


def _use_case(
    report_source: ReportSource, port: ParcelsPort, sink: Sink
) -> DetectCutCandidatesUseCase:
    provider = CadastralParcelSignalProvider(
        lambda _code: port, Boundaries((-100, -100, 300, 100)), 900.0
    )
    return DetectCutCandidatesUseCase(report_source, [provider], sink)


def test_trazado_de_catastro_no_pide_parcelas() -> None:
    port, sink = ParcelsPort([parcel(ORDINARY, rect(0, -50, 200, 50))]), Sink()
    record = base_record("r1", line((0.0, 0.0), (200.0, 0.0)), "C-1", "catastro_vt")
    # Un trazado catastro_vt nunca es base de ign_red_transporte con sujeto ajeno a la señal:
    result = _use_case(ReportSource(report_of(record)), port, sink).execute("28043")
    assert port.requests == []
    assert result.candidates == ()
    assert sink.written == [result]


def test_informe_redactado_lanza_error_y_no_escribe() -> None:
    port, sink = ParcelsPort([]), Sink()
    redacted = dataclasses.replace(
        report_of(base_record("r1", line((0.0, 0.0), (100.0, 0.0)))), redacted=True
    )
    with pytest.raises(ValueError, match="interno"):
        _use_case(ReportSource(redacted), port, sink).execute("28043")
    assert sink.written == []


def test_base_record_ids_ordenados() -> None:
    sink = Sink()
    report = report_of(
        base_record("b", line((0.0, 0.0), (100.0, 0.0)), "VP-2"),
        base_record("a", line((0.0, 50.0), (100.0, 50.0)), "VP-1"),
    )
    result = _use_case(ReportSource(report), ParcelsPort([]), sink).execute("28043")
    assert result.base_record_ids == ("a", "b")
    assert result.discrepancy_criterion_id == "discrepancia_trazados@1"
