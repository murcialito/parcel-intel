"""Unitarios de `CuratedHistoricCoverageSource` con dobles de los ports (#313, ADR 0057).
La ruta completa sobre la unidad sintética está en `tests/acceptance/test_historia_313.py`."""

from datetime import date
from typing import Any

import pytest

from parcel_intel.application.historic_coverage import (
    REPOSITORY_URL,
    CuratedHistoricCoverageSource,
)
from parcel_intel.domain.provenance import Redistribution
from parcel_intel.ports.errors import CuratedUnitNotFoundError, HistoricCoverageError

TODAY = date(2026, 11, 28)


class _Catalog:
    def __init__(self, *ids: str) -> None:
        self._ids = ids

    def unit_ids(self) -> tuple[str, ...]:
        return self._ids


class _MissingInputs:
    def read_unit(self, unit_id: str) -> Any:
        raise CuratedUnitNotFoundError(unit_id, "falta unidad.json")


class _BoomInputs:
    def read_unit(self, unit_id: str) -> Any:
        raise RuntimeError("boom")


def test_sin_unidades_la_procedencia_es_la_del_repositorio_y_se_fecha_con_el_reloj() -> None:
    source = CuratedHistoricCoverageSource(_Catalog(), _MissingInputs(), None, lambda: TODAY)  # type: ignore[arg-type]
    coverage = source.get_coverage("mtn50")
    assert coverage.units == () and coverage.trails == ()
    assert coverage.provenance.source == "curated/historico: sin unidades aceptadas de mtn50"
    assert coverage.provenance.url == REPOSITORY_URL
    assert coverage.provenance.retrieved_at == TODAY
    assert coverage.provenance.license == "CC BY 4.0"
    assert coverage.provenance.redistribution is Redistribution.PUBLIC


def test_un_fichero_que_falta_es_un_error_de_cobertura_con_motivo_fijo() -> None:
    source = CuratedHistoricCoverageSource(
        _Catalog("280075-w1"),
        _MissingInputs(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        lambda: TODAY,
    )
    with pytest.raises(HistoricCoverageError) as caught:
        source.get_coverage("planimetria")
    assert caught.value.unit_id == "280075-w1"
    assert caught.value.reason == "entrada no válida: falta un fichero"


def test_otra_excepcion_se_propaga() -> None:
    source = CuratedHistoricCoverageSource(
        _Catalog("280075-w1"),
        _BoomInputs(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        lambda: TODAY,
    )
    with pytest.raises(RuntimeError):
        source.get_coverage("planimetria")
