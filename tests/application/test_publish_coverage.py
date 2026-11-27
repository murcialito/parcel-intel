"""Caso de uso `PublishCoverageUseCase` (historia #185, ADR 0051). Límites sintéticos."""

from collections.abc import Sequence
from datetime import date

import pytest

from parcel_intel.application.publish_coverage import PublishCoverageUseCase
from parcel_intel.domain.coverage import CoverageFile
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.publication import NotRedistributableError, PublishableLayer
from parcel_intel.ports.errors import MunicipalBoundaryNotFoundError

_PUBLICA = Provenance(
    source="límites sintéticos",
    url="https://example.invalid/limites",
    retrieved_at=date(2026, 11, 27),
    license="CC BY 4.0 ign.es",
    redistribution=Redistribution.PUBLIC,
)
_INTERNA = Provenance(
    source="límites sintéticos",
    url="https://example.invalid/limites",
    retrieved_at=date(2026, 11, 27),
    license="sin licencia",
)
_CUADRO = Geometry(
    rings=(((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (0.0, 0.0)),), srid=25830
)


class _Limites:
    def __init__(self, provenance: Provenance = _PUBLICA) -> None:
        self.pedidos: list[list[str]] = []
        self._provenance = provenance

    def get_municipal_boundaries(self, ine_codes: Sequence[str]) -> list[MunicipalBoundary]:
        self.pedidos.append(list(ine_codes))
        if "99999" in ine_codes:
            raise MunicipalBoundaryNotFoundError(["99999"])
        return [MunicipalBoundary(c, f"M{c}", _CUADRO, self._provenance) for c in ine_codes]


class _Sink:
    def __init__(self) -> None:
        self.capas: list[PublishableLayer[MunicipalBoundary]] = []

    def publish(self, layer: PublishableLayer[MunicipalBoundary]) -> CoverageFile:
        self.capas.append(layer)
        codes = tuple(b.ine_code for b in layer.items)
        return CoverageFile(path="cobertura.geojson", size_bytes=1, municipality_codes=codes)


def test_publica_los_municipios_pedidos_sin_repetir_y_ordenados_por_ine() -> None:
    limites, sink = _Limites(), _Sink()
    resultado = PublishCoverageUseCase(limites, sink).execute(["28043", "28013", "28043"])
    assert limites.pedidos == [["28043", "28013"]]
    assert resultado.municipality_codes == ("28013", "28043")
    assert [b.ine_code for b in sink.capas[0].items] == ["28013", "28043"]


def test_un_municipio_que_falta_se_propaga_sin_llamar_al_sink() -> None:
    sink = _Sink()
    with pytest.raises(MunicipalBoundaryNotFoundError):
        PublishCoverageUseCase(_Limites(), sink).execute(["28043", "99999"])
    assert sink.capas == []


def test_un_limite_no_redistribuible_no_pasa_la_puerta() -> None:
    sink = _Sink()
    with pytest.raises(NotRedistributableError):
        PublishCoverageUseCase(_Limites(_INTERNA), sink).execute(["28043"])
    assert sink.capas == []


def test_sin_municipios_es_un_error() -> None:
    with pytest.raises(ValueError):
        PublishCoverageUseCase(_Limites(), _Sink()).execute([])
