"""Tests unitarios de `domain/historic_coverage.py` (historia #240). Fixtures SINTÉTICAS."""

import dataclasses
from datetime import date, datetime

import pytest

from parcel_intel.domain.geometry import Geometry, MultiLineGeometry
from parcel_intel.domain.historic_coverage import (
    HISTORIC_SOURCE_KIND,
    HistoricUnitCoverage,
    historic_trail_shape,
)
from tests.convergence_support import coverage, historic_trail, p, strip, unit

SQUARE = strip(0, 0, 100, 100)


def test_fuente_de_cada_tipo_de_documento() -> None:
    assert dict(HISTORIC_SOURCE_KIND) == {
        "planimetria": "planimetria_historica",
        "mtn50": "mtn50_historico",
    }


def test_unidad_valida() -> None:
    built = unit("280075-w1", SQUARE)
    assert built.footprint == SQUARE


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"unit_id": "280075"}, "unit_id"),
        ({"document_kind": "catastron"}, "document_kind"),
        ({"document_date": datetime(1875, 1, 1)}, "document_date"),
        ({"retrieved_at": "2026-11-20"}, "retrieved_at"),
        ({"footprint": MultiLineGeometry(lines=(), srid=25830)}, "Geometry"),
        ({"footprint": Geometry(rings=SQUARE.rings, srid=4326)}, "EPSG"),
        ({"footprint": Geometry(rings=SQUARE.rings * 2, srid=25830)}, "un anillo"),
        ({"footprint": Geometry(rings=((p(0, 0), p(1, 1), p(0, 0)),), srid=25830)}, "3"),
        (
            {"footprint": Geometry(rings=((p(0, 0), p(1, 0), (float("nan"), 0.0)),), srid=25830)},
            "finita",
        ),
    ],
)
def test_unidad_invalida(changes: dict[str, object], fragment: str) -> None:
    with pytest.raises(ValueError, match=fragment):
        dataclasses.replace(unit("280075-w1", SQUARE), **changes)  # type: ignore[arg-type]


def test_cobertura_vacia_es_valida() -> None:
    empty = coverage("mtn50")
    assert empty.units == () and empty.trails == ()


def test_cobertura_con_unidades_y_aprobados() -> None:
    units = [unit("280075-w1", SQUARE), unit("280246-w1", strip(500, 0, 600, 100))]
    trails = [
        historic_trail("280075-w1-T001", [(0, 0), (10, 0)]),
        historic_trail("280246-w1-T001", [(500, 0), (510, 0)]),
    ]
    built = coverage("planimetria", units, trails)
    assert len(built.units) == 2 and len(built.trails) == 2


@pytest.mark.parametrize("status", ["proposed", "rejected"])
def test_rechaza_trazados_no_aprobados(status: str) -> None:
    trail = historic_trail("280075-w1-T001", [(0, 0), (10, 0)], status=status)
    with pytest.raises(ValueError, match="aprobado"):
        coverage("planimetria", [unit("280075-w1", SQUARE)], [trail])


def test_rechaza_tipos_mezclados() -> None:
    mtn = unit("0606-w1", SQUARE, document_kind="mtn50")
    with pytest.raises(ValueError, match="no es de planimetria"):
        coverage("planimetria", [mtn])
    trail = historic_trail("280075-w1-T001", [(0, 0), (10, 0)], document_kind="mtn50")
    with pytest.raises(ValueError, match="no es de planimetria"):
        coverage("planimetria", [unit("280075-w1", SQUARE)], [trail])


def test_rechaza_repetidos_y_desordenados() -> None:
    a, b = unit("280075-w1", SQUARE), unit("280246-w1", SQUARE)
    with pytest.raises(ValueError, match="repetidos"):
        coverage("planimetria", [a, a])
    with pytest.raises(ValueError, match="ordenada"):
        coverage("planimetria", [b, a])
    t1 = historic_trail("280075-w1-T001", [(0, 0), (10, 0)])
    t2 = historic_trail("280075-w1-T002", [(0, 0), (10, 0)])
    with pytest.raises(ValueError, match="repetidos"):
        coverage("planimetria", [a], [t1, t1])
    with pytest.raises(ValueError, match="ordenada"):
        coverage("planimetria", [a], [t2, t1])


def test_rechaza_trazados_sin_unidad() -> None:
    trail = historic_trail("280075-w2-T001", [(0, 0), (10, 0)])
    with pytest.raises(ValueError, match="ninguna unidad"):
        coverage("planimetria", [unit("280075-w1", SQUARE)], [trail])
    with pytest.raises(ValueError, match="ninguna unidad"):
        coverage("planimetria", [], [trail])


def test_forma_del_trazado() -> None:
    trail = historic_trail("280075-w1-T001", [(0, 0), (10, 0), (10, 10)])
    shape = historic_trail_shape(trail)
    assert shape == MultiLineGeometry(lines=((p(0, 0), p(10, 0), p(10, 10)),), srid=25830)


def test_retrieved_at_obligatoria() -> None:
    with pytest.raises(ValueError, match="retrieved_at"):
        HistoricUnitCoverage("280075-w1", "planimetria", date(1875, 1, 1), SQUARE, None)  # type: ignore[arg-type]
