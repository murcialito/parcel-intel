"""Historia #86: publicar los municipios restantes del ámbito y comprobar el peso del sitio."""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.cli import main as cli
from parcel_intel.cli.main import AMBITO_HITO_INE
from tests.fixtures.published_layers import (
    line_feature,
    provenance,
    synthetic_layer,
    write_real_derived_layers,
    zigzag,
)

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
LAYERS = ("vias_pecuarias", "camino_actual")
BELMONTE = "28019"
LON_MIN, LON_MAX, LAT_MIN, LAT_MAX = -3.62 - 0.3, -3.15 + 0.1, 39.98 - 0.2, 40.22 + 0.1
FORBIDDEN_KEYS = ("propietario", "titular", "titularidad", "owner")


def _load_script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


peso = _load_script("comprobar_peso_sitio")
construir_sitio = _load_script("construir_sitio")


@pytest.fixture(scope="module")
def real_derived(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("real86")
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


def _publish_ambito(derived: Path, salida: Path) -> int:
    return _run(["publicar-capas", "--ambito", "--entrada", str(derived), "--salida", str(salida)])


def _load(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _positions(value: Any) -> list[tuple[float, float]]:
    if value and isinstance(value[0], int | float):
        return [(float(value[0]), float(value[1]))]
    return [position for item in value for position in _positions(item)]


def test_ca1_ambito_completo_sin_ficheros_vacios(
    real_derived: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dado el resultado de `publicar-capas` para los 7 municipios del ámbito, cuando se lista
    `site/datos/`, entonces hay un GeoJSON y su `.procedencia.json` por cada capa y municipio con
    datos, y ningún municipio sin datos queda con fichero vacío (se documenta en la salida del
    comando cuáles no tienen)."""
    salida = tmp_path / "datos"

    assert _publish_ambito(real_derived, salida) == 0

    out = capsys.readouterr().out
    assert len(AMBITO_HITO_INE) == 7
    published = 0
    for layer in LAYERS:
        for ine in AMBITO_HITO_INE:
            geojson = salida / layer / f"{ine}.geojson"
            if (layer, ine) == ("vias_pecuarias", BELMONTE):
                assert not geojson.exists()
                assert f"capa vacía, no se publica: vias_pecuarias {BELMONTE}" in out
                continue
            assert geojson.is_file()
            assert (salida / layer / f"{ine}.geojson.procedencia.json").is_file()
            assert _load(geojson)["features"], f"{geojson} vacío"
            published += 1
    assert published == 13


def test_ca2_procedencia_publicable_epsg4326_sin_titularidad(
    real_derived: Path, tmp_path: Path
) -> None:
    """Dado un fichero publicado, cuando se lee su `.procedencia.json`, entonces trae fuente, URL,
    fecha de descarga, licencia y `redistribucion: publicable`, y el GeoJSON está en EPSG:4326 sin
    datos de titularidad."""
    salida = tmp_path / "datos"
    assert _publish_ambito(real_derived, salida) == 0

    for sidecar in sorted(salida.glob("*/*.geojson.procedencia.json")):
        content = _load(sidecar)
        for field in ("fuente", "url", "fecha_descarga", "licencia"):
            assert isinstance(content[field], str) and content[field].strip()
        assert content["redistribucion"] == "publicable"
        geojson = _load(sidecar.with_name(sidecar.name.removesuffix(".procedencia.json")))
        assert "crs" not in geojson or "4326" in json.dumps(geojson["crs"])
        text = json.dumps(geojson).lower()
        assert not any(key in text for key in FORBIDDEN_KEYS)
        for feature in geojson["features"]:
            for lon, lat in _positions(feature["geometry"]["coordinates"]):
                assert LON_MIN <= lon <= LON_MAX
                assert LAT_MIN <= lat <= LAT_MAX


def test_ca3_selector_alimentado_por_el_indice_estatico(
    real_derived: Path, tmp_path: Path
) -> None:
    """Dado el visor de #85, cuando se abre el selector de municipio, entonces aparecen los 7
    municipios del ámbito (nombre y código INE) y al elegir cada uno se cargan sus capas; el
    selector se alimenta de un índice estático (p. ej. `site/datos/indice.json`) generado por
    `publicar-capas`/`construir_sitio.py`, no de una lista escrita a mano en el HTML."""
    salida = tmp_path / "datos"
    assert _publish_ambito(real_derived, salida) == 0

    index = _load(salida / "indice.json")
    assert sorted(entry["ine"] for entry in index["municipios"]) == sorted(AMBITO_HITO_INE)
    for entry in index["municipios"]:
        assert entry["nombre"].strip()
        assert entry["capas"], entry["ine"]
        for relative in entry["capas"].values():
            assert (salida / relative).is_file()
    # El selector no lleva municipios escritos a mano: se rellena desde el índice.
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert "<option" not in html
    assert 'indice: "datos/indice.json"' in (SITE / "config.js").read_text(encoding="utf-8")
    # El sitio versionado trae ya los 7 municipios.
    committed = _load(SITE / "datos" / "indice.json")
    assert sorted(entry["ine"] for entry in committed["municipios"]) == sorted(AMBITO_HITO_INE)


def test_ca4_comprobacion_de_peso_falla_nombrando_fichero_y_tamano(tmp_path: Path) -> None:
    """Dado `site/` construido, cuando se ejecuta una comprobación de peso, entonces falla con un
    mensaje que nombra el fichero y su tamaño si algún GeoJSON supera 3 MB, la suma de `site/`
    supera 40 MB o un municipio supera 8 MB por pantalla, y pasa si no. Se prueba con fixtures
    sintéticas de tamaño controlado (sin red)."""

    def write(site: Path, relative: str, size: int) -> None:
        path = site / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)

    ligero = tmp_path / "ligero"
    write(ligero, "datos/camino_actual/28001.geojson", 3_000_000)
    assert peso.comprobar(ligero) == []

    fichero = tmp_path / "fichero"
    write(fichero, "datos/camino_actual/28002.geojson", 3_000_001)
    errors = peso.comprobar(fichero)
    assert any("28002.geojson" in e and "3000001" in e for e in errors)

    pantalla = tmp_path / "pantalla"
    for layer in ("a", "b", "c"):
        write(pantalla, f"datos/{layer}/28003.geojson", 2_900_000)
    assert any("28003" in e and "8700000" in e for e in peso.comprobar(pantalla))

    total = tmp_path / "total"
    for i in range(5):
        write(total, f"vendor/f{i}.bin", 8_500_000)
    assert any("42500000" in e for e in peso.comprobar(total))
    assert peso.main(str(total)) == 1

    # El sitio versionado de verdad pasa la comprobación.
    assert peso.comprobar(SITE) == []


def test_ca5_simplifica_solo_lo_que_supera_el_umbral(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dado un fichero que supere el umbral, cuando se ejecuta la simplificación, entonces la
    geometría se simplifica con una tolerancia métrica explícita (en EPSG:25830 antes de
    reproyectar), conserva el tipo de geometría y no deja líneas vacías; la tolerancia y el
    antes/después de tamaño se anotan en el `.procedencia.json`. Si no hay ficheros sobre umbral,
    no se simplifica nada."""
    monkeypatch.setattr(cli, "PUBLISH_SIZE_THRESHOLD_BYTES", 20_000)
    derived = tmp_path / "derived"
    # SINTÉTICA: un camino pesado y otro ligero, en municipios distintos.
    synthetic_layer(
        derived,
        "camino_actual",
        "28997",
        [
            line_feature(
                "900001",
                [zigzag(0, 100, 800), zigzag(0, 200, 800)],
                procedencia=provenance("camino_actual"),
            )
        ],
    )
    synthetic_layer(
        derived,
        "camino_actual",
        "28998",
        [line_feature("900002", [zigzag(0, 300, 4)], procedencia=provenance("camino_actual"))],
    )
    salida = tmp_path / "datos"

    code = _run(
        [
            "publicar-capas",
            "--entrada",
            str(derived),
            "--salida",
            str(salida),
            "--municipio",
            "28997",
            "--municipio",
            "28998",
            "--capa",
            "camino_actual",
        ]
    )

    assert code == 0
    pesado = _load(salida / "camino_actual" / "28997.geojson.procedencia.json")
    simplification = pesado["transformacion"]["simplificacion"]
    assert simplification["tolerancia_m"] == 2.0
    assert simplification["bytes_antes"] > 20_000 > simplification["bytes_despues"]
    geometry = _load(salida / "camino_actual" / "28997.geojson")["features"][0]["geometry"]
    assert geometry["type"] == "MultiLineString"
    assert len(geometry["coordinates"]) == 2
    assert all(len(line) >= 2 for line in geometry["coordinates"])
    ligero = _load(salida / "camino_actual" / "28998.geojson.procedencia.json")
    assert ligero["transformacion"]["simplificacion"] is None


def test_ca6_el_peso_del_ambito_real_cabe_y_el_aviso_remite_a_teselas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dado el informe final de la PR, cuando se revisa, entonces incluye una tabla con el peso por
    municipio y capa y el total de `site/`, y si algún municipio sigue sobre umbral tras
    simplificar, la PR documenta el disparador para pasar a teselas vectoriales (`.pmtiles`) en
    lugar de forzar la simplificación. (La tabla vive en la PR; aquí se comprueba que el sitio
    publicado respeta los umbrales y que un fallo remite a las teselas.)"""
    assert peso.comprobar(SITE) == []
    gordo = tmp_path / "site"
    (gordo / "datos" / "camino_actual").mkdir(parents=True)
    (gordo / "datos" / "camino_actual" / "28013.geojson").write_bytes(b"x" * 3_000_001)

    assert peso.main(str(gordo)) == 1

    assert "pmtiles" in capsys.readouterr().err


@pytest.mark.integration
def test_ca7_el_sitio_publicado_no_referencia_ficheros_inexistentes(tmp_path: Path) -> None:
    """Dado el sitio generado, cuando se despliega (workflow de #41), entonces los 7 municipios
    cargan en el visor publicado sin errores 404 en consola. (Sin navegador: se construye el
    sitio como el workflow y se comprueba que cada ruta del índice existe en el resultado.)"""
    destino = tmp_path / "_site"

    assert construir_sitio.main(str(SITE), str(destino)) == 0

    index = _load(destino / "datos" / "indice.json")
    assert len(index["municipios"]) == 7
    for entry in index["municipios"]:
        for relative in entry["capas"].values():
            assert (destino / "datos" / relative).is_file(), relative
            assert (destino / "datos" / f"{relative}.procedencia.json").is_file()
    # El paso "Comprobar peso" en desplegar.yml queda pendiente del fundador: el token de los
    # agentes no tiene permiso `workflows` (ver la PR). Mientras, `pytest` ya lo vigila (CA4/CA6).
    assert peso.comprobar(destino) == []
