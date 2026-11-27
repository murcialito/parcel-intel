"""Decodificador y codificador PNG propios, sin Pillow — historia #140, ADR 0043
(«Herramientas»).

Decodifica PNG de 8 bits no entrelazados de los tipos de color 0 (grises), 2 (RGB),
3 (paleta), 4 (grises con alfa) y 6 (RGBA) con los cinco filtros, a RGB `uint8`.
El alfa se descarta (no se compone). Codifica RGB tipo 2 con filtro 0 y zlib.
Cualquier otra cosa (entrelazado, 16 bits o menos de 8, JPEG, CRC o zlib rotos)
lanza `EvidenceImageFormatError`.
"""

import struct
import zlib

import numpy as np
import numpy.typing as npt

from parcel_intel.ports.errors import EvidenceImageFormatError

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}

Rgb = npt.NDArray[np.uint8]


def _chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if data[:8] != PNG_SIGNATURE:
        raise EvidenceImageFormatError("no empieza por la firma PNG")
    chunks: list[tuple[bytes, bytes]] = []
    position = 8
    while position < len(data):
        if position + 12 > len(data):
            raise EvidenceImageFormatError("PNG truncado")
        length = struct.unpack(">I", data[position : position + 4])[0]
        kind = data[position + 4 : position + 8]
        body = data[position + 8 : position + 8 + length]
        crc_bytes = data[position + 8 + length : position + 12 + length]
        if len(body) != length or len(crc_bytes) != 4:
            raise EvidenceImageFormatError("PNG truncado")
        if struct.unpack(">I", crc_bytes)[0] != zlib.crc32(kind + body):
            raise EvidenceImageFormatError(f"CRC incorrecto en el bloque {kind!r}")
        chunks.append((kind, body))
        position += 12 + length
        if kind == b"IEND":
            break
    return chunks


def _unfilter(raw: bytes, width_bytes: int, height: int, bpp: int) -> npt.NDArray[np.uint8]:
    if len(raw) != height * (width_bytes + 1):
        raise EvidenceImageFormatError("los datos descomprimidos no cuadran con el IHDR")
    rows = np.frombuffer(raw, dtype=np.uint8).reshape(height, width_bytes + 1)
    out = np.zeros((height, width_bytes), dtype=np.uint8)
    previous = np.zeros(width_bytes, dtype=np.uint8)
    for y in range(height):
        filter_type = int(rows[y, 0])
        line = rows[y, 1:]
        if filter_type == 0:
            current = line.copy()
        elif filter_type == 1:  # Sub: acumulado por canal, módulo 256
            current = np.empty(width_bytes, dtype=np.uint8)
            for channel in range(bpp):
                current[channel::bpp] = np.cumsum(line[channel::bpp], dtype=np.uint8)
        elif filter_type == 2:  # Up
            current = line + previous
        elif filter_type == 3:  # Average
            current = _average(line.tolist(), previous.tolist(), bpp)
        elif filter_type == 4:  # Paeth
            current = _paeth(line.tolist(), previous.tolist(), bpp)
        else:
            raise EvidenceImageFormatError(f"filtro PNG desconocido: {filter_type}")
        out[y] = current
        previous = out[y]
    return out


def _average(line: list[int], up: list[int], bpp: int) -> npt.NDArray[np.uint8]:
    current = [0] * len(line)
    for i, value in enumerate(line):
        left = current[i - bpp] if i >= bpp else 0
        current[i] = (value + ((left + up[i]) >> 1)) & 255
    return np.array(current, dtype=np.uint8)


def _paeth(line: list[int], up: list[int], bpp: int) -> npt.NDArray[np.uint8]:
    current = [0] * len(line)
    for i, value in enumerate(line):
        left = current[i - bpp] if i >= bpp else 0
        upper = up[i]
        upper_left = up[i - bpp] if i >= bpp else 0
        estimate = left + upper - upper_left
        da, db, dc = abs(estimate - left), abs(estimate - upper), abs(estimate - upper_left)
        if da <= db and da <= dc:
            predictor = left
        elif db <= dc:
            predictor = upper
        else:
            predictor = upper_left
        current[i] = (value + predictor) & 255
    return np.array(current, dtype=np.uint8)


def decode_png(data: bytes) -> Rgb:
    """Decodifica un PNG a una matriz `(alto, ancho, 3)` de `uint8`."""
    chunks = _chunks(data)
    if not chunks or chunks[0][0] != b"IHDR" or len(chunks[0][1]) != 13:
        raise EvidenceImageFormatError("falta el bloque IHDR")
    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1]
    )
    if color_type not in _CHANNELS:
        raise EvidenceImageFormatError(f"tipo de color no soportado: {color_type}")
    if bit_depth != 8:
        raise EvidenceImageFormatError(f"solo se admiten 8 bits por canal, no {bit_depth}")
    if interlace != 0:
        raise EvidenceImageFormatError("PNG entrelazado no soportado")
    if compression != 0 or filter_method != 0:
        raise EvidenceImageFormatError("método de compresión o de filtro desconocido")
    if width == 0 or height == 0:
        raise EvidenceImageFormatError("dimensiones vacías")
    palette: bytes | None = next((body for kind, body in chunks if kind == b"PLTE"), None)
    if color_type == 3 and (palette is None or len(palette) % 3 != 0 or not palette):
        raise EvidenceImageFormatError("falta la paleta PLTE (tipo de color 3)")
    idat = b"".join(body for kind, body in chunks if kind == b"IDAT")
    try:
        raw = zlib.decompress(idat)
    except zlib.error as error:
        raise EvidenceImageFormatError(f"datos zlib corruptos: {error}") from error
    channels = _CHANNELS[color_type]
    pixels = _unfilter(raw, width * channels, height, channels).reshape(height, width, channels)
    if color_type == 0 or color_type == 4:
        return np.repeat(pixels[:, :, :1], 3, axis=2)
    if color_type in (2, 6):
        return np.ascontiguousarray(pixels[:, :, :3])
    assert palette is not None
    table = np.frombuffer(palette, dtype=np.uint8).reshape(-1, 3)
    indexes = pixels[:, :, 0]
    if int(indexes.max()) >= len(table):
        raise EvidenceImageFormatError("índice de paleta fuera de la tabla PLTE")
    return np.ascontiguousarray(table[indexes])


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def encode_png_rgb(pixels: Rgb) -> bytes:
    """Codifica una matriz `(alto, ancho, 3)` de `uint8` como PNG RGB de 8 bits,
    filtro 0 y zlib al nivel 9. Es determinista para la misma matriz."""
    if pixels.ndim != 3 or pixels.shape[2] != 3 or pixels.dtype != np.uint8:
        raise ValueError("se espera una matriz (alto, ancho, 3) de uint8")
    height, width = int(pixels.shape[0]), int(pixels.shape[1])
    if height == 0 or width == 0:
        raise ValueError("imagen vacía")
    scanlines = np.zeros((height, 1 + width * 3), dtype=np.uint8)
    scanlines[:, 1:] = pixels.reshape(height, width * 3)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(scanlines.tobytes(), 9))
        + _chunk(b"IEND", b"")
    )
