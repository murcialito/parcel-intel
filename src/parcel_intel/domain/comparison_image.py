"""Imágenes de comparación de un tramo: ventanas, franjas de vuelo y entidades
-- historia #121, ADR 0042. Solo stdlib."""

import math
import re
from dataclasses import dataclass
from typing import Literal

from parcel_intel.domain.discrepancy_criterion import CriterionRef
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.orthophoto import HistoricalVintage, OrthophotoWindow
from parcel_intel.domain.provenance import Provenance

GROUND_RESOLUTION_M = 0.5
STRETCH_MARGIN_M = 50.0
MIN_WINDOW_SIDE_M = 224
MAX_WINDOW_SIDE_M = 512
WINDOW_SIDE_STEP_M = 32
DENSIFY_STEP_M = 5.0
MAX_WINDOWS_PER_STRETCH = 4
MAX_WINDOWS_PER_MUNICIPALITY = 400
RECENT_FLIGHT_YEAR = 2023

COMPARISON_POLICY = CriterionRef("imagenes_comparacion", 2)

IGN_COMPARISON_SOURCE = "pnoa-historico"
IDEM_COMPARISON_SOURCE = "idem-vuelos-historicos"
IDEM_ATTRIBUTION = (
    "Información geográfica de la Comunidad de Madrid. Acceso público y gratuito en "
    "CC BY 4.0 Comunidad de Madrid ."
)  # literal del aviso legal de la IDEM (NOTICE), con el espacio antes del punto
IDEM_NOTICE = (
    "Cartografía de carácter informativo, sin valor vinculante en procedimientos administrativos."
)

_STRETCH_ID = re.compile(r"[0-9a-f]{16}")
_MUNICIPALITY = re.compile(r"[0-9]{5}")
_SRID = 25830
# Lado máximo de un trozo de puntos: ventana máxima menos dos márgenes y 1 m de holgura.
_MAX_CHUNK_EXTENT_M = MAX_WINDOW_SIDE_M - 2 * STRETCH_MARGIN_M - 1


@dataclass(frozen=True)
class FlightInfo:
    vintage: HistoricalVintage
    period: str
    resolution_m: float
    attribution: str  # cadena literal de la fuente (SCNE o aviso legal de la IDEM)
    source: str  # la `Provenance.source` que pone el adapter del vuelo
    notice: str | None  # aviso obligatorio de la fuente que acompaña a la imagen, o None


def _ign(
    vintage: HistoricalVintage, period: str, resolution_m: float, attribution: str
) -> FlightInfo:
    return FlightInfo(vintage, period, resolution_m, attribution, IGN_COMPARISON_SOURCE, None)


def _pnoa(year: int, resolution_m: float) -> FlightInfo:
    return _ign(year, str(year), resolution_m, f"PNOA {year} CC-BY 4.0 scne.es")


def _idem(vintage: HistoricalVintage, period: str) -> FlightInfo:
    return FlightInfo(vintage, period, 0.5, IDEM_ATTRIBUTION, IDEM_COMPARISON_SOURCE, IDEM_NOTICE)


# Los vuelos de la serie (ADR 0042 §3, ampliado en #208). `CM_1956` no entra: el adapter de
# la IDEM lo sabe pedir, pero queda fuera hasta confirmar la licencia del CECAF.
FLIGHTS: dict[HistoricalVintage, FlightInfo] = {
    f.vintage: f
    for f in (
        _ign(
            "AMS_1956-1957",
            "1956-1957",
            0.5,
            "Orto-AMS 1956-1957 CC-BY 4.0 ejercito.defensa.gob.es",
        ),
        _idem("CM_1975", "1975"),
        _idem("CM_1991", "1991"),
        _ign("SIGPAC", "1997-2003", 0.5, "Orto-SIGPAC 1997-2003 CC-BY 4.0 scne.es"),
        _ign("OLISTAT", "1997-1999", 1.0, "Orto-OLISTAT 1997-1999 CC-BY 4.0 scne.es"),
        _pnoa(2006, 0.5),
        _pnoa(2009, 0.5),
        _pnoa(2011, 0.25),
        _pnoa(2014, 0.25),
        _pnoa(2017, 0.25),
        _pnoa(2020, 0.25),
        _pnoa(RECENT_FLIGHT_YEAR, 0.25),
    )
}


@dataclass(frozen=True)
class ComparisonSlot:
    """Franja de comparación: vuelos por orden de preferencia."""

    name: str
    vintages: tuple[HistoricalVintage, ...]


COMPARISON_SLOTS: tuple[ComparisonSlot, ...] = (
    ComparisonSlot("1956-1957", ("AMS_1956-1957",)),
    ComparisonSlot("1975", ("CM_1975",)),
    ComparisonSlot("1991", ("CM_1991",)),
    ComparisonSlot("1997-2003", ("SIGPAC", "OLISTAT")),
    ComparisonSlot("2006-2011", (2009, 2006, 2011)),
    ComparisonSlot("2014-2020", (2017, 2014, 2020)),
    ComparisonSlot("reciente", (RECENT_FLIGHT_YEAR,)),
)


@dataclass(frozen=True)
class DeclaredGap:
    from_year: int
    to_year: int
    reason: str


# Política v2 (#208): se declara todo intervalo de más de 10 años (inclusivos) sin ningún
# vuelo de la serie. 1992-1996 (5 años) no se declara.
DECLARED_GAPS: tuple[DeclaredGap, ...] = (
    DeclaredGap(1958, 1974, "la serie no tiene ninguna ortofoto de esos años sobre el ámbito"),
    DeclaredGap(
        1976,
        1990,
        "la serie no tiene ninguna ortofoto de esos años sobre el ámbito (los vuelos "
        "Interministerial y Nacional del IGN no tienen imagen en él)",
    ),
)


@dataclass(frozen=True)
class StretchRequest:
    stretch_id: str  # id opaco de 16 hexadecimales en minúscula
    municipality_code: str  # 5 dígitos (INE)
    stretch: MultiLineGeometry  # EPSG:25830

    def __post_init__(self) -> None:
        if not _STRETCH_ID.fullmatch(self.stretch_id):
            raise ValueError("stretch_id debe ser un id opaco de 16 hexadecimales en minúscula")
        if not _MUNICIPALITY.fullmatch(self.municipality_code):
            raise ValueError("municipality_code debe ser un código INE de 5 dígitos")
        if self.stretch.srid != _SRID:
            raise ValueError(f"el tramo debe estar en EPSG:{_SRID}")


@dataclass(frozen=True)
class ComparisonImage:
    slot: str
    vintage: HistoricalVintage
    period: str
    resolution_m: float
    attribution: str
    sha256: str
    byte_size: int
    provenance: Provenance


@dataclass(frozen=True)
class OmittedSlot:
    slot: str
    reason: Literal["sin_cobertura", "fallo"]
    tried: tuple[HistoricalVintage, ...]
    error_type: str | None  # solo con "fallo": nombre de la clase, nunca el mensaje


@dataclass(frozen=True)
class ComparisonWindow:
    window: OrthophotoWindow
    stretch_px: tuple[tuple[tuple[float, float], ...], ...]
    images: tuple[ComparisonImage, ...]
    omitted: tuple[OmittedSlot, ...]


@dataclass(frozen=True)
class StretchComparison:
    stretch_id: str
    municipality_code: str
    policy: CriterionRef
    status: Literal["generada", "tramo_demasiado_largo"]
    windows: tuple[ComparisonWindow, ...]
    gaps: tuple[DeclaredGap, ...]


@dataclass(frozen=True)
class ComparisonManifest:
    """El manifiesto interno de un municipio ya leído (#122; lo consume #172)."""

    municipality_code: str
    policy: CriterionRef
    gaps: tuple[DeclaredGap, ...]
    stretches: tuple[StretchComparison, ...]  # en orden de stretch_id, ids únicos

    def __post_init__(self) -> None:
        ids = [stretch.stretch_id for stretch in self.stretches]
        if len(set(ids)) != len(ids):
            raise ValueError("el manifiesto tiene ids de tramo repetidos")

    def stretch(self, stretch_id: str) -> StretchComparison | None:
        for comparison in self.stretches:
            if comparison.stretch_id == stretch_id:
                return comparison
        return None


class DegenerateStretchError(ValueError):
    """El tramo no tiene ningún segmento medible (vacío, un punto o puntos repetidos)."""


def attribution_for(vintage: HistoricalVintage) -> str:
    return "Obra derivada de " + FLIGHTS[vintage].attribution


def _measurable_parts(
    stretch: MultiLineGeometry,
) -> list[tuple[tuple[float, float], ...]]:
    parts = []
    for line in stretch.lines:
        if len(line) < 2:
            continue
        length = sum(
            math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line, line[1:], strict=False)
        )
        if length > 0:
            parts.append(line)
    return parts


def _densify(line: tuple[tuple[float, float], ...]) -> list[tuple[float, float]]:
    points = [line[0]]
    for a, b in zip(line, line[1:], strict=False):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        pieces = max(1, math.ceil(length / DENSIFY_STEP_M))
        for i in range(1, pieces + 1):
            if i == pieces:
                points.append(b)
            else:
                t = i / pieces
                points.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return points


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def _window_for_chunk(min_x: float, min_y: float, max_x: float, max_y: float) -> OrthophotoWindow:
    extent = max(max_x - min_x, max_y - min_y)
    side = max(
        MIN_WINDOW_SIDE_M,
        math.ceil((extent + 2 * STRETCH_MARGIN_M + 1) / WINDOW_SIDE_STEP_M) * WINDOW_SIDE_STEP_M,
    )
    half = side // 2
    cx = _round_half_up((min_x + max_x) / 2)
    cy = _round_half_up((min_y + max_y) / 2)
    pixels = round(side / GROUND_RESOLUTION_M)
    return OrthophotoWindow(cx - half, cy - half, cx + half, cy + half, _SRID, pixels, pixels)


def comparison_windows(stretch: MultiLineGeometry) -> tuple[OrthophotoWindow, ...] | None:
    """Ventanas de comparación del tramo (ADR 0042 §2), en el orden de sus partes.
    `None` = `tramo_demasiado_largo`. `DegenerateStretchError` si no hay segmento
    medible."""
    parts = _measurable_parts(stretch)
    if not parts:
        raise DegenerateStretchError("el tramo no tiene ningún segmento medible")
    windows: list[OrthophotoWindow] = []
    box: tuple[float, float, float, float] | None = None  # min_x, min_y, max_x, max_y
    for part in parts:
        for x, y in _densify(part):
            if box is not None:
                grown = (min(box[0], x), min(box[1], y), max(box[2], x), max(box[3], y))
                if max(grown[2] - grown[0], grown[3] - grown[1]) <= _MAX_CHUNK_EXTENT_M:
                    box = grown
                    continue
                windows.append(_window_for_chunk(*box))
                if len(windows) >= MAX_WINDOWS_PER_STRETCH:
                    return None  # ya habría al menos una ventana más
            box = (x, y, x, y)
    assert box is not None
    windows.append(_window_for_chunk(*box))
    if len(windows) > MAX_WINDOWS_PER_STRETCH:
        return None
    return tuple(windows)


def stretch_pixels(
    stretch: MultiLineGeometry, window: OrthophotoWindow
) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Trazado en píxeles de la ventana, una lista por parte (ADR 0042 §2)."""
    return tuple(
        tuple(
            (
                round((x - window.min_x) / GROUND_RESOLUTION_M, 1),
                round((window.max_y - y) / GROUND_RESOLUTION_M, 1),
            )
            for x, y in part
        )
        for part in _measurable_parts(stretch)
    )
