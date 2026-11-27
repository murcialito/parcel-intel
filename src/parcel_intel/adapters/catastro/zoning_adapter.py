"""Catastro: polígonos catastrales rústicos (`cp:CadastralZoning`) de un bbox (WFS).

Historia #217. Mismo servicio, caché y licencia que `CatastroAreaAdapter` (ADR 0028).
Capa de uso interno: nunca se publica.
"""

from parcel_intel.adapters.catastro.area_adapter import CATASTRO_INSPIRE_LICENSE
from parcel_intel.adapters.catastro.client import WFS_PARCEL_URL, wfs_getfeature_params
from parcel_intel.adapters.catastro.parsing import geometry_from_rings, parse_wfs_zoning_collection
from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.domain.cadastral_zoning import POLYGON_ZONING_LEVEL, CadastralZone
from parcel_intel.domain.geometry import BBox
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import (
    AreaQueryLimitExceededError,
    CadastralServiceError,
    TruncatedAreaQueryError,
)

# El servicio responde en español para esta capa («Area de la extensión fuera de los límites»,
# comprobado el 2026-11-27) y en inglés para parcelas («out of limits»).
_AREA_LIMIT_TEXTS = ("out of limits", "fuera de los límites", "fuera de los limites")


class CatastroZoningAdapter:
    """Implementa `CadastralZoningPort` contra el WFS INSPIRE de Catastro."""

    def __init__(self, fetcher: CachedRawFetcher) -> None:
        self._fetcher = fetcher

    def get_zones_in_bbox(self, bbox: BBox) -> list[CadastralZone]:
        params = wfs_getfeature_params("cp:CadastralZoning", bbox)

        def validate(content: bytes) -> None:
            collection = parse_wfs_zoning_collection(content)
            text = collection["exception_text"]
            if text is not None:
                if any(limit in text.lower() for limit in _AREA_LIMIT_TEXTS):
                    raise AreaQueryLimitExceededError(bbox)
                raise CadastralServiceError(text)
            matched, returned = collection["number_matched"], collection["number_returned"]
            if matched is None or returned is None:
                raise CadastralServiceError("respuesta sin numberMatched/numberReturned")
            if returned < matched:
                raise TruncatedAreaQueryError(bbox, matched, returned)

        response = self._fetcher.fetch(WFS_PARCEL_URL, params, validate=validate)
        provenance = Provenance(
            source="catastro_wfs_cp_zoning",
            url=response.url,
            retrieved_at=response.retrieved_at,
            license=CATASTRO_INSPIRE_LICENSE,
            redistribution=Redistribution.INTERNAL_ONLY,
        )
        # CA2: solo `2ndOrder` (polígonos); el nivel `1stOrder` (el término) se descarta.
        return [
            CadastralZone(
                label=raw["label"],
                level=raw["level"],
                geometry=geometry_from_rings(raw["rings"]),
                provenance=provenance,
            )
            for raw in parse_wfs_zoning_collection(response.content)["zones"]
            if raw["level"] == POLYGON_ZONING_LEVEL
        ]
