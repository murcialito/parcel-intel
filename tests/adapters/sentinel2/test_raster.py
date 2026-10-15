from pathlib import Path

import numpy as np
import tifffile

from parcel_intel.adapters.sentinel2.raster import open_band, read_pixel_window

# Imagen 48x40 con tiles de 16x16 (el tamaño de tile en TIFF debe ser
# múltiplo de 16): 3x3 tiles, con el último tile de cada columna parcial
# (40/16 = 2.5 -> el tercer tile de filas solo tiene 8 filas reales de 16).
# Valor de cada píxel = row*1000+col, para comprobar que cada celda leída es
# la que corresponde.
_WIDTH, _HEIGHT = 48, 40
_TILE = 16


def _make_synthetic_tiff(path: Path) -> None:
    data = np.fromfunction(
        lambda r, c: r * 1000 + c, (_HEIGHT, _WIDTH), dtype=np.uint16
    ).astype(np.uint16)
    tifffile.imwrite(path, data, tile=(_TILE, _TILE), compression=None)


def _open(path: Path) -> tifffile.TiffFile:
    def ranged_get(url: str, start: int, length: int) -> bytes:
        with open(url, "rb") as f:
            f.seek(start)
            return f.read(length)

    def content_length(url: str) -> int:
        return path.stat().st_size

    return open_band(str(path), ranged_get, content_length)


def test_ventana_dentro_de_un_solo_tile(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.tif"
    _make_synthetic_tiff(path)
    tiff = _open(path)

    window, origin = read_pixel_window(tiff, min_col=0, min_row=0, max_col=1, max_row=1)

    assert origin == (0, 0)
    assert window.tolist() == [[0, 1], [1000, 1001]]


def test_ventana_que_cruza_varios_tiles(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.tif"
    _make_synthetic_tiff(path)
    tiff = _open(path)

    # Columnas 14-17 cruzan el límite entre el tile 0 y el tile 1 (tile=16);
    # filas 14-17 cruzan el mismo límite entre tiles de fila.
    window, origin = read_pixel_window(tiff, min_col=14, min_row=14, max_col=17, max_row=17)

    assert origin == (14, 14)
    expected = [[(14 + r) * 1000 + (14 + c) for c in range(4)] for r in range(4)]
    assert window.tolist() == expected


def test_tile_parcial_del_borde_inferior(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.tif"
    _make_synthetic_tiff(path)
    tiff = _open(path)

    # Fila 39 es la última fila real (altura 40); el tile que la contiene
    # nominalmente llega hasta la fila 47 (fuera de la imagen).
    window, origin = read_pixel_window(tiff, min_col=0, min_row=39, max_col=1, max_row=39)

    assert origin == (0, 39)
    assert window.tolist() == [[39000, 39001]]


def test_ventana_fuera_de_rango_se_acota_y_el_origen_devuelto_coincide(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.tif"
    _make_synthetic_tiff(path)
    tiff = _open(path)

    # Ventana pedida con min_col/min_row negativos y max_col/max_row más allá
    # del borde: reproduce el caso real (celda de salida que reproyecta
    # fuera del raster nativo de la escena) que causaba el bug de
    # desalineación encontrado en revisión.
    window, origin = read_pixel_window(
        tiff, min_col=-5, min_row=-5, max_col=_WIDTH + 5, max_row=_HEIGHT + 5
    )

    # El origen devuelto debe ser el real (acotado a la imagen), no el
    # pedido -- quien llama debe indexar con ESTE origen, no con el que pasó
    # como argumento.
    assert origin == (0, 0)
    assert window.shape == (_HEIGHT, _WIDTH)
    assert window[0, 0] == 0
    assert window[_HEIGHT - 1, _WIDTH - 1] == (_HEIGHT - 1) * 1000 + (_WIDTH - 1)
