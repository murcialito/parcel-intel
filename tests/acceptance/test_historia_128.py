"""Historia #128: fichero interno de candidatos y comando `candidatos-corte`.

Todo sintético y sin red; CA12 necesita `data/` local.
"""

import ast
import dataclasses
import json
import os
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.adapters.cut_candidate_files import (
    GeoJsonCutCandidateReader,
    GeoJsonCutCandidateWriter,
    report_to_geojson_text,
)
from parcel_intel.adapters.discrepancy_files import GeoJsonDiscrepancyWriter
from parcel_intel.application.detect_cut_candidates import DetectCutCandidatesUseCase
from parcel_intel.cli import main
from parcel_intel.ports.errors import CutCandidateFileError
from tests.adapters.cut_candidate_files.support import (
    PerMunicipalityReports,
    discrepancy_report,
    sample_report,
    use_case_over,
)
from tests.cut_signal_support import (
    ORDINARY,
    Boundaries,
    ParcelsPort,
    Sink,
    parcel,
    rect,
)

pytestmark = pytest.mark.acceptance

SRC = Path(__file__).resolve().parents[2] / "src" / "parcel_intel"


def _read_json(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _write_read(tmp_path: Path, report: Any) -> Any:
    GeoJsonCutCandidateWriter(tmp_path).write(report)
    return GeoJsonCutCandidateReader(tmp_path).get_report(report.municipality_code)


def test_ca1_el_escritor_guarda_una_featurecollection_en_25830(tmp_path: Path) -> None:
    """CA1. Dado un `MunicipalCutCandidateReport` con candidatos, cuando el escritor lo guarda,
    entonces `data/derived/candidatos/interno/<ine>.geojson` es una `FeatureCollection` en
    EPSG:25830 (miembro `crs` como en el fichero de discrepancias) con una feature
    `MultiLineString` por candidato, cuyas propiedades llevan `candidate_id`,
    `municipality_code`, condiciones, confianza, señales y evidencia, y cuyo nivel superior
    lleva método, `discrepancy_criterion_id`, `base_record_ids` y el resumen por señal."""
    report = sample_report()
    GeoJsonCutCandidateWriter(tmp_path).write(report)
    data = _read_json(tmp_path / "28043.geojson")
    assert data["type"] == "FeatureCollection"
    assert data["crs"]["properties"]["name"].endswith("EPSG::25830")
    assert len(data["features"]) == len(report.candidates)
    feature = data["features"][0]
    assert feature["geometry"]["type"] == "MultiLineString"
    props = feature["properties"]
    candidate = report.candidates[0]
    assert props["candidate_id"] == candidate.candidate_id
    assert props["municipality_code"] == "28043"
    assert props["condiciones"] == list(candidate.conditions)
    assert props["confianza"] == candidate.confidence
    assert props["senales"] and props["evidencia"]
    top = data["properties"]
    assert top["metodo"] == "candidato_corte@1"
    assert top["criterio_discrepancias"] == report.discrepancy_criterion_id
    assert top["registros_base"] == list(report.base_record_ids)
    assert top["senales"][0]["senal"]["identificador"] == "parcela_no_camino"
    assert top["senales"][0]["estado"] == "ejecutada"


def test_ca2_el_lector_reconstruye_un_informe_igual(tmp_path: Path) -> None:
    """CA2. Dado un fichero escrito por el escritor, cuando el lector lo lee con
    `get_report(ine)`, entonces devuelve un `MunicipalCutCandidateReport` igual (`==`) al
    original, incluidos el orden canónico de candidatos y las coordenadas del tramo (ida y
    vuelta sin pérdida a 0,01 m)."""
    report = sample_report()
    assert _write_read(tmp_path, report) == report


def test_ca3_informe_sin_candidatos_es_evaluable(tmp_path: Path) -> None:
    """CA3. Dado un informe con cero candidatos, cuando se escribe y se lee, entonces el
    fichero existe (colección sin features, con su metadato) y `get_report` devuelve un
    informe con `candidates == ()`: «municipio evaluable»."""
    empty = dataclasses.replace(sample_report(), candidates=())
    result = _write_read(tmp_path, empty)
    assert (tmp_path / "28043.geojson").is_file()
    assert _read_json(tmp_path / "28043.geojson")["features"] == []
    assert result is not None
    assert result.candidates == ()
    assert result == empty


def test_ca4_sin_fichero_es_none_y_fichero_roto_es_error(tmp_path: Path) -> None:
    """CA4. Dado un municipio sin fichero, cuando se llama a `get_report(ine)`, entonces
    devuelve `None` («sin capas»); un fichero ilegible o con un CRS distinto de 25830 lanza
    un error propio del port, no `None` (un fichero roto no es «sin capas»)."""
    reader = GeoJsonCutCandidateReader(tmp_path)
    assert reader.get_report("28043") is None

    (tmp_path / "28043.geojson").write_text("{truncado", encoding="utf-8")
    with pytest.raises(CutCandidateFileError):
        reader.get_report("28043")

    GeoJsonCutCandidateWriter(tmp_path).write(sample_report("28013"))
    path = tmp_path / "28013.geojson"
    data = _read_json(path)
    data["crs"]["properties"]["name"] = "urn:ogc:def:crs:EPSG::4326"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CutCandidateFileError, match="25830"):
        reader.get_report("28013")


def test_ca5_bytes_deterministas_y_escritura_atomica(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CA5. Dado un informe, cuando se escribe dos veces, entonces los bytes son idénticos
    (orden determinista, sin marcas de tiempo, números a 3 decimales) y el fichero previo se
    sustituye de forma atómica (escribe en temporal y renombra: un fallo a medias no deja un
    fichero truncado que el lector tomaría por «evaluable»)."""
    report = sample_report()
    writer = GeoJsonCutCandidateWriter(tmp_path)
    writer.write(report)
    first = (tmp_path / "28043.geojson").read_bytes()
    writer.write(report)
    assert (tmp_path / "28043.geojson").read_bytes() == first
    assert first == report_to_geojson_text(report).encode("utf-8")

    def broken_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise OSError("disco lleno")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError):
        writer.write(dataclasses.replace(report, candidates=()))
    assert (tmp_path / "28043.geojson").read_bytes() == first
    assert sorted(p.name for p in tmp_path.iterdir()) == ["28043.geojson"]


def _keys(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key))
            found |= _keys(value)
    elif isinstance(node, list):
        for item in node:
            found |= _keys(item)
    return found


def test_ca6_sin_titularidad_ni_referencias_ni_parcelas(tmp_path: Path) -> None:
    """CA6. Dado el fichero escrito, cuando se inspecciona, entonces no contiene ningún campo
    de titularidad, propietario, referencia catastral de finca ni geometría de parcela (test
    sobre las claves y sobre un informe construido con provenance de Catastro)."""
    report = sample_report()
    assert any("Catastro" in p.source for s in report.signals for p in s.provenance)
    GeoJsonCutCandidateWriter(tmp_path).write(report)
    text = (tmp_path / "28043.geojson").read_text(encoding="utf-8")
    keys = {key.lower() for key in _keys(json.loads(text))}
    forbidden = ("titular", "propietari", "owner", "referencia", "catastral", "parcela", "nif")
    assert not [k for k in keys if any(word in k for word in forbidden)]
    assert ORDINARY not in text
    geometry_types = {f["geometry"]["type"] for f in json.loads(text)["features"]}
    assert geometry_types == {"MultiLineString"}


def _fake_use_case(
    tmp_path: Path,
    reports: PerMunicipalityReports,
    port: ParcelsPort | None = None,
) -> DetectCutCandidatesUseCase:
    port = port or ParcelsPort([parcel(ORDINARY, rect(50, -50, 150, 50))])
    provider_use_case = use_case_over(reports, Sink(), port)
    return DetectCutCandidatesUseCase(
        reports,
        provider_use_case._providers,
        GeoJsonCutCandidateWriter(tmp_path / "salida"),
    )


def _patch(monkeypatch: pytest.MonkeyPatch, use_case: DetectCutCandidatesUseCase) -> None:
    monkeypatch.setattr(main, "build_cut_candidate_use_case", lambda *a, **k: use_case)


def _run(*argv: str) -> int:
    return int(main._candidatos_corte(main._build_parser().parse_args(["candidatos-corte", *argv])))


def test_ca7_comando_con_dos_municipios(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA7. Dado `candidatos-corte --municipio 28043 --municipio 28013`, cuando se ejecuta con
    fakes inyectados, entonces ejecuta el caso de uso por municipio, escribe un fichero por
    cada uno, imprime una línea por municipio con el número de candidatos y las señales
    `sin_datos`, y sale con 0."""
    _patch(monkeypatch, _fake_use_case(tmp_path, PerMunicipalityReports()))
    assert _run("--municipio", "28043", "--municipio", "28013") == 0
    assert sorted(p.name for p in (tmp_path / "salida").iterdir()) == [
        "28013.geojson",
        "28043.geojson",
    ]
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("28043: 1 candidatos") and "sin_datos: ninguna" in lines[0]
    assert lines[1].startswith("28013: 1 candidatos")


def test_ca8_un_fallo_no_frena_el_lote_y_sin_capas_no_es_fallo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA8. Dado un municipio que falla en el caso de uso, cuando se ejecuta el comando con
    varios municipios, entonces sigue con los demás, informa del fallo en stderr y sale con 1.
    Dado un municipio sin informe de discrepancias («sin capas»), entonces se registra como
    tal, no escribe fichero y no cuenta como fallo."""
    reports = PerMunicipalityReports(missing=("28052",), broken=("28013",))
    _patch(monkeypatch, _fake_use_case(tmp_path, reports))
    assert _run("--municipio", "28013", "--municipio", "28043", "--municipio", "28052") == 1
    captured = capsys.readouterr()
    assert "FALLO 28013" in captured.err
    assert "28052: sin capas" in captured.out
    assert sorted(p.name for p in (tmp_path / "salida").iterdir()) == ["28043.geojson"]

    # Solo «sin capas»: no es un fallo.
    assert _run("--municipio", "28052") == 0


def test_ca9_ambito_y_uso(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA9. Dado `candidatos-corte --ambito`, cuando se ejecuta, entonces recorre los 7
    municipios de `AMBITO_HITO_INE`; sin `--municipio` ni `--ambito` sale con 1 y un mensaje
    de uso."""
    _patch(monkeypatch, _fake_use_case(tmp_path, PerMunicipalityReports()))
    assert _run("--ambito") == 0
    written = sorted(p.stem for p in (tmp_path / "salida").iterdir())
    assert written == sorted(main.AMBITO_HITO_INE)
    capsys.readouterr()
    assert _run() == 1
    assert "--municipio" in capsys.readouterr().err


def test_ca10_sin_red_las_teselas_que_faltan_dejan_la_senal_sin_datos(tmp_path: Path) -> None:
    """CA10. Dado `--sin-red`, cuando faltan teselas de parcelas en la caché, entonces la
    señal queda `sin_datos` con su motivo y no se intenta ninguna petición de red (los tests
    usan un fetcher que falla si se le llama)."""
    derived = tmp_path / "derived"
    GeoJsonDiscrepancyWriter(derived / "discrepancias" / "interno", publishable=False).write(
        discrepancy_report()
    )
    calls: list[str] = []

    def no_network(url: str, params: dict[str, str]) -> bytes:
        calls.append(url)
        raise AssertionError("no debe haber red con --sin-red")

    use_case = main.build_cut_candidate_use_case(
        derived,
        tmp_path / "salida",
        tmp_path / "raw",
        offline=True,
        catastro_http_get=no_network,
        ign_http_get=no_network,
        boundaries=Boundaries((-100, -100, 300, 100)),
    )
    result = use_case.execute("28043")
    assert calls == []
    [summary] = result.signals
    assert summary.status == "sin_datos"
    assert summary.reason and "sin red" in summary.reason
    assert result.candidates == ()
    reread = GeoJsonCutCandidateReader(tmp_path / "salida").get_report("28043")
    assert reread == result


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def test_ca11_capas_respetadas() -> None:
    """CA11. Dado el módulo del lector, cuando se ejecuta `lint-imports`, entonces
    `ports/cut_candidate_source.py` solo importa `domain` y el adapter es el único que
    lee/escribe GeoJSON."""
    port = _imports(SRC / "ports" / "cut_candidate_source.py")
    assert all(m.startswith(("parcel_intel.domain", "typing")) for m in port)
    for path in (SRC / "adapters" / "cut_candidate_files").glob("*.py"):
        imports = _imports(path)
        assert not [m for m in imports if m.startswith("parcel_intel.application")], path
        assert not [
            m
            for m in imports
            if m.startswith("parcel_intel.adapters") and "cut_candidate_files" not in m
        ], path
    for path in (SRC / "application").glob("*.py"):
        assert "geojson" not in path.read_text(encoding="utf-8").lower() or path.name in {
            "publish_layers.py",
            "publish_discrepancies.py",
        }, path


@pytest.mark.integration
@pytest.mark.fuera_de_ci  # depende de data/ local (caché de #37 e informe de #94)
def test_ca12_colmenar_real_genera_el_fichero_y_el_lector_lo_reconstruye(tmp_path: Path) -> None:
    """CA12. [integración] Dado Colmenar de Oreja (28043) con la caché de #37 y el informe de
    discrepancias ya generados, cuando se ejecuta `candidatos-corte --municipio 28043
    --sin-red`, entonces genera el fichero y el lector lo reconstruye. Se marca `integration`
    porque depende de `data/` local; el resto de criterios se prueba con fixtures."""
    derived = Path("data/derived")
    if not (derived / "discrepancias" / "interno" / "28043.geojson").is_file():
        pytest.skip("falta el informe interno de 28043 en data/derived (ejecuta `discrepancias`)")
    exit_code = _run("--municipio", "28043", "--sin-red", "--salida", str(tmp_path))
    assert exit_code == 0
    report = GeoJsonCutCandidateReader(tmp_path).get_report("28043")
    assert report is not None
    assert report.municipality_code == "28043"
    assert (tmp_path / "28043.geojson").read_bytes() == report_to_geojson_text(report).encode()
