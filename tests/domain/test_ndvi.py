from datetime import date

import pytest

from parcel_intel.domain.ndvi import MismatchedNdviGridError, NdviGrid, compute_change_mask
from parcel_intel.domain.provenance import Provenance

_BBOX = (0.0, 0.0, 20.0, 20.0)
_PROVENANCE = Provenance(
    source="sentinel-2-l2a", url="https://example.invalid", retrieved_at=date(2026, 10, 15)
)


def _grid(values: tuple[tuple[float, ...], ...], scene_date: date = date(2026, 1, 1)) -> NdviGrid:
    return NdviGrid(
        values=values,
        bbox=_BBOX,
        srid=25830,
        scene_date=scene_date,
        cloud_cover_percent=1.0,
        provenance=_PROVENANCE,
    )


def test_celdas_que_superan_el_umbral_se_marcan_como_cambiadas() -> None:
    before = _grid(((0.2, 0.3), (0.4, 0.5)), scene_date=date(2026, 1, 1))
    after = _grid(((0.2, 0.3), (0.4, 0.9)), scene_date=date(2026, 6, 1))

    mask = compute_change_mask(before, after, threshold=0.1)

    assert mask.changed == ((False, False), (False, True))
    assert mask.threshold == 0.1
    assert mask.before == before
    assert mask.after == after


def test_umbral_distinto_cambia_el_resultado() -> None:
    before = _grid(((0.2,),))
    after = _grid(((0.35,),))

    mask_estricto = compute_change_mask(before, after, threshold=0.1)
    mask_laxo = compute_change_mask(before, after, threshold=0.2)

    assert mask_estricto.changed == ((True,),)
    assert mask_laxo.changed == ((False,),)


def test_grids_de_distinto_bbox_lanzan_error() -> None:
    before = _grid(((0.2,),))
    after = NdviGrid(
        values=((0.2,),),
        bbox=(100.0, 100.0, 120.0, 120.0),
        srid=25830,
        scene_date=date(2026, 6, 1),
        cloud_cover_percent=1.0,
        provenance=_PROVENANCE,
    )

    with pytest.raises(MismatchedNdviGridError):
        compute_change_mask(before, after, threshold=0.1)


def test_grids_de_distinta_forma_lanzan_error() -> None:
    before = _grid(((0.2, 0.3),))
    after = _grid(((0.2,),))

    with pytest.raises(MismatchedNdviGridError):
        compute_change_mask(before, after, threshold=0.1)
