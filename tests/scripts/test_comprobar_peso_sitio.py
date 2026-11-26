"""`scripts/comprobar_peso_sitio.py` con ficheros SINTÉTICOS de tamaño controlado."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load() -> Any:
    spec = importlib.util.spec_from_file_location(
        "comprobar_peso_sitio", ROOT / "scripts" / "comprobar_peso_sitio.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


peso = _load()


def _write(site: Path, relative: str, size: int) -> None:
    path = site / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_sitio_ligero_pasa(tmp_path: Path) -> None:
    _write(tmp_path, "datos/vias_pecuarias/28001.geojson", 1000)
    _write(tmp_path, "datos/camino_actual/28001.geojson", 2000)

    assert peso.comprobar(tmp_path) == []
    assert peso.main(str(tmp_path)) == 0


def test_geojson_sobre_umbral_nombra_fichero_y_tamano(tmp_path: Path) -> None:
    _write(tmp_path, "datos/camino_actual/28013.geojson", 3_000_001)

    errors = peso.comprobar(tmp_path)

    assert any("datos/camino_actual/28013.geojson" in e and "3000001" in e for e in errors)


def test_exactamente_en_el_umbral_pasa(tmp_path: Path) -> None:
    _write(tmp_path, "datos/camino_actual/28013.geojson", 3_000_000)

    assert peso.comprobar(tmp_path) == []


def test_pantalla_sobre_umbral_nombra_municipio(tmp_path: Path) -> None:
    for layer in ("camino_actual", "vias_pecuarias", "otra"):
        _write(tmp_path, f"datos/{layer}/28013.geojson", 2_900_000)

    errors = peso.comprobar(tmp_path)

    assert len(errors) == 1
    assert "municipio 28013" in errors[0] and "8700000" in errors[0]


def test_suma_del_sitio_sobre_umbral(tmp_path: Path) -> None:
    for i in range(5):
        _write(tmp_path, f"vendor/f{i}.bin", 8_500_000)

    errors = peso.comprobar(tmp_path)

    assert len(errors) == 1
    assert "42500000" in errors[0]


def test_main_falla_con_codigo_1_y_sugiere_teselas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "datos/camino_actual/28013.geojson", 3_000_001)

    assert peso.main(str(tmp_path)) == 1
    assert "pmtiles" in capsys.readouterr().err


def test_directorio_inexistente_sale_con_2(tmp_path: Path) -> None:
    assert peso.main(str(tmp_path / "no")) == 2


def test_discrepancias_cuenta_en_fichero_pantalla_y_total(tmp_path: Path) -> None:
    _write(tmp_path, "datos/discrepancias/28043.geojson", 3_000_001)
    errors = peso.comprobar(tmp_path)
    assert any("datos/discrepancias/28043.geojson" in e and "3000001" in e for e in errors)

    pantalla = tmp_path / "pantalla"
    for layer in ("discrepancias", "camino_actual"):
        _write(pantalla, f"datos/{layer}/28013.geojson", 2_900_000)
    _write(pantalla, "datos/vias_pecuarias/28013.geojson", 2_300_000)
    (error,) = peso.comprobar(pantalla)
    assert "municipio 28013" in error and "8100000" in error
