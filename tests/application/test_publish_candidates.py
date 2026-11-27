"""Caso de uso `PublishCandidatesUseCase` (historias #170 y #172) con dobles. Datos
sintéticos."""

import dataclasses
from collections.abc import Sequence
from datetime import date, datetime

from parcel_intel.application.publish_candidates import PublishCandidatesUseCase
from parcel_intel.domain.candidate_review import CandidateReview, candidate_fingerprint
from parcel_intel.domain.comparison_image import ComparisonManifest
from parcel_intel.domain.cut_candidate import MunicipalCutCandidateReport
from parcel_intel.domain.discrepancy_criterion import CriterionRef
from parcel_intel.domain.published_candidate import CandidateLayerPublication, MeasurementReport
from parcel_intel.domain.published_layers import PublishedFile
from parcel_intel.ports.errors import (
    CandidateReviewFileError,
    ComparisonManifestFileError,
    CutCandidateFileError,
    MeasurementReportUnavailableError,
)
from tests.fixtures.candidatos_publicar import generar as publicar
from tests.fixtures.candidatos_revision import generar

INE = "28043"
MEASUREMENT = MeasurementReport(
    label="validacion-v1",
    frozen=True,
    run_date=date(2026, 11, 27),
    candidate_methods=("candidato_corte@1",),
    total_cases=6,
    out_of_scope_cases=4,
    evaluable_cases=0,
    flagged_cases=0,
    coverage=None,
    evaluable_candidates=0,
    hit_candidates=0,
    precision=None,
    precision_bound="inferior",
)


class _Measurement:
    def __init__(self, report: MeasurementReport | Exception) -> None:
        self._report = report

    def get_measurement(self) -> MeasurementReport:
        if isinstance(self._report, Exception):
            raise self._report
        return self._report


class _Candidates:
    def __init__(self, reports: dict[str, MunicipalCutCandidateReport | Exception]) -> None:
        self._reports = reports
        self.calls: list[str] = []

    def get_report(self, municipality_code: str) -> MunicipalCutCandidateReport | None:
        self.calls.append(municipality_code)
        found = self._reports.get(municipality_code)
        if isinstance(found, Exception):
            raise found
        return found


class _Reviews:
    def __init__(self, reviews: tuple[CandidateReview, ...] | Exception) -> None:
        self._reviews = reviews

    def reviews(self, municipality_code: str) -> tuple[CandidateReview, ...]:
        if isinstance(self._reviews, Exception):
            raise self._reviews
        return self._reviews


class _Comparisons:
    def __init__(self, manifest: ComparisonManifest | None | Exception) -> None:
        self._manifest = manifest
        self.calls: list[str] = []

    def get_manifest(self, municipality_code: str) -> ComparisonManifest | None:
        self.calls.append(municipality_code)
        if isinstance(self._manifest, Exception):
            raise self._manifest
        return self._manifest


MANIFEST = publicar.manifest_for(list(generar.candidates().values()))


class _Sink:
    def __init__(self) -> None:
        self.received: list[list[CandidateLayerPublication]] = []

    def publish(
        self, publications: Sequence[CandidateLayerPublication]
    ) -> tuple[PublishedFile, ...]:
        self.received.append(list(publications))
        return tuple(
            PublishedFile(
                "candidatos",
                p.municipality_code,
                f"candidatos/{p.municipality_code}.geojson",
                1,
                None,
                False,
            )
            for p in publications
        )


def _approval(role: str, fingerprint: str | None = None) -> CandidateReview:
    candidate = generar.candidates()[role]
    return CandidateReview(
        candidate_id=candidate.candidate_id,
        status="approved",
        reviewed_by=generar.REVIEWER,
        reviewed_at=datetime.fromisoformat(generar.REVIEWED_AT),
        candidate_sha256=fingerprint or candidate_fingerprint(candidate),
    )


def _use_case(
    measurement: MeasurementReport | Exception = MEASUREMENT,
    reports: dict[str, MunicipalCutCandidateReport | Exception] | None = None,
    reviews: tuple[CandidateReview, ...] | Exception = (),
    manifest: ComparisonManifest | None | Exception = MANIFEST,
) -> tuple[PublishCandidatesUseCase, _Candidates, _Sink]:
    candidates = _Candidates({INE: generar.report()} if reports is None else reports)
    sink = _Sink()
    use_case = PublishCandidatesUseCase(
        _Measurement(measurement), candidates, _Reviews(reviews), _Comparisons(manifest), sink
    )
    return use_case, candidates, sink


def test_publica_los_aprobados_y_cuenta_los_demas() -> None:
    use_case, _, sink = _use_case(reviews=(_approval("aprobado"),))
    result = use_case.execute([INE])
    assert result.failures == () and result.measurement_error is None
    assert result.counts == ((INE, 1, 4, 0),)
    (publications,) = sink.received
    assert [p.municipality_code for p in publications] == [INE]
    assert result.measurement_texts[2] == "Solo 2 casos en el ámbito, no es una estadística."
    assert result.published[0].path == "candidatos/28043.geojson"


def test_sin_informe_de_medicion_no_mira_ningun_municipio() -> None:
    error = MeasurementReportUnavailableError("data/medicion.json", "no existe")
    use_case, candidates, sink = _use_case(measurement=error)
    result = use_case.execute([INE])
    assert (
        result.measurement_error
        == "Informe de medición no disponible data/medicion.json: no existe"
    )
    assert candidates.calls == [] and sink.received == []


def test_un_fallo_impide_publicar_todo() -> None:
    use_case, _, sink = _use_case(reviews=(_approval("aprobado"),))
    result = use_case.execute([INE, "28013"])
    assert result.published == ()
    assert [f.municipality_code for f in result.failures] == ["28013"]
    assert "código de Catastro verificado (28043)" in result.failures[0].reason
    assert sink.received == []


def test_codigo_raro_falla_sin_repetirlo() -> None:
    use_case, candidates, _ = _use_case()
    result = use_case.execute(["../x"])
    assert "../x" not in result.failures[0].reason
    assert candidates.calls == []


def test_sin_fichero_y_fichero_de_otro_municipio() -> None:
    use_case, _, _ = _use_case(reports={})
    assert "sin fichero de candidatos" in use_case.execute([INE]).failures[0].reason
    other = dataclasses.replace(generar.report(), municipality_code="28013")
    use_case, _, _ = _use_case(reports={INE: other})
    assert "es del municipio 28013" in use_case.execute([INE]).failures[0].reason


def test_errores_de_fichero_y_de_revision_son_fallos_del_municipio() -> None:
    broken = CutCandidateFileError("c/28043.geojson", "no es JSON")
    use_case, _, _ = _use_case(reports={INE: broken})
    assert "c/28043.geojson" in use_case.execute([INE]).failures[0].reason
    reviews_error = CandidateReviewFileError("r/revision.json", "campo review")
    use_case, _, _ = _use_case(reviews=reviews_error)
    assert "r/revision.json" in use_case.execute([INE]).failures[0].reason
    repeated = (_approval("aprobado"), _approval("aprobado"))
    use_case, _, _ = _use_case(reviews=repeated)
    assert "repetido" in use_case.execute([INE]).failures[0].reason


def test_medicion_no_utilizable_es_fallo_del_municipio() -> None:
    use_case, _, sink = _use_case(
        measurement=dataclasses.replace(MEASUREMENT, frozen=False), reviews=(_approval("aprobado"),)
    )
    failure = use_case.execute([INE]).failures[0]
    assert "no es de un conjunto congelado" in failure.reason
    assert sink.received == []


def test_caducadas_listan_ids_y_el_fichero_a_corregir() -> None:
    use_case, _, _ = _use_case(reviews=(_approval("aprobado", "0" * 64),))
    reason = use_case.execute([INE]).failures[0].reason
    aprobado = generar.candidates()["aprobado"].candidate_id
    assert reason == (
        f"revisiones no vigentes; caducadas: {aprobado}; huérfanas: ninguna; "
        "corrígelas en curated/candidatos/28043/revision.json"
    )


def test_no_redistribuible_y_sin_fecha_de_catastro() -> None:
    use_case, _, _ = _use_case(reviews=(_approval("rechazado"),))
    reason = use_case.execute([INE]).failures[0].reason
    assert reason.startswith("no publicable: el candidato")
    assert generar.CATASTRO_TRAIL_ID not in reason

    found = generar.candidates()
    base = found["aprobado"]
    signal = dataclasses.replace(base.signals[0], provenance=(base.subject.source.provenance,))
    no_date = dataclasses.replace(base, signals=(signal,))
    report = dataclasses.replace(generar.report(), candidates=(no_date,))
    review = dataclasses.replace(
        _approval("aprobado"), candidate_sha256=candidate_fingerprint(no_date)
    )
    use_case, _, _ = _use_case(reports={INE: report}, reviews=(review,))
    assert "ninguna procedencia de Catastro" in use_case.execute([INE]).failures[0].reason


# --- imágenes de comparación (#172) ----------------------------------------------------


def test_sin_manifiesto_falla_el_municipio_sin_publicar() -> None:
    use_case, _, sink = _use_case(reviews=(_approval("aprobado"),), manifest=None)
    (failure,) = use_case.execute([INE]).failures
    assert failure.reason == (
        "sin manifiesto de imágenes de comparación; ejecuta imagenes-comparacion"
    )
    assert sink.received == []


def test_manifiesto_ilegible_es_fallo_del_municipio() -> None:
    error = ComparisonManifestFileError("c/28043.json", "JSON ilegible")
    use_case, _, sink = _use_case(reviews=(_approval("aprobado"),), manifest=error)
    (failure,) = use_case.execute([INE]).failures
    assert "c/28043.json" in failure.reason and "JSON ilegible" in failure.reason
    assert sink.received == []


def test_manifiesto_de_otra_politica_es_fallo_del_municipio() -> None:
    other = dataclasses.replace(MANIFEST, policy=CriterionRef("imagenes_comparacion", 2))
    use_case, _, sink = _use_case(reviews=(_approval("aprobado"),), manifest=other)
    (failure,) = use_case.execute([INE]).failures
    assert failure.reason.startswith("manifiesto de imágenes no utilizable: el manifiesto es de")
    assert sink.received == []


def test_aprobado_fuera_del_manifiesto_nombra_su_id() -> None:
    empty = dataclasses.replace(MANIFEST, stretches=())
    use_case, _, _ = _use_case(reviews=(_approval("aprobado"),), manifest=empty)
    (failure,) = use_case.execute([INE]).failures
    aprobado = generar.candidates()["aprobado"].candidate_id
    assert failure.reason == (
        f"no publicable: el candidato {aprobado}: no está en el manifiesto de imágenes de "
        "comparación; ejecuta imagenes-comparacion"
    )


def test_sin_fichero_de_candidatos_no_mira_el_manifiesto() -> None:
    comparisons = _Comparisons(MANIFEST)
    use_case = PublishCandidatesUseCase(
        _Measurement(MEASUREMENT), _Candidates({}), _Reviews(()), comparisons, _Sink()
    )
    assert "sin fichero de candidatos" in use_case.execute([INE]).failures[0].reason
    assert comparisons.calls == []
