import pytest

from parcel_intel.domain.comparison_image import (
    attribution_for,
    comparison_windows,
    stretch_pixels,
)
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.orthophoto import OrthophotoWindow


def test_attribution_for_prefija_obra_derivada() -> None:
    assert attribution_for(2011) == "Obra derivada de PNOA 2011 CC-BY 4.0 scne.es"


def test_parte_degenerada_se_ignora_si_hay_otra_medible() -> None:
    stretch = MultiLineGeometry(
        lines=(((0.0, 0.0), (0.0, 0.0)), ((10.0, 10.0), (60.0, 10.0))), srid=25830
    )
    windows = comparison_windows(stretch)
    assert windows is not None and len(windows) == 1
    assert len(stretch_pixels(stretch, windows[0])) == 1


def test_tramo_en_diagonal_larga_es_demasiado_largo() -> None:
    stretch = MultiLineGeometry(lines=(((0.0, 0.0), (2100.0, 2100.0)),), srid=25830)
    assert comparison_windows(stretch) is None


@pytest.mark.parametrize(
    "args",
    [(0, 0, 0, 10, 25830, 1, 1), (0, 0, 10, 10, 4326, 1, 1), (0, 0, 10, 10, 25830, 0, 1)],
)
def test_ventana_invalida(args: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        OrthophotoWindow(*args)
