from collections.abc import Callable, Sequence
from datetime import UTC, date
from datetime import datetime as _datetime
from urllib.parse import urlencode

import requests
from pyproj import Transformer

from parcel_intel.adapters.ign_admin_units.client import WFS_URL, HttpGetter, default_http_getter
from parcel_intel.adapters.ign_admin_units.parsing import (
    AdministrativeUnitParseError,
    ParsedAdministrativeUnits,
    RawAdministrativeUnit,
    is_municipality,
    parse_administrative_units,
)
from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import (
    IncompleteWfsResponseError,
    MunicipalBoundaryNotFoundError,
    MunicipalBoundaryUnusableError,
)

SOURCE = "ign_unidades_administrativas"
LICENSE = "CC BY 4.0 ign.es"
TARGET_SRID = 25830
_SOURCE_CRS = "EPSG:4258"
_CRS_URN = "urn:ogc:def:crs:EPSG::4258"
_COUNT = "200"

SearchBBox = tuple[float, float, float, float]
"""(lat_min, lon_min, lat_max, lon_max) en EPSG:4258: orden de ejes de la
autoridad, el que exige el WFS con el CRS en `urn:ogc:def:crs:EPSG::4258`."""


def _today() -> date:
    return _datetime.now(tz=UTC).date()


class IgnAdministrativeUnitsAdapter:
    """Implementa `MunicipalBoundaryPort` contra el WFS INSPIRE de unidades
    administrativas del IGN (ADR 0031).

    Pide por bbox (el servicio no se ha verificado que filtre por atributo) y
    filtra en el cliente: nivel `4thOrder` e INE = 5 últimos dígitos de
    `nationalCode`. Reproyecta de EPSG:4258 a EPSG:25830.
    """

    def __init__(
        self,
        search_bbox: SearchBBox,
        http_get: HttpGetter = default_http_getter,
        fetcher: CachedRawFetcher | None = None,
        today: Callable[[], date] = _today,
    ) -> None:
        self._search_bbox = search_bbox
        self._http_get = http_get
        self._fetcher = fetcher
        self._today = today

    def get_municipal_boundaries(self, ine_codes: Sequence[str]) -> list[MunicipalBoundary]:
        params = self._params()
        canonical_url = f"{WFS_URL}?{urlencode(sorted(params.items()))}"
        parsed_box: list[ParsedAdministrativeUnits] = []

        def validate(body: bytes) -> None:
            parsed = _parse_and_check(body, canonical_url)
            parsed_box.append(parsed)

        try:
            if self._fetcher is not None:
                response = self._fetcher.fetch(WFS_URL, params, validate=validate)
                body, url, retrieved_at = response.content, response.url, response.retrieved_at
            else:
                body = self._http_get(WFS_URL, params)
                validate(body)
                url, retrieved_at = canonical_url, self._today()
            # Respuesta fresca: `validate` ya la parseó. Respuesta de la caché cruda:
            # no pasa por `validate`, así que se parsea (y comprueba) aquí.
            parsed = parsed_box[0] if parsed_box else _parse_and_check(body, canonical_url)
        except requests.RequestException as exc:
            raise MunicipalBoundaryUnusableError(str(exc)) from exc
        except AdministrativeUnitParseError as exc:
            raise MunicipalBoundaryUnusableError(str(exc)) from exc

        by_code = {u["ine_code"]: u for u in parsed["units"] if is_municipality(u)}
        missing = [code for code in ine_codes if code not in by_code]
        if missing:
            raise MunicipalBoundaryNotFoundError(missing)

        # CC BY 4.0 ign.es, «Publicar» en REGISTRY.md: redistribuible (historia #185, ADR 0051).
        provenance = Provenance(
            source=SOURCE,
            url=url,
            retrieved_at=retrieved_at,
            license=LICENSE,
            redistribution=Redistribution.PUBLIC,
        )
        transformer = Transformer.from_crs(_SOURCE_CRS, f"EPSG:{TARGET_SRID}")
        return [_to_boundary(by_code[code], transformer, provenance) for code in ine_codes]

    def _params(self) -> dict[str, str]:
        lat_min, lon_min, lat_max, lon_max = self._search_bbox
        return {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": "au:AdministrativeUnit",
            "bbox": f"{lat_min},{lon_min},{lat_max},{lon_max},{_CRS_URN}",
            "count": _COUNT,
        }


def _parse_and_check(body: bytes, url: str) -> ParsedAdministrativeUnits:
    parsed = parse_administrative_units(body)
    matched = parsed["number_matched"]
    if matched is not None and matched != len(parsed["units"]):
        raise IncompleteWfsResponseError(url, matched, len(parsed["units"]))
    return parsed


def _to_boundary(
    unit: RawAdministrativeUnit, transformer: Transformer, provenance: Provenance
) -> MunicipalBoundary:
    if unit["has_interior"]:
        raise MunicipalBoundaryUnusableError(
            f"el municipio {unit['ine_code']} tiene huecos (gml:interior), no modelados"
        )
    if not unit["rings"]:
        raise MunicipalBoundaryUnusableError(f"el municipio {unit['ine_code']} no tiene geometría")
    rings = []
    for ring in unit["rings"]:
        lats = [lat for lat, _ in ring]
        lons = [lon for _, lon in ring]
        # Sin always_xy: la entrada es (lat, lon), como vienen en posList.
        eastings, northings = transformer.transform(lats, lons)
        rings.append(tuple(zip(eastings, northings, strict=True)))
    return MunicipalBoundary(
        ine_code=unit["ine_code"],
        name=unit["name"],
        geometry=Geometry(rings=tuple(rings), srid=TARGET_SRID),
        provenance=provenance,
    )
