from typing import Protocol

from parcel_intel.domain.published_candidate import MeasurementReport


class MeasurementReportSource(Protocol):
    """Capacidad: leer el informe agregado de `medir-candidatos` (#111)."""

    def get_measurement(self) -> MeasurementReport:
        """Devuelve el informe sin interpretar: si sirve para publicar lo decide el
        dominio (`summarize_measurement`). Lanza `MeasurementReportUnavailableError` si no
        existe, no es JSON o le falta, o tiene de otro tipo, alguna clave que se usa.
        Nunca devuelve un informe parcial."""
        ...
