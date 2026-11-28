import math

from parcel_intel.domain.width_signal import (
    MAX_CONFIDENCE,
    NARROWING_RATIO_THRESHOLD,
    WidthAssessment,
    assess_width,
    official_width_m,
    piece_ids,
)

# Franja de 1000 x 10 m: W = 10 m.


def _assess(covered: float, count: int = 1, **overrides: float) -> WidthAssessment:
    args = {"source_area": 10000.0, "source_length": 1000.0, "piece_area": 10000.0}
    args.update(overrides)
    return assess_width(
        "Vereda",
        args["source_area"],
        args["source_length"],
        args["piece_area"],
        covered,
        count,
    )


def test_anchura_oficial_es_area_entre_longitud() -> None:
    assert official_width_m(11100.0, 1000.0) == 11.1


def test_anchura_oficial_no_derivable() -> None:
    for area, length in [(0.0, 10.0), (10.0, 0.0), (math.nan, 10.0), (10.0, math.inf), (-1, 5)]:
        assert official_width_m(area, length) is None


def test_indicio_si_la_anchura_catastral_es_muy_inferior() -> None:
    result = _assess(4000.0, 2)
    assert result.outcome == "indicio"
    assert result.ratio is not None
    assert abs(result.ratio - 0.4) < 1e-9
    assert result.evidence is not None
    assert result.evidence.cadastral_width_m == 4.0
    assert result.evidence.official_width_m == 10.0
    assert result.evidence.road_parcel_count == 2
    assert result.confidence is not None
    assert 0.0 < result.confidence <= MAX_CONFIDENCE


def test_sin_indicio_en_el_umbral_y_por_encima() -> None:
    at_threshold = 10000.0 * NARROWING_RATIO_THRESHOLD
    assert _assess(at_threshold).outcome == "sin_indicio"
    assert _assess(9500.0).outcome == "sin_indicio"
    assert _assess(20000.0).ratio == 1.0


def test_sin_parcela_de_camino() -> None:
    assert _assess(0.0, 0).outcome == "sin_parcela_camino"


def test_sin_datos_con_motivo() -> None:
    for result in (
        _assess(5000.0, source_length=0.0),
        _assess(5000.0, source_area=math.nan),
        _assess(5000.0, source_area=20.0, source_length=1000.0),  # W = 0,02 m
        _assess(5000.0, piece_area=100.0),  # pieza de 10 m
    ):
        assert result.outcome == "sin_datos"
        assert result.reason
        assert result.ratio is None and result.evidence is None


def test_ids_de_pieza() -> None:
    assert piece_ids(["A", "B", "A"]) == ["A-1", "B", "A-2"]
