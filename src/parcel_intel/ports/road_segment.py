from typing import Protocol

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.road_segment import RoadSegment


class RoadSegmentPort(Protocol):
    """Capacidad: tramos sin asfaltar de la red de transporte que
    intersectan el entorno (bbox + margen) de una geometría."""

    def get_nearby_unpaved_roads(self, geometry: Geometry, margin_m: float) -> list[RoadSegment]:
        """Solo tramos sin asfaltar (`unpaved`). Lista vacía si no hay
        ninguno en el entorno — no es una excepción. Lanza
        `RoadNetworkError` si la respuesta del servicio no es utilizable."""
        ...
