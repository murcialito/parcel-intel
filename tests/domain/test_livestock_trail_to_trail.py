"""Conversión `LivestockTrail` → `Trail` (historia #22)."""

import dataclasses
import unicodedata
from datetime import date

import pytest

from parcel_intel.adapters.livestock_trails.parsing import parse_wfs_livestock_trails
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.livestock_trail import (
    LIVESTOCK_TRAIL_CHARACTER,
    LIVESTOCK_TRAIL_LICENSE,
    LIVESTOCK_TRAIL_TYPE_ROLE,
    LivestockTrail,
    UnknownLivestockTrailTypeError,
    livestock_trail_role,
    livestock_trail_to_trail,
)
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.trail import InvalidTrailError
from tests.adapters.livestock_trails.helpers import FIXTURES_DIR

_PROVENANCE = Provenance(
    source="idem",
    url="https://idem.comunidad.madrid/geoidem/Zonas/wfs",
    retrieved_at=date(2026, 10, 16),
)


def _real_villaconejos() -> list[LivestockTrail]:
    xml = (FIXTURES_DIR / "wfs_cql_villaconejos_municipio_completo_2_tramos.xml").read_bytes()
    return [
        LivestockTrail(
            trail_type=raw["trail_type"],
            name=raw["name"],
            municipality_code=raw["municipality_code"],
            municipality_name=raw["municipality_name"],
            trail_code=raw["trail_code"],
            length_m=raw["length_m"],
            area_m2=raw["area_m2"],
            geometry=Geometry(rings=raw["rings"], srid=25830),
            provenance=_PROVENANCE,
        )
        for raw in parse_wfs_livestock_trails(xml)
    ]


def test_tramo_real_de_villaconejos_se_convierte_entero() -> None:
    source = next(t for t in _real_villaconejos() if t.trail_code == "2817001")

    converted = livestock_trail_to_trail(source)

    assert converted.identifier == "2817001"
    assert converted.source == "via_pecuaria_oficial"
    assert converted.role == "via"
    assert converted.name == "Vereda del Raso"
    assert converted.trail_type == "Vereda"
    assert converted.municipality_code == "28170"
    assert converted.geometry is source.geometry
    assert converted.data_date is None
    assert converted.character == LIVESTOCK_TRAIL_CHARACTER
    assert converted.provenance == dataclasses.replace(
        _PROVENANCE, license=LIVESTOCK_TRAIL_LICENSE, redistribution=Redistribution.PUBLIC
    )


def test_la_conversion_no_modifica_el_original() -> None:
    source = _real_villaconejos()[0]

    livestock_trail_to_trail(source)

    assert source.provenance == _PROVENANCE


def test_licencia_ya_correcta_se_conserva_y_se_marca_publica() -> None:
    source = dataclasses.replace(
        _real_villaconejos()[0],
        provenance=dataclasses.replace(_PROVENANCE, license=LIVESTOCK_TRAIL_LICENSE),
    )

    converted = livestock_trail_to_trail(source)

    assert converted.provenance.license == LIVESTOCK_TRAIL_LICENSE
    assert converted.provenance.redistribution is Redistribution.PUBLIC


def test_licencia_vacia_sintetica_es_error() -> None:
    source = dataclasses.replace(
        _real_villaconejos()[0], provenance=dataclasses.replace(_PROVENANCE, license="")
    )

    with pytest.raises(InvalidTrailError, match="provenance.license"):
        livestock_trail_to_trail(source)


def test_geometria_sintetica_en_otro_crs_no_se_reproyecta_y_falla() -> None:
    source = dataclasses.replace(
        _real_villaconejos()[0],
        geometry=Geometry(rings=(((-3.4, 40.1), (-3.3, 40.2), (-3.4, 40.1)),), srid=4326),
    )

    with pytest.raises(InvalidTrailError, match="geometry.srid"):
        livestock_trail_to_trail(source)


def test_tabla_de_tipos_tiene_los_siete_valores_reales() -> None:
    assert dict(LIVESTOCK_TRAIL_TYPE_ROLE) == {
        "Cañada": "via",
        "Cordel": "via",
        "Vereda": "via",
        "Colada": "via",
        "Abrevadero": "anejo",
        "Descansadero": "anejo",
        "Descansadero-Abrevadero": "anejo",
    }


def test_tipo_sintetico_con_espacios_y_forma_nfd_se_normaliza() -> None:
    nfd = unicodedata.normalize("NFD", "Cañada")
    assert nfd != "Cañada"

    assert livestock_trail_role(f"  {nfd} ", "2804399") == "via"


def test_tipo_sintetico_desconocido_guarda_valor_y_codigo() -> None:
    with pytest.raises(UnknownLivestockTrailTypeError) as excinfo:
        livestock_trail_role("cañada", "2804399")  # sintético: en minúsculas no está en la tabla

    assert excinfo.value.trail_type == "cañada"
    assert excinfo.value.trail_code == "2804399"
    assert "'cañada'" in str(excinfo.value)
    assert "2804399" in str(excinfo.value)
