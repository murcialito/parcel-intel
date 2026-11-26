"""Tests unitarios del generador de fixtures sintéticas de caminos de Catastro (historia #46)."""

from pathlib import Path

import pytest

from tests.fixtures import generate_caminos as gen


def test_el_teselado_cubre_600x600_sin_huecos_ni_solapes() -> None:
    assert len(gen.TILES) == 20
    assert sum(t.area for t in gen.TILES) == 600 * 600
    for i, a in enumerate(gen.TILES):
        for b in gen.TILES[i + 1 :]:
            assert not (min(a.x1, b.x1) > max(a.x0, b.x0) and min(a.y1, b.y1) > max(a.y0, b.y0))


def test_anillo_horario_cerrado_con_origen_sintetico() -> None:
    ring = gen.clockwise_ring(gen.TILES[0])

    assert ring == (
        (469000.0, 4439000.0),
        (469000.0, 4439145.0),
        (469145.0, 4439145.0),
        (469145.0, 4439000.0),
        (469000.0, 4439000.0),
    )


def test_render_dnppp_deriva_poligono_y_parcela_de_la_referencia() -> None:
    body = gen.render_dnppp("28043A99109101", "VT", "VÍA", 6011).decode("utf-8")

    assert "<cpo>991</cpo>" in body and "<cpa>9101</cpa>" in body
    assert "<pc1>28043A9</pc1>" in body and "<pc2>9109101</pc2>" in body
    assert "<ssp>6011</ssp>" in body
    assert "Polígono 991 Parcela 9101 PARAJE SINTETICO" in body


def test_nombres_de_fichero_no_codifican_datos_reales() -> None:
    nombres = sorted(gen.build_all())

    assert nombres == [
        "catastro_dnppp_sintetica_pol991_parc1.xml",
        "catastro_dnppp_sintetica_pol991_parc9101.xml",
        "catastro_dnppp_sintetica_pol991_parc9102.xml",
        "catastro_dnppp_sintetica_pol992_parc9201.xml",
        "catastro_dnppp_sintetica_pol992_parc9202.xml",
        "catastro_wfsCP_sintetica_rustica_bbox600m.xml",
    ]


def test_check_devuelve_1_si_un_fichero_difiere_falta_o_sobra(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gen.main(["--destino", str(tmp_path)]) == 0
    assert gen.main(["--check", "--destino", str(tmp_path)]) == 0

    (tmp_path / "catastro_wfsCP_sintetica_rustica_bbox600m.xml").write_bytes(b"<x/>")
    (tmp_path / "catastro_dnppp_sintetica_pol991_parc1.xml").unlink()
    (tmp_path / "catastro_original.xml").write_bytes(b"<x/>")
    (tmp_path / "otra_fuente.json").write_text("{}", encoding="utf-8")

    assert gen.main(["--check", "--destino", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "difiere catastro_wfsCP_sintetica_rustica_bbox600m.xml" in err
    assert "falta catastro_dnppp_sintetica_pol991_parc1.xml" in err
    assert "sobra catastro_original.xml" in err
    assert "otra_fuente" not in err


def test_argumentos_desconocidos_devuelven_2() -> None:
    assert gen.main(["--otra-cosa"]) == 2
