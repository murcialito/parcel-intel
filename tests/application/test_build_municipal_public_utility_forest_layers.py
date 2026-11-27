"""Caso de uso de la capa de montes de utilidad pública (historia #220). Datos SINTÉTICOS."""

from datetime import date

import pytest

from parcel_intel.application.build_municipal_public_utility_forest_layers import (
    BBOX_MARGIN_M,
    BuildMunicipalPublicUtilityForestLayersUseCase,
)
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.public_utility_forest import PublicUtilityForest

_PROV = Provenance(source="idem", url="https://example.org", retrieved_at=date(2026, 11, 27))


def _rect(x0: float, y0: float, x1: float, y1: float, srid: int = 25830) -> Geometry:
    return Geometry(rings=(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)),), srid=srid)


def _forest(code: str, name: str, geometry: Geometry) -> PublicUtilityForest:
    return PublicUtilityForest(code, name, "X", geometry, _PROV)


class _Boundaries:
    def __init__(self, boundaries: list[MunicipalBoundary]) -> None:
        self._boundaries = boundaries

    def get_municipal_boundaries(self, ine_codes: object) -> list[MunicipalBoundary]:
        return self._boundaries


class _Forests:
    def __init__(self, forests: list[PublicUtilityForest]) -> None:
        self._forests = forests
        self.margins: list[float] = []

    def get_nearby_public_utility_forests(
        self, geometry: Geometry, margin_m: float
    ) -> list[PublicUtilityForest]:
        self.margins.append(margin_m)
        return self._forests


class _Clipper:
    """Recorte por bbox: basta para rectángulos alineados con los ejes."""

    def clip(self, subject: Geometry, boundary: Geometry) -> Geometry:
        sx = [p[0] for p in subject.rings[0]]
        sy = [p[1] for p in subject.rings[0]]
        bx = [p[0] for p in boundary.rings[0]]
        by = [p[1] for p in boundary.rings[0]]
        x0, x1 = max(min(sx), min(bx)), min(max(sx), max(bx))
        y0, y1 = max(min(sy), min(by)), min(max(sy), max(by))
        if x0 >= x1 or y0 >= y1:
            return Geometry(rings=(), srid=subject.srid)
        return _rect(x0, y0, x1, y1, subject.srid)


def _boundary(geometry: Geometry) -> MunicipalBoundary:
    return MunicipalBoundary("00001", "X", geometry, _PROV)


def _use_case(
    boundary: MunicipalBoundary, forests: _Forests
) -> BuildMunicipalPublicUtilityForestLayersUseCase:
    return BuildMunicipalPublicUtilityForestLayersUseCase(
        _Boundaries([boundary]), forests, _Clipper()
    )


def test_recorta_ordena_y_descarta_los_montes_de_vecinos() -> None:
    forests = _Forests(
        [
            _forest("20", "B", _rect(0, 0, 20, 10)),  # cruza el borde: se recorta a 10 x 10
            _forest("10", "A", _rect(2, 2, 4, 4)),
            _forest("30", "Vecino", _rect(50, 50, 60, 60)),  # el bbox lo trae, no toca
        ]
    )

    (layer,) = _use_case(_boundary(_rect(0, 0, 10, 10)), forests).execute(["00001"])

    assert [f.source.forest_code for f in layer.forests] == ["10", "20"]
    assert [f.area_m2 for f in layer.forests] == [4.0, 100.0]
    assert forests.margins == [BBOX_MARGIN_M]


def test_municipio_sin_montes_da_capa_vacia_no_error() -> None:
    (layer,) = _use_case(_boundary(_rect(0, 0, 10, 10)), _Forests([])).execute(["00001"])

    assert layer.forests == ()


def test_srid_inesperado_del_limite_o_del_monte_es_un_error() -> None:
    with pytest.raises(ValueError, match="EPSG:4326"):
        _use_case(_boundary(_rect(0, 0, 1, 1, 4326)), _Forests([])).execute(["00001"])
    with pytest.raises(ValueError, match="EPSG:4326"):
        _use_case(
            _boundary(_rect(0, 0, 10, 10)), _Forests([_forest("1", "A", _rect(0, 0, 1, 1, 4326))])
        ).execute(["00001"])
