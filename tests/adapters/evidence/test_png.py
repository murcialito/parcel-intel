import struct
import zlib

import numpy as np
import pytest

from parcel_intel.adapters.evidence.png import decode_png, encode_png_rgb
from parcel_intel.ports.errors import EvidenceImageFormatError
from tests.adapters.evidence.helpers import (
    CHANNELS,
    PNOA_FIXTURE,
    RECORTE,
    SIGNATURE,
    chunk,
    make_png,
)

WIDTH, HEIGHT = 7, 6
PALETTE = [(10 * i, 255 - 20 * i, (i * 97) % 256) for i in range(12)]


def _samples(color_type: int) -> list[list[int]]:
    """Muestras deterministas con saltos grandes, para que cada filtro importe."""
    channels = CHANNELS[color_type]
    modulus = len(PALETTE) if color_type == 3 else 256
    return [
        [(row * 91 + i * 53 + (i // channels) * 7) % modulus for i in range(WIDTH * channels)]
        for row in range(HEIGHT)
    ]


def _expected(color_type: int, rows: list[list[int]]) -> np.ndarray:
    channels = CHANNELS[color_type]
    out = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    for y, line in enumerate(rows):
        for x in range(WIDTH):
            pixel = line[x * channels : (x + 1) * channels]
            if color_type in (0, 4):
                out[y, x] = (pixel[0],) * 3
            elif color_type in (2, 6):
                out[y, x] = pixel[:3]
            else:
                out[y, x] = PALETTE[pixel[0]]
    return out


@pytest.mark.parametrize("color_type", [0, 2, 3, 4, 6])
@pytest.mark.parametrize("filter_type", [0, 1, 2, 3, 4])
def test_cada_tipo_de_color_con_cada_filtro(color_type: int, filter_type: int) -> None:
    rows = _samples(color_type)
    png = make_png(
        color_type, rows, filters=(filter_type,), palette=PALETTE if color_type == 3 else None
    )
    assert np.array_equal(decode_png(png), _expected(color_type, rows))


def test_filtros_distintos_en_filas_consecutivas() -> None:
    rows = _samples(2)
    png = make_png(2, rows, filters=(1, 4, 3, 2, 0, 4))
    assert np.array_equal(decode_png(png), _expected(2, rows))


def test_varios_bloques_idat_se_concatenan() -> None:
    rows = _samples(2)
    png = make_png(2, rows)
    compressed = zlib.compress(b"".join(b"\x00" + bytes(line) for line in rows))
    half = len(compressed) // 2
    header = png[: png.index(b"IDAT") - 4]
    split = (
        header
        + chunk(b"IDAT", compressed[:half])
        + chunk(b"IDAT", compressed[half:])
        + chunk(b"IEND", b"")
    )
    assert np.array_equal(decode_png(split), _expected(2, rows))


def test_los_dos_png_reales_se_decodifican() -> None:
    planimetria = decode_png(RECORTE.read_bytes())
    pnoa = decode_png(PNOA_FIXTURE.read_bytes())
    assert planimetria.shape == (500, 500, 3)
    assert pnoa.shape == (352, 400, 3)
    assert planimetria.dtype == pnoa.dtype == np.uint8
    # No es una imagen vacía: tiene tonos distintos.
    assert len(np.unique(pnoa.reshape(-1, 3), axis=0)) > 1000


def test_codificar_y_decodificar_de_vuelta_es_exacto() -> None:
    for original in (decode_png(RECORTE.read_bytes()), decode_png(PNOA_FIXTURE.read_bytes())):
        encoded = encode_png_rgb(original)
        assert encoded.startswith(SIGNATURE)
        assert np.array_equal(decode_png(encoded), original)
        assert encode_png_rgb(original) == encoded  # determinista
    header = struct.unpack(">IIBBBBB", encode_png_rgb(original)[16:29])
    assert header == (400, 352, 8, 2, 0, 0, 0)


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(make_png(2, _samples(2), interlace=1), id="entrelazado"),
        pytest.param(make_png(2, _samples(2), bit_depth=16), id="16 bits"),
        pytest.param(make_png(0, _samples(0), bit_depth=4), id="4 bits"),
        pytest.param(b"\xff\xd8\xff\xe0" + b"\x00" * 40 + b"JFIF", id="jpeg"),
        pytest.param(b"", id="vacío"),
        pytest.param(b"<html>502 Bad Gateway</html>", id="html"),
    ],
)
def test_formatos_no_soportados_lanzan_error(bad: bytes) -> None:
    with pytest.raises(EvidenceImageFormatError):
        decode_png(bad)


def test_png_corrupto_lanza_error() -> None:
    good = make_png(2, _samples(2))
    with pytest.raises(EvidenceImageFormatError, match="CRC"):
        decode_png(good[:-20] + b"\x00" + good[-19:])
    with pytest.raises(EvidenceImageFormatError):
        decode_png(good[:30])  # truncado
    broken = SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
    broken += chunk(b"IDAT", b"no es zlib") + chunk(b"IEND", b"")
    with pytest.raises(EvidenceImageFormatError, match="zlib"):
        decode_png(broken)
    short = SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
    short += chunk(b"IDAT", zlib.compress(b"\x00" * 3)) + chunk(b"IEND", b"")
    with pytest.raises(EvidenceImageFormatError):
        decode_png(short)


def test_paleta_ausente_o_indice_fuera_de_la_tabla() -> None:
    rows = [[0, 1, 2]]
    with pytest.raises(EvidenceImageFormatError, match="PLTE"):
        decode_png(make_png(3, rows))
    with pytest.raises(EvidenceImageFormatError, match="paleta"):
        decode_png(make_png(3, [[0, 1, 5]], palette=PALETTE[:2]))


def test_filtro_desconocido_y_tipo_de_color_desconocido() -> None:
    bad_filter = SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    bad_filter += chunk(b"IDAT", zlib.compress(b"\x09\x01\x02\x03")) + chunk(b"IEND", b"")
    with pytest.raises(EvidenceImageFormatError, match="filtro"):
        decode_png(bad_filter)
    bad_color = SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 5, 0, 0, 0))
    bad_color += chunk(b"IEND", b"")
    with pytest.raises(EvidenceImageFormatError, match="tipo de color"):
        decode_png(bad_color)


def test_el_codificador_rechaza_matrices_invalidas() -> None:
    with pytest.raises(ValueError):
        encode_png_rgb(np.zeros((2, 2), dtype=np.uint8))
    with pytest.raises(ValueError):
        encode_png_rgb(np.zeros((2, 2, 3), dtype=np.int32))
    with pytest.raises(ValueError):
        encode_png_rgb(np.zeros((0, 2, 3), dtype=np.uint8))
