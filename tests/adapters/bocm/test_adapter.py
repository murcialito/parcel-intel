from pathlib import Path

import pytest

from parcel_intel.adapters.bocm.adapter import BocmAdapter
from parcel_intel.adapters.bocm.client import SUMARIOS_RSS_URL
from parcel_intel.adapters.bocm.parsing import derive_xml_url, extract_identifier_pdf_pairs
from parcel_intel.domain.bulletin import filter_by_title
from parcel_intel.ports.errors import BulletinNotPublishedError, InvalidBulletinDayError

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures" / "bocm"
DISPOSICIONES_DIR = FIXTURES_DIR / "disposiciones"

# XML mínimo válido para cualquier disposición de la que no se capturó una
# fixture real -- permite ejercitar el pipeline completo (81 peticiones: 1
# RSS + 80 XML) sin almacenar 80 ficheros reales en el repo. Las cuatro
# disposiciones que sí importan para los asserts (1, 2, 3 y 32 -- la 32 es
# la coincidencia real de "Colmenar de Oreja" y la 3 la de "madrid" como
# término genérico, independiente de los municipios del MVP) usan la
# fixture real.
_GENERIC_XML = b"""<documento>
  <metadatos>
    <identificador>BOCM-GENERICA</identificador>
    <titulo>Disposicion generica de prueba, sin relacion con los municipios del MVP</titulo>
    <seccion>III. ADMINISTRACION LOCAL AYUNTAMIENTOS</seccion>
  </metadatos>
</documento>"""


class _FakeUrlGetter:
    def __init__(self, real_xml_paths: dict[str, Path]) -> None:
        self._real_xml_paths = real_xml_paths
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if url == SUMARIOS_RSS_URL:
            return (FIXTURES_DIR / "sumarios.rss").read_bytes()
        if url in self._real_xml_paths:
            return self._real_xml_paths[url].read_bytes()
        return _GENERIC_XML


def _real_xml_url_map() -> dict[str, Path]:
    mapping = {}
    for n in (1, 2, 3, 32):
        pdf_url = f"https://www.bocm.es/boletin/CM_Orden_BOCM/2026/10/15/BOCM-20261015-{n}.PDF"
        mapping[derive_xml_url(pdf_url)] = DISPOSICIONES_DIR / f"BOCM-20261015-{n}.xml"
    return mapping


def test_extrae_80_pares_reales_del_sumario_del_dia() -> None:
    rss_body = (FIXTURES_DIR / "sumarios.rss").read_bytes()
    import xml.etree.ElementTree as ET

    root = ET.fromstring(rss_body)
    first_item = next(root.iter("item"))
    description_el = first_item.find("description")
    assert description_el is not None and description_el.text is not None

    pairs = extract_identifier_pdf_pairs(description_el.text)

    assert len(pairs) == 80
    assert pairs[0]["identifier"] == "BOCM-20261015-1"
    assert pairs[0]["pdf_url"].endswith("BOCM-20261015-1.PDF")


def test_derive_xml_url_cambia_solo_la_extension() -> None:
    pdf_url = "https://www.bocm.es/boletin/CM_Orden_BOCM/2026/10/15/BOCM-20261015-32.PDF"
    assert derive_xml_url(pdf_url) == (
        "https://www.bocm.es/boletin/CM_Orden_BOCM/2026/10/15/BOCM-20261015-32.xml"
    )


def test_bulletin_del_dia_real_con_80_disposiciones_y_coincidencia_real_colmenar() -> None:
    getter = _FakeUrlGetter(_real_xml_url_map())
    adapter = BocmAdapter(get_url=getter)

    notices = adapter.get_daily_bulletin("20261015")

    assert len(notices) == 80
    # 1 RSS + 80 XML -- confirma el coste N+1 por llamada que señala el ADR 0009.
    assert len(getter.calls) == 81

    colmenar = filter_by_title(notices, "Colmenar de Oreja")
    assert len(colmenar) == 1
    assert colmenar[0].identifier == "BOCM-20261015-32"
    assert "Ayuntamiento de Colmenar de Oreja" in colmenar[0].title
    assert colmenar[0].section_code == "I"
    assert colmenar[0].section_name == "COMUNIDAD DE MADRID"

    assert filter_by_title(notices, "Villaconejos") == []
    assert all(n.provenance.source == "bocm" for n in notices)
    assert all(n.provenance.url == SUMARIOS_RSS_URL for n in notices)


def test_filtro_por_termino_generico_madrid_no_depende_de_colmenar_o_villaconejos() -> None:
    """Criterio de aceptación (`docs/stories/0009-ingesta-bocm.md:30`): el
    filtro debe probarse con un término genérico que aparece en el título
    de alguna disposición real, sin depender de que "Colmenar de Oreja" o
    "Villaconejos" aparezcan por casualidad.

    Verificación real (ver `REGISTRY.md` / ADR 0009): sobre las 80
    disposiciones reales del 20261015, "madrid" aparece en 38 títulos,
    entre ellas la Nº 3 ("Convocatoria proceso selectivo..."), que no
    menciona ningún municipio del MVP -- confirma que el filtro funciona
    de forma independiente de la coincidencia de Colmenar."""
    getter = _FakeUrlGetter(_real_xml_url_map())
    adapter = BocmAdapter(get_url=getter)

    notices = adapter.get_daily_bulletin("20261015")

    madrid_by_id = {n.identifier: n for n in filter_by_title(notices, "madrid")}

    assert "BOCM-20261015-3" in madrid_by_id
    assert "BOCM-20261015-32" in madrid_by_id
    # La Nº 3 es la prueba de independencia: coincide con "madrid" sin
    # mencionar Colmenar de Oreja ni Villaconejos en su título real.
    assert "colmenar" not in madrid_by_id["BOCM-20261015-3"].title.lower()
    assert "villaconejos" not in madrid_by_id["BOCM-20261015-3"].title.lower()


def test_dia_fuera_de_la_ventana_de_20_boletines_lanza_error() -> None:
    getter = _FakeUrlGetter({})
    adapter = BocmAdapter(get_url=getter)

    with pytest.raises(BulletinNotPublishedError) as exc_info:
        adapter.get_daily_bulletin("20200101")

    assert "20200101" in str(exc_info.value)
    # Solo se pidió el RSS -- nunca llegó a intentar ningún XML de disposición.
    assert getter.calls == [SUMARIOS_RSS_URL]


@pytest.mark.parametrize("bad_day", ["20261332", "2026101", "2026-10-15", "", "abcdefgh"])
def test_dia_con_formato_invalido_lanza_error_antes_de_red(bad_day: str) -> None:
    getter = _FakeUrlGetter({})
    adapter = BocmAdapter(get_url=getter)

    with pytest.raises(InvalidBulletinDayError):
        adapter.get_daily_bulletin(bad_day)

    assert getter.calls == []
