"""Tests del adapter de Catastro sobre las fixtures SINTÉTICAS de la historia #45.

Las fixtures de `tests/fixtures/catastro/` las genera `tests/fixtures/generate_catastro.py`
con el esquema de las respuestas reales y datos inventados (provincia `99`, hoja `ZZ`).
"""

from datetime import date

import pytest

from parcel_intel.adapters.catastro.adapter import CatastroAdapter
from parcel_intel.adapters.catastro.geometry_ops import ring_centroid
from parcel_intel.adapters.catastro.parsing import parse_wfs_buildings, parse_wfs_parcels
from parcel_intel.ports.errors import ParcelNotFoundError
from tests.adapters.catastro.helpers import FIXTURES_DIR, SequenceHttpGetter


def _adapter(http_get: SequenceHttpGetter, municipio: str) -> CatastroAdapter:
    return CatastroAdapter(provincia="MADRID", municipio=municipio, http_get=http_get)


def _buildings_getter() -> SequenceHttpGetter:
    return SequenceHttpGetter(
        [
            FIXTURES_DIR / "cpmrc_colmenar_edificio.xml",
            FIXTURES_DIR / "wfsCP_colmenar_parcela_con_edificios.xml",
            FIXTURES_DIR / "wfsBU_colmenar_dense_bbox.xml",
        ]
    )


def test_get_parcel_rustica_colmenar_de_oreja() -> None:
    http_get = SequenceHttpGetter(
        [
            FIXTURES_DIR / "cpmrc_colmenar_14char.xml",
            FIXTURES_DIR / "wfsCP_colmenar_rustica_por_centroide.xml",
        ]
    )
    reloj_fijo = date(2026, 1, 15)
    adapter = CatastroAdapter(
        provincia="MADRID",
        municipio="COLMENAR DE OREJA",
        http_get=http_get,
        clock=lambda: reloj_fijo,
    )

    parcel = adapter.get_parcel("99043A901000010000ZZ")

    assert parcel.cadastral_reference == "99043A90100001"
    assert parcel.municipality == "COLMENAR DE OREJA"
    assert parcel.area_m2 == 844.0
    assert parcel.geometry.srid == 25830
    assert len(parcel.geometry.rings) == 1
    assert len(parcel.geometry.rings[0]) == 5  # rombo cerrado
    assert parcel.provenance.source == "catastro"
    assert parcel.provenance.retrieved_at == reloj_fijo


def test_get_parcel_normaliza_referencia_de_20_a_14_caracteres() -> None:
    # CA9 (f): la petición de centroide se hace con la referencia de 14 caracteres.
    http_get = SequenceHttpGetter(
        [
            FIXTURES_DIR / "cpmrc_villaconejos_14char.xml",
            FIXTURES_DIR / "wfsCP_villaconejos_rustica_por_centroide.xml",
        ]
    )
    adapter = _adapter(http_get, "VILLACONEJOS")

    parcel = adapter.get_parcel("99170A901000010000ZZ")

    assert parcel.cadastral_reference == "99170A90100001"
    assert http_get.calls[0][1]["RC"] == "99170A90100001"
    assert parcel.area_m2 == 25290.0


def test_get_parcel_multisurface_en_bbox_denso_de_121_parcelas() -> None:
    # CA9 (c): el objetivo es un MultiSurface de 2 superficies en medio de una rejilla.
    http_get = SequenceHttpGetter(
        [
            FIXTURES_DIR / "cpmrc_colmenar_urbano_14char.xml",
            FIXTURES_DIR / "wfsCP_colmenar_bbox_denso.xml",
        ]
    )
    adapter = _adapter(http_get, "COLMENAR DE OREJA")

    parcel = adapter.get_parcel("99043A93700001")

    assert len(
        parse_wfs_parcels((FIXTURES_DIR / "wfsCP_colmenar_bbox_denso.xml").read_bytes())
    ) == (121)
    assert parcel.cadastral_reference == "99043A93700001"
    assert parcel.area_m2 == 320.0
    assert len(parcel.geometry.rings) == 2
    xs = sorted({x for ring in parcel.geometry.rings for x, _ in ring})
    assert xs == [459990.0, 459998.0, 460002.0, 460010.0]


def test_vecina_con_hueco_se_parsea_con_su_anillo_interior() -> None:
    # CA9 (d): la vecina 99170A90100002 trae exterior + 1 gml:interior; el parser
    # devuelve los dos anillos (el adapter de Catastro no descarta huecos).
    xml = (FIXTURES_DIR / "wfsCP_villaconejos_rustica_por_centroide.xml").read_bytes()
    assert xml.count(b"<gml:interior>") == 1

    vecina = next(p for p in parse_wfs_parcels(xml) if p["reference"] == "99170A90100002")

    assert len(vecina["rings"]) == 2
    exterior, interior = vecina["rings"]
    ex_xs = [x for x, _ in exterior]
    in_xs = [x for x, _ in interior]
    assert min(ex_xs) < min(in_xs) and max(in_xs) < max(ex_xs)
    assert vecina["area_m2"] == 80.0 * 60.0 - 20.0 * 20.0


def test_get_buildings_parcela_urbana_con_edificio_de_tres_cuerpos() -> None:
    # CA9 (a): el edificio de la parcela tiene 3 cuerpos y se devuelve como 1 edificio.
    http_get = _buildings_getter()
    adapter = _adapter(http_get, "COLMENAR DE OREJA")

    buildings = adapter.get_buildings("9900105ZZ0000S")

    assert len(buildings) == 1
    building = buildings[0]
    assert building.cadastral_reference == "9900105ZZ0000S"
    assert building.area_m2 == 96.0
    assert building.construction_year == 1975
    assert len(building.geometry.rings) == 3
    assert building.origin == "catastro"
    assert building.geometry.srid == 25830


def test_get_buildings_descarta_edificios_fuera_de_la_parcela() -> None:
    # CA9 (b): 9900108ZZ0000S tiene el centroide dentro de la envolvente de la
    # parcela pero fuera del rombo; las demás están en parcelas vecinas.
    xml = (FIXTURES_DIR / "wfsBU_colmenar_dense_bbox.xml").read_bytes()
    vecino = next(b for b in parse_wfs_buildings(xml) if b["reference"] == "9900108ZZ0000S")
    x, y = ring_centroid(vecino["rings"][0])
    assert 457153.87 <= x <= 457183.48 and 4436018.27 <= y <= 4436055.23
    adapter = _adapter(_buildings_getter(), "COLMENAR DE OREJA")

    buildings = adapter.get_buildings("9900105ZZ0000S")

    returned_refs = {b.cadastral_reference for b in buildings}
    assert returned_refs == {"9900105ZZ0000S"}
    assert len(parse_wfs_buildings(xml)) == 11


def test_get_buildings_parcela_rustica_sin_edificios() -> None:
    http_get = SequenceHttpGetter(
        [
            FIXTURES_DIR / "cpmrc_colmenar_14char.xml",
            FIXTURES_DIR / "wfsCP_colmenar_rustica_por_centroide.xml",
            FIXTURES_DIR / "wfsBU_colmenar_urbano_por_centroide.xml",
        ]
    )
    adapter = _adapter(http_get, "COLMENAR DE OREJA")

    buildings = adapter.get_buildings("99043A901000010000ZZ")

    assert buildings == []


def test_get_parcel_referencia_inexistente_lanza_error() -> None:
    # CA9 (e): Consulta_CPMRC con cuerr=1.
    http_get = SequenceHttpGetter(
        [
            FIXTURES_DIR / "cpmrc_no_encontrada.xml",
        ]
    )
    adapter = _adapter(http_get, "COLMENAR DE OREJA")

    with pytest.raises(ParcelNotFoundError):
        adapter.get_parcel("99043A99999999")
