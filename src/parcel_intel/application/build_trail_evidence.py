"""Caso de uso: evidencia de los trazados propuestos de una unidad — historia #140
(hija E de #20), ADR 0043.

Hace los pasos 1–7 de la carga de una unidad (leer, imagen, puntos, ajuste,
umbrales, trazados, aprobaciones vigentes) y llama a `render` solo para los
trazados `proposed`. No toca la base. Ningún LLM interviene.
"""

from parcel_intel.domain.digitization import check_approvals_current, check_trails_in_image
from parcel_intel.domain.georeferencing import (
    GeoreferenceRejectedError,
    GeoreferenceUnit,
    check_acceptable,
    check_points_in_image,
    fit_affine,
)
from parcel_intel.domain.trail_evidence import EvidenceRecord
from parcel_intel.ports.historic_georeference import CuratedHistoricInputPort, WorkingImagePort
from parcel_intel.ports.trail_evidence import TrailEvidencePort


class BuildTrailEvidenceUseCase:
    def __init__(
        self,
        inputs: CuratedHistoricInputPort,
        images: WorkingImagePort,
        evidence: TrailEvidencePort,
    ) -> None:
        self._inputs = inputs
        self._images = images
        self._evidence = evidence

    def execute(self, unit_id: str) -> tuple[EvidenceRecord, ...]:
        """Valida la unidad entera antes de escribir nada: una unidad rechazada
        (`GeoreferenceRejectedError`) o con aprobaciones caducadas
        (`StaleApprovalError`) no produce evidencia."""
        spec = self._inputs.read_unit(unit_id)
        image = self._images.fetch(spec)
        control_points = self._inputs.read_control_points(unit_id)
        check_points_in_image(control_points.points, image.width_px, image.height_px)
        fit = fit_affine(control_points.points)
        verdict = check_acceptable(control_points.points, fit, spec)
        if not verdict.ok:
            raise GeoreferenceRejectedError(unit_id, verdict)
        trails = self._inputs.read_trails(unit_id)
        check_trails_in_image(trails, image.width_px, image.height_px)
        check_approvals_current(trails, control_points.sha256)
        unit = GeoreferenceUnit(spec=spec, image=image, control_points=control_points, fit=fit)
        return tuple(
            self._evidence.render(unit, trail) for trail in trails if trail.status == "proposed"
        )
