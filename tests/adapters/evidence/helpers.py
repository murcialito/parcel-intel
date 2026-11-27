"""Ayudas de los tests de la evidencia (historia #140): PNG sintéticos con cualquier
tipo de color y cualquier filtro, escritos con un codificador independiente del código
de producción (filtrado directo, byte a byte), y unidades y trazados sintéticos."""

import struct
import zlib
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from parcel_intel.domain.digitization import DigitizedTrail
from parcel_intel.domain.georeferencing import (
    AffineTransform,
    ControlPointSet,
    GeoreferenceFit,
    GeoreferenceUnit,
    UnitSpec,
    WorkingImage,
)
from parcel_intel.domain.provenance import Provenance, Redistribution

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "caminos" / "planimetrias"
HISTORICO = FIXTURES / "historico"
PNOA_FIXTURE = HISTORICO / "pnoa_ma_280075-w1_T003.png"
RECORTE = FIXTURES / "planimetria_colmenar_280075_recorte_casco_2mpx.png"

SYNTHETIC_SHA256 = "ab" * 32
POINTS_SHA256 = "cd" * 32
IMAGE_URL = "https://example.invalid/sintetica"


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def filter_row(filter_type: int, line: Sequence[int], previous: Sequence[int], bpp: int) -> bytes:
    out = bytearray([filter_type])
    for i, value in enumerate(line):
        left = line[i - bpp] if i >= bpp else 0
        up = previous[i]
        up_left = previous[i - bpp] if i >= bpp else 0
        if filter_type == 0:
            predictor = 0
        elif filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = up
        elif filter_type == 3:
            predictor = (left + up) // 2
        else:
            predictor = _paeth(left, up, up_left)
        out.append((value - predictor) & 255)
    return bytes(out)


def make_png(
    color_type: int,
    rows: Sequence[Sequence[int]],
    filters: Sequence[int] = (0,),
    palette: Sequence[tuple[int, int, int]] | None = None,
    bit_depth: int = 8,
    interlace: int = 0,
) -> bytes:
    """`rows`: las muestras de cada fila, ya intercaladas por canal. `filters` se
    reparte cíclicamente entre las filas."""
    channels = CHANNELS[color_type]
    stride = len(rows[0])
    width = stride // channels
    scanlines = b""
    previous = [0] * stride
    for index, line in enumerate(rows):
        scanlines += filter_row(filters[index % len(filters)], line, previous, channels)
        previous = list(line)
    header = struct.pack(">IIBBBBB", width, len(rows), bit_depth, color_type, 0, 0, interlace)
    body = chunk(b"IHDR", header)
    if palette is not None:
        body += chunk(b"PLTE", bytes(c for color in palette for c in color))
    return SIGNATURE + body + chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b"")


def make_unit(
    transform: AffineTransform,
    width_px: int = 3000,
    height_px: int = 2000,
    loo_rmse_m: float = 5.0,
    image_sha256: str = SYNTHETIC_SHA256,
) -> GeoreferenceUnit:
    """Unidad sintética con la afín y el LOO que pida el test (sin puntos de control)."""
    spec = UnitSpec(
        unit_id="280075-w1",
        document_id="280075",
        document_kind="planimetria",
        municipality_code="28043",
        document_date=date(1875, 8, 6),
        document_date_precision="day",
        scale_denominator=25000,
        image_kind="wms_render",
        image_url=IMAGE_URL,
        image_sha256=image_sha256,
        image_width_px=width_px,
        image_height_px=height_px,
        image_retrieved_at=date(2026, 11, 26),
        provenance_source="Planimetría de Colmenar de Oreja, IGN, documento 280075",
        georeferenced_by="fixture-sintetica",
        georeferenced_at=datetime(2026, 11, 26, 10, tzinfo=UTC),
    )
    image = WorkingImage(
        kind="wms_render",
        sha256=image_sha256,
        width_px=width_px,
        height_px=height_px,
        format="image/png",
        provenance=Provenance(
            source=spec.provenance_source,
            url=IMAGE_URL,
            retrieved_at=date(2026, 11, 26),
            license="CC-BY 4.0 © Instituto Geográfico Nacional de España",
            redistribution=Redistribution.PUBLIC,
        ),
    )
    fit = GeoreferenceFit(
        transform=transform,
        n_retained=6,
        rmse_m=loo_rmse_m / 2,
        max_residual_m=loo_rmse_m,
        loo_rmse_m=loo_rmse_m,
        residuals=(),
    )
    return GeoreferenceUnit(
        spec=spec,
        image=image,
        control_points=ControlPointSet(points=(), sha256=POINTS_SHA256),
        fit=fit,
    )


def make_trail(*pixels: tuple[float, float], trail_id: str = "T003") -> DigitizedTrail:
    return DigitizedTrail(
        trail_id=trail_id, pixels=tuple(pixels), kind="senda", label=None, status="proposed"
    )
