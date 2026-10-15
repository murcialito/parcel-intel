from pathlib import Path

import pytest

from parcel_intel.adapters.boe.adapter import BoeAdapter
from parcel_intel.domain.bulletin import filter_by_title
from parcel_intel.ports.errors import BulletinNotPublishedError, InvalidBulletinDayError

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures" / "boe"


class _FixedGetter:
    def __init__(self, status_code: int, body: bytes) -> None:
        self.status_code = status_code
        self.body = body
        self.calls: list[str] = []

    def __call__(self, day: str) -> tuple[int, bytes]:
        self.calls.append(day)
        return self.status_code, self.body


def test_sumario_real_con_166_disposiciones_recorriendo_las_cuatro_variantes() -> None:
    body = (FIXTURES_DIR / "sumario_hoy.json").read_bytes()
    adapter = BoeAdapter(get_daily_summary=_FixedGetter(200, body))

    notices = adapter.get_daily_bulletin("20261015")

    assert len(notices) == 166
    # Al menos una disposición de la variante "departamento.texto.item"
    # (sección 5C, Anuncios particulares) debe estar presente -- si el
    # parsing solo cubriera las otras tres variantes, esta aparecería
    # silenciosamente ausente sin ningún error.
    assert any(n.identifier == "BOE-B-2026-33550" for n in notices)
    # Y al menos una de "departamento.item" directo (sección 5A/5B, sin epígrafe).
    assert any(n.section_code == "5A" for n in notices)
    # Y al menos una de "epigrafe.item" (secciones 1/2A/2B/3).
    assert any(n.section_code == "1" for n in notices)
    assert all(n.provenance.source == "boe" for n in notices)


def test_filtro_por_municipio_real_sin_coincidencias() -> None:
    body = (FIXTURES_DIR / "sumario_hoy.json").read_bytes()
    adapter = BoeAdapter(get_daily_summary=_FixedGetter(200, body))
    notices = adapter.get_daily_bulletin("20261015")

    assert filter_by_title(notices, "Colmenar de Oreja") == []
    assert filter_by_title(notices, "Villaconejos") == []


def test_filtro_por_termino_real_con_coincidencias() -> None:
    body = (FIXTURES_DIR / "sumario_hoy.json").read_bytes()
    adapter = BoeAdapter(get_daily_summary=_FixedGetter(200, body))
    notices = adapter.get_daily_bulletin("20261015")

    madrid = filter_by_title(notices, "madrid")
    assert len(madrid) == 14


def test_filtro_insensible_a_mayusculas_y_tildes() -> None:
    body = (FIXTURES_DIR / "sumario_hoy.json").read_bytes()
    adapter = BoeAdapter(get_daily_summary=_FixedGetter(200, body))
    notices = adapter.get_daily_bulletin("20261015")

    assert filter_by_title(notices, "MADRID") == filter_by_title(notices, "madrid")
    assert filter_by_title(notices, "madrid") == filter_by_title(notices, "MadríD")


def test_mismo_sumario_filtrado_dos_veces_sin_segunda_peticion_de_red() -> None:
    body = (FIXTURES_DIR / "sumario_hoy.json").read_bytes()
    getter = _FixedGetter(200, body)
    adapter = BoeAdapter(get_daily_summary=getter)

    notices = adapter.get_daily_bulletin("20261015")
    filter_by_title(notices, "Colmenar de Oreja")
    filter_by_title(notices, "Villaconejos")

    assert getter.calls == ["20261015"]  # una sola llamada de red


def test_dia_sin_sumario_real_lanza_error_explicito() -> None:
    body = (FIXTURES_DIR / "sumario_sin_publicar_20261011.xml").read_bytes()
    adapter = BoeAdapter(get_daily_summary=_FixedGetter(404, body))

    with pytest.raises(BulletinNotPublishedError) as exc_info:
        adapter.get_daily_bulletin("20261011")

    assert "20261011" in str(exc_info.value)


@pytest.mark.parametrize(
    "bad_day", ["20261332", "2026101", "2026-10-15", "", "abcdefgh"]
)
def test_dia_con_formato_invalido_lanza_error_antes_de_red(bad_day: str) -> None:
    getter = _FixedGetter(400, b"")
    adapter = BoeAdapter(get_daily_summary=getter)

    with pytest.raises(InvalidBulletinDayError):
        adapter.get_daily_bulletin(bad_day)

    assert getter.calls == []
