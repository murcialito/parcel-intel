"""Georreferenciación afín por unidad, con su error medido y sus umbrales —
historia #136 (hija A de #20), ADR 0043 (método) y ADR 0044 (carga).

Lógica pura, solo stdlib: el ajuste por mínimos cuadrados con coordenadas
centradas, el error (RMSE, residuo máximo y *leave-one-out*), los umbrales
por escala, la envolvente de los puntos retenidos y las entidades que describen
una unidad (imagen de trabajo, puntos de control, ajuste). La carga, la caché
de imágenes y PostGIS son de las hermanas (#137–#140).

No sabe nada de fincas ni de titulares: los puntos de control son referencias
visibles en el documento (esquinas de iglesias, cruces) y nunca vienen del
Catastro.
"""

import math
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, get_args

from parcel_intel.domain.geometry import Point
from parcel_intel.domain.historic_trail import DatePrecision, HistoricDocumentKind
from parcel_intel.domain.provenance import Provenance

# ADR 0043, "Licencia y publicación".
IGN_HISTORIC_LICENSE = "CC-BY 4.0 © Instituto Geográfico Nacional de España"

MIN_RETAINED_POINTS = 6
MIN_QUADRANTS = 3
MAX_DISCARDED_FRACTION = 0.25
# Umbrales de producto del ADR 0043: LOO = 6 mm y residuo máximo = 14 mm sobre
# el papel a la escala del documento (en 1:25.000, 15 m y 35 m).
_LOO_MM_ON_PAPER = 6
_MAX_RESIDUAL_MM_ON_PAPER = 14
_DEGENERACY_TOLERANCE = 1e-12

WorkingImageKind = Literal["wms_render", "original_cnig"]
ImageFormat = Literal["image/png", "image/jpeg"]

_UNIT_ID_RE = re.compile(r"[0-9]{4,6}-[wh][0-9]+")
_MUNICIPALITY_CODE_RE = re.compile(r"[0-9]{5}")
_POINT_ID_RE = re.compile(r"P[0-9]{2,3}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_GITHUB_USER_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")

_X_RANGE = (0.0, 1_000_000.0)
_Y_RANGE = (3_000_000.0, 5_000_000.0)


class InsufficientControlPointsError(ValueError):
    """Los puntos retenidos no bastan para un ajuste afín (pocos, colineales,
    repetidos o con una LOO indeterminada). El mensaje distingue el motivo."""


class InvalidControlPointError(ValueError):
    """Un `ControlPoint` (o su posición respecto a la imagen) no cumple sus invariantes."""


@dataclass(frozen=True)
class Verdict:
    """Veredicto de aceptabilidad. `reasons` está vacío si `ok`; cada motivo
    nombra la métrica, el valor (2 decimales) y el umbral."""

    ok: bool
    reasons: tuple[str, ...]


class GeoreferenceRejectedError(Exception):
    """El ajuste de una unidad no es aceptable: lleva el `Verdict` con los motivos."""

    def __init__(self, unit_id: str, verdict: Verdict) -> None:
        super().__init__(
            f"Georreferenciación de {unit_id} rechazada: " + "; ".join(verdict.reasons)
        )
        self.unit_id = unit_id
        self.verdict = verdict


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} no puede estar vacío")
    return value


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _require_finite_nonnegative_int(value: object, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} debe ser un entero > 0: {value!r}")


@dataclass(frozen=True)
class WorkingImage:
    """Imagen sobre la que se leen los puntos y se dibujan los trazados,
    identificada por su sha256. Su procedencia lleva la URL exacta y la fecha
    real de descarga."""

    kind: WorkingImageKind
    sha256: str
    width_px: int
    height_px: int
    format: ImageFormat
    provenance: Provenance

    def __post_init__(self) -> None:
        if self.kind not in get_args(WorkingImageKind):
            raise ValueError(f"kind no reconocido: {self.kind!r}")
        if not isinstance(self.sha256, str) or not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError(f"sha256 debe ser 64 hex minúsculas: {self.sha256!r}")
        _require_finite_nonnegative_int(self.width_px, "width_px")
        _require_finite_nonnegative_int(self.height_px, "height_px")
        if self.format not in get_args(ImageFormat):
            raise ValueError(f"format no reconocido: {self.format!r}")
        if not isinstance(self.provenance, Provenance):
            raise ValueError("provenance es obligatoria")


@dataclass(frozen=True)
class UnitSpec:
    """Lo que declara `unidad.json` de una unidad de georreferenciación."""

    unit_id: str
    document_id: str
    document_kind: HistoricDocumentKind
    municipality_code: str
    document_date: date
    document_date_precision: DatePrecision
    scale_denominator: int
    image_kind: WorkingImageKind
    image_url: str
    image_sha256: str
    image_width_px: int
    image_height_px: int
    image_retrieved_at: date
    provenance_source: str
    georeferenced_by: str
    georeferenced_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.unit_id, str) or not _UNIT_ID_RE.fullmatch(self.unit_id):
            raise ValueError(f"unit_id no cumple ^[0-9]{{4,6}}-[wh][0-9]+$: {self.unit_id!r}")
        _require_text(self.document_id, "document_id")
        if not self.unit_id.startswith(f"{self.document_id}-"):
            raise ValueError(
                f"unit_id {self.unit_id!r} debe empezar por document_id {self.document_id!r}"
            )
        if self.document_kind not in get_args(HistoricDocumentKind):
            raise ValueError(f"document_kind no reconocido: {self.document_kind!r}")
        if not isinstance(self.municipality_code, str) or not _MUNICIPALITY_CODE_RE.fullmatch(
            self.municipality_code
        ):
            raise ValueError(
                f"municipality_code debe ser un código INE de 5 dígitos: {self.municipality_code!r}"
            )
        for field, value in (
            ("document_date", self.document_date),
            ("image_retrieved_at", self.image_retrieved_at),
        ):
            if not isinstance(value, date) or isinstance(value, datetime):
                raise ValueError(f"{field} debe ser una fecha: {value!r}")
        if self.document_date_precision not in get_args(DatePrecision):
            raise ValueError(
                f"document_date_precision no reconocida: {self.document_date_precision!r}"
            )
        _require_finite_nonnegative_int(self.scale_denominator, "scale_denominator")
        if self.image_kind not in get_args(WorkingImageKind):
            raise ValueError(f"image_kind no reconocido: {self.image_kind!r}")
        _require_text(self.image_url, "image_url")
        if not isinstance(self.image_sha256, str) or not _SHA256_RE.fullmatch(self.image_sha256):
            raise ValueError(f"image_sha256 debe ser 64 hex minúsculas: {self.image_sha256!r}")
        _require_finite_nonnegative_int(self.image_width_px, "image_width_px")
        _require_finite_nonnegative_int(self.image_height_px, "image_height_px")
        self._check_provenance_source()
        if not isinstance(self.georeferenced_by, str) or not _GITHUB_USER_RE.fullmatch(
            self.georeferenced_by
        ):
            raise ValueError(
                f"georeferenced_by debe ser un usuario de GitHub: {self.georeferenced_by!r}"
            )
        if not isinstance(self.georeferenced_at, datetime) or self.georeferenced_at.tzinfo is None:
            raise ValueError("georeferenced_at debe ser un datetime con zona horaria")

    def _check_provenance_source(self) -> None:
        source = self.provenance_source
        if self.document_kind == "planimetria":
            pattern = rf"Planimetría de .+, IGN, documento {re.escape(self.document_id)}"
        else:
            pattern = rf"Primera edición MTN50, IGN, hoja {re.escape(self.document_id)}"
        if not isinstance(source, str) or not re.fullmatch(pattern, source):
            raise ValueError(
                f"provenance_source no sigue el patrón de {self.document_kind} "
                f"({pattern!r}): {source!r}"
            )


def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@dataclass(frozen=True)
class ControlPoint:
    """Punto de control: píxel `(col, row)` continuo (origen en la esquina
    superior izquierda del píxel (0, 0), fila hacia abajo) y su coordenada
    objetivo en EPSG:25830. Nunca viene del Catastro."""

    point_id: str
    col: float
    row: float
    target: Point
    coordinate_source: str
    description: str
    retained: bool
    discard_reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.point_id, str) or not _POINT_ID_RE.fullmatch(self.point_id):
            raise InvalidControlPointError(f"point_id no cumple ^P[0-9]{{2,3}}$: {self.point_id!r}")
        for name, value in (("col", self.col), ("row", self.row)):
            if not _is_number(value) or not math.isfinite(value) or value < 0:
                raise InvalidControlPointError(
                    f"{self.point_id}: {name} debe ser finito y >= 0: {value!r}"
                )
        self._check_target()
        if not isinstance(self.coordinate_source, str) or not self.coordinate_source.strip():
            raise InvalidControlPointError(
                f"{self.point_id}: coordinate_source no puede estar vacío"
            )
        if "catastro" in _normalized(self.coordinate_source):
            raise InvalidControlPointError(
                f"{self.point_id}: coordinate_source no puede ser el Catastro "
                f"(ADR 0043): {self.coordinate_source!r}"
            )
        if not isinstance(self.description, str) or not self.description.strip():
            raise InvalidControlPointError(f"{self.point_id}: description no puede estar vacía")
        if not isinstance(self.retained, bool):
            raise InvalidControlPointError(f"{self.point_id}: retained debe ser bool")
        if self.retained:
            if self.discard_reason is not None:
                raise InvalidControlPointError(
                    f"{self.point_id}: un punto retenido no puede tener discard_reason"
                )
        elif not isinstance(self.discard_reason, str) or not self.discard_reason.strip():
            raise InvalidControlPointError(
                f"{self.point_id}: un punto descartado necesita discard_reason"
            )

    def _check_target(self) -> None:
        target = self.target
        if (
            not isinstance(target, tuple)
            or len(target) != 2
            or not all(_is_number(c) and math.isfinite(c) for c in target)
        ):
            raise InvalidControlPointError(f"{self.point_id}: target debe ser (x, y) finito")
        x, y = target
        if not (_X_RANGE[0] <= x <= _X_RANGE[1] and _Y_RANGE[0] <= y <= _Y_RANGE[1]):
            raise InvalidControlPointError(
                f"{self.point_id}: target ({x}, {y}) fuera del rango de EPSG:25830 "
                "(¿grados o ejes cambiados?)"
            )


@dataclass(frozen=True)
class ControlPointSet:
    """Los puntos de una unidad y el sha256 del fichero tal cual."""

    points: tuple[ControlPoint, ...]
    sha256: str

    def __post_init__(self) -> None:
        ids = [p.point_id for p in self.points]
        if len(set(ids)) != len(ids):
            raise InvalidControlPointError("point_id repetido en el conjunto de puntos")
        if not isinstance(self.sha256, str) or not _SHA256_RE.fullmatch(self.sha256):
            raise InvalidControlPointError(f"sha256 debe ser 64 hex minúsculas: {self.sha256!r}")


@dataclass(frozen=True)
class AffineTransform:
    """`x = a + b·col + c·row`, `y = d + e·col + f·row`."""

    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

    def apply(self, col: float, row: float) -> Point:
        return (self.a + self.b * col + self.c * row, self.d + self.e * col + self.f * row)


@dataclass(frozen=True)
class PointResidual:
    point_id: str
    residual_m: float
    loo_residual_m: float | None


@dataclass(frozen=True)
class GeoreferenceFit:
    transform: AffineTransform
    n_retained: int
    rmse_m: float
    max_residual_m: float
    loo_rmse_m: float
    residuals: tuple[PointResidual, ...]


@dataclass(frozen=True)
class GeoreferenceUnit:
    """Registro por unidad (ADR 0043, "Registro"); solo se construye con veredicto ok."""

    spec: UnitSpec
    image: WorkingImage
    control_points: ControlPointSet
    fit: GeoreferenceFit


@dataclass(frozen=True)
class SyncOutcome:
    """Resultado de sincronizar una unidad: identificadores, ordenados."""

    inserted: tuple[str, ...]
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]
    withdrawn: tuple[str, ...]


def _solve(points: Sequence[ControlPoint]) -> AffineTransform:
    """Mínimos cuadrados exactos con coordenadas centradas, sin numpy."""
    n = len(points)
    mean_col = math.fsum(p.col for p in points) / n
    mean_row = math.fsum(p.row for p in points) / n
    mean_x = math.fsum(p.target[0] for p in points) / n
    mean_y = math.fsum(p.target[1] for p in points) / n
    us = [p.col - mean_col for p in points]
    vs = [p.row - mean_row for p in points]
    suu = math.fsum(u * u for u in us)
    svv = math.fsum(v * v for v in vs)
    suv = math.fsum(u * v for u, v in zip(us, vs, strict=True))
    det = suu * svv - suv * suv
    if suu == 0 or svv == 0 or det <= _DEGENERACY_TOLERANCE * suu * svv:
        raise InsufficientControlPointsError(
            "puntos colineales o repetidos: no determinan una afín"
        )

    def coefficients(values: list[float], mean: float) -> tuple[float, float, float]:
        shifted = [value - mean for value in values]
        su = math.fsum(u * s for u, s in zip(us, shifted, strict=True))
        sv = math.fsum(v * s for v, s in zip(vs, shifted, strict=True))
        b = (svv * su - suv * sv) / det
        c = (suu * sv - suv * su) / det
        return mean - b * mean_col - c * mean_row, b, c

    a, b, c = coefficients([p.target[0] for p in points], mean_x)
    d, e, f = coefficients([p.target[1] for p in points], mean_y)
    return AffineTransform(a, b, c, d, e, f)


def _residual(transform: AffineTransform, point: ControlPoint) -> float:
    x, y = transform.apply(point.col, point.row)
    return math.hypot(x - point.target[0], y - point.target[1])


def fit_affine(points: Sequence[ControlPoint]) -> GeoreferenceFit:
    """Ajusta la afín con los puntos retenidos y mide su error.

    Lanza `InsufficientControlPointsError` si hay menos de `MIN_RETAINED_POINTS`
    retenidos, si son colineales o repetidos, o si quitar uno cualquiera deja
    una afín indeterminada (la LOO no se puede calcular)."""
    retained = [p for p in points if p.retained]
    if len(retained) < MIN_RETAINED_POINTS:
        raise InsufficientControlPointsError(
            f"menos de {MIN_RETAINED_POINTS} puntos retenidos: {len(retained)}"
        )
    distinct = len({(p.col, p.row) for p in retained})
    if distinct < 3:
        raise InsufficientControlPointsError(
            f"puntos repetidos: solo {distinct} posiciones distintas entre {len(retained)}"
        )
    transform = _solve(retained)
    loo: dict[str, float] = {}
    for index, point in enumerate(retained):
        others = retained[:index] + retained[index + 1 :]
        try:
            without = _solve(others)
        except InsufficientControlPointsError as error:
            raise InsufficientControlPointsError(
                f"LOO indeterminada sin {point.point_id}: {error}"
            ) from error
        loo[point.point_id] = _residual(without, point)
    residuals = tuple(
        PointResidual(
            point_id=p.point_id,
            residual_m=_residual(transform, p),
            loo_residual_m=loo.get(p.point_id),
        )
        for p in points
    )
    own = [r.residual_m for r, p in zip(residuals, points, strict=True) if p.retained]
    return GeoreferenceFit(
        transform=transform,
        n_retained=len(retained),
        rmse_m=math.sqrt(math.fsum(r * r for r in own) / len(own)),
        max_residual_m=max(own),
        loo_rmse_m=math.sqrt(math.fsum(v * v for v in loo.values()) / len(loo)),
        residuals=residuals,
    )


def thresholds_m(scale_denominator: int) -> tuple[float, float]:
    """`(umbral LOO, umbral de residuo máximo)` en metros: 6 mm y 14 mm sobre el
    papel a la escala dada (1:25.000 → (15,0, 35,0))."""
    return (
        scale_denominator * _LOO_MM_ON_PAPER / 10000,
        scale_denominator * _MAX_RESIDUAL_MM_ON_PAPER / 10000,
    )


def occupied_quadrants(points: Sequence[ControlPoint], width_px: int, height_px: int) -> int:
    """Cuadrantes de la imagen (mitades por `width/2` y `height/2`) con algún punto retenido."""
    return len({(p.col >= width_px / 2, p.row >= height_px / 2) for p in points if p.retained})


def check_acceptable(
    points: Sequence[ControlPoint], fit: GeoreferenceFit, spec: UnitSpec
) -> Verdict:
    """Aplica los umbrales de producto del ADR 0043 y acumula todos los motivos."""
    loo_limit, max_limit = thresholds_m(spec.scale_denominator)
    scale = f"1:{spec.scale_denominator}"
    reasons: list[str] = []
    if fit.loo_rmse_m > loo_limit:
        reasons.append(f"rmse_loo {fit.loo_rmse_m:.2f} m > umbral {loo_limit:.2f} m ({scale})")
    if fit.max_residual_m > max_limit:
        reasons.append(
            f"residuo_max {fit.max_residual_m:.2f} m > umbral {max_limit:.2f} m ({scale})"
        )
    quadrants = occupied_quadrants(points, spec.image_width_px, spec.image_height_px)
    if quadrants < MIN_QUADRANTS:
        reasons.append(f"cuadrantes ocupados {quadrants} < mínimo {MIN_QUADRANTS}")
    if points:
        discarded = sum(1 for p in points if not p.retained) / len(points)
        if discarded > MAX_DISCARDED_FRACTION:
            reasons.append(
                f"descartados {discarded * 100:.2f} % > umbral {MAX_DISCARDED_FRACTION * 100:.2f} %"
            )
    return Verdict(ok=not reasons, reasons=tuple(reasons))


def check_points_in_image(points: Sequence[ControlPoint], width_px: int, height_px: int) -> None:
    """Todo punto debe caer dentro de la imagen (`0 ≤ col ≤ width`, `0 ≤ row ≤ height`)."""
    for point in points:
        if point.col > width_px or point.row > height_px:
            raise InvalidControlPointError(
                f"{point.point_id}: ({point.col}, {point.row}) cae fuera de la imagen "
                f"{width_px}x{height_px} px"
            )


def _cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _convex_hull(pixels: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """Cadena monótona de Andrew; descarta los puntos colineales del borde."""
    unique = sorted(set(pixels))
    if len(unique) <= 2:
        return unique
    lower: list[tuple[float, float]] = []
    for p in unique:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(unique):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def pixel_hull_contains(points: Sequence[ControlPoint], col: float, row: float) -> bool:
    """¿Está el píxel dentro de la envolvente convexa de los puntos retenidos?
    El borde (aristas y vértices) cuenta como dentro."""
    hull = _convex_hull([(p.col, p.row) for p in points if p.retained])
    if len(hull) < 3:
        return False
    candidate = (col, row)
    for start, end in zip(hull, hull[1:] + hull[:1], strict=True):
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        # La envolvente sale en sentido antihorario: dentro = a la izquierda de cada arista.
        if _cross(start, end, candidate) / length < -1e-9:
            return False
    return True


def round_mm(point: Point) -> Point:
    """Redondea al milímetro (ADR 0044, decisión 5)."""
    return (round(point[0], 3), round(point[1], 3))
