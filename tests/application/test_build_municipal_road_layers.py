"""Caso de uso de la capa de camino actual (historia #27). Geometrías SINTÉTICAS."""

from collections.abc import Sequence
from datetime import date

import pytest

from parcel_intel.application.build_municipal_road_layers import (
    BBOX_MARGIN_M,
    BuildMunicipalRoadLayersUseCase,
)
from parcel_intel.domain.geometry import Geometry, LineGeometry, MultiLineGeometry
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.road_segment import RoadQueryResult, RoadSegment, RoadSurface
from parcel_intel.ports.errors import RoadNetworkError

_PROV = Provenance(
    source="ign-roadlink", url="https://example.org/q", retrieved_at=date(2026, 11, 26)
)


def _rect(x0: float, y0: float, x1: float, y1: float, srid: int = 25830) -> Geometry:
    return Geometry(rings=(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)),), srid=srid)


def _boundary(ine: str, geometry: Geometry) -> MunicipalBoundary:
    return MunicipalBoundary(ine, f"M{ine}", geometry, _PROV)


def _road(
    segment_id: int, *points: tuple[float, float], srid: int = 25830, surface: str = "unpaved"
) -> RoadSegment:
    return RoadSegment(segment_id, None, surface, True, LineGeometry(points, srid), _PROV)


class _Boundaries:
    def __init__(self, boundaries: list[MunicipalBoundary]) -> None:
        self._boundaries = boundaries

    def get_municipal_boundaries(self, ine_codes: Sequence[str]) -> list[MunicipalBoundary]:
        return self._boundaries


class _Roads:
    def __init__(self, by_ine: dict[str, list[RoadSegment] | Exception]) -> None:
        self._by_ine = by_ine
        self.margins: list[float] = []
        self.surfaces: list[RoadSurface] = []

    def get_nearby_unpaved_roads(self, geometry: Geometry, margin_m: float) -> list[RoadSegment]:
        return list(self.query_unpaved_roads(geometry, margin_m).segments)

    def query_unpaved_roads(self, geometry: Geometry, margin_m: float) -> RoadQueryResult:
        return self.query_roads(geometry, margin_m, "unpaved")

    def query_roads(
        self, geometry: Geometry, margin_m: float, surface: RoadSurface
    ) -> RoadQueryResult:
        self.margins.append(margin_m)
        self.surfaces.append(surface)
        # Se identifica el municipio por la x mínima de su límite (cada uno en un x distinto).
        key = str(int(geometry.rings[0][0][0]))
        result = self._by_ine[key]
        if isinstance(result, Exception):
            raise result
        return RoadQueryResult(tuple(result), _PROV)


class _Clipper:
    """Recorte por x: basta para límites rectangulares alineados con los ejes."""

    def clip(self, subject: LineGeometry, boundary: Geometry) -> MultiLineGeometry:
        x0 = min(x for x, _ in boundary.rings[0])
        x1 = max(x for x, _ in boundary.rings[0])
        (ax, ay), (bx, by) = subject.points[0], subject.points[-1]
        lo, hi = max(min(ax, bx), x0), min(max(ax, bx), x1)
        if lo >= hi:
            return MultiLineGeometry((), subject.srid)
        slope = (by - ay) / (bx - ax)
        return MultiLineGeometry(
            lines=(((lo, ay + slope * (lo - ax)), (hi, ay + slope * (hi - ax))),), srid=subject.srid
        )


def _use_case(
    boundaries: list[MunicipalBoundary],
    by_ine: dict[str, list[RoadSegment] | Exception],
    surface: RoadSurface = "unpaved",
) -> tuple[BuildMunicipalRoadLayersUseCase, _Roads]:
    roads = _Roads(by_ine)
    use_case = BuildMunicipalRoadLayersUseCase(
        _Boundaries(boundaries), roads, _Clipper(), surface=surface
    )
    return use_case, roads


def test_por_defecto_pide_sin_asfaltar_y_la_capa_lo_declara() -> None:
    use_case, roads = _use_case([_boundary("A", _rect(0, 0, 10, 10))], {"0": []})

    layer = use_case.execute(("A",)).layers[0]

    assert roads.surfaces == ["unpaved"]
    assert layer.surface == "unpaved"


def test_la_superficie_pasa_al_port_y_a_la_capa() -> None:
    paved = _road(1, (1.0, 1.0), (2.0, 2.0), surface="paved")
    use_case, roads = _use_case(
        [_boundary("A", _rect(0, 0, 10, 10))], {"0": [paved]}, surface="paved"
    )

    batch = use_case.execute(("A",))

    assert roads.surfaces == ["paved"]
    assert batch.failures == ()
    assert batch.layers[0].surface == "paved"
    assert batch.layers[0].segments[0].source is paved


def test_un_tramo_de_otra_superficie_es_un_fallo_del_municipio() -> None:
    """SINTÉTICO: el port devuelve un tramo `unpaved` en una consulta `paved`."""
    boundaries = [_boundary("A", _rect(0, 0, 10, 10)), _boundary("B", _rect(10, 0, 20, 10))]
    use_case, _ = _use_case(
        boundaries,
        {
            "0": [_road(1, (1.0, 1.0), (2.0, 2.0), surface="unpaved")],
            "10": [_road(2, (11.0, 1.0), (12.0, 2.0), surface="paved")],
        },
        surface="paved",
    )

    batch = use_case.execute(("A", "B"))

    assert [layer.municipality.ine_code for layer in batch.layers] == ["B"]
    assert [f.ine_code for f in batch.failures] == ["A"]
    assert "'unpaved'" in batch.failures[0].reason
    assert "'paved'" in batch.failures[0].reason


def test_el_tramo_que_cruza_aparece_en_las_dos_capas_con_su_parte() -> None:
    west, east = _boundary("A", _rect(0, 0, 10, 10)), _boundary("B", _rect(10, 0, 20, 10))
    crossing = _road(1, (4.0, 5.0), (14.0, 5.0))
    use_case, roads = _use_case([west, east], {"0": [crossing], "10": [crossing]})

    batch = use_case.execute(("A", "B"))

    assert batch.failures == ()
    parts = {layer.municipality.ine_code: layer.segments[0] for layer in batch.layers}
    assert parts["A"].length_m == pytest.approx(6.0)
    assert parts["B"].length_m == pytest.approx(4.0)
    assert parts["A"].share_of_source == pytest.approx(0.6)
    assert parts["B"].share_of_source == pytest.approx(0.4)
    assert parts["A"].source is crossing  # el tramo original, sin tocar
    assert roads.margins == [BBOX_MARGIN_M, BBOX_MARGIN_M]


def test_un_tramo_de_un_vecino_que_no_toca_el_termino_se_descarta_y_el_orden_es_por_id() -> None:
    boundary = _boundary("A", _rect(0, 0, 10, 10))
    use_case, _ = _use_case(
        [boundary],
        {"0": [_road(9, (1.0, 1.0), (2.0, 2.0)), _road(3, (50.0, 1.0), (60.0, 2.0)),
               _road(2, (3.0, 1.0), (4.0, 2.0))]},
    )

    layer = use_case.execute(("A",)).layers[0]

    assert [p.source.segment_id for p in layer.segments] == [2, 9]
    assert layer.provenance is _PROV


def test_municipio_sin_tramos_da_capa_vacia_con_procedencia() -> None:
    use_case, _ = _use_case([_boundary("A", _rect(0, 0, 10, 10))], {"0": []})

    batch = use_case.execute(("A",))

    assert batch.layers[0].segments == ()
    assert batch.layers[0].provenance is _PROV
    assert batch.failures == ()


def test_un_fallo_en_un_municipio_no_detiene_el_lote() -> None:
    boundaries = [_boundary("A", _rect(0, 0, 10, 10)), _boundary("B", _rect(10, 0, 20, 10))]
    use_case, _ = _use_case(
        boundaries, {"0": RoadNetworkError("502"), "10": [_road(1, (11.0, 1.0), (12.0, 2.0))]}
    )

    batch = use_case.execute(("A", "B"))

    assert [layer.municipality.ine_code for layer in batch.layers] == ["B"]
    assert [(f.ine_code, f.name) for f in batch.failures] == [("A", "MA")]
    assert "RoadNetworkError" in batch.failures[0].reason
    assert "502" in batch.failures[0].reason


def test_el_lote_se_recupera_tras_un_fallo_con_el_mismo_caso_de_uso() -> None:
    boundary = _boundary("A", _rect(0, 0, 10, 10))
    flaky: dict[str, list[RoadSegment] | Exception] = {"0": RoadNetworkError("x")}
    use_case, _ = _use_case([boundary], flaky)

    assert use_case.execute(("A",)).failures
    flaky["0"] = [_road(1, (1.0, 1.0), (2.0, 2.0))]
    assert use_case.execute(("A",)).layers


def test_srid_distinto_de_25830_es_un_fallo_del_municipio_no_un_dato_silencioso() -> None:
    bad_boundary = _boundary("A", _rect(0, 0, 10, 10, srid=4258))
    bad_road = _road(1, (1.0, 1.0), (2.0, 2.0), srid=4258)
    use_case, _ = _use_case(
        [bad_boundary, _boundary("B", _rect(10, 0, 20, 10))],
        {"0": [], "10": [bad_road]},
    )

    batch = use_case.execute(("A", "B"))

    assert batch.layers == ()
    assert {f.ine_code for f in batch.failures} == {"A", "B"}
    assert all("25830" in f.reason for f in batch.failures)
