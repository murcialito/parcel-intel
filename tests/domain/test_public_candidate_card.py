"""Tests unitarios de la ficha pública del candidato (historia #169)."""

import dataclasses
from datetime import date
from typing import Any

import pytest

from parcel_intel.domain.cut_candidate import CutCandidate, SignalRef, SignalSupport
from parcel_intel.domain.cut_method import CUT_METHOD
from parcel_intel.domain.discrepancy import Measurement, SourceRef, TrailRef
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.public_candidate_card import (
    MissingCatastroDateError,
    build_candidate_card,
)

_SOURCE = SourceRef(
    "via_pecuaria_oficial",
    Provenance(
        "vp",
        "https://example.invalid/vp",
        date(2026, 11, 26),
        "CC BY 4.0",
        Redistribution.PUBLIC,
    ),
    date(2019, 5, 1),
)


def _catastro(day: int, source: str = "catastro_wfs_cp") -> Provenance:
    return Provenance(source, "https://example.invalid/cp", date(2026, 11, day), "INSPIRE v1.0")


def candidate(
    *,
    fraction: float = 0.5,
    provenance: tuple[Provenance, ...] = (),
    with_signal: bool = True,
    length: float = 120.4,
    **changes: Any,
) -> CutCandidate:
    signals = (
        (
            SignalSupport(
                SignalRef("parcela_no_camino", 1, "dentro_de_cierre"), fraction, 0.0, provenance
            ),
        )
        if with_signal
        else (SignalSupport(SignalRef("visibilidad_ortofoto", 1, "no_se_distingue"), 1.0, 0.0, ()),)
    )
    base = CutCandidate(
        candidate_id="0" * 16,
        municipality_code="28043",
        subject=TrailRef("VP-1", _SOURCE),
        discrepancy_ids=("r1",),
        stretch=MultiLineGeometry(lines=(((0.0, 0.0), (30.0, 0.0)),), srid=25830),
        conditions=("dentro_de_cierre",) if with_signal else ("no_se_distingue",),
        signals=signals,
        confidence=0.4,
        evidence=(Measurement("longitud_tramo_m", length, "m"),),
        method=CUT_METHOD,
    )
    return dataclasses.replace(base, **changes)


def test_porcentaje_y_longitud_se_redondean_a_entero() -> None:
    card = build_candidate_card(candidate(fraction=0.625, length=99.5, provenance=(_catastro(26),)))
    assert "tramo de 100 m" in card.text
    assert "el 63 % del tramo" in card.text


def test_con_varias_entradas_la_fecha_es_la_mas_reciente() -> None:
    card = build_candidate_card(candidate(provenance=(_catastro(24), _catastro(26), _catastro(25))))
    assert "consultados el 26/11/2026" in card.text
    assert "consultado el 26/11/2026" in card.warning


def test_sin_entrada_de_catastro_se_lanza_error() -> None:
    with pytest.raises(MissingCatastroDateError):
        build_candidate_card(candidate(provenance=(_catastro(26, source="otra"),)))


def test_uso_interno_conserva_la_fuente_no_verificada() -> None:
    sin_licencia = dataclasses.replace(
        _SOURCE, provenance=dataclasses.replace(_SOURCE.provenance, license=None)
    )
    cand = candidate(with_signal=False, subject=TrailRef("VP-1", sin_licencia))
    interna = build_candidate_card(cand, for_publication=False)
    assert len(interna.sources) == 1
    assert interna.omission_notice is None
