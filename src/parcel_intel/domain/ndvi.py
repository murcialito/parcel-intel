import math
from dataclasses import dataclass
from datetime import date

from parcel_intel.domain.geometry import BBox
from parcel_intel.domain.provenance import Provenance

Grid = tuple[tuple[float, ...], ...]
"""Valores NDVI en `[-1, 1]`, o `float('nan')` en una celda cuya banda roja
o NIR era `nodata` en la escena de origen — nunca `0.0`, que es un valor
NDVI válido (y distinto de "sin dato")."""
ChangeGrid = tuple[tuple[bool, ...], ...]


class MismatchedNdviGridError(Exception):
    """Dos `NdviGrid` no comparten bbox/srid/forma: no se puede calcular una
    máscara de cambios entre ellos."""


@dataclass(frozen=True)
class NdviGrid:
    values: Grid
    bbox: BBox
    srid: int
    scene_date: date
    cloud_cover_percent: float
    provenance: Provenance


@dataclass(frozen=True)
class ChangeMask:
    changed: ChangeGrid
    bbox: BBox
    srid: int
    before: NdviGrid
    after: NdviGrid
    threshold: float


def _shape(grid: Grid) -> tuple[int, int]:
    return (len(grid), len(grid[0]) if grid else 0)


def compute_change_mask(before: NdviGrid, after: NdviGrid, threshold: float) -> ChangeMask:
    """Compara dos `NdviGrid` de la misma geometría+margen celda a celda.

    Aritmética pura, sin E/S: dos `NdviGrid` de la misma rejilla de salida
    comparten bbox/srid/forma por construcción (ver ADR 0007), así que esto
    no necesita ningún port — vive en `domain/`, igual que `bbox_with_margin`.
    """
    if before.bbox != after.bbox or before.srid != after.srid:
        raise MismatchedNdviGridError(
            "Los dos NdviGrid no comparten bbox/srid: no vienen de la misma geometría+margen"
        )
    if _shape(before.values) != _shape(after.values):
        raise MismatchedNdviGridError(
            f"Los dos NdviGrid tienen formas distintas: "
            f"{_shape(before.values)} != {_shape(after.values)}"
        )
    # Una celda `nan` (sin dato en alguna de las dos bandas de origen) nunca
    # se marca como cambiada, con independencia del umbral: no hay base para
    # afirmar un cambio sin dato en al menos una de las dos fechas. Explícito
    # aquí en vez de confiar en que una comparación con `nan` da `False` por
    # semántica IEEE 754 (correcto, pero no obvio para quien lea el código).
    changed = tuple(
        tuple(
            False if (math.isnan(a) or math.isnan(b)) else abs(a - b) > threshold
            for a, b in zip(row_after, row_before, strict=True)
        )
        for row_after, row_before in zip(after.values, before.values, strict=True)
    )
    return ChangeMask(
        changed=changed,
        bbox=before.bbox,
        srid=before.srid,
        before=before,
        after=after,
        threshold=threshold,
    )
