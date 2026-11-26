from datetime import date

import pytest

from parcel_intel.application.build_municipal_livestock_trail_layers import (
    BBOX_MARGIN_M,
    BuildMunicipalLivestockTrailLayersUseCase,
)
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.livestock_trail import LivestockTrail
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance

_PROV = Provenance(source="idem", url="https://example.org", retrieved_at=date(2026, 11, 26))


def _rect(x0: float, y0: float, x1: float, y1: float, srid: int = 25830) -> Geometry:
    return Geometry(rings=(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)),), srid=srid)


def _trail(code: str, name: str, geometry: Geometry) -> LivestockTrail:
    return LivestockTrail("Vereda", name, "00001", "X", code, 1.0, 1.0, geometry, _PROV)


class _Boundaries:
    def __init__(self, boundaries: list[MunicipalBoundary]) -> None:
        self._boundaries = boundaries

    def get_municipal_boundaries(self, ine_codes: object) -> list[MunicipalBoundary]:
        return self._boundaries


class _Trails:
    def __init__(self, trails: list[LivestockTrail]) -> None:
        self._trails = trails
        self.margins: list[float] = []

    def get_nearby_livestock_trails(
        self, geometry: Geometry, margin_m: float
    ) -> list[LivestockTrail]:
        self.margins.append(margin_m)
        return self._trails


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


def _use_case(
    boundaries: list[MunicipalBoundary], trails: list[LivestockTrail]
) -> tuple[BuildMunicipalLivestockTrailLayersUseCase, _Trails]:
    port = _Trails(trails)
    use_case = BuildMunicipalLivestockTrailLayersUseCase(
        _Boundaries(boundaries), port, _Clipper()
    )
    return use_case, port


def _boundary(code: str, geometry: Geometry) -> MunicipalBoundary:
    return MunicipalBoundary(code, f"M{code}", geometry, _PROV)


def test_una_capa_por_limite_en_orden_y_vacia_si_no_cae_nada() -> None:
    use_case, _ = _use_case(
        [_boundary("A", _rect(0, 0, 10, 10)), _boundary("B", _rect(100, 100, 110, 110))],
        [_trail("T1", "t", _rect(2, 2, 4, 4))],
    )

    first, second = use_case.execute(("A", "B"))

    assert [len(first.trails), len(second.trails)] == [1, 0]
    assert first.municipality.ine_code == "A"


def test_pide_los_tramos_con_margen_de_2_m() -> None:
    use_case, port = _use_case([_boundary("A", _rect(0, 0, 10, 10))], [])

    use_case.execute(("A",))

    assert port.margins == [BBOX_MARGIN_M] == [2.0]


def test_pieza_con_area_y_proporcion_sin_umbral_de_astillas() -> None:
    use_case, _ = _use_case(
        [_boundary("A", _rect(0, 0, 10, 10))],
        [_trail("T1", "astilla", _rect(9.99, 0, 20, 10))],  # 0.1 m² de 110
    )

    (layer,) = use_case.execute(("A",))

    (piece,) = layer.trails
    assert piece.area_m2 == pytest.approx(0.1)
    assert piece.share_of_source == pytest.approx(0.1 / 100.1)
    assert piece.source.area_m2 == 1.0  # el del tramo de IDEM, intacto


def test_orden_por_codigo_nombre_y_area_descendente() -> None:
    use_case, _ = _use_case(
        [_boundary("A", _rect(0, 0, 100, 100))],
        [
            _trail("B", "x", _rect(0, 0, 1, 1)),
            _trail("A", "y", _rect(0, 0, 1, 1)),
            _trail("A", "x", _rect(0, 0, 1, 1)),
            _trail("A", "x", _rect(0, 0, 5, 5)),
        ],
    )

    (layer,) = use_case.execute(("A",))

    assert [(p.source.trail_code, p.source.name, p.area_m2) for p in layer.trails] == [
        ("A", "x", 25.0),
        ("A", "x", 1.0),
        ("A", "y", 1.0),
        ("B", "x", 1.0),
    ]


def test_limite_en_otro_srid_es_value_error() -> None:
    use_case, _ = _use_case([_boundary("A", _rect(0, 0, 1, 1, srid=4258))], [])

    with pytest.raises(ValueError, match="EPSG:4258"):
        use_case.execute(("A",))


def test_tramo_en_otro_srid_es_value_error() -> None:
    use_case, _ = _use_case(
        [_boundary("A", _rect(0, 0, 10, 10))], [_trail("T", "t", _rect(0, 0, 1, 1, srid=4258))]
    )

    with pytest.raises(ValueError, match="T"):
        use_case.execute(("A",))
