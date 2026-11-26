from datetime import date

from parcel_intel.domain.building import Building
from parcel_intel.domain.geometry import Geometry, Line, LineGeometry
from parcel_intel.domain.historic_trail import HistoricTrail
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.provenance import Provenance

_SQUARE_RING = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))


def make_provenance(source: str = "catastro") -> Provenance:
    return Provenance(source=source, url="https://example.invalid", retrieved_at=date(2026, 10, 15))


def make_parcel(
    cadastral_reference: str = "99043A90100001",
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
    cadastral_reference: str = "9900201ZZ0000S",
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


# SINTÉTICO (historia #19): trazado escrito a mano con los metadatos reales
# de la planimetría de Colmenar de Oreja (documento 280075, REGISTRY.md), pero
# la línea NO sale de ninguna digitalización real (eso es #20). Coordenadas
# con como mucho 3 decimales para que `ST_AsText` las devuelva idénticas.
SYNTHETIC_COLMENAR_280075_LINE: Line = (
    (467400.0, 4441800.0),
    (467520.5, 4441910.25),
    (467650.75, 4441985.5),
)
SYNTHETIC_COLMENAR_280075_PROVENANCE = Provenance(
    source="Planimetría de Colmenar de Oreja, IGN, documento 280075",
    url="https://www.ign.es/wms/minutas-cartograficas",
    retrieved_at=date(2026, 11, 25),
    license="CC BY 4.0 ign.es",
)


def make_synthetic_historic_trail(
    identifier: str = "280075-001",
    municipality_code: str = "28043",
    points: Line = SYNTHETIC_COLMENAR_280075_LINE,
    georeferencing_error_m: float = 12.5,
) -> HistoricTrail:
    """Trazado histórico SINTÉTICO de Colmenar de Oreja (ver comentario de
    arriba). `georeferencing_error_m=12.5` es ilustrativo, no un umbral."""
    return HistoricTrail(
        identifier=identifier,
        municipality_code=municipality_code,
        document_kind="planimetria",
        document_id="280075",
        document_date=date(1875, 8, 6),
        document_date_precision="day",
        geometry=LineGeometry(points=points, srid=25830),
        georeferencing_error_m=georeferencing_error_m,
        provenance=SYNTHETIC_COLMENAR_280075_PROVENANCE,
    )
