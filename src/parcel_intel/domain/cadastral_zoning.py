"""Polígonos catastrales rústicos (historia #217, ADR 0028).

Un polígono catastral es una zona (`CadastralZoning`, nivel `2ndOrder`) que agrupa
parcelas rústicas; no es una finca y no identifica a ningún propietario. La capa es de
**uso interno**: la licencia INSPIRE de Catastro no permite redistribuirla. Solo la
etiqueta del polígono sale del adaptador; ninguna referencia catastral. Solo stdlib.
"""

from dataclasses import dataclass

from parcel_intel.domain.geometry import BBox, Geometry
from parcel_intel.domain.provenance import Provenance, Redistribution

CADASTRAL_ZONING_SRID = 25830
POLYGON_ZONING_LEVEL = "2ndOrder"
"""Nivel INSPIRE de los polígonos rústicos. Los demás (`1stOrder`, el término) se descartan."""


@dataclass(frozen=True)
class CadastralZone:
    label: str  # número de polígono, p. ej. "040"
    level: str  # siempre `POLYGON_ZONING_LEVEL`
    geometry: Geometry  # EPSG:25830, solo anillos exteriores (los huecos no se modelan)
    provenance: Provenance  # petición WFS de la tesela donde apareció primero

    def __post_init__(self) -> None:
        if self.geometry.srid != CADASTRAL_ZONING_SRID:
            raise ValueError(
                f"un polígono catastral va en EPSG:{CADASTRAL_ZONING_SRID}, "
                f"no en {self.geometry.srid}"
            )
        if self.provenance.redistribution is not Redistribution.INTERNAL_ONLY:
            raise ValueError(
                "un polígono catastral es de uso interno: su procedencia no puede ser "
                f"{self.provenance.redistribution.value}"
            )


@dataclass(frozen=True)
class CadastralZoningLayer:
    bbox: BBox
    zones: tuple[CadastralZone, ...]  # únicas, ordenadas por etiqueta
    tiles: int

    @property
    def redistribution(self) -> Redistribution:
        return Redistribution.INTERNAL_ONLY
