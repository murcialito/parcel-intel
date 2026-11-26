import dataclasses
from datetime import UTC, date, datetime
from typing import Any

import pytest

from parcel_intel.domain.geometry import LineGeometry
from parcel_intel.domain.historic_trail import (
    HistoricTrail,
    HistoricTrailAlreadyReviewedError,
    InvalidHistoricTrailError,
    approve,
    derived_work_attribution,
    reject,
)
from tests.factories import make_synthetic_historic_trail

_AT = datetime(2026, 11, 26, 10, 0, tzinfo=UTC)


def _build(**overrides: Any) -> HistoricTrail:
    trail = make_synthetic_historic_trail()
    kwargs = {field.name: getattr(trail, field.name) for field in dataclasses.fields(trail)}
    kwargs.update(overrides)
    return HistoricTrail(**kwargs)


def test_dos_puntos_distintos_bastan() -> None:
    trail = _build(geometry=LineGeometry(points=((0.0, 0.0), (1.0, 0.0)), srid=25830))
    assert len(trail.geometry.points) == 2


def test_puntos_repetidos_no_consecutivos_cuentan_como_distintos_si_hay_dos() -> None:
    points = ((0.0, 0.0), (1.0, 0.0), (0.0, 0.0))
    assert _build(geometry=LineGeometry(points=points, srid=25830)).geometry.points == points


def test_error_cero_es_valido() -> None:
    assert _build(georeferencing_error_m=0.0).georeferencing_error_m == 0.0


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"identifier": "   "}, "identifier"),
        ({"document_id": ""}, "document_id"),
        ({"municipality_code": "280430"}, "municipality_code"),
        ({"document_kind": "catastro"}, "document_kind"),
        ({"document_date": datetime(1875, 8, 6, tzinfo=UTC)}, "document_date"),
        ({"document_date_precision": "month"}, "document_date_precision"),
        ({"georeferencing_error_m": True}, "georeferencing_error_m"),
        ({"status": "pending"}, "status"),
        ({"status": "approved", "reviewer": " ", "reviewed_at": _AT}, "reviewer"),
    ],
)
def test_el_mensaje_nombra_el_campo(overrides: dict[str, Any], field: str) -> None:
    with pytest.raises(InvalidHistoricTrailError, match=field):
        _build(**overrides)


def test_approve_con_revisor_vacio_se_rechaza() -> None:
    with pytest.raises(InvalidHistoricTrailError, match="reviewer"):
        approve(make_synthetic_historic_trail(), "", _AT)


def test_reject_no_modifica_el_original() -> None:
    trail = make_synthetic_historic_trail()
    rejected = reject(trail, "revisora", _AT)
    assert rejected.status == "rejected"
    assert trail == make_synthetic_historic_trail()


def test_error_ya_revisado_lleva_identificador_y_estado() -> None:
    approved = approve(make_synthetic_historic_trail(), "revisora", _AT)
    with pytest.raises(HistoricTrailAlreadyReviewedError) as excinfo:
        reject(approved, "revisora", _AT)
    assert (excinfo.value.identifier, excinfo.value.status) == ("280075-001", "approved")


def test_atribucion_usa_solo_el_anio_con_fecha_generica_de_serie() -> None:
    trail = _build(document_date=date(1870, 1, 1), document_date_precision="year")
    assert derived_work_attribution(trail).endswith(" 1870 CC BY 4.0 ign.es")
