"""Escritor del manifiesto interno de imágenes de comparación de un municipio
(historia #122, ADR 0042 §5 y §7).

`<directorio>/<ine>.json`: JSON con claves ordenadas y UTF-8, sin fecha de generación
(la de cada imagen es la del sidecar de la caché), escrito de forma atómica. Solo lleva
el id opaco del tramo, el INE y los vuelos."""

import json
from collections.abc import Sequence
from pathlib import Path

from parcel_intel.adapters.road_layer_files.common import write_atomic
from parcel_intel.domain.comparison_image import (
    COMPARISON_POLICY,
    DECLARED_GAPS,
    ComparisonImage,
    ComparisonWindow,
    DeclaredGap,
    OmittedSlot,
    StretchComparison,
)
from parcel_intel.domain.discrepancy_criterion import CriterionRef

MAX_MANIFEST_BYTES = 3_000_000


class ManifestTooLargeError(Exception):
    def __init__(self, size: int) -> None:
        super().__init__(f"el manifiesto serializado pesa {size} bytes (tope {MAX_MANIFEST_BYTES})")
        self.size = size


def _image(image: ComparisonImage) -> dict[str, object]:
    provenance = image.provenance
    return {
        "franja": image.slot,
        "vuelo": image.vintage,
        "periodo": image.period,
        "resolucion_m": image.resolution_m,
        "atribucion": image.attribution,
        "sha256": image.sha256,
        "bytes": image.byte_size,
        "procedencia": {
            "fuente": provenance.source,
            "url": provenance.url,
            "fecha_descarga": provenance.retrieved_at.isoformat(),
            "licencia": provenance.license,
            "redistribucion": provenance.redistribution.value,
        },
    }


def _omitted(omitted: OmittedSlot) -> dict[str, object]:
    return {
        "franja": omitted.slot,
        "motivo": omitted.reason,
        "probados": list(omitted.tried),
        "tipo_error": omitted.error_type,
    }


def _window(window: ComparisonWindow) -> dict[str, object]:
    box = window.window
    return {
        "bbox": [box.min_x, box.min_y, box.max_x, box.max_y],
        "srid": box.srid,
        "ancho_px": box.width_px,
        "alto_px": box.height_px,
        "trazo_px": [[[x, y] for x, y in part] for part in window.stretch_px],
        "imagenes": [_image(image) for image in window.images],
        "omitidas": [_omitted(omitted) for omitted in window.omitted],
    }


def _gap(gap: DeclaredGap) -> dict[str, object]:
    return {"desde": gap.from_year, "hasta": gap.to_year, "motivo": gap.reason}


def manifest_text(municipality_code: str, comparisons: Sequence[StretchComparison]) -> str:
    policy: CriterionRef = comparisons[0].policy if comparisons else COMPARISON_POLICY
    gaps = comparisons[0].gaps if comparisons else DECLARED_GAPS
    manifest = {
        "municipio": municipality_code,
        "politica": {"id": policy.identifier, "version": policy.version},
        "huecos": [_gap(gap) for gap in gaps],
        "tramos": [
            {
                "id": comparison.stretch_id,
                "estado": comparison.status,
                "ventanas": [_window(window) for window in comparison.windows],
            }
            for comparison in sorted(comparisons, key=lambda c: c.stretch_id)
        ],
    }
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


class JsonComparisonManifestWriter:
    """Implementa `ComparisonManifestSink`."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def write(self, municipality_code: str, comparisons: Sequence[StretchComparison]) -> None:
        text = manifest_text(municipality_code, comparisons)
        size = len(text.encode("utf-8"))
        if size > MAX_MANIFEST_BYTES:
            raise ManifestTooLargeError(size)
        write_atomic(self._directory, f"{municipality_code}.json", text)
