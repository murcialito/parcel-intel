from datetime import date

import pytest

from parcel_intel.domain.cadastral_zoning import CadastralZone, CadastralZoningLayer
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance, Redistribution

RING = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0))


def _provenance(redistribution: Redistribution = Redistribution.INTERNAL_ONLY) -> Provenance:
    return Provenance("fuente", "https://x", date(2026, 11, 27), "licencia", redistribution)


def test_una_zona_valida_es_de_uso_interno() -> None:
    zone = CadastralZone("040", "2ndOrder", Geometry((RING,), 25830), _provenance())
    layer = CadastralZoningLayer((0.0, 0.0, 1.0, 1.0), (zone,), 1)
    assert layer.redistribution is Redistribution.INTERNAL_ONLY


def test_una_zona_en_otro_crs_se_rechaza() -> None:
    with pytest.raises(ValueError, match="EPSG:25830"):
        CadastralZone("040", "2ndOrder", Geometry((RING,), 4326), _provenance())


def test_una_zona_publicable_se_rechaza() -> None:
    with pytest.raises(ValueError, match="uso interno"):
        CadastralZone(
            "040", "2ndOrder", Geometry((RING,), 25830), _provenance(Redistribution.PUBLIC)
        )
