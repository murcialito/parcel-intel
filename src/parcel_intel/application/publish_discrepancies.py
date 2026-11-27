"""Caso de uso: publicar los indicios de discrepancia de uno o varios municipios
(historia #94, ADR 0044).

Lee el informe **publicable** que escribió `discrepancias` (#32), deja solo los
indicios publicables con su ficha (`build_discrepancy_layer`) y se los pasa al
sink. Todo o nada: si un municipio falla, no se llama al sink y no se escribe
nada. Un fichero corrupto (cualquier otro error del adapter) se propaga.
"""

from collections.abc import Sequence

from parcel_intel.domain.publication import NotRedistributableError
from parcel_intel.domain.published_discrepancy import (
    DiscrepancyLayerPublication,
    DiscrepancyPublicationFailure,
    DiscrepancyPublicationResult,
    NotPublishableReportError,
    OmittedByLicense,
    build_discrepancy_layer,
)
from parcel_intel.ports.discrepancy_report_source import DiscrepancyReportSource
from parcel_intel.ports.errors import DiscrepancyReportUnavailableError
from parcel_intel.ports.published_discrepancy_sink import PublishedDiscrepancySink


class PublishDiscrepanciesUseCase:
    def __init__(self, reports: DiscrepancyReportSource, sink: PublishedDiscrepancySink) -> None:
        self._reports = reports
        self._sink = sink

    def execute(self, municipality_codes: Sequence[str]) -> DiscrepancyPublicationResult:
        publications: list[DiscrepancyLayerPublication] = []
        empty: list[str] = []
        omitted: list[tuple[str, OmittedByLicense]] = []
        failures: list[DiscrepancyPublicationFailure] = []
        for code in municipality_codes:
            try:
                report = self._reports.get_report(code)
            except DiscrepancyReportUnavailableError as error:
                failures.append(DiscrepancyPublicationFailure(code, f"sin fichero: {error.reason}"))
                continue
            if report.municipality_code != code:
                failures.append(
                    DiscrepancyPublicationFailure(
                        code, f"el fichero es del municipio {report.municipality_code}"
                    )
                )
                continue
            try:
                build = build_discrepancy_layer(report)
            except NotPublishableReportError as error:
                failures.append(
                    DiscrepancyPublicationFailure(code, f"no publicable: {error.reason}")
                )
                continue
            except NotRedistributableError as error:
                provenance = error.provenance
                failures.append(
                    DiscrepancyPublicationFailure(
                        code,
                        f"no redistribuible: procedencia '{provenance.source}' marcada "
                        f"'{provenance.redistribution.value}'; regenera con `discrepancias`",
                    )
                )
                continue
            omitted.append((code, build.omitted))
            if build.publication is None:
                empty.append(code)
            else:
                publications.append(build.publication)
        if failures:
            return DiscrepancyPublicationResult(
                published=(), empty=tuple(empty), omitted=tuple(omitted), failures=tuple(failures)
            )
        published = self._sink.publish(publications) if publications else ()
        return DiscrepancyPublicationResult(
            published=published,
            empty=tuple(empty),
            omitted=tuple(omitted),
            failures=(),
            kinds=tuple(
                (p.municipality_code, tuple(item.card.kind for item in p.content.items))
                for p in publications
            ),
        )
