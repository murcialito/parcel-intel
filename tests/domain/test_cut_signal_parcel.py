"""Tests unitarios de la señal `parcela_no_camino` (historia #127)."""

import dataclasses
import math

import pytest

from parcel_intel.domain.cut_method import SIGNAL_WEIGHTS
from parcel_intel.domain.cut_signal_parcel import (
    PARCEL_SIGNAL,
    ParcelFootprint,
    index_footprints,
    parcel_verdict,
    read_parcel_signal,
)
from parcel_intel.domain.discrepancy import trail_samples
from parcel_intel.domain.geometry import Geometry
from tests.cut_signal_support import line, rect

MARGIN = math.hypot(10, 5)


def _samples(length: float = 200.0):  # type: ignore[no-untyped-def]
    return trail_samples(line((0.0, 0.0), (length, 0.0)))


def test_ejemplo_trabajado_40_veredictos_16_apoyan() -> None:
    samples = _samples()
    index = index_footprints([ParcelFootprint(rect(50, -50, 150, 50), "ordinaria")])
    reading = read_parcel_signal(samples, index, MARGIN, [False] * 40)
    assert len(reading.verdicts) == 40
    assert [i for i, v in enumerate(reading.verdicts) if v == "apoya"] == list(range(12, 28))
    assert reading.signal == PARCEL_SIGNAL
    assert reading.evidence[0].name == "margen_borde_parcela_m"
    assert reading.evidence[0].value == round(MARGIN, 3)


def test_el_peso_de_la_senal_esta_en_la_tabla() -> None:
    assert SIGNAL_WEIGHTS[PARCEL_SIGNAL.identifier] == 0.6


@pytest.mark.parametrize(
    ("x", "expected"),
    [(59.0, "no_apoya"), (59.99, "no_apoya"), (60.0, "apoya"), (60.5, "apoya")],
)
def test_margen_exacto_apoya_y_menos_no(x: float, expected: str) -> None:
    footprint = ParcelFootprint(rect(50, -50, 150, 50), "ordinaria")
    assert parcel_verdict((x, 0.0), [footprint], 10.0) == expected


def test_infraestructura_anula_el_apoyo_de_la_ordinaria() -> None:
    ordinary = ParcelFootprint(rect(0, -50, 200, 50), "ordinaria")
    enclave = ParcelFootprint(rect(90, -5, 110, 5), "infraestructura")
    assert parcel_verdict((100.0, 0.0), [ordinary, enclave], 10.0) == "no_apoya"
    assert parcel_verdict((50.0, 0.0), [ordinary, enclave], 10.0) == "apoya"


def test_fuera_de_toda_huella_o_en_otra_no_apoya() -> None:
    other = ParcelFootprint(rect(0, -50, 200, 50), "otra")
    assert parcel_verdict((100.0, 0.0), [other], 10.0) == "no_apoya"
    assert parcel_verdict((100.0, 0.0), [], 10.0) == "no_apoya"


def test_huella_multiparte_mira_el_anillo_que_contiene_la_muestra() -> None:
    two = Geometry(
        rings=(
            ((0.0, 0.0), (50.0, 0.0), (50.0, 50.0), (0.0, 50.0), (0.0, 0.0)),
            ((100.0, 0.0), (200.0, 0.0), (200.0, 50.0), (100.0, 50.0), (100.0, 0.0)),
        ),
        srid=25830,
    )
    footprint = ParcelFootprint(two, "ordinaria")
    assert parcel_verdict((150.0, 25.0), [footprint], 10.0) == "apoya"
    assert parcel_verdict((25.0, 25.0), [footprint], 10.0) == "apoya"
    assert parcel_verdict((75.0, 25.0), [footprint], 10.0) == "no_apoya"


def test_sin_dato_donde_falta_la_tesela_y_el_resto_se_evalua() -> None:
    samples = _samples()
    index = index_footprints([ParcelFootprint(rect(50, -50, 150, 50), "ordinaria")])
    no_data = [i < 10 for i in range(40)]
    reading = read_parcel_signal(samples, index, MARGIN, no_data)
    assert set(reading.verdicts[:10]) == {"sin_dato"}
    assert [i for i, v in enumerate(reading.verdicts) if v == "apoya"] == list(range(12, 28))


def test_no_data_de_otra_longitud_lanza_error() -> None:
    with pytest.raises(ValueError, match="marcas"):
        read_parcel_signal(_samples(), index_footprints([]), MARGIN, [False])


def test_huella_sin_anillos_validos_no_rompe() -> None:
    empty = ParcelFootprint(Geometry(rings=(), srid=25830), "ordinaria")
    index = index_footprints([empty])
    reading = read_parcel_signal(_samples(10.0), index, MARGIN, [False] * 2)
    assert reading.verdicts == ("no_apoya", "no_apoya")


def test_la_huella_no_tiene_campo_de_referencia() -> None:
    assert [f.name for f in dataclasses.fields(ParcelFootprint)] == ["geometry", "kind"]
