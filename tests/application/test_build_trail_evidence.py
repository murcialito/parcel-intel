import shutil
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.curated_historic import CuratedHistoricFiles
from parcel_intel.application.build_trail_evidence import BuildTrailEvidenceUseCase
from parcel_intel.domain.digitization import DigitizedTrail, StaleApprovalError
from parcel_intel.domain.georeferencing import (
    GeoreferenceRejectedError,
    GeoreferenceUnit,
    InsufficientControlPointsError,
    UnitSpec,
    WorkingImage,
)
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.trail_evidence import EvidenceRecord
from tests.adapters.evidence.helpers import HISTORICO

UNIT_ID = "280075-w1"
SHA = "ef" * 32


class FakeImages:
    def __init__(self) -> None:
        self.fetched: list[str] = []

    def fetch(self, spec: UnitSpec) -> WorkingImage:
        self.fetched.append(spec.unit_id)
        return WorkingImage(
            kind="wms_render",
            sha256=spec.image_sha256,
            width_px=spec.image_width_px,
            height_px=spec.image_height_px,
            format="image/png",
            provenance=Provenance(
                source=spec.provenance_source,
                url=spec.image_url,
                retrieved_at=date(2026, 11, 26),
                license="CC-BY 4.0 © Instituto Geográfico Nacional de España",
                redistribution=Redistribution.PUBLIC,
            ),
        )


class FakeEvidence:
    def __init__(self) -> None:
        self.rendered: list[tuple[GeoreferenceUnit, DigitizedTrail]] = []

    def render(self, unit: GeoreferenceUnit, trail: DigitizedTrail) -> EvidenceRecord:
        self.rendered.append((unit, trail))
        provenance = Provenance(
            "pnoa-ma", "u", date(2026, 11, 26), "CC BY 4.0", Redistribution.PUBLIC
        )
        return EvidenceRecord(trail.trail_id, SHA, provenance)


def _use_case(root: Path) -> tuple[BuildTrailEvidenceUseCase, FakeImages, FakeEvidence]:
    images, evidence = FakeImages(), FakeEvidence()
    return BuildTrailEvidenceUseCase(CuratedHistoricFiles(root), images, evidence), images, evidence


def test_solo_se_renderizan_los_propuestos_con_la_unidad_ajustada() -> None:
    use_case, images, evidence = _use_case(HISTORICO)
    records = use_case.execute(UNIT_ID)
    assert [r.trail_id for r in records] == ["T003"]
    assert images.fetched == [UNIT_ID]
    ((unit, trail),) = evidence.rendered
    assert trail.status == "proposed"
    assert unit.spec.unit_id == UNIT_ID
    assert unit.fit.n_retained == 7
    assert (
        unit.control_points.sha256
        == "619cbca3c49dcbbdf974d9b102dae5d2d782144a5b19a37bfda7094d9b28af05"
    )


def test_una_unidad_no_aceptable_no_renderiza_nada(tmp_path: Path) -> None:
    shutil.copytree(HISTORICO / UNIT_ID, tmp_path / UNIT_ID)
    csv = tmp_path / UNIT_ID / "puntos_control.csv"
    csv.write_text(
        csv.read_text(encoding="utf-8").replace("466701.0,4439952.0", "466701.0,4440152.0"),
        encoding="utf-8",
    )
    use_case, _images, evidence = _use_case(tmp_path)
    with pytest.raises(GeoreferenceRejectedError) as raised:
        use_case.execute(UNIT_ID)
    assert any("rmse_loo" in reason for reason in raised.value.verdict.reasons)
    assert evidence.rendered == []


def test_aprobaciones_caducadas_no_renderizan_nada(tmp_path: Path) -> None:
    shutil.copytree(HISTORICO / UNIT_ID, tmp_path / UNIT_ID)
    csv = tmp_path / UNIT_ID / "puntos_control.csv"
    csv.write_text(
        csv.read_text(encoding="utf-8").replace("Plaza en el", "Plaza del"), encoding="utf-8"
    )
    use_case, _images, evidence = _use_case(tmp_path)
    with pytest.raises(StaleApprovalError) as raised:
        use_case.execute(UNIT_ID)
    assert raised.value.trail_ids == ("T001", "T002")
    assert evidence.rendered == []


def test_puntos_insuficientes_lanzan_el_error_del_dominio(tmp_path: Path) -> None:
    shutil.copytree(HISTORICO / UNIT_ID, tmp_path / UNIT_ID)
    csv = tmp_path / UNIT_ID / "puntos_control.csv"
    lines = csv.read_text(encoding="utf-8").splitlines()[:5]  # cabecera + 4 puntos
    csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    use_case, _images, evidence = _use_case(tmp_path)
    with pytest.raises(InsufficientControlPointsError):
        use_case.execute(UNIT_ID)
    assert evidence.rendered == []


def test_trazado_fuera_de_la_imagen_lanza_error_antes_de_renderizar(tmp_path: Path) -> None:
    shutil.copytree(HISTORICO / UNIT_ID, tmp_path / UNIT_ID)
    unit_file = tmp_path / UNIT_ID / "trazados.geojson"
    unit_file.write_text(
        unit_file.read_text(encoding="utf-8").replace("[380.0, 150.0]", "[900.0, 150.0]"),
        encoding="utf-8",
    )
    use_case, _images, evidence = _use_case(tmp_path)
    with pytest.raises(ValueError, match="T003"):
        use_case.execute(UNIT_ID)
    assert evidence.rendered == []
