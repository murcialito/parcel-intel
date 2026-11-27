from pathlib import Path

import numpy as np
import pytest

from parcel_intel.adapters.evidence.png import encode_png_rgb
from parcel_intel.adapters.idem_vuelos.window import is_blank, layer_name
from parcel_intel.ports.errors import InvalidHistoricalVintageError

FIXTURES = Path(__file__).parents[2] / "fixtures" / "idem_vuelos"


def test_blanco_y_reales_de_las_fixtures() -> None:
    assert is_blank((FIXTURES / "tesela_1956_fuera_cobertura_z18.png").read_bytes())
    for name in (
        "tesela_1956_colmenar_z18.png",
        "tesela_1975_colmenar_z18.png",
        "tesela_1991_colmenar_z18.png",
    ):
        assert not is_blank((FIXTURES / name).read_bytes())


def test_un_solo_nivel_que_no_es_blanco_tambien_cuenta() -> None:
    assert is_blank(encode_png_rgb(np.full((8, 8, 3), 90, dtype=np.uint8)))


def test_imagen_con_contraste_no_es_blanca() -> None:
    pixels = np.zeros((8, 8, 3), dtype=np.uint8)
    pixels[:, 4:] = 200
    assert not is_blank(encode_png_rgb(pixels))


def test_capas_y_vuelo_invalido() -> None:
    assert layer_name("CM_1991") == "fotosAereasHistoricas_1990-1999_orto-1991-ed50"
    with pytest.raises(InvalidHistoricalVintageError):
        layer_name(1991)
