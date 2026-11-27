"""Señal «camino de Catastro más estrecho que la franja oficial» (historia #243).

Compara la anchura oficial de una pieza de vía pecuaria (`area_m2 / length_m` del
tramo completo de IDEM, REGISTRY.md CA4 de #216) con la anchura **catastral** de la
parcela de camino (clase VT, número >= 9000) que la recorre. La anchura catastral es la
de la parcela de camino, no la del firme real: nunca se llama «anchura real».

Es un **indicio a verificar**, no un dictamen. Función pura, solo stdlib. Sin
referencias catastrales ni titularidad: el dominio solo recibe áreas y recuentos.

Con la franja de la pieza `S` (área `S_m2`), la longitud de la pieza es `S_m2 / W` y la
anchura catastral media es `A = (área de VT ∩ S) / longitud = W * cubierta / S_m2`, así
que `ratio = A / W = cubierta / S_m2`. Es media por pieza: un estrechamiento local dentro
de una pieza larga queda diluido (medir por ventanas es mejora posterior).
"""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance

WidthOutcome = Literal["indicio", "sin_indicio", "sin_parcela_camino", "sin_datos"]

WIDTH_METHOD = "estrechamiento_via_pecuaria@1"

NARROWING_RATIO_THRESHOLD = 0.5
"""Umbral de estrechez: hay indicio si `A / W` es menor. Valor inicial **no validado**
(no se ha medido contra el conjunto de validación). Medio ancho oficial deja margen para
la imprecisión de la geometría de IDEM y de Catastro (ambas son cartografía informativa)
y evita señalar diferencias de pocos metros."""

MIN_OFFICIAL_WIDTH_M = 3.0
"""Anchura oficial mínima evaluable. Por debajo, `area / length` no describe una franja
(IDEM trae sistemáticamente menos que los mínimos legales, pero nunca ~0): se trata como
dato inutilizable. Valor inicial no validado."""

MIN_PIECE_LENGTH_M = 50.0
"""Longitud mínima de pieza evaluable (`piece_area / W`). Una astilla de recorte al
término no tiene anchura media con sentido. Valor inicial no validado."""

MAX_CONFIDENCE = 0.8
"""Techo de la confianza: el método no está validado."""

NOTICE = (
    "Indicio automático a verificar sobre el terreno; no es un dictamen. La anchura es la "
    "catastral de la parcela de camino, no la del firme real. Fichero interno: no se publica."
)


@dataclass(frozen=True)
class WidthEvidence:
    """Evidencia de un indicio: sin referencias catastrales."""

    trail_type: str
    official_width_m: float
    cadastral_width_m: float
    road_parcel_count: int


@dataclass(frozen=True)
class WidthAssessment:
    outcome: WidthOutcome
    ratio: float | None = None
    confidence: float | None = None
    evidence: WidthEvidence | None = None
    reason: str | None = None  # motivo de `sin_datos`


def official_width_m(area_m2: float, length_m: float) -> float | None:
    """`area_m2 / length_m` del tramo completo; `None` si no es derivable."""
    if not (math.isfinite(area_m2) and math.isfinite(length_m)):
        return None
    if area_m2 <= 0.0 or length_m <= 0.0:
        return None
    return area_m2 / length_m


def no_data(reason: str) -> WidthAssessment:
    return WidthAssessment(outcome="sin_datos", reason=reason)


def assess_width(
    trail_type: str,
    source_area_m2: float,
    source_length_m: float,
    piece_area_m2: float,
    covered_area_m2: float,
    road_parcel_count: int,
) -> WidthAssessment:
    """Veredicto de una pieza.

    `source_*` son los del tramo completo de IDEM; `piece_area_m2` es el área de la pieza
    recortada al término y `covered_area_m2` el área de las parcelas VT recortadas a esa
    pieza. `road_parcel_count` cuenta las parcelas VT con área dentro de la pieza."""
    width = official_width_m(source_area_m2, source_length_m)
    if width is None:
        return no_data("anchura oficial no derivable (longitud o área nulas o no finitas)")
    if width < MIN_OFFICIAL_WIDTH_M:
        return no_data(f"anchura oficial {width:.2f} m por debajo del mínimo evaluable")
    if not (math.isfinite(piece_area_m2) and piece_area_m2 > 0.0):
        return no_data("pieza sin área")
    piece_length = piece_area_m2 / width
    if piece_length < MIN_PIECE_LENGTH_M:
        return no_data(f"pieza de {piece_length:.0f} m, demasiado corta para medir su anchura")
    if road_parcel_count <= 0 or covered_area_m2 <= 0.0:
        return WidthAssessment(outcome="sin_parcela_camino")
    covered = min(covered_area_m2, piece_area_m2)
    cadastral_width = covered / piece_length
    ratio = cadastral_width / width
    if ratio >= NARROWING_RATIO_THRESHOLD:
        return WidthAssessment(outcome="sin_indicio", ratio=ratio)
    confidence = MAX_CONFIDENCE * (NARROWING_RATIO_THRESHOLD - ratio) / NARROWING_RATIO_THRESHOLD
    return WidthAssessment(
        outcome="indicio",
        ratio=ratio,
        confidence=confidence,
        evidence=WidthEvidence(trail_type, width, cadastral_width, road_parcel_count),
    )


@dataclass(frozen=True)
class PieceWidthResult:
    """Resultado de una pieza de vía pecuaria. `piece_id` es el de la capa de vías
    pecuarias (`CD_VP` o `CD_VP-k`); `trail_code` es el código de la vía, dato público."""

    piece_id: str
    trail_code: str
    name: str
    geometry: Geometry  # EPSG:25830
    assessment: WidthAssessment


def piece_ids(trail_codes: Sequence[str]) -> list[str]:
    """Identificadores de pieza: el código si aparece una vez; si no, `<código>-<k>`."""
    counts = Counter(trail_codes)
    seen: Counter[str] = Counter()
    ids: list[str] = []
    for code in trail_codes:
        seen[code] += 1
        ids.append(code if counts[code] == 1 else f"{code}-{seen[code]}")
    return ids


@dataclass(frozen=True)
class MunicipalWidthReport:
    """Piezas evaluadas de un municipio. Sin piezas: «sin vías», no se escribe fichero."""

    municipality_code: str
    method: str
    trail_provenance: tuple[Provenance, ...]
    cadastral_provenance: tuple[Provenance, ...]
    pieces: tuple[PieceWidthResult, ...]
    notice: str = NOTICE
