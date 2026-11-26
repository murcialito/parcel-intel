"""Comprueba que el sitio estático sigue siendo ligero (historia #86).

Uso: python3 scripts/comprobar_peso_sitio.py <sitio>

Falla (código 1) y nombra el fichero o municipio y su tamaño si:
- algún GeoJSON de ``datos/<capa>/<ine>.geojson`` supera 3 MB;
- la suma de todo el sitio supera 40 MB;
- lo que carga una pantalla (todas las capas de un municipio) supera 8 MB.

Si se superan, el camino no es forzar la simplificación sino pasar a teselas
vectoriales (.pmtiles), según el ADR del visor (#85). Solo stdlib.
"""

from __future__ import annotations

import sys
from pathlib import Path

MAX_GEOJSON_BYTES = 3_000_000
MAX_SITE_BYTES = 40_000_000
MAX_SCREEN_BYTES = 8_000_000


def comprobar(sitio: Path) -> list[str]:
    errors: list[str] = []
    total = 0
    screens: dict[str, int] = {}
    for path in sorted(sitio.rglob("*")):
        if not path.is_file():
            continue
        size = path.stat().st_size
        total += size
        rel = path.relative_to(sitio)
        if path.suffix.lower() == ".geojson":
            if size > MAX_GEOJSON_BYTES:
                errors.append(
                    f"{rel}: {size} bytes, supera el umbral de "
                    f"{MAX_GEOJSON_BYTES} bytes por fichero"
                )
            if rel.parts[0] == "datos" and len(rel.parts) == 3:
                screens[path.stem] = screens.get(path.stem, 0) + size
    for ine, size in sorted(screens.items()):
        if size > MAX_SCREEN_BYTES:
            errors.append(
                f"municipio {ine}: {size} bytes por pantalla, supera el umbral de "
                f"{MAX_SCREEN_BYTES} bytes"
            )
    if total > MAX_SITE_BYTES:
        errors.append(
            f"{sitio}: {total} bytes en total, supera el umbral de {MAX_SITE_BYTES} bytes"
        )
    return errors


def main(sitio: str) -> int:
    path = Path(sitio)
    if not path.is_dir():
        print(f"error: {path} no es un directorio", file=sys.stderr)
        return 2
    errors = comprobar(path)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        print(
            "Si no basta con simplificar, el siguiente paso son teselas vectoriales "
            "(.pmtiles), ver el ADR del visor (#85).",
            file=sys.stderr,
        )
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("uso: comprobar_peso_sitio.py <sitio>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
