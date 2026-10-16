from typing import Protocol

from parcel_intel.domain.report import ParcelReport
from parcel_intel.domain.rule import ProposedRule


class ParcelRepositoryPort(Protocol):
    """Capacidad: cachear y recuperar el informe completo de una parcela.

    Un solo port, no dos (parcela/edificios) como `ParcelGeometryPort` y
    `BuildingGeometryPort` del ADR 0002: aquí no hay asimetría de autoridad
    entre proveedores que lo justifique — la caché lee y escribe parcela y
    edificios como una sola unidad. Ver ADR 0005.
    """

    def get_report(self, cadastral_reference: str) -> ParcelReport: ...

    def save_report(self, report: ParcelReport) -> None: ...


class RuleRepositoryPort(Protocol):
    """Capacidad: persistir y revisar propuestas de `Rule` -- historia
    0019, ADR 0019. Un único port compuesto (mismo criterio que
    `ParcelRepositoryPort`): los dos consumidores reales (comando de
    autoría, comando de revisión) comparten la misma tabla y la misma
    unidad de trabajo, sin asimetría de autoridad que justifique
    partirlo en dos."""

    def save_proposal(self, proposal: ProposedRule) -> None: ...

    def list_proposed(self) -> list[ProposedRule]: ...

    def approve(self, identifier: str) -> None: ...

    def reject(self, identifier: str) -> None: ...
