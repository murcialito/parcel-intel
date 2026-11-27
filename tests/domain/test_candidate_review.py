"""Revisión de candidatos a corte en el dominio (historia #168). Datos sintéticos."""

import dataclasses
from datetime import UTC, date, datetime
from typing import Any

import pytest

from parcel_intel.domain.candidate_review import (
    MAX_NOTE_LENGTH,
    CandidateReview,
    InvalidCandidateReviewError,
    StaleCandidateApprovalError,
    candidate_fingerprint,
    check_candidate_approvals_current,
    reconcile,
)
from parcel_intel.domain.cut_candidate import CutCandidate
from parcel_intel.domain.discrepancy import Measurement
from parcel_intel.domain.geometry import MultiLineGeometry
from tests.fixtures.candidatos_revision import generar

WHEN = datetime(2026, 11, 28, 10, 0, tzinfo=UTC)
CANDIDATES = generar.candidates()
APPROVED = CANDIDATES["aprobado"]
CID = APPROVED.candidate_id


def _approved(candidate: CutCandidate = APPROVED, **changes: Any) -> CandidateReview:
    review = CandidateReview(
        candidate.candidate_id,
        "approved",
        reviewed_by="revisora",
        reviewed_at=WHEN,
        candidate_sha256=candidate_fingerprint(candidate),
    )
    return dataclasses.replace(review, **changes) if changes else review


# -- CandidateReview -------------------------------------------------------------------


def test_revisiones_validas() -> None:
    CandidateReview(CID, "proposed")
    CandidateReview(CID, "proposed", review_note="Pendiente de imágenes.")
    _approved()
    _approved(review_note="Visto con la ortofoto.")
    CandidateReview(CID, "rejected", reviewed_by="r", reviewed_at=WHEN, review_note="Se ve.")
    CandidateReview(
        CID,
        "rejected",
        reviewed_by="r",
        reviewed_at=WHEN,
        review_note="Se ve.",
        candidate_sha256="f" * 64,
    )


@pytest.mark.parametrize("candidate_id", ["", "ABCDEF0123456789", "abc", "g" * 16, "a" * 17])
def test_id_no_valido_no_se_repite_en_el_mensaje(candidate_id: str) -> None:
    with pytest.raises(InvalidCandidateReviewError) as error:
        CandidateReview(candidate_id, "proposed")
    assert str(error.value).startswith("revisión:")
    if candidate_id:
        assert candidate_id not in str(error.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"reviewed_by": None},
        {"reviewed_by": "-mal"},
        {"reviewed_at": None},
        {"reviewed_at": datetime(2026, 11, 28, 10, 0)},
        {"candidate_sha256": None},
        {"candidate_sha256": "A" * 64},
        {"status": "otro"},
    ],
)
def test_aprobado_incompleto(changes: dict[str, Any]) -> None:
    with pytest.raises(InvalidCandidateReviewError) as error:
        _approved(**changes)
    assert str(error.value).startswith(f"{CID}:")


@pytest.mark.parametrize(
    "changes",
    [
        {"reviewed_by": None},
        {"reviewed_at": None},
        {"review_note": None},
        {"review_note": " "},
        {"candidate_sha256": "corto"},
    ],
)
def test_rechazado_incompleto(changes: dict[str, Any]) -> None:
    base = CandidateReview(CID, "rejected", reviewed_by="r", reviewed_at=WHEN, review_note="n")
    with pytest.raises(InvalidCandidateReviewError, match=CID):
        dataclasses.replace(base, **changes)


@pytest.mark.parametrize(
    "changes",
    [{"reviewed_by": "r"}, {"reviewed_at": WHEN}, {"candidate_sha256": "0" * 64}],
)
def test_propuesto_no_admite_datos_de_revision(changes: dict[str, Any]) -> None:
    with pytest.raises(InvalidCandidateReviewError, match="propuesto"):
        dataclasses.replace(CandidateReview(CID, "proposed"), **changes)


@pytest.mark.parametrize(
    ("note", "secret"),
    [
        ("x" * (MAX_NOTE_LENGTH + 1), "x" * (MAX_NOTE_LENGTH + 1)),
        ("Junto a 99999A00109102", "99999A00109102"),
        ("ver https://example.invalid/?poligono=9", "poligono=9"),
        ("Parece una USURPACION", "USURPACION"),
        ("Lo cerró el titular", "titular"),
        ("", ""),
    ],
)
def test_nota_no_valida_sin_repetir_el_valor(note: str, secret: str) -> None:
    with pytest.raises(InvalidCandidateReviewError) as error:
        CandidateReview(CID, "proposed", review_note=note)
    if secret:
        assert secret not in str(error.value)


def test_nota_de_500_caracteres_vale() -> None:
    CandidateReview(CID, "proposed", review_note="x" * MAX_NOTE_LENGTH)


# -- Huella ------------------------------------------------------------------------------


def test_huella_64_hex_y_estable() -> None:
    fingerprint = candidate_fingerprint(APPROVED)
    assert len(fingerprint) == 64 and set(fingerprint) <= set("0123456789abcdef")
    assert candidate_fingerprint(dataclasses.replace(APPROVED)) == fingerprint


def _changed(**changes: Any) -> CutCandidate:
    return dataclasses.replace(APPROVED, **changes)


@pytest.mark.parametrize(
    "variant",
    [
        _changed(confidence=0.51),
        _changed(evidence=(Measurement("longitud_tramo_m", 1.0, "m"),)),
        _changed(signals=(dataclasses.replace(APPROVED.signals[0], no_data_fraction=0.1),)),
        _changed(
            subject=dataclasses.replace(
                APPROVED.subject,
                source=dataclasses.replace(APPROVED.subject.source, data_date=date(2020, 1, 1)),
            )
        ),
        _changed(subject=dataclasses.replace(APPROVED.subject, trail_id="VP-OTRO")),
        _changed(
            stretch=MultiLineGeometry(
                ((APPROVED.stretch.lines[0][0], (460200.0, 4436000.01)),), 25830
            )
        ),
    ],
)
def test_la_huella_cambia_con_lo_que_se_juzga(variant: CutCandidate) -> None:
    assert candidate_fingerprint(variant) != candidate_fingerprint(APPROVED)


def test_la_huella_no_cambia_con_procedencia_ni_registros_base_ni_ruido_bajo_redondeo() -> None:
    later = dataclasses.replace(
        APPROVED.subject.source.provenance, url="https://example.invalid/otra"
    )
    variants = [
        _changed(discrepancy_ids=("ffffffffffffffff",)),
        _changed(
            subject=dataclasses.replace(
                APPROVED.subject,
                source=dataclasses.replace(APPROVED.subject.source, provenance=later),
            )
        ),
        _changed(signals=(dataclasses.replace(APPROVED.signals[0], provenance=()),)),
        _changed(confidence=0.5000001),
    ]
    for variant in variants:
        assert candidate_fingerprint(variant) == candidate_fingerprint(APPROVED)


# -- reconcile ---------------------------------------------------------------------------


def test_reconcile_estados_huerfanas_y_orden() -> None:
    report = generar.report()
    stale = generar.stale_variant(CANDIDATES["caducado"])
    reviews = [
        _approved(),
        CandidateReview(
            CANDIDATES["rechazado"].candidate_id,
            "rejected",
            reviewed_by="r",
            reviewed_at=WHEN,
            review_note="Se ve.",
        ),
        CandidateReview(CANDIDATES["propuesto"].candidate_id, "proposed"),
        _approved(stale),
        CandidateReview("0" * 16, "proposed"),
    ]
    state = reconcile(report, list(reversed(reviews)))
    by_id = {item.candidate.candidate_id: item for item in state.candidates}
    assert [c.candidate.candidate_id for c in state.candidates] == sorted(by_id)
    assert by_id[CID].status == "approved"
    assert by_id[CANDIDATES["rechazado"].candidate_id].status == "rejected"
    assert by_id[CANDIDATES["propuesto"].candidate_id].status == "proposed"
    assert by_id[CANDIDATES["caducado"].candidate_id].status == "stale"
    assert by_id[CANDIDATES["sin_revision"].candidate_id].review is None
    assert by_id[CANDIDATES["sin_revision"].candidate_id].status == "proposed"
    assert [o.candidate_id for o in state.orphans] == ["0" * 16]
    assert state.stale_ids() == (CANDIDATES["caducado"].candidate_id,)
    assert state.approved() == (APPROVED,)
    assert not state.is_current()
    with pytest.raises(StaleCandidateApprovalError) as error:
        check_candidate_approvals_current(state)
    assert error.value.stale_ids == (CANDIDATES["caducado"].candidate_id,)
    assert error.value.orphan_ids == ("0" * 16,)


def test_reconcile_vigente_y_vacio() -> None:
    state = reconcile(generar.report(), [_approved()])
    assert state.is_current()
    check_candidate_approvals_current(state)
    empty = reconcile(dataclasses.replace(generar.report(), candidates=()), [])
    assert empty.candidates == () and empty.orphans == () and empty.is_current()


def test_rechazado_no_caduca() -> None:
    rejected = CandidateReview(
        CID,
        "rejected",
        reviewed_by="r",
        reviewed_at=WHEN,
        review_note="n",
        candidate_sha256="f" * 64,
    )
    assert reconcile(generar.report(), [rejected]).is_current()


def test_reconcile_rechaza_ids_repetidos() -> None:
    with pytest.raises(InvalidCandidateReviewError, match=f"{CID}: candidate_id repetido"):
        reconcile(generar.report(), [_approved(), CandidateReview(CID, "proposed")])
