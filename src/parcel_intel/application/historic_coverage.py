"""Cobertura histórica de la tabla de convergencia desde `curated/historico/` — historia #313
(hija A de #246), ADR 0057.

Implementa `HistoricCoverageSource` componiendo ports, sin PostGIS, sin red y sin escribir:
repite los pasos de `historico cargar` (ADR 0043, 0045) para cada unidad y se queda con las
aceptadas. Una unidad con veredicto negativo es trabajo en curso: no cuenta y se informa en
`skipped_units`. Una aprobación caducada, una imagen ausente o distinta o un fichero no válido
son un fallo (`HistoricCoverageError`): nunca se devuelve una cobertura a medias.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from parcel_intel.application.load_historic_trails import HistoricUnitUseCase, is_extrapolated
from parcel_intel.domain.digitization import (
    InvalidDigitizationError,
    StaleApprovalError,
    check_approvals_current,
    check_trail_municipalities,
    check_trails_in_image,
    to_historic_trail,
)
from parcel_intel.domain.georeferencing import (
    GeoreferenceUnit,
    InsufficientControlPointsError,
    InvalidControlPointError,
    unit_footprint,
)
from parcel_intel.domain.historic_coverage import HistoricCoverage, HistoricUnitCoverage
from parcel_intel.domain.historic_trail import HistoricDocumentKind, HistoricTrail
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import (
    CuratedUnitNotFoundError,
    HistoricCoverageError,
    RawImageMismatchError,
    WorkingImageUnavailableError,
)
from parcel_intel.ports.historic_georeference import (
    CuratedHistoricCatalogPort,
    CuratedHistoricInputPort,
    WorkingImagePort,
)

REPOSITORY_URL = "https://github.com/murcialito/paso-comun"
HISTORIC_COVERAGE_LICENSE = "CC BY 4.0"


@dataclass(frozen=True)
class _AcceptedUnit:
    coverage: HistoricUnitCoverage
    trails: tuple[HistoricTrail, ...]
    provenance: Provenance


class CuratedHistoricCoverageSource:
    """Implementa `HistoricCoverageSource` sobre la entrada humana versionada."""

    def __init__(
        self,
        catalog: CuratedHistoricCatalogPort,
        inputs: CuratedHistoricInputPort,
        images: WorkingImagePort,
        today: Callable[[], date],
        repository_url: str = REPOSITORY_URL,
    ) -> None:
        self._catalog = catalog
        self._inputs = inputs
        self._use_case = HistoricUnitUseCase(inputs, images)
        self._today = today
        self._repository_url = repository_url
        self._accepted: dict[str, _AcceptedUnit] = {}
        self._skipped: dict[str, tuple[str, ...]] = {}

    def get_coverage(self, document_kind: HistoricDocumentKind) -> HistoricCoverage:
        for unit_id in self._catalog.unit_ids():
            self._load(unit_id)
        accepted = sorted(
            (a for a in self._accepted.values() if a.coverage.document_kind == document_kind),
            key=lambda a: a.coverage.unit_id,
        )
        trails = sorted((trail for a in accepted for trail in a.trails), key=lambda t: t.identifier)
        if accepted:
            latest = max(accepted, key=lambda a: (a.provenance.retrieved_at, a.coverage.unit_id))
            provenance = latest.provenance
        else:
            provenance = Provenance(
                source=f"curated/historico: sin unidades aceptadas de {document_kind}",
                url=self._repository_url,
                retrieved_at=self._today(),
                license=HISTORIC_COVERAGE_LICENSE,
                redistribution=Redistribution.PUBLIC,
            )
        return HistoricCoverage(
            document_kind=document_kind,
            provenance=provenance,
            units=tuple(a.coverage for a in accepted),
            trails=tuple(trails),
        )

    def skipped_units(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """(unit_id, motivos del veredicto) de las unidades con veredicto negativo ya leídas."""
        return tuple(sorted(self._skipped.items()))

    def _load(self, unit_id: str) -> None:
        if unit_id in self._accepted or unit_id in self._skipped:
            return
        # Campo de la entrada humana que se está leyendo. Sin extensión: en `application/` no
        # se nombra el formato de ningún fichero (test de #128).
        stage = "unidad"
        try:
            assessment = self._use_case.assess(unit_id)
            if not assessment.verdict.ok:
                self._skipped[unit_id] = assessment.verdict.reasons
                return
            stage = "trazados"
            unit = GeoreferenceUnit(
                spec=assessment.spec,
                image=assessment.image,
                control_points=assessment.control_points,
                fit=assessment.fit,
            )
            trails = self._inputs.read_trails(unit_id)
            check_trails_in_image(trails, unit.image.width_px, unit.image.height_px)
            check_trail_municipalities(trails)
            check_approvals_current(trails, unit.control_points.sha256)
            approved = tuple(
                sorted(
                    (
                        to_historic_trail(unit, trail)
                        for trail in trails
                        if trail.status == "approved" and not is_extrapolated(unit, trail)
                    ),
                    key=lambda t: t.identifier,
                )
            )
            coverage = HistoricUnitCoverage(
                unit_id=unit_id,
                document_kind=assessment.spec.document_kind,
                document_date=assessment.spec.document_date,
                footprint=unit_footprint(unit.control_points, unit.fit.transform),
                retrieved_at=assessment.spec.image_retrieved_at,
            )
        except StaleApprovalError as exc:
            raise HistoricCoverageError(
                unit_id,
                f"aprobaciones caducadas: {', '.join(exc.trail_ids)}; vuelve a revisar la unidad",
            ) from exc
        except WorkingImageUnavailableError as exc:
            raise HistoricCoverageError(
                unit_id,
                f"falta la imagen de trabajo en la caché; ejecuta historico ajuste {unit_id}",
            ) from exc
        except RawImageMismatchError as exc:
            raise HistoricCoverageError(unit_id, "la imagen de trabajo no es la declarada") from exc
        except CuratedUnitNotFoundError as exc:
            raise HistoricCoverageError(unit_id, "entrada no válida: falta un fichero") from exc
        except (InvalidControlPointError, InsufficientControlPointsError) as exc:
            raise HistoricCoverageError(unit_id, "entrada no válida: puntos_control") from exc
        except InvalidDigitizationError as exc:
            raise HistoricCoverageError(unit_id, "entrada no válida: trazados") from exc
        except ValueError as exc:
            raise HistoricCoverageError(unit_id, f"entrada no válida: {stage}") from exc
        self._accepted[unit_id] = _AcceptedUnit(coverage, approved, assessment.image.provenance)
