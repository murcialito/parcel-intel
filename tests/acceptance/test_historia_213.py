"""Historia #213: `publicar-kit-campo` exporta los tramos publicados de un municipio a GPX y KML.

Entradas SINTÉTICAS en `tests/fixtures/kit_campo/datos/` (vías pecuarias y discrepancias de
28043; sin candidatos). Los docstrings copian el criterio de la issue.
"""

import json
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.cli import main as cli

pytestmark = pytest.mark.acceptance

FIXTURES = Path(__file__).parent.parent / "fixtures" / "kit_campo" / "datos"
GPX = "{http://www.topografix.com/GPX/1/1}"
KML = "{http://www.opengis.net/kml/2.2}"
WARNING_START = "Esto no es un dictamen"


@pytest.fixture
def entrada(tmp_path: Path) -> Path:
    target = tmp_path / "entrada"
    shutil.copytree(FIXTURES, target)
    return target


def run(entrada: Path, salida: Path, *municipios: str) -> int:
    args = ["--entrada", str(entrada), "--salida", str(salida)]
    for code in municipios:
        args += ["--municipio", code]
    parser = cli._build_parser()
    namespace = parser.parse_args(["publicar-kit-campo", *args])
    exit_code: int = namespace.func(namespace)
    return exit_code


def edit_geojson(entrada: Path, layer: str, mutate: Callable[[Any], object]) -> None:
    path = entrada / layer / "28043.geojson"
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document), encoding="utf-8")


def kit_files(salida: Path) -> list[Path]:
    kit = salida / "kit"
    return sorted(p for p in kit.rglob("*") if p.is_file()) if kit.exists() else []


def test_ca1_escribe_gpx_y_kml_bien_formados(entrada: Path, tmp_path: Path) -> None:
    """Dado un municipio con ficheros publicados de `discrepancias` y `vias_pecuarias` cuando se
    ejecuta `publicar-kit-campo --municipio <ine>` entonces escribe
    `site/datos/kit/<ine>/tramos.gpx` y `tramos.kml` bien formados (XML válido), con un elemento
    por tramo y la geometría en EPSG:4326."""
    salida = tmp_path / "salida"
    assert run(entrada, salida, "28043") == 0
    gpx = ET.parse(salida / "kit/28043/tramos.gpx").getroot()
    kml = ET.parse(salida / "kit/28043/tramos.kml").getroot()
    assert len(gpx.findall(f"{GPX}trk")) == 4  # 2 vías pecuarias + 2 indicios
    assert len(kml.findall(f".//{KML}Placemark")) == 4
    lat_lon = [(float(p.get("lat", "")), float(p.get("lon", ""))) for p in gpx.iter(f"{GPX}trkpt")]
    assert lat_lon and all(-90 <= la <= 90 and -180 <= lo <= 180 for la, lo in lat_lon)
    assert (40.0499, -3.5188) in lat_lon
    assert kml.find(f".//{KML}LineString") is not None
    assert kml.find(f".//{KML}Polygon") is not None
    assert kml.find(f".//{KML}MultiGeometry") is not None  # el MultiPolygon


def test_ca2_discrepancia_con_etiqueta_texto_confianza_y_aviso(
    entrada: Path, tmp_path: Path
) -> None:
    """Dado un tramo de discrepancia publicado cuando se exporta entonces su nombre es la
    etiqueta de la ficha y su descripción incluye el texto de la ficha, la confianza y el aviso
    literal del fichero publicado; nunca una afirmación de ilegalidad."""
    salida = tmp_path / "salida"
    assert run(entrada, salida, "28043") == 0
    published = json.loads((entrada / "discrepancias/28043.geojson").read_text(encoding="utf-8"))
    first = published["features"][0]["properties"]
    kml = ET.parse(salida / "kit/28043/tramos.kml").getroot()
    marks = {
        m.findtext(f"{KML}name"): m.findtext(f"{KML}description")
        for m in kml.iter(f"{KML}Placemark")
    }
    description = marks[first["etiqueta"]]
    assert description is not None
    assert first["texto"] in description
    assert "Confianza: alta" in description
    assert first["aviso"] in description
    assert "ilegal" not in description.lower()
    gpx = ET.parse(salida / "kit/28043/tramos.gpx").getroot()
    names = [t.findtext(f"{GPX}name") for t in gpx.iter(f"{GPX}trk")]
    assert first["etiqueta"] in names
    for descr in (d.text or "" for d in gpx.iter(f"{GPX}desc")):
        assert descr


def test_ca3_metadatos_con_fuente_licencia_y_atribucion(entrada: Path, tmp_path: Path) -> None:
    """Dado un GPX/KML generado cuando se leen sus metadatos entonces constan la fuente, la
    licencia y la atribución de cada capa tomadas de su `.procedencia.json`."""
    salida = tmp_path / "salida"
    assert run(entrada, salida, "28043") == 0
    gpx = ET.parse(salida / "kit/28043/tramos.gpx").getroot()
    kml = ET.parse(salida / "kit/28043/tramos.kml").getroot()
    metadata = gpx.findtext(f"{GPX}metadata/{GPX}desc") or ""
    document = kml.findtext(f"{KML}Document/{KML}description") or ""
    for text in (metadata, document):
        for layer in ("vias_pecuarias", "discrepancias"):
            sidecar = json.loads(
                (entrada / layer / "28043.geojson.procedencia.json").read_text(encoding="utf-8")
            )
            assert sidecar["fuente"] in text
            assert sidecar["licencia"] in text
            attribution = sidecar["atribucion"]
            for item in [attribution] if isinstance(attribution, str) else attribution:
                assert item in text


def test_ca4_sin_candidatos_el_resumen_lo_dice_y_sin_capas_sale_con_1(
    entrada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dado un municipio sin fichero publicado de `candidatos` cuando se ejecuta entonces el kit
    se genera con las demás capas y el resumen dice qué capas incluyó y cuáles faltaban; si no
    hay ninguna capa publicada sale con 1 sin escribir."""
    salida = tmp_path / "salida"
    assert run(entrada, salida, "28043") == 0
    out = capsys.readouterr().out
    assert "capas incluidas: vias_pecuarias, discrepancias" in out
    assert "capas que faltaban: camino_actual, candidatos" in out
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    otra = tmp_path / "otra"
    assert run(vacio, otra, "28043") == 1
    assert kit_files(otra) == []


def test_ca5_sin_aviso_o_propiedad_no_permitida_falla_sin_escribir(
    entrada: Path, tmp_path: Path
) -> None:
    """Dado un fichero publicado sin aviso, o con una propiedad que no está en la lista blanca
    de la ficha, cuando se exporta entonces falla (todo o nada, sale con 1, no escribe) en lugar
    de omitir el aviso o copiar propiedades arbitrarias."""
    salida = tmp_path / "a"
    edit_geojson(
        entrada, "discrepancias", lambda d: d["features"][1]["properties"].update(aviso=None)
    )
    assert run(entrada, salida, "28043") == 1
    assert kit_files(salida) == []

    shutil.rmtree(entrada)
    shutil.copytree(FIXTURES, entrada)
    salida = tmp_path / "b"
    edit_geojson(
        entrada, "vias_pecuarias", lambda d: d["features"][0]["properties"].update(extra="x")
    )
    assert run(entrada, salida, "28043") == 1
    assert kit_files(salida) == []


@pytest.mark.parametrize("key", ["titular", "propietario", "referencia_catastral", "refcat"])
def test_ca6_propiedad_de_titularidad_o_catastral_falla(
    entrada: Path, tmp_path: Path, key: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dado un fichero de entrada con alguna propiedad de titularidad o referencia catastral
    cuando se exporta entonces la exportación falla; ninguna propiedad fuera de la lista blanca
    llega al GPX/KML."""
    salida = tmp_path / "salida"
    edit_geojson(
        entrada, "discrepancias", lambda d: d["features"][0]["properties"].update({key: "x"})
    )
    assert run(entrada, salida, "28043") == 1
    assert "titularidad o referencia catastral" in capsys.readouterr().err
    assert kit_files(salida) == []


def test_ca7_procedencia_indice_y_tamano_maximo(
    entrada: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dado el kit generado cuando se escribe el `.procedencia.json` del fichero entonces lleva
    las capas de origen, fecha de generación y licencia, y el fichero de índice
    `site/datos/kit/indice.json` lista municipios y tamaños; ningún fichero pasa de 3.000.000
    bytes (si pasa, falla sin escribir)."""
    salida = tmp_path / "salida"
    assert run(entrada, salida, "28043") == 0
    for extension in ("gpx", "kml"):
        sidecar = json.loads(
            (salida / f"kit/28043/tramos.{extension}.procedencia.json").read_text(encoding="utf-8")
        )
        assert [c["capa"] for c in sidecar["capas"]] == ["vias_pecuarias", "discrepancias"]
        assert sidecar["fecha_generacion"]
        assert "CC BY 4.0" in sidecar["licencia"]
    index = json.loads((salida / "kit/indice.json").read_text(encoding="utf-8"))
    entry = index["municipios"][0]
    assert entry["ine"] == "28043"
    assert entry["ficheros"]["gpx"]["bytes"] == (salida / "kit/28043/tramos.gpx").stat().st_size
    assert entry["ficheros"]["kml"]["bytes"] == (salida / "kit/28043/tramos.kml").stat().st_size
    assert all(p.stat().st_size <= 3_000_000 for p in kit_files(salida))

    import parcel_intel.adapters.kit_campo.sink as sink

    monkeypatch.setattr(sink, "MAX_KIT_FILE_BYTES", 100)
    otra = tmp_path / "otra"
    assert run(entrada, otra, "28043") == 1
    assert kit_files(otra) == []


def test_ca8_reproducible_byte_a_byte(entrada: Path, tmp_path: Path) -> None:
    """Dado el mismo municipio y los mismos ficheros de entrada cuando se ejecuta dos veces
    entonces el resultado es idéntico byte a byte (reproducible)."""
    uno, dos = tmp_path / "uno", tmp_path / "dos"
    assert run(entrada, uno, "28043") == 0
    assert run(entrada, dos, "28043") == 0
    first = kit_files(uno)
    assert first
    assert [p.relative_to(uno) for p in first] == [p.relative_to(dos) for p in kit_files(dos)]
    for path in first:
        assert path.read_bytes() == (dos / path.relative_to(uno)).read_bytes()
