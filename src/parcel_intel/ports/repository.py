from typing import Protocol

from parcel_intel.domain.report import ParcelReport


class ParcelRepositoryPort(Protocol):
    """Capacidad: cachear y recuperar el informe completo de una parcela.

    Un solo port, no dos (parcela/edificios) como `ParcelGeometryPort` y
    `BuildingGeometryPort` del ADR 0002: aquí no hay asimetría de autoridad
    entre proveedores que lo justifique — la caché lee y escribe parcela y
    edificios como una sola unidad. Ver ADR 0005.
    """

    def get_report(self, cadastral_reference: str) -> ParcelReport: ...

    def save_report(self, report: ParcelReport) -> None: ...
