"""Pruebas unitarias de `HistoricUnitUseCase` sobre la fixture sintética `280075-w1` (#139)."""

import hashlib
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.curated_historic import CuratedHistoricFiles
from parcel_intel.application.load_historic_trails import (
    EXTRAPOLATION_REASON,
    HistoricUnitUseCase,
)
from parcel_intel.domain.georeferencing import (
    IGN_HISTORIC_LICENSE,
    GeoreferenceUnit,
    SyncOutcome,
    UnitSpec,
    WorkingImage,
)
from parcel_intel.domain.historic_trail import HistoricTrail
from parcel_intel.domain.provenance import Provenance, Redistribution

HISTORICO = (
    Path(__file__).resolve().parents[1] / "fixtures" / "caminos" / "planimetrias" / "historico"
)
UNIT_ID = "280075-w1"


class _Images:
    def fetch(self, spec: UnitSpec) -> WorkingImage:
        return WorkingImage(
            kind=spec.image_kind,
            sha256=spec.image_sha256,
            width_px=spec.image_width_px,
            height_px=spec.image_height_px,
            format="image/png",
            provenance=Provenance(
                source=spec.provenance_source,
                url=spec.image_url,
                retrieved_at=date(2026, 11, 26),
                license=IGN_HISTORIC_LICENSE,
                redistribution=Redistribution.PUBLIC,
            ),
        )


class _Repository:
    def __init__(self) -> None:
        self.approved: list[tuple[str, ...]] = []

    def sync_unit(self, unit: GeoreferenceUnit, approved: Sequence[HistoricTrail]) -> SyncOutcome:
        self.approved.append(tuple(t.identifier for t in approved))
        return SyncOutcome((), (), (), ())

    def get_unit(self, unit_id: str) -> GeoreferenceUnit:
        raise AssertionError

    def list_unit_trail_ids(self, unit_id: str) -> tuple[str, ...]:
        raise AssertionError


def _use_case(root: Path, repository: _Repository | None) -> HistoricUnitUseCase:
    return HistoricUnitUseCase(CuratedHistoricFiles(root), _Images(), repository)


def test_assess_no_necesita_repositorio_y_mide_el_ajuste() -> None:
    assessment = _use_case(HISTORICO, None).assess(UNIT_ID)

    assert assessment.verdict.ok
    assert assessment.fit.n_retained == 7
    assert (
        assessment.control_points.sha256
        == hashlib.sha256((HISTORICO / UNIT_ID / "puntos_control.csv").read_bytes()).hexdigest()
    )


def test_load_sin_repositorio_falla_antes_de_leer_nada() -> None:
    with pytest.raises(RuntimeError, match="repositorio"):
        _use_case(HISTORICO, None).load(UNIT_ID)


def test_load_pasa_solo_los_aprobados_y_cuenta_el_resto() -> None:
    repository = _Repository()

    outcome = _use_case(HISTORICO, repository).load(UNIT_ID)

    assert repository.approved == [("280075-w1-T001", "280075-w1-T002")]
    assert outcome.proposed == ("T003",)
    assert outcome.rejected == ("T004",)
    assert outcome.extrapolated == ()
    # Las dos atribuciones son iguales: salen una sola vez.
    assert len(outcome.attributions) == 1


def test_el_motivo_de_extrapolacion_es_el_del_adr() -> None:
    assert EXTRAPOLATION_REASON == "extrapolación: añadir puntos de control"
