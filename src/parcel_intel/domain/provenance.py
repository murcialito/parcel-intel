from dataclasses import dataclass
from datetime import date
from enum import Enum


class Redistribution(Enum):
    """Si la licencia de la fuente permite redistribuir el dato."""

    INTERNAL_ONLY = "solo_uso_interno"  # se puede analizar, no se publica
    PUBLIC = "publicable"  # la licencia permite redistribuirlo


@dataclass(frozen=True)
class Provenance:
    """Procedencia de un dato: de dónde salió, cuándo, bajo qué licencia y si es publicable.

    `redistribution` cierra por defecto en `INTERNAL_ONLY`: publicar exige marcarlo
    `PUBLIC` explícitamente en el adapter, junto a la licencia citada en `REGISTRY.md`.
    """

    source: str
    url: str
    retrieved_at: date
    license: str | None = None
    redistribution: Redistribution = Redistribution.INTERNAL_ONLY
