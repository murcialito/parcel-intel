from typing import Protocol

from parcel_intel.domain.geometry import BBox
from parcel_intel.domain.historic_trail import HistoricTrail


class HistoricTrailRepositoryPort(Protocol):
    """Capacidad: guardar trazados históricos, registrar su revisión y
    consultar los publicables — historia #19, ADR 0026.

    Dos escrituras separadas (mismo criterio que `RuleRepositoryPort`, ADR
    0019): guardar una propuesta nunca sobrescribe una revisión, y la
    revisión solo pasa de `proposed` a otro estado. Las consultas de
    publicación llevan "approved" en el nombre y no aceptan estado como
    parámetro. Todas las listas se ordenan por `identifier`."""

    def save_proposal(self, trail: HistoricTrail) -> None:
        """Upsert de un trazado `proposed` (`ValueError` si no lo es). Si la
        fila existe ya revisada → `HistoricTrailAlreadyReviewedError`, sin
        tocarla."""
        ...

    def record_review(self, trail: HistoricTrail) -> None:
        """Persiste `status`/`reviewer`/`reviewed_at` de un trazado
        `approved`/`rejected` (`ValueError` si es `proposed`), solo si en la
        base sigue `proposed`; si no existe o ya está revisado →
        `HistoricTrailNotPendingError`."""
        ...

    def get(self, identifier: str) -> HistoricTrail:
        """`HistoricTrailNotFoundError` si no existe."""
        ...

    def list_pending(self, municipality_code: str) -> list[HistoricTrail]: ...

    def list_approved_by_municipality(self, municipality_code: str) -> list[HistoricTrail]: ...

    def list_approved_in_bbox(self, bbox: BBox) -> list[HistoricTrail]:
        """Aprobados cuya línea real corta `bbox` (EPSG:25830), no solo su
        rectángulo envolvente."""
        ...
