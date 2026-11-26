"""Parseo de `Consulta_DNPPP` y filtro de camino. Fixtures sintéticas (#45/#46), sin red."""

from __future__ import annotations

from pathlib import Path

import pytest

from parcel_intel.adapters.catastro.camino import es_camino, es_camino_catastro
from parcel_intel.adapters.catastro.parsing import parse_dnppp
from parcel_intel.ports.errors import ParcelNotFoundError
from tests.fixtures import generate_caminos

CAMINOS = Path(__file__).parents[2] / "fixtures" / "caminos"
REF = "28043A99109301"


def test_parsea_una_via_vt_de_la_fixture_sintetica() -> None:
    xml = (CAMINOS / "catastro_dnppp_sintetica_pol991_parc9101.xml").read_bytes()
    resultado = parse_dnppp(xml, "28043A99109101")
    assert resultado["paraje"] == "PARAJE SINTETICO"
    assert [s["class_code"] for s in resultado["subparcels"]] == ["VT"]
    assert resultado["subparcels"][0]["area_m2"] == 6011.0


def test_parsea_la_parcela_de_control_con_cultivo() -> None:
    xml = (CAMINOS / "catastro_dnppp_sintetica_pol991_parc1.xml").read_bytes()
    sub = parse_dnppp(xml, "28043A99100001")["subparcels"]
    assert [(s["class_code"], s["description"]) for s in sub] == [("C-", "LABOR O LABRADÍO SECANO")]


def test_parsea_varias_subparcelas() -> None:
    cuerpo = generate_caminos.render_dnppp(REF, "C-", "LABOR", 10).decode("utf-8")
    segunda = (
        "      <spr>\n        <cspr>1</cspr>\n        <dspr>\n          <ccc>E-</ccc>\n"
        "          <dcc>PASTOS</dcc>\n          <ip>00</ip>\n          <ssp>20</ssp>\n"
        "        </dspr>\n      </spr>\n    </lspr>"
    )
    xml = cuerpo.replace("    </lspr>", segunda).encode("utf-8")
    sub = parse_dnppp(xml, REF)["subparcels"]
    assert [(s["class_code"], s["area_m2"]) for s in sub] == [("C-", 10.0), ("E-", 20.0)]


def test_sin_subparcelas_ni_paraje() -> None:
    xml = (
        b'<consulta_dnp xmlns="http://www.catastro.meh.es/"><control><cudnp>1</cudnp></control>'
        b"<bico><bi><dt/></bi></bico></consulta_dnp>"
    )
    assert parse_dnppp(xml, REF) == {"paraje": None, "subparcels": ()}


def test_error_de_control_lanza_parcel_not_found() -> None:
    xml = (
        b'<consulta_dnp xmlns="http://www.catastro.meh.es/"><control><cuerr>1</cuerr></control>'
        b"<lerr><err><cod>43</cod><des>NO EXISTE</des></err></lerr></consulta_dnp>"
    )
    with pytest.raises(ParcelNotFoundError):
        parse_dnppp(xml, REF)


@pytest.mark.parametrize(
    ("clase", "esperado"), [("VT", True), (" vt ", True), ("HG", False), ("", False)]
)
def test_es_camino(clase: str, esperado: bool) -> None:
    assert es_camino(clase) is esperado


def test_es_camino_catastro_exige_9000_y_todas_vt() -> None:
    assert es_camino_catastro(9101, ["VT"])
    assert es_camino_catastro(9000, ["VT", "VT"])
    assert not es_camino_catastro(8999, ["VT"])
    assert not es_camino_catastro(9101, ["VT", "C-"])
    assert not es_camino_catastro(9101, ["HG"])
    assert not es_camino_catastro(9101, [])
