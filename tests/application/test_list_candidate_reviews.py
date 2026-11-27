"""Caso de uso del listado de revisiones de candidatos (historia #168). Dobles en memoria."""

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from parcel_intel.application.list_candidate_reviews import ListCandidateReviewsUseCase
from parcel_intel.domain.candidate_review import (
    CandidateReview,
    ManifestImageState,
    candidate_fingerprint,
)
from parcel_intel.domain.cut_candidate import MunicipalCutCandidateReport
from parcel_intel.ports.errors import (
    CandidateReviewFileError,
    ComparisonManifestFileError,
    CutCandidateFileError,
)
from tests.fixtures.candidatos_revision import generar

INE = generar.INE
CANDIDATES = generar.candidates()
APPROVED = CANDIDATES["aprobado"]
WHEN = datetime(2026, 11, 28, tzinfo=UTC)


class Candidates:
    def __init__(self, reports: Mapping[str, MunicipalCutCandidateReport | Exception]) -> None:
        self._reports = reports
        self.calls: list[str] = []

    def get_report(self, municipality_code: str) -> MunicipalCutCandidateReport | None:
        self.calls.append(municipality_code)
        found = self._reports.get(municipality_code)
        if isinstance(found, Exception):
            raise found
        return found


class Reviews:
    def __init__(self, reviews: Mapping[str, tuple[CandidateReview, ...] | Exception]) -> None:
        self._reviews = reviews

    def reviews(self, municipality_code: str) -> tuple[CandidateReview, ...]:
        found = self._reviews.get(municipality_code, ())
        if isinstance(found, Exception):
            raise found
        return found


class Images:
    def __init__(self, manifests: Mapping[str, Mapping[str, ManifestImageState] | Exception]):
        self._manifests = manifests

    def availability(self, municipality_code: str) -> Mapping[str, ManifestImageState] | None:
        found = self._manifests.get(municipality_code)
        if isinstance(found, Exception):
            raise found
        return found


def _approval() -> CandidateReview:
    return CandidateReview(
        APPROVED.candidate_id,
        "approved",
        reviewed_by="r",
        reviewed_at=WHEN,
        candidate_sha256=candidate_fingerprint(APPROVED),
    )


def _use_case(
    reports: Mapping[str, MunicipalCutCandidateReport | Exception],
    reviews: Mapping[str, tuple[CandidateReview, ...] | Exception] | None = None,
    manifests: Mapping[str, Mapping[str, ManifestImageState] | Exception] | None = None,
) -> ListCandidateReviewsUseCase:
    return ListCandidateReviewsUseCase(
        Candidates(reports), Reviews(reviews or {}), Images(manifests or {})
    )


def test_listado_vigente_con_imagenes_y_sin_manifiesto() -> None:
    manifest: dict[str, ManifestImageState] = {APPROVED.candidate_id: "con_imagenes"}
    use_case = _use_case(
        {INE: generar.report(), "28013": generar.report()},
        {INE: (_approval(),)},
        {INE: manifest},
    )
    listed, without = use_case.execute([INE, "28013"])
    assert listed.outcome == "listado" and not listed.failed and listed.has_manifest
    assert listed.state is not None and listed.state.approved() == (APPROVED,)
    assert listed.images[APPROVED.candidate_id] == "con_imagenes"
    assert listed.images[CANDIDATES["propuesto"].candidate_id] == "no_en_manifiesto"
    assert not without.has_manifest
    assert set(without.images.values()) == {"sin_manifiesto"}


def test_caducadas_y_huerfanas_hacen_fallar_el_listado() -> None:
    orphan = CandidateReview("0" * 16, "proposed")
    (listing,) = _use_case({INE: generar.report()}, {INE: (orphan,)}).execute([INE])
    assert listing.outcome == "listado" and listing.failed


def test_sin_candidatos_cuenta_revisiones_sin_comprobar() -> None:
    orphan = CandidateReview("0" * 16, "proposed")
    (listing,) = _use_case({}, {INE: (orphan, _approval())}).execute([INE])
    assert listing.outcome == "sin_candidatos"
    assert listing.unchecked_reviews == 2 and not listing.failed


def test_codigo_no_valido_falla_sin_leer_nada() -> None:
    candidates = Candidates({})
    use_case = ListCandidateReviewsUseCase(candidates, Reviews({}), Images({}))
    (listing,) = use_case.execute(["2804X"])
    assert listing.outcome == "fallo" and listing.failed
    assert listing.error is not None and "2804X" not in listing.error
    assert candidates.calls == []


@pytest.mark.parametrize(
    ("reports", "reviews", "manifests"),
    [
        ({}, {INE: CandidateReviewFileError("r.json", "roto")}, {}),
        ({INE: CutCandidateFileError("c.geojson", "roto")}, {}, {}),
        ({INE: generar.report()}, {}, {INE: ComparisonManifestFileError("m.json", "roto")}),
        ({INE: generar.report()}, {INE: (_approval(), _approval())}, {}),
    ],
)
def test_errores_de_port_son_fallo_del_municipio_sin_frenar_el_lote(
    reports: dict[str, MunicipalCutCandidateReport | Exception],
    reviews: dict[str, tuple[CandidateReview, ...] | Exception],
    manifests: dict[str, Mapping[str, ManifestImageState] | Exception],
) -> None:
    reports = {**reports, "28013": generar.report()}
    failed, other = _use_case(reports, reviews, manifests).execute([INE, "28013"])
    assert failed.outcome == "fallo" and failed.failed and failed.error
    assert failed.state is None
    assert other.outcome == "listado"


def test_un_fichero_de_revision_invalido_falla_aunque_no_haya_candidatos() -> None:
    (listing,) = _use_case({}, {INE: CandidateReviewFileError("r.json", "roto")}).execute([INE])
    assert listing.outcome == "fallo"


def test_otros_errores_se_propagan() -> None:
    with pytest.raises(RuntimeError):
        _use_case({INE: RuntimeError("inesperado")}).execute([INE])
