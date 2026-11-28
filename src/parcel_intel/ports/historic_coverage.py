from typing import Protocol

from parcel_intel.domain.historic_coverage import HistoricCoverage
from parcel_intel.domain.historic_trail import HistoricDocumentKind


class HistoricCoverageSource(Protocol):
    """Capacidad: trazados históricos aprobados de un tipo de documento y zona que cubren
    las unidades georreferenciadas aceptadas (todas, no solo las del municipio: decide la
    geometría) -- historia #240, ADR 0054.

    Sin unidades devuelve una `HistoricCoverage` con `units == ()` y `trails == ()` (la
    fila sale «Sin cobertura»), nunca `None` ni una excepción. Cualquier excepción es un
    fallo real y se propaga."""

    def get_coverage(self, document_kind: HistoricDocumentKind) -> HistoricCoverage: ...
