"""Tests unitarios de `domain/georeferencing.py` (historia #136)."""

import math
from collections.abc import Sequence
from datetime import UTC, date, datetime

import pytest

from parcel_intel.domain.georeferencing import (
    IGN_HISTORIC_LICENSE,
    AffineTransform,
    ControlPoint,
    ControlPointSet,
    GeoreferenceFit,
    GeoreferenceRejectedError,
    InsufficientControlPointsError,
    InvalidControlPointError,
    UnitSpec,
    Verdict,
    WorkingImage,
    check_acceptable,
    check_points_in_image,
    fit_affine,
    pixel_hull_contains,
    round_mm,
    thresholds_m,
    unit_footprint,
)
from parcel_intel.domain.provenance import Provenance, Redistribution

PIXELS = [(100, 100), (900, 150), (500, 400), (150, 700), (850, 650), (300, 300), (700, 500)]


def truth(col: float, row: float) -> tuple[float, float]:
    return 455000 + 2.5 * col + 0.10 * row, 4445000 + 0.12 * col - 2.5 * row


def point(
    n: int,
    col: float,
    row: float,
    target: tuple[float, float] | None = None,
    retained: bool = True,
) -> ControlPoint:
    return ControlPoint(
        point_id=f"P{n:02d}",
        col=col,
        row=row,
        target=target if target is not None else truth(col, row),
        coordinate_source="PNOA 1:1.000",
        description="esquina de la iglesia",
        retained=retained,
        discard_reason=None if retained else "no se reconoce",
    )


def exact_points(pixels: Sequence[tuple[float, float]] = PIXELS) -> list[ControlPoint]:
    return [point(i + 1, c, r) for i, (c, r) in enumerate(pixels)]


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
        "georeferenced_at": datetime(2026, 11, 26, 10, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return UnitSpec(**values)  # type: ignore[arg-type]


def test_afin_exacta_se_recupera_sin_error() -> None:
    fit = fit_affine(exact_points())
    t = fit.transform
    for got, want in zip(
        (t.a, t.b, t.c, t.d, t.e, t.f), (455000, 2.5, 0.10, 4445000, 0.12, -2.5), strict=True
    ):
        assert got == pytest.approx(want, abs=1e-6)
    assert fit.n_retained == 7
    assert fit.rmse_m < 1e-6 and fit.max_residual_m < 1e-6 and fit.loo_rmse_m < 1e-6


def test_descartados_se_ajustan_sin_ellos_y_llevan_residuo_sin_loo() -> None:
    points = exact_points() + [point(8, 400, 400, target=(456000.0, 4444000.0), retained=False)]
    fit = fit_affine(points)
    assert fit.n_retained == 7 and fit.rmse_m < 1e-6
    last = fit.residuals[-1]
    assert last.point_id == "P08" and last.loo_residual_m is None and last.residual_m > 50
    assert all(r.loo_residual_m is not None for r in fit.residuals[:-1])


def test_afin_con_rotacion_y_escala_distinta_por_eje() -> None:
    def other(col: float, row: float) -> tuple[float, float]:
        return 400000 + 1.9 * col - 0.8 * row, 4400000 + 0.8 * col + 1.9 * row

    fit = fit_affine([point(i + 1, c, r, other(c, r)) for i, (c, r) in enumerate(PIXELS)])
    assert fit.transform.b == pytest.approx(1.9, abs=1e-6)
    assert fit.transform.c == pytest.approx(-0.8, abs=1e-6)
    assert fit.rmse_m < 1e-6


def test_menos_de_seis_retenidos() -> None:
    with pytest.raises(InsufficientControlPointsError, match="menos de 6"):
        fit_affine(exact_points(PIXELS[:5]))


def test_los_descartados_no_cuentan_para_el_minimo() -> None:
    points = exact_points(PIXELS[:5]) + [point(6, 400, 400, retained=False)]
    with pytest.raises(InsufficientControlPointsError, match="menos de 6"):
        fit_affine(points)


def test_seis_colineales() -> None:
    line = [(100.0 * i, 50.0 * i) for i in range(1, 7)]
    with pytest.raises(InsufficientControlPointsError, match="colineales"):
        fit_affine(exact_points(line))


def test_seis_con_dos_posiciones_repetidas() -> None:
    repeated = [(100, 100), (100, 100), (100, 100), (800, 600), (800, 600), (800, 600)]
    with pytest.raises(InsufficientControlPointsError, match="repetidos"):
        fit_affine(exact_points(repeated))


def test_loo_indeterminada_si_quitar_uno_deja_cinco_colineales() -> None:
    pixels = [(100.0 * i, 50.0 * i) for i in range(1, 6)] + [(300.0, 700.0)]
    with pytest.raises(InsufficientControlPointsError, match="LOO indeterminada sin P06"):
        fit_affine(exact_points(pixels))


def test_el_criterio_de_degeneracion_no_depende_de_la_escala() -> None:
    # La misma figura colineal a escalas distintas se rechaza igual.
    for factor in (0.01, 1.0, 100.0):
        pixels = [(factor * 100.0 * i, factor * 50.0 * i) for i in range(1, 7)]
        with pytest.raises(InsufficientControlPointsError):
            fit_affine(exact_points(pixels))


def test_thresholds_m() -> None:
    assert thresholds_m(25000) == (15.0, 35.0)
    assert thresholds_m(50000) == (30.0, 70.0)


def _fit(loo: float = 1.0, max_residual: float = 1.0) -> GeoreferenceFit:
    return GeoreferenceFit(
        transform=AffineTransform(0, 1, 0, 0, 0, 1),
        n_retained=6,
        rmse_m=1.0,
        max_residual_m=max_residual,
        loo_rmse_m=loo,
        residuals=(),
    )


SPREAD = exact_points([(100, 100), (900, 100), (100, 700), (900, 700), (500, 400), (300, 300)])


def test_aceptable_en_el_umbral_exacto() -> None:
    verdict = check_acceptable(SPREAD, _fit(loo=15.0, max_residual=35.0), spec())
    assert verdict == Verdict(ok=True, reasons=())


def test_loo_por_encima_del_umbral() -> None:
    verdict = check_acceptable(SPREAD, _fit(loo=15.01), spec())
    assert not verdict.ok
    assert verdict.reasons == ("rmse_loo 15.01 m > umbral 15.00 m (1:25000)",)


def test_residuo_maximo_por_encima_del_umbral() -> None:
    verdict = check_acceptable(SPREAD, _fit(max_residual=35.01), spec())
    assert verdict.reasons == ("residuo_max 35.01 m > umbral 35.00 m (1:25000)",)


def test_solo_dos_cuadrantes() -> None:
    two = exact_points([(100, 100), (900, 100), (200, 200), (800, 300), (300, 150), (600, 50)])
    verdict = check_acceptable(two, _fit(), spec())
    assert verdict.reasons == ("cuadrantes ocupados 2 < mínimo 3",)


def test_los_cuadrantes_solo_cuentan_retenidos() -> None:
    north = exact_points([(100, 100), (900, 100), (200, 200), (800, 300), (300, 150), (600, 50)])
    south = [point(20, 100, 700, retained=False), point(21, 900, 700, retained=False)]
    verdict = check_acceptable(north + south, _fit(), spec())
    assert any("cuadrantes ocupados 2" in r for r in verdict.reasons)


def test_tercio_de_descartados() -> None:
    points = [*SPREAD, *(point(20 + i, 400 + i, 500, retained=False) for i in range(3))]
    verdict = check_acceptable(points, _fit(), spec())
    assert verdict.reasons == ("descartados 33.33 % > umbral 25.00 %",)


def test_un_cuarto_exacto_de_descartados_es_aceptable() -> None:
    points = [*SPREAD, point(20, 400, 500, retained=False), point(21, 410, 500, retained=False)]
    assert check_acceptable(points, _fit(), spec()).ok  # 2/8 = 25 % no supera el umbral


def test_acumula_todos_los_motivos() -> None:
    two = exact_points([(100, 100), (900, 100), (200, 200), (800, 300), (300, 150), (600, 50)])
    verdict = check_acceptable(two, _fit(loo=20.0, max_residual=40.0), spec())
    assert len(verdict.reasons) == 3


def test_escala_distinta_cambia_el_umbral_y_el_texto() -> None:
    verdict = check_acceptable(SPREAD, _fit(loo=29.0), spec(scale_denominator=50000))
    assert verdict.ok
    verdict = check_acceptable(SPREAD, _fit(loo=30.5), spec(scale_denominator=50000))
    assert verdict.reasons == ("rmse_loo 30.50 m > umbral 30.00 m (1:50000)",)


def test_rechazo_lleva_el_veredicto() -> None:
    verdict = Verdict(ok=False, reasons=("rmse_loo 20.00 m > umbral 15.00 m (1:25000)",))
    error = GeoreferenceRejectedError("280075-w1", verdict)
    assert error.verdict is verdict and "280075-w1" in str(error) and "rmse_loo" in str(error)


@pytest.mark.parametrize(
    "overrides",
    [
        {"row": -1.0},
        {"col": -0.5},
        {"col": math.inf},
        {"row": math.nan},
        {"coordinate_source": "Catastro"},
        {"coordinate_source": "catastro"},
        {"coordinate_source": "CATASTRO"},
        {"coordinate_source": "Dirección General del CATASTRO"},
        {"coordinate_source": "  "},
        {"retained": False, "discard_reason": None},
        {"retained": False, "discard_reason": " "},
        {"retained": True, "discard_reason": "porque sí"},
        {"target": (-3.4, 40.1)},
        {"target": (455000.0, 4445000.0, 0.0)},
        {"target": (4445000.0, 455000.0)},
        {"point_id": "P1"},
        {"point_id": "p01"},
        {"point_id": "P1000"},
        {"description": ""},
    ],
)
def test_control_point_invalido(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "point_id": "P01",
        "col": 10.0,
        "row": 10.0,
        "target": (455000.0, 4445000.0),
        "coordinate_source": "PNOA",
        "description": "cruce",
        "retained": True,
        "discard_reason": None,
    }
    values.update(overrides)
    with pytest.raises(InvalidControlPointError):
        ControlPoint(**values)  # type: ignore[arg-type]


def test_control_point_set_rechaza_ids_repetidos_y_sha_malo() -> None:
    p = point(1, 10, 10)
    with pytest.raises(InvalidControlPointError, match="repetido"):
        ControlPointSet((p, p), "a" * 64)
    with pytest.raises(InvalidControlPointError, match="sha256"):
        ControlPointSet((p,), "xyz")
    assert ControlPointSet((p,), "a" * 64).sha256 == "a" * 64


def test_check_points_in_image() -> None:
    check_points_in_image([point(1, 1000, 800)], 1000, 800)  # el borde vale
    with pytest.raises(InvalidControlPointError, match="P01"):
        check_points_in_image([point(1, 1000.5, 10)], 1000, 800)
    with pytest.raises(InvalidControlPointError):
        check_points_in_image([point(1, 10, 801)], 1000, 800)


SQUARE = [point(1, 0, 0), point(2, 100, 0), point(3, 100, 100), point(4, 0, 100)]


@pytest.mark.parametrize(
    ("col", "row", "expected"),
    [
        (50, 50, True),
        (50, 0, True),  # sobre una arista
        (0, 0, True),  # vértice
        (100, 100, True),
        (100.01, 50, False),  # 0,01 px fuera
        (50, -0.01, False),
        (-0.01, -0.01, False),
        (500, 500, False),
    ],
)
def test_pixel_hull_contains(col: float, row: float, expected: bool) -> None:
    assert pixel_hull_contains(SQUARE, col, row) is expected


def test_envolvente_con_tres_colineales_en_un_lado() -> None:
    points = [
        point(1, 0, 0),
        point(2, 50, 0),
        point(3, 100, 0),
        point(4, 100, 100),
        point(5, 0, 100),
    ]
    assert pixel_hull_contains(points, 25, 0)
    assert pixel_hull_contains(points, 50, 0)
    assert pixel_hull_contains(points, 50, 50)
    assert not pixel_hull_contains(points, 50, -0.01)
    assert not pixel_hull_contains(points, 100.01, 100)


def test_envolvente_ignora_descartados_y_triangulo_no_cuadrado() -> None:
    points = [
        point(1, 0, 0),
        point(2, 100, 0),
        point(3, 0, 100),
        point(4, 100, 100, retained=False),
    ]
    assert pixel_hull_contains(points, 10, 10)
    assert not pixel_hull_contains(points, 90, 90)  # solo vale con el descartado


def test_envolvente_degenerada_no_contiene_nada() -> None:
    assert not pixel_hull_contains([point(1, 0, 0), point(2, 10, 10)], 5, 5)
    assert not pixel_hull_contains([], 0, 0)


def test_round_mm() -> None:
    assert round_mm((455000.12345, 4445000.9996)) == (455000.123, 4445001.0)


@pytest.mark.parametrize(
    ("overrides", "campo"),
    [
        ({"unit_id": "999999-w1"}, "empezar por document_id"),
        ({"unit_id": "280075-x1"}, "unit_id"),
        (
            {"provenance_source": "Planimetría de Colmenar de Oreja, IGN, documento 280076"},
            "provenance_source",
        ),
        ({"provenance_source": "Colmenar"}, "provenance_source"),
        ({"georeferenced_at": datetime(2026, 11, 26, 10, 0)}, "georeferenced_at"),
        ({"georeferenced_by": "no es usuario"}, "georeferenced_by"),
        ({"georeferenced_by": "-malo"}, "georeferenced_by"),
        ({"scale_denominator": 0}, "scale_denominator"),
        ({"municipality_code": "2804"}, "municipality_code"),
        ({"image_sha256": "A" * 64}, "image_sha256"),
        ({"image_width_px": 0}, "image_width_px"),
        ({"document_kind": "otro"}, "document_kind"),
    ],
)
def test_unit_spec_invalido(overrides: dict[str, object], campo: str) -> None:
    with pytest.raises(ValueError, match=campo):
        spec(**overrides)


def test_unit_spec_mtn50() -> None:
    mtn = spec(
        unit_id="0606-h1",
        document_id="0606",
        document_kind="mtn50",
        provenance_source="Primera edición MTN50, IGN, hoja 0606",
        scale_denominator=50000,
    )
    assert mtn.unit_id == "0606-h1"
    with pytest.raises(ValueError, match="provenance_source"):
        spec(
            unit_id="0606-h1",
            document_id="0606",
            document_kind="mtn50",
            provenance_source="Planimetría de Colmenar de Oreja, IGN, documento 0606",
        )


def test_working_image_valida() -> None:
    provenance = Provenance(
        source="x",
        url="https://www.ign.es/",
        retrieved_at=date(2026, 11, 26),
        license=IGN_HISTORIC_LICENSE,
        redistribution=Redistribution.PUBLIC,
    )
    image = WorkingImage("wms_render", "b" * 64, 10, 10, "image/png", provenance)
    assert image.provenance.license == "CC-BY 4.0 © Instituto Geográfico Nacional de España"
    with pytest.raises(ValueError, match="sha256"):
        WorkingImage("wms_render", "b" * 63, 10, 10, "image/png", provenance)
    with pytest.raises(ValueError, match="format"):
        WorkingImage("wms_render", "b" * 64, 10, 10, "image/gif", provenance)  # type: ignore[arg-type]


# --- unit_footprint (historia #240). ---------------------------------------------------
_IDENTITY_FLIP = AffineTransform(a=450000, b=1, c=0, d=4436000, e=0, f=-1)


def _set(points: Sequence[ControlPoint]) -> ControlPointSet:
    return ControlPointSet(points=tuple(points), sha256="c" * 64)


def test_unit_footprint_oraculo_del_diseno_sin_el_descartado() -> None:
    pixels = [(0, 0), (1000, 0), (1000, 1000), (0, 1000), (500, 500), (250, 750)]
    points = [point(i + 1, c, r) for i, (c, r) in enumerate(pixels)]
    points.append(point(7, 2000, 2000, retained=False))
    footprint = unit_footprint(_set(points), _IDENTITY_FLIP)
    assert footprint.srid == 25830
    assert footprint.rings == (
        ((450000, 4436000), (451000, 4436000), (451000, 4435000), (450000, 4435000)),
    )
    # Con el punto lejano retenido, la envolvente sí crece.
    points[-1] = point(7, 2000, 2000)
    assert (452000, 4434000) in unit_footprint(_set(points), _IDENTITY_FLIP).rings[0]


def test_unit_footprint_con_menos_de_tres_vertices() -> None:
    collinear = [point(i + 1, 100 * i, 100 * i) for i in range(6)]
    with pytest.raises(ValueError, match="3"):
        unit_footprint(_set(collinear), _IDENTITY_FLIP)
    with pytest.raises(ValueError, match="3"):
        unit_footprint(_set([]), _IDENTITY_FLIP)
