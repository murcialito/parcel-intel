"""Ports de la georreferenciación histórica -- historia #137 (hija B de #20), ADR 0043.

Dos capacidades: obtener la imagen de trabajo de una unidad, verificada por
sha256, y leer la entrada humana versionada de una unidad.
"""

from typing import Protocol

from parcel_intel.domain.digitization import DigitizedTrail
from parcel_intel.domain.georeferencing import ControlPointSet, UnitSpec, WorkingImage


class WorkingImagePort(Protocol):
    """Capacidad: obtener la imagen de trabajo declarada por una unidad,
    verificada por sha256.

    Lanza `RawImageMismatchError` si no es la declarada y
    `WorkingImageUnavailableError` si no hay forma de obtenerla."""

    def fetch(self, spec: UnitSpec) -> WorkingImage: ...


class CuratedHistoricInputPort(Protocol):
    """Capacidad: leer la entrada humana versionada de una unidad.

    Lanza `CuratedUnitNotFoundError` si falta el directorio o un fichero, y los
    errores de validación del dominio (`InvalidControlPointError`,
    `InvalidDigitizationError`, `ValueError`) si el contenido sale del formato cerrado."""

    def read_unit(self, unit_id: str) -> UnitSpec: ...

    def read_control_points(self, unit_id: str) -> ControlPointSet: ...

    def read_trails(self, unit_id: str) -> tuple[DigitizedTrail, ...]: ...
