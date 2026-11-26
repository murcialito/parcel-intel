"""Camino según Catastro (historia #37, ADR 0028).

Un camino es una parcela rústica con número 9000 o superior cuya subparcela es de
clase `VT` (vía de comunicación de dominio público). La capa es de **uso interno**:
la licencia INSPIRE de Catastro no permite redistribuirla. Sin datos de titularidad.
Solo stdlib.
"""

from dataclasses import dataclass

from parcel_intel.domain.geometry import BBox, Geometry
from parcel_intel.domain.provenance import Provenance, Redistribution

ROAD_PARCEL_NUMBER_MIN = 9000
ROAD_LAND_USE_CLASS = "VT"
CADASTRAL_SRID = 25830
_RURAL_REFERENCE_LENGTH = 14


@dataclass(frozen=True)
class RuralCadastralReference:
    municipality_code: str  # provincia (2) + municipio (3), p. ej. "28043"
    sector: str  # 1 letra
    polygon: int  # posiciones 6-8
    parcel: int  # posiciones 9-13

    @property
    def compact(self) -> str:
        return f"{self.municipality_code}{self.sector}{self.polygon:03d}{self.parcel:05d}"


def parse_rural_reference(compact: str) -> RuralCadastralReference | None:
    """None si no es una referencia rústica de 14 caracteres (urbana, longitud distinta,
    sector no alfabético o tramos no numéricos)."""
    if len(compact) != _RURAL_REFERENCE_LENGTH or not compact.isascii():
        return None
    municipality, sector, polygon, parcel = compact[:5], compact[5], compact[6:9], compact[9:]
    if not (municipality.isdigit() and sector.isalpha() and polygon.isdigit() and parcel.isdigit()):
        return None
    return RuralCadastralReference(
        municipality_code=municipality,
        sector=sector,
        polygon=int(polygon),
        parcel=int(parcel),
    )


def is_road_parcel_number(reference: RuralCadastralReference) -> bool:
    return reference.parcel >= ROAD_PARCEL_NUMBER_MIN


@dataclass(frozen=True)
class SubparcelLandUse:
    class_code: str  # "VT", "HG", "C-"...
    description: str
    area_m2: float  # `ssp` de DNPPP


@dataclass(frozen=True)
class RuralParcelLandUse:
    reference: str
    subparcels: tuple[SubparcelLandUse, ...]
    provenance: Provenance


def is_road_class(class_code: str) -> bool:
    """True si la clase de subparcela es `VT` (vía de comunicación de dominio público)."""
    return class_code.strip().upper() == ROAD_LAND_USE_CLASS


def is_public_road(land_use: RuralParcelLandUse) -> bool:
    """True si al menos una subparcela es de clase `VT`."""
    return any(is_road_class(s.class_code) for s in land_use.subparcels)


@dataclass(frozen=True)
class CadastralRoad:
    cadastral_reference: str
    municipality_code: str
    polygon: int
    parcel: int
    land_use_classes: tuple[str, ...]
    area_m2: float  # `areaValue` del WFS, no el `ssp` de DNPPP
    geometry: Geometry  # EPSG:25830, solo anillos exteriores
    provenance: Provenance  # petición WFS de la tesela donde apareció primero
    land_use_provenance: Provenance  # petición `Consulta_DNPPP`

    def __post_init__(self) -> None:
        if self.geometry.srid != CADASTRAL_SRID:
            raise ValueError(
                f"un camino de Catastro va en EPSG:{CADASTRAL_SRID}, no en {self.geometry.srid}"
            )
        for provenance in (self.provenance, self.land_use_provenance):
            if provenance.redistribution is not Redistribution.INTERNAL_ONLY:
                raise ValueError(
                    "un camino de Catastro es de uso interno: su procedencia no puede ser "
                    f"{provenance.redistribution.value}"
                )


@dataclass(frozen=True)
class CadastralRoadLayer:
    municipality_code: str
    bbox: BBox
    roads: tuple[CadastralRoad, ...]  # ordenados por referencia
    tiles: int
    parcels_seen: int  # únicas y del municipio
    road_number_candidates: int  # de ellas, número >= 9000
    excluded: tuple[tuple[str, tuple[str, ...]], ...]  # (referencia, clases) de 9xxx no VT
    unclassified: tuple[str, ...]  # 9xxx sin respuesta de DNPPP

    @property
    def redistribution(self) -> Redistribution:
        return Redistribution.INTERNAL_ONLY
