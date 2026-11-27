from dataclasses import dataclass

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance

PUBLIC_UTILITY_FOREST_LICENSE = "CC BY 4.0 Comunidad de Madrid"
"""Licencia leída en REGISTRY.md (AccessConstraints del workspace `Zonas` de IDEM;
el proveedor no publica un documento aparte). Misma que las vías pecuarias."""

PUBLIC_UTILITY_FOREST_NOTICE = "cartografía informativa del catálogo de montes de utilidad pública"


@dataclass(frozen=True)
class PublicUtilityForest:
    """Monte de utilidad pública del catálogo de la Comunidad de Madrid (IDEM).

    Solo lo imprescindible para situarlo: código del catálogo (`CD_UP`), nombre,
    municipio y geometría. No existe ningún campo de titularidad: el dominio no
    tiene dónde guardarlo (ningún dato de titularidad entra en el sistema)."""

    forest_code: str
    name: str
    municipality_name: str
    geometry: Geometry
    provenance: Provenance
