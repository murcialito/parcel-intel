from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Provenance:
    """Procedencia de un dato: de dónde salió, cuándo y bajo qué licencia."""

    source: str
    url: str
    retrieved_at: date
    license: str | None = None
