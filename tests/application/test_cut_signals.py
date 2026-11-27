"""Tests unitarios de `CadastralParcelSignalProvider` (historia #127)."""

import pytest

from parcel_intel.application.cut_signals import (
    CadastralParcelSignalProvider,
    footprint_kind,
    to_footprint,
)
from parcel_intel.domain.discrepancy import TrailRef, trail_samples
from parcel_intel.ports.errors import CadastralServiceError
from tests.cut_signal_support import (
    INFRASTRUCTURE_HG,
    INFRASTRUCTURE_VT,
    ORDINARY,
    UNREADABLE,
    URBAN,
    Boundaries,
    ParcelsPort,
    line,
    parcel,
    rect,
    source,
)

SUBJECT = TrailRef("VP-1", source("via_pecuaria_oficial"))


def _provider(
    port: ParcelsPort, bbox: tuple[float, float, float, float]
) -> CadastralParcelSignalProvider:
    return CadastralParcelSignalProvider(lambda _code: port, Boundaries(bbox), 900.0)


@pytest.mark.parametrize(
    ("reference", "kind"),
    [
        (ORDINARY, "ordinaria"),
        (INFRASTRUCTURE_VT, "infraestructura"),
        (INFRASTRUCTURE_HG, "infraestructura"),
        (URBAN, "otra"),
        (UNREADABLE, "otra"),
    ],
)
def test_clasificacion_de_la_huella(reference: str, kind: str) -> None:
    assert footprint_kind(parcel(reference, rect(0, 0, 1, 1))) == kind
    assert to_footprint(parcel(reference, rect(0, 0, 1, 1))).kind == kind


def test_aplica_a_vias_planimetrias_y_mtn50_pero_no_a_catastro() -> None:
    provider = _provider(ParcelsPort([]), (0, 0, 10, 10))
    assert not provider.applies_to("catastro_vt")
    for kind in ("via_pecuaria_oficial", "planimetria_historica", "mtn50_historico"):
        assert provider.applies_to(kind)


def test_pide_las_teselas_de_la_zona_una_sola_vez() -> None:
    port = ParcelsPort([])
    provider = _provider(port, (0, 0, 2700, 900))
    zone = line((100.0, 100.0), (1000.0, 100.0))  # cruza dos teselas
    provider.prepare("28043", [zone, zone])
    assert port.requests == [(0.0, 0.0, 900.0, 900.0), (900.0, 0.0, 1800.0, 900.0)]


def test_sin_zonas_no_pide_nada() -> None:
    port = ParcelsPort([])
    provider = _provider(port, (0, 0, 900, 900))
    provider.prepare("28043", [])
    assert port.requests == []
    assert provider.run_summary().status == "ejecutada"


def test_tesela_fallida_deja_sin_dato_solo_sus_muestras() -> None:
    port = ParcelsPort(
        [parcel(ORDINARY, rect(-100, -50, 2000, 50))],
        fail=lambda tile: CadastralServiceError("x") if tile[0] == 900.0 else None,
    )
    provider = _provider(port, (0, -100, 1800, 100))
    zone = line((0.0, 0.0), (1800.0, 0.0))
    provider.prepare("28043", [zone])
    samples = trail_samples(zone)
    reading = provider.read("28043", SUBJECT, samples)
    assert reading.verdicts[0] == "apoya"
    assert reading.verdicts[-1] == "sin_dato"
    summary = provider.run_summary()
    assert summary.status == "ejecutada" and summary.reason is None


def test_todas_las_teselas_fallidas_es_sin_datos() -> None:
    port = ParcelsPort([], fail=lambda _t: CadastralServiceError("caído"))
    provider = _provider(port, (0, 0, 900, 900))
    zone = line((100.0, 100.0), (200.0, 100.0))
    provider.prepare("28043", [zone])
    summary = provider.run_summary()
    assert summary.status == "sin_datos" and summary.reason and "caído" in summary.reason
    assert set(provider.read("28043", SUBJECT, trail_samples(zone)).verdicts) == {"sin_dato"}


def test_otro_error_se_propaga() -> None:
    port = ParcelsPort([], fail=lambda _t: RuntimeError("bug"))
    provider = _provider(port, (0, 0, 900, 900))
    with pytest.raises(RuntimeError):
        provider.prepare("28043", [line((100.0, 100.0), (200.0, 100.0))])


def test_deduplica_parcelas_entre_teselas_y_recoge_procedencia() -> None:
    port = ParcelsPort([parcel(ORDINARY, rect(800, -50, 1000, 50))])
    provider = _provider(port, (0, -100, 1800, 100))
    zone = line((0.0, 0.0), (1800.0, 0.0))
    provider.prepare("28043", [zone])
    reading = provider.read("28043", SUBJECT, trail_samples(zone))
    assert len(reading.provenance) == 1
    assert reading.provenance == provider.run_summary().provenance
