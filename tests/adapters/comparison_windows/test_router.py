"""Despacho de ventanas por vuelo (historia #208, ADR 0052). Sin red: ports falsos."""

from datetime import date

import pytest

from parcel_intel.adapters.comparison_windows.router import (
    FlightRoutedWindowAdapter,
    comparison_window_url,
    is_idem_vintage,
)
from parcel_intel.adapters.pnoa import window as pnoa_window
from parcel_intel.domain.orthophoto import HistoricalVintage, Orthophoto, OrthophotoWindow
from parcel_intel.domain.provenance import Provenance

WINDOW = OrthophotoWindow(463638, 4437138, 463862, 4437362, 25830, 448, 448)

# Oráculo calculado a mano en el diseño de la issue #208 (no con `window_url`, lección 0017).
IDEM_1975_URL = (
    "https://idem.comunidad.madrid/srvimagenes2/ogc/wms/visorcartografia2?"
    "bbox=463638%2C4437138%2C463862%2C4437362&crs=EPSG%3A25830&format=image%2Fpng"
    "&height=448&layers=fotosAereasHistoricas_1970-1979_orto-1975-ed50&request=GetMap"
    "&service=WMS&styles=&version=1.3.0&width=448"
)


class _FakePort:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[HistoricalVintage] = []

    def get_orthophoto_window(
        self, window: OrthophotoWindow, vintage: HistoricalVintage
    ) -> Orthophoto:
        self.calls.append(vintage)
        provenance = Provenance(
            source=self.name, url="https://example.invalid/", retrieved_at=date(2026, 11, 28)
        )
        return Orthophoto(b"png", vintage, provenance)


@pytest.mark.parametrize("vintage", ["CM_1956", "CM_1975", "CM_1991"])
def test_los_vuelos_cm_son_de_la_idem(vintage: HistoricalVintage) -> None:
    assert is_idem_vintage(vintage)


@pytest.mark.parametrize("vintage", [2017, "AMS_1956-1957", "SIGPAC", "OLISTAT"])
def test_el_resto_no_es_de_la_idem(vintage: HistoricalVintage) -> None:
    assert not is_idem_vintage(vintage)


def test_url_canonica_de_la_idem_es_el_literal_del_oraculo() -> None:
    assert comparison_window_url(WINDOW, "CM_1975") == IDEM_1975_URL
    assert comparison_window_url(WINDOW, "CM_1991") == IDEM_1975_URL.replace(
        "fotosAereasHistoricas_1970-1979_orto-1975-ed50",
        "fotosAereasHistoricas_1990-1999_orto-1991-ed50",
    )


def test_url_canonica_del_ign_es_la_del_adapter_del_ign() -> None:
    assert comparison_window_url(WINDOW, 2017) == pnoa_window.window_url(WINDOW, 2017)
    assert not comparison_window_url(WINDOW, 2017).startswith("https://idem.")


def test_despacha_cada_vuelo_a_su_adapter() -> None:
    ign, idem = _FakePort("ign"), _FakePort("idem")
    router = FlightRoutedWindowAdapter(ign=ign, idem=idem)
    vintages: tuple[HistoricalVintage, ...] = (
        "CM_1975",
        2017,
        "CM_1991",
        "SIGPAC",
        "AMS_1956-1957",
    )
    for vintage in vintages:
        router.get_orthophoto_window(WINDOW, vintage)
    assert idem.calls == ["CM_1975", "CM_1991"]
    assert ign.calls == [2017, "SIGPAC", "AMS_1956-1957"]


def test_un_vuelo_desconocido_va_al_ign() -> None:
    ign, idem = _FakePort("ign"), _FakePort("idem")
    image = FlightRoutedWindowAdapter(ign=ign, idem=idem).get_orthophoto_window(
        WINDOW,
        "Nacional_1981-1986",
    )
    assert image.provenance.source == "ign" and idem.calls == []
