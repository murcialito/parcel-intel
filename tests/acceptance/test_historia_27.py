"""Historia #27: capa de camino actual por municipio (lote)."""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from shapely.geometry import LineString, Polygon

from parcel_intel.adapters.ign_admin_units import IgnAdministrativeUnitsAdapter
from parcel_intel.adapters.road_layer_files import GeoJsonRoadLayerWriter
from parcel_intel.adapters.road_network.adapter import RoadNetworkAdapter
from parcel_intel.adapters.shapely_geometry import ShapelyLineClipper
from parcel_intel.application.build_municipal_road_layers import BuildMunicipalRoadLayersUseCase
from parcel_intel.cli import main as cli
from parcel_intel.cli.main import (
    AMBITO_HITO_BBOX_ETRS89,
    AMBITO_HITO_INE,
    build_municipal_road_layers,
)
from parcel_intel.domain.geometry import MultiLineGeometry, multiline_length
from parcel_intel.domain.municipal_road_layer import MunicipalRoadLayer, MunicipalRoadLayerBatch
from parcel_intel.domain.municipality import MunicipalBoundary
from tests.municipal_layer_fixtures import FakeIgnHttp, municipal_boundaries
from tests.road_layer_fixtures import (
    VACIO_FIXTURE,
    NoNetwork,
    prepare_road_cache,
    recorte_for,
)

pytestmark = pytest.mark.acceptance

D1 = date(2026, 11, 26)
D2 = date(2027, 1, 15)
ATTRIBUTION = "Obra derivada de red de transporte IGN CC-BY 4.0 ign.es"
NOTICE = "cartografía informativa"

Prepared = tuple[Path, MunicipalRoadLayerBatch]


@pytest.fixture(scope="module")
def prepared(tmp_path_factory: pytest.TempPathFactory) -> Prepared:
    cache_dir = tmp_path_factory.mktemp("raw")
    return cache_dir, prepare_road_cache(cache_dir, D1)


def _layer(batch: MunicipalRoadLayerBatch, ine: str) -> MunicipalRoadLayer:
    return next(layer for layer in batch.layers if layer.municipality.ine_code == ine)


def _boundary(ine: str) -> MunicipalBoundary:
    return next(b for b in municipal_boundaries() if b.ine_code == ine)


def _written(batch: MunicipalRoadLayerBatch, directory: Path) -> dict[str, dict[str, Any]]:
    writer = GeoJsonRoadLayerWriter(directory)
    return {
        layer.municipality.ine_code: json.loads(writer.write(layer).read_text(encoding="utf-8"))
        for layer in batch.layers
    }


def test_ca1_solo_unpaved_dentro_del_termino_en_25830(prepared: Prepared) -> None:
    """Dado el límite de un municipio y los tramos de roadlink de su entorno (fixtures), cuando
    se genera la capa, entonces solo contiene tramos `unpaved` y cada geometría queda dentro del
    término, en EPSG:25830."""
    _, batch = prepared
    # Sintético: se añade a la respuesta real un tramo asfaltado, que no puede entrar.
    real = json.loads(recorte_for("28043").read_text(encoding="utf-8"))
    paved = json.loads(json.dumps(real["features"][0]))
    paved["properties"]["surfacecategory"] = "paved"
    paved["properties"]["id_tramo"] = 1
    real["features"].append(paved)
    real["numberMatched"] = real["numberReturned"] = len(real["features"])
    body = json.dumps(real).encode()
    boundary_adapter = IgnAdministrativeUnitsAdapter(
        AMBITO_HITO_BBOX_ETRS89, http_get=FakeIgnHttp()
    )
    use_case = BuildMunicipalRoadLayersUseCase(
        boundaries=boundary_adapter,
        roads=RoadNetworkAdapter(http_get=lambda url, params: body),
        clipper=ShapelyLineClipper(),
    )
    synthetic = use_case.execute(("28043",))

    for layer in (_layer(batch, "28043"), synthetic.layers[0]):
        assert layer.segments
        assert all(p.source.surface_category == "unpaved" for p in layer.segments)
        assert 1 not in {p.source.segment_id for p in layer.segments}
        boundary = _boundary("28043").geometry
        polygon = Polygon(boundary.rings[0]).buffer(1e-6)
        for piece in layer.segments:
            assert piece.geometry.srid == 25830
            assert piece.geometry.lines
            for line in piece.geometry.lines:
                assert polygon.covers(LineString(line))


def test_ca2_tramo_que_cruza_el_limite_se_reparte_sin_perder_longitud(prepared: Prepared) -> None:
    """Dado un tramo que cruza el límite entre dos municipios, cuando se generan ambas capas,
    entonces cada una recibe solo su parte y la suma de longitudes coincide con la original
    (tolerancia 1 m). Casos reales: 280430189746 (Colmenar/Chinchón, 239,19 + 272,14 m) y el
    multi-parte 281700231594 (Chinchón/Villaconejos, 3 + 2 partes)."""
    _, batch = prepared
    casos = {
        "280430189746": ({"28043", "28052"}, 511.323),
        "281700231594": ({"28052", "28170"}, 221.792),
    }
    for segment_id, (codes, original_length) in casos.items():
        pieces = {
            layer.municipality.ine_code: piece
            for layer in batch.layers
            for piece in layer.segments
            if piece.source.segment_id == int(segment_id)
        }
        assert set(pieces) == codes
        source = next(iter(pieces.values())).source.geometry
        original = multiline_length(MultiLineGeometry(lines=(source.points,), srid=25830))
        assert original == pytest.approx(original_length, abs=0.01)
        assert sum(p.length_m for p in pieces.values()) == pytest.approx(original, abs=1.0)
        for ine, piece in pieces.items():
            assert piece.geometry.srid == 25830
            polygon = Polygon(_boundary(ine).geometry.rings[0]).buffer(1e-6)
            assert all(polygon.covers(LineString(line)) for line in piece.geometry.lines)
    multi = next(
        p
        for p in _layer(batch, "28052").segments
        if p.source.segment_id == 281700231594
    )
    assert len(multi.geometry.lines) == 3


def test_ca3_municipio_sin_tramos_produce_fichero_valido_con_cero_elementos(
    tmp_path: Path,
) -> None:
    """Dado un municipio sin tramos sin asfaltar, cuando se genera la capa, entonces produce un
    fichero válido con cero elementos, no un error."""
    vacio = VACIO_FIXTURE.read_bytes()
    use_case = BuildMunicipalRoadLayersUseCase(
        boundaries=IgnAdministrativeUnitsAdapter(
            AMBITO_HITO_BBOX_ETRS89, http_get=FakeIgnHttp()
        ),
        roads=RoadNetworkAdapter(http_get=lambda url, params: vacio, today=lambda: D1),
        clipper=ShapelyLineClipper(),
    )

    batch = use_case.execute(("28043",))

    assert batch.failures == ()
    written = _written(batch, tmp_path)["28043"]
    assert written["type"] == "FeatureCollection"
    assert written["features"] == []
    properties = written["properties"]
    assert isinstance(properties, dict)
    assert properties["municipio"] == "28043"
    assert properties["procedencia"]["fecha_descarga"] == D1.isoformat()


def test_ca4_elementos_con_procedencia_y_capa_con_atribucion_y_aviso(
    prepared: Prepared, tmp_path: Path
) -> None:
    """Dada la capa generada, entonces cada elemento lleva `id_tramo`, `fecha_alta`,
    `fictitious` y su `Provenance` (fuente, URL de la consulta, fecha de descarga, licencia), y
    la capa lleva la atribución "Obra derivada de red de transporte IGN CC-BY 4.0 ign.es" y el
    aviso "cartografía informativa"."""
    _, batch = prepared
    files = _written(batch, tmp_path)

    assert set(files) == set(AMBITO_HITO_INE)
    for ine, collection in files.items():
        properties = collection["properties"]
        assert isinstance(properties, dict)
        assert properties["atribucion"] == ATTRIBUTION
        assert properties["aviso"] == NOTICE
        assert properties["fuente"] == "ign_red_transporte"
        assert properties["municipio"] == ine
        assert collection["crs"] == {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::25830"},
        }
        features = collection["features"]
        assert isinstance(features, list)
        assert features
        for feature in features:
            props = feature["properties"]
            assert isinstance(props["id_tramo"], int)
            assert str(props["id_tramo"]) == feature["id"]
            assert "fecha_alta" in props
            assert isinstance(props["fictitious"], bool)
            procedencia = props["procedencia"]
            assert procedencia["fuente"] == "ign-roadlink"
            assert procedencia["url"].startswith("https://api-features.idee.es/collections/roadlink")
            assert "bbox=" in procedencia["url"]
            assert procedencia["fecha_descarga"] == D1.isoformat()
            assert "CC BY 4.0" in procedencia["licencia"]


def test_ca5_se_conserva_el_indicador_fictitious(prepared: Prepared, tmp_path: Path) -> None:
    """Dado un tramo con `fictitious="true"`, entonces se conserva el indicador en el fichero.
    (Real: casi todos los tramos sin asfaltar del ámbito son ficticios; Villaconejos trae además
    tramos con `fictitious="false"` (5 en la respuesta completa, 3 en el recorte), que también
    se conservan.)"""
    _, batch = prepared
    files = _written(batch, tmp_path)

    flags = {
        feature["properties"]["fictitious"]
        for collection in files.values()
        for feature in collection["features"]
    }
    assert flags == {True, False}
    villaconejos = files["28170"]["features"]
    assert sum(f["properties"]["fictitious"] is False for f in villaconejos) == 3
    assert sum(f["properties"]["fictitious"] is True for f in villaconejos) == 9


def test_ca6_sin_red_el_fichero_es_identico_byte_a_byte(
    prepared: Prepared, tmp_path: Path
) -> None:
    """Dada la caché local de las respuestas crudas, cuando se regenera la capa sin red,
    entonces el fichero resultante es idéntico byte a byte."""
    cache_dir, first = prepared
    first_dir = tmp_path / "primera"
    second_dir = tmp_path / "segunda"
    for batch, directory in ((first, first_dir),):
        writer = GeoJsonRoadLayerWriter(directory)
        for layer in batch.layers:
            writer.write(layer)

    second = build_municipal_road_layers(
        cache_dir,
        offline=True,
        ign_http_get=NoNetwork(),
        roadlink_http_get=NoNetwork(),
        today=lambda: D2,  # otra fecha: la procedencia es la de la descarga original
        sleep=lambda _: None,
    )
    second_writer = GeoJsonRoadLayerWriter(second_dir)
    for layer in second.layers:
        second_writer.write(layer)

    assert second.failures == ()
    names = sorted(p.name for p in first_dir.iterdir())
    assert names == sorted(f"{ine}.geojson" for ine in AMBITO_HITO_INE)
    for name in names:
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes()
    assert D2.isoformat() not in (second_dir / "28043.geojson").read_text(encoding="utf-8")


def test_ca7_un_municipio_que_falla_se_informa_y_los_demas_se_generan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dado el lote de los 7 municipios, cuando falla la consulta de uno, entonces se informa
    del fallo de ese municipio y los demás se generan (el lote no se queda a medias en
    silencio)."""
    cache_dir = tmp_path / "raw"
    out_dir = tmp_path / "derived"
    batch = prepare_road_cache(cache_dir, D1, fail_for=("28052",))

    assert [f.ine_code for f in batch.failures] == ["28052"]
    assert batch.failures[0].name == "Chinchón"
    assert "sin conexión simulada" in batch.failures[0].reason
    assert {layer.municipality.ine_code for layer in batch.layers} == set(AMBITO_HITO_INE) - {
        "28052"
    }

    # El comando: escribe los 6 ficheros, avisa por stderr del fallo y sale con código 1.
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "camino-actual-municipios",
            "--sin-red",
            "--cache",
            str(cache_dir),
            "--salida",
            str(out_dir),
        ],
    )
    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert "FALLO 28052 Chinchón" in captured.err
    assert sorted(p.name for p in out_dir.iterdir()) == sorted(
        f"{ine}.geojson" for ine in AMBITO_HITO_INE if ine != "28052"
    )
    assert "28043 Colmenar de Oreja" in captured.out


@pytest.mark.integration
@pytest.mark.fuera_de_ci  # api-features.idee.es agota el tiempo (30 s) desde GitHub Actions
def test_ca8_integracion_los_7_municipios_reales(tmp_path: Path) -> None:
    """[integración] Dados los 7 municipios reales, cuando se ejecuta el lote, entonces cada uno
    produce su fichero y Colmenar contiene tramos sin asfaltar."""
    batch = build_municipal_road_layers(tmp_path / "raw", offline=False)
    writer = GeoJsonRoadLayerWriter(tmp_path / "derived")
    paths = [writer.write(layer) for layer in batch.layers]

    assert batch.failures == ()
    assert sorted(p.name for p in paths) == sorted(f"{ine}.geojson" for ine in AMBITO_HITO_INE)
    colmenar = json.loads((tmp_path / "derived" / "28043.geojson").read_text(encoding="utf-8"))
    assert len(colmenar["features"]) > 0
