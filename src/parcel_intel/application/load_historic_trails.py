"""Caso de uso de una unidad georreferenciada: ajuste y carga de trazados — historia #139
(hija D de #20), ADR 0043 y ADR 0044.

`assess` mide el ajuste sin escribir y sin lanzar por un veredicto negativo. `load` hace los
pasos 1–8 sin tocar la base y solo en el 9 llama a `sync_unit`: cualquier fallo anterior deja la
base como estaba. Ningún LLM interviene y los umbrales son constantes del dominio.
"""

from dataclasses import dataclass

from parcel_intel.domain.digitization import (
    DigitizedTrail,
    check_approvals_current,
    check_trails_in_image,
    to_historic_trail,
)
from parcel_intel.domain.georeferencing import (
    ControlPointSet,
    GeoreferenceFit,
    GeoreferenceRejectedError,
    GeoreferenceUnit,
    SyncOutcome,
    UnitSpec,
    Verdict,
    WorkingImage,
    check_acceptable,
    check_points_in_image,
    fit_affine,
    pixel_hull_contains,
)
from parcel_intel.domain.historic_trail import HistoricTrail, derived_work_attribution
from parcel_intel.ports.georeference_repository import GeoreferenceRepositoryPort
from parcel_intel.ports.historic_georeference import CuratedHistoricInputPort, WorkingImagePort

EXTRAPOLATION_REASON = "extrapolación: añadir puntos de control"


@dataclass(frozen=True)
class UnitAssessment:
    spec: UnitSpec
    image: WorkingImage
    control_points: ControlPointSet
    fit: GeoreferenceFit
    verdict: Verdict


@dataclass(frozen=True)
class LoadOutcome:
    unit: GeoreferenceUnit
    sync: SyncOutcome
    proposed: tuple[str, ...]  # trail_id no cargados por estar propuestos
    rejected: tuple[str, ...]  # trail_id no cargados por estar rechazados
    extrapolated: tuple[tuple[str, str], ...]  # (trail_id, motivo): aprobados excluidos
    attributions: tuple[str, ...]  # derived_work_attribution de cada cargado, sin repetir


class HistoricUnitUseCase:
    def __init__(
        self,
        inputs: CuratedHistoricInputPort,
        images: WorkingImagePort,
        repository: GeoreferenceRepositoryPort | None = None,
    ) -> None:
        """`repository` puede omitirse para `assess`, que no usa la base; `load` lo exige."""
        self._inputs = inputs
        self._images = images
        self._repository = repository

    def assess(self, unit_id: str) -> UnitAssessment:
        """Pasos 1–5 sin escribir. Un veredicto negativo no lanza: viaja en el resultado."""
        spec = self._inputs.read_unit(unit_id)
        image = self._images.fetch(spec)
        control_points = self._inputs.read_control_points(unit_id)
        check_points_in_image(control_points.points, image.width_px, image.height_px)
        fit = fit_affine(control_points.points)
        verdict = check_acceptable(control_points.points, fit, spec)
        return UnitAssessment(spec, image, control_points, fit, verdict)

    def load(self, unit_id: str) -> LoadOutcome:
        repository = self._repository
        if repository is None:
            raise RuntimeError("cargar una unidad exige un repositorio")
        assessment = self.assess(unit_id)
        if not assessment.verdict.ok:
            raise GeoreferenceRejectedError(unit_id, assessment.verdict)
        unit = GeoreferenceUnit(
            spec=assessment.spec,
            image=assessment.image,
            control_points=assessment.control_points,
            fit=assessment.fit,
        )
        trails = self._inputs.read_trails(unit_id)
        check_trails_in_image(trails, unit.image.width_px, unit.image.height_px)
        check_approvals_current(trails, unit.control_points.sha256)

        approved: list[HistoricTrail] = []
        extrapolated: list[tuple[str, str]] = []
        for trail in trails:
            if trail.status != "approved":
                continue
            if _is_extrapolated(unit, trail):
                extrapolated.append((trail.trail_id, EXTRAPOLATION_REASON))
            else:
                approved.append(to_historic_trail(unit, trail))

        sync = repository.sync_unit(unit, approved)
        attributions = tuple(dict.fromkeys(derived_work_attribution(t) for t in approved))
        return LoadOutcome(
            unit=unit,
            sync=sync,
            proposed=tuple(t.trail_id for t in trails if t.status == "proposed"),
            rejected=tuple(t.trail_id for t in trails if t.status == "rejected"),
            extrapolated=tuple(extrapolated),
            attributions=attributions,
        )


def _is_extrapolated(unit: GeoreferenceUnit, trail: DigitizedTrail) -> bool:
    points = unit.control_points.points
    return any(not pixel_hull_contains(points, col, row) for col, row in trail.pixels)
