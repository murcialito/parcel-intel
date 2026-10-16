from typing import Protocol

from parcel_intel.domain.flood_hazard import FloodHazardSample
from parcel_intel.domain.geometry import Geometry


class FloodHazardPort(Protocol):
    """Capacidad: peligrosidad por inundación (profundidad de agua
    estimada) para los periodos de retorno y tipos conocidos, en el
    entorno de una geometría."""

    def get_flood_hazard(self, geometry: Geometry, margin_m: float) -> list[FloodHazardSample]:
        """Una muestra por cada combinación conocida de periodo de retorno
        y tipo (5 a fecha de esta historia: fluvial T10/T100/T500, marina
        T100/T500). `water_depth_m=None` si el servicio devuelve "NO DATA"
        en el punto muestreado — resultado esperado y mayoritario, NO una
        excepción. LIMITACIÓN DOCUMENTADA: el servicio real (REGISTRY.md)
        es un raster, no devuelve geometría poligonal — cada muestra se
        toma en el centro del bbox (geometry + margin_m), no en cada punto
        de la geometría real."""
        ...
