"""Subcomando `catastro-caminos` (historia #37) con la red sustituida por fixtures sintéticas."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from parcel_intel.cli import main
from parcel_intel.domain.cadastral_road import CadastralRoadLayer
from parcel_intel.domain.geometry import BBox
from parcel_intel.ports.errors import AreaQueryLimitExceededError
from tests.caminos_catastro_support import TODAY, WINDOW, FixtureCatastroHttp

_ARGS = [
    "catastro-caminos",
    "--provincia",
    "MADRID",
    "--municipio",
    "COLMENAR DE OREJA",
    "--codigo",
    "28043",
    "--bbox",
    "469000,4439000,469600,4439600",
]


def _run(argv: list[str]) -> int:
    args = main._build_parser().parse_args(argv)
    code: int = args.func(args)
    return code


def _con_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    real = main.build_cadastral_road_layer

    def con_red_falsa(
        provincia: str,
        municipio: str,
        codigo: str,
        bbox: BBox,
        cache_dir: Path,
        offline: bool,
    ) -> CadastralRoadLayer:
        return real(
            provincia,
            municipio,
            codigo,
            bbox,
            cache_dir,
            offline,
            http_get=FixtureCatastroHttp(),
            today=lambda: TODAY,
            sleep=lambda _s: None,
        )

    monkeypatch.setattr(main, "build_cadastral_road_layer", con_red_falsa)


def test_imprime_el_resumen_los_caminos_y_la_marca_de_uso_interno(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _con_fixtures(monkeypatch)
    out = tmp_path / "out"
    assert _run([*_ARGS, "--cache-dir", str(tmp_path), "--salida", str(out)]) == 0
    salida = capsys.readouterr().out
    assert "28043 COLMENAR DE OREJA" in salida
    for fragmento in (
        "teselas: 1",
        "parcelas vistas: 20",
        "candidatas (número >= 9000): 4",
        "caminos: 4",
        "excluidas por clase: 0",
        "sin clasificar: 0",
        "28043A99109101 area_m2=6000.0 clases=VT",
        "28043A99209202 area_m2=1950.0 clases=VT",
    ):
        assert fragmento in salida
    assert "Capa de uso interno: no publicable (licencia INSPIRE de Catastro)." in salida
    assert "rejilla: bbox 469000,4439000,469600,4439600" in salida
    assert (out / "28043.geojson").is_file()


def test_el_cache_dir_por_defecto_es_data_raw_catastro() -> None:
    args = main._build_parser().parse_args(_ARGS)
    assert args.cache_dir == Path("data/raw/catastro")
    assert args.sin_red is False
    assert args.bbox == WINDOW


def test_sin_red_con_cache_vacia_sale_con_1(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert _run([*_ARGS, "--cache-dir", str(tmp_path), "--sin-red"]) == 1
    assert "Sin red y no cacheado" in capsys.readouterr().err


def test_un_error_de_area_sale_con_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def falla(*_args: object) -> CadastralRoadLayer:
        raise AreaQueryLimitExceededError(WINDOW)

    monkeypatch.setattr(main, "build_cadastral_road_layer", falla)
    assert _run(_ARGS) == 1
    assert "límite" in capsys.readouterr().err


@pytest.mark.parametrize("valor", ["1,2,3", "a,b,c,d", "5,0,1,10", "0,5,10,1"])
def test_bbox_invalido_se_rechaza(valor: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        main._bbox_argument(valor)
