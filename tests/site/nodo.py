"""Lanza los tests de módulo del visor (`tests/site/visor.test.mjs`) con `node --test`.

Historia #85 (ADR 0037): los módulos de `site/` se copian a un directorio temporal con un
`package.json` `{"type": "module"}` para que Node los cargue como ES modules sin tocar `site/`
(que no debe llevar `package.json`: sería un `.json` sin procedencia). Si `node` no está en el
`PATH`, el test **falla** con un mensaje claro; no se salta (lección de #44).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from parcel_intel.domain.public_card import BANNED_WORDS
from parcel_intel.domain.published_discrepancy import CADASTRAL_REFERENCE_RE

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
TEST_FILE = Path(__file__).with_name("visor.test.mjs")
FIXTURES = ROOT / "tests" / "fixtures" / "visor" / "datos"
CANDIDATOS = ROOT / "tests" / "fixtures" / "site" / "candidatos_28043.geojson"
CANDIDATOS_IMG = ROOT / "tests" / "fixtures" / "site" / "candidatos_comparacion_28043.geojson"
CANDIDATOS_IDEM = ROOT / "tests" / "fixtures" / "site" / "candidatos_comparacion_idem_28043.geojson"
DISENO = ROOT / "docs" / "design-system" / "site" / "js" / "estilos-capas.js"
MODULOS = ("config.js", "controlador.js", "enlace.js", "estilos-capas.js", "mapa.js", "vista.js")


@dataclass(frozen=True)
class NodeResult:
    returncode: int
    output: str
    passed: int
    failed: int


def _count(output: str, label: str) -> int:
    match = re.search(rf"^# {label} (\d+)$", output, re.MULTILINE)
    return int(match.group(1)) if match else -1


def run_node_tests(pattern: str, workdir: Path) -> NodeResult:
    """Ejecuta los tests cuyo nombre casa con `pattern` (regex de `--test-name-pattern`)."""
    node = shutil.which("node")
    assert node is not None, (
        "No se encuentra `node` en el PATH: los tests del visor (historia #85) lo necesitan. "
        "En CI viene en la imagen ubuntu-latest; en local, instala Node >= 18."
    )
    copia = workdir / "visor"
    copia.mkdir(parents=True, exist_ok=True)
    for nombre in MODULOS:
        shutil.copyfile(SITE / nombre, copia / nombre)
    (copia / "package.json").write_text(json.dumps({"type": "module"}), encoding="utf-8")
    env = {
        **os.environ,
        "VISOR_DIR": str(copia),
        "VISOR_FIXTURES": str(FIXTURES),
        "VISOR_DATOS": str(SITE / "datos"),
        # Fichero publicado de tramos a verificar, sintético (historia #171).
        "VISOR_CANDIDATOS": str(CANDIDATOS),
        # El mismo con `imagenes_comparacion` y el bloque `comparacion` de #172 (historia #178).
        "VISOR_CANDIDATOS_IMG": str(CANDIDATOS_IMG),
        # Publicado con imágenes de la IDEM (1975 y 1991), caso de dos ventanas (historia #208).
        "VISOR_CANDIDATOS_IDEM": str(CANDIDATOS_IDEM),
        # Original del sistema de diseño, contra el que se compara estilos-capas.js (#165 CA1).
        "VISOR_DISENO": str(DISENO),
        "VISOR_REFCAT_RE": CADASTRAL_REFERENCE_RE.pattern,
        "VISOR_BANNED_WORDS": json.dumps([w.lower() for w in BANNED_WORDS]),
    }
    proceso = subprocess.run(
        [
            node,
            "--test",
            "--test-reporter=tap",
            f"--test-name-pattern={pattern}",
            str(TEST_FILE),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
        timeout=120,
        check=False,
    )
    salida = proceso.stdout + proceso.stderr
    return NodeResult(
        returncode=proceso.returncode,
        output=salida,
        passed=_count(salida, "pass"),
        failed=_count(salida, "fail"),
    )


def assert_node_tests_pass(pattern: str, workdir: Path, minimum: int = 1) -> NodeResult:
    """Exige que haya al menos `minimum` tests que casen y que ninguno falle."""
    resultado = run_node_tests(pattern, workdir)
    assert resultado.returncode == 0 and resultado.failed == 0, resultado.output
    assert resultado.passed >= minimum, (
        f"solo {resultado.passed} tests casan con {pattern!r} (mínimo {minimum}):\n"
        f"{resultado.output}"
    )
    return resultado


def volcar_base(workdir: Path) -> dict[str, object]:
    """`BASE` de `site/estilos-capas.js` como JSON (historia #166, CA2), sin tocar `site/`."""
    node = shutil.which("node")
    assert node is not None, "No se encuentra `node` en el PATH."
    copia = workdir / "base"
    copia.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SITE / "estilos-capas.js", copia / "estilos-capas.js")
    (copia / "package.json").write_text(json.dumps({"type": "module"}), encoding="utf-8")
    proceso = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            'import { BASE } from "./estilos-capas.js"; console.log(JSON.stringify(BASE));',
        ],
        capture_output=True,
        text=True,
        cwd=copia,
        timeout=60,
        check=False,
    )
    assert proceso.returncode == 0, proceso.stderr
    base: dict[str, object] = json.loads(proceso.stdout)
    return base
