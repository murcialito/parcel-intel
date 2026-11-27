"""Lector estricto de `curated/candidatos/<ine>/revision.json` (historia #168). Sintético."""

import json
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.adapters.curated_candidates import CuratedCandidateReviewFiles
from parcel_intel.ports.errors import CandidateReviewFileError
from tests.fixtures.candidatos_revision import generar

INE = generar.INE
FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "candidatos_revision" / "curated"
CID = "0123456789abcdef"


def _write(root: Path, document: object, code: str = INE) -> CuratedCandidateReviewFiles:
    directory = root / code
    directory.mkdir(parents=True, exist_ok=True)
    text = document if isinstance(document, str) else json.dumps(document, ensure_ascii=False)
    (directory / "revision.json").write_text(text, encoding="utf-8")
    return CuratedCandidateReviewFiles(root)


def _doc(*revisions: object) -> dict[str, Any]:
    return {"municipio": INE, "revisiones": list(revisions)}


def test_lee_la_fixture() -> None:
    reviews = CuratedCandidateReviewFiles(FIXTURE_ROOT).reviews(INE)
    assert [r.status for r in reviews] == [
        "approved",
        "rejected",
        "proposed",
        "approved",
        "approved",
    ]
    assert reviews[0].reviewed_by == generar.REVIEWER
    assert reviews[0].reviewed_at is not None and reviews[0].reviewed_at.utcoffset() is not None
    assert reviews[2].review_note == "Pendiente de imágenes."


def test_sin_fichero_o_sin_directorio_devuelve_vacio(tmp_path: Path) -> None:
    files = CuratedCandidateReviewFiles(tmp_path / "no-existe")
    assert files.reviews(INE) == ()
    (tmp_path / INE).mkdir()
    assert CuratedCandidateReviewFiles(tmp_path).reviews(INE) == ()


def test_lista_vacia_y_null_como_ausente(tmp_path: Path) -> None:
    assert _write(tmp_path, _doc()).reviews(INE) == ()
    reviews = _write(
        tmp_path, _doc({"candidate_id": CID, "review": "propuesto", "reviewed_by": None})
    ).reviews(INE)
    assert reviews[0].status == "proposed" and reviews[0].reviewed_by is None


def test_codigo_no_valido(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        CuratedCandidateReviewFiles(tmp_path).reviews("2804")


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ("￾{", "no es JSON válido"),
        ("[]", "objeto JSON"),
        ({"municipio": INE}, "faltan revisiones"),
        ({"municipio": INE, "revisiones": [], "otra": 1, "mas": 2}, "2 claves desconocidas"),
        ({"municipio": "28013", "revisiones": []}, "municipio no coincide"),
        ({"municipio": INE, "revisiones": {}}, "revisiones debe ser una lista"),
        (_doc("texto"), "revisión 1 debe ser un objeto"),
        (_doc({"review": "propuesto"}), "revisión 1: faltan candidate_id"),
        (_doc({"candidate_id": 7, "review": "propuesto"}), "revisión 1: candidate_id no cumple"),
        (_doc({"candidate_id": CID}), f"{CID}: faltan review"),
        (_doc({"candidate_id": CID, "review": "propuesto", "x": 1}), f"{CID}: 1 claves"),
        (_doc({"candidate_id": CID, "review": "hecho"}), f"{CID}: review no reconocido"),
        (_doc({"candidate_id": CID, "review": 1}), f"{CID}: review no reconocido"),
        (
            _doc({"candidate_id": CID, "review": "propuesto", "review_note": 3}),
            f"{CID}: review_note debe ser texto",
        ),
        (
            _doc({"candidate_id": CID, "review": "aprobado", "reviewed_at": "hoy"}),
            f"{CID}: reviewed_at no es un instante ISO 8601",
        ),
        (
            _doc({"candidate_id": CID, "review": "aprobado"}),
            f"{CID}: una revisión aprobado necesita reviewed_by",
        ),
        (
            _doc(
                {"candidate_id": CID, "review": "propuesto"},
                {"candidate_id": CID, "review": "propuesto"},
            ),
            f"{CID}: candidate_id repetido",
        ),
        (
            _doc({"candidate_id": CID, "review": "propuesto", "review_note": "99999A00109102"}),
            "contiene una referencia catastral o un localizador de parcela",
        ),
        (
            _doc({"candidate_id": CID, "review": "propuesto", "review_note": "?refcat=1"}),
            "contiene una referencia catastral o un localizador de parcela",
        ),
    ],
)
def test_formato_cerrado(tmp_path: Path, document: object, expected: str) -> None:
    files = _write(tmp_path, document)
    with pytest.raises(CandidateReviewFileError) as error:
        files.reviews(INE)
    assert expected in str(error.value)
    assert "revision.json" in str(error.value)


def test_no_utf8(tmp_path: Path) -> None:
    directory = tmp_path / INE
    directory.mkdir()
    (directory / "revision.json").write_bytes(b"\xff\xfe")
    with pytest.raises(CandidateReviewFileError, match="no es UTF-8"):
        CuratedCandidateReviewFiles(tmp_path).reviews(INE)


def test_los_mensajes_no_repiten_valores(tmp_path: Path) -> None:
    secret = "valor-secreto"
    for document in (
        {"municipio": INE, "revisiones": [], secret: 1},
        _doc({"candidate_id": secret, "review": "propuesto"}),
        _doc({"candidate_id": CID, "review": secret}),
        _doc({"candidate_id": CID, "review": "propuesto", secret: 1}),
        _doc({"candidate_id": CID, "review": "aprobado", "reviewed_by": secret + "!"}),
        _doc({"candidate_id": CID, "review": "aprobado", "reviewed_at": secret}),
        _doc({"candidate_id": CID, "review": "propuesto", "review_note": secret + " ilegal"}),
        {"municipio": secret, "revisiones": []},
    ):
        files = _write(tmp_path, document)
        with pytest.raises(CandidateReviewFileError) as error:
            files.reviews(INE)
        assert secret not in str(error.value)
