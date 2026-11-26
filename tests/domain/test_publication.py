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
    layer: PublishableLayer[_Item] = PublishableLayer(name="vacia", items=())

    assert layer.items == ()


def test_items_se_guardan_como_tupla_aunque_entre_un_generador() -> None:
    items = (_item(Redistribution.PUBLIC) for _ in range(2))

    layer: PublishableLayer[_Item] = PublishableLayer(
        name="gen",
        items=items,  # type: ignore[arg-type]
    )

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


def test_capa_vacia_con_procedencia_de_coleccion_interna_se_rechaza() -> None:
    internal = _item(Redistribution.INTERNAL_ONLY).provenance

    with pytest.raises(NotRedistributableError) as caught:
        PublishableLayer[_Item](name="vacia", items=(), layer_provenance=internal)

    assert caught.value.provenance == internal


def test_procedencia_de_coleccion_publica_con_elementos_publicos_se_admite() -> None:
    public = _item(Redistribution.PUBLIC)

    layer = PublishableLayer[_Item](
        name="capa", items=(public,), layer_provenance=public.provenance
    )

    assert layer.layer_provenance == public.provenance


def test_elemento_interno_se_rechaza_aunque_la_coleccion_sea_publica() -> None:
    public = _item(Redistribution.PUBLIC)

    with pytest.raises(NotRedistributableError):
        PublishableLayer[_Item](
            name="capa",
            items=(_item(Redistribution.INTERNAL_ONLY),),
            layer_provenance=public.provenance,
        )
