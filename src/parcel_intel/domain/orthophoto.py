from dataclasses import dataclass
from typing import Literal

from parcel_intel.domain.provenance import Provenance

HistoricalVintage = (
    int | Literal["AMS_1956-1957", "Interministerial_1973-1986", "Nacional_1981-1986"]
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
