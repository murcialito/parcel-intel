from collections.abc import Sequence
from typing import Protocol

from parcel_intel.domain.georeferencing import GeoreferenceUnit, SyncOutcome
from parcel_intel.domain.historic_trail import HistoricTrail


class GeoreferenceRepositoryPort(Protocol):
    """Capacidad: guardar el registro de una unidad georreferenciada y
    proyectar en una sola transacción sus trazados aprobados — historia #138,
    ADR 0044 (la base es una proyección de git por unidad)."""

    def sync_unit(self, unit: GeoreferenceUnit, approved: Sequence[HistoricTrail]) -> SyncOutcome:
        """Reescribe la unidad y sus trazados en una transacción: inserta los
        nuevos, actualiza los que cambiaron, retira los que ya no están y no
        toca los idénticos. `ValueError` (antes de cualquier SQL) si un
        trazado no es `approved` o no pertenece a la unidad, y también si un
        `identifier` ya existe con otro origen (`unit_id` nulo u otra unidad);
        en ese caso no se escribe nada."""
        ...

    def get_unit(self, unit_id: str) -> GeoreferenceUnit:
        """`GeoreferenceUnitNotFoundError` si no existe."""
        ...

    def list_unit_trail_ids(self, unit_id: str) -> tuple[str, ...]:
        """Identificadores de los trazados cargados de la unidad, ordenados."""
        ...
