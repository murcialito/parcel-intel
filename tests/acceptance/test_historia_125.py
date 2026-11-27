"""Historia #125: validador y congelación del conjunto de validación en código de producción."""

import copy
import json
from pathlib import Path

import pytest

from parcel_intel.adapters.validation_cases import casos_schema, congelacion

pytestmark = pytest.mark.acceptance

RAIZ = Path(__file__).resolve().parents[2]
VALIDACION = RAIZ / "docs" / "validacion"


def test_ca1_validar_casos_en_adapters() -> None:
    """Dado el módulo `parcel_intel.adapters.validation_cases.casos_schema`, cuando se llama a
    `validar_casos` con el `casos.json` actual, entonces devuelve la lista vacía, y con un caso
    inválido devuelve los mismos errores que antes del cambio."""
    casos = json.loads((VALIDACION / "casos.json").read_text(encoding="utf-8"))
    assert casos_schema.validar_casos(casos) == []

    roto = copy.deepcopy(casos)
    roto["casos"][0].pop("fuente_url")
    errores = casos_schema.validar_casos(roto)
    assert errores
    assert any("fuente_url" in e for e in errores)


def test_ca2_version_vigente_e_integridad() -> None:
    """Dado el módulo `parcel_intel.adapters.validation_cases.congelacion`, cuando se llama a
    `version_vigente` y `comprobar_integridad` sobre `docs/validacion/`, entonces la versión
    vigente y la huella coinciden con las de `CONGELADO*.md` y no hay errores."""
    casos_path = VALIDACION / "casos.json"
    vigente = congelacion.version_vigente(VALIDACION)
    assert vigente.sha256 == congelacion.calcular_huella(casos_path)
    assert congelacion.comprobar_integridad(VALIDACION, casos_path) == []


def test_ca3_tests_conservados_y_modulos_antiguos_eliminados() -> None:
    """Dado el repo, entonces `tests/validacion/` conserva sus tests (`test_casos.py`,
    `test_congelacion.py`, `test_integridad.py`) importando del nuevo sitio y siguen en verde, y
    ya no existen `tests/validacion/casos_schema.py` ni `tests/validacion/congelacion.py`."""
    carpeta = RAIZ / "tests" / "validacion"
    for nombre in ("test_casos.py", "test_congelacion.py", "test_integridad.py"):
        texto = (carpeta / nombre).read_text(encoding="utf-8")
        assert "parcel_intel.adapters.validation_cases" in texto
        assert "tests.validacion.casos_schema" not in texto
        assert "tests.validacion.congelacion" not in texto
    assert not (carpeta / "casos_schema.py").exists()
    assert not (carpeta / "congelacion.py").exists()


def test_ca4_src_no_importa_de_tests() -> None:
    """Dado el cambio, entonces ningún módulo bajo `src/` importa de `tests/`, y
    `uv run lint-imports`, `mypy`, `ruff` y `pytest` siguen en verde. Hay un test de aceptación
    por criterio en `tests/acceptance/test_historia_<n>.py`."""
    ofensores = []
    for fichero in (RAIZ / "src").rglob("*.py"):
        for linea in fichero.read_text(encoding="utf-8").splitlines():
            parte = linea.strip()
            if parte.startswith(("from tests", "import tests")):
                ofensores.append(f"{fichero.relative_to(RAIZ)}: {parte}")
    assert ofensores == []
