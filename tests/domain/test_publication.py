from dataclasses import dataclass
from datetime import date

import pytest

from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.publication import NotRedistributableError, PublishableLayer

_DATE = date(2026, 11, 26)


@dataclass(frozen=True)
class _Item:
    provenance: Provenance


def _item(redistribution: Redistribution) -> _Item:
    return _Item(
        provenance=Provenance(
            source="fuente",
            url="https://example.invalid",
            retrieved_at=_DATE,
            redistribution=redistribution,
        )
    )


def test_capa_vacia_se_admite() -> None:
    layer = PublishableLayer(name="vacia", items=())

    assert layer.items == ()


def test_items_se_guardan_como_tupla_aunque_entre_un_generador() -> None:
    items = (_item(Redistribution.PUBLIC) for _ in range(2))

    layer = PublishableLayer(name="gen", items=items)  # type: ignore[arg-type]

    assert isinstance(layer.items, tuple)
    assert len(layer.items) == 2


def test_error_expone_capa_y_procedencia_del_elemento_interno() -> None:
    internal = _item(Redistribution.INTERNAL_ONLY)

    with pytest.raises(NotRedistributableError) as caught:
        PublishableLayer(name="capa", items=(internal,))

    assert caught.value.layer_name == "capa"
    assert caught.value.provenance == internal.provenance


def test_procedencia_por_defecto_es_solo_uso_interno() -> None:
    provenance = Provenance(source="s", url="u", retrieved_at=_DATE)

    assert provenance.redistribution is Redistribution.INTERNAL_ONLY
