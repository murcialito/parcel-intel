"""Lector del fichero de discrepancias (historia #94): ida y vuelta byte a byte y errores.
Datos SINTÉTICOS."""

import json
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.discrepancy_files import (
    DiscrepancyFileFormatError,
    GeoJsonDiscrepancyReportReader,
    GeoJsonDiscrepancyWriter,
    read_report,
    report_to_geojson_text,
)
from parcel_intel.domain.discrepancy import Discrepancy, Measurement, SourceRef, TrailRef
from parcel_intel.domain.discrepancy_criterion import CRITERION
from parcel_intel.domain.discrepancy_policy import redact_for_publication
from parcel_intel.domain.discrepancy_report import (
    DiscrepancyRecord,
    LayerStatus,
    LayerSummary,
    MunicipalDiscrepancyReport,
    TrailEvidence,
)
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry, TrailShape
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import DiscrepancyReportUnavailableError


def _prov(name: str, redistribution: Redistribution, license: str | None = "SINT") -> Provenance:
    return Provenance(
        f"SINTÉTICO {name}",
        f"https://example.invalid/{name}",
        date(2026, 11, 20),
        license,
        redistribution,
    )


VIA = SourceRef("via_pecuaria_oficial", _prov("vias", Redistribution.PUBLIC), date(2014, 1, 1))
IGN = SourceRef("ign_red_transporte", _prov("ign", Redistribution.PUBLIC), date(2025, 3, 15))
CAT = SourceRef("catastro_vt", _prov("cat", Redistribution.INTERNAL_ONLY, None), None)

POLYGON = Geometry(rings=(((0.0, 0.0), (10.0, 0.0), (10.0, 5.25), (0.0, 0.0)),), srid=25830)
MULTIPOLYGON = Geometry(
    rings=(
        ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)),
        ((5.0, 5.0), (6.0, 5.0), (6.0, 6.0), (5.0, 5.0)),
    ),
    srid=25830,
)
SOLAPE = MultiLineGeometry(lines=(((0.0, 0.0), (5.0, 0.0)), ((7.5, 0.0), (9.25, 0.0))), srid=25830)
ROAD = MultiLineGeometry(lines=(((0.0, 1.0), (5.0, 1.0)),), srid=25830)


def _record(
    record_id: str,
    kind: str,
    zone: TrailShape,
    subject: TrailRef,
    b: SourceRef,
    b_trails: tuple[tuple[str, TrailShape], ...] = (),
) -> DiscrepancyRecord:
    discrepancy = Discrepancy(
        kind=kind,  # type: ignore[arg-type]
        zone=zone,
        subject=subject,
        counterpart_source=b,
        counterpart_trails=tuple(TrailRef(i, b) for i, _ in b_trails),
        confidence=0.123,
        evidence=(
            Measurement("tolerancia_par_m", 11.18, "m"),
            Measurement("fraccion_solapada", 0.5, "fraccion"),
        ),
        criterion=CRITERION,
    )
    trails = (
        TrailEvidence(
            subject.trail_id,
            subject.source.kind,
            subject.source.provenance,
            subject.source.data_date,
            zone,
        ),
        *(TrailEvidence(i, b.kind, b.provenance, b.data_date, s) for i, s in b_trails),
    )
    return DiscrepancyRecord(record_id, discrepancy, trails, False)


def _report() -> MunicipalDiscrepancyReport:
    return MunicipalDiscrepancyReport(
        municipality_code="28043",
        criterion_id="discrepancia_trazados@1",
        layers=(
            LayerSummary("catastro_vt", LayerStatus.DISPONIBLE, CAT.provenance, 2, ("C-0",), None),
            LayerSummary("mtn50_historico", LayerStatus.AUSENTE, None, 0, (), "sin capa"),
        ),
        records=(
            _record("a1", "AUSENTE_EN_FUENTE", MULTIPOLYGON, TrailRef("VP-2", VIA), CAT),
            _record("a2", "AUSENTE_EN_FUENTE", POLYGON, TrailRef("99043A00109002", CAT), IGN),
            _record("s1", "SOLAPE", SOLAPE, TrailRef("VP-9", VIA), IGN, (("R-9", ROAD),)),
            _record(
                "d1",
                "DESPLAZAMIENTO",
                ROAD,
                TrailRef("R-9", IGN),
                CAT,
                (("99043A00109001", POLYGON),),
            ),
        ),
        redacted=False,
        municipality_name="Colmenar de Oreja",
    )


@pytest.mark.parametrize("publishable", [False, True])
def test_ida_y_vuelta_byte_a_byte(tmp_path: Path, publishable: bool) -> None:
    report = _report()
    if publishable:
        report = redact_for_publication(report)
    GeoJsonDiscrepancyWriter(tmp_path, publishable=publishable).write(report)
    path = tmp_path / "28043.geojson"
    read = GeoJsonDiscrepancyReportReader(tmp_path).get_report("28043")
    assert read == report
    assert report_to_geojson_text(read) == path.read_text(encoding="utf-8")


def test_sin_fichero_es_no_disponible(tmp_path: Path) -> None:
    with pytest.raises(DiscrepancyReportUnavailableError) as error:
        GeoJsonDiscrepancyReportReader(tmp_path).get_report("28043")
    assert "discrepancias --municipio" in error.value.reason
    with pytest.raises(ValueError, match="5 dígitos"):
        GeoJsonDiscrepancyReportReader(tmp_path).get_report("280")


def _written(tmp_path: Path) -> dict[str, object]:
    path = tmp_path / "x.geojson"
    path.write_text(report_to_geojson_text(_report()), encoding="utf-8")
    loaded: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def test_json_ilegible(tmp_path: Path) -> None:
    path = tmp_path / "x.geojson"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(DiscrepancyFileFormatError, match="JSON ilegible"):
        read_report(path)


@pytest.mark.parametrize(
    "key", ["nombre_municipio", "procedencia_b", "fecha_dato_b", "redistribucion"]
)
def test_un_fichero_anterior_a_94_se_rechaza(tmp_path: Path, key: str) -> None:
    document = _written(tmp_path)
    props = document["properties"]
    assert isinstance(props, dict)
    features = document["features"]
    assert isinstance(features, list)
    if key == "nombre_municipio":
        del props[key]
    elif key == "redistribucion":
        del features[0]["properties"]["trazados"][0]["procedencia"][key]
    else:
        del features[0]["properties"][key]
    path = tmp_path / "x.geojson"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(DiscrepancyFileFormatError) as error:
        read_report(path)
    assert "#94" in error.value.detail and "discrepancias --municipio" in error.value.detail


def test_trazados_incoherentes_se_rechazan(tmp_path: Path) -> None:
    document = _written(tmp_path)
    features = document["features"]
    assert isinstance(features, list)
    features[0]["properties"]["trazados"][0]["lado"] = "B"
    path = tmp_path / "x.geojson"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(DiscrepancyFileFormatError, match="lado A"):
        read_report(path)


def test_crs_distinto_se_rechaza(tmp_path: Path) -> None:
    document = _written(tmp_path)
    crs = document["crs"]
    assert isinstance(crs, dict)
    crs["properties"]["name"] = "urn:ogc:def:crs:EPSG::4326"
    path = tmp_path / "x.geojson"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(DiscrepancyFileFormatError, match="CRS"):
        read_report(path)
