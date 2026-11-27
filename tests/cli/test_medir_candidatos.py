"""Subcomando `medir-candidatos` (historia #111): informe agregado, sin red."""

import json
from pathlib import Path
from typing import Any

import pytest

from tests.medir_candidatos_support import escribir_candidatos, escribir_casos, medir


def _informe(ruta: Path) -> dict[str, Any]:
    datos: dict[str, Any] = json.loads(ruta.read_text(encoding="utf-8"))
    return datos


def test_cobertura_y_precision_con_recuentos(tmp_path: Path) -> None:
    casos = escribir_casos(tmp_path / "validacion")
    escribir_candidatos(tmp_path / "candidatos")
    salida = tmp_path / "out" / "medicion.json"
    assert medir(casos, tmp_path / "candidatos", salida) == 0
    informe = _informe(salida)
    assert informe["cobertura"]["valor"] == 1.0
    assert informe["cobertura"]["casos_senalados"] == 1
    assert informe["cobertura"]["casos_evaluables"] == 1
    assert informe["precision"]["valor"] == 0.5
    assert informe["precision"]["cota"] == "inferior"
    assert informe["precision"]["candidatos_acertados"] == 1
    assert informe["precision"]["candidatos_evaluables"] == 2
    assert informe["criterio_casamiento"]["identificador"] == "casamiento_candidato_caso"


def test_motivos_de_no_evaluables(tmp_path: Path) -> None:
    casos = escribir_casos(tmp_path / "validacion")
    escribir_candidatos(tmp_path / "candidatos")
    salida = tmp_path / "medicion.json"
    medir(casos, tmp_path / "candidatos", salida)
    no_eval = _informe(salida)["no_evaluables"]
    assert no_eval["total"] == 5
    assert no_eval["por_motivo"] == {"fuera_del_ambito": 3, "sin_capas": 1, "sin_geometria": 1}


def test_sin_ningun_fichero_de_candidatos_las_metricas_son_nulas(tmp_path: Path) -> None:
    casos = escribir_casos(tmp_path / "validacion")
    salida = tmp_path / "medicion.json"
    assert medir(casos, tmp_path / "vacio", salida) == 0
    informe = _informe(salida)
    assert informe["cobertura"]["valor"] is None
    assert informe["precision"]["valor"] is None
    assert informe["metodo_candidatos"] == []


def test_fichero_ilegible_sale_con_1_y_no_escribe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    casos = escribir_casos(tmp_path / "validacion")
    entrada = tmp_path / "candidatos"
    entrada.mkdir()
    (entrada / "28043.geojson").write_text("no es json", encoding="utf-8")
    salida = tmp_path / "medicion.json"
    assert medir(casos, entrada, salida) == 1
    assert "28043.geojson" in capsys.readouterr().err
    assert not salida.exists()


def test_casos_que_no_pasan_el_validador_salen_con_1(tmp_path: Path) -> None:
    carpeta = tmp_path / "validacion"
    carpeta.mkdir()
    (carpeta / "casos.json").write_text('{"casos": [{"id": "x"}]}', encoding="utf-8")
    salida = tmp_path / "medicion.json"
    assert medir(carpeta / "casos.json", tmp_path / "c", salida) == 1
    assert not salida.exists()


def test_sin_congelado_el_conjunto_se_marca_no_congelado(tmp_path: Path) -> None:
    casos = escribir_casos(tmp_path / "validacion", congelar_conjunto=False)
    salida = tmp_path / "medicion.json"
    assert medir(casos, tmp_path / "c", salida) == 0
    informe = _informe(salida)
    assert informe["congelado"] is False
    assert informe["etiqueta"] is None
