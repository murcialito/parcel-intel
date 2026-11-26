"""Índice espacial de rejilla uniforme (historia #31, ADR 0030).

Prefiltro exacto para la comparación de capas: devuelve un superconjunto de
los elementos cuyo bbox toca el bbox pedido. Solo stdlib (el dominio no admite
terceros).
"""

import math
from collections.abc import Sequence

from parcel_intel.domain.geometry import BBox

CELL_SIZE_M = 250.0

type _Cell = tuple[int, int]


class GridIndex[T]:
    """Rejilla uniforme sobre bboxes. El índice no ordena: devuelve los
    candidatos en el orden de inserción, así que quien lo construye inserta ya
    ordenado."""

    def __init__(
        self, cell_size_m: float, items: tuple[tuple[BBox, T], ...], cells: dict[_Cell, list[int]]
    ) -> None:
        self._cell_size_m = cell_size_m
        self._items = items
        self._cells = cells

    @classmethod
    def build(
        cls, items: Sequence[tuple[BBox, T]], cell_size_m: float = CELL_SIZE_M
    ) -> "GridIndex[T]":
        if not cell_size_m > 0.0:
            raise ValueError(f"cell_size_m debe ser positivo: {cell_size_m!r}")
        frozen = tuple(items)
        cells: dict[_Cell, list[int]] = {}
        for position, (bbox, _) in enumerate(frozen):
            for cell in _cells_of(bbox, cell_size_m):
                cells.setdefault(cell, []).append(position)
        return cls(cell_size_m, frozen, cells)

    def __len__(self) -> int:
        return len(self._items)

    def query(self, bbox: BBox) -> tuple[T, ...]:
        """Elementos cuyo bbox toca `bbox` (bordes incluidos), sin duplicados y
        en el orden de inserción."""
        positions: set[int] = set()
        for cell in _cells_of(bbox, self._cell_size_m):
            positions.update(self._cells.get(cell, ()))
        # `sorted` fija el orden: nunca se itera el `set` tal cual (PYTHONHASHSEED).
        return tuple(
            self._items[position][1]
            for position in sorted(positions)
            if _touches(self._items[position][0], bbox)
        )


def _cells_of(bbox: BBox, cell_size_m: float) -> list[_Cell]:
    min_col = math.floor(bbox[0] / cell_size_m)
    min_row = math.floor(bbox[1] / cell_size_m)
    max_col = math.floor(bbox[2] / cell_size_m)
    max_row = math.floor(bbox[3] / cell_size_m)
    return [
        (col, row) for col in range(min_col, max_col + 1) for row in range(min_row, max_row + 1)
    ]


def _touches(a: BBox, b: BBox) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]
