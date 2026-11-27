"""Entidad de montes de utilidad pública (historia #220): sin ningún campo de titularidad."""

import dataclasses
from datetime import date

import pytest

from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.public_utility_forest import (
    PUBLIC_UTILITY_FOREST_LICENSE,
    PublicUtilityForest,
)

_PROV = Provenance("idem", "https://example.org", date(2026, 11, 27))


def test_la_entidad_no_tiene_donde_guardar_la_titularidad() -> None:
    names = {field.name for field in dataclasses.fields(PublicUtilityForest)}

    assert names == {"forest_code", "name", "municipality_name", "geometry", "provenance"}


def test_es_inmutable() -> None:
    forest = PublicUtilityForest("1", "A", "X", Geometry((), 25830), _PROV)

    with pytest.raises(dataclasses.FrozenInstanceError):
        forest.name = "B"  # type: ignore[misc]


def test_licencia_literal() -> None:
    assert PUBLIC_UTILITY_FOREST_LICENSE == "CC BY 4.0 Comunidad de Madrid"
