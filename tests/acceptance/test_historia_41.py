"""Aceptación de la historia #41: despliegue automático en GitHub Pages."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "construir_sitio.py"
WORKFLOW = ROOT / ".github" / "workflows" / "desplegar.yml"

VALID = {
    "fuente": "IGN",
    "url": "https://example.org/capa",
    "fecha_descarga": "2026-11-26",
    "licencia": "CC BY 4.0",
    "redistribucion": "publicable",
}


def _run(site: Path, out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(site), str(out)],
        capture_output=True,
        text=True,
        check=False,
    )


def _site(tmp_path: Path) -> tuple[Path, Path]:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<html></html>", encoding="utf-8")
    return site, tmp_path / "_site"


def _add_data(site: Path, procedencia: dict[str, str] | None) -> None:
    (site / "capa.geojson").write_text("{}", encoding="utf-8")
    if procedencia is not None:
        (site / "capa.geojson.procedencia.json").write_text(
            json.dumps(procedencia), encoding="utf-8"
        )


def test_ca1_solo_index_html(tmp_path: Path) -> None:
    """Dado un `site/` con solo `index.html`, cuando se ejecuta
    `python3 scripts/construir_sitio.py site _site`, entonces `_site/` contiene
    `index.html` y un fichero `.nojekyll`, y el código de salida es 0."""
    site, out = _site(tmp_path)
    result = _run(site, out)
    assert result.returncode == 0
    assert (out / "index.html").is_file()
    assert (out / ".nojekyll").is_file()


@pytest.mark.parametrize(
    "name",
    ["a.geojson", "a.json", "a.gml", "a.xml", "a.pmtiles", "a.tif", "a.csv"],
)
def test_ca2_dato_sin_procedencia_falla(tmp_path: Path, name: str) -> None:
    """Dado un `site/` con un fichero de datos (`.geojson`, `.json`, `.gml`, `.xml`,
    `.pmtiles`, `.tif`, `.csv`) sin `<nombre>.procedencia.json` al lado, cuando se
    ejecuta el script, entonces falla con código ≠ 0, el mensaje nombra el fichero y
    no se crea `_site/`."""
    site, out = _site(tmp_path)
    (site / name).write_text("x", encoding="utf-8")
    result = _run(site, out)
    assert result.returncode != 0
    assert name in result.stderr
    assert not out.exists()


def test_ca3_dato_publicable_se_copia(tmp_path: Path) -> None:
    """Dado un fichero de datos con `.procedencia.json` que contiene `fuente`, `url`,
    `fecha_descarga`, `licencia` y `redistribucion: "publicable"`, cuando se ejecuta
    el script, entonces el fichero de datos se copia a `_site/`."""
    site, out = _site(tmp_path)
    _add_data(site, VALID)
    result = _run(site, out)
    assert result.returncode == 0, result.stderr
    assert (out / "capa.geojson").is_file()


def test_ca4_redistribucion_no_publicable_falla(tmp_path: Path) -> None:
    """Dado un `.procedencia.json` con `redistribucion` distinto de `"publicable"`
    (p. ej. `"solo_uso_interno"`) o al que le falta alguno de los cinco campos, cuando
    se ejecuta el script, entonces falla con código ≠ 0 y el mensaje nombra el fichero
    y el campo problemático."""
    site, out = _site(tmp_path)
    _add_data(site, {**VALID, "redistribucion": "solo_uso_interno"})
    result = _run(site, out)
    assert result.returncode != 0
    assert "capa.geojson.procedencia.json" in result.stderr
    assert "redistribucion" in result.stderr
    assert not out.exists()


@pytest.mark.parametrize("campo", list(VALID))
def test_ca4_falta_un_campo_falla(tmp_path: Path, campo: str) -> None:
    """CA4 (campo ausente): el mensaje nombra el fichero y el campo problemático."""
    site, out = _site(tmp_path)
    _add_data(site, {k: v for k, v in VALID.items() if k != campo})
    result = _run(site, out)
    assert result.returncode != 0
    assert "capa.geojson.procedencia.json" in result.stderr
    assert campo in result.stderr
    assert not out.exists()


def test_ca5_directorio_data_falla(tmp_path: Path) -> None:
    """Dado un `site/` que contiene un directorio `data/`, cuando se ejecuta el
    script, entonces falla con código ≠ 0."""
    site, out = _site(tmp_path)
    (site / "data").mkdir()
    (site / "data" / "x.txt").write_text("x", encoding="utf-8")
    result = _run(site, out)
    assert result.returncode != 0
    assert not out.exists()


def test_ca5_fichero_env_falla(tmp_path: Path) -> None:
    """Dado un `site/` que contiene un fichero `*.env`, cuando se ejecuta el script,
    entonces falla con código ≠ 0."""
    site, out = _site(tmp_path)
    (site / "prod.env").write_text("K=V", encoding="utf-8")
    result = _run(site, out)
    assert result.returncode != 0
    assert "prod.env" in result.stderr


def test_ca5_procedencia_huerfana_falla(tmp_path: Path) -> None:
    """Dado un `site/` que contiene un `.procedencia.json` sin su fichero de datos,
    cuando se ejecuta el script, entonces falla con código ≠ 0."""
    site, out = _site(tmp_path)
    (site / "capa.geojson.procedencia.json").write_text(
        json.dumps(VALID), encoding="utf-8"
    )
    result = _run(site, out)
    assert result.returncode != 0
    assert not out.exists()


def test_ca6_workflow_usa_el_script_y_no_usa_secrets() -> None:
    """Dado `.github/workflows/desplegar.yml`, cuando se lee, entonces el paso
    "Construir" invoca `scripts/construir_sitio.py`, el workflow no usa secrets ni
    llama a un LLM, y mantiene `if: github.event.repository.private == false`."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/construir_sitio.py" in text
    assert "secrets." not in text
    for word in ("deepseek", "anthropic", "openai", "llm"):
        assert word not in text.lower()
    assert "if: github.event.repository.private == false" in text


@pytest.mark.integration
def test_ca7_pages_sirve_index() -> None:
    """[integración] Dado el repo ya público (#39) y Pages configurado con origen
    "GitHub Actions", cuando se hace push a `main`, entonces el workflow `Desplegar`
    termina en verde y la URL de Pages sirve `index.html`."""
    pytest.skip("Requiere el repo público (#39) y Pages activado: verificación posterior")
