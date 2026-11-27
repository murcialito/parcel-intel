"""Apoyo de los tests de la capa de caminos de Catastro (historia #37).

Todo sale de las fixtures SINTÉTICAS de `tests/fixtures/caminos/` y de su generador
(`tests/fixtures/generate_caminos.py`, #46): no se graba ninguna respuesta real ni se
nombra ninguna referencia real. Los casos que la tabla `TILES` no cubre se construyen
aquí con `render_dnppp`, `SyntheticParcel`/`SyntheticSurface` y `wfs_cp_collection`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from parcel_intel.adapters.catastro.client import DNPPP_URL, WFS_PARCEL_URL
from parcel_intel.adapters.catastro.parsing import (
    geometry_from_rings,
    parse_dnppp,
    parse_wfs_parcel_collection,
)
from parcel_intel.domain.cadastral_road import (
    RuralCadastralReference,
    RuralParcelLandUse,
    SubparcelLandUse,
)
from parcel_intel.domain.geometry import BBox
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import ParcelNotFoundError
from tests.fixtures import generate_caminos
from tests.fixtures.generate_caminos import TILES, Tile

CAMINOS_DIR = Path(__file__).parent / "fixtures" / "caminos"
WFS_FIXTURE = CAMINOS_DIR / generate_caminos.WFS_FILE
TODAY = date(2026, 11, 26)
WINDOW: BBox = (469000.0, 4439000.0, 469600.0, 4439600.0)

ROAD_REFS = (
    "28043A99109101",
    "28043A99109102",
    "28043A99209201",
    "28043A99209202",
)
CONTROL_REF = "28043A99100001"
HG_DESCRIPTION = "HIDROGRAFÍA NATURAL (RÍO,LAGUNA,ARROYO.)"


def provenance(source: str = "test", url: str = "https://prueba.invalid/") -> Provenance:
    return Provenance(
        source=source,
        url=url,
        retrieved_at=TODAY,
        license="licencia de prueba",
        redistribution=Redistribution.INTERNAL_ONLY,
    )


def dnppp_bytes(reference: str) -> bytes:
    """Respuesta DNPPP sintética versionada de una parcela de la tabla."""
    for tile in TILES:
        if tile.ref == reference and tile.dnppp is not None:
            return (CAMINOS_DIR / generate_caminos.dnppp_file_name(tile)).read_bytes()
    raise ParcelNotFoundError(reference)


def fixture_parcels() -> list[Parcel]:
    """Las 20 parcelas de la fixture WFS, tal como las parsea el adapter."""
    collection = parse_wfs_parcel_collection(WFS_FIXTURE.read_bytes())
    return [
        Parcel(
            cadastral_reference=raw["reference"],
            municipality="COLMENAR DE OREJA",
            geometry=geometry_from_rings(raw["rings"]),
            area_m2=raw["area_m2"],
            provenance=provenance("catastro_wfs_cp", "https://prueba.invalid/wfs"),
        )
        for raw in collection["parcels"]
    ]


def table_parcel(tile: Tile) -> Parcel:
    return Parcel(
        cadastral_reference=tile.ref,
        municipality="COLMENAR DE OREJA",
        geometry=geometry_from_rings((generate_caminos.clockwise_ring(tile),)),
        area_m2=float(tile.area),
        provenance=provenance("catastro_wfs_cp", "https://prueba.invalid/wfs"),
    )


class FixtureParcelsPort:
    """Devuelve las mismas parcelas para cualquier bbox y anota las llamadas."""

    def __init__(self, parcels: list[Parcel]) -> None:
        self._parcels = parcels
        self.calls: list[BBox] = []

    def get_parcels_in_bbox(self, bbox: BBox) -> list[Parcel]:
        self.calls.append(bbox)
        return list(self._parcels)


class TableParcelsPort:
    """Port de prueba de CA3: para cada bbox, las parcelas de la tabla sintética cuyo
    rectángulo interseca el INTERIOR del bbox, con su geometría completa (sin recortar)."""

    def __init__(self) -> None:
        self.calls: list[BBox] = []
        self.responses: list[list[str]] = []

    def get_parcels_in_bbox(self, bbox: BBox) -> list[Parcel]:
        found = self._intersecting(bbox)
        self.calls.append(bbox)
        self.responses.append([p.cadastral_reference for p in found])
        return found

    @staticmethod
    def _intersecting(bbox: BBox) -> list[Parcel]:
        minx, miny, maxx, maxy = bbox
        found: list[Parcel] = []
        for tile in TILES:
            x0 = generate_caminos.ORIGIN_X + tile.x0
            x1 = generate_caminos.ORIGIN_X + tile.x1
            y0 = generate_caminos.ORIGIN_Y + tile.y0
            y1 = generate_caminos.ORIGIN_Y + tile.y1
            if x0 < maxx and x1 > minx and y0 < maxy and y1 > miny:
                found.append(table_parcel(tile))
        return found


class FixtureLandUsePort:
    """Uso de suelo desde respuestas DNPPP (versionadas o añadidas por el test).

    Una referencia sin respuesta o en `missing` lanza `ParcelNotFoundError`."""

    def __init__(
        self,
        extra: dict[str, bytes] | None = None,
        missing: frozenset[str] = frozenset(),
    ) -> None:
        self._extra = extra or {}
        self._missing = missing
        self.calls: list[str] = []

    def get_land_use(self, reference: RuralCadastralReference) -> RuralParcelLandUse:
        self.calls.append(reference.compact)
        if reference.compact in self._missing:
            raise ParcelNotFoundError(reference.compact)
        body = self._extra.get(reference.compact) or dnppp_bytes(reference.compact)
        raw = parse_dnppp(body, reference.compact)
        return RuralParcelLandUse(
            reference=reference.compact,
            subparcels=tuple(
                SubparcelLandUse(s["class_code"], s["description"], s["area_m2"])
                for s in raw["subparcels"]
            ),
            provenance=provenance("catastro_dnppp", "https://prueba.invalid/dnppp"),
        )


class FixtureCatastroHttp:
    """`HttpGet` de prueba para el adapter: sirve la fixture WFS y las DNPPP sintéticas."""

    def __init__(self, wfs: bytes | None = None, dnppp: dict[str, bytes] | None = None) -> None:
        self._wfs = WFS_FIXTURE.read_bytes() if wfs is None else wfs
        self._dnppp = dnppp or {}
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls.append((url, dict(params)))
        if url == WFS_PARCEL_URL:
            return self._wfs
        assert url == DNPPP_URL, url
        reference = f"28043A{int(params['Poligono']):03d}{int(params['Parcela']):05d}"
        if reference in self._dnppp:
            return self._dnppp[reference]
        try:
            return dnppp_bytes(reference)
        except ParcelNotFoundError:
            return DNPPP_NOT_FOUND


DNPPP_NOT_FOUND = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<consulta_dnp xmlns="http://www.catastro.meh.es/">'
    "<control><cudnp>0</cudnp></control>"
    "<lerr><err><cod>4</cod><des>LA PARCELA NO EXISTE (SINTÉTICA)</des></err></lerr>"
    "</consulta_dnp>"
).encode()
