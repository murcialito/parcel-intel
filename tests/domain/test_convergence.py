"""Tests unitarios de `domain/convergence.py` (historia #240). Fixtures SINTÉTICAS."""

import dataclasses
from datetime import date

import pytest

from parcel_intel.domain.comparison_image import COMPARISON_SLOTS
from parcel_intel.domain.convergence import (
    APPEARS_MIN_FRACTION,
    CATASTRO_ROW_LABEL,
    CONVERGENCE_METHOD,
    CONVERGENCE_ROW_SOURCES,
    CONVERGENCE_TITLE,
    CONVERGENCE_WARNING,
    ConvergenceRow,
    ConvergenceStretch,
    ConvergenceTable,
    HistoricRowSource,
    InvalidConvergenceRowError,
    InvalidConvergenceStretchError,
    InvalidConvergenceTableError,
    LayerRowSource,
    OrthophotoRowSource,
    StretchNotComputableError,
    YearSpan,
    appears,
    build_convergence_table,
    historic_row,
    image_axis,
    layer_row,
    orthophoto_rows,
    prepare_layer,
    stretch_from_candidate,
)
from parcel_intel.domain.cut_candidate import CutCandidate, SignalRef, SignalSupport
from parcel_intel.domain.discrepancy import Measurement, TrailRef
from parcel_intel.domain.discrepancy_criterion import CRITERION, CriterionRef
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry
from parcel_intel.domain.public_card import CATASTRO_ATTRIBUTION, SOURCE_POLICY
from parcel_intel.domain.published_comparison import NOT_IN_MANIFEST
from tests.convergence_support import (
    INE,
    NO_IMAGES_SLOT_VINTAGES,
    STRETCH_ID,
    comparison_for,
    coverage,
    empty_coverages,
    historic_trail,
    layer,
    line,
    lines,
    origin,
    p,
    stretch,
    strip,
    unit,
)
from tests.trail_factories import make_trail

TRAMO = line((0, 0), (200, 0))
SLOTS = tuple(slot.name for slot in COMPARISON_SLOTS)


def _row(**changes: object) -> ConvergenceRow:
    values: dict[str, object] = {
        "source_key": "via_pecuaria_oficial",
        "label": "Vía pecuaria oficial",
        "evidence_kind": "trazado",
        "value": "aparece",
        "years": YearSpan(2014, 2014),
        "consulted_on": date(2026, 11, 26),
        "links": (),
        "attributions": ("atribución sintética",),
    }
    values.update(changes)
    return ConvergenceRow(**values)  # type: ignore[arg-type]


def _table(**changes: object) -> ConvergenceTable:
    values: dict[str, object] = {
        "stretch_id": STRETCH_ID,
        "municipality_code": INE,
        "title": CONVERGENCE_TITLE,
        "rows": (_row(),),
        "warning": CONVERGENCE_WARNING,
        "method": CONVERGENCE_METHOD,
        "criterion": CRITERION,
        "appears_min_fraction": APPEARS_MIN_FRACTION,
    }
    values.update(changes)
    return ConvergenceTable(**values)  # type: ignore[arg-type]


# --- YearSpan. --------------------------------------------------------------------------
def test_year_span_rotulos() -> None:
    assert YearSpan(1875, 1875).label() == "1875"
    assert YearSpan(2017, 2026).label() == "2017–2026"


@pytest.mark.parametrize(("first", "last"), [(1799, 1800), (2000, 1999), (2000, 2101)])
def test_year_span_fuera_de_rango(first: int, last: int) -> None:
    with pytest.raises(InvalidConvergenceRowError, match="years"):
        YearSpan(first, last)


def test_year_span_exige_enteros() -> None:
    with pytest.raises(InvalidConvergenceRowError, match="entero"):
        YearSpan(True, 2000)


# --- ConvergenceRow. --------------------------------------------------------------------
def test_fila_valida_y_sus_textos() -> None:
    row = _row()
    assert list(row.strings()) == [
        "Vía pecuaria oficial",
        "Aparece",
        "2014",
        "2026-11-26",
        "atribución sintética",
    ]
    assert "año no declarado" in list(_row(years=None).strings())


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"source_key": " "}, "source_key"),
        ({"label": ""}, "label"),
        ({"evidence_kind": "mapa"}, "evidence_kind"),
        ({"value": "quizas"}, "value no reconocido"),
        ({"value": "imagen_disponible", "links": ("https://x.invalid",)}, "no vale"),
        ({"evidence_kind": "imagen"}, "no vale"),
        ({"links": ("https://x.invalid",)}, "trazado"),
        ({"years": (2014, 2014)}, "YearSpan"),
        ({"consulted_on": "2026-11-26"}, "consulted_on"),
        ({"attributions": ()}, "attributions"),
        ({"attributions": ("",)}, "vacíos"),
        ({"attributions": ["x"]}, "tupla"),
        ({"value": "sin_cobertura"}, "sin_cobertura"),
        ({"label": "Titularidad de la finca"}, "vetados"),
        ({"attributions": ("tramo que es público",)}, "vetados"),
    ],
)
def test_fila_invalida(changes: dict[str, object], fragment: str) -> None:
    with pytest.raises(InvalidConvergenceRowError, match=fragment):
        _row(**changes)


def test_filas_de_imagen() -> None:
    image = _row(
        source_key="ortofoto:reciente",
        label="Ortofoto reciente",
        evidence_kind="imagen",
        value="imagen_disponible",
        links=("https://x.invalid/a",),
    )
    assert image.links == ("https://x.invalid/a",)
    with pytest.raises(InvalidConvergenceRowError, match="https"):
        dataclasses.replace(image, links=("http://x.invalid/a",))
    with pytest.raises(InvalidConvergenceRowError, match="links"):
        dataclasses.replace(image, links=())
    empty = ConvergenceRow(
        "ortofoto:1975", "Ortofoto 1975", "imagen", "sin_cobertura", None, None, (), ()
    )
    assert list(empty.strings()) == ["Ortofoto 1975", "Sin cobertura"]


def test_fila_de_catastro() -> None:
    catastro = _row(
        source_key="catastro_vt", label=CATASTRO_ROW_LABEL, attributions=(CATASTRO_ATTRIBUTION,)
    )
    assert catastro.value == "aparece"
    with pytest.raises(InvalidConvergenceRowError, match="label de Catastro"):
        dataclasses.replace(catastro, label="Catastro")
    none = ConvergenceRow(
        "catastro_vt", CATASTRO_ROW_LABEL, "trazado", "sin_cobertura", None, None, (), ()
    )
    assert none.value == "sin_cobertura"


# --- ConvergenceTable. ------------------------------------------------------------------
@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"stretch_id": "ABC"}, "stretch_id"),
        ({"municipality_code": "2804"}, "municipality_code"),
        ({"title": "Otro título"}, "title"),
        ({"warning": "Otro aviso"}, "warning"),
        ({"method": CriterionRef("convergencia_fuentes", 2)}, "method"),
        ({"criterion": CriterionRef("discrepancia_trazados", 2)}, "criterion"),
        ({"appears_min_fraction": 0.0}, "appears_min_fraction"),
        ({"appears_min_fraction": 1.5}, "appears_min_fraction"),
        ({"appears_min_fraction": float("nan")}, "appears_min_fraction"),
        ({"rows": [_row()]}, "tupla"),
        ({"rows": (_row(), _row())}, "repetidos"),
    ],
)
def test_tabla_invalida(changes: dict[str, object], fragment: str) -> None:
    with pytest.raises(InvalidConvergenceTableError, match=fragment):
        _table(**changes)


def test_tabla_textos_con_titulo_y_aviso() -> None:
    strings = list(_table().strings())
    assert strings[0] == CONVERGENCE_TITLE and strings[-1] == CONVERGENCE_WARNING
    assert _table(appears_min_fraction=1).appears_min_fraction == 1


# --- ConvergenceStretch y conversiones. -------------------------------------------------
@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"stretch_id": "0123"}, "stretch_id"),
        ({"municipality_code": "x"}, "municipality_code"),
        ({"origin": "ign_red_transporte"}, "origin"),
        ({"shape": "linea"}, "shape"),
        ({"shape": MultiLineGeometry(lines=TRAMO.lines, srid=4326)}, "EPSG"),
        ({"shape": MultiLineGeometry(lines=(), srid=25830)}, "medible"),
        ({"shape": MultiLineGeometry(lines=((p(0, 0),),), srid=25830)}, "medible"),
        ({"shape": MultiLineGeometry(lines=((p(0, 0), p(0, 0)),), srid=25830)}, "medible"),
        ({"shape": Geometry(rings=(), srid=25830)}, "medible"),
    ],
)
def test_tramo_invalido(changes: dict[str, object], fragment: str) -> None:
    with pytest.raises(InvalidConvergenceStretchError, match=fragment):
        dataclasses.replace(stretch(TRAMO), **changes)  # type: ignore[arg-type]


def test_tramo_desde_un_candidato() -> None:
    subject = TrailRef("VP1", origin("via_pecuaria_oficial"))
    candidate = CutCandidate(
        candidate_id="aaaaaaaaaaaaaaaa",
        municipality_code=INE,
        subject=subject,
        discrepancy_ids=("bbbbbbbbbbbbbbbb",),
        stretch=TRAMO,
        conditions=("no_se_distingue",),
        signals=(_support(),),
        confidence=0.5,
        evidence=(Measurement("longitud_tramo_m", 200.0, "m"),),
        method=CriterionRef("candidatos_corte", 1),
    )
    converted = stretch_from_candidate(candidate)
    assert converted == ConvergenceStretch("aaaaaaaaaaaaaaaa", INE, subject.source, TRAMO)


def _support() -> SignalSupport:
    return SignalSupport(SignalRef("parcela_no_camino", 1, "no_se_distingue"), 1.0, 0.0, ())


def test_eje_de_imagen() -> None:
    assert image_axis(TRAMO) is TRAMO
    axis = image_axis(strip(0, -5, 200, 5))
    assert isinstance(axis, MultiLineGeometry)
    # Pseudo-eje de una franja de 200 × 10 m: a h = área / perímetro = 2000 / 420 del borde.
    h = 2000 / 420
    ys = {round(y - 4435000, 6) for part in axis.lines for _, y in part}
    assert round(-5 + h, 6) in ys and round(5 - h, 6) in ys


# --- Fuentes de fila. -------------------------------------------------------------------
def test_fuentes_de_fila_validas_e_invalidas() -> None:
    assert len(CONVERGENCE_ROW_SOURCES) == 5 + len(COMPARISON_SLOTS)
    with pytest.raises(ValueError, match="no admite"):
        LayerRowSource("planimetria_historica")
    with pytest.raises(ValueError, match="no admite"):
        HistoricRowSource("catastron")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="no existe"):
        OrthophotoRowSource("1960")


# --- Capas. -----------------------------------------------------------------------------
def test_prepare_layer_ordena_omite_vacias_y_anota_fechas() -> None:
    trails = layer(
        "ign_red_transporte",
        {
            "B": line((0, 0), (10, 0)),
            "A": MultiLineGeometry(lines=(), srid=25830),
            "C": line((0, 5), (10, 5)),
        },
        {"B": date(2017, 1, 1), "C": date(2026, 1, 1)},
    )
    prepared = prepare_layer(trails)
    assert [item.ref.trail_id for _, item in prepared.items] == ["B", "C"]
    assert prepared.years == YearSpan(2017, 2026)
    assert prepared.consulted_on == date(2026, 11, 26)
    assert prepared.source_ref.data_date is None
    assert prepare_layer(layer("ign_red_transporte", {"B": TRAMO})).years is None


def test_prepare_layer_rechaza_trazados_de_otra_fuente() -> None:
    bad = dataclasses.replace(
        layer("ign_red_transporte", {}),
        trails=(make_trail("X", "catastro_vt", TRAMO),),
    )
    with pytest.raises(ValueError, match="no de ign_red_transporte"):
        prepare_layer(bad)


def test_layer_row_rechaza_capa_de_otra_fuente() -> None:
    prepared = prepare_layer(layer("catastro_vt", {"99999A00109001": TRAMO}))
    with pytest.raises(ValueError, match="no de ign_red_transporte"):
        layer_row(stretch(TRAMO), "ign_red_transporte", prepared)


def test_umbral_configurable() -> None:
    half = prepare_layer(layer("ign_red_transporte", {"T": line((0, 0), (100, 0))}))  # 0,525
    subject = stretch(TRAMO)
    assert layer_row(subject, "ign_red_transporte", half).value == "aparece"
    assert layer_row(subject, "ign_red_transporte", half, 0.6).value == "no_aparece"
    assert layer_row(subject, "ign_red_transporte", half, 0.525).value == "aparece"
    assert appears(subject, half.source_ref, [i for _, i in half.items], 1.0) is False
    for bad in (0, -0.1, 1.01, True, "0.5"):
        with pytest.raises(ValueError, match="appears_min_fraction"):
            appears(subject, half.source_ref, [], bad)  # type: ignore[arg-type]
    table = build_convergence_table(
        subject,
        (LayerRowSource("ign_red_transporte"),),
        {"ign_red_transporte": half},
        {},
        None,
        0.6,
    )
    assert table.appears_min_fraction == 0.6
    assert table.rows[0].value == "no_aparece"


def test_sin_trazados_en_la_capa_no_aparece() -> None:
    empty = prepare_layer(layer("via_pecuaria_oficial", {}))
    row = layer_row(stretch(TRAMO), "via_pecuaria_oficial", empty)
    assert row.value == "no_aparece"
    assert row.attributions == (SOURCE_POLICY["via_pecuaria_oficial"].attribution,)


# --- Históricas. ------------------------------------------------------------------------
def test_historica_aparece_fuera_de_las_unidades_toma_el_ano_de_todas() -> None:
    far = unit("280075-w1", strip(1000, 1000, 1100, 1100), document_date=date(1870, 1, 1))
    trail = historic_trail("280075-w1-T001", [(0, 0), (200, 0)])
    row = historic_row(stretch(TRAMO), coverage("planimetria", [far], [trail]))
    assert row.value == "aparece"
    assert row.years == YearSpan(1870, 1870)
    assert row.source_key == "planimetria_historica"


def test_historica_varias_unidades_cubren_juntas() -> None:
    left = unit("280075-w1", strip(-50, -50, 120, 50), document_date=date(1875, 8, 6))
    right = unit(
        "280246-w1",
        strip(100, -50, 250, 50),
        document_date=date(1878, 3, 1),
        retrieved_at=date(2026, 11, 22),
    )
    away = unit("280264-w1", strip(5000, 5000, 5100, 5100), document_date=date(1860, 1, 1))
    row = historic_row(stretch(TRAMO), coverage("planimetria", [left, right, away]))
    assert row.value == "no_aparece"
    assert row.years == YearSpan(1875, 1878)  # solo las que contienen el tramo
    assert row.consulted_on == date(2026, 11, 22)


def test_historica_mtn50() -> None:
    sheet = unit(
        "0606-w1", strip(-50, -50, 250, 50), document_kind="mtn50", document_date=date(1881, 1, 1)
    )
    row = historic_row(stretch(TRAMO), coverage("mtn50", [sheet]))
    assert (row.source_key, row.label, row.value) == (
        "mtn50_historico",
        "MTN50, primera edición (IGN)",
        "no_aparece",
    )
    assert row.years == YearSpan(1881, 1881)


def test_falta_la_cobertura_historica() -> None:
    with pytest.raises(ValueError, match="falta la cobertura"):
        build_convergence_table(stretch(TRAMO), (HistoricRowSource("mtn50"),), {}, {}, None)


# --- Ortofotos. -------------------------------------------------------------------------
def test_ortofotos_de_varias_ventanas_llevan_los_enlaces_en_orden() -> None:
    long = lines([(0, 0), (900, 0)])
    rows = orthophoto_rows(stretch(long), comparison_for(long), SLOTS)
    recent = rows[-1]
    assert len(recent.links) >= 3
    assert recent.links == tuple(
        f"https://example.invalid/wms?ventana={i}&vuelo=2023" for i in range(len(recent.links))
    )
    assert len(recent.attributions) == 1


def test_ortofotos_solo_las_franjas_pedidas() -> None:
    rows = orthophoto_rows(stretch(TRAMO), comparison_for(TRAMO), ("reciente", "1975"))
    assert [row.source_key for row in rows] == ["ortofoto:reciente", "ortofoto:1975"]
    with pytest.raises(ValueError, match="no existe"):
        orthophoto_rows(stretch(TRAMO), comparison_for(TRAMO), ("1960",))


def test_ortofotos_sin_imagenes_y_sin_comparacion() -> None:
    empty = comparison_for(TRAMO, slot_vintages=NO_IMAGES_SLOT_VINTAGES)
    assert {row.value for row in orthophoto_rows(stretch(TRAMO), empty, SLOTS)} == {"sin_cobertura"}
    with pytest.raises(StretchNotComputableError) as error:
        orthophoto_rows(stretch(TRAMO), None, SLOTS)
    assert error.value.reason == NOT_IN_MANIFEST


def test_tabla_sin_fuentes_de_imagen_no_mira_la_comparacion() -> None:
    table = build_convergence_table(
        stretch(TRAMO), (LayerRowSource("catastro_vt"),), {}, empty_coverages(), None
    )
    assert [row.value for row in table.rows] == ["sin_cobertura"]
