"""Evidencia PNG de dos paneles de un trazado propuesto — historia #140 (hija E
de #20), ADR 0043 y diseño de #20 (2.d).

Panel 1: el recorte de la imagen de trabajo con el trazado (línea de 2 px).
Panel 2: la ortofoto PNOA con la banda de ± 2 × RMSE LOO mezclada al 35 % y,
encima, el trazado transformado. Van lado a lado, rellenos de blanco hasta la
altura mayor. Se escribe `<unit_id>/evidencia/<trail_id>.png` y su
`.procedencia.json`, sin ninguna clave de titularidad.
"""

import hashlib
import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt

from parcel_intel.adapters.evidence.png import Rgb, decode_png, encode_png_rgb
from parcel_intel.adapters.evidence.pnoa_png import PnoaPngSource
from parcel_intel.domain.digitization import DigitizedTrail
from parcel_intel.domain.geometry import Point
from parcel_intel.domain.georeferencing import GeoreferenceUnit, round_mm
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.trail_evidence import (
    BAND_ALPHA,
    BAND_COLOR,
    LINE_COLOR,
    LINE_WIDTH_PX,
    PNOA_EVIDENCE_LICENSE,
    EvidenceLayout,
    EvidenceRecord,
    band_radius_m,
    evidence_layout,
    layer_attributions,
)
from parcel_intel.ports.errors import EvidenceImageFormatError, RawImageMismatchError

_Floats = npt.NDArray[np.float64]
_PNOA_SOURCE = "pnoa-ma"


def within_distance(
    xs: _Floats, ys: _Floats, vertices: Sequence[Point], radius: float
) -> npt.NDArray[np.bool_]:
    """Máscara `(len(ys), len(xs))` de los centros de píxel a ≤ `radius` de la
    polilínea. `xs` e `ys` son las coordenadas de los centros de columna y de
    fila, en la misma unidad que los vértices y el radio."""
    mask = np.zeros((len(ys), len(xs)), dtype=np.bool_)
    for (ax, ay), (bx, by) in zip(vertices, vertices[1:], strict=False):
        columns = np.nonzero((xs >= min(ax, bx) - radius) & (xs <= max(ax, bx) + radius))[0]
        rows = np.nonzero((ys >= min(ay, by) - radius) & (ys <= max(ay, by) + radius))[0]
        if columns.size == 0 or rows.size == 0:
            continue
        px = xs[columns][np.newaxis, :]
        py = ys[rows][:, np.newaxis]
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / length_sq, 0.0, 1.0) if length_sq else 0.0
        distance_sq = (px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2
        mask[np.ix_(rows, columns)] |= distance_sq <= radius * radius
    return mask


def _centers(count: int) -> _Floats:
    return np.arange(count, dtype=np.float64) + 0.5


def _draw_line(panel: Rgb, vertices: Sequence[Point]) -> None:
    height, width = panel.shape[:2]
    mask = within_distance(_centers(width), _centers(height), vertices, LINE_WIDTH_PX / 2)
    panel[mask] = LINE_COLOR


def _blend_band(panel: Rgb, mask: npt.NDArray[np.bool_]) -> None:
    mixed = panel[mask].astype(np.float64) * (1 - BAND_ALPHA) + np.array(BAND_COLOR) * BAND_ALPHA
    panel[mask] = np.rint(mixed).astype(np.uint8)


def _write_atomic(path: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


class PngTrailEvidence:
    """Implementa `TrailEvidencePort` escribiendo bajo `output_root` (en
    producción `curated/historico/`; en los tests, un `tmp_path`)."""

    def __init__(self, raw_image_dir: Path, output_root: Path, pnoa: PnoaPngSource) -> None:
        self._raw_image_dir = raw_image_dir
        self._output_root = output_root
        self._pnoa = pnoa

    def render(self, unit: GeoreferenceUnit, trail: DigitizedTrail) -> EvidenceRecord:
        layout = evidence_layout(unit, trail)
        planimetry_panel = self._planimetry_panel(unit, trail, layout)
        response = self._pnoa.fetch(layout.window, layout.pnoa_width_px, layout.pnoa_height_px)
        pnoa_panel = self._pnoa_panel(unit, trail, layout, decode_png(response.content))
        png = encode_png_rgb(_side_by_side(planimetry_panel, pnoa_panel))
        png_sha256 = hashlib.sha256(png).hexdigest()
        pnoa_provenance = Provenance(
            source=_PNOA_SOURCE,
            url=response.url,
            retrieved_at=response.retrieved_at,
            license=PNOA_EVIDENCE_LICENSE,
            redistribution=Redistribution.PUBLIC,
        )
        self._write(unit, trail, png, png_sha256, pnoa_provenance)
        return EvidenceRecord(trail.trail_id, png_sha256, pnoa_provenance)

    # -- paneles -------------------------------------------------------------

    def _planimetry_panel(
        self, unit: GeoreferenceUnit, trail: DigitizedTrail, layout: EvidenceLayout
    ) -> Rgb:
        path = self._raw_image_dir / f"{unit.spec.unit_id}.png"
        try:
            content = path.read_bytes()
        except FileNotFoundError as error:
            raise RawImageMismatchError(unit.spec.unit_id, f"falta {path.name}") from error
        if hashlib.sha256(content).hexdigest() != unit.image.sha256:
            raise RawImageMismatchError(
                unit.spec.unit_id, "el cuerpo en caché no es la imagen de trabajo declarada"
            )
        image = decode_png(content)
        if image.shape[:2] != (unit.image.height_px, unit.image.width_px):
            raise RawImageMismatchError(
                unit.spec.unit_id, "dimensiones distintas de las declaradas"
            )
        x0, y0, x1, y1 = layout.crop
        panel = np.ascontiguousarray(image[y0 : y1 : layout.step, x0 : x1 : layout.step])
        vertices = [
            ((col - x0) / layout.step, (row - y0) / layout.step) for col, row in trail.pixels
        ]
        _draw_line(panel, vertices)
        return panel

    def _pnoa_panel(
        self, unit: GeoreferenceUnit, trail: DigitizedTrail, layout: EvidenceLayout, image: Rgb
    ) -> Rgb:
        height, width = layout.pnoa_height_px, layout.pnoa_width_px
        if image.shape[:2] != (height, width):
            raise EvidenceImageFormatError(
                f"PNOA devolvió {image.shape[1]}x{image.shape[0]} px, se pedían {width}x{height}"
            )
        min_x, min_y, max_x, max_y = layout.window
        scale_x = (max_x - min_x) / width
        scale_y = (max_y - min_y) / height
        world = [round_mm(unit.fit.transform.apply(col, row)) for col, row in trail.pixels]
        panel = image.copy()
        xs = min_x + _centers(width) * scale_x
        ys = max_y - _centers(height) * scale_y
        _blend_band(panel, within_distance(xs, ys, world, band_radius_m(unit)))
        pixels = [((x - min_x) / scale_x, (max_y - y) / scale_y) for x, y in world]
        _draw_line(panel, pixels)
        return panel

    # -- salida --------------------------------------------------------------

    def _write(
        self,
        unit: GeoreferenceUnit,
        trail: DigitizedTrail,
        png: bytes,
        png_sha256: str,
        pnoa: Provenance,
    ) -> None:
        directory = self._output_root / unit.spec.unit_id / "evidencia"
        directory.mkdir(parents=True, exist_ok=True)
        image = unit.image.provenance
        record = {
            "unit_id": unit.spec.unit_id,
            "trail_id": trail.trail_id,
            "control_points_sha256": unit.control_points.sha256,
            "imagen_trabajo": {
                "url": image.url,
                "sha256": unit.image.sha256,
                "fecha_descarga": image.retrieved_at.isoformat(),
                "licencia": image.license,
            },
            "pnoa": {
                "url": pnoa.url,
                "fecha_descarga": pnoa.retrieved_at.isoformat(),
                "licencia": pnoa.license,
            },
            "atribuciones": list(layer_attributions(unit)),
            "png_sha256": png_sha256,
        }
        # El PNG va antes que su procedencia: sin ella, el PNG no está completo.
        _write_atomic(directory / f"{trail.trail_id}.png", png)
        _write_atomic(
            directory / f"{trail.trail_id}.procedencia.json",
            (json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
        )


def _side_by_side(left: Rgb, right: Rgb) -> Rgb:
    height = max(left.shape[0], right.shape[0])
    canvas = np.full((height, left.shape[1] + right.shape[1], 3), 255, dtype=np.uint8)
    canvas[: left.shape[0], : left.shape[1]] = left
    canvas[: right.shape[0], left.shape[1] :] = right
    return canvas
