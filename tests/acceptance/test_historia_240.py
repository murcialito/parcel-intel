"""Tests de aceptación de la historia #240: tabla de convergencia de fuentes de un tramo.

Todas las fixtures son SINTÉTICAS (`tests/convergence_support.py`). Los oráculos de CA9 son
los del arquitecto, confirmados con la función pública `compare_trail` (lección 0017): se
comprueba el tipo y la fracción que da `compare_trail` además del valor de la fila.

Adaptación anotada en la PR: por decisión del fundador en la issue (comentario posterior al
diseño, «documenta ese 50 % y que sea configurable»), el umbral `APPEARS_MIN_FRACTION` es el
valor por defecto de un parámetro `appears_min_fraction` del cálculo y del caso de uso, y
cada `ConvergenceTable` anota el que usó (campo añadido a la lista blanca de CA4).

Actualizado por #315 (ADR 0057 §4, CA10): `ConvergenceTable` gana el último campo
`images_unavailable` (un `bool`, que entra en la lista blanca de tipos) y el método pasa a
`("convergencia_fuentes", 2)`.
"""

import dataclasses
import re
import typing
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.application.build_convergence_tables import (
    NO_MANIFEST,
    BuildConvergenceTablesUseCase,
)
from parcel_intel.domain.comparison_image import (
    COMPARISON_SLOTS,
    DECLARED_GAPS,
    ComparisonManifest,
    StretchComparison,
)
from parcel_intel.domain.convergence import (
    APPEARS_MIN_FRACTION,
    CATASTRO_ROW_LABEL,
    CONVERGENCE_METHOD,
    CONVERGENCE_ROW_SOURCES,
    CONVERGENCE_TEXT_VALIDATION,
    CONVERGENCE_TITLE,
    CONVERGENCE_WARNING,
    LAYER_ROW_LABEL,
    ORTHOPHOTO_ROW_LABEL,
    VALUE_TEXT,
    ConvergenceNotComputableError,
    ConvergenceRow,
    ConvergenceTable,
    HistoricRowSource,
    InvalidConvergenceRowError,
    InvalidConvergenceStretchError,
    LayerRowSource,
    OrthophotoRowSource,
    PreparedLayer,
    RowSource,
    YearSpan,
    build_convergence_table,
    compute_convergence_text_hash,
    convergence_text_fingerprint,
    image_axis,
    prepare_layer,
    stretch_from_discrepancy,
    vetoed_terms_in,
)
from parcel_intel.domain.discrepancy import (
    ComparableTrail,
    Discrepancy,
    SourceRef,
    TrailRef,
    compare_trail,
)
from parcel_intel.domain.discrepancy_criterion import CRITERION, CriterionRef
from parcel_intel.domain.discrepancy_detection import record_id
from parcel_intel.domain.discrepancy_report import DiscrepancyRecord, TrailLayer
from parcel_intel.domain.geometry import Geometry, LineGeometry, MultiLineGeometry
from parcel_intel.domain.georeferencing import (
    AffineTransform,
    ControlPoint,
    ControlPointSet,
    unit_footprint,
)
from parcel_intel.domain.historic_coverage import HistoricCoverage
from parcel_intel.domain.historic_trail import HistoricDocumentKind
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.public_card import CATASTRO_ATTRIBUTION, SOURCE_POLICY
from parcel_intel.domain.published_comparison import (
    INCOHERENT,
    NOT_IN_MANIFEST,
    TOO_LONG,
)
from parcel_intel.domain.published_discrepancy import CADASTRAL_REFERENCE_RE
from parcel_intel.domain.trail import SourceKind
from tests.convergence_support import (
    INE,
    NO_IMAGES_SLOT_VINTAGES,
    STRETCH_ID,
    X0,
    Y0,
    FakeComparisons,
    FakeHistoric,
    FakeLayers,
    comparison_for,
    coverage,
    empty_coverages,
    historic_trail,
    layer,
    line,
    lines,
    manifest,
    stretch,
    strip,
    unit,
)

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
TRAMO = line((0, 0), (200, 0))
LAYER_SOURCES: tuple[RowSource, ...] = (
    LayerRowSource("via_pecuaria_oficial"),
    LayerRowSource("ign_red_transporte"),
    LayerRowSource("catastro_vt"),
)
NO_IMAGE_SOURCES: tuple[RowSource, ...] = tuple(
    s for s in CONVERGENCE_ROW_SOURCES if not isinstance(s, OrthophotoRowSource)
)


def _row(table: ConvergenceTable, key: str) -> ConvergenceRow:
    return next(row for row in table.rows if row.source_key == key)


def _table(
    shape: MultiLineGeometry | Geometry = TRAMO,
    layers: dict[SourceKind, PreparedLayer] | None = None,
    historic: dict[HistoricDocumentKind, HistoricCoverage] | None = None,
    sources: tuple[RowSource, ...] = NO_IMAGE_SOURCES,
    comparison: StretchComparison | None = None,
    kind: SourceKind = "ign_red_transporte",
) -> ConvergenceTable:
    return build_convergence_table(
        stretch(shape, kind),
        sources,
        layers or {},
        historic if historic is not None else empty_coverages(),
        comparison,
    )


def _prepared(kind: SourceKind, **shapes: MultiLineGeometry | Geometry) -> PreparedLayer:
    return prepare_layer(layer(kind, shapes))


FULL_KINDS: tuple[SourceKind, ...] = ("via_pecuaria_oficial", "ign_red_transporte", "catastro_vt")


def _raw_layer(kind: SourceKind) -> TrailLayer:
    if kind == "via_pecuaria_oficial":
        return layer(kind, {"VP1": strip(-10, -2, 210, 8)}, {"VP1": date(2014, 5, 1)})
    if kind == "ign_red_transporte":
        return layer(
            kind,
            {"IGN2": line((0, 0), (100, 0)), "IGN1": line((0, 400), (200, 400))},
            {"IGN1": date(2017, 1, 1), "IGN2": date(2026, 3, 1)},
        )
    return layer(kind, {"99999A00109001": strip(-5, -4, 205, 4)})


def _full_inputs() -> tuple[dict[SourceKind, PreparedLayer], StretchComparison]:
    layers = {kind: prepare_layer(_raw_layer(kind)) for kind in FULL_KINDS}
    return layers, comparison_for(TRAMO)


def _full_table() -> ConvergenceTable:
    layers, comparison = _full_inputs()
    return _table(layers=layers, sources=CONVERGENCE_ROW_SOURCES, comparison=comparison)


def test_ca1_via_pecuaria_aparece_con_su_fecha_y_no_aparece_sin_trazado_cercano() -> None:
    """CA1. Dado un tramo y un conjunto de capas con un trazado de la vía pecuaria oficial a
    menos de la tolerancia del ADR 0025, cuando se calcula la convergencia, entonces la fila
    «Vía pecuaria oficial» sale «Aparece» con el año/fecha de la capa; con la capa presente y
    sin trazado cercano, «No aparece»."""
    near = prepare_layer(
        layer("via_pecuaria_oficial", {"VP1": strip(-10, -2, 210, 8)}, {"VP1": date(2014, 5, 1)})
    )
    row = _row(_table(layers={"via_pecuaria_oficial": near}), "via_pecuaria_oficial")
    assert row.label == "Vía pecuaria oficial"
    assert row.value == "aparece"
    assert row.years == YearSpan(2014, 2014)
    assert row.consulted_on == date(2026, 11, 26)  # fecha de la procedencia de la capa
    assert row.attributions == (SOURCE_POLICY["via_pecuaria_oficial"].attribution,)

    far = _prepared("via_pecuaria_oficial", VP1=strip(-10, 500, 210, 510))
    row = _row(_table(layers={"via_pecuaria_oficial": far}), "via_pecuaria_oficial")
    assert row.value == "no_aparece"
    assert row.years is None  # la capa no declara fecha: «año no declarado»
    assert "año no declarado" in list(row.strings())
    assert row.consulted_on == date(2026, 11, 26)


def test_ca2_fuente_sin_cobertura_nunca_no_aparece() -> None:
    """CA2. Dado un tramo y una fuente cuya capa no cubre la zona (o no se cargó), cuando se
    calcula, entonces su fila sale «Sin cobertura» y nunca «No aparece»."""
    table = _table(layers={})
    for kind in ("via_pecuaria_oficial", "ign_red_transporte", "catastro_vt"):
        row = _row(table, kind)
        assert row.value == "sin_cobertura"
        assert (row.years, row.consulted_on, row.links, row.attributions) == (None, None, (), ())

    # Por el caso de uso: el port dice que no hay capa (TrailLayerUnavailableError).
    use_case = BuildConvergenceTablesUseCase(
        FakeLayers(), FakeHistoric(), FakeComparisons(), sources=NO_IMAGE_SOURCES
    )
    result = use_case.execute(INE, [stretch(TRAMO)]).results[0]
    assert result.table is not None
    assert {row.value for row in result.table.rows} == {"sin_cobertura"}

    # Una unidad histórica que no cubre la zona del tramo tampoco dice «No aparece».
    far_unit = unit("280075-w1", strip(1000, 1000, 2000, 2000))
    historic = {**empty_coverages(), "planimetria": coverage("planimetria", [far_unit])}
    assert _row(_table(historic=historic), "planimetria_historica").value == "sin_cobertura"


def test_ca3_filas_de_las_cinco_fuentes_e_historicas_sin_cobertura() -> None:
    """CA3. Dado el tramo, cuando se calcula, entonces hay filas para vía pecuaria oficial,
    camino actual (IGN), Catastro (vía de comunicación), planimetría de 1875 y MTN50 de 1881;
    las dos históricas salen «Sin cobertura» si ninguna unidad georreferenciada aprobada
    cubre el tramo."""
    layers, _ = _full_inputs()
    table = _table(layers=layers)
    keys = [row.source_key for row in table.rows]
    assert keys == [
        "via_pecuaria_oficial",
        "ign_red_transporte",
        "catastro_vt",
        "planimetria_historica",
        "mtn50_historico",
    ]
    assert [row.label for row in table.rows] == [
        "Vía pecuaria oficial",
        "Camino actual (IGN)",
        "Catastro: vía de comunicación",
        "Planimetría del IGN",
        "MTN50, primera edición (IGN)",
    ]
    assert _row(table, "planimetria_historica").value == "sin_cobertura"
    assert _row(table, "mtn50_historico").value == "sin_cobertura"

    # Una unidad que solo tiene trazados propuestos no cuenta como trazado aprobado, y
    # HistoricCoverage ni siquiera admite construirse con ellos.
    with pytest.raises(ValueError, match="aprobado"):
        coverage(
            "mtn50", [], [historic_trail("0606-w1-T001", [(0, 0), (1, 1)], "mtn50", "proposed")]
        )


_ALLOWED_TYPES = {
    bool,  # images_unavailable (#315)
    str,
    int,
    float,
    date,
    type(None),
    YearSpan,
    CriterionRef,
    ConvergenceRow,
    ConvergenceTable,
}
_FORBIDDEN_TYPES = (
    Geometry,
    MultiLineGeometry,
    LineGeometry,
    Provenance,
    TrailRef,
    SourceRef,
)


def _walk_types(tp: object, seen: set[object]) -> None:
    """Recorre las anotaciones de campos (también anidadas) y falla si alguna es un tipo
    prohibido o desconocido."""
    origin = typing.get_origin(tp)
    if origin is not None:
        for arg in typing.get_args(tp):
            if arg is not Ellipsis:
                _walk_types(arg, seen)
        return
    if typing.get_args(tp):
        return
    if isinstance(tp, type) and issubclass(tp, _FORBIDDEN_TYPES):
        raise AssertionError(f"tipo prohibido en la tabla: {tp}")
    if isinstance(tp, str):
        return  # valores de un Literal
    assert tp in _ALLOWED_TYPES, f"tipo fuera de la lista blanca: {tp!r}"
    if dataclasses.is_dataclass(tp) and tp not in seen:
        seen.add(tp)
        for name, hint in typing.get_type_hints(tp).items():
            del name
            _walk_types(hint, seen)


def test_ca4_catastro_solo_resultado_atribucion_y_aviso() -> None:
    """CA4. Dado el resultado de Catastro, cuando se construye la fila, entonces solo lleva
    «Aparece»/«No aparece», la atribución y el aviso del ADR 0041; ninguna geometría,
    atributo de parcela ni referencia catastral entra en la entidad (se comprueba con un test
    que falla si aparece un campo fuera de la lista blanca)."""
    catastro = _prepared("catastro_vt", **{"99999A00109001": strip(-5, -4, 205, 4)})
    table = _table(layers={"catastro_vt": catastro})
    row = _row(table, "catastro_vt")
    assert row.label == CATASTRO_ROW_LABEL
    assert row.value == "aparece"
    assert row.attributions == (CATASTRO_ATTRIBUTION,)
    assert row.consulted_on == date(2026, 11, 26)
    assert row.links == ()
    far = _prepared("catastro_vt", **{"99999A00109002": strip(-5, 300, 205, 308)})
    assert _row(_table(layers={"catastro_vt": far}), "catastro_vt").value == "no_aparece"

    # (a) Lista blanca exacta de campos.
    assert [f.name for f in dataclasses.fields(ConvergenceRow)] == [
        "source_key",
        "label",
        "evidence_kind",
        "value",
        "years",
        "consulted_on",
        "links",
        "attributions",
    ]
    assert [f.name for f in dataclasses.fields(ConvergenceTable)] == [
        "stretch_id",
        "municipality_code",
        "title",
        "rows",
        "warning",
        "method",
        "criterion",
        "appears_min_fraction",
        "images_unavailable",  # #315
    ]
    # (b) Ningún tipo de campo, ni anidado, es geometría, procedencia o referencia.
    _walk_types(ConvergenceTable, set())
    # (c) El id con forma de referencia de la capa no llega a la tabla.
    assert CADASTRAL_REFERENCE_RE.search("99999A00109001")
    assert not CADASTRAL_REFERENCE_RE.search(repr(table))
    assert "99999" not in repr(table)
    # Catastro no admite otra atribución ni ir sin fecha de consulta.
    with pytest.raises(InvalidConvergenceRowError, match="CATASTRO_ATTRIBUTION"):
        dataclasses.replace(row, attributions=("otra",))
    with pytest.raises(InvalidConvergenceRowError, match="consulted_on"):
        dataclasses.replace(row, consulted_on=None)


def test_ca5_ortofotos_imagen_disponible_o_sin_cobertura() -> None:
    """CA5. Dado un vuelo ortofotográfico con imagen de comparación disponible en #172, cuando
    se construye la fila, entonces su valor es «Imagen disponible» con año y enlace; sin
    imagen o en blanco, «Sin cobertura». Ninguna fila de ortofoto lleva «Aparece» ni «No
    aparece»."""
    table = _full_table()
    images = [row for row in table.rows if row.evidence_kind == "imagen"]
    assert [row.source_key for row in images] == [f"ortofoto:{s.name}" for s in COMPARISON_SLOTS]
    assert [row.label for row in images] == [
        ORTHOPHOTO_ROW_LABEL.format(franja=s.name) for s in COMPARISON_SLOTS
    ]
    assert {row.value for row in images} == {"imagen_disponible", "sin_cobertura"}

    old = _row(table, "ortofoto:1956-1957")
    assert old.value == "imagen_disponible"
    assert old.years == YearSpan(1956, 1957)
    assert old.years.label() == "1956–1957"
    assert old.links == ("https://example.invalid/wms?ventana=0&vuelo=AMS_1956-1957",)
    assert old.consulted_on == date(2026, 11, 27)
    assert old.attributions == (
        "Obra derivada de Orto-AMS 1956-1957 CC-BY 4.0 ejercito.defensa.gob.es",
    )
    madrid = _row(table, "ortofoto:1991")
    assert madrid.years == YearSpan(1991, 1991)
    assert len(madrid.attributions) == 2  # atribución y aviso obligatorio de la IDEM
    pnoa = _row(table, "ortofoto:2006-2011")
    assert pnoa.years == YearSpan(2009, 2009)

    # Sin imagen (omitida «sin_cobertura»: también la imagen en blanco de #124).
    for slot in ("1975", "2014-2020"):
        row = _row(table, f"ortofoto:{slot}")
        assert row.value == "sin_cobertura"
        assert (row.years, row.links, row.attributions) == (None, (), ())
    # Ninguna fila de imagen puede decir «Aparece» ni «No aparece».
    for value in ("aparece", "no_aparece"):
        with pytest.raises(InvalidConvergenceRowError):
            dataclasses.replace(old, value=value, links=())


def _allowed_strings(table: ConvergenceTable) -> set[str]:
    """Todo texto que puede salir de la tabla viene de una constante, un año, una fecha o un
    enlace de #172: ningún texto libre de las fuentes (nombres) puede colarse."""
    allowed = {CONVERGENCE_TITLE, CONVERGENCE_WARNING, "año no declarado"}
    allowed |= set(VALUE_TEXT.values()) | set(LAYER_ROW_LABEL.values())
    allowed |= {ORTHOPHOTO_ROW_LABEL.format(franja=s.name) for s in COMPARISON_SLOTS}
    allowed |= {policy.attribution for policy in SOURCE_POLICY.values()}
    for row in table.rows:
        allowed |= set(row.links) | ({row.years.label()} if row.years else set())
        allowed |= {row.consulted_on.isoformat()} if row.consulted_on else set()
        if row.evidence_kind == "imagen":
            allowed |= set(row.attributions)
            assert all(
                a.startswith("Obra derivada de ") or "informativo" in a for a in row.attributions
            )
    return allowed


def test_ca6_sin_textos_vetados_y_aviso_siempre() -> None:
    """CA6. Dado cualquier resultado, cuando se serializan los textos, entonces ningún valor
    ni texto contiene «es público», «ilegal», «corte» ni nombres de propietarios, y el aviso
    fijo se adjunta siempre."""
    tables = [_full_table(), _table(), _table(layers=_full_inputs()[0])]
    for table in tables:
        strings = list(table.strings())
        assert strings[0] == CONVERGENCE_TITLE
        assert strings[-1] == CONVERGENCE_WARNING
        for text in strings[:-1]:
            assert vetoed_terms_in(text) == (), text
            normalized = text.casefold()
            assert "es público" not in normalized and "ilegal" not in normalized
            assert not re.search(r"\bcorte\b", normalized)
        assert set(strings) <= _allowed_strings(table)
    # El aviso fijo es el único texto que dice «es público», y lo exige la tabla.
    assert "es público" in CONVERGENCE_WARNING
    assert vetoed_terms_in("recorte del término") == ()
    assert vetoed_terms_in("posible corte") == ("corte",)
    with pytest.raises(ValueError, match="warning"):
        dataclasses.replace(tables[0], warning="otro aviso")
    with pytest.raises(InvalidConvergenceRowError, match="vetados"):
        dataclasses.replace(tables[0].rows[0], label="Camino que es público")


def test_ca7_determinista() -> None:
    """CA7. Dados los mismos datos de entrada, cuando se calcula dos veces, entonces la
    salida es idéntica (determinista, sin LLM, sin red)."""
    assert _full_table() == _full_table()
    _, comparison = _full_inputs()
    reversed_layers = {
        kind: prepare_layer(
            dataclasses.replace(_raw_layer(kind), trails=tuple(reversed(_raw_layer(kind).trails)))
        )
        for kind in FULL_KINDS
    }
    again = _table(layers=reversed_layers, sources=CONVERGENCE_ROW_SOURCES, comparison=comparison)
    assert again == _full_table()

    second_axis = line((0, 0), (0, 150))
    stretches = [stretch(TRAMO), stretch(second_axis, stretch_id="fedcba9876543210")]
    comps = manifest(comparison, comparison_for(second_axis, "fedcba9876543210"))
    runs = [
        BuildConvergenceTablesUseCase(
            FakeLayers({kind: _raw_layer(kind) for kind in FULL_KINDS}),
            FakeHistoric(),
            FakeComparisons(comps),
        ).execute(INE, order)
        for order in (stretches, list(reversed(stretches)))
    ]
    assert runs[0] == runs[1]
    assert all(result.table is not None for result in runs[0].results)


def test_ca8_fuente_nueva_anade_fila_sin_cambiar_las_demas() -> None:
    """CA8. Dada una fuente nueva (vuelos de #194, catastrones de #195), cuando se añade a la
    lista de fuentes del caso de uso, entonces aparece una fila nueva sin cambiar las
    existentes (el orden de filas es fijo y está documentado)."""
    layers, comparison = _full_inputs()
    full = _table(layers=layers, sources=CONVERGENCE_ROW_SOURCES, comparison=comparison)
    for index in range(len(CONVERGENCE_ROW_SOURCES)):
        without = CONVERGENCE_ROW_SOURCES[:index] + CONVERGENCE_ROW_SOURCES[index + 1 :]
        smaller = _table(layers=layers, sources=without, comparison=comparison)
        assert smaller.rows == full.rows[:index] + full.rows[index + 1 :]

    # Orden fijo y documentado.
    assert CONVERGENCE_ROW_SOURCES[:5] == (
        LayerRowSource("via_pecuaria_oficial"),
        LayerRowSource("ign_red_transporte"),
        LayerRowSource("catastro_vt"),
        HistoricRowSource("planimetria"),
        HistoricRowSource("mtn50"),
    )
    assert CONVERGENCE_ROW_SOURCES[5:] == tuple(
        OrthophotoRowSource(s.name) for s in COMPARISON_SLOTS
    )
    # Todo tipo de documento histórico tiene su fila (#221 no puede añadir uno sin ella).
    historic = {
        s.document_kind for s in CONVERGENCE_ROW_SOURCES if isinstance(s, HistoricRowSource)
    }
    assert historic == set(typing.get_args(HistoricDocumentKind))
    adr = _adr_text()
    assert "Orden fijo de filas" in adr and "COMPARISON_SLOTS" in adr


def test_ca9_umbral_de_aparece_con_oraculos() -> None:
    """CA9. Dado un tramo sintético `(0,0)→(200,0)` (relativo a `X0 = 450000`,
    `Y0 = 4435000`, EPSG:25830) con origen `ign_red_transporte` y una capa de camino actual
    con un único trazado `(0,0)→(100,0)`, cuando se calcula, entonces la fila «Camino actual
    (IGN)» sale «Aparece» (`compare_trail` da `SOLAPE` con `fraccion_solapada = 0.525`: 21
    piezas cubiertas de 40, tolerancia del par 7,071 m); con el trazado `(0,0)→(90,0)` sale
    «No aparece» (`SOLAPE`, `0.475`). Con una vía pecuaria en franja de 10 m cuyo borde
    cercano está a 20 m del eje del tramo (`DESPLAZAMIENTO`, tolerancia 11,180 m, radio
    33,541 m) la fila sale «No aparece»; con la franja de `y = -2` a `y = 8` (el tramo
    dentro), «Aparece»."""
    assert (X0, Y0) == (450000.0, 4435000.0)
    subject = stretch(TRAMO)

    def compared(
        kind: SourceKind, shape: MultiLineGeometry | Geometry
    ) -> tuple[Discrepancy | None, str]:
        prepared = _prepared(kind, T1=shape)
        d = compare_trail(
            ComparableTrail(TrailRef(STRETCH_ID, subject.origin), subject.shape),
            prepared.source_ref,
            [item for _, item in prepared.items],
        )
        return d, _row(_table(layers={kind: prepared}), kind).value

    d, value = compared("ign_red_transporte", line((0, 0), (100, 0)))
    assert d is not None and d.kind == "SOLAPE"
    assert d.measurement("fraccion_solapada") == 0.525
    assert d.measurement("tolerancia_par_m") == 7.071
    assert value == "aparece"

    d, value = compared("ign_red_transporte", line((0, 0), (90, 0)))
    assert d is not None and d.kind == "SOLAPE" and d.measurement("fraccion_solapada") == 0.475
    assert value == "no_aparece"

    d, value = compared("via_pecuaria_oficial", strip(0, 20, 200, 30))
    assert d is not None and d.kind == "DESPLAZAMIENTO"
    assert d.measurement("tolerancia_par_m") == 11.18
    assert d.measurement("radio_busqueda_m") == 33.541
    assert value == "no_aparece"

    d, value = compared("via_pecuaria_oficial", strip(0, -2, 200, 8))
    assert d is None
    assert value == "aparece"
    assert APPEARS_MIN_FRACTION == 0.5


def _square_footprint(x0: float, y0: float, x1: float, y1: float) -> Geometry:
    return strip(x0, y0, x1, y1)


def test_ca10_cobertura_historica_por_envolvente() -> None:
    """CA10. Dado un tramo y una fuente histórica, cuando una unidad aceptada tiene una
    envolvente que contiene todas las muestras del tramo y ningún trazado aprobado está
    cerca, entonces la fila sale «No aparece»; si la envolvente solo contiene una parte de
    las muestras y no hay trazado aprobado cerca, sale «Sin cobertura»; si un trazado
    aprobado coincide (regla de CA9) sale «Aparece», aunque el tramo se salga en parte de la
    envolvente. Los trazados propuestos o rechazados nunca cuentan: `HistoricCoverage`
    rechaza construirse con ellos. La envolvente es la de los puntos **retenidos**
    transformada con la afín: un punto descartado lejos de los demás no la agranda (oráculo
    de `unit_footprint` en el diseño)."""
    whole = unit(
        "280075-w1", _square_footprint(-100, -100, 300, 100), document_date=date(1875, 8, 6)
    )
    part = unit("280075-w1", _square_footprint(-100, -100, 100, 100))
    far_trail = historic_trail("280075-w1-T001", [(0, 500), (200, 500)])
    near_trail = historic_trail("280075-w1-T001", [(0, 3), (200, 3)])

    def value(cov: HistoricCoverage) -> ConvergenceRow:
        return _row(
            _table(historic={**empty_coverages(), "planimetria": cov}), "planimetria_historica"
        )

    row = value(coverage("planimetria", [whole], [far_trail]))
    assert row.value == "no_aparece"
    assert row.years == YearSpan(1875, 1875)
    assert row.consulted_on == date(2026, 11, 20)
    assert row.attributions == (SOURCE_POLICY["planimetria_historica"].attribution,)
    assert value(coverage("planimetria", [part], [far_trail])).value == "sin_cobertura"
    assert value(coverage("planimetria", [part], [near_trail])).value == "aparece"

    for status in ("proposed", "rejected"):
        with pytest.raises(ValueError, match="aprobado"):
            coverage(
                "planimetria",
                [whole],
                [historic_trail("280075-w1-T002", [(0, 0), (200, 0)], status=status)],
            )

    def cp(point_id: str, col: float, row_: float, retained: bool = True) -> ControlPoint:
        return ControlPoint(
            point_id=point_id,
            col=col,
            row=row_,
            target=(X0 + col, Y0 + 1000 - row_),
            coordinate_source="PNOA sintético",
            description="punto sintético",
            retained=retained,
            discard_reason=None if retained else "residuo alto (sintético)",
        )

    points = ControlPointSet(
        points=(
            cp("P01", 0, 0),
            cp("P02", 1000, 0),
            cp("P03", 1000, 1000),
            cp("P04", 0, 1000),
            cp("P05", 500, 500),
            cp("P06", 250, 750),
            cp("P07", 2000, 2000, retained=False),
        ),
        sha256="5" * 64,
    )
    footprint = unit_footprint(points, AffineTransform(a=X0, b=1, c=0, d=Y0 + 1000, e=0, f=-1))
    assert footprint == Geometry(
        rings=(((X0, Y0 + 1000), (X0 + 1000, Y0 + 1000), (X0 + 1000, Y0), (X0, Y0)),),
        srid=25830,
    )


def test_ca11_imagenes_no_utilizables_dejan_el_tramo_sin_tabla() -> None:
    """CA11. Dado un tramo con imágenes de comparación, cuando el tramo no está en el
    manifiesto, el manifiesto no existe, el tramo es demasiado largo, el manifiesto no
    corresponde al tramo actual o una franja se omitió por `fallo`, entonces no hay tabla para
    ese tramo: el resultado lleva el motivo fijo de `published_comparison` (o `NO_MANIFEST` si
    falta el fichero) y ninguna fila sale «Sin cobertura» por ese motivo. Si el manifiesto es
    de otro municipio, de otra versión de la política o con otros huecos, falla el municipio
    entero (`ConvergenceNotComputableError`). Si el tramo está en el manifiesto y ninguna
    franja tiene imagen, todas las filas de ortofoto salen «Sin cobertura» y la tabla sí se
    calcula."""

    def run(manifest_: ComparisonManifest | None) -> tuple[ConvergenceTable | None, str | None]:
        use_case = BuildConvergenceTablesUseCase(
            FakeLayers(), FakeHistoric(), FakeComparisons(manifest_)
        )
        result = use_case.execute(INE, [stretch(TRAMO)]).results[0]
        return result.table, result.failure

    other = "fedcba9876543210"
    too_long = StretchComparison(
        STRETCH_ID, INE, comparison_for(TRAMO).policy, "tramo_demasiado_largo", (), DECLARED_GAPS
    )
    cases = [
        (manifest(comparison_for(TRAMO, other)), NOT_IN_MANIFEST),
        (None, NO_MANIFEST),
        (manifest(too_long), TOO_LONG),
        (manifest(comparison_for(line((0, 0), (200, 30)))), INCOHERENT),
        (
            manifest(
                comparison_for(TRAMO, slot_vintages=NO_IMAGES_SLOT_VINTAGES, omission="fallo")
            ),
            "una franja se omitió por un fallo de descarga; vuelve a ejecutar imagenes-comparacion",
        ),
    ]
    for manifest_, reason in cases:
        assert run(manifest_) == (None, reason)

    good = manifest(comparison_for(TRAMO))
    for broken in (
        dataclasses.replace(good, municipality_code="28013"),
        dataclasses.replace(good, policy=CriterionRef("imagenes_comparacion", 1)),
        dataclasses.replace(good, gaps=DECLARED_GAPS[:1]),
    ):
        with pytest.raises(ConvergenceNotComputableError):
            run(broken)

    table, failure = run(manifest(comparison_for(TRAMO, slot_vintages=NO_IMAGES_SLOT_VINTAGES)))
    assert failure is None and isinstance(table, ConvergenceTable)
    images = [row for row in table.rows if row.evidence_kind == "imagen"]
    assert len(images) == len(COMPARISON_SLOTS)
    assert {row.value for row in images} == {"sin_cobertura"}


def test_ca12_prefiltro_de_rejilla_igual_que_fuerza_bruta() -> None:
    """CA12. Dado un tramo de dos partes y capas cuyos trazados tienen varias partes (franja
    de dos anillos, multilínea de dos líneas), cuando se calcula con el prefiltro de rejilla
    (`GridIndex`), entonces cada fila es idéntica a la que da `compare_trail` con todos los
    trazados de la capa (fuerza bruta), para todas las filas y con las entradas en orden
    inverso."""
    two_parts = lines([(0, 0), (300, 0)], [(600, 0), (900, 0)])
    ring_a = strip(-10, -3, 310, 7).rings[0]
    ring_b = strip(590, -3, 910, 7).rings[0]
    shapes: dict[SourceKind, dict[str, MultiLineGeometry | Geometry]] = {
        "via_pecuaria_oficial": {
            "VP2": Geometry(rings=(ring_a, ring_b), srid=25830),
            "VP1": strip(2000, 2000, 2400, 2010),
        },
        "ign_red_transporte": {
            "IGN1": lines([(0, 2), (100, 2)], [(600, 40), (900, 40)]),
            "IGN2": line((5000, 0), (5300, 0)),
            "IGN3": lines([(590, -1), (700, -1)], [(-3000, 0), (-2000, 0)]),
        },
        "catastro_vt": {
            "99999A00109003": Geometry(rings=(strip(-5, -4, 120, 4).rings[0], ring_b), srid=25830),
            "99999A00109004": strip(200, -4, 310, 4),
        },
    }
    subject = stretch(two_parts)
    for kind, by_id in shapes.items():
        for order in (list(by_id.items()), list(reversed(by_id.items()))):
            prepared = prepare_layer(layer(kind, dict(order)))
            row = _row(_table(two_parts, layers={kind: prepared}), kind)
            brute = compare_trail(
                ComparableTrail(TrailRef(STRETCH_ID, subject.origin), two_parts),
                prepared.source_ref,
                [item for _, item in prepared.items],
            )
            expected = brute is None or (
                brute.kind == "SOLAPE" and brute.measurement("fraccion_solapada") >= 0.5
            )
            assert row.value == ("aparece" if expected else "no_aparece"), kind
    # Los tres casos no son triviales: hay de los dos valores.
    values = {
        kind: _row(_table(two_parts, layers={kind: prepare_layer(layer(kind, by_id))}), kind).value
        for kind, by_id in shapes.items()
    }
    assert set(values.values()) == {"aparece", "no_aparece"}


def test_ca13_franja_usa_el_pseudo_eje_y_registro_redactado_no_vale() -> None:
    """CA13. Dado un tramo que viene de un indicio cuya zona es una franja (`Geometry`),
    cuando se calculan las filas de ortofoto, entonces se usa `image_axis(zona)` (el
    pseudo-eje del ADR 0025 en una `MultiLineGeometry`) y no la franja; y un registro con
    `zone_redacted = True` no se puede convertir en tramo (`InvalidConvergenceStretchError`)."""
    zone = strip(0, -5, 200, 5)
    via = SourceRef(
        "via_pecuaria_oficial",
        Provenance("sintetica", "https://example.invalid", date(2026, 11, 26), "x"),
        None,
    )
    empty_ign = SourceRef(
        "ign_red_transporte",
        Provenance("sintetica", "https://example.invalid", date(2026, 11, 26), "y"),
        None,
    )
    discrepancy = compare_trail(ComparableTrail(TrailRef("VP1", via), zone), empty_ign, [])
    assert discrepancy is not None and discrepancy.zone == zone
    record = DiscrepancyRecord(record_id(discrepancy), discrepancy, (), zone_redacted=False)
    converted = stretch_from_discrepancy(record, INE)
    assert converted.shape == zone and converted.stretch_id == record.record_id

    axis = image_axis(zone)
    assert isinstance(axis, MultiLineGeometry)
    assert axis.lines and axis.lines != zone.rings
    sources = tuple(s for s in CONVERGENCE_ROW_SOURCES if isinstance(s, OrthophotoRowSource))

    def failure_for(comp: StretchComparison) -> str | None:
        use_case = BuildConvergenceTablesUseCase(
            FakeLayers(), FakeHistoric(), FakeComparisons(manifest(comp)), sources=sources
        )
        return use_case.execute(INE, [converted]).results[0].failure

    assert failure_for(comparison_for(axis, record.record_id)) is None
    as_lines = MultiLineGeometry(lines=zone.rings, srid=25830)  # la franja tomada como línea
    assert failure_for(comparison_for(as_lines, record.record_id)) == INCOHERENT

    with pytest.raises(InvalidConvergenceStretchError, match="redactada"):
        stretch_from_discrepancy(dataclasses.replace(record, zone_redacted=True), INE)


def test_ca14_huella_del_texto_validado() -> None:
    """CA14. Dado el texto público, cuando se calcula la huella canónica de título, valores,
    aviso y rótulo de Catastro, entonces coincide con `CONVERGENCE_TEXT_VALIDATION.text_hash`
    (fecha 2026-11-27 y enlace a la respuesta del fundador en #198); cambiar cualquiera de esos
    textos hace fallar el test."""
    assert compute_convergence_text_hash() == CONVERGENCE_TEXT_VALIDATION.text_hash
    assert CONVERGENCE_TEXT_VALIDATION.validated_by_founder == date(2026, 11, 27)
    assert CONVERGENCE_TEXT_VALIDATION.validation_url == (
        "https://github.com/murcialito/paso-comun/issues/198#issuecomment-7224344953"
    )
    fingerprint = convergence_text_fingerprint()
    for text in (CONVERGENCE_TITLE, CONVERGENCE_WARNING, CATASTRO_ROW_LABEL, *VALUE_TEXT.values()):
        assert text in fingerprint
    # Los literales que fijó el fundador en la issue.
    assert CONVERGENCE_TITLE == "Qué fuentes muestran este trazado"
    assert dict(VALUE_TEXT) == {
        "aparece": "Aparece",
        "no_aparece": "No aparece",
        "sin_cobertura": "Sin cobertura",
        "imagen_disponible": "Imagen disponible",
    }
    assert CATASTRO_ROW_LABEL == "Catastro: vía de comunicación"
    assert CONVERGENCE_WARNING == (
        "Esta tabla recoge qué fuentes muestran un trazado cerca de este tramo y de qué año. "
        "No dice quién tiene razón ni si el camino es público: eso solo lo puede decidir la "
        "administración competente. Cada fuente tiene su propia precisión y puede estar "
        "desactualizada."
    )
    assert CONVERGENCE_METHOD == CriterionRef("convergencia_fuentes", 2)  # v2 desde #315
    assert _full_table().criterion == CRITERION


def _adr_text() -> str:
    matches = [
        path
        for path in sorted((ROOT / "docs" / "adr").glob("*.md"))
        if "Historia: #240" in path.read_text(encoding="utf-8")
    ]
    assert len(matches) == 1
    return matches[0].read_text(encoding="utf-8")


def test_ca15_adr_de_la_historia() -> None:
    """CA15. Dado el ADR nuevo de esta historia (cabecera `Historia: #240`), cuando se lee
    `docs/adr/`, entonces existe con contexto, decisión, umbrales a revisar con el fundador y
    consecuencias, y no hay dos ADR con el mismo número."""
    numbers = [path.name[:4] for path in (ROOT / "docs" / "adr").glob("*.md")]
    assert len(numbers) == len(set(numbers)), "números de ADR repetidos"
    text = _adr_text()
    for heading in ("## Contexto", "## Decisión", "A revisar con el fundador", "## Consecuencias"):
        assert heading in text, heading
    for phrase in ("APPEARS_MIN_FRACTION", "appears_min_fraction", "unit_footprint", "image_axis"):
        assert phrase in text, phrase
