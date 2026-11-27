"""Lector del informe de medición (historia #170). Ficheros sintéticos en `tmp_path`."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.adapters.published_layers import JsonMeasurementReportReader
from parcel_intel.ports.errors import MeasurementReportUnavailableError

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "candidatos_publicar"
SECRET = "valor-secreto-rechazado"


def _document() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(
        (FIXTURE / "medicion_calculable.json").read_text(encoding="utf-8")
    )
    return loaded


def _read(tmp_path: Path, document: object) -> JsonMeasurementReportReader:
    path = tmp_path / "medicion.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return JsonMeasurementReportReader(path)


def test_lee_las_claves_que_usa_del_informe_real() -> None:
    report = JsonMeasurementReportReader(FIXTURE / "medicion_calculable.json").get_measurement()
    assert report.label == "validacion-v1"
    assert report.frozen is True
    assert report.run_date == date(2026, 11, 27)
    assert report.candidate_methods == ("candidato_corte@1",)
    assert (report.total_cases, report.out_of_scope_cases) == (6, 4)
    assert (report.evaluable_cases, report.flagged_cases, report.coverage) == (2, 1, 0.5)
    assert (report.evaluable_candidates, report.hit_candidates) == (3, 1)
    assert report.precision == 0.3333
    assert report.precision_bound == "inferior"


def test_no_calculable_es_none_e_ignora_claves_desconocidas(tmp_path: Path) -> None:
    document = json.loads((FIXTURE / "medicion.json").read_text(encoding="utf-8"))
    document["aviso"] = "lo que sea"
    document["nueva_clave"] = {"x": 1}
    report = _read(tmp_path, document).get_measurement()
    assert report.coverage is None and report.precision is None


def test_sin_fuera_del_ambito_cuenta_cero(tmp_path: Path) -> None:
    document = _document()
    document["no_evaluables"]["por_motivo"] = {}
    assert _read(tmp_path, document).get_measurement().out_of_scope_cases == 0


def test_fichero_ausente_o_roto(tmp_path: Path) -> None:
    missing = tmp_path / "no.json"
    with pytest.raises(MeasurementReportUnavailableError) as error:
        JsonMeasurementReportReader(missing).get_measurement()
    assert str(error.value) == f"Informe de medición no disponible {missing}: no existe"
    broken = tmp_path / "roto.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(MeasurementReportUnavailableError) as error:
        JsonMeasurementReportReader(broken).get_measurement()
    assert "no es JSON" in error.value.detail


@pytest.mark.parametrize(
    ("path", "value", "key"),
    [
        (("etiqueta",), 3, "etiqueta"),
        (("congelado",), "sí", "congelado"),
        (("fecha",), "27/11/2026", "fecha"),
        (("metodo_candidatos",), "candidato_corte@1", "metodo_candidatos"),
        (("metodo_candidatos",), [SECRET], "metodo_candidatos"),
        (("casos_total",), True, "casos_total"),
        (("casos_total",), -1, "casos_total"),
        (("cobertura", "casos_evaluables"), 1.5, "cobertura.casos_evaluables"),
        (("cobertura", "valor"), SECRET, "cobertura.valor"),
        (("precision", "cota"), 1, "precision.cota"),
        (("no_evaluables", "por_motivo", "fuera_del_ambito"), SECRET, "fuera_del_ambito"),
        (("precision",), [], "precision"),
    ],
)
def test_tipo_inesperado_nombra_la_clave_y_no_el_valor(
    tmp_path: Path, path: tuple[str, ...], value: object, key: str
) -> None:
    document = _document()
    target = document
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(MeasurementReportUnavailableError) as error:
        _read(tmp_path, document).get_measurement()
    assert key in error.value.detail
    assert SECRET not in str(error.value)


@pytest.mark.parametrize(
    "path",
    [("etiqueta",), ("fecha",), ("cobertura",), ("precision", "valor"), ("no_evaluables",)],
)
def test_clave_que_falta(tmp_path: Path, path: tuple[str, ...]) -> None:
    document = _document()
    target = document
    for part in path[:-1]:
        target = target[part]
    del target[path[-1]]
    with pytest.raises(MeasurementReportUnavailableError) as error:
        _read(tmp_path, document).get_measurement()
    assert "falta la clave" in error.value.detail


def test_raiz_que_no_es_objeto(tmp_path: Path) -> None:
    with pytest.raises(MeasurementReportUnavailableError):
        _read(tmp_path, [1, 2]).get_measurement()
