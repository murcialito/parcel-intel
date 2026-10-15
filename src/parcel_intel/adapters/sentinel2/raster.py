import numpy as np
import tifffile

from parcel_intel.adapters.sentinel2.client import ContentLengthGetter, RangedHttpGetter


class _RangedFile:
    """File-like mínimo que traduce `.read()`/`.seek()`/`.tell()` a
    peticiones por rango de bytes, para que `tifffile.TiffFile` pueda leer
    un COG remoto sin descargarlo (ADR 0007)."""

    def __init__(self, url: str, ranged_get: RangedHttpGetter, size: int) -> None:
        self._url = url
        self._ranged_get = ranged_get
        self._size = size
        self._pos = 0

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            n = self._size - self._pos
        n = max(0, min(n, self._size - self._pos))
        if n == 0:
            return b""
        data = self._ranged_get(self._url, self._pos, n)
        self._pos += len(data)
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = self._size + offset
        return self._pos

    def tell(self) -> int:
        return self._pos


def open_band(
    url: str, ranged_get: RangedHttpGetter, content_length: ContentLengthGetter
) -> tifffile.TiffFile:
    size = content_length(url)
    return tifffile.TiffFile(_RangedFile(url, ranged_get, size))  # type: ignore[arg-type]


def read_pixel_window(
    tiff: tifffile.TiffFile,
    min_col: int,
    min_row: int,
    max_col: int,
    max_row: int,
) -> tuple[np.ndarray, tuple[int, int]]:
    """Lee solo los tiles que cubren `[min_col,max_col] x [min_row,max_row]`
    (inclusive) y devuelve `(ventana, origen)`, donde `origen` es
    `(min_col, min_row)` **ya acotado** a los límites reales de la imagen.

    Devolver el origen acotado desde aquí (en vez de que quien llama lo
    recalcule) es deliberado: si `min_col`/`min_row` caen fuera del raster
    (p. ej. una celda de salida que reproyecta a un punto fuera de la escena
    nativa, en el borde de un huso UTM), el origen cambia respecto al pedido
    y cualquier indexado posterior debe usar este valor, no el original —
    bug real encontrado en revisión: `_read_window` del adapter devolvía el
    origen sin acotar, desalineado con la ventana realmente leída."""
    page = tiff.pages[0]
    assert isinstance(page, tifffile.TiffPage)
    tile_w, tile_h = page.tilewidth, page.tilelength
    img_w, img_h = page.imagewidth, page.imagelength
    tiles_across = -(-img_w // tile_w)
    tiles_down = -(-img_h // tile_h)

    min_col = max(0, min(min_col, img_w - 1))
    max_col = max(0, min(max_col, img_w - 1))
    min_row = max(0, min(min_row, img_h - 1))
    max_row = max(0, min(max_row, img_h - 1))

    min_tile_col = min_col // tile_w
    max_tile_col = min(tiles_across - 1, max_col // tile_w)
    min_tile_row = min_row // tile_h
    max_tile_row = min(tiles_down - 1, max_row // tile_h)

    window = np.zeros((max_row - min_row + 1, max_col - min_col + 1), dtype=np.uint16)
    for tile_row in range(min_tile_row, max_tile_row + 1):
        for tile_col in range(min_tile_col, max_tile_col + 1):
            index = tile_row * tiles_across + tile_col
            offset = page.dataoffsets[index]
            bytecount = page.databytecounts[index]
            tiff.filehandle.seek(offset)
            raw = tiff.filehandle.read(bytecount)
            decoded = page.decode(raw, index)
            tile = decoded[0] if isinstance(decoded, tuple) else decoded
            tile2d = np.asarray(tile).reshape(tile_h, tile_w)

            tile_col0 = tile_col * tile_w
            tile_row0 = tile_row * tile_h
            ov_col0 = max(tile_col0, min_col)
            ov_row0 = max(tile_row0, min_row)
            ov_col1 = min(tile_col0 + tile_w, max_col + 1)
            ov_row1 = min(tile_row0 + tile_h, max_row + 1)
            window[
                ov_row0 - min_row : ov_row1 - min_row,
                ov_col0 - min_col : ov_col1 - min_col,
            ] = tile2d[
                ov_row0 - tile_row0 : ov_row1 - tile_row0,
                ov_col0 - tile_col0 : ov_col1 - tile_col0,
            ]
    return window, (min_col, min_row)
