from datetime import UTC, date
from datetime import datetime as _datetime

from parcel_intel.adapters.catastro.client import (
    CPMRC_URL,
    WFS_BUILDING_URL,
    WFS_PARCEL_URL,
    HttpGetter,
    default_http_getter,
)
from parcel_intel.adapters.catastro.geometry_ops import point_in_any_ring, ring_centroid
from parcel_intel.adapters.catastro.parsing import (
    geometry_from_rings,
    parse_cpmrc_centroid,
    parse_wfs_buildings,
    parse_wfs_parcels,
)
from parcel_intel.adapters.catastro.reference import to_compact_reference
from parcel_intel.domain.building import Building
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.provenance import Provenance
from parcel_intel.ports.errors import ParcelNotFoundError

_BBOX_HALF_WIDTH_M = 150.0
_CRS_PARAM = "EPSG:25830"


def _today() -> date:
    return _datetime.now(tz=UTC).date()


class CatastroAdapter:
    """Implementa `ParcelGeometryPort` y `BuildingGeometryPort` contra Catastro.

    Método confirmado en `sources/REGISTRY.md`: Catastro no soporta filtrar su
    WFS por referencia catastral (ni `CQL_FILTER` ni `Filter` OGC por POST
    funcionan en este servicio). La única vía fiable es resolver primero un
    centroide vía `Consulta_CPMRC` y luego pedir un `GetFeature` de bbox
    pequeño centrado en ese punto, emparejando el resultado del lado del
    cliente por `nationalCadastralReference`.
    """

    def __init__(
        self,
        provincia: str,
        municipio: str,
        http_get: HttpGetter = default_http_getter,
    ) -> None:
        self._provincia = provincia
        self._municipio = municipio
        self._http_get = http_get

    def get_parcel(self, cadastral_reference: str) -> Parcel:
        compact = to_compact_reference(cadastral_reference)
        x, y = self._centroid(compact)
        return self._parcel_at(compact, x, y)

    def _parcel_at(self, compact: str, x: float, y: float) -> Parcel:
        bbox = self._bbox(x, y)
        params = self._wfs_params("cp:CadastralParcel", bbox)
        raw = self._http_get(WFS_PARCEL_URL, params)
        for parcel in parse_wfs_parcels(raw):
            if parcel["reference"] == compact:
                return Parcel(
                    cadastral_reference=compact,
                    municipality=self._municipio,
                    geometry=geometry_from_rings(parcel["rings"]),
                    area_m2=parcel["area_m2"],
                    provenance=Provenance(
                        source="catastro",
                        url=f"{WFS_PARCEL_URL}?{self._params_to_query(params)}",
                        retrieved_at=_today(),
                    ),
                )
        raise ParcelNotFoundError(compact)

    def get_buildings(self, cadastral_reference: str) -> list[Building]:
        compact = to_compact_reference(cadastral_reference)
        x, y = self._centroid(compact)
        parcel = self._parcel_at(compact, x, y)

        bbox = self._bbox(x, y)
        params = self._wfs_params("bu:Building", bbox)
        raw = self._http_get(WFS_BUILDING_URL, params)

        buildings: list[Building] = []
        for raw_building in parse_wfs_buildings(raw):
            rings = raw_building["rings"]
            if not rings:
                continue
            # Un edificio puede tener varios cuerpos (anillos); basta con que
            # el centroide de alguno caiga en alguno de los anillos de la
            # parcela para considerarlo asociado a ella.
            belongs_to_parcel = any(
                point_in_any_ring(ring_centroid(ring), parcel.geometry.rings) for ring in rings
            )
            if not belongs_to_parcel:
                continue
            buildings.append(
                Building(
                    cadastral_reference=raw_building["reference"],
                    geometry=geometry_from_rings(rings),
                    area_m2=raw_building["area_m2"],
                    construction_year=raw_building["construction_year"],
                    origin="catastro",
                    provenance=Provenance(
                        source="catastro",
                        url=f"{WFS_BUILDING_URL}?{self._params_to_query(params)}",
                        retrieved_at=_today(),
                    ),
                )
            )
        return buildings

    def _centroid(self, compact_reference: str) -> tuple[float, float]:
        params = {
            "Provincia": self._provincia,
            "Municipio": self._municipio,
            "RC": compact_reference,
            "SRS": _CRS_PARAM,
        }
        raw = self._http_get(CPMRC_URL, params)
        return parse_cpmrc_centroid(raw, compact_reference)

    def _bbox(self, x: float, y: float) -> tuple[float, float, float, float]:
        return (
            x - _BBOX_HALF_WIDTH_M,
            y - _BBOX_HALF_WIDTH_M,
            x + _BBOX_HALF_WIDTH_M,
            y + _BBOX_HALF_WIDTH_M,
        )

    def _wfs_params(
        self, type_name: str, bbox: tuple[float, float, float, float]
    ) -> dict[str, str]:
        minx, miny, maxx, maxy = bbox
        return {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typenames": type_name,
            "srsname": "urn:ogc:def:crs:EPSG::25830",
            "bbox": f"{minx},{miny},{maxx},{maxy},urn:ogc:def:crs:EPSG::25830",
        }

    @staticmethod
    def _params_to_query(params: dict[str, str]) -> str:
        return "&".join(f"{key}={value}" for key, value in params.items())
