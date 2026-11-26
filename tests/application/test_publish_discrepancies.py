"""Caso de uso `PublishDiscrepanciesUseCase` (historia #94) con dobles. Datos SINTÉTICOS."""

import dataclasses
from collections.abc import Sequence
from datetime import date

import pytest

from parcel_intel.application.publish_discrepancies import PublishDiscrepanciesUseCase
from parcel_intel.domain.discrepancy import Discrepancy, Measurement, SourceRef, TrailRef
from parcel_intel.domain.discrepancy_criterion import CRITERION
from parcel_intel.domain.discrepancy_report import DiscrepancyRecord, MunicipalDiscrepancyReport
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.published_discrepancy import DiscrepancyLayerPublication
from parcel_intel.domain.published_layers import PublishedFile
from parcel_intel.domain.trail import SourceKind
from parcel_intel.ports.errors import DiscrepancyReportUnavailableError


def _source(kind: SourceKind, redistribution: Redistribution) -> SourceRef:
    return SourceRef(
        kind,
        Provenance(
            "SINTÉTICO", "https://example.invalid", date(2026, 11, 20), "SINT", redistribution
        ),
        date(2014, 1, 1),
    )


def _record(
    a: SourceKind = "via_pecuaria_oficial",
    *,
    redacted: bool = False,
    redistribution: Redistribution = Redistribution.PUBLIC,
) -> DiscrepancyRecord:
    zone = (
        Geometry(rings=(), srid=25830)
        if redacted
        else MultiLineGeometry(lines=(((0.0, 0.0), (10.0, 0.0)),), srid=25830)
    )
    discrepancy = Discrepancy(
        kind="AUSENTE_EN_FUENTE",
        zone=zone,
        subject=TrailRef("A-1", _source(a, redistribution)),
        counterpart_source=_source("ign_red_transporte", Redistribution.PUBLIC),
        counterpart_trails=(),
        confidence=0.5,
        evidence=(Measurement("radio_busqueda_m", 33.5, "m"),),
        criterion=CRITERION,
    )
    return DiscrepancyRecord("r", discrepancy, (), redacted)


def _report(
    code: str, *records: DiscrepancyRecord, **changes: object
) -> MunicipalDiscrepancyReport:
    report = MunicipalDiscrepancyReport(
        municipality_code=code,
        criterion_id="discrepancia_trazados@1",
        layers=(),
        records=records,
        redacted=True,
        municipality_name="Municipio sintético",
    )
    return dataclasses.replace(report, **changes)  # type: ignore[arg-type]


class _Reports:
    def __init__(self, reports: dict[str, MunicipalDiscrepancyReport | Exception]) -> None:
        self._reports = reports

    def get_report(self, municipality_code: str) -> MunicipalDiscrepancyReport:
        value = self._reports.get(municipality_code)
        if value is None:
            raise DiscrepancyReportUnavailableError(municipality_code, "no existe")
        if isinstance(value, Exception):
            raise value
        return value


class _Sink:
    def __init__(self) -> None:
        self.calls: list[list[DiscrepancyLayerPublication]] = []

    def publish(
        self, publications: Sequence[DiscrepancyLayerPublication]
    ) -> tuple[PublishedFile, ...]:
        self.calls.append(list(publications))
        return tuple(
            PublishedFile(
                "discrepancias",
                p.municipality_code,
                f"discrepancias/{p.municipality_code}.geojson",
                1,
                None,
                False,
            )
            for p in publications
        )


def test_publica_y_cuenta_vacios_y_omitidos() -> None:
    reports = _Reports(
        {
            "28043": _report("28043", _record(), _record("catastro_vt", redacted=True)),
            "28045": _report("28045", _record("catastro_vt", redacted=True)),
        }
    )
    sink = _Sink()
    result = PublishDiscrepanciesUseCase(reports, sink).execute(["28043", "28045"])
    assert result.failures == ()
    assert [f.municipality_code for f in result.published] == ["28043"]
    assert result.empty == ("28045",)
    assert [(c, o.subject, o.counterpart) for c, o in result.omitted] == [
        ("28043", 1, 0),
        ("28045", 1, 0),
    ]
    assert result.kinds == (("28043", ("AUSENTE_EN_FUENTE",)),)
    assert len(sink.calls) == 1 and len(sink.calls[0]) == 1


@pytest.mark.parametrize(
    ("report", "prefix"),
    [
        (None, "sin fichero: no existe"),
        (_report("28043", _record(), redacted=False), "no publicable: no es la variante"),
        (_report("28999", _record()), "el fichero es del municipio 28999"),
        (
            _report("28043", _record(redistribution=Redistribution.INTERNAL_ONLY)),
            "no redistribuible: procedencia 'SINTÉTICO' marcada 'solo_uso_interno'",
        ),
    ],
)
def test_un_fallo_no_escribe_nada(report: MunicipalDiscrepancyReport | None, prefix: str) -> None:
    reports: dict[str, MunicipalDiscrepancyReport | Exception] = {
        "28045": _report("28045", _record())
    }
    if report is not None:
        reports["28043"] = report
    sink = _Sink()
    result = PublishDiscrepanciesUseCase(_Reports(reports), sink).execute(["28045", "28043"])
    assert sink.calls == []
    assert result.published == ()
    (failure,) = result.failures
    assert failure.municipality_code == "28043"
    assert failure.reason.startswith(prefix), failure.reason


def test_un_fichero_corrupto_se_propaga() -> None:
    reports = _Reports({"28043": RuntimeError("corrupto")})
    sink = _Sink()
    with pytest.raises(RuntimeError, match="corrupto"):
        PublishDiscrepanciesUseCase(reports, sink).execute(["28043"])
    assert sink.calls == []


def test_sin_publicaciones_no_llama_al_sink() -> None:
    reports = _Reports({"28045": _report("28045")})
    sink = _Sink()
    result = PublishDiscrepanciesUseCase(reports, sink).execute(["28045"])
    assert sink.calls == []
    assert result.empty == ("28045",)
