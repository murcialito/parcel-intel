from datetime import date

from parcel_intel.domain.building import Building
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.provenance import Provenance

_SQUARE_RING = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))


def make_provenance(source: str = "catastro") -> Provenance:
    return Provenance(source=source, url="https://example.invalid", retrieved_at=date(2026, 10, 15))


def make_parcel(
    cadastral_reference: str = "REFCAT-RETIRADA",
    municipality: str = "COLMENAR DE OREJA",
    rings: tuple[tuple[tuple[float, float], ...], ...] = (_SQUARE_RING,),
    area_m2: float = 100.0,
) -> Parcel:
    return Parcel(
        cadastral_reference=cadastral_reference,
        municipality=municipality,
        geometry=Geometry(rings=rings, srid=25830),
        area_m2=area_m2,
        provenance=make_provenance(),
    )


def make_building(
    cadastral_reference: str = "REFCAT-RETIRADA",
    rings: tuple[tuple[tuple[float, float], ...], ...] = (_SQUARE_RING,),
    area_m2: float = 50.0,
    construction_year: int | None = 1980,
) -> Building:
    return Building(
        cadastral_reference=cadastral_reference,
        geometry=Geometry(rings=rings, srid=25830),
        area_m2=area_m2,
        construction_year=construction_year,
        origin="catastro",
        provenance=make_provenance(),
    )
