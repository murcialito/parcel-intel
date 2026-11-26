"""Frontera de `docs/validacion/casos.json` → `ValidationCase` (historia #110, ADR 0038).

Recibe el JSON ya parseado **y ya validado** con `validar_casos` (que sigue en
`tests/validacion/` hasta #111; el código de producción no importa de `tests/`). Solo copia
`id`, `ambito`, `municipio` (como código INE) y `tramo_linea`; nunca `tramo_descripcion`,
`fuente_url` ni `nota_fecha` (CA11).
"""

from typing import NotRequired, TypedDict, cast

from parcel_intel.domain.candidate_evaluation import METRIC_SRID, CaseScope, ValidationCase
from parcel_intel.domain.geometry import LineGeometry

MUNICIPALITY_INE: dict[str, str] = {
    "Colmenar de Oreja": "28043",
    "Aranjuez": "28013",
    "Chinchón": "28052",
    "Belmonte de Tajo": "28019",
    "Villaconejos": "28170",
    "Villarejo de Salvanés": "28180",
    "Valdelaguna": "28157",
}
"""Nombre → código INE de los 7 municipios del hito (`REGISTRY.md`, límites del IGN)."""


class RawValidationCase(TypedDict):
    """Campos de un caso de `casos.json` que lee el arnés (lección 0001: TypedDict en el
    borde). El resto de campos del formato se ignoran a propósito."""

    id: str
    ambito: CaseScope
    municipio: str
    tramo_linea: NotRequired[list[list[float]]]


def _raw_cases(data: object) -> list[RawValidationCase]:
    if not isinstance(data, dict) or not isinstance(data.get("casos"), list):
        raise ValueError("casos.json debe ser un objeto con la lista 'casos' (ya validado)")
    return cast(list[RawValidationCase], data["casos"])


def _to_case(raw: RawValidationCase) -> ValidationCase:
    scope = raw["ambito"]
    municipality_ine: str | None = None
    if scope == "hito":
        name = raw["municipio"]
        if name not in MUNICIPALITY_INE:
            raise ValueError(
                f"el caso {raw['id']!r} es del hito pero su municipio no está en la tabla"
            )
        municipality_ine = MUNICIPALITY_INE[name]
    line: LineGeometry | None = None
    if "tramo_linea" in raw:
        points = tuple((float(x), float(y)) for x, y in raw["tramo_linea"])
        line = LineGeometry(points=points, srid=METRIC_SRID)
    return ValidationCase(
        case_id=raw["id"], scope=scope, municipality_ine=municipality_ine, line=line
    )


def parse_validation_cases(data: object) -> tuple[ValidationCase, ...]:
    """Convierte el JSON validado de `casos.json` en casos del arnés, en el orden del
    fichero. `ambito` `comunidad` → INE `None`; `tramo_linea` ausente → `line=None`."""
    return tuple(_to_case(raw) for raw in _raw_cases(data))
