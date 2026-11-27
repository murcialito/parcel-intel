"""Composición de la evidencia de un trazado propuesto — historia #140 (hija E
de #20), ADR 0043 («Digitalización y revisión», punto 3).

Lógica pura, solo stdlib: dado un trazado en píxeles y la afín de su unidad,
calcula el recorte de la imagen de trabajo, el escalón de reducción y la ventana
de PNOA que enseñan los dos paneles de la evidencia. El dibujo y la red son del
adapter `evidence/`.

No sabe nada de fincas ni de titulares.
"""

import math
from dataclasses import dataclass

from parcel_intel.domain.digitization import DigitizedTrail
from parcel_intel.domain.georeferencing import GeoreferenceUnit
from parcel_intel.domain.provenance import Provenance

EVIDENCE_MARGIN_PX = 200
"""Margen del recorte alrededor del trazado, en píxeles de la imagen de trabajo."""

EVIDENCE_MAX_PANEL_PX = 800
"""Lado máximo de un panel: por encima se reduce por un escalón entero (`step`)."""

BAND_FACTOR = 2.0
"""La banda de incertidumbre mide ± `BAND_FACTOR` × RMSE LOO (ADR 0043)."""

LINE_COLOR = (230, 0, 0)
BAND_COLOR = (255, 140, 0)
BAND_ALPHA = 0.35
LINE_WIDTH_PX = 2

PNOA_EVIDENCE_LICENSE = "CC BY 4.0"
PNOA_EVIDENCE_ATTRIBUTION = "Obra derivada de PNOA 2023 CC-BY 4.0 scne.es"
"""ADR 0043 («Licencia y publicación»): por las coordenadas de los puntos y la evidencia."""

_LAYER_ATTRIBUTIONS = {
    "planimetria": (
        "Obra derivada de Planimetrías 1870-1950 CC-BY 4.0 "
        "© Instituto Geográfico Nacional de España"
    ),
    "mtn50": (
        "Obra derivada de Primera edición MTN50 1875-1968 CC-BY 4.0 "
        "© Instituto Geográfico Nacional de España"
    ),
}


@dataclass(frozen=True)
class EvidenceLayout:
    """Geometría de los dos paneles.

    - `crop`: `(x0, y0, x1, y1)` en píxeles de la imagen de trabajo (`x1`, `y1` exclusivos).
    - `step`: escalón de reducción del panel de la planimetría (1 = sin reducir).
    - `window`: `(min_x, min_y, max_x, max_y)` enteros en EPSG:25830 que se pide a PNOA.
    - `pnoa_width_px` y `pnoa_height_px`: tamaño de la respuesta de PNOA.
    """

    crop: tuple[int, int, int, int]
    step: int
    panel_width_px: int
    panel_height_px: int
    window: tuple[int, int, int, int]
    pnoa_width_px: int
    pnoa_height_px: int


@dataclass(frozen=True)
class EvidenceRecord:
    """Lo que devuelve `TrailEvidencePort.render` de un PNG escrito."""

    trail_id: str
    png_sha256: str
    pnoa_provenance: Provenance


def evidence_layout(unit: GeoreferenceUnit, trail: DigitizedTrail) -> EvidenceLayout:
    """Calcula el recorte, el escalón y la ventana de PNOA del trazado (ADR 0043).

    - Recorte: bbox de los vértices (suelo y techo) ± 200 px, acotado a la imagen.
    - `step = max(1, ceil(max(ancho, alto) / 800))`; el panel mide
      `ceil(ancho / step) × ceil(alto / step)`.
    - Ventana de PNOA: envolvente de las 4 esquinas del recorte transformadas, con el
      mínimo redondeado hacia abajo y el máximo hacia arriba al metro. `pnoa_width_px`
      es el ancho del panel y `pnoa_height_px = ceil((max_y − min_y) / ((max_x − min_x) /
      pnoa_width_px))`, de modo que el píxel de PNOA es casi cuadrado."""
    width_px, height_px = unit.image.width_px, unit.image.height_px
    cols = [col for col, _ in trail.pixels]
    rows = [row for _, row in trail.pixels]
    x0 = max(0, math.floor(min(cols)) - EVIDENCE_MARGIN_PX)
    y0 = max(0, math.floor(min(rows)) - EVIDENCE_MARGIN_PX)
    x1 = min(width_px, math.ceil(max(cols)) + EVIDENCE_MARGIN_PX)
    y1 = min(height_px, math.ceil(max(rows)) + EVIDENCE_MARGIN_PX)
    if x1 <= x0 or y1 <= y0:
        raise ValueError(
            f"{trail.trail_id}: el recorte cae fuera de la imagen {width_px}x{height_px}"
        )
    crop_width, crop_height = x1 - x0, y1 - y0
    step = max(1, math.ceil(max(crop_width, crop_height) / EVIDENCE_MAX_PANEL_PX))
    panel_width = math.ceil(crop_width / step)
    panel_height = math.ceil(crop_height / step)

    corners = [unit.fit.transform.apply(col, row) for col in (x0, x1) for row in (y0, y1)]
    min_x = math.floor(min(x for x, _ in corners))
    max_x = math.ceil(max(x for x, _ in corners))
    min_y = math.floor(min(y for _, y in corners))
    max_y = math.ceil(max(y for _, y in corners))
    if max_x <= min_x or max_y <= min_y:
        raise ValueError(f"{trail.trail_id}: la ventana de PNOA es degenerada")
    # Aritmética entera: la ventana ya es entera y así no hay redondeo de coma flotante.
    pnoa_height = -(-((max_y - min_y) * panel_width) // (max_x - min_x))
    return EvidenceLayout(
        crop=(x0, y0, x1, y1),
        step=step,
        panel_width_px=panel_width,
        panel_height_px=panel_height,
        window=(min_x, min_y, max_x, max_y),
        pnoa_width_px=panel_width,
        pnoa_height_px=pnoa_height,
    )


def layer_attributions(unit: GeoreferenceUnit) -> tuple[str, ...]:
    """Atribuciones de capa del ADR 0043 que acompañan a la evidencia: la del
    documento de la unidad y la de PNOA."""
    return (_LAYER_ATTRIBUTIONS[unit.spec.document_kind], PNOA_EVIDENCE_ATTRIBUTION)


def band_radius_m(unit: GeoreferenceUnit) -> float:
    """Semianchura de la banda de incertidumbre: 2 × RMSE LOO de la unidad."""
    return BAND_FACTOR * unit.fit.loo_rmse_m
