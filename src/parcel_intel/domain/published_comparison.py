"""Imágenes de comparación publicables de un tramo a verificar (historia #172, ADR 0049).

Parte del manifiesto interno de `imagenes-comparacion` (#122, ADR 0042) y deja, de cada
ventana de un tramo aprobado, solo lo que se publica: tamaño en píxeles, trazo en
píxeles (todas las partes), imágenes en orden cronológico con su URL, franja, periodo,
resolución, atribución y texto alternativo, y las franjas omitidas con un texto llano.
Ni `sha256`, ni `bytes`, ni vuelo, ni `bbox`: la URL ya lleva el encuadre.

Antes de dejar nada comprueba que el manifiesto corresponde al tramo actual
(`comparison_windows` y `stretch_pixels` recalculados, igualdad exacta), que es de la
política vigente y que cada imagen es de su franja, con la atribución, licencia y
fuente de su vuelo en `FLIGHTS` (ADR 0042 §3, ampliado en #208). La URL la cierra el
adapter (igual a la URL canónica de la ventana y el vuelo en su servidor). Todo texto se
redacta aquí (ADR 0044). Solo stdlib.
"""

from dataclasses import dataclass
from datetime import date

from parcel_intel.domain.comparison_image import (
    COMPARISON_POLICY,
    COMPARISON_SLOTS,
    DECLARED_GAPS,
    FLIGHTS,
    ComparisonManifest,
    ComparisonWindow,
    DegenerateStretchError,
    StretchComparison,
    attribution_for,
    comparison_windows,
    stretch_pixels,
)
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Redistribution

COMPARISON_LICENSE = "CC BY 4.0"
OMISSION_TEXT = "sin cobertura de ese vuelo"
IMAGE_ALT_TEXT = "Ortofoto de {periodo} con el tramo a verificar marcado"
GAP_TEXT = "De {desde} a {hasta}: {motivo}."
SERVED_BY_TEXT = (
    "Las imágenes de comparación las sirven el Instituto Geográfico Nacional y la "
    "Comunidad de Madrid al abrir la ficha; este sitio no aloja ninguna."
)
NOT_AVAILABLE_TEXT = "Imagen no disponible"

RERUN = "vuelve a ejecutar imagenes-comparacion"
NOT_IN_MANIFEST = (
    "no está en el manifiesto de imágenes de comparación; ejecuta imagenes-comparacion"
)
TOO_LONG = "tramo demasiado largo para las imágenes de comparación"
INCOHERENT = f"el manifiesto no corresponde al tramo actual; {RERUN}"
NO_IMAGES = "sin imágenes de comparación"

_SLOT_INDEX = {slot.name: index for index, slot in enumerate(COMPARISON_SLOTS)}
_SLOT_VINTAGES = {slot.name: slot.vintages for slot in COMPARISON_SLOTS}


@dataclass(frozen=True)
class PublishedImage:
    url: str
    slot: str
    period: str
    resolution_m: float
    attribution: str  # «Obra derivada de …» (ADR 0042 §5)
    alt_text: str
    retrieved_at: date  # solo para la procedencia; no sale en la feature
    source: str  # la fuente del vuelo (`FLIGHTS`); solo para la procedencia
    notice: str | None  # aviso obligatorio de la fuente; sale como `aviso_fuente` si no es None


@dataclass(frozen=True)
class PublishedOmission:
    slot: str
    text: str


@dataclass(frozen=True)
class PublishedWindow:
    width_px: int
    height_px: int
    stretch_px: tuple[tuple[tuple[float, float], ...], ...]
    images: tuple[PublishedImage, ...]  # orden de COMPARISON_SLOTS
    omitted: tuple[PublishedOmission, ...]  # orden de COMPARISON_SLOTS


@dataclass(frozen=True)
class PublishedComparison:
    windows: tuple[PublishedWindow, ...]

    def images(self) -> tuple[PublishedImage, ...]:
        return tuple(image for window in self.windows for image in window.images)


@dataclass(frozen=True)
class PublishedGap:
    from_year: int
    to_year: int
    text: str


@dataclass(frozen=True)
class ComparisonNotes:
    """Bloque `comparacion` de la colección."""

    policy: str  # "imagenes_comparacion v2"
    gaps: tuple[PublishedGap, ...]
    served_by: str
    not_available: str


class ComparisonManifestNotUsableError(ValueError):
    """El manifiesto entero no sirve para publicar. `reason` en castellano."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ComparisonNotPublishableError(ValueError):
    """Las imágenes de un candidato no se pueden publicar. `reason` en castellano."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def check_comparison_manifest(
    manifest: ComparisonManifest, municipality_code: str
) -> ComparisonNotes:
    """Notas publicables del manifiesto, o `ComparisonManifestNotUsableError` si es de
    otro municipio, de otra versión de la política o con otros huecos (CA12)."""
    if manifest.municipality_code != municipality_code:
        raise ComparisonManifestNotUsableError(
            f"el manifiesto es del municipio {manifest.municipality_code}"
        )
    if manifest.policy != COMPARISON_POLICY:
        raise ComparisonManifestNotUsableError(
            f"el manifiesto es de otra versión de la política de imágenes; {RERUN}"
        )
    if manifest.gaps != DECLARED_GAPS:
        raise ComparisonManifestNotUsableError(
            f"el manifiesto declara otros huecos que la política vigente; {RERUN}"
        )
    return ComparisonNotes(
        policy=f"{COMPARISON_POLICY.identifier} v{COMPARISON_POLICY.version}",
        gaps=tuple(
            PublishedGap(
                gap.from_year,
                gap.to_year,
                GAP_TEXT.format(desde=gap.from_year, hasta=gap.to_year, motivo=gap.reason),
            )
            for gap in DECLARED_GAPS
        ),
        served_by=SERVED_BY_TEXT,
        not_available=NOT_AVAILABLE_TEXT,
    )


def _check_coherent(stretch: MultiLineGeometry, comparison: StretchComparison) -> None:
    try:
        expected = comparison_windows(stretch)
    except DegenerateStretchError as error:
        raise ComparisonNotPublishableError(INCOHERENT) from error
    if expected is None or tuple(w.window for w in comparison.windows) != expected:
        raise ComparisonNotPublishableError(INCOHERENT)
    for window in comparison.windows:
        if window.stretch_px != stretch_pixels(stretch, window.window):
            raise ComparisonNotPublishableError(INCOHERENT)


def _check_slots(window: ComparisonWindow) -> None:
    slots = [image.slot for image in window.images] + [o.slot for o in window.omitted]
    if sorted(slots) != sorted(_SLOT_INDEX):
        raise ComparisonNotPublishableError(
            f"una ventana no cubre exactamente las franjas de la política una vez; {RERUN}"
        )
    if any(omitted.reason == "fallo" for omitted in window.omitted):
        raise ComparisonNotPublishableError(
            f"una franja se omitió por un fallo de descarga; {RERUN}"
        )


def _published_image(window: ComparisonWindow, index: int) -> PublishedImage:
    image = window.images[index]
    where = f"la imagen de la franja {image.slot}"
    if image.vintage not in _SLOT_VINTAGES[image.slot]:
        raise ComparisonNotPublishableError(f"{where} es de un vuelo de otra franja")
    flight = FLIGHTS[image.vintage]
    if image.period != flight.period:
        raise ComparisonNotPublishableError(f"{where} no lleva el periodo de su vuelo")
    if image.resolution_m != flight.resolution_m:
        raise ComparisonNotPublishableError(f"{where} no lleva la resolución de su vuelo")
    if image.attribution != attribution_for(image.vintage):
        raise ComparisonNotPublishableError(f"{where} no lleva la atribución de su vuelo")
    provenance = image.provenance
    if provenance.source != flight.source:
        raise ComparisonNotPublishableError(f"{where} no es del servicio de su vuelo")
    if provenance.license != COMPARISON_LICENSE:
        raise ComparisonNotPublishableError(f"{where} no lleva la licencia {COMPARISON_LICENSE}")
    if provenance.redistribution is not Redistribution.PUBLIC:
        raise ComparisonNotPublishableError(f"{where} no está marcada como publicable")
    return PublishedImage(
        url=provenance.url,
        slot=image.slot,
        period=image.period,
        resolution_m=image.resolution_m,
        attribution=image.attribution,
        alt_text=IMAGE_ALT_TEXT.format(periodo=image.period),
        retrieved_at=provenance.retrieved_at,
        source=flight.source,
        notice=flight.notice,
    )


def _published_window(window: ComparisonWindow) -> PublishedWindow:
    _check_slots(window)
    images = sorted(
        (_published_image(window, i) for i in range(len(window.images))),
        key=lambda image: _SLOT_INDEX[image.slot],
    )
    omitted = sorted(window.omitted, key=lambda o: _SLOT_INDEX[o.slot])
    return PublishedWindow(
        width_px=window.window.width_px,
        height_px=window.window.height_px,
        stretch_px=window.stretch_px,
        images=tuple(images),
        omitted=tuple(PublishedOmission(o.slot, OMISSION_TEXT) for o in omitted),
    )


def build_published_comparison(
    stretch: MultiLineGeometry, comparison: StretchComparison | None
) -> PublishedComparison:
    """Imágenes publicables de un tramo aprobado, o `ComparisonNotPublishableError` con un
    motivo fijo: ausente, demasiado largo, incoherente con el tramo, franjas mal
    cubiertas, imagen fuera de su vuelo o licencia, o ninguna imagen (ADR 0049)."""
    if comparison is None:
        raise ComparisonNotPublishableError(NOT_IN_MANIFEST)
    if comparison.status == "tramo_demasiado_largo":
        raise ComparisonNotPublishableError(TOO_LONG)
    _check_coherent(stretch, comparison)
    windows = tuple(_published_window(window) for window in comparison.windows)
    if not any(window.images for window in windows):
        raise ComparisonNotPublishableError(NO_IMAGES)
    return PublishedComparison(windows=windows)
