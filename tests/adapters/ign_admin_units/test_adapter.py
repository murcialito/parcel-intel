from datetime import date
from pathlib import Path

import pytest
import requests

from parcel_intel.adapters.ign_admin_units import IgnAdministrativeUnitsAdapter
from parcel_intel.adapters.ign_admin_units.parsing import (
    AdministrativeUnitParseError,
    is_municipality,
    parse_administrative_units,
)
from parcel_intel.ports.errors import MunicipalBoundaryUnusableError

FIXTURE = Path(__file__).parents[2] / "fixtures" / "caminos" / "ign_au_ambito_7_municipios.xml"
BBOX = (39.98, -3.62, 40.22, -3.15)


def test_parsing_extrae_ine_nombre_nivel_y_cuenta_todas_las_features() -> None:
    parsed = parse_administrative_units(FIXTURE.read_bytes())

    assert parsed["number_matched"] == 8
    assert len(parsed["units"]) == 8
    colmenar = next(u for u in parsed["units"] if u["ine_code"] == "28043")
    assert colmenar["name"] == "Colmenar de Oreja"
    assert is_municipality(colmenar)
    assert len(colmenar["rings"]) == 1
    assert not colmenar["has_interior"]
    lat, lon = colmenar["rings"][0][0]
    assert 39 < lat < 41 and -4 < lon < -3  # orden (lat, lon)


def test_parsing_sin_number_matched_no_lo_exige() -> None:
    body = FIXTURE.read_bytes().replace(b'numberMatched="8"', b"")

    assert parse_administrative_units(body)["number_matched"] is None


def test_parsing_xml_malformado_lanza_error() -> None:
    with pytest.raises(AdministrativeUnitParseError):
        parse_administrative_units(b"<no-xml")


def test_sin_cache_usa_el_reloj_inyectado_y_la_url_completa() -> None:
    adapter = IgnAdministrativeUnitsAdapter(
        BBOX, http_get=lambda url, params: FIXTURE.read_bytes(), today=lambda: date(2026, 5, 1)
    )

    (boundary,) = adapter.get_municipal_boundaries(["28043"])

    assert boundary.provenance.retrieved_at == date(2026, 5, 1)
    assert "request=GetFeature" in boundary.provenance.url


def test_lista_vacia_de_codigos_devuelve_lista_vacia() -> None:
    adapter = IgnAdministrativeUnitsAdapter(BBOX, http_get=lambda url, params: FIXTURE.read_bytes())

    assert adapter.get_municipal_boundaries([]) == []


def test_error_http_se_traduce_a_error_de_puerto() -> None:
    def failing(url: str, params: dict[str, str]) -> bytes:
        raise requests.ConnectionError("sin conexión")

    with pytest.raises(MunicipalBoundaryUnusableError):
        IgnAdministrativeUnitsAdapter(BBOX, http_get=failing).get_municipal_boundaries(["28043"])


def test_municipio_con_hueco_se_rechaza_en_vez_de_descartarlo() -> None:
    # Fixture SINTÉTICA: la real con un gml:interior inyectado en el primer anillo (Colmenar).
    body = FIXTURE.read_bytes().replace(
        b"</gml:exterior>",
        b"</gml:exterior><gml:interior><gml:LinearRing><gml:posList>"
        b"39 -3 39 -3.1 39.1 -3.1 39 -3</gml:posList></gml:LinearRing></gml:interior>",
        1,
    )
    adapter = IgnAdministrativeUnitsAdapter(BBOX, http_get=lambda url, params: body)

    with pytest.raises(MunicipalBoundaryUnusableError, match="28043"):
        adapter.get_municipal_boundaries(["28043"])
    # Un municipio sin huecos de la misma respuesta sigue siendo utilizable.
    assert adapter.get_municipal_boundaries(["28170"])[0].ine_code == "28170"
