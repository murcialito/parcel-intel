"""Historia #84: `publicar-capas` publica vías pecuarias y camino actual en `site/datos/`."""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pyproj import Transformer

from parcel_intel.adapters.road_layer_files import (
    GeoJsonLivestockTrailLayerWriter,
    GeoJsonRoadLayerWriter,
)
from parcel_intel.adapters.trail_layers import GeoJsonTrailLayerReader, TrailLayerFormatError
from parcel_intel.application.publish_layers import PublishLayersUseCase
from parcel_intel.cli import main as cli
from parcel_intel.cli.main import build_municipal_layers, build_municipal_road_layers
from parcel_intel.domain.discrepancy_report import TrailLayer
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.publication import NotRedistributableError, PublishableLayer
from parcel_intel.domain.published_layers import PublishedFile, TrailLayerPublication
from parcel_intel.domain.trail import SourceKind, Trail
from tests.fixtures.published_layers import (
    line_feature,
    polygon_feature,
    provenance,
    small_pair,
    square,
    synthetic_layer,
    write_real_derived_layers,
    zigzag,
)
from tests.municipal_layer_fixtures import prepare_cache
from tests.road_layer_fixtures import prepare_road_cache

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
NOTICE = ROOT / "NOTICE"
SITE_INDEX_HTML = ROOT / "site" / "index.html"
LAYERS = ("vias_pecuarias", "camino_actual")
VP: SourceKind = "via_pecuaria_oficial"
RT: SourceKind = "ign_red_transporte"

# bbox del ámbito (CA2): longitud entre -3,62 y -3,15 y latitud entre 39,98 y 40,22.
LON_MIN, LON_MAX, LAT_MIN, LAT_MAX = -3.62, -3.15, 39.98, 40.22

_TO_METRIC = Transformer.from_crs("EPSG:4326", "EPSG:25830", always_xy=True)


def _load_construir_sitio() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "construir_sitio", ROOT / "scripts" / "construir_sitio.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


construir_sitio = _load_construir_sitio()


@pytest.fixture(scope="module")
def real_derived(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Capas derivadas reales de los 7 municipios (fixtures grabadas, escritores reales)."""
    base = tmp_path_factory.mktemp("real")
    write_real_derived_layers(base / "derived", base / "raw")
    return base / "derived"


def _run(argv: list[str]) -> int:
    old = sys.argv
    sys.argv = ["parcel_intel.cli.main", *argv]
    try:
        with pytest.raises(SystemExit) as exit_info:
            cli.main()
    finally:
        sys.argv = old
    code = exit_info.value.code
    assert isinstance(code, int)
    return code


def _publish(entrada: Path, salida: Path, *codes: str, extra: tuple[str, ...] = ()) -> int:
    argv = ["publicar-capas", "--entrada", str(entrada), "--salida", str(salida)]
    for code in codes:
        argv += ["--municipio", code]
    return _run([*argv, *extra])


def _load(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _snapshot(directory: Path) -> dict[str, bytes]:
    if not directory.exists():
        return {}
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _positions(value: Any) -> list[tuple[float, float]]:
    if value and isinstance(value[0], int | float):
        return [(float(value[0]), float(value[1]))]
    return [position for item in value for position in _positions(item)]


def _reader(derived: Path) -> GeoJsonTrailLayerReader:
    return GeoJsonTrailLayerReader({VP: derived / "vias_pecuarias", RT: derived / "camino_actual"})


def test_ca1_publica_las_dos_capas_con_su_procedencia(real_derived: Path, tmp_path: Path) -> None:
    """Dado `data/derived/vias_pecuarias/28043.geojson` y `data/derived/camino_actual/28043.geojson`
    con licencia redistribuible, cuando se ejecuta `publicar-capas --municipio 28043`, entonces
    existen `site/datos/vias_pecuarias/28043.geojson` y `site/datos/camino_actual/28043.geojson`,
    cada uno con su `<fichero>.procedencia.json`."""
    salida = tmp_path / "datos"

    assert _publish(real_derived, salida, "28043") == 0

    for layer_id in LAYERS:
        assert (salida / layer_id / "28043.geojson").is_file()
        assert (salida / layer_id / "28043.geojson.procedencia.json").is_file()


def test_ca2_epsg4326_mismas_features_id_y_propiedades_publicas(
    real_derived: Path, tmp_path: Path
) -> None:
    """Dado un fichero publicado, cuando se lee, entonces su CRS es EPSG:4326 (lon/lat: longitud
    entre -3,62 y -3,15 y latitud entre 39,98 y 40,22, el bbox del ámbito; el GeoJSON no declara
    `crs`), el número de features coincide con el de entrada y cada feature conserva su `id` y sus
    propiedades públicas `nombre`, `tipo`, `fecha_dato` y `procedencia` (con valor `null` si la
    fuente no lo da). Un test ida y vuelta (4326→25830) de un punto real de la fixture difiere del
    original menos de 0,15 m (redondeo a 6 decimales)."""
    salida = tmp_path / "datos"
    assert _publish(real_derived, salida, "28043") == 0
    reader = _reader(real_derived)

    for layer_id, source in (("vias_pecuarias", VP), ("camino_actual", RT)):
        published = _load(salida / layer_id / "28043.geojson")
        layer = reader.get_layer(source, "28043")
        assert "crs" not in published
        assert len(published["features"]) == len(layer.trails) > 0
        for feature, trail in zip(published["features"], layer.trails, strict=True):
            assert feature["id"] == trail.identifier
            props = feature["properties"]
            assert set(props) == {"nombre", "tipo", "fecha_dato", "procedencia"}
            assert props["nombre"] == trail.name
            assert props["tipo"] == trail.trail_type
            expected_date = trail.data_date.isoformat() if trail.data_date else None
            assert props["fecha_dato"] == expected_date
            assert props["procedencia"] == {
                "fuente": trail.provenance.source,
                "url": trail.provenance.url,
                "fecha_descarga": trail.provenance.retrieved_at.isoformat(),
                "licencia": trail.provenance.license,
                "redistribucion": "publicable",
            }
            for lon, lat in _positions(feature["geometry"]["coordinates"]):
                assert LON_MIN <= lon <= LON_MAX
                assert LAT_MIN <= lat <= LAT_MAX

        # Ida y vuelta de un punto real: el primero de la primera feature.
        geometry = layer.trails[0].geometry
        original = geometry.rings[0][0] if isinstance(geometry, Geometry) else geometry.lines[0][0]
        lon, lat = _positions(published["features"][0]["geometry"]["coordinates"])[0]
        x, y = _TO_METRIC.transform(lon, lat)
        assert ((x - original[0]) ** 2 + (y - original[1]) ** 2) ** 0.5 < 0.15

    # Vías pecuarias de IDEM traen nombre y tipo; camino actual no (null).
    vias = _load(salida / "vias_pecuarias" / "28043.geojson")["features"]
    assert all(f["properties"]["nombre"] and f["properties"]["tipo"] for f in vias)
    caminos = _load(salida / "camino_actual" / "28043.geojson")["features"]
    assert all(f["properties"]["nombre"] is None for f in caminos)
    assert all(f["properties"]["tipo"] is None for f in caminos)


def test_ca3_procedencia_valida_para_construir_sitio_y_atribucion_de_notice(
    real_derived: Path, tmp_path: Path
) -> None:
    """Dado un `.procedencia.json` generado, cuando se valida con `scripts/construir_sitio.py`,
    entonces pasa; contiene `fuente`, `url`, `fecha_descarga`, `licencia` y
    `redistribucion: "publicable"`, y además `atribucion` (literal de `NOTICE`), `aviso`
    (cartografía informativa), `capa`, `municipio`, `procedencia_limite` y `transformacion` (CRS
    de origen y destino, decimales y simplificación o `null`). Un test comprueba que `atribucion`
    aparece tal cual en `NOTICE`."""
    salida = tmp_path / "datos"
    assert _publish(real_derived, salida, "28043") == 0
    notice = NOTICE.read_text(encoding="utf-8")

    for layer_id in LAYERS:
        path = salida / layer_id / "28043.geojson.procedencia.json"
        assert construir_sitio._check_provenance(path) == []
        sidecar = _load(path)
        assert set(sidecar) == {
            "fuente",
            "url",
            "fecha_descarga",
            "licencia",
            "redistribucion",
            "atribucion",
            "aviso",
            "capa",
            "municipio",
            "procedencia_limite",
            "transformacion",
        }
        assert sidecar["redistribucion"] == "publicable"
        assert f"`{sidecar['atribucion']}`" in notice
        assert sidecar["aviso"].startswith("cartografía informativa")
        assert sidecar["capa"] == layer_id
        assert sidecar["municipio"] == "28043"
        assert set(sidecar["procedencia_limite"]) == {"fuente", "url", "fecha_descarga", "licencia"}
        assert sidecar["procedencia_limite"]["fuente"] == "ign_unidades_administrativas"
        assert sidecar["transformacion"] == {
            "crs_origen": "EPSG:25830",
            "crs_destino": "EPSG:4326",
            "decimales": 6,
            "simplificacion": None,
        }
    assert (
        _load(salida / "camino_actual" / "28043.geojson.procedencia.json")["atribucion"]
        == "Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional"
    )


@pytest.mark.parametrize(
    ("caso", "coleccion", "feature"),
    [
        ("marca ausente en la colección", None, "publicable"),
        ("solo_uso_interno en la colección", "solo_uso_interno", "publicable"),
        ("solo_uso_interno en una feature", "publicable", "solo_uso_interno"),
        ("marca ausente en una feature", "publicable", None),
    ],
)
def test_ca4_capa_no_redistribuible_sale_con_1_y_no_escribe_nada(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caso: str,
    coleccion: str | None,
    feature: str | None,
) -> None:
    """Dada una capa cuya procedencia no es redistribuible (marca ausente o `solo_uso_interno`,
    en la colección o en cualquier feature), cuando se ejecuta `publicar-capas`, entonces el
    comando sale con código 1, nombra la capa y el municipio, sugiere regenerar la capa
    derivada, y **no escribe nada** en `site/datos/` en esa ejecución (ni de esa capa ni de las
    demás pedidas; tampoco borra lo ya publicado)."""
    derived = tmp_path / "derived"
    salida = tmp_path / "datos"
    # Lo ya publicado de otro municipio (sintético) no se toca.
    small_pair(derived, "28998", "Ya publicado")
    assert _publish(derived, salida, "28998") == 0
    before = _snapshot(salida)
    capsys.readouterr()

    small_pair(derived, "28997")  # camino actual válido, pedido en la misma ejecución
    synthetic_layer(
        derived,
        "vias_pecuarias",
        "28997",
        [
            polygon_feature("S1", [square(0, 0)], procedencia=provenance("vias_pecuarias")),
            polygon_feature(
                "S2", [square(50, 0)], procedencia=provenance("vias_pecuarias", feature)
            ),
        ],
        redistribucion=coleccion,
    )

    assert _publish(derived, salida, "28997", "28998") == 1, caso

    err = capsys.readouterr().err
    assert "vias_pecuarias 28997" in err
    assert "no redistribuible" in err
    assert "vias-pecuarias-municipios --sin-red" in err
    assert _snapshot(salida) == before


def test_ca5_toda_publicacion_pasa_por_publishable_layer(tmp_path: Path) -> None:
    """Dado el flujo completo, entonces toda publicación pasa por `PublishableLayer`: un test
    demuestra que un elemento `INTERNAL_ONLY` lanza `NotRedistributableError` antes de escribir
    ningún fichero, y otro que una capa **sin features** cuya procedencia de colección es
    `INTERNAL_ONLY` también la lanza."""
    public = Provenance(
        "idem", "https://example.invalid", date(2026, 11, 26), "CC BY 4.0", Redistribution.PUBLIC
    )
    internal = Provenance("idem", "https://example.invalid", date(2026, 11, 26), "CC BY 4.0")
    trail = Trail(
        identifier="S1",
        source=VP,
        role="via",
        name=None,
        trail_type=None,
        municipality_code="28997",
        geometry=Geometry(rings=(tuple((x, y) for x, y in square(0, 0)),), srid=25830),
        provenance=internal,
        data_date=None,
        character="sintética",
    )

    with pytest.raises(NotRedistributableError):
        PublishableLayer[Trail](
            name="vias_pecuarias/28997", items=(trail,), layer_provenance=public
        )
    with pytest.raises(NotRedistributableError):
        PublishableLayer[Trail](name="vias_pecuarias/28997", items=(), layer_provenance=internal)

    # En el flujo completo, el sink (que solo acepta `TrailLayerPublication`, construida sobre
    # un `PublishableLayer`) no llega a llamarse: nada se escribe.
    class _Layers:
        def get_layer(self, source: SourceKind, municipality_code: str) -> TrailLayer:
            if source == VP:
                return TrailLayer(source, municipality_code, public, (trail,), "Sintético")
            return TrailLayer(source, municipality_code, internal, (), "Sintético")

    calls: list[tuple[TrailLayerPublication, ...]] = []

    class _Sink:
        def publish(self, publications: Any) -> tuple[PublishedFile, ...]:
            calls.append(tuple(publications))
            return ()

    result = PublishLayersUseCase(_Layers(), _Sink()).execute(["28997"])

    assert calls == []
    assert [f.layer_id for f in result.failures] == ["vias_pecuarias", "camino_actual"]
    assert all(f.reason.startswith("no redistribuible") for f in result.failures)


def test_ca6_capa_inexistente_o_corrupta_sale_con_1_sin_tocar_nada(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dada una capa de entrada inexistente para un municipio, cuando se ejecuta
    `publicar-capas`, entonces se informa "sin capa" y sale con 1 sin tocar `site/datos/` (un
    fichero corrupto es un fallo, nunca "ausente": también sale con 1 y nombra el fichero)."""
    derived = tmp_path / "derived"
    salida = tmp_path / "datos"
    small_pair(derived, "28998")
    assert _publish(derived, salida, "28998") == 0
    before = _snapshot(salida)
    capsys.readouterr()

    # Sin capa de camino actual para 28997.
    synthetic_layer(
        derived,
        "vias_pecuarias",
        "28997",
        [polygon_feature("S1", [square(0, 0)], procedencia=provenance("vias_pecuarias"))],
    )
    assert _publish(derived, salida, "28997") == 1
    err = capsys.readouterr().err
    assert "camino_actual 28997" in err
    assert "sin capa" in err
    assert _snapshot(salida) == before

    # Fichero corrupto.
    corrupt = derived / "camino_actual" / "28997.geojson"
    corrupt.write_text("{no es json", encoding="utf-8")
    assert _publish(derived, salida, "28997") == 1
    err = capsys.readouterr().err
    assert str(corrupt) in err
    assert "sin capa" not in err
    assert _snapshot(salida) == before


def test_ca7_dos_ejecuciones_seguidas_son_identicas_byte_a_byte(
    real_derived: Path, tmp_path: Path
) -> None:
    """Dados dos ejecuciones seguidas con las mismas entradas, entonces los ficheros de salida
    (capas, procedencias e índice) son idénticos byte a byte (serialización determinista, sin
    fecha de generación)."""
    first, second = tmp_path / "a", tmp_path / "b"

    assert _publish(real_derived, first, "28043", "28170") == 0
    snapshot = _snapshot(first)
    assert _publish(real_derived, first, "28043", "28170") == 0
    assert _publish(real_derived, second, "28043", "28170") == 0

    assert _snapshot(first) == snapshot == _snapshot(second)
    assert {"indice.json", "indice.json.procedencia.json"} <= set(snapshot)
    assert len(snapshot) == 2 + 2 * 2 * 2


def test_ca8_simplifica_solo_por_encima_del_umbral(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dada una capa, cuando se publica, entonces el comando imprime el tamaño en bytes de cada
    fichero; si supera 3 000 000 bytes, simplifica la geometría en EPSG:25830 (antes de
    reproyectar) con tolerancia de 2,0 m, conserva el tipo de geometría y todas las partes no
    vacías, imprime que lo hizo y cuánto pesaba antes, y lo anota en
    `transformacion.simplificacion` del `.procedencia.json`; nunca simplifica un fichero que no
    supera el umbral. Se prueba con una fixture sintética etiquetada con umbral inyectado
    pequeño."""
    assert cli.PUBLISH_SIZE_THRESHOLD_BYTES == 3_000_000
    monkeypatch.setattr(cli, "PUBLISH_SIZE_THRESHOLD_BYTES", 20_000)
    derived = tmp_path / "derived"
    salida = tmp_path / "datos"
    # SINTÉTICA: vía pecuaria pequeña (bajo el umbral) y camino pesado (sobre el umbral),
    # con un MultiLineString de 2 partes densas y una línea de 2 vértices.
    synthetic_layer(
        derived,
        "vias_pecuarias",
        "28997",
        [polygon_feature("S1", [square(0, 0)], procedencia=provenance("vias_pecuarias"))],
    )
    synthetic_layer(
        derived,
        "camino_actual",
        "28997",
        [
            line_feature(
                "900001",
                [zigzag(0, 100, 800), zigzag(0, 200, 800)],
                procedencia=provenance("camino_actual"),
            ),
            line_feature("900002", [zigzag(0, 300, 2)], procedencia=provenance("camino_actual")),
        ],
    )

    assert _publish(derived, salida, "28997") == 0

    out = capsys.readouterr().out
    caminos = salida / "camino_actual" / "28997.geojson"
    vias = salida / "vias_pecuarias" / "28997.geojson"
    sidecar = _load(salida / "camino_actual" / "28997.geojson.procedencia.json")
    simplification = sidecar["transformacion"]["simplificacion"]
    assert simplification["tolerancia_m"] == 2.0
    assert simplification["bytes_antes"] > 20_000
    assert simplification["bytes_despues"] == caminos.stat().st_size < 20_000
    assert f"publicada {caminos} {caminos.stat().st_size} bytes" in out
    assert f"publicada {vias} {vias.stat().st_size} bytes" in out
    assert f"simplificada con tolerancia 2.0 m (antes {simplification['bytes_antes']} bytes)" in out
    assert out.count("simplificada") == 1
    features = _load(caminos)["features"]
    assert features[0]["geometry"]["type"] == "MultiLineString"
    assert len(features[0]["geometry"]["coordinates"]) == 2
    assert all(len(line) >= 2 for line in features[0]["geometry"]["coordinates"])
    assert features[1]["geometry"]["type"] == "LineString"
    assert len(features[1]["geometry"]["coordinates"]) == 2
    vias_sidecar = _load(salida / "vias_pecuarias" / "28997.geojson.procedencia.json")
    assert vias_sidecar["transformacion"]["simplificacion"] is None


_COLLECTION_KEYS = {"capa", "municipio", "nombre_municipio", "atribucion", "aviso", "procedencia"}
_FEATURE_KEYS = {"type", "id", "geometry", "properties"}
_PROPERTY_KEYS = {"nombre", "tipo", "fecha_dato", "procedencia"}
_PROVENANCE_KEYS = {"fuente", "url", "fecha_descarga", "licencia", "redistribucion"}
_SIDECAR_KEYS = _PROVENANCE_KEYS | {
    "atribucion",
    "aviso",
    "capa",
    "municipio",
    "procedencia_limite",
    "transformacion",
}
_BOUNDARY_KEYS = {"fuente", "url", "fecha_descarga", "licencia"}
_TRANSFORM_KEYS = {"crs_origen", "crs_destino", "decimales", "simplificacion"}
_SIMPLIFICATION_KEYS = {"tolerancia_m", "bytes_antes", "bytes_despues"}
_INDEX_ENTRY_KEYS = {"ine", "nombre", "bbox", "capas"}


def _check_provenance_keys(value: dict[str, Any], keys: set[str]) -> None:
    assert set(value) == keys
    assert "catastro" not in str(value["fuente"]).lower()
    assert "catastro" not in str(value["url"]).lower()


def test_ca9_solo_claves_de_la_lista_blanca_y_nada_de_catastro(
    real_derived: Path, tmp_path: Path
) -> None:
    """Dado el contenido de `site/datos/`, entonces no hay nombres de propietarios ni referencias
    catastrales, ni datos de Catastro: un test recorre todos los GeoJSON y procedencias publicados
    y exige que las claves estén en la lista blanca del Diseño (§Datos) y que ninguna `fuente` ni
    `url` contenga `catastro`. `nombre` solo aparece como propiedad de feature (nombre de la vía)
    y `nombre_municipio` en la colección y el índice."""
    salida = tmp_path / "datos"
    assert _publish(real_derived, salida, *cli.AMBITO_HITO_INE[:1], "28170", "28052") == 0

    files = sorted(salida.rglob("*.json")) + sorted(salida.rglob("*.geojson"))
    assert len(files) == 2 + 3 * 2 * 2
    for path in files:
        document = _load(path)
        if path.name == "indice.json":
            assert set(document) == {"municipios"}
            for entry in document["municipios"]:
                assert set(entry) == _INDEX_ENTRY_KEYS
                # Nombre del municipio (contrato del visor, #85): igual al de la colección.
                for relative in entry["capas"].values():
                    collection = _load(salida / relative)["properties"]
                    assert entry["nombre"] == collection["nombre_municipio"]
        elif path.name == "indice.json.procedencia.json":
            _check_provenance_keys(document, _PROVENANCE_KEYS)
        elif path.name.endswith(".procedencia.json"):
            _check_provenance_keys(document, _SIDECAR_KEYS)
            _check_provenance_keys(document["procedencia_limite"], _BOUNDARY_KEYS)
            assert set(document["transformacion"]) == _TRANSFORM_KEYS
            if document["transformacion"]["simplificacion"] is not None:
                assert set(document["transformacion"]["simplificacion"]) == _SIMPLIFICATION_KEYS
        else:
            assert set(document) == {"type", "properties", "features"}
            assert set(document["properties"]) == _COLLECTION_KEYS
            _check_provenance_keys(document["properties"]["procedencia"], _PROVENANCE_KEYS)
            for feature in document["features"]:
                assert set(feature) == _FEATURE_KEYS
                assert set(feature["properties"]) == _PROPERTY_KEYS
                _check_provenance_keys(feature["properties"]["procedencia"], _PROVENANCE_KEYS)
        text = path.read_text(encoding="utf-8").lower()
        for word in ("propiet", "titular", "owner", "catastr", "refcat"):
            assert word not in text, (path, word)


def test_ca10_la_salida_pasa_construir_sitio(real_derived: Path, tmp_path: Path) -> None:
    """Dado el resultado de `publicar-capas` sobre una fixture, cuando se pasa por
    `scripts/construir_sitio.py site <destino>`, entonces termina con código 0 (integración entre
    ambos, sin red)."""
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_bytes(SITE_INDEX_HTML.read_bytes())
    assert _publish(real_derived, site / "datos", "28043") == 0

    assert construir_sitio.main(str(site), str(tmp_path / "_site")) == 0
    assert (tmp_path / "_site" / "datos" / "indice.json").is_file()


def test_ca11_la_marca_sobrevive_al_ciclo_fichero_dominio(tmp_path: Path) -> None:
    """Dada una capa derivada escrita por `GeoJsonRoadLayerWriter` o
    `GeoJsonLivestockTrailLayerWriter` a partir de datos de `RoadNetworkAdapter` o
    `LivestockTrailAdapter`, cuando la lee `GeoJsonTrailLayerReader`, entonces la `Provenance` de
    la capa y de cada trazado es `PUBLIC` (la marca sobrevive al ciclo fichero→dominio); un
    fichero sin `redistribucion` se lee como `INTERNAL_ONLY` (compatibilidad con lo ya escrito),
    y uno con un valor desconocido es `TrailLayerFormatError`."""
    derived = tmp_path / "derived"
    day = date(2026, 11, 26)
    vias = {layer.municipality.ine_code: layer for layer in prepare_cache(tmp_path / "raw", day)}
    roads = {
        layer.municipality.ine_code: layer
        for layer in prepare_road_cache(tmp_path / "raw", day).layers
    }
    GeoJsonLivestockTrailLayerWriter(derived / "vias_pecuarias").write(vias["28043"])
    GeoJsonRoadLayerWriter(derived / "camino_actual").write(roads["28043"])
    reader = _reader(derived)

    for source in (VP, RT):
        layer = reader.get_layer(source, "28043")
        assert layer.trails
        assert layer.provenance.redistribution is Redistribution.PUBLIC
        assert all(t.provenance.redistribution is Redistribution.PUBLIC for t in layer.trails)
        assert layer.municipality_name == "Colmenar de Oreja"
        assert layer.boundary_provenance is not None

    # Fichero sin marca (escrito antes de #84): solo uso interno.
    path = derived / "vias_pecuarias" / "28043.geojson"
    document = _load(path)
    document["properties"]["procedencia"].pop("redistribucion")
    for feature in document["features"]:
        feature["properties"]["procedencia"].pop("redistribucion")
    path.write_text(json.dumps(document), encoding="utf-8")
    layer = reader.get_layer(VP, "28043")
    assert layer.provenance.redistribution is Redistribution.INTERNAL_ONLY
    assert all(t.provenance.redistribution is Redistribution.INTERNAL_ONLY for t in layer.trails)

    # Valor desconocido: error de formato.
    document["properties"]["procedencia"]["redistribucion"] = "interno"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(TrailLayerFormatError):
        reader.get_layer(VP, "28043")


def test_ca12_indice_con_contrato_del_visor_que_se_regenera_entero(
    real_derived: Path, tmp_path: Path
) -> None:
    """Dado `site/datos/` tras publicar, entonces existe `site/datos/indice.json` y su
    `.procedencia.json` con el contrato de #85 (§Datos): municipios ordenados por nombre, solo
    capas publicadas, `bbox` `[oeste, sur, este, norte]` en EPSG:4326 con 6 decimales que contiene
    todas las coordenadas publicadas del municipio. El índice se regenera entero leyendo
    `site/datos/`: publicar un segundo municipio sintético no quita el primero del índice."""
    salida = tmp_path / "datos"
    assert _publish(real_derived, salida, "28170", "28043", extra=("--capa", "camino_actual")) == 0
    assert _publish(real_derived, salida, "28043", extra=("--capa", "vias_pecuarias")) == 0

    index = _load(salida / "indice.json")
    names = [entry["nombre"] for entry in index["municipios"]]
    assert names == ["Colmenar de Oreja", "Villaconejos"]
    colmenar, villaconejos = index["municipios"]
    assert colmenar["ine"] == "28043"
    assert colmenar["capas"] == {
        "camino_actual": "camino_actual/28043.geojson",
        "vias_pecuarias": "vias_pecuarias/28043.geojson",
    }
    # Solo capas publicadas: de Villaconejos solo se pidió camino actual.
    assert villaconejos["capas"] == {"camino_actual": "camino_actual/28170.geojson"}
    for entry in index["municipios"]:
        west, south, east, north = entry["bbox"]
        assert all(round(value, 6) == value for value in entry["bbox"])
        assert west < east and south < north
        for relative in entry["capas"].values():
            for feature in _load(salida / relative)["features"]:
                for lon, lat in _positions(feature["geometry"]["coordinates"]):
                    assert west <= lon <= east
                    assert south <= lat <= north
    index_provenance = _load(salida / "indice.json.procedencia.json")
    assert index_provenance == {
        "fuente": "Parcel Intel, índice de capas publicadas",
        "url": "https://github.com/murcialito/parcel-intel",
        "fecha_descarga": "2026-11-26",
        "licencia": "CC BY 4.0",
        "redistribucion": "publicable",
    }

    # Un segundo municipio SINTÉTICO, publicado aparte, no quita los anteriores.
    derived = tmp_path / "derived"
    small_pair(derived, "28997", "Aaa sintético")
    assert _publish(derived, salida, "28997") == 0
    index = _load(salida / "indice.json")
    assert [entry["ine"] for entry in index["municipios"]] == ["28997", "28043", "28170"]


def test_ca13_capa_vacia_no_se_publica_ni_entra_en_el_indice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dada una capa derivada válida y publicable pero sin features, cuando se publica, entonces
    no se escribe su fichero, la salida dice «capa vacía, no se publica» con capa y municipio, el
    código de salida es 0 si no hay otros fallos, y un municipio sin ninguna capa publicada no
    aparece en el índice."""
    derived = tmp_path / "derived"
    salida = tmp_path / "datos"
    small_pair(derived, "28998")
    synthetic_layer(derived, "vias_pecuarias", "28997", [])
    synthetic_layer(derived, "camino_actual", "28997", [])

    assert _publish(derived, salida, "28997", "28998") == 0

    out = capsys.readouterr().out
    assert "capa vacía, no se publica: vias_pecuarias 28997" in out
    assert "capa vacía, no se publica: camino_actual 28997" in out
    assert not (salida / "vias_pecuarias" / "28997.geojson").exists()
    assert not (salida / "camino_actual" / "28997.geojson").exists()
    assert [entry["ine"] for entry in _load(salida / "indice.json")["municipios"]] == ["28998"]


def test_ca14_multiparte_conserva_tipo_partes_y_anillos_cerrados(
    real_derived: Path, tmp_path: Path
) -> None:
    """Dada una capa con un trazado multi-parte (`MultiPolygon` de 2 partes y `MultiLineString`
    de 2 partes, como `2801308` y `281700231594` de REGISTRY), cuando se publica, entonces el
    GeoJSON publicado conserva el tipo y las 2 partes, y cada anillo de polígono sigue cerrado
    (primer punto igual al último)."""
    # Casos reales en las fixtures: en Colmenar, la pieza de `2801308` es de 1 anillo y la de
    # «Vereda de la Mesa» (`2804303`) es el `MultiPolygon` de 2 partes; `281700231594` es de 2
    # partes en Villaconejos (REGISTRY, #36 y #27).
    salida = tmp_path / "datos"
    assert _publish(real_derived, salida, "28043", "28170") == 0

    vias = {f["id"]: f for f in _load(salida / "vias_pecuarias" / "28043.geojson")["features"]}
    mesa = vias["2804303"]["geometry"]
    assert mesa["type"] == "MultiPolygon"
    assert len(mesa["coordinates"]) == 2
    caminos = {f["id"]: f for f in _load(salida / "camino_actual" / "28170.geojson")["features"]}
    multi = caminos["281700231594"]["geometry"]
    assert multi["type"] == "MultiLineString"
    assert len(multi["coordinates"]) == 2
    assert all(len(line) >= 2 for line in multi["coordinates"])

    for path in salida.glob("vias_pecuarias/*.geojson"):
        for feature in _load(path)["features"]:
            geometry = feature["geometry"]
            polygons = (
                [geometry["coordinates"]]
                if geometry["type"] == "Polygon"
                else geometry["coordinates"]
            )
            for polygon in polygons:
                for ring in polygon:
                    assert ring[0] == ring[-1]
                    assert len(ring) >= 4


@pytest.mark.integration
def test_ca15_integracion_colmenar_real_19_vias_y_893_tramos(tmp_path: Path) -> None:
    """[integración, red] Dada la ejecución real de `camino-actual-municipios` y
    `vias-pecuarias-municipios` y luego `publicar-capas --municipio 28043`, entonces la PR incluye
    `site/datos/{vias_pecuarias,camino_actual}/28043.geojson`, sus procedencias e `indice.json`,
    con 19 features de vías pecuarias y 893 de camino actual (oráculo de REGISTRY.md, historias
    #36 y #27), y una tabla con el peso en bytes de cada fichero. Si el número no coincide, no se
    reinterpreta: se comenta y se pasa a `estado:necesita-fundador` (lección de #35)."""
    derived = tmp_path / "derived"
    for layer in build_municipal_layers(tmp_path / "raw", offline=False):
        GeoJsonLivestockTrailLayerWriter(derived / "vias_pecuarias").write(layer)
    batch = build_municipal_road_layers(tmp_path / "raw", offline=False)
    assert batch.failures == ()
    for road in batch.layers:
        GeoJsonRoadLayerWriter(derived / "camino_actual").write(road)
    salida = tmp_path / "datos"

    assert _publish(derived, salida, "28043") == 0

    for datos in (salida, ROOT / "site" / "datos"):
        assert len(_load(datos / "vias_pecuarias" / "28043.geojson")["features"]) == 19
        assert len(_load(datos / "camino_actual" / "28043.geojson")["features"]) == 893
        for layer_id in LAYERS:
            sidecar = datos / layer_id / "28043.geojson.procedencia.json"
            assert construir_sitio._check_provenance(sidecar) == []
        index = _load(datos / "indice.json")
        assert [entry["ine"] for entry in index["municipios"]] == ["28043"]
