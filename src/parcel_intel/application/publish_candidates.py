"""Caso de uso: publicar los tramos a verificar aprobados de uno o varios municipios
(historia #170, ADR 0048).

Lee primero el informe de medición de `medir-candidatos` (#111): sin informe utilizable
no se mira ningún municipio. Por municipio, reconcilia candidatos (#128) y revisiones
(#168) y deja solo los aprobados vigentes con su ficha (`build_candidate_layer`) y sus
imágenes de comparación del manifiesto de `imagenes-comparacion` (#172, ADR 0049). Todo
o nada: si un municipio falla, no se llama al sink y no se escribe nada.

Los mensajes nunca incluyen `trail_id` ni `review_note`; los `candidate_id` sí, porque ya
son públicos en `revision.json`.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from parcel_intel.domain.candidate_review import (
    InvalidCandidateReviewError,
    StaleCandidateApprovalError,
    reconcile,
)
from parcel_intel.domain.public_candidate_card import MissingCatastroDateError
from parcel_intel.domain.publication import NotRedistributableError
from parcel_intel.domain.published_candidate import (
    CANDIDATE_PUBLISHABLE_MUNICIPALITIES,
    CandidateLayerBuild,
    CandidateLayerPublication,
    CandidatesNotPublishableError,
    MeasurementNotUsableError,
    MeasurementReport,
    build_candidate_layer,
    summarize_measurement,
)
from parcel_intel.domain.published_comparison import ComparisonManifestNotUsableError
from parcel_intel.domain.published_layers import PublishedFile
from parcel_intel.ports.candidate_review_source import CandidateReviewSource
from parcel_intel.ports.comparison_manifest_source import ComparisonManifestSource
from parcel_intel.ports.cut_candidate_source import CutCandidateSource
from parcel_intel.ports.errors import (
    CandidateReviewFileError,
    ComparisonManifestFileError,
    CutCandidateFileError,
    MeasurementReportUnavailableError,
)
from parcel_intel.ports.measurement_report_source import MeasurementReportSource
from parcel_intel.ports.published_candidate_sink import PublishedCandidateSink


@dataclass(frozen=True)
class CandidatePublicationFailure:
    municipality_code: str
    reason: str


@dataclass(frozen=True)
class CandidatePublicationResult:
    published: tuple[PublishedFile, ...]  # () si hay cualquier fallo
    failures: tuple[CandidatePublicationFailure, ...]
    measurement_error: str | None  # si no hay informe utilizable, no se mira ningún municipio
    counts: tuple[tuple[str, int, int, int], ...]  # (ine, aprobados, propuestos, rechazados)
    measurement_texts: tuple[str, ...] = ()  # el resumen publicado (igual en todos)


class _MunicipalityFailed(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


_VERIFIED_CODES = ", ".join(sorted(CANDIDATE_PUBLISHABLE_MUNICIPALITIES))


class PublishCandidatesUseCase:
    def __init__(
        self,
        measurement: MeasurementReportSource,
        candidates: CutCandidateSource,
        reviews: CandidateReviewSource,
        comparisons: ComparisonManifestSource,
        sink: PublishedCandidateSink,
    ) -> None:
        self._measurement = measurement
        self._candidates = candidates
        self._reviews = reviews
        self._comparisons = comparisons
        self._sink = sink

    def execute(self, municipality_codes: Sequence[str]) -> CandidatePublicationResult:
        try:
            measurement = self._measurement.get_measurement()
        except MeasurementReportUnavailableError as error:
            return CandidatePublicationResult(
                published=(), failures=(), measurement_error=str(error), counts=()
            )
        builds: list[CandidateLayerBuild] = []
        failures: list[CandidatePublicationFailure] = []
        for code in municipality_codes:
            try:
                builds.append(self._build(code, measurement))
            except _MunicipalityFailed as error:
                failures.append(CandidatePublicationFailure(code, error.reason))
        counts = tuple(
            (b.publication.municipality_code, b.approved, b.proposed, b.rejected) for b in builds
        )
        if failures:
            return CandidatePublicationResult(
                published=(), failures=tuple(failures), measurement_error=None, counts=counts
            )
        publications: list[CandidateLayerPublication] = [b.publication for b in builds]
        published = self._sink.publish(publications) if publications else ()
        texts = publications[0].measurement.texts if publications else ()
        return CandidatePublicationResult(
            published=published,
            failures=(),
            measurement_error=None,
            counts=counts,
            measurement_texts=texts,
        )

    def _build(self, code: str, measurement: MeasurementReport) -> CandidateLayerBuild:
        name = CANDIDATE_PUBLISHABLE_MUNICIPALITIES.get(code)
        if name is None:
            raise _MunicipalityFailed(
                "solo se publican candidatos de municipios con código de Catastro "
                f"verificado ({_VERIFIED_CODES})"
            )
        try:
            report = self._candidates.get_report(code)
            if report is None:
                raise _MunicipalityFailed("sin fichero de candidatos; ejecuta candidatos-corte")
            if report.municipality_code != code:
                raise _MunicipalityFailed(
                    f"el fichero de candidatos es del municipio {report.municipality_code}"
                )
            manifest = self._comparisons.get_manifest(code)
            if manifest is None:
                raise _MunicipalityFailed(
                    "sin manifiesto de imágenes de comparación; ejecuta imagenes-comparacion"
                )
            summary = summarize_measurement(measurement, report.method)
            state = reconcile(report, self._reviews.reviews(code))
            return build_candidate_layer(state, summary, name, manifest)
        except (
            CutCandidateFileError,
            CandidateReviewFileError,
            ComparisonManifestFileError,
        ) as error:
            raise _MunicipalityFailed(str(error)) from error
        except ComparisonManifestNotUsableError as error:
            raise _MunicipalityFailed(
                f"manifiesto de imágenes no utilizable: {error.reason}"
            ) from error
        except InvalidCandidateReviewError as error:
            raise _MunicipalityFailed(f"revisión no válida: {error}") from error
        except MeasurementNotUsableError as error:
            raise _MunicipalityFailed(
                f"informe de medición no utilizable: {error.reason}"
            ) from error
        except StaleCandidateApprovalError as error:
            raise _MunicipalityFailed(
                "revisiones no vigentes; caducadas: "
                f"{', '.join(error.stale_ids) or 'ninguna'}; huérfanas: "
                f"{', '.join(error.orphan_ids) or 'ninguna'}; "
                f"corrígelas en curated/candidatos/{code}/revision.json"
            ) from error
        except CandidatesNotPublishableError as error:
            raise _MunicipalityFailed(f"no publicable: {error.reason}") from error
        except MissingCatastroDateError as error:
            raise _MunicipalityFailed(f"no publicable: {error}") from error
        except NotRedistributableError as error:
            provenance = error.provenance
            raise _MunicipalityFailed(
                f"no redistribuible: procedencia '{provenance.source}' marcada "
                f"'{provenance.redistribution.value}'"
            ) from error
