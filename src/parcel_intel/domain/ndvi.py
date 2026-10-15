from dataclasses import dataclass
from datetime import date

from parcel_intel.domain.geometry import BBox
from parcel_intel.domain.provenance import Provenance

Grid = tuple[tuple[float, ...], ...]
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
    changed = tuple(
        tuple(abs(a - b) > threshold for a, b in zip(row_after, row_before, strict=True))
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
