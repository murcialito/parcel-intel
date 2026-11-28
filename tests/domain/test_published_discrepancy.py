"""Dominio de publicación de indicios (historia #94, ADR 0044). Datos SINTÉTICOS."""

import dataclasses
from datetime import date
from typing import get_args

import pytest

from parcel_intel.domain.discrepancy import (
    Discrepancy,
    DiscrepancyKind,
    Measurement,
    SourceRef,
    TrailRef,
)
from parcel_intel.domain.discrepancy_criterion import CRITERION
from parcel_intel.domain.discrepancy_policy import REDISTRIBUTABLE_SOURCES
from parcel_intel.domain.discrepancy_report import DiscrepancyRecord, MunicipalDiscrepancyReport
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry, TrailShape
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.public_card import build_card
from parcel_intel.domain.publication import NotRedistributableError
from parcel_intel.domain.published_discrepancy import (
    CADASTRAL_REFERENCE_RE,
    PARCEL_LOCATOR_RE,
    PUBLISHABLE_COUNTERPART_SOURCES,
    NotPublishableReportError,
    build_discrepancy_layer,
    public_indicio_id,
)
from parcel_intel.domain.trail import SourceKind

LINE = MultiLineGeometry(lines=(((465000.0, 4440000.0), (465200.0, 4440000.0)),), srid=25830)


def _source(kind: SourceKind, public: bool = True) -> SourceRef:
    return SourceRef(
        kind=kind,
        provenance=Provenance(
            source=f"SINTÉTICO {kind}",
            url=f"https://example.invalid/{kind}",
            retrieved_at=date(2026, 11, 20),
            license="SINTÉTICA",
            redistribution=Redistribution.PUBLIC if public else Redistribution.INTERNAL_ONLY,
        ),
        data_date=date(2014, 1, 1),
    )


def _record(
    a: SourceKind = "via_pecuaria_oficial",
    b: SourceKind = "ign_red_transporte",
    *,
    trail_id: str = "VP-1",
    zone: TrailShape = LINE,
    redacted: bool = False,
    kind: DiscrepancyKind = "AUSENTE_EN_FUENTE",
    public_subject: bool = True,
) -> DiscrepancyRecord:
    discrepancy = Discrepancy(
        kind=kind,
        zone=zone,
        subject=TrailRef(trail_id, _source(a, public_subject)),
        counterpart_source=_source(b, b in REDISTRIBUTABLE_SOURCES),
        counterpart_trails=(),
        confidence=0.6,
        evidence=(Measurement("desplazamiento_mediano_m", 20.0, "m"),),
        criterion=CRITERION,
    )
    return DiscrepancyRecord(
        record_id=f"rec-{trail_id}", discrepancy=discrepancy, trails=(), zone_redacted=redacted
    )


def _report(*records: DiscrepancyRecord, **changes: object) -> MunicipalDiscrepancyReport:
    report = MunicipalDiscrepancyReport(
        municipality_code="28043",
        criterion_id="discrepancia_trazados@1",
        layers=(),
        records=records,
        redacted=True,
        municipality_name="Colmenar de Oreja",
    )
    return dataclasses.replace(report, **changes)  # type: ignore[arg-type]


# --- Patrones de última barrera ---------------------------------------------------------


@pytest.mark.parametrize(
    "reference",
    [
        "99043A00109001",  # rústica, 14
        "99043A001090010001AB",  # rústica, 20
        "9904301VK4590S",  # urbana, 14
        "9904301VK4590S0001WX",  # urbana, 20
        "ref 99043A00109001.",
    ],
)
def test_la_forma_de_referencia_catastral_casa_rustica_y_urbana(reference: str) -> None:
    assert CADASTRAL_REFERENCE_RE.search(reference) is not None


@pytest.mark.parametrize(
    "text",
    [
        # URLs reales de bbox de las capas publicadas (vías pecuarias e IGN).
        "https://idem.comunidad.madrid/geoidem/Zonas/wfs?bbox=470173.1391980562%2C"
        "4433515.89948871%2C483164.45611997315%2C4451633.093908208%2CEPSG%3A25830"
        "&request=GetFeature&service=WFS&typenames=Zonas%3AIDEM_MA_VIAS_PECUARIAS",
        "https://api-features.ign.es/collections/roadlink/items?bbox=-3.62%2C39.98%2C"
        "-3.15%2C40.22&filter=surfacecategory%3D%27unpaved%27&limit=500&offset=1000",
        "Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional",
        "2026-11-26",
        "99043a00109001",  # en minúsculas no es una referencia
    ],
)
def test_textos_publicados_no_casan_con_la_forma_de_referencia(text: str) -> None:
    assert CADASTRAL_REFERENCE_RE.search(text) is None
    assert PARCEL_LOCATOR_RE.search(text) is None


def test_localizador_de_parcela_en_url() -> None:
    url = "https://ovc.catastro.meh.es/x?Provincia=28&Municipio=43&Poligono=1&Parcela=9001"
    assert PARCEL_LOCATOR_RE.search(url) is not None
    assert PARCEL_LOCATOR_RE.search("https://x.invalid/?refcat=1") is not None


# --- Construcción de la capa -------------------------------------------------------------


def test_contrapartes_publicables_son_las_redistribuibles_y_catastro() -> None:
    assert PUBLISHABLE_COUNTERPART_SOURCES == REDISTRIBUTABLE_SOURCES | {"catastro_vt"}
    assert set(get_args(SourceKind)) == PUBLISHABLE_COUNTERPART_SOURCES


def test_publica_la_ficha_y_la_zona_y_cuenta_el_lado_a_redactado() -> None:
    publishable = _record()
    catastro_b = _record(
        b="catastro_vt",
        trail_id="VP-2",
        zone=MultiLineGeometry(lines=(((465000.0, 4440300.0), (465100.0, 4440300.0)),), srid=25830),
    )
    redacted = _record(
        a="catastro_vt",
        trail_id="99043A00109002",
        zone=Geometry(rings=(), srid=25830),
        redacted=True,
    )
    build = build_discrepancy_layer(_report(redacted, publishable, catastro_b))
    assert (build.omitted.subject, build.omitted.counterpart, build.omitted.total) == (1, 0, 1)
    assert build.publication is not None
    items = build.publication.content.items
    assert [i.card for i in items] == [
        build_card(publishable.discrepancy),
        build_card(catastro_b.discrepancy),
    ]
    assert items[0].zone == LINE
    assert items[0].provenance == publishable.discrepancy.subject.source.provenance
    assert build.publication.municipality_name == "Colmenar de Oreja"
    assert build.publication.criterion_id == "discrepancia_trazados@1"
    assert build.publication.content.name == "discrepancias/28043"


def test_sin_indicios_publicables_no_hay_publicacion() -> None:
    redacted = _record(a="catastro_vt", zone=Geometry(rings=(), srid=25830), redacted=True)
    build = build_discrepancy_layer(_report(redacted))
    assert build.publication is None
    assert build.omitted.subject == 1


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"redacted": False}, "variante publicable"),
        ({"municipality_name": None}, "nombre del municipio"),
        ({"municipality_name": ""}, "nombre del municipio"),
    ],
)
def test_informe_no_publicable(changes: dict[str, object], message: str) -> None:
    with pytest.raises(NotPublishableReportError) as error:
        build_discrepancy_layer(_report(_record(), **changes))
    assert message in error.value.reason
    assert error.value.municipality_code == "28043"


def test_registro_sin_redactar_con_lado_a_no_redistribuible_falla() -> None:
    record = _record(a="catastro_vt", public_subject=False)
    with pytest.raises(NotPublishableReportError, match="sin redactar"):
        build_discrepancy_layer(_report(record))


def test_registro_sin_redactar_con_zona_vacia_falla() -> None:
    record = _record(zone=Geometry(rings=(), srid=25830))
    with pytest.raises(NotPublishableReportError, match="zona vacía"):
        build_discrepancy_layer(_report(record))
    empty_line = _record(zone=MultiLineGeometry(lines=((),), srid=25830))
    with pytest.raises(NotPublishableReportError, match="zona vacía"):
        build_discrepancy_layer(_report(empty_line))


def test_trazado_a_con_procedencia_interna_no_pasa_la_puerta() -> None:
    record = _record(public_subject=False)
    with pytest.raises(NotRedistributableError):
        build_discrepancy_layer(_report(record))


# --- Identificador público --------------------------------------------------------------


def test_el_id_publico_no_depende_de_los_ids_de_trazado() -> None:
    a = _record(trail_id="VP-1").discrepancy
    b = _record(trail_id="99043A00109001").discrepancy
    assert public_indicio_id(a) == public_indicio_id(b)
    assert len(public_indicio_id(a)) == 16
    int(public_indicio_id(a), 16)


def test_el_id_publico_cambia_con_la_zona_el_tipo_y_las_fuentes() -> None:
    base = _record().discrepancy
    other_zone = dataclasses.replace(
        base,
        zone=MultiLineGeometry(lines=(((465000.0, 4440001.0), (465200.0, 4440000.0)),), srid=25830),
    )
    other_kind = dataclasses.replace(base, kind="DESPLAZAMIENTO")
    other_b = _record(b="catastro_vt").discrepancy
    ids = {public_indicio_id(d) for d in (base, other_zone, other_kind, other_b)}
    assert len(ids) == 4


def test_colision_de_id_lleva_sufijo_en_orden_canonico() -> None:
    # Dos trazados idénticos de la misma fuente con distinto id: mismo id público.
    first, second, third = (_record(trail_id=f"VP-{n}") for n in (1, 2, 3))
    build = build_discrepancy_layer(_report(first, second, third))
    assert build.publication is not None
    ids = [item.public_id for item in build.publication.content.items]
    base = public_indicio_id(first.discrepancy)
    assert ids == [base, f"{base}-2", f"{base}-3"]


def test_is_publishable_indicio_fuente_a_y_contraparte() -> None:
    """#314: la regla de publicación de un indicio es una función propia."""
    from parcel_intel.domain.published_discrepancy import is_publishable_indicio
    from tests.indicio_comparison_support import line, record

    zone = line(0.0, 0.0)
    assert is_publishable_indicio(record("0" * 16, zone).discrepancy)
    assert is_publishable_indicio(
        record("1" * 16, zone, counterpart_kind="catastro_vt").discrepancy
    )
    assert not is_publishable_indicio(
        record("2" * 16, zone, subject_kind="catastro_vt").discrepancy
    )
