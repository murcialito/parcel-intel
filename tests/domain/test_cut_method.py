"""Tests unitarios del método de candidatos a corte (historia #126)."""

from datetime import date

import pytest

from parcel_intel.domain.cut_candidate import SignalReading, SignalRef
from parcel_intel.domain.cut_method import (
    CUT_METHOD,
    SIGNAL_WEIGHTS,
    build_cut_candidates,
)
from parcel_intel.domain.discrepancy import Discrepancy, SourceRef, TrailRef
from parcel_intel.domain.discrepancy_criterion import CRITERION
from parcel_intel.domain.discrepancy_report import (
    DiscrepancyRecord,
    MunicipalDiscrepancyReport,
    TrailEvidence,
)
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Provenance


def _src(kind: str) -> SourceRef:
    return SourceRef(
        kind,  # type: ignore[arg-type]
        Provenance(kind, "https://example.invalid", date(2026, 11, 26)),
        None,
    )


def _report(geometry: MultiLineGeometry | None) -> MunicipalDiscrepancyReport:
    subject = TrailRef("VP-1", _src("via_pecuaria_oficial"))
    shape = MultiLineGeometry(lines=(((0.0, 0.0), (100.0, 0.0)),), srid=25830)
    discrepancy = Discrepancy(
        "AUSENTE_EN_FUENTE", shape, subject, _src("ign_red_transporte"), (), 0.7, (), CRITERION
    )
    evidence = TrailEvidence(
        "VP-1", "via_pecuaria_oficial", subject.source.provenance, None, geometry
    )
    record = DiscrepancyRecord("r1", discrepancy, (evidence,), False)
    return MunicipalDiscrepancyReport("28043", "x@1", (), (record,), False)


def test_el_metodo_esta_en_version_1() -> None:
    assert (CUT_METHOD.identifier, CUT_METHOD.version) == ("candidato_corte", 1)


def test_senal_sin_peso_lanza_error_explicito() -> None:
    shape = MultiLineGeometry(lines=(((0.0, 0.0), (100.0, 0.0)),), srid=25830)
    signal = SignalRef("senal_desconocida", 1, "dentro_de_cierre")
    assert "senal_desconocida" not in SIGNAL_WEIGHTS
    reading = SignalReading(signal, ("apoya",) * 20, (), ())
    with pytest.raises(ValueError, match="senal_desconocida"):
        build_cut_candidates(_report(shape), {("via_pecuaria_oficial", "VP-1"): [reading]})


def test_senal_repetida_lanza_error() -> None:
    shape = MultiLineGeometry(lines=(((0.0, 0.0), (100.0, 0.0)),), srid=25830)
    signal = SignalRef("parcela_no_camino", 1, "dentro_de_cierre")
    reading = SignalReading(signal, ("apoya",) * 20, (), ())
    with pytest.raises(ValueError, match="dos veces"):
        build_cut_candidates(_report(shape), {("via_pecuaria_oficial", "VP-1"): [reading, reading]})


def test_registro_sin_geometria_del_trazado_lanza_error() -> None:
    with pytest.raises(ValueError, match="geometría"):
        build_cut_candidates(_report(None), {})
