from dataclasses import dataclass

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance


@dataclass(frozen=True)
class LivestockTrail:
    """Tramo real de vía pecuaria o elemento anejo (abrevadero,
    descansadero), con la geometría de la franja/polígono ya cartografiada
    por IDEM (Comunidad de Madrid) — a diferencia de un curso de agua
    (historia 0012, línea de eje), esta fuente SÍ modela la anchura como
    área real, no como un valor escalar: `area_m2 / length_m` da una
    anchura media aproximada, pero NO es la anchura legal citada por la
    Ley 8/1998 de Vías Pecuarias (confirmado real: sistemáticamente menor
    que los mínimos legales — ver REGISTRY.md). No existe ningún campo de
    anchura legal en la fuente real; este tipo no inventa uno."""

    trail_type: str  # DS_TIPO: "Cañada"/"Cordel"/"Vereda"/"Colada", pero
    # también "Abrevadero"/"Descansadero"/"Descansadero-Abrevadero"
    # (confirmado real, no son vías pecuarias en sí). Cadena libre, no
    # enum: la fuente real ya tiene más valores que los cuatro
    # anticipados, sin garantía de lista cerrada.
    name: str
    municipality_code: str
    municipality_name: str
    trail_code: str
    length_m: float
    area_m2: float
    geometry: Geometry
    provenance: Provenance
