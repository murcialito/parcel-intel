import pytest

from parcel_intel.adapters.catastro.parsing import geometry_from_rings, parse_wfs_parcels
from parcel_intel.adapters.pnoa.adapter import DEFAULT_MARGIN_M, PnoaAdapter
from parcel_intel.domain.geometry import Geometry, bbox_with_margin
from parcel_intel.ports.errors import InvalidHistoricalVintageError
from tests.adapters.pnoa.helpers import FIXTURES_DIR, SequenceHttpGetter

_CATASTRO_FIXTURES_DIR = FIXTURES_DIR.parent / "catastro"


def _parcela_con_edificios() -> Geometry:
    """Parcela sintética 9900105ZZ0000S (historia #45): conserva la envolvente
    de la parcela urbana de Colmenar de Oreja con la que se grabaron las
    ortofotos, así que el bbox que produce con el margen por defecto de PNOA
    es exactamente el usado para grabar esas fixtures."""
    xml = (_CATASTRO_FIXTURES_DIR / "wfsCP_colmenar_parcela_con_edificios.xml").read_bytes()
    parcels = parse_wfs_parcels(xml)
    target = next(p for p in parcels if p["reference"] == "9900105ZZ0000S")
    return geometry_from_rings(target["rings"])


def test_bbox_calculado_coincide_con_el_de_las_fixtures_grabadas() -> None:
    geometry = _parcela_con_edificios()

    bbox = bbox_with_margin(geometry, DEFAULT_MARGIN_M)

    assert bbox == pytest.approx((457143.87, 4436008.27, 457193.48, 4436065.23))


def test_get_current_orthophoto_real() -> None:
    http_get = SequenceHttpGetter([FIXTURES_DIR / "getmap_parcela_real_bbox_actual.jpg"])
    adapter = PnoaAdapter(http_get=http_get)
    geometry = _parcela_con_edificios()

    orthophoto = adapter.get_current_orthophoto(geometry, DEFAULT_MARGIN_M)

    assert orthophoto.vintage == "actual"
    assert orthophoto.image.startswith(b"\xff\xd8")  # cabecera JPEG real
    assert orthophoto.provenance.source == "pnoa-actual"
    assert "OI.OrthoimageCoverage" in orthophoto.provenance.url
    assert len(http_get.calls) == 1


def test_get_historical_orthophoto_year_real() -> None:
    # PNOA2010 y PNOA2016 devuelven, para este bbox exacto, un placeholder en
    # blanco real (verificado contra la red: 1819 bytes, sin contenido visual
    # útil) -- PNOA2020 sí tiene cobertura real (45 KB) y sirve de evidencia
    # no trivial de que el vuelo histórico pedido es el que de verdad llega.
    http_get = SequenceHttpGetter([FIXTURES_DIR / "getmap_parcela_real_bbox_pnoa2020.jpg"])
    adapter = PnoaAdapter(http_get=http_get)
    geometry = _parcela_con_edificios()

    orthophoto = adapter.get_historical_orthophoto(geometry, DEFAULT_MARGIN_M, 2020)

    assert orthophoto.vintage == 2020
    assert orthophoto.image.startswith(b"\xff\xd8")
    assert orthophoto.provenance.source == "pnoa-historico"
    assert "PNOA2020" in orthophoto.provenance.url


def test_get_historical_orthophoto_vuelo_nombrado_real() -> None:
    http_get = SequenceHttpGetter([FIXTURES_DIR / "getmap_parcela_real_bbox_ams1956.jpg"])
    adapter = PnoaAdapter(http_get=http_get)
    geometry = _parcela_con_edificios()

    orthophoto = adapter.get_historical_orthophoto(geometry, DEFAULT_MARGIN_M, "AMS_1956-1957")

    assert orthophoto.vintage == "AMS_1956-1957"
    assert "AMS_1956-1957" in orthophoto.provenance.url


def _format_bbox(geometry: Geometry, margin_m: float) -> str:
    minx, miny, maxx, maxy = bbox_with_margin(geometry, margin_m)
    return f"{minx},{miny},{maxx},{maxy}"


def test_margen_distinto_produce_bbox_distinto_en_la_peticion() -> None:
    http_get = SequenceHttpGetter([FIXTURES_DIR / "getmap_colmenar_actual.jpg"])
    adapter = PnoaAdapter(http_get=http_get)
    geometry = _parcela_con_edificios()

    adapter.get_current_orthophoto(geometry, margin_m=100.0)

    _, params = http_get.calls[0]
    assert params["bbox"] == _format_bbox(geometry, 100.0)
    assert params["bbox"] != _format_bbox(geometry, DEFAULT_MARGIN_M)


@pytest.mark.parametrize("vintage", [1999, 2030, "no-es-un-vuelo-valido"])
def test_vintage_no_confirmado_lanza_error_antes_de_la_red(vintage: object) -> None:
    http_get = SequenceHttpGetter([])  # ninguna fixture: una llamada real fallaría con IndexError
    adapter = PnoaAdapter(http_get=http_get)
    geometry = _parcela_con_edificios()

    with pytest.raises(InvalidHistoricalVintageError):
        adapter.get_historical_orthophoto(geometry, DEFAULT_MARGIN_M, vintage)  # type: ignore[arg-type]

    assert http_get.calls == []


@pytest.mark.parametrize("year", [2004, 2024])
def test_limites_del_rango_de_anios_confirmados_son_validos(year: int) -> None:
    http_get = SequenceHttpGetter([FIXTURES_DIR / "getmap_parcela_real_bbox_pnoa2020.jpg"])
    adapter = PnoaAdapter(http_get=http_get)
    geometry = _parcela_con_edificios()

    orthophoto = adapter.get_historical_orthophoto(geometry, DEFAULT_MARGIN_M, year)

    assert orthophoto.vintage == year
