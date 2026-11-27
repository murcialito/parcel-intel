"""Port de la evidencia de revisión de un trazado propuesto — historia #140 (hija E de #20)."""

from typing import Protocol

from parcel_intel.domain.digitization import DigitizedTrail
from parcel_intel.domain.georeferencing import GeoreferenceUnit
from parcel_intel.domain.trail_evidence import EvidenceRecord


class TrailEvidencePort(Protocol):
    """Capacidad: producir la evidencia de dos paneles de un trazado propuesto
    (la imagen de trabajo con el trazado y la ortofoto con el trazado
    transformado y su banda de error) y dejarla escrita.

    Lanza `RawImageMismatchError` si la imagen de trabajo no es la declarada y
    `EvidenceImageFormatError` si una imagen no se puede leer."""

    def render(self, unit: GeoreferenceUnit, trail: DigitizedTrail) -> EvidenceRecord: ...
