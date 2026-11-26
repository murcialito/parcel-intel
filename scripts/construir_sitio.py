"""Construye el sitio estático a publicar en GitHub Pages (historia #41).

Uso: python3 scripts/construir_sitio.py <origen> <destino>

Es la última barrera antes de publicar: ningún fichero de datos llega a
``destino`` sin un ``<nombre>.procedencia.json`` que declare fuente, URL, fecha de
descarga, licencia y ``redistribucion: "publicable"``. Se valida todo primero y
``destino`` solo se escribe si todo pasa. Solo stdlib.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

DATA_EXTENSIONS = frozenset(
    {".geojson", ".json", ".gml", ".xml", ".pmtiles", ".tif", ".csv"}
)
PROVENANCE_SUFFIX = ".procedencia.json"
REQUIRED_FIELDS = ("fuente", "url", "fecha_descarga", "licencia", "redistribucion")
PUBLISHABLE = "publicable"
FORBIDDEN_DIRS = frozenset({"data"})


def _check_provenance(path: Path) -> list[str]:
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{path}: procedencia ilegible ({exc})"]
    if not isinstance(content, dict):
        return [f"{path}: la procedencia debe ser un objeto JSON"]
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        value = content.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{path}: falta el campo '{field}' o está vacío")
    redistribution = content.get("redistribucion")
    if isinstance(redistribution, str) and redistribution != PUBLISHABLE:
        errors.append(
            f"{path}: campo 'redistribucion' es {redistribution!r}, "
            f"debe ser {PUBLISHABLE!r}"
        )
    return errors


def _validate(origen: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(origen.rglob("*")):
        rel = path.relative_to(origen)
        if path.is_dir():
            if path.name in FORBIDDEN_DIRS:
                errors.append(f"{rel}: directorio no publicable en el sitio")
            continue
        if any(part in FORBIDDEN_DIRS for part in rel.parts[:-1]):
            continue  # ya señalado por su directorio
        name = path.name
        if name.endswith(".env") or name == ".env":
            errors.append(f"{rel}: fichero de entorno no publicable")
        elif name.endswith(PROVENANCE_SUFFIX):
            if not path.with_name(name[: -len(PROVENANCE_SUFFIX)]).is_file():
                errors.append(f"{rel}: procedencia sin su fichero de datos")
            errors.extend(_check_provenance(path))
        elif path.suffix.lower() in DATA_EXTENSIONS:
            sidecar = path.with_name(name + PROVENANCE_SUFFIX)
            if not sidecar.is_file():
                errors.append(f"{rel}: fichero de datos sin {name}{PROVENANCE_SUFFIX}")
    return errors


def main(origen: str, destino: str) -> int:
    src = Path(origen)
    dst = Path(destino)
    if not src.is_dir():
        print(f"error: {src} no es un directorio", file=sys.stderr)
        return 2
    errors = _validate(src)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    (dst / ".nojekyll").touch()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("uso: construir_sitio.py <origen> <destino>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
