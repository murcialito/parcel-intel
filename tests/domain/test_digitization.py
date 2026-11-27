"""Tests unitarios de `domain/digitization.py` (historia #136)."""

from datetime import UTC, date, datetime

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
    AffineTransform,
    ControlPointSet,
    GeoreferenceFit,
    GeoreferenceUnit,
    UnitSpec,
    WorkingImage,
)
from parcel_intel.domain.historic_trail import (
    InvalidHistoricTrailError,
    derived_work_attribution,
)
from parcel_intel.domain.provenance import Provenance, Redistribution

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
SHA = "c" * 64


def trail(**overrides: object) -> DigitizedTrail:
    values: dict[str, object] = {
        "trail_id": "T001",
        "pixels": ((10.0, 20.0), (30.5, 40.25), (50.0, 60.0)),
        "kind": "camino",
        "label": "Camino de Chinchón",
        "status": "approved",
        "reviewed_by": "murcialito",
        "reviewed_at": NOW,
        "review_note": None,
        "control_points_sha256": SHA,
    }
    values.update(overrides)
    return DigitizedTrail(**values)  # type: ignore[arg-type]


def unit(transform: AffineTransform | None = None) -> GeoreferenceUnit:
    spec = UnitSpec(
        unit_id="280075-w1",
        document_id="280075",
        document_kind="planimetria",
        municipality_code="28043",
        document_date=date(1875, 8, 6),
        document_date_precision="day",
        scale_denominator=25000,
        image_kind="wms_render",
        image_url="https://www.ign.es/wms/minutas-cartograficas?x=1",
        image_sha256="a" * 64,
        image_width_px=1000,
        image_height_px=800,
        image_retrieved_at=date(2026, 11, 26),
        provenance_source="Planimetría de Colmenar de Oreja, IGN, documento 280075",
        georeferenced_by="murcialito",
        georeferenced_at=NOW,
    )
    image = WorkingImage(
        "wms_render",
        "a" * 64,
        1000,
        800,
        "image/png",
        Provenance(
            source=spec.provenance_source,
            url=spec.image_url,
            retrieved_at=date(2026, 11, 26),
            license=IGN_HISTORIC_LICENSE,
            redistribution=Redistribution.PUBLIC,
        ),
    )
    t = transform or AffineTransform(455000.0, 2.5, 0.10, 4445000.0, 0.12, -2.5)
    fit = GeoreferenceFit(t, 7, 1.0, 2.0, 3.5, ())
    return GeoreferenceUnit(spec, image, ControlPointSet((), SHA), fit)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "desconocido"},
        {"reviewed_by": None},
        {"reviewed_at": None},
        {"control_points_sha256": None},
        {"control_points_sha256": "C" * 64},
        {"reviewed_at": datetime(2026, 11, 26, 12, 0)},
        {"status": "rejected", "review_note": None, "control_points_sha256": None},
        {"status": "rejected", "review_note": "  ", "control_points_sha256": None},
        {"status": "proposed", "control_points_sha256": None},
        {
            "status": "proposed",
            "reviewed_by": None,
            "control_points_sha256": None,
            "reviewed_at": NOW,
        },
        {"pixels": ((1.0, 1.0),)},
        {"pixels": ((1.0, 1.0), (1.0, 1.0))},
        {"pixels": ((1.0, 1.0), (-1.0, 5.0))},
        {"pixels": ((1.0, 1.0), (5.0, -0.1))},
        {"pixels": ((1.0, 1.0), (float("nan"), 5.0))},
        {"pixels": ((1.0, 1.0), (5.0, float("inf")))},
        {"trail_id": "T1"},
        {"trail_id": "t001"},
        {"kind": "autopista"},
        {"label": "x" * 81},
        {"label": ""},
        {"reviewed_by": "usuario con espacios"},
    ],
)
def test_digitized_trail_invalido_nombra_el_trail_id(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidDigitizationError) as info:
        trail(**overrides)
    if overrides.get("trail_id") is None:
        assert "T001" in str(info.value)


def test_digitized_trail_validos() -> None:
    assert trail(label=None).label is None
    assert trail(label="x" * 80).status == "approved"
    proposed = trail(
        status="proposed", reviewed_by=None, reviewed_at=None, control_points_sha256=None
    )
    assert proposed.status == "proposed"
    rejected = trail(status="rejected", review_note="no es un camino", control_points_sha256=None)
    assert rejected.review_note == "no es un camino"
    assert trail(trail_id="T0001").trail_id == "T0001"


def test_check_trails_in_image() -> None:
    check_trails_in_image([trail(pixels=((0.0, 0.0), (1000.0, 800.0)))], 1000, 800)
    with pytest.raises(InvalidDigitizationError, match="T001"):
        check_trails_in_image([trail(pixels=((0.0, 0.0), (10.0, 800.5)))], 1000, 800)
    with pytest.raises(InvalidDigitizationError, match="T002"):
        check_trails_in_image(
            [trail(), trail(trail_id="T002", pixels=((0.0, 0.0), (1000.5, 5.0)))], 1000, 800
        )


def test_check_approvals_current() -> None:
    other = trail(trail_id="T002", control_points_sha256="d" * 64)
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
    check_approvals_current([trail(), proposed, rejected], SHA)
    with pytest.raises(StaleApprovalError) as info:
        check_approvals_current([trail(), other, proposed, rejected], SHA)
    assert info.value.trail_ids == ("T002",)
    assert "T002" in str(info.value)


def test_to_historic_trail() -> None:
    result = to_historic_trail(unit(), trail())
    assert result.identifier == "280075-w1-T001"
    assert result.status == "approved" and result.reviewer == "murcialito"
    assert result.reviewed_at == NOW
    assert result.georeferencing_error_m == 3.5
    assert result.geometry.srid == 25830
    assert result.geometry.points == (
        (455000.0 + 2.5 * 10 + 0.10 * 20, 4445000.0 + 0.12 * 10 - 2.5 * 20),
        (
            round(455000 + 2.5 * 30.5 + 0.10 * 40.25, 3),
            round(4445000 + 0.12 * 30.5 - 2.5 * 40.25, 3),
        ),
        (455000.0 + 2.5 * 50 + 0.10 * 60, 4445000.0 + 0.12 * 50 - 2.5 * 60),
    )
    assert result.municipality_code == "28043" and result.document_id == "280075"
    assert result.document_date == date(1875, 8, 6)
    assert result.provenance.license == IGN_HISTORIC_LICENSE
    assert result.provenance.redistribution is Redistribution.PUBLIC
    assert derived_work_attribution(result) == (
        "Obra derivada de Planimetría de Colmenar de Oreja, IGN, documento 280075 "
        "1875 CC-BY 4.0 © Instituto Geográfico Nacional de España"
    )


def test_to_historic_trail_redondea_al_milimetro_sin_simplificar() -> None:
    odd = unit(AffineTransform(455000.12345, 2.51234, 0.0, 4445000.98765, 0.0, -2.50987))
    pixels = tuple((float(i) * 1.1, float(i) * 0.7 + 3) for i in range(40))
    result = to_historic_trail(odd, trail(pixels=pixels))
    assert len(result.geometry.points) == 40
    assert all(round(c, 3) == c for p in result.geometry.points for c in p)


def test_to_historic_trail_solo_acepta_aprobados() -> None:
    proposed = trail(
        status="proposed", reviewed_by=None, reviewed_at=None, control_points_sha256=None
    )
    rejected = trail(status="rejected", review_note="no", control_points_sha256=None)
    for other in (proposed, rejected):
        with pytest.raises(ValueError, match="approved"):
            to_historic_trail(unit(), other)


def test_to_historic_trail_degenerado_tras_redondear() -> None:
    flat = unit(AffineTransform(455000.0, 0.0001, 0.0, 4445000.0, 0.0, 0.0001))
    with pytest.raises(InvalidHistoricTrailError):
        to_historic_trail(flat, trail(pixels=((10.0, 10.0), (11.0, 11.0))))
