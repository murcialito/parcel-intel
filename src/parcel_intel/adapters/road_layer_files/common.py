"""Piezas comunes de los escritores de capas derivadas (ADR 0030).

Formato común: `FeatureCollection` en EPSG:25830; serialización determinista (claves
ordenadas, redondeo solo al escribir, sin fecha de generación); escritura atómica.
"""

import json
import os
import tempfile
from pathlib import Path

from parcel_intel.domain.provenance import Provenance

CRS = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25830"}}


def provenance_properties(provenance: Provenance) -> dict[str, object]:
    return {
        "fuente": provenance.source,
        "url": provenance.url,
        "fecha_descarga": provenance.retrieved_at.isoformat(),
        "licencia": provenance.license,
    }


def round_coords(points: tuple[tuple[float, float], ...]) -> list[list[float]]:
    return [[round(x, 2), round(y, 2)] for x, y in points]


def dump_collection(collection: dict[str, object]) -> str:
    return (
        json.dumps(
            collection, ensure_ascii=False, sort_keys=True, indent=1, separators=(",", ": ")
        )
        + "\n"
    )


def write_atomic(directory: Path, filename: str, text: str) -> Path:
    """Escribe `directory/filename` con `os.replace`: nunca deja un fichero a medias."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    fd, tmp_name = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(text.encode("utf-8"))
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path
