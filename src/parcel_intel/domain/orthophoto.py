from dataclasses import dataclass
from typing import Literal

from parcel_intel.domain.provenance import Provenance

HistoricalVintage = (
    int
    | Literal[
        "AMS_1956-1957",
        "Interministerial_1973-1986",
        "Nacional_1981-1986",
        "SIGPAC",
        "OLISTAT",
        "CM_1956",
        "CM_1975",
        "CM_1991",
    ]
)
Vintage = Literal["actual"] | HistoricalVintage


@dataclass(frozen=True)
class Orthophoto:
    """Recorte de ortofoto alrededor de una parcela. `vintage` identifica de
    qué momento es la imagen una vez que se desprende de la llamada que la
    produjo (p. ej. al compararse con otras en el módulo de datación) — ver
    ADR 0006."""

    image: bytes
    vintage: Vintage
    provenance: Provenance


@dataclass(frozen=True)
class OrthophotoWindow:
    """Ventana exacta de ortofoto en EPSG:25830: esquinas en metros enteros y
    tamaño en píxeles -- ADR 0042 §2. La resolución (metros por píxel) sale de
    `(max_x - min_x) / width_px`."""

    min_x: int
    min_y: int
    max_x: int
    max_y: int
    srid: int
    width_px: int
    height_px: int

    def __post_init__(self) -> None:
        if self.srid != 25830:
            raise ValueError(f"srid de ventana debe ser 25830, no {self.srid}")
        if self.max_x <= self.min_x or self.max_y <= self.min_y:
            raise ValueError("ventana sin superficie: max debe ser mayor que min")
        if self.width_px <= 0 or self.height_px <= 0:
            raise ValueError("ventana con tamaño en píxeles no positivo")
