from datetime import date

import psycopg

from parcel_intel.adapters.postgis.mapping import geometry_to_ewkt, wkt_multipolygon_to_rings
from parcel_intel.domain.building import Building, BuildingOrigin
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.provenance import Provenance

_ParcelRow = tuple[str, str, str, int, float, str, str, date, str | None]
_BuildingRow = tuple[str, str, int, float, int | None, str, str, str, date, str | None]


class ParcelNotFoundInRepositoryError(Exception):
    def __init__(self, cadastral_reference: str) -> None:
        super().__init__(
            f"No hay ninguna parcela guardada con referencia {cadastral_reference!r}"
        )


def _to_building_origin(value: str) -> BuildingOrigin:
    if value == "catastro":
        return "catastro"
    if value == "detected":
        return "detected"
    raise ValueError(f"origin desconocido en la tabla building: {value!r}")


class PostgisParcelRepository:
    """Repositorio concreto, sin port todavía (ver ADR 0004): no hay ningún
    caso de uso real en `application/` que lo consuma por inyección hasta
    que una historia futura lo necesite. Métodos nombrados por capacidad
    para que extraer el `Protocol` el día que haga falta sea barato."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def save_parcel(self, parcel: Parcel) -> None:
        ewkt = geometry_to_ewkt(parcel.geometry)
        try:
            with self._connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO parcel (
                        cadastral_reference, municipality, geometry, area_m2,
                        provenance_source, provenance_url, provenance_retrieved_at,
                        provenance_license
                    ) VALUES (%s, %s, ST_GeomFromEWKT(%s), %s, %s, %s, %s, %s)
                    ON CONFLICT (cadastral_reference) DO UPDATE SET
                        municipality = EXCLUDED.municipality,
                        geometry = EXCLUDED.geometry,
                        area_m2 = EXCLUDED.area_m2,
                        provenance_source = EXCLUDED.provenance_source,
                        provenance_url = EXCLUDED.provenance_url,
                        provenance_retrieved_at = EXCLUDED.provenance_retrieved_at,
                        provenance_license = EXCLUDED.provenance_license
                    """,
                    (
                        parcel.cadastral_reference,
                        parcel.municipality,
                        ewkt,
                        parcel.area_m2,
                        parcel.provenance.source,
                        parcel.provenance.url,
                        parcel.provenance.retrieved_at,
                        parcel.provenance.license,
                    ),
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def get_parcel(self, cadastral_reference: str) -> Parcel:
        try:
            with self._connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT cadastral_reference, municipality, ST_AsText(geometry),
                           ST_SRID(geometry), area_m2, provenance_source, provenance_url,
                           provenance_retrieved_at, provenance_license
                    FROM parcel WHERE cadastral_reference = %s
                    """,
                    (cadastral_reference,),
                )
                row: _ParcelRow | None = cur.fetchone()
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        if row is None:
            raise ParcelNotFoundInRepositoryError(cadastral_reference)
        ref, municipality, wkt, srid, area_m2, p_source, p_url, p_retrieved_at, p_license = row
        return Parcel(
            cadastral_reference=ref,
            municipality=municipality,
            geometry=Geometry(rings=wkt_multipolygon_to_rings(wkt), srid=srid),
            area_m2=float(area_m2),
            provenance=Provenance(
                source=p_source, url=p_url, retrieved_at=p_retrieved_at, license=p_license
            ),
        )

    def save_buildings(self, parcel_reference: str, buildings: list[Building]) -> None:
        try:
            with self._connection.cursor() as cur:
                for building in buildings:
                    ewkt = geometry_to_ewkt(building.geometry)
                    cur.execute(
                        """
                        INSERT INTO building (
                            parcel_reference, cadastral_reference, geometry, area_m2,
                            construction_year, origin, provenance_source, provenance_url,
                            provenance_retrieved_at, provenance_license
                        ) VALUES (%s, %s, ST_GeomFromEWKT(%s), %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            parcel_reference,
                            building.cadastral_reference,
                            ewkt,
                            building.area_m2,
                            building.construction_year,
                            building.origin,
                            building.provenance.source,
                            building.provenance.url,
                            building.provenance.retrieved_at,
                            building.provenance.license,
                        ),
                    )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def get_buildings_for_parcel(self, parcel_reference: str) -> list[Building]:
        try:
            with self._connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT cadastral_reference, ST_AsText(geometry), ST_SRID(geometry), area_m2,
                           construction_year, origin, provenance_source, provenance_url,
                           provenance_retrieved_at, provenance_license
                    FROM building WHERE parcel_reference = %s
                    ORDER BY id
                    """,
                    (parcel_reference,),
                )
                rows: list[_BuildingRow] = cur.fetchall()
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        buildings = []
        for row in rows:
            ref, wkt, srid, area_m2, year, origin, p_source, p_url, p_retrieved_at, p_license = row
            buildings.append(
                Building(
                    cadastral_reference=ref,
                    geometry=Geometry(rings=wkt_multipolygon_to_rings(wkt), srid=srid),
                    area_m2=float(area_m2),
                    construction_year=year,
                    origin=_to_building_origin(origin),
                    provenance=Provenance(
                        source=p_source,
                        url=p_url,
                        retrieved_at=p_retrieved_at,
                        license=p_license,
                    ),
                )
            )
        return buildings
