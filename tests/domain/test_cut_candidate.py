"""Tests unitarios de la entidad `CutCandidate` (historia #126)."""

import dataclasses
from datetime import date
from typing import Any

import pytest

from parcel_intel.domain.cut_candidate import CutCandidate, SignalRef, SignalSupport
from parcel_intel.domain.cut_method import CUT_METHOD
from parcel_intel.domain.discrepancy import SourceRef, TrailRef
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Provenance

_SOURCE = SourceRef(
    "via_pecuaria_oficial", Provenance("vp", "https://example.invalid", date(2026, 11, 26)), None
)
_SIGNAL = SignalRef("parcela_no_camino", 1, "dentro_de_cierre")


def _candidate(**changes: Any) -> CutCandidate:
    base = CutCandidate(
        candidate_id="0" * 16,
        municipality_code="28043",
        subject=TrailRef("VP-1", _SOURCE),
        discrepancy_ids=("r1",),
        stretch=MultiLineGeometry(lines=(((0.0, 0.0), (30.0, 0.0)),), srid=25830),
        conditions=("dentro_de_cierre",),
        signals=(SignalSupport(_SIGNAL, 1.0, 0.0, ()),),
        confidence=0.4,
        evidence=(),
        method=CUT_METHOD,
    )
    return dataclasses.replace(base, **changes)


def test_candidato_valido_y_congelado() -> None:
    candidate = _candidate()
    with pytest.raises(dataclasses.FrozenInstanceError):
        candidate.confidence = 0.9  # type: ignore[misc]


def test_confianza_en_los_extremos_es_valida() -> None:
    assert _candidate(confidence=0.0).confidence == 0.0
    assert _candidate(confidence=1.0).confidence == 1.0


def test_linea_de_un_solo_punto_cuenta_como_tramo_vacio() -> None:
    with pytest.raises(ValueError, match="vacío"):
        _candidate(stretch=MultiLineGeometry(lines=(((0.0, 0.0),),), srid=25830))
