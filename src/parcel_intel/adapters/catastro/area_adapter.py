"""Catastro por área: parcelas de un bbox (WFS) y uso de una parcela rústica (DNPPP).

Historia #37, ADR 0028. Todas las peticiones pasan por `CachedRawFetcher`: la caché
es inmutable y la fecha de descarga de `Provenance` es la real, no la de lectura.
"""

from parcel_intel.adapters.catastro.client import DNPPP_URL, WFS_PARCEL_URL, wfs_getfeature_params
from parcel_intel.adapters.catastro.parsing import (
    geometry_from_rings,
    parse_dnppp,
    parse_wfs_parcel_collection,
)
from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.domain.cadastral_road import (
    RuralCadastralReference,
    RuralParcelLandUse,
    SubparcelLandUse,
)
from parcel_intel.domain.geometry import BBox
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import (
    AreaQueryLimitExceededError,
    CadastralServiceError,
    TruncatedAreaQueryError,
)

CATASTRO_WFS_TILE_SIDE_M = 900.0
"""REGISTRY.md: 1000×1000 m funciona y 1200×1200 m da "Area of extension out of limits"."""

CATASTRO_INSPIRE_LICENSE = (
    "Licencia de acceso y uso de los servicios y conjuntos de datos INSPIRE de la Dirección "
    "General del Catastro, v1.0 (julio de 2016) — "
    "https://www.catastro.hacienda.gob.es/webinspire/documentos/Licencia.pdf"
)

_AREA_LIMIT_TEXT = "out of limits"


class CatastroAreaAdapter:
    """Implementa `ParcelsInAreaPort` y `RuralParcelLandUsePort` contra Catastro.

    Capa de uso interno: toda `Provenance` sale `INTERNAL_ONLY` (licencia INSPIRE)."""

    def __init__(self, provincia: str, municipio: str, fetcher: CachedRawFetcher) -> None:
        self._provincia = provincia
        self._municipio = municipio
        self._fetcher = fetcher

    def get_parcels_in_bbox(self, bbox: BBox) -> list[Parcel]:
        params = wfs_getfeature_params("cp:CadastralParcel", bbox)

        def validate(content: bytes) -> None:
            collection = parse_wfs_parcel_collection(content)
            text = collection["exception_text"]
            if text is not None:
                if _AREA_LIMIT_TEXT in text.lower():
                    raise AreaQueryLimitExceededError(bbox)
                raise CadastralServiceError(text)
            matched, returned = collection["number_matched"], collection["number_returned"]
            if matched is None or returned is None:
                raise CadastralServiceError("respuesta sin numberMatched/numberReturned")
            if returned < matched:
                raise TruncatedAreaQueryError(bbox, matched, returned)

        response = self._fetcher.fetch(WFS_PARCEL_URL, params, validate=validate)
        provenance = Provenance(
            source="catastro_wfs_cp",
            url=response.url,
            retrieved_at=response.retrieved_at,
            license=CATASTRO_INSPIRE_LICENSE,
            redistribution=Redistribution.INTERNAL_ONLY,
        )
        return [
            Parcel(
                cadastral_reference=raw["reference"],
                municipality=self._municipio,
                geometry=geometry_from_rings(raw["rings"]),
                area_m2=raw["area_m2"],
                provenance=provenance,
            )
            for raw in parse_wfs_parcel_collection(response.content)["parcels"]
        ]

    def get_land_use(self, reference: RuralCadastralReference) -> RuralParcelLandUse:
        params = {
            "Provincia": self._provincia,
            "Municipio": self._municipio,
            "Poligono": str(reference.polygon),
            "Parcela": str(reference.parcel),
        }

        def validate(content: bytes) -> None:
            # `ParcelNotFoundError` si Catastro responde con `lerr`: no se cachea.
            parse_dnppp(content, reference.compact)

        response = self._fetcher.fetch(DNPPP_URL, params, validate=validate)
        raw = parse_dnppp(response.content, reference.compact)
        return RuralParcelLandUse(
            reference=reference.compact,
            subparcels=tuple(
                SubparcelLandUse(
                    class_code=s["class_code"],
                    description=s["description"],
                    area_m2=s["area_m2"],
                )
                for s in raw["subparcels"]
            ),
            provenance=Provenance(
                source="catastro_dnppp",
                url=response.url,
                retrieved_at=response.retrieved_at,
                license=CATASTRO_INSPIRE_LICENSE,
                redistribution=Redistribution.INTERNAL_ONLY,
            ),
        )
