import unicodedata
from dataclasses import dataclass

from parcel_intel.domain.provenance import Provenance


@dataclass(frozen=True)
class BulletinNotice:
    """Disposición de un boletín oficial, sin geolocalizar ni extraer
    entidades todavía (eso es `bulletin_entry` de `docs/vision.md`, una
    historia futura — ver ADR 0008 sobre por qué no se adelanta aquí)."""

    identifier: str
    title: str
    section_code: str
    section_name: str
    pdf_url: str
    provenance: Provenance


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def filter_by_title(notices: list[BulletinNotice], search_text: str) -> list[BulletinNotice]:
    """Substring simple, insensible a mayúsculas y tildes, sobre el título.

    Función pura de dominio, no un método de port (ADR 0008): comparar un
    texto de búsqueda contra disposiciones ya obtenidas no tiene E/S ni
    conocimiento de ningún proveedor de boletines — mismo criterio que
    `bbox_with_margin` (ADR 0006) y `compute_change_mask` (ADR 0007).
    """
    needle = _normalize(search_text)
    return [notice for notice in notices if needle in _normalize(notice.title)]
