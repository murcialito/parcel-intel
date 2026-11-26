"""Historia #50: proteger curated/** con CODEOWNERS y revisión obligatoria del fundador.

Sin red: los scripts se ejecutan con entradas fijas y el workflow se lee como texto.
Los JSON de `gh pr view` son sintéticos (no grabados): reproducen la forma de sus campos.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

RAIZ = Path(__file__).resolve().parents[2]
GH = RAIZ / ".github"
TOCA = GH / "scripts" / "toca_curated.sh"
APROBADA = GH / "scripts" / "aprobada_por_fundador.sh"
FUSIONAR = GH / "workflows" / "fusionar.yml"
ADR = RAIZ / "docs" / "adr" / "0024-merge-por-workflow-no-por-agente.md"

HEAD = "a" * 40
ANTERIOR = "b" * 40


def toca_curated(*rutas: str) -> int:
    return subprocess.run(
        ["bash", str(TOCA)], input="\n".join(rutas) + "\n", text=True, check=False
    ).returncode


def aprobada(datos: dict[str, object]) -> int:
    return subprocess.run(
        ["bash", str(APROBADA)], input=json.dumps(datos), text=True, check=False
    ).returncode


def review(estado: str, autor: str, commit: str) -> dict[str, object]:
    return {"state": estado, "author": {"login": autor}, "commit": {"oid": commit}}


def pr(*reviews: dict[str, object]) -> dict[str, object]:
    return {"headRefOid": HEAD, "reviews": list(reviews)}


def guardia_del_workflow() -> str:
    texto = FUSIONAR.read_text(encoding="utf-8")
    inicio = texto.index("Guardia de curated/**")
    return texto[inicio : texto.index("Con varias historias en paralelo", inicio)]


def test_ca1_codeowners_asigna_curated_al_fundador() -> None:
    """Dado el repo cuando se lee `.github/CODEOWNERS` entonces contiene la regla
    `curated/**` asignada a `@murcialito`."""
    lineas = [
        linea.split()
        for linea in (GH / "CODEOWNERS").read_text(encoding="utf-8").splitlines()
        if linea.strip() and not linea.lstrip().startswith("#")
    ]
    assert ["curated/**", "@murcialito"] in lineas


def test_ca2_toca_curated_distingue_rutas() -> None:
    """Dada una lista de ficheros cambiados que incluye alguno bajo `curated/` cuando se ejecuta
    el script de guardia entonces sale con código que indica "requiere revisión del fundador";
    con rutas sin `curated/` indica "no requiere" (rutas como `docs/curated/x` o
    `curated-notas.md` no cuentan)."""
    assert toca_curated("README.md", "curated/caso-1.json") == 0
    assert toca_curated("curated/a/b.json") == 0
    assert toca_curated("src/x.py", "README.md") == 1
    assert toca_curated("docs/curated/x") == 1
    assert toca_curated("curated-notas.md") == 1
    assert toca_curated("") == 1


def test_ca3_sin_aprobacion_del_fundador_no_se_fusiona() -> None:
    """Dada una PR que toca `curated/**` con CI y `revision` en verde pero sin aprobación de
    `murcialito` sobre el último commit cuando `fusionar.yml` la evalúa entonces no la fusiona y
    lo registra en el log."""
    assert aprobada(pr()) == 1
    assert aprobada(pr(review("APPROVED", "claude-revisor", HEAD))) == 1
    assert aprobada(pr(review("COMMENTED", "murcialito", HEAD))) == 1
    assert aprobada(pr(review("CHANGES_REQUESTED", "murcialito", HEAD))) == 1
    guardia = guardia_del_workflow()
    assert "toca_curated.sh" in guardia and "aprobada_por_fundador.sh" in guardia
    assert re.search(r"no se fusiona", guardia)
    assert "exit 0" in guardia  # sale sin fusionar


def test_ca4_aprobacion_vale_solo_sobre_el_ultimo_commit() -> None:
    """Dada esa misma PR con aprobación de `murcialito` sobre el último commit (review
    `APPROVED`, autor `murcialito`, commit = `headRefOid`) cuando se evalúa entonces se fusiona;
    si se empuja un commit nuevo, la aprobación anterior ya no vale."""
    assert aprobada(pr(review("APPROVED", "murcialito", HEAD))) == 0
    assert aprobada(pr(review("APPROVED", "murcialito", ANTERIOR))) == 1
    # Aprobó el commit viejo y el nuevo no: no vale; aprobó el nuevo además: vale.
    assert aprobada(pr(review("APPROVED", "murcialito", ANTERIOR))) == 1
    assert (
        aprobada(
            pr(review("APPROVED", "murcialito", ANTERIOR), review("APPROVED", "murcialito", HEAD))
        )
        == 0
    )


def test_ca5_sin_curated_el_comportamiento_no_cambia() -> None:
    """Dada una PR que no toca `curated/**` cuando se evalúa entonces el comportamiento de
    `fusionar.yml` no cambia."""
    texto = FUSIONAR.read_text(encoding="utf-8")
    guardia = guardia_del_workflow()
    # La guardia solo actúa dentro de un `if` sobre toca_curated.sh: sin curated/ no cambia nada.
    assert re.search(r"if jq .*toca_curated\.sh; then", guardia)
    assert guardia.count("exit") == 1
    # La fusión sigue siendo la misma, tras la guardia.
    assert texto.index("toca_curated.sh") < texto.index('gh pr merge "$pr"')
    assert '--squash --delete-branch --match-head-commit "$SHA"' in texto
    for condicion in ("checks revision", "veto", "cambios-pedidos", "behind_by"):
        assert condicion in texto


def test_ca6_aprobacion_tardia_reevalua_fusionar() -> None:
    """Dada una aprobación del fundador enviada después de que CI y Revisar terminaran cuando se
    envía entonces `fusionar.yml` se vuelve a evaluar (disparador `pull_request_review`) sin
    intervención adicional."""
    texto = FUSIONAR.read_text(encoding="utf-8")
    cabecera = texto[: texto.index("jobs:")]
    assert re.search(r"pull_request_review:\s*\n\s+types: \[submitted\]", cabecera)
    assert "workflow_run:" in cabecera  # el disparador de siempre se mantiene
    # Con ese evento, rama y SHA salen de la PR.
    assert "github.event.pull_request.head.ref" in texto
    assert "github.event.pull_request.head.sha" in texto
    assert "github.event.review.state == 'approved'" in texto


def test_ca7_adr_0024_documenta_la_guardia_y_los_pasos_manuales() -> None:
    """Dado el ADR 0024 cuando se lee entonces documenta la guardia de `curated/**` y los pasos
    manuales del fundador (protección de rama con code owners)."""
    texto = ADR.read_text(encoding="utf-8")
    assert "curated/**" in texto
    assert "toca_curated.sh" in texto
    assert "pull_request_review" in texto
    assert "Require review from Code Owners" in texto
    assert "Pasos manuales del fundador" in texto
