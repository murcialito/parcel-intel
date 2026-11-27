"""Escritor de la capa de caminos de Catastro (historia #160). Datos SINTÉTICOS."""

from dataclasses import replace
from datetime import date
from pathlib import Path

from parcel_intel.adapters.trail_layers import GeoJsonCadastralRoadWriter, GeoJsonTrailLayerReader
from parcel_intel.domain.cadastral_road import CadastralRoad, CadastralRoadLayer
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance, Redistribution

_PROVENANCE = Provenance(
    "catastro_wfs_cp",
    "https://example.invalid/wfs",
    date(2026, 11, 26),
    "licencia sintética",
    Redistribution.INTERNAL_ONLY,
)


def _road(reference: str, x: float) -> CadastralRoad:
    ring = ((x, 0.0), (x + 100.0, 0.0), (x + 100.0, 10.0), (x, 10.0), (x, 0.0))
    return CadastralRoad(
        cadastral_reference=reference,
        municipality_code="28043",
        polygon=991,
        parcel=9101,
        land_use_classes=("VT",),
        area_m2=1000.04,
        geometry=Geometry(rings=(ring,), srid=25830),
        provenance=_PROVENANCE,
        land_use_provenance=_PROVENANCE,
    )


def _layer(roads: tuple[CadastralRoad, ...]) -> CadastralRoadLayer:
    return CadastralRoadLayer("28043", (0, 0, 1, 1), roads, 1, len(roads), len(roads), (), ())


def test_escribe_y_el_lector_la_recupera_sin_referencias(tmp_path: Path) -> None:
    roads = (_road("28043A99109101", 0.0), _road("28043A99109102", 500.0))
    path = GeoJsonCadastralRoadWriter(tmp_path).write(_layer(roads), _PROVENANCE)
    assert "28043A" not in path.read_text(encoding="utf-8")
    layer = GeoJsonTrailLayerReader({"catastro_vt": tmp_path}).get_layer("catastro_vt", "28043")
    assert [t.identifier for t in layer.trails] == ["VT-0001", "VT-0002"]
    assert layer.provenance.redistribution is Redistribution.INTERNAL_ONLY


def test_capa_sin_caminos_se_escribe_vacia_y_es_legible(tmp_path: Path) -> None:
    GeoJsonCadastralRoadWriter(tmp_path).write(_layer(()), _PROVENANCE)
    layer = GeoJsonTrailLayerReader({"catastro_vt": tmp_path}).get_layer("catastro_vt", "28043")
    assert layer.trails == ()


def test_es_determinista_y_no_deja_temporales(tmp_path: Path) -> None:
    layer = _layer((_road("28043A99109101", 0.0),))
    writer = GeoJsonCadastralRoadWriter(tmp_path)
    first = writer.write(layer, _PROVENANCE).read_bytes()
    assert writer.write(replace(layer), _PROVENANCE).read_bytes() == first
    assert [p.name for p in tmp_path.iterdir()] == ["28043.geojson"]
