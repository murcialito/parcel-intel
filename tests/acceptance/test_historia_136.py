"""Historia #136: ajuste afín, error LOO y validación de trazados en el dominio (#20, hija A).

Adaptación anotada: el CA12 pide el ADR de #20 «con el siguiente número libre (hoy 0044)»,
pero el 0044 ya lo ocupa #94; el ADR de #20 es el 0045 y se localiza por su cabecera
(`Historias: #20`), no por el número. Los docstrings copian el criterio literal.

Los oráculos del CA2 salen de `numpy.linalg.lstsq` (cálculo en el comentario del test).
"""

import re
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.domain.digitization import (
    DigitizedTrail,
    InvalidDigitizationError,
    StaleApprovalError,
    check_approvals_current,
    check_trails_in_image,
    to_historic_trail,
)
from parcel_intel.domain.georeferencing import (
    IGN_HISTORIC_LICENSE,
    ControlPoint,
    ControlPointSet,
    GeoreferenceFit,
    GeoreferenceUnit,
    InsufficientControlPointsError,
    InvalidControlPointError,
    UnitSpec,
    WorkingImage,
    check_acceptable,
    check_points_in_image,
    fit_affine,
    pixel_hull_contains,
    round_mm,
    thresholds_m,
)
from parcel_intel.domain.historic_trail import derived_work_attribution
from parcel_intel.domain.provenance import Provenance, Redistribution

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
PIXELS = [(100, 100), (900, 150), (500, 400), (150, 700), (850, 650), (300, 300), (700, 500)]


def truth(col: float, row: float) -> tuple[float, float]:
    return 455000 + 2.5 * col + 0.10 * row, 4445000 + 0.12 * col - 2.5 * row


def cp(
    n: int,
    col: float,
    row: float,
    target: tuple[float, float] | None = None,
    retained: bool = True,
    **extra: object,
) -> ControlPoint:
    values: dict[str, object] = {
        "point_id": f"P{n:02d}",
        "col": col,
        "row": row,
        "target": target or truth(col, row),
        "coordinate_source": "PNOA 1:1.000",
        "description": "cruce de caminos",
        "retained": retained,
        "discard_reason": None if retained else "no se reconoce",
    }
    values.update(extra)
    return ControlPoint(**values)  # type: ignore[arg-type]


def exact(pixels: Sequence[tuple[float, float]] = PIXELS) -> list[ControlPoint]:
    return [cp(i + 1, c, r) for i, (c, r) in enumerate(pixels)]


def spec(**overrides: object) -> UnitSpec:
    values: dict[str, object] = {
        "unit_id": "280075-w1",
        "document_id": "280075",
        "document_kind": "planimetria",
        "municipality_code": "28043",
        "document_date": date(1875, 8, 6),
        "document_date_precision": "day",
        "scale_denominator": 25000,
        "image_kind": "wms_render",
        "image_url": "https://www.ign.es/wms/minutas-cartograficas?x=1",
        "image_sha256": "a" * 64,
        "image_width_px": 1000,
        "image_height_px": 800,
        "image_retrieved_at": date(2026, 11, 26),
        "provenance_source": "Planimetría de Colmenar de Oreja, IGN, documento 280075",
        "georeferenced_by": "murcialito",
        "georeferenced_at": NOW,
    }
    values.update(overrides)
    return UnitSpec(**values)  # type: ignore[arg-type]


def trail(**overrides: object) -> DigitizedTrail:
    values: dict[str, object] = {
        "trail_id": "T001",
        "pixels": ((10.0, 20.0), (30.5, 40.25), (50.0, 60.0)),
        "kind": "camino",
        "label": None,
        "status": "approved",
        "reviewed_by": "murcialito",
        "reviewed_at": NOW,
        "review_note": None,
        "control_points_sha256": "c" * 64,
    }
    values.update(overrides)
    return DigitizedTrail(**values)  # type: ignore[arg-type]


def _fit_stub(loo: float = 1.0, max_residual: float = 1.0) -> GeoreferenceFit:
    base = fit_affine(exact())
    return GeoreferenceFit(base.transform, 6, 1.0, max_residual, loo, ())


def test_ca1_afin_conocida_se_recupera() -> None:
    """Dada la afín conocida `x = 455000 + 2.5·col + 0.10·row`, `y = 4445000 + 0.12·col − 2.5·row`
    con 7 puntos retenidos repartidos, cuando se llama a `fit_affine`, entonces los seis parámetros
    tienen error < 1e-6 y RMSE, residuo máximo y LOO son < 1e-6."""
    fit = fit_affine(exact())
    t = fit.transform
    expected = (455000, 2.5, 0.10, 4445000, 0.12, -2.5)
    for got, want in zip((t.a, t.b, t.c, t.d, t.e, t.f), expected, strict=True):
        assert abs(got - want) < 1e-6
    assert fit.rmse_m < 1e-6 and fit.max_residual_m < 1e-6 and fit.loo_rmse_m < 1e-6


def test_ca2_punto_desplazado_coincide_con_numpy() -> None:
    """Dado el mismo caso con un punto desplazado +30 m en X, cuando se ajusta, entonces `rmse_m`,
    `max_residual_m`, `loo_rmse_m` y el residuo de cada punto coinciden (abs 1e-9) con literales
    calculados con `numpy.linalg.lstsq` y escritos en el test. El cálculo del oráculo va en un
    comentario."""
    # Oráculo: A = [[1, col, row]] de los 7 puntos; bx, by = numpy.linalg.lstsq(A, x), (A, y) con
    # el P03 (500, 400) desplazado +30 m en X; residuo = hypot(A@bx - x, A@by - y); LOO = repetir el
    # ajuste quitando cada punto y medir su residuo; rmse = sqrt(mean(r²)), loo = sqrt(mean(loo²)).
    points = exact()
    x, y = points[2].target
    points[2] = cp(3, 500, 400, (x + 30.0, y))
    fit = fit_affine(points)
    assert fit.rmse_m == pytest.approx(10.497813183353083, abs=1e-9)
    assert fit.max_residual_m == pytest.approx(25.714285714377183, abs=1e-9)
    assert fit.loo_rmse_m == pytest.approx(14.39756287866481, abs=1e-9)
    residuals = [
        4.285714285681024,
        4.285714285564609,
        25.714285714377183,
        4.285714285681024,
        4.285714285564609,
        4.2857142856228165,
        4.285714285564609,
    ]
    loo = [
        11.377717453520745,
        11.519354242656846,
        30.000000000058208,
        12.484105927171186,
        8.446772117866203,
        5.553372006397694,
        5.553372006164864,
    ]
    assert [r.residual_m for r in fit.residuals] == pytest.approx(residuals, abs=1e-9)
    assert [r.loo_residual_m for r in fit.residuals] == pytest.approx(loo, abs=1e-9)


def test_ca3_puntos_insuficientes_con_motivo_distinto() -> None:
    """Dados 5 puntos retenidos, 6 colineales, 6 con dos repetidos, o 6 donde quitar uno deja 5
    colineales (LOO indeterminada), cuando se ajusta, entonces se lanza
    `InsufficientControlPointsError` con un motivo que lo distingue."""
    line = [(100.0 * i, 50.0 * i) for i in range(1, 7)]
    repeated = [(100, 100), (100, 100), (100, 100), (800, 600), (800, 600), (800, 600)]
    loo_case = [(100.0 * i, 50.0 * i) for i in range(1, 6)] + [(300.0, 700.0)]
    cases = {
        "menos de 6": exact(PIXELS[:5]),
        "colineales": exact(line),
        "repetidos": exact(repeated),
        "LOO indeterminada": exact(loo_case),
    }
    messages = []
    for fragment, points in cases.items():
        with pytest.raises(InsufficientControlPointsError, match=fragment) as info:
            fit_affine(points)
        messages.append(str(info.value))
    assert len(set(messages)) == 4


def test_ca4_umbrales_por_escala() -> None:
    """Dada una unidad 1:25.000, cuando se llama a `thresholds_m(25000)` y `thresholds_m(50000)`,
    entonces devuelven `(15.0, 35.0)` y `(30.0, 70.0)` exactos."""
    assert thresholds_m(25000) == (15.0, 35.0)
    assert thresholds_m(50000) == (30.0, 70.0)


def test_ca5_check_acceptable_motivos() -> None:
    """Dado un ajuste con LOO 15,01 m, otro con residuo máximo 35,01 m, 6 retenidos en solo 2
    cuadrantes y 9 candidatos con 3 descartados (33 %), cuando se llama a `check_acceptable`,
    entonces cada uno da `ok=False` con un motivo que nombra la métrica, el valor con 2 decimales y
    el umbral. Un caso que incumple dos reglas devuelve los dos motivos. Con LOO = 15,00 exacto da
    `ok=True`."""
    spread = exact([(100, 100), (900, 100), (100, 700), (900, 700), (500, 400), (300, 300)])
    north = exact([(100, 100), (900, 100), (200, 200), (800, 300), (300, 150), (600, 50)])
    discarded = [cp(20 + i, 400 + i, 500, retained=False) for i in range(3)]

    loo = check_acceptable(spread, _fit_stub(loo=15.01), spec())
    assert not loo.ok and "rmse_loo" in loo.reasons[0]
    assert "15.01" in loo.reasons[0] and "15.00" in loo.reasons[0]
    residual = check_acceptable(spread, _fit_stub(max_residual=35.01), spec())
    assert not residual.ok and "residuo_max" in residual.reasons[0]
    assert "35.01" in residual.reasons[0] and "35.00" in residual.reasons[0]
    quadrants = check_acceptable(north, _fit_stub(), spec())
    assert not quadrants.ok and "cuadrantes" in quadrants.reasons[0]
    assert "2" in quadrants.reasons[0] and "3" in quadrants.reasons[0]
    ratio = check_acceptable([*spread, *discarded], _fit_stub(), spec())
    assert not ratio.ok and "descartados" in ratio.reasons[0]
    assert "33.33" in ratio.reasons[0] and "25.00" in ratio.reasons[0]

    two = check_acceptable(north, _fit_stub(loo=15.01), spec())
    assert not two.ok and len(two.reasons) == 2
    assert check_acceptable(spread, _fit_stub(loo=15.00), spec()).ok


@pytest.mark.parametrize(
    "overrides",
    [
        {"row": -1.0},
        {"col": -1.0},
        {"col": float("inf")},
        {"row": float("nan")},
        {"coordinate_source": "Catastro"},
        {"coordinate_source": "catastro"},
        {"coordinate_source": "CATASTRO"},
        {"retained": False, "discard_reason": None},
        {"retained": True, "discard_reason": "motivo"},
        {"target": (-3.4, 40.1)},
        {"point_id": "P1"},
        {"point_id": "Q01"},
        {"point_id": "P0001"},
    ],
)
def test_ca6_control_point_invalido(overrides: dict[str, Any]) -> None:
    """Dado un `ControlPoint` con `row` o `col` negativos, no finitos, `coordinate_source`
    "Catastro"/"catastro"/"CATASTRO", descartado sin `discard_reason`, retenido con
    `discard_reason`, `x` en grados (p. ej. −3.4) o `point_id` fuera de `^P[0-9]{2,3}$`, cuando se
    construye, entonces lanza `InvalidControlPointError`. Y `check_points_in_image` rechaza un
    punto con `col > width_px`."""
    with pytest.raises(InvalidControlPointError):
        values = {"col": 10.0, "row": 10.0, **overrides}
        cp(1, values.pop("col"), values.pop("row"), **values)


def test_ca6_punto_fuera_de_la_imagen() -> None:
    """Dado un `ControlPoint` con `row` o `col` negativos [...] Y `check_points_in_image` rechaza un
    punto con `col > width_px`."""
    with pytest.raises(InvalidControlPointError):
        check_points_in_image([cp(1, 1000.5, 10.0)], 1000, 800)
    check_points_in_image([cp(1, 1000.0, 800.0)], 1000, 800)


def test_ca7_envolvente_de_retenidos() -> None:
    """Dada una envolvente de retenidos, cuando se llama a `pixel_hull_contains`, entonces es
    `True` para un punto interior, un punto sobre una arista y un vértice, y `False` para un punto
    a 0,01 px fuera. Incluye una envolvente con tres puntos colineales en un lado."""
    square = [cp(1, 0, 0), cp(2, 100, 0), cp(3, 100, 100), cp(4, 0, 100)]
    assert pixel_hull_contains(square, 50, 50)
    assert pixel_hull_contains(square, 50, 0)
    assert pixel_hull_contains(square, 0, 0)
    assert not pixel_hull_contains(square, 100.01, 50)
    collinear = [cp(1, 0, 0), cp(2, 50, 0), cp(3, 100, 0), cp(4, 100, 100), cp(5, 0, 100)]
    assert pixel_hull_contains(collinear, 25, 0)
    assert pixel_hull_contains(collinear, 50, 50)
    assert not pixel_hull_contains(collinear, 50, -0.01)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "desconocido"},
        {"reviewed_by": None},
        {"reviewed_at": None},
        {"control_points_sha256": None},
        {"reviewed_at": datetime(2026, 11, 26, 12, 0)},
        {"status": "rejected", "review_note": None, "control_points_sha256": None},
        {"status": "proposed", "control_points_sha256": None},
        {"pixels": ((1.0, 1.0), (1.0, 1.0))},
        {"pixels": ((1.0, 1.0), (-1.0, 3.0))},
    ],
)
def test_ca8_trazado_invalido(overrides: dict[str, object]) -> None:
    """Dados `DigitizedTrail` con estado desconocido, `approved` sin `reviewed_by`, `reviewed_at`
    o `control_points_sha256`, `reviewed_at` sin zona, `rejected` sin `review_note`, `proposed` con
    `reviewed_by`, un solo vértice distinto o un vértice negativo, cuando se construyen, entonces
    lanzan `InvalidDigitizationError` con el `trail_id` en el mensaje."""
    with pytest.raises(InvalidDigitizationError, match="T001"):
        trail(**overrides)


def test_ca8_vertice_fuera_de_la_imagen() -> None:
    """Y `check_trails_in_image` rechaza un vértice con `row > height_px`."""
    with pytest.raises(InvalidDigitizationError, match="T001"):
        check_trails_in_image([trail(pixels=((0.0, 0.0), (10.0, 800.5)))], 1000, 800)


def test_ca9_aprobaciones_caducadas() -> None:
    """Dados dos trazados aprobados, uno con el `control_points_sha256` actual y otro con uno
    distinto, cuando se llama a `check_approvals_current`, entonces lanza `StaleApprovalError` con
    el `trail_id` caducado. Los `proposed` y `rejected` no se comprueban."""
    current = trail(trail_id="T001")
    stale = trail(trail_id="T002", control_points_sha256="d" * 64)
    proposed = trail(
        trail_id="T003",
        status="proposed",
        reviewed_by=None,
        reviewed_at=None,
        control_points_sha256=None,
    )
    rejected = trail(
        trail_id="T004", status="rejected", review_note="no", control_points_sha256="e" * 64
    )
    with pytest.raises(StaleApprovalError) as info:
        check_approvals_current([current, stale, proposed, rejected], "c" * 64)
    assert info.value.trail_ids == ("T002",)
    check_approvals_current([current, proposed, rejected], "c" * 64)


def _unit() -> GeoreferenceUnit:
    image = WorkingImage(
        "wms_render",
        "a" * 64,
        1000,
        800,
        "image/png",
        Provenance(
            source="Planimetría de Colmenar de Oreja, IGN, documento 280075",
            url="https://www.ign.es/wms/minutas-cartograficas?x=1",
            retrieved_at=date(2026, 11, 26),
            license=IGN_HISTORIC_LICENSE,
            redistribution=Redistribution.PUBLIC,
        ),
    )
    fit = fit_affine(exact())
    return GeoreferenceUnit(spec(), image, ControlPointSet(tuple(exact()), "c" * 64), fit)


def test_ca10_conversion_a_trazado_historico() -> None:
    """Dada una `GeoreferenceUnit` de Colmenar (planimetría 280075, 1875-08-06, `day`) y un trazado
    aprobado de 3 vértices, cuando se llama a `to_historic_trail`, entonces el resultado es
    `approved`, con `identifier = "280075-w1-T001"`, vértices iguales a
    `round_mm(transform.apply(...))`, `georeferencing_error_m = loo_rmse_m`,
    `provenance.license = "CC-BY 4.0 © Instituto Geográfico Nacional de España"` y
    `derived_work_attribution` = `Obra derivada de Planimetría de Colmenar de Oreja, IGN, documento
    280075 1875 CC-BY 4.0 © Instituto Geográfico Nacional de España`. Con un trazado `proposed`,
    `ValueError`."""
    unit = _unit()
    approved = trail()
    result = to_historic_trail(unit, approved)
    assert result.status == "approved"
    assert result.identifier == "280075-w1-T001"
    assert result.geometry.points == tuple(
        round_mm(unit.fit.transform.apply(c, r)) for c, r in approved.pixels
    )
    assert result.georeferencing_error_m == unit.fit.loo_rmse_m
    assert result.provenance.license == "CC-BY 4.0 © Instituto Geográfico Nacional de España"
    assert derived_work_attribution(result) == (
        "Obra derivada de Planimetría de Colmenar de Oreja, IGN, documento 280075 "
        "1875 CC-BY 4.0 © Instituto Geográfico Nacional de España"
    )
    proposed = trail(
        status="proposed", reviewed_by=None, reviewed_at=None, control_points_sha256=None
    )
    with pytest.raises(ValueError):
        to_historic_trail(unit, proposed)


@pytest.mark.parametrize(
    "overrides",
    [
        {"unit_id": "999999-w1"},
        {"provenance_source": "Colmenar de Oreja"},
        {"provenance_source": "Planimetría de Colmenar de Oreja, IGN, documento 111111"},
        {"georeferenced_at": datetime(2026, 11, 26, 12, 0)},
        {"georeferenced_by": "no es un usuario"},
    ],
)
def test_ca11_unit_spec_invalido(overrides: dict[str, object]) -> None:
    """Dado un `UnitSpec` cuyo `unit_id` no empieza por `document_id`, con `provenance_source` que
    no sigue el patrón de su tipo, `georeferenced_at` sin zona o `georeferenced_by` que no es un
    usuario de GitHub válido, cuando se construye, entonces lanza `ValueError` con el campo."""
    campo = next(iter(overrides))
    expected = "document_id" if campo == "unit_id" else campo
    with pytest.raises(ValueError, match=expected):
        spec(**overrides)


def test_ca12_adr_de_la_historia_20() -> None:
    """Dado el repositorio, cuando se buscan en `docs/adr/` el ADR de #20 y el de #18, entonces el
    de #20 existe con las secciones Contexto, Decisión, Alternativas descartadas y Consecuencias, y
    cita el ADR 0043. Además, `uv run lint-imports`, `uv run mypy`, `uv run ruff check .` y
    `uv run pytest` están en verde."""
    adrs = {p: p.read_text(encoding="utf-8") for p in (ROOT / "docs" / "adr").glob("*.md")}
    by_story = {
        p: t for p, t in adrs.items() if re.search(r"^- Historias: #20\b", t, flags=re.MULTILINE)
    }
    assert len(by_story) == 1
    path, text = next(iter(by_story.items()))
    assert re.fullmatch(r"\d{4}-.*\.md", path.name)
    for section in (
        "## Contexto",
        "## Decisión",
        "## Alternativas descartadas",
        "## Consecuencias",
    ):
        assert section in text
    assert "ADR 0043" in text
    adr_18 = [p for p, t in adrs.items() if re.search(r"^- Historias: #18 ", t, flags=re.MULTILINE)]
    assert [p.name for p in adr_18] == [
        "0043-georreferenciacion-y-digitalizacion-con-revision-humana.md"
    ]
    numbers = [p.name[:4] for p in adrs]
    assert len(numbers) == len(set(numbers)), "números de ADR duplicados"
