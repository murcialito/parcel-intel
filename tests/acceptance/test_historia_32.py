"""Criterios de aceptación de la historia #32: lote de discrepancias por municipio
desde la CLI (lector de capas y ficheros GeoJSON). Fixtures SINTÉTICAS en
`tests/fixtures/discrepancias/` (ver su LEEME.md)."""

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.discrepancy_files import GeoJsonDiscrepancyWriter, UnredactedReportError
from parcel_intel.adapters.trail_layers import GeoJsonTrailLayerReader, TrailLayerFormatError
from parcel_intel.cli import main
from parcel_intel.domain.discrepancy_detection import detect_municipal_discrepancies
from parcel_intel.domain.discrepancy_policy import redact_for_publication
from parcel_intel.domain.discrepancy_report import MunicipalDiscrepancyReport
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry
from parcel_intel.domain.trail import SourceKind
from parcel_intel.ports.errors import TrailLayerUnavailableError

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).parents[2]
SRC = ROOT / "src" / "parcel_intel"
ENTRADA = ROOT / "tests" / "fixtures" / "discrepancias" / "entrada"
CATASTRO: SourceKind = "catastro_vt"
IGN: SourceKind = "ign_red_transporte"
VIA: SourceKind = "via_pecuaria_oficial"


def _reader(entrada: Path = ENTRADA) -> GeoJsonTrailLayerReader:
    return GeoJsonTrailLayerReader(
        {
            VIA: entrada / "vias_pecuarias",
            IGN: entrada / "camino_actual",
            CATASTRO: entrada / "catastro_caminos",
        }
    )


def _run_cli(argv: list[str]) -> int:
    """Ejecuta `main.main()` con esos argumentos y devuelve el código de salida."""
    old = sys.argv
    sys.argv = ["parcel_intel.cli.main", *argv]
    try:
        with pytest.raises(SystemExit) as exit_info:
            main.main()
    finally:
        sys.argv = old
    code = exit_info.value.code
    assert isinstance(code, int)
    return code


def _read(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _features(document: dict[str, object]) -> list[dict[str, object]]:
    features = document["features"]
    assert isinstance(features, list)
    return features


def _properties(item: dict[str, object]) -> dict[str, object]:
    properties = item["properties"]
    assert isinstance(properties, dict)
    return properties


def _trails(feature: dict[str, object]) -> list[dict[str, object]]:
    trails = _properties(feature)["trazados"]
    assert isinstance(trails, list)
    return trails


@pytest.fixture
def salida(tmp_path: Path) -> Path:
    """Ejecuta el subcomando sobre 28043 y devuelve el directorio de salida."""
    out = tmp_path / "salida"
    assert (
        _run_cli(
            [
                "discrepancias",
                "--municipio",
                "28043",
                "--entrada",
                str(ENTRADA),
                "--salida",
                str(out),
            ]
        )
        == 0
    )
    return out


def _report(*, with_catastro: bool = True) -> MunicipalDiscrepancyReport:
    layers = [_reader().get_layer(VIA, "28043"), _reader().get_layer(IGN, "28043")]
    if with_catastro:
        layers.append(_reader().get_layer(CATASTRO, "28043"))
    return detect_municipal_discrepancies("28043", layers, [])


def test_ca1_el_lector_devuelve_el_trail_layer_en_25830_sin_z() -> None:
    """Dada una capa en el formato común (fixture sintética, con `Polygon`, `MultiPolygon` y
    `LineString` 3D), cuando la lee `GeoJsonTrailLayerReader`, entonces devuelve un `TrailLayer`
    con cada trazado en EPSG:25830 (sin Z), su `Provenance` y su fecha del dato, y el
    `MultiPolygon` conserva todas sus partes."""
    layer = _reader().get_layer(VIA, "28043")

    assert layer.source == VIA
    assert layer.municipality_code == "28043"
    assert layer.provenance.source == "SINTÉTICO capa de vías pecuarias"
    assert layer.provenance.url == "https://example.invalid/vias_pecuarias"
    assert layer.provenance.retrieved_at == date(2026, 11, 26)
    assert layer.provenance.license == "SINTÉTICA, solo para pruebas"
    by_id = {trail.identifier: trail for trail in layer.trails}
    assert set(by_id) == {"VP-1", "VP-2", "VP-3"}
    assert all(trail.geometry.srid == 25830 for trail in layer.trails)
    assert all(trail.data_date == date(2014, 1, 1) for trail in layer.trails)
    assert all(trail.provenance.license for trail in layer.trails)

    polygon = by_id["VP-1"].geometry
    assert isinstance(polygon, Geometry)
    assert polygon.rings == (((0, 0), (200, 0), (200, 20), (0, 20), (0, 0)),)

    multipolygon = by_id["VP-2"].geometry
    assert isinstance(multipolygon, Geometry)
    assert len(multipolygon.rings) == 2  # conserva las dos partes
    assert multipolygon.rings[1][0] == (200, 300)

    line = by_id["VP-3"].geometry
    assert isinstance(line, MultiLineGeometry)
    assert line.lines == (((0, 600), (200, 600)),)  # la Z (650,5 / 651,2) se descarta


def _layer_text(**changes: object) -> str:
    document = _read(ENTRADA / "vias_pecuarias" / "28043.geojson")
    for key, value in changes.items():
        if value is None:
            document.pop(key, None)
        else:
            document[key] = value
    return json.dumps(document)


def test_ca2_sin_fichero_es_no_disponible_y_un_fichero_invalido_es_error_de_formato(
    tmp_path: Path,
) -> None:
    """Dada una fuente sin fichero para el municipio, cuando se pide su capa, entonces se lanza
    `TrailLayerUnavailableError`. Dado un fichero con JSON inválido, CRS distinto de 25830,
    `fuente` que no coincide o sin procedencia, entonces se lanza `TrailLayerFormatError`
    nombrando fuente y fichero."""
    reader = _reader()
    with pytest.raises(TrailLayerUnavailableError):
        reader.get_layer(CATASTRO, "28045")  # directorio configurado, sin fichero
    with pytest.raises(TrailLayerUnavailableError):
        reader.get_layer("planimetria_historica", "28043")  # fuente sin directorio

    directory = tmp_path / "vias_pecuarias"
    directory.mkdir()
    bad_crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}}
    wrong_source = _read(ENTRADA / "vias_pecuarias" / "28043.geojson")
    props = wrong_source["properties"]
    assert isinstance(props, dict)
    props["fuente"] = "catastro_vt"
    no_provenance = _read(ENTRADA / "vias_pecuarias" / "28043.geojson")
    props_np = no_provenance["properties"]
    assert isinstance(props_np, dict)
    del props_np["procedencia"]
    cases = {
        "28001": "{no es json",
        "28002": _layer_text(crs=bad_crs),
        "28003": json.dumps(wrong_source),
        "28004": json.dumps(no_provenance),
    }
    for code, text in cases.items():
        document = text if text.startswith("{no") else text.replace("28043", code)
        (directory / f"{code}.geojson").write_text(document, encoding="utf-8")
        with pytest.raises(TrailLayerFormatError) as error:
            GeoJsonTrailLayerReader({VIA: directory}).get_layer(VIA, code)
        assert VIA in str(error.value)
        assert f"{code}.geojson" in str(error.value)
        assert error.value.source == VIA
        assert error.value.path == directory / f"{code}.geojson"


def test_ca3_cada_feature_lleva_tipo_medidas_confianza_evidencia_criterio_y_trazados(
    salida: Path,
) -> None:
    """Dado un informe con discrepancias entre dos fuentes, cuando se escribe, entonces cada
    feature lleva tipo, medidas, confianza, evidencia, criterio y `trazados` de todas las
    fuentes implicadas, cada uno con `procedencia` (fuente, URL, fecha de descarga, licencia)."""
    document = _read(salida / "interno" / "28043.geojson")
    features = _features(document)
    assert features
    for feature in features:
        properties = _properties(feature)
        for key in ("tipo", "medidas", "confianza", "evidencia", "criterio", "trazados"):
            assert key in properties, key
        for trail in _trails(feature):
            procedencia = trail["procedencia"]
            assert isinstance(procedencia, dict)
            assert set(procedencia) == {"fuente", "url", "fecha_descarga", "licencia"}
            assert all(procedencia.values())

    # Oráculo fijado a mano (LEEME.md): R-3 (IGN) paralela a 12,5 m de VP-3 (tolerancia 11,18 m).
    displaced = [f for f in features if _properties(f)["tipo"] == "DESPLAZAMIENTO"]
    assert len(displaced) == 1
    properties = _properties(displaced[0])
    medidas = properties["medidas"]
    assert isinstance(medidas, dict)
    assert medidas["desplazamiento_mediano_m"] == pytest.approx(12.5, abs=0.01)
    assert (properties["fuente_a"], properties["fuente_b"]) == (IGN, VIA)
    assert [(t["id"], t["fuente"]) for t in _trails(displaced[0])] == [("R-3", IGN), ("VP-3", VIA)]
    assert 0.0 < float(str(properties["confianza"])) <= 1.0


def test_ca4_dos_ejecuciones_con_distinto_pythonhashseed_son_identicas_byte_a_byte(
    tmp_path: Path,
) -> None:
    """Dado el mismo conjunto de capas, cuando se ejecuta el subcomando dos veces en
    subprocesos con `PYTHONHASHSEED` distinto, entonces los dos ficheros (interno y publicable)
    son idénticos byte a byte y no contienen ninguna fecha de generación."""
    outputs: list[Path] = []
    for seed in ("1", "12345"):
        out = tmp_path / f"salida_{seed}"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "parcel_intel.cli.main",
                "discrepancias",
                "--municipio",
                "28043",
                "--entrada",
                str(ENTRADA),
                "--salida",
                str(out),
            ],
            env={**os.environ, "PYTHONHASHSEED": seed},
            check=True,
            capture_output=True,
            cwd=ROOT,
        )
        outputs.append(out)
    for variant in ("interno", "publicable"):
        first = (outputs[0] / variant / "28043.geojson").read_bytes()
        second = (outputs[1] / variant / "28043.geojson").read_bytes()
        assert first == second
        text = first.decode("utf-8")
        # Las únicas fechas del fichero son las de las capas sintéticas, no la de generación.
        dates = set(re.findall(r"\d{4}-\d{2}-\d{2}", text))
        assert dates <= {"2014-01-01", "2020-05-01", "2025-01-01", "2026-11-26"}
        assert "generaci" not in text


_FORBIDDEN = ("titular", "titularidad", "propietario", "dueño", "dueno")


def _walk(value: object) -> Iterator[str]:
    """Todas las claves y los valores de texto del JSON."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, str):
        yield value


def test_ca5_geojson_en_25830_con_criterio_y_sin_titularidad(salida: Path) -> None:
    """Dado el fichero generado, cuando se inspecciona, entonces es un GeoJSON
    `FeatureCollection` con `crs` EPSG:25830 y el `criterio` de #14 en la colección y en cada
    feature. Ninguna clave ni valor de todo el fichero contiene titular, titularidad,
    propietario, dueño ni nombres de persona (test que recorre el JSON completo)."""
    for variant in ("interno", "publicable"):
        document = _read(salida / variant / "28043.geojson")
        assert document["type"] == "FeatureCollection"
        assert document["crs"] == {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::25830"},
        }
        collection = document["properties"]
        assert isinstance(collection, dict)
        criterion = collection["criterio"]
        assert criterion == "discrepancia_trazados@1"
        assert collection["aviso"] == "Indicios automáticos a verificar; no son un dictamen."
        assert collection["publicable"] is (variant == "publicable")
        for feature in _features(document):
            assert _properties(feature)["criterio"] == criterion
        for text in _walk(document):
            lowered = text.lower()
            assert not any(word in lowered for word in _FORBIDDEN), text
            assert "nombre" not in lowered, text  # ningún campo de nombres (de persona)


def test_ca6_el_publicable_omite_la_geometria_de_catastro_y_el_interno_la_conserva(
    salida: Path,
) -> None:
    """Dado un informe con trazados de Catastro, cuando se escribe el publicable, entonces cada
    trazado de Catastro aparece con `id` y `procedencia`, `geometria: null` y
    `geometria_omitida: "licencia"`. Si el lado A es Catastro, la feature tiene
    `geometry: null` y `zona_omitida_por_licencia: true`. El interno conserva todas las
    geometrías."""
    public = _features(_read(salida / "publicable" / "28043.geojson"))
    internal = _features(_read(salida / "interno" / "28043.geojson"))
    assert {f["id"] for f in public} == {f["id"] for f in internal}

    catastro_trails = 0
    for feature in public:
        for trail in _trails(feature):
            if trail["fuente"] == CATASTRO:
                catastro_trails += 1
                assert trail["id"] and trail["procedencia"]
                assert trail["geometria"] is None
                assert trail["geometria_omitida"] == "licencia"
            else:
                assert trail["geometria"] is not None  # las redistribuibles se conservan
    assert catastro_trails >= 1

    side_a_catastro = [f for f in public if _properties(f)["fuente_a"] == CATASTRO]
    assert side_a_catastro  # C-2 no tiene equivalente en el IGN
    for feature in side_a_catastro:
        assert feature["geometry"] is None
        assert _properties(feature)["zona_omitida_por_licencia"] is True

    for feature in internal:
        assert feature["geometry"] is not None
        assert _properties(feature)["zona_omitida_por_licencia"] is False
        assert all(trail["geometria"] is not None for trail in _trails(feature))


def test_ca7_el_escritor_publicable_rechaza_un_informe_sin_redactar(tmp_path: Path) -> None:
    """Dado un informe sin redactar, cuando se escribe con el escritor publicable, entonces
    lanza `UnredactedReportError` y no crea ni modifica ningún fichero."""
    report = _report()
    assert report.redacted is False

    fresh = tmp_path / "nuevo"
    with pytest.raises(UnredactedReportError):
        GeoJsonDiscrepancyWriter(fresh, publishable=True).write(report)
    assert not fresh.exists()

    existing = tmp_path / "existente"
    existing.mkdir()
    (existing / "28043.geojson").write_text("previo\n", encoding="utf-8")
    with pytest.raises(UnredactedReportError):
        GeoJsonDiscrepancyWriter(existing, publishable=True).write(report)
    assert [p.name for p in existing.iterdir()] == ["28043.geojson"]
    assert (existing / "28043.geojson").read_text(encoding="utf-8") == "previo\n"

    # Con el informe redactado sí escribe.
    GeoJsonDiscrepancyWriter(fresh, publishable=True).write(redact_for_publication(report))
    assert (fresh / "28043.geojson").is_file()


def test_ca8_un_municipio_con_capa_corrupta_no_impide_escribir_los_demas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dados tres municipios en el lote, uno con una capa corrupta, cuando se ejecuta
    `discrepancias --municipio A --municipio B --municipio C`, entonces A y C se escriben,
    stderr nombra el municipio, la fuente y el fichero que fallaron, y el código de salida es 1.
    Sin fallos, el código es 0."""
    out = tmp_path / "salida"
    argv = ["discrepancias", "--entrada", str(ENTRADA), "--salida", str(out)]

    code = _run_cli([*argv, "--municipio", "28043", "--municipio", "28044", "--municipio", "28045"])

    assert code == 1
    for variant in ("interno", "publicable"):
        assert (out / variant / "28043.geojson").is_file()
        assert (out / variant / "28045.geojson").is_file()
        assert not (out / variant / "28044.geojson").exists()
    stderr = capsys.readouterr().err
    assert "28044" in stderr
    assert IGN in stderr
    assert str(ENTRADA / "camino_actual" / "28044.geojson") in stderr

    out_ok = tmp_path / "salida_ok"
    assert (
        _run_cli(
            [
                "discrepancias",
                "--entrada",
                str(ENTRADA),
                "--salida",
                str(out_ok),
                "--municipio",
                "28043",
                "--municipio",
                "28045",
            ]
        )
        == 0
    )


def test_ca9_sin_catastro_ni_historico_las_capas_constan_como_ausentes(tmp_path: Path) -> None:
    """Dado un municipio sin capa de Catastro ni de histórico, cuando se ejecuta, entonces el
    fichero se escribe y `capas` las lista como `ausente` con su motivo."""
    out = tmp_path / "salida"
    assert (
        _run_cli(
            [
                "discrepancias",
                "--municipio",
                "28045",
                "--entrada",
                str(ENTRADA),
                "--salida",
                str(out),
            ]
        )
        == 0
    )

    for variant in ("interno", "publicable"):
        document = _read(out / variant / "28045.geojson")
        collection = document["properties"]
        assert isinstance(collection, dict)
        capas = {layer["fuente"]: layer for layer in collection["capas"]}
        assert set(capas) == {VIA, IGN, CATASTRO, "planimetria_historica", "mtn50_historico"}
        for source in (CATASTRO, "planimetria_historica", "mtn50_historico"):
            assert capas[source]["estado"] == "ausente"
            assert capas[source]["motivo_ausencia"]
            assert capas[source]["procedencia"] is None
        for source in (VIA, IGN):
            assert capas[source]["estado"] == "disponible"
            assert capas[source]["procedencia"]["licencia"]
            assert capas[source]["trazados"] == 1


def _imports(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_ca10_los_adapters_solo_se_instancian_en_la_cli_y_no_hay_red() -> None:
    """`uv run lint-imports`, `uv run mypy`, `uv run ruff check .`, `uv run pytest` y
    `uv run pytest -m acceptance` en verde, ejecutados literalmente. Los adapters solo se
    instancian en `cli/main.py` y ningún test llama a red."""
    # (Los cinco comandos se ejecutan en la PR; aquí se fijan las dos garantías comprobables.)
    adapter_classes = {"GeoJsonTrailLayerReader", "GeoJsonDiscrepancyWriter"}
    for path in SRC.rglob("*.py"):
        relative = path.relative_to(SRC)
        if relative.parts[0] in {"adapters", "cli"}:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                assert name not in adapter_classes, f"{relative} instancia {name}"
    cli_calls = {
        n.func.id
        for n in ast.walk(ast.parse((SRC / "cli" / "main.py").read_text(encoding="utf-8")))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert adapter_classes <= cli_calls

    for package in ("trail_layers", "discrepancy_files"):
        for path in (SRC / "adapters" / package).glob("*.py"):
            assert not _imports(path) & {"requests", "urllib", "socket", "http"}, path


@pytest.mark.integration
def test_ca11_integracion_colmenar_con_las_capas_reales(tmp_path: Path) -> None:
    """[integración] Dado Colmenar de Oreja (28043) con las capas de #23 y #27 ya generadas en
    `data/derived/`, cuando se ejecuta `uv run python -m parcel_intel.cli.main discrepancias
    --municipio 28043`, entonces escribe `data/derived/discrepancias/interno/28043.geojson` y
    `.../publicable/28043.geojson` sin errores y con código 0. La PR anota el número de
    discrepancias por tipo y el tiempo de ejecución."""
    derived = ROOT / "data" / "derived"
    if not (derived / "camino_actual" / "28043.geojson").is_file():
        pytest.skip(
            "Faltan las capas reales en data/derived (se generan con camino-actual-municipios "
            "y vias-pecuarias-municipios desde la caché de data/raw)"
        )
    out = tmp_path / "discrepancias"
    started = time.monotonic()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "parcel_intel.cli.main",
            "discrepancias",
            "--municipio",
            "28043",
            "--entrada",
            str(derived),
            "--salida",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    elapsed = time.monotonic() - started
    assert result.returncode == 0, result.stderr
    print(result.stdout, f"{elapsed:.1f} s")
    for variant in ("interno", "publicable"):
        assert (out / variant / "28043.geojson").is_file()
    shutil.rmtree(out)
