import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.trail import InvalidTrailError, Trail, TrailRole

LIVESTOCK_TRAIL_LICENSE = "CC BY 4.0 Comunidad de Madrid"
"""Licencia leída en REGISTRY.md (AccessConstraints del WMS `Zonas` de IDEM;
el proveedor no publica un documento aparte)."""

LIVESTOCK_TRAIL_CHARACTER = "cartografía informativa, no deslinde"

LIVESTOCK_TRAIL_TYPE_ROLE: Mapping[str, TrailRole] = MappingProxyType(
    {
        "Cañada": "via",
        "Cordel": "via",
        "Vereda": "via",
        "Colada": "via",
        "Abrevadero": "anejo",
        "Descansadero": "anejo",
        "Descansadero-Abrevadero": "anejo",
    }
)
"""Los 7 valores reales de `DS_TIPO` observados (REGISTRY.md, hallazgo 1).
Tabla cerrada: un valor nuevo detiene el lote (ADR 0029) y se añade aquí
junto con la fixture que lo muestra."""


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


class UnknownLivestockTrailTypeError(ValueError):
    """`DS_TIPO` fuera de `LIVESTOCK_TRAIL_TYPE_ROLE`: no se clasifica en silencio."""

    def __init__(self, trail_type: str, trail_code: str) -> None:
        super().__init__(
            f"DS_TIPO desconocido {trail_type!r} en la vía pecuaria CD_VP={trail_code!r}: "
            "añádelo a LIVESTOCK_TRAIL_TYPE_ROLE con la fixture que lo muestra"
        )
        self.trail_type = trail_type
        self.trail_code = trail_code


def livestock_trail_role(trail_type: str, trail_code: str) -> TrailRole:
    """Papel (`via`/`anejo`) de un `DS_TIPO`, normalizado a NFC y sin espacios
    de borde. Un valor fuera de la tabla lanza `UnknownLivestockTrailTypeError`."""
    role = LIVESTOCK_TRAIL_TYPE_ROLE.get(unicodedata.normalize("NFC", trail_type.strip()))
    if role is None:
        raise UnknownLivestockTrailTypeError(trail_type, trail_code)
    return role


def livestock_trail_to_trail(trail: LivestockTrail) -> Trail:
    """Conversión pura de un tramo de IDEM al trazado común (ADR 0029, decisión 4).

    `identifier = CD_VP`, `role` por tabla cerrada, misma geometría (sin
    reproyectar), `data_date = None` (la fuente no fecha cada tramo).

    Procedencia, denegar por defecto: si falta la licencia se rellena con
    `LIVESTOCK_TRAIL_LICENSE`; cualquier otra licencia es `InvalidTrailError`;
    solo entonces se marca `Redistribution.PUBLIC`. `source`, `url` y
    `retrieved_at` no cambian."""
    provenance = trail.provenance
    license_ = provenance.license if provenance.license is not None else LIVESTOCK_TRAIL_LICENSE
    if license_ != LIVESTOCK_TRAIL_LICENSE:
        raise InvalidTrailError(
            f"provenance.license inesperada para una vía pecuaria: {license_!r} "
            f"(solo se acepta {LIVESTOCK_TRAIL_LICENSE!r})"
        )
    return Trail(
        identifier=trail.trail_code,
        source="via_pecuaria_oficial",
        role=livestock_trail_role(trail.trail_type, trail.trail_code),
        name=trail.name,
        trail_type=trail.trail_type,
        municipality_code=trail.municipality_code,
        geometry=trail.geometry,
        provenance=replace(provenance, license=license_, redistribution=Redistribution.PUBLIC),
        data_date=None,
        character=LIVESTOCK_TRAIL_CHARACTER,
    )
