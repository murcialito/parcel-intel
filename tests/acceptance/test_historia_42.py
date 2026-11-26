"""Historia #42: LICENSE Apache-2.0 y metadatos de pyproject.

Son tests de documentación y configuración: leen `LICENSE`, `pyproject.toml` y
`docs/vision.md`. No llaman a red.
"""

import hashlib
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
LICENSE = REPO / "LICENSE"
PYPROJECT = REPO / "pyproject.toml"
VISION = REPO / "docs" / "vision.md"

# SHA-256 del texto oficial https://www.apache.org/licenses/LICENSE-2.0.txt,
# descargado el 2026-11-26 sin modificar.
SHA256_APACHE_2_0 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def test_ca1_licence_contiene_texto_oficial_apache_2_0() -> None:
    """Dado el repo, cuando se lee `LICENSE` en la raíz, entonces contiene el texto oficial
    completo de la Apache License 2.0, versión 2.0."""
    contenido = LICENSE.read_bytes()
    texto = contenido.decode("utf-8")
    assert "Version 2.0, January 2004" in texto
    assert "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION" in texto
    assert "END OF TERMS AND CONDITIONS" in texto
    assert hashlib.sha256(contenido).hexdigest() == SHA256_APACHE_2_0


def test_ca2_pyproject_declara_licencia_spdx_y_build_hatchling() -> None:
    """Dado `pyproject.toml`, cuando se parsea, entonces `[project]` declara
    `license = "Apache-2.0"` (expresión SPDX) y `license-files = ["LICENSE"]`, y `uv sync`
    y el build con hatchling siguen funcionando."""
    proyecto = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert proyecto["project"]["license"] == "Apache-2.0"
    assert proyecto["project"]["license-files"] == ["LICENSE"]
    assert proyecto["build-system"]["build-backend"] == "hatchling.build"


def test_ca3_vision_licencia_del_codigo_resuelta_apache_2_0() -> None:
    """Dado `docs/vision.md`, cuando se lee la sección de decisiones abiertas, entonces el
    punto "Licencia del código" queda marcado como resuelto: Apache-2.0, fecha 2026-11-25."""
    lineas = VISION.read_text(encoding="utf-8").splitlines()
    inicio = lineas.index("**Decisiones abiertas:**")
    fin = lineas.index("## Convenciones (sin cambios)")
    seccion = lineas[inicio:fin]
    pendientes = [linea for linea in seccion if linea.startswith("- [ ] Licencia del código")]
    resueltas = [linea for linea in seccion if linea.startswith("- [x] Licencia del código")]
    assert pendientes == []
    assert len(resueltas) == 1
    assert "Apache-2.0" in resueltas[0]
    assert "2026-11-25" in resueltas[0]
