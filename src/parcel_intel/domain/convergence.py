"""Tabla de convergencia de fuentes de un tramo (historia #240, ADR 0054).

Para un tramo (un indicio o un tramo a verificar) dice, fuente por fuente, si esa fuente
muestra un trazado cerca («Aparece», «No aparece»), si no cubre el tramo («Sin
cobertura») o, en las ortofotos, si hay imagen («Imagen disponible»). **No dice quién
tiene razón ni si el camino es público**: el aviso fijo lo dice siempre.

Reutiliza sin cambiarlos el criterio de coincidencia del ADR 0025 (`compare_trail`), el
prefiltro de rejilla del ADR 0030 y las comprobaciones de imágenes de #172
(`build_published_comparison`). Funciones puras, deterministas, sin red ni LLM. La tabla
no lleva geometría, procedencias ni identificadores de trazado o de parcela: solo
valores cerrados, años, fecha de consulta, enlaces de imagen ya validados y atribuciones
fijas por fuente (ADR 0041 §1-§2 para Catastro). Solo stdlib.
"""

import hashlib
import math
import re
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Literal, get_args

from parcel_intel.domain.comparison_image import COMPARISON_SLOTS, StretchComparison
from parcel_intel.domain.cut_candidate import CutCandidate
from parcel_intel.domain.discrepancy import (
    ComparableTrail,
    SourceRef,
    TrailRef,
    compare_trail,
    samples_stretch,
    trail_samples,
)
from parcel_intel.domain.discrepancy_criterion import (
    CRITERION,
    METRIC_SRID,
    CriterionRef,
    correspondence_radius_m,
)
from parcel_intel.domain.discrepancy_report import DiscrepancyRecord, TrailLayer
from parcel_intel.domain.geometry import (
    BBox,
    EmptyGeometryError,
    Geometry,
    MultiLineGeometry,
    TrailShape,
    bbox_of,
    expand_bbox,
    point_in_ring,
    shape_bbox,
)
from parcel_intel.domain.historic_coverage import (
    HISTORIC_SOURCE_KIND,
    HistoricCoverage,
    HistoricUnitCoverage,
    historic_trail_shape,
)
from parcel_intel.domain.historic_trail import HistoricDocumentKind
from parcel_intel.domain.public_card import (
    BANNED_WORDS,
    CATASTRO_ATTRIBUTION,
    SOURCE_POLICY,
    UNKNOWN_YEAR,
    TextValidation,
)
from parcel_intel.domain.published_comparison import (
    NO_IMAGES,
    TOO_LONG,
    ComparisonNotPublishableError,
    PublishedImage,
    build_published_comparison,
)
from parcel_intel.domain.spatial_index import GridIndex
from parcel_intel.domain.trail import SourceKind

ConvergenceValue = Literal["aparece", "no_aparece", "sin_cobertura", "imagen_disponible"]
EvidenceKind = Literal["trazado", "imagen"]  # el «papel» de la fila

CONVERGENCE_METHOD = CriterionRef("convergencia_fuentes", 2)
"""Sube con cualquier cambio de regla, constante u orden de filas. v2 (#315, ADR 0057 §4):
la tabla sin filas de ortofoto de un tramo demasiado largo (`images_unavailable`)."""

APPEARS_MIN_FRACTION = 0.5
"""Umbral de producto (a revisar con el fundador, ADR 0054): un tramo que coincide en
parte con una fuente sale «Aparece» si al menos esta fracción de su longitud tiene un
trazado de esa fuente a menos de la tolerancia del par (ADR 0025). Es el valor por
defecto: el caso de uso y las funciones de cálculo admiten otro (`appears_min_fraction`)
y cada tabla anota el que usó."""

# --- Texto validado por el fundador (#198), protegido por huella (lección #16). -------
CONVERGENCE_TITLE = "Qué fuentes muestran este trazado"
VALUE_TEXT: Mapping[ConvergenceValue, str] = MappingProxyType(
    {
        "aparece": "Aparece",
        "no_aparece": "No aparece",
        "sin_cobertura": "Sin cobertura",
        "imagen_disponible": "Imagen disponible",
    }
)
CONVERGENCE_WARNING = (
    "Esta tabla recoge qué fuentes muestran un trazado cerca de este tramo y de qué año. "
    "No dice quién tiene razón ni si el camino es público: eso solo lo puede decidir la "
    "administración competente. Cada fuente tiene su propia precisión y puede estar "
    "desactualizada."
)
CATASTRO_ROW_LABEL = "Catastro: vía de comunicación"
CONVERGENCE_TEXT_VALIDATION = TextValidation(
    validated_by_founder=date(2026, 11, 27),
    validation_url="https://github.com/murcialito/paso-comun/issues/198#issuecomment-7224344953",
    text_hash="34a8c3f7fe8c152410d2a390ca651a81beb5ea47506da1213957c0979138f049",
)


def convergence_text_fingerprint() -> str:
    """Texto canónico de lo que validó el fundador: título, valores, Catastro y aviso."""
    lines = [f"TITULO|{CONVERGENCE_TITLE}"]
    lines.extend(f"VALOR|{key}|{VALUE_TEXT[key]}" for key in sorted(VALUE_TEXT))
    lines.append(f"CATASTRO|{CATASTRO_ROW_LABEL}")
    lines.append(f"AVISO|{CONVERGENCE_WARNING}")
    return "\n".join(lines)


def compute_convergence_text_hash() -> str:
    return hashlib.sha256(convergence_text_fingerprint().encode("utf-8")).hexdigest()


# --- Rótulos de fila: los propuso el arquitecto y los aprobó el fundador en #240 -------
# («vamos con tus recomendaciones en lo demás», 2026-11-27, respuesta al punto 3 del
# comentario anterior). No entran en la huella de `CONVERGENCE_TEXT_VALIDATION`.
ROW_LABELS_APPROVAL_URL = (
    "https://github.com/murcialito/paso-comun/issues/240#issuecomment-7224620545"
)
LAYER_ROW_LABEL: Mapping[SourceKind, str] = MappingProxyType(
    {
        "via_pecuaria_oficial": "Vía pecuaria oficial",
        "ign_red_transporte": "Camino actual (IGN)",
        "catastro_vt": CATASTRO_ROW_LABEL,
        "planimetria_historica": "Planimetría del IGN",
        "mtn50_historico": "MTN50, primera edición (IGN)",
    }
)
ORTHOPHOTO_ROW_LABEL = "Ortofoto {franja}"  # «Ortofoto 1956-1957» … «Ortofoto reciente»

_TRAIL_VALUES: frozenset[ConvergenceValue] = frozenset({"aparece", "no_aparece", "sin_cobertura"})
_IMAGE_VALUES: frozenset[ConvergenceValue] = frozenset({"imagen_disponible", "sin_cobertura"})
_STRETCH_ID_RE = re.compile(r"[0-9a-f]{16}")
_MUNICIPALITY_RE = re.compile(r"[0-9]{5}")
_CUT_WORD_RE = re.compile(r"\bcorte\b")
_SLOT_NAMES = tuple(slot.name for slot in COMPARISON_SLOTS)
_LAYER_KINDS: tuple[SourceKind, ...] = ("via_pecuaria_oficial", "ign_red_transporte", "catastro_vt")
_MIN_YEAR, _MAX_YEAR = 1800, 2100


# --- Errores de dominio. ----------------------------------------------------------------
class InvalidConvergenceStretchError(ValueError):
    """Un `ConvergenceStretch` no cumple sus invariantes; el mensaje nombra el campo."""


class InvalidConvergenceRowError(ValueError):
    """Una `ConvergenceRow` no cumple sus invariantes; el mensaje nombra el campo."""


class InvalidConvergenceTableError(ValueError):
    """Una `ConvergenceTable` no cumple sus invariantes; el mensaje nombra el campo."""


class StretchNotComputableError(ValueError):
    """La tabla de UN tramo no se puede calcular. `reason` es un texto fijo."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ConvergenceNotComputableError(ValueError):
    """Las tablas de TODO un municipio no se pueden calcular. `reason` es un texto fijo."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --- Texto vetado (CA6). ----------------------------------------------------------------
def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def vetoed_terms_in(text: str) -> tuple[str, ...]:
    """Términos vetados en `text`: las palabras de `public_card.BANNED_WORDS` y «es
    público» por subcadena normalizada (sin tildes ni mayúsculas), y «corte» como palabra
    entera (no da positivo con «recorte», lección #170)."""
    haystack = _normalized(text)
    found = [word for word in BANNED_WORDS if _normalized(word) in haystack]
    if "es publico" in haystack:
        found.append("es público")
    if _CUT_WORD_RE.search(haystack):
        found.append("corte")
    return tuple(found)


# --- Entidades de la tabla. -------------------------------------------------------------
@dataclass(frozen=True)
class YearSpan:
    first: int
    last: int  # 1800 <= first <= last <= 2100

    def __post_init__(self) -> None:
        for field, value in (("first", self.first), ("last", self.last)):
            if not isinstance(value, int) or isinstance(value, bool):
                raise InvalidConvergenceRowError(f"years.{field} debe ser un entero: {value!r}")
        if not _MIN_YEAR <= self.first <= self.last <= _MAX_YEAR:
            raise InvalidConvergenceRowError(
                f"years debe cumplir {_MIN_YEAR} <= first <= last <= {_MAX_YEAR}: "
                f"{self.first}..{self.last}"
            )

    def label(self) -> str:
        """«1875» si es un solo año; «2017–2026» (raya corta U+2013) si no."""
        if self.first == self.last:
            return str(self.first)
        return f"{self.first}–{self.last}"


def _span(years: Sequence[int]) -> YearSpan | None:
    return YearSpan(min(years), max(years)) if years else None


@dataclass(frozen=True)
class ConvergenceRow:
    source_key: str  # "via_pecuaria_oficial", …, "ortofoto:1956-1957"; único en la tabla
    label: str
    evidence_kind: EvidenceKind
    value: ConvergenceValue
    years: YearSpan | None  # None = «año no declarado» (o fila sin cobertura)
    consulted_on: date | None  # fecha de consulta de la fuente; obligatoria en Catastro
    links: tuple[str, ...]  # URLs https de #172, en orden de ventana; solo «Imagen disponible»
    attributions: tuple[str, ...]

    def __post_init__(self) -> None:
        for field, text in (("source_key", self.source_key), ("label", self.label)):
            if not isinstance(text, str) or not text.strip():
                raise InvalidConvergenceRowError(f"{field} no puede estar vacío")
        if self.evidence_kind not in get_args(EvidenceKind):
            raise InvalidConvergenceRowError(f"evidence_kind no reconocido: {self.evidence_kind!r}")
        if self.value not in get_args(ConvergenceValue):
            raise InvalidConvergenceRowError(f"value no reconocido: {self.value!r}")
        allowed = _TRAIL_VALUES if self.evidence_kind == "trazado" else _IMAGE_VALUES
        if self.value not in allowed:
            raise InvalidConvergenceRowError(
                f"value {self.value!r} no vale en una fila de {self.evidence_kind}"
            )
        if self.years is not None and not isinstance(self.years, YearSpan):
            raise InvalidConvergenceRowError("years debe ser un YearSpan o None")
        if self.consulted_on is not None and not isinstance(self.consulted_on, date):
            raise InvalidConvergenceRowError("consulted_on debe ser una fecha o None")
        self._check_links()
        self._check_attributions()
        if self.source_key == "catastro_vt":
            if self.label != CATASTRO_ROW_LABEL:
                raise InvalidConvergenceRowError(
                    f"label de Catastro debe ser {CATASTRO_ROW_LABEL!r}"
                )
            if self.value != "sin_cobertura":
                if self.attributions != (CATASTRO_ATTRIBUTION,):
                    raise InvalidConvergenceRowError(
                        "attributions de Catastro debe ser solo CATASTRO_ATTRIBUTION (ADR 0041)"
                    )
                if self.consulted_on is None:
                    raise InvalidConvergenceRowError(
                        "consulted_on es obligatoria en Catastro (ADR 0041 §2.1)"
                    )
        for text in self.strings():
            terms = vetoed_terms_in(text)
            if terms:
                raise InvalidConvergenceRowError(
                    f"la fila {self.source_key} contiene términos vetados: {', '.join(terms)}"
                )

    def _check_links(self) -> None:
        if not isinstance(self.links, tuple):
            raise InvalidConvergenceRowError("links debe ser una tupla")
        if self.evidence_kind == "trazado" and self.links:
            raise InvalidConvergenceRowError("links debe estar vacío en una fila de trazado")
        if (self.value == "imagen_disponible") != bool(self.links):
            raise InvalidConvergenceRowError(
                "links no puede estar vacío con «Imagen disponible» y solo va con ese valor"
            )
        for link in self.links:
            if not isinstance(link, str) or not link.startswith("https://"):
                raise InvalidConvergenceRowError("cada enlace de links debe empezar por https://")

    def _check_attributions(self) -> None:
        if not isinstance(self.attributions, tuple):
            raise InvalidConvergenceRowError("attributions debe ser una tupla")
        for attribution in self.attributions:
            if not isinstance(attribution, str) or not attribution.strip():
                raise InvalidConvergenceRowError("attributions no admite textos vacíos")
        if self.value == "sin_cobertura":
            if (
                self.years is not None
                or self.consulted_on is not None
                or self.links
                or self.attributions
            ):
                raise InvalidConvergenceRowError(
                    "una fila sin_cobertura no lleva years, consulted_on, links ni attributions"
                )
        elif not self.attributions:
            raise InvalidConvergenceRowError(
                f"attributions no puede estar vacío con el valor {self.value!r}"
            )

    def strings(self) -> Iterator[str]:
        """Todo el texto visible de la fila."""
        yield self.label
        yield VALUE_TEXT[self.value]
        if self.value != "sin_cobertura":
            yield self.years.label() if self.years is not None else UNKNOWN_YEAR
        if self.consulted_on is not None:
            yield self.consulted_on.isoformat()
        yield from self.links
        yield from self.attributions


@dataclass(frozen=True)
class ConvergenceTable:
    stretch_id: str  # 16 hex: record_id del indicio o candidate_id
    municipality_code: str
    title: str  # == CONVERGENCE_TITLE
    rows: tuple[ConvergenceRow, ...]  # en el orden de las fuentes pedidas
    warning: str  # == CONVERGENCE_WARNING
    method: CriterionRef  # == CONVERGENCE_METHOD
    criterion: CriterionRef  # == discrepancy_criterion.CRITERION (trazabilidad hasta la regla)
    appears_min_fraction: float  # umbral de «Aparece» que se usó (configurable, ADR 0054)
    # Tramo demasiado largo para las imágenes: la tabla va sin filas de ortofoto (ADR 0057 §4).
    images_unavailable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.stretch_id, str) or not _STRETCH_ID_RE.fullmatch(self.stretch_id):
            raise InvalidConvergenceTableError("stretch_id debe ser 16 hexadecimales en minúscula")
        if not isinstance(self.municipality_code, str) or not _MUNICIPALITY_RE.fullmatch(
            self.municipality_code
        ):
            raise InvalidConvergenceTableError("municipality_code debe tener 5 dígitos")
        if self.title != CONVERGENCE_TITLE:
            raise InvalidConvergenceTableError("title debe ser CONVERGENCE_TITLE")
        if self.warning != CONVERGENCE_WARNING:
            raise InvalidConvergenceTableError("warning debe ser CONVERGENCE_WARNING")
        if self.method != CONVERGENCE_METHOD:
            raise InvalidConvergenceTableError("method debe ser CONVERGENCE_METHOD")
        if self.criterion != CRITERION:
            raise InvalidConvergenceTableError("criterion debe ser el CRITERION del ADR 0025")
        check_appears_min_fraction(self.appears_min_fraction, InvalidConvergenceTableError)
        if not isinstance(self.rows, tuple) or not all(
            isinstance(row, ConvergenceRow) for row in self.rows
        ):
            raise InvalidConvergenceTableError("rows debe ser una tupla de ConvergenceRow")
        keys = [row.source_key for row in self.rows]
        if len(set(keys)) != len(keys):
            raise InvalidConvergenceTableError("rows tiene source_key repetidos")
        if not isinstance(self.images_unavailable, bool):
            raise InvalidConvergenceTableError("images_unavailable debe ser un bool")
        if self.images_unavailable and any(row.evidence_kind == "imagen" for row in self.rows):
            raise InvalidConvergenceTableError(
                "una tabla con images_unavailable no lleva filas de imagen"
            )
        terms = vetoed_terms_in(self.title)
        if terms:
            raise InvalidConvergenceTableError(f"title contiene términos vetados: {terms}")

    def strings(self) -> Iterator[str]:
        """Todo el texto visible de la tabla, aviso incluido."""
        yield self.title
        for row in self.rows:
            yield from row.strings()
        yield self.warning


def check_appears_min_fraction(value: object, error: type[ValueError] = ValueError) -> float:
    """El umbral de «Aparece» debe ser un número finito en (0, 1]."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or not 0.0 < value <= 1.0
    ):
        raise error(f"appears_min_fraction debe estar en (0, 1]: {value!r}")
    return float(value)


# --- Tramo y conversiones. --------------------------------------------------------------
@dataclass(frozen=True)
class ConvergenceStretch:
    stretch_id: str  # 16 hex
    municipality_code: str  # 5 dígitos
    origin: SourceRef  # fuente del trazado del que sale el tramo: fija la tolerancia del par
    shape: TrailShape  # EPSG:25830; trail_samples(shape) no vacío

    def __post_init__(self) -> None:
        if not isinstance(self.stretch_id, str) or not _STRETCH_ID_RE.fullmatch(self.stretch_id):
            raise InvalidConvergenceStretchError(
                "stretch_id debe ser 16 hexadecimales en minúscula"
            )
        if not isinstance(self.municipality_code, str) or not _MUNICIPALITY_RE.fullmatch(
            self.municipality_code
        ):
            raise InvalidConvergenceStretchError("municipality_code debe tener 5 dígitos")
        if not isinstance(self.origin, SourceRef):
            raise InvalidConvergenceStretchError("origin debe ser un SourceRef")
        if not isinstance(self.shape, Geometry | MultiLineGeometry):
            raise InvalidConvergenceStretchError("shape debe ser una Geometry o MultiLineGeometry")
        if self.shape.srid != METRIC_SRID:
            raise InvalidConvergenceStretchError(f"shape debe estar en EPSG:{METRIC_SRID}")
        # Sin muestras, `compare_trail` devolvería None, que se leería como «Aparece».
        if not trail_samples(self.shape):
            raise InvalidConvergenceStretchError("shape no tiene ningún tramo medible")


def stretch_from_candidate(candidate: CutCandidate) -> ConvergenceStretch:
    """Tramo de un tramo a verificar (#128): su id, municipio, fuente y tramo."""
    return ConvergenceStretch(
        stretch_id=candidate.candidate_id,
        municipality_code=candidate.municipality_code,
        origin=candidate.subject.source,
        shape=candidate.stretch,
    )


def stretch_from_discrepancy(
    record: DiscrepancyRecord, municipality_code: str
) -> ConvergenceStretch:
    """Tramo de un indicio del informe INTERNO (#94): su id, la fuente del sujeto y la zona.
    Un registro con la zona redactada no tiene tramo."""
    if record.zone_redacted:
        raise InvalidConvergenceStretchError(
            "el registro tiene la zona redactada: usa el informe interno"
        )
    return ConvergenceStretch(
        stretch_id=record.record_id,
        municipality_code=municipality_code,
        origin=record.discrepancy.subject.source,
        shape=record.discrepancy.zone,
    )


def image_axis(shape: TrailShape) -> MultiLineGeometry:
    """Trazo de las imágenes de comparación de un tramo: la multilínea tal cual; de una
    franja, su pseudo-eje (ADR 0025). Es la ÚNICA función que lo define: quien genere el
    manifiesto de los indicios (#246) debe usarla (lección #160)."""
    if isinstance(shape, MultiLineGeometry):
        return shape
    samples = trail_samples(shape)
    return samples_stretch(samples, [True] * len(samples))


# --- Fuentes de fila (orden fijo, CA8). -------------------------------------------------
@dataclass(frozen=True)
class LayerRowSource:
    """Capa municipal: vía pecuaria, camino actual o Catastro."""

    kind: SourceKind

    def __post_init__(self) -> None:
        if self.kind not in _LAYER_KINDS:
            raise ValueError(f"LayerRowSource no admite la fuente {self.kind!r}")


@dataclass(frozen=True)
class HistoricRowSource:
    document_kind: HistoricDocumentKind

    def __post_init__(self) -> None:
        if self.document_kind not in get_args(HistoricDocumentKind):
            raise ValueError(f"HistoricRowSource no admite {self.document_kind!r}")


@dataclass(frozen=True)
class OrthophotoRowSource:
    slot: str  # nombre de una franja de COMPARISON_SLOTS

    def __post_init__(self) -> None:
        if self.slot not in _SLOT_NAMES:
            raise ValueError(f"OrthophotoRowSource: la franja {self.slot!r} no existe")


RowSource = LayerRowSource | HistoricRowSource | OrthophotoRowSource

CONVERGENCE_ROW_SOURCES: tuple[RowSource, ...] = (
    LayerRowSource("via_pecuaria_oficial"),
    LayerRowSource("ign_red_transporte"),
    LayerRowSource("catastro_vt"),
    HistoricRowSource("planimetria"),
    HistoricRowSource("mtn50"),
    *(OrthophotoRowSource(slot.name) for slot in COMPARISON_SLOTS),  # orden cronológico de #172
)
"""Orden fijo de filas (ADR 0054 §8). Una fuente nueva se añade sin mover las demás: un tipo
histórico nuevo tras el MTN50; una franja nueva, en su sitio de `COMPARISON_SLOTS`."""


def orthophoto_source_key(slot: str) -> str:
    return f"ortofoto:{slot}"


# --- Cálculo. ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PreparedLayer:
    """Capa municipal lista para consultar; se construye una vez por municipio y fuente."""

    source_ref: SourceRef  # kind, provenance de la capa, data_date=None
    items: tuple[tuple[BBox, ComparableTrail], ...]  # por identificador, sin geometrías vacías
    index: GridIndex[ComparableTrail]
    years: YearSpan | None  # min..max de data_date.year de TODOS los trazados; None si ninguno
    consulted_on: date  # layer.provenance.retrieved_at


def prepare_layer(layer: TrailLayer) -> PreparedLayer:
    source_ref = SourceRef(kind=layer.source, provenance=layer.provenance, data_date=None)
    items: list[tuple[BBox, ComparableTrail]] = []
    for trail in sorted(layer.trails, key=lambda t: t.identifier):
        if trail.source != layer.source:
            raise ValueError(
                f"el trazado {trail.identifier!r} es de {trail.source}, no de {layer.source}"
            )
        try:
            bbox = bbox_of(trail.geometry)
        except EmptyGeometryError:
            continue
        ref = TrailRef(trail_id=trail.identifier, source=source_ref)
        items.append((bbox, ComparableTrail(ref=ref, shape=trail.geometry)))
    years = [t.data_date.year for t in layer.trails if t.data_date is not None]
    return PreparedLayer(
        source_ref=source_ref,
        items=tuple(items),
        index=GridIndex.build(items),
        years=_span(years),
        consulted_on=layer.provenance.retrieved_at,
    )


def appears(
    stretch: ConvergenceStretch,
    source_ref: SourceRef,
    candidates: Sequence[ComparableTrail],
    appears_min_fraction: float = APPEARS_MIN_FRACTION,
) -> bool:
    """¿Muestra la fuente un trazado en el tramo? Sí si `compare_trail` no ve discrepancia
    o ve un `SOLAPE` que cubre al menos `appears_min_fraction` del tramo. Un
    `DESPLAZAMIENTO` o una ausencia (nada a menos de la tolerancia del par) es «No»."""
    threshold = check_appears_min_fraction(appears_min_fraction)
    subject = ComparableTrail(TrailRef(stretch.stretch_id, stretch.origin), stretch.shape)
    discrepancy = compare_trail(subject, source_ref, candidates)
    if discrepancy is None:
        return True
    return discrepancy.kind == "SOLAPE" and (
        discrepancy.measurement("fraccion_solapada") >= threshold
    )


def _trail_row(
    kind: SourceKind,
    value: ConvergenceValue,
    years: YearSpan | None,
    consulted_on: date | None,
) -> ConvergenceRow:
    attributions: tuple[str, ...] = ()
    if value == "sin_cobertura":
        years, consulted_on = None, None
    else:
        attributions = (SOURCE_POLICY[kind].attribution,)
    return ConvergenceRow(
        source_key=kind,
        label=LAYER_ROW_LABEL[kind],
        evidence_kind="trazado",
        value=value,
        years=years,
        consulted_on=consulted_on,
        links=(),
        attributions=attributions,
    )


def layer_row(
    stretch: ConvergenceStretch,
    kind: SourceKind,
    layer: PreparedLayer | None,
    appears_min_fraction: float = APPEARS_MIN_FRACTION,
) -> ConvergenceRow:
    """Fila de una capa municipal. Sin capa (no cargada): «Sin cobertura». Una capa
    cargada cubre todo el término (es un recorte por el límite del IGN)."""
    if layer is None:
        return _trail_row(kind, "sin_cobertura", None, None)
    if layer.source_ref.kind != kind:
        raise ValueError(f"la capa es de {layer.source_ref.kind}, no de {kind}")
    radius = correspondence_radius_m(stretch.origin.kind, kind)
    candidates = layer.index.query(expand_bbox(shape_bbox(stretch.shape), radius))
    found = appears(stretch, layer.source_ref, candidates, appears_min_fraction)
    return _trail_row(kind, "aparece" if found else "no_aparece", layer.years, layer.consulted_on)


def _inside(point: tuple[float, float], unit: HistoricUnitCoverage) -> bool:
    return point_in_ring(point, unit.footprint.rings[0])


def historic_row(
    stretch: ConvergenceStretch,
    coverage: HistoricCoverage,
    appears_min_fraction: float = APPEARS_MIN_FRACTION,
) -> ConvergenceRow:
    """Fila de una fuente histórica. «Aparece» si un trazado aprobado coincide (aunque el
    tramo salga en parte de las unidades); «No aparece» si todas las muestras del tramo
    caen dentro de alguna unidad; si no, «Sin cobertura»."""
    kind = HISTORIC_SOURCE_KIND[coverage.document_kind]
    source_ref = SourceRef(kind=kind, provenance=coverage.provenance, data_date=None)
    trails = [
        ComparableTrail(TrailRef(trail.identifier, source_ref), historic_trail_shape(trail))
        for trail in coverage.trails
    ]
    samples = trail_samples(stretch.shape)
    covering = [unit for unit in coverage.units if any(_inside(s.point, unit) for s in samples)]
    covered = all(any(_inside(s.point, unit) for unit in covering) for s in samples)
    value: ConvergenceValue
    if appears(stretch, source_ref, trails, appears_min_fraction):
        value = "aparece"
    elif covered:
        value = "no_aparece"
    else:
        value = "sin_cobertura"
    dated = covering if covering or value != "aparece" else list(coverage.units)
    years = _span([unit.document_date.year for unit in dated])
    consulted_on = max((unit.retrieved_at for unit in dated), default=None)
    return _trail_row(kind, value, years, consulted_on)


def _period_years(period: str) -> list[int]:
    return [int(part) for part in period.split("-")]


def _image_row(slot: str, images: Sequence[PublishedImage]) -> ConvergenceRow:
    key, label = orthophoto_source_key(slot), ORTHOPHOTO_ROW_LABEL.format(franja=slot)
    if not images:
        return ConvergenceRow(key, label, "imagen", "sin_cobertura", None, None, (), ())
    attributions: list[str] = []
    for image in images:
        for text in (image.attribution, image.notice):
            if text is not None and text not in attributions:
                attributions.append(text)
    years = [year for image in images for year in _period_years(image.period)]
    return ConvergenceRow(
        source_key=key,
        label=label,
        evidence_kind="imagen",
        value="imagen_disponible",
        years=_span(years),
        consulted_on=max(image.retrieved_at for image in images),
        links=tuple(image.url for image in images),
        attributions=tuple(attributions),
    )


def orthophoto_rows(
    stretch: ConvergenceStretch, comparison: StretchComparison | None, slots: Sequence[str]
) -> tuple[ConvergenceRow, ...]:
    """Una fila por franja pedida. Reutiliza todas las comprobaciones de #172: un tramo
    ausente, demasiado largo, incoherente con el manifiesto o con una franja omitida por
    fallo no tiene tabla (`StretchNotComputableError` con el motivo fijo). Solo «ninguna
    imagen» (franjas omitidas por falta de cobertura) deja todas las filas sin cobertura."""
    for slot in slots:
        if slot not in _SLOT_NAMES:
            raise ValueError(f"la franja {slot!r} no existe")
    try:
        published = build_published_comparison(image_axis(stretch.shape), comparison)
    except ComparisonNotPublishableError as error:
        if error.reason != NO_IMAGES:
            raise StretchNotComputableError(error.reason) from error
        return tuple(_image_row(slot, ()) for slot in slots)
    images = published.images()
    return tuple(_image_row(slot, [i for i in images if i.slot == slot]) for slot in slots)


def build_convergence_table(
    stretch: ConvergenceStretch,
    sources: Sequence[RowSource],
    layers: Mapping[SourceKind, PreparedLayer],
    historic: Mapping[HistoricDocumentKind, HistoricCoverage],
    comparison: StretchComparison | None,
    appears_min_fraction: float = APPEARS_MIN_FRACTION,
    without_images_if_too_long: bool = False,
) -> ConvergenceTable:
    """Una fila por fuente, en el orden de `sources`. Una capa ausente de `layers` es una
    capa no cargada («Sin cobertura»); una fuente histórica sin cobertura en `historic` es
    un error de composición (el port nunca devuelve nada vacío). `StretchNotComputableError`
    si las imágenes del tramo no se pueden usar.

    Con `without_images_if_too_long`, un tramo demasiado largo para las imágenes
    (`published_comparison.TOO_LONG`) no es un fallo: la tabla sale con las demás fuentes,
    en el mismo orden, sin filas de ortofoto y con `images_unavailable=True` (ADR 0057 §4).
    Cualquier otro motivo se propaga."""
    threshold = check_appears_min_fraction(appears_min_fraction)
    slots = [source.slot for source in sources if isinstance(source, OrthophotoRowSource)]
    images: dict[str, ConvergenceRow] = {}
    images_unavailable = False
    if slots:
        try:
            images = {row.source_key: row for row in orthophoto_rows(stretch, comparison, slots)}
        except StretchNotComputableError as error:
            if not (without_images_if_too_long and error.reason == TOO_LONG):
                raise
            images_unavailable = True
    rows: list[ConvergenceRow] = []
    for source in sources:
        if isinstance(source, LayerRowSource):
            rows.append(layer_row(stretch, source.kind, layers.get(source.kind), threshold))
        elif isinstance(source, HistoricRowSource):
            if source.document_kind not in historic:
                raise ValueError(f"falta la cobertura histórica de {source.document_kind}")
            rows.append(historic_row(stretch, historic[source.document_kind], threshold))
        elif not images_unavailable:
            rows.append(images[orthophoto_source_key(source.slot)])
    return ConvergenceTable(
        stretch_id=stretch.stretch_id,
        municipality_code=stretch.municipality_code,
        title=CONVERGENCE_TITLE,
        rows=tuple(rows),
        warning=CONVERGENCE_WARNING,
        method=CONVERGENCE_METHOD,
        criterion=CRITERION,
        appears_min_fraction=threshold,
        images_unavailable=images_unavailable,
    )
