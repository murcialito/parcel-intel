"""Fixture SINTÉTICA del inventario de códigos (historia #288). Nada es real.

Regenera `curated/28043/inventario.json`:

    uv run python -m tests.fixtures.candidatos_inventario.generar

Asigna `COL-001` al candidato «aprobado» y `COL-002-Camino de Uceda` al «propuesto» de
`tests/fixtures/candidatos_revision/` (los `candidate_id` salen de ese generador). Los
tests aprueban el segundo en una copia para tener dos aprobados vigentes. Los códigos
reales los escribe el fundador en `curated/candidatos/28043/inventario.json`.
"""

import json
from pathlib import Path

from tests.fixtures.candidatos_revision import generar as revision

DIRECTORY = Path(__file__).resolve().parent
INE = revision.INE


def inventory_document() -> dict[str, object]:
    found = revision.candidates()
    return {
        "municipio": INE,
        "prefijo": "COL",
        "codigos": [
            {"candidate_id": found["aprobado"].candidate_id, "codigo": "COL-001"},
            {
                "candidate_id": found["propuesto"].candidate_id,
                "codigo": "COL-002-Camino de Uceda",
            },
        ],
    }


def texts() -> dict[Path, str]:
    text = json.dumps(inventory_document(), ensure_ascii=False, indent=1) + "\n"
    return {Path("curated") / INE / "inventario.json": text}


def main() -> None:
    for relative, text in texts().items():
        path = DIRECTORY / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
