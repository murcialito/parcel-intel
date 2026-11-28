import json
import shutil
from pathlib import Path

import pytest

from parcel_intel.adapters.curated_historic import CuratedHistoricFiles
from parcel_intel.domain.digitization import InvalidDigitizationError
from parcel_intel.domain.georeferencing import InvalidControlPointError
from parcel_intel.ports.errors import CuratedUnitNotFoundError

HISTORICO = (
    Path(__file__).resolve().parents[2] / "fixtures" / "caminos" / "planimetrias" / "historico"
)
UNIT = "280075-w1"


def _copy(tmp_path: Path) -> Path:
    shutil.copytree(HISTORICO / UNIT, tmp_path / UNIT)
    return tmp_path


def test_falta_un_fichero_de_la_unidad(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    (root / UNIT / "trazados.geojson").unlink()
    with pytest.raises(CuratedUnitNotFoundError, match="trazados.geojson"):
        CuratedHistoricFiles(root).read_trails(UNIT)


def test_unit_ids_ordena_e_ignora_lo_que_no_es_una_unidad(tmp_path: Path) -> None:
    shutil.copytree(HISTORICO / UNIT, tmp_path / "280075-w2")
    shutil.copytree(HISTORICO / UNIT, tmp_path / UNIT)
    shutil.copytree(HISTORICO / UNIT, tmp_path / "no-es-unidad")
    (tmp_path / "280075-w3").mkdir()  # nombre válido pero sin unidad.json
    (tmp_path / "LEEME.md").write_text("texto", encoding="utf-8")
    assert CuratedHistoricFiles(tmp_path).unit_ids() == (UNIT, "280075-w2")


def test_unit_ids_sin_directorio_raiz_es_vacio(tmp_path: Path) -> None:
    assert CuratedHistoricFiles(tmp_path / "no_existe").unit_ids() == ()


def test_unit_id_malformado_no_toca_el_sistema_de_ficheros(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unit_id"):
        CuratedHistoricFiles(tmp_path).read_unit("../../etc")


def test_csv_con_finales_crlf_y_linea_final_en_blanco_se_lee(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    path = root / UNIT / "puntos_control.csv"
    original = path.read_bytes()
    crlf = original.replace(b"\n", b"\r\n") + b"\r\n"
    path.write_bytes(crlf)
    points = CuratedHistoricFiles(root).read_control_points(UNIT)
    assert len(points.points) == 8
    assert points.points[7].discard_reason == "Referencia ambigua en el mapa"
    assert points.sha256 != CuratedHistoricFiles(HISTORICO).read_control_points(UNIT).sha256


def test_csv_con_numero_con_coma_decimal_se_rechaza(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    path = root / UNIT / "puntos_control.csv"
    path.write_text(path.read_text("utf-8").replace("60.0,70.0", "60,5,70.0", 1), "utf-8")
    with pytest.raises(InvalidControlPointError):
        CuratedHistoricFiles(root).read_control_points(UNIT)


def test_trazados_con_json_roto_o_estado_aprobado_sin_hash_se_rechazan(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    path = root / UNIT / "trazados.geojson"
    data = json.loads(path.read_text("utf-8"))
    del data["features"][0]["properties"]["control_points_sha256"]
    path.write_text(json.dumps(data), "utf-8")
    with pytest.raises(InvalidDigitizationError, match="T001"):
        CuratedHistoricFiles(root).read_trails(UNIT)
    path.write_text("{", "utf-8")
    with pytest.raises(InvalidDigitizationError, match="JSON"):
        CuratedHistoricFiles(root).read_trails(UNIT)


def test_vertice_tridimensional_o_no_numerico_se_rechaza(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    path = root / UNIT / "trazados.geojson"
    data = json.loads(path.read_text("utf-8"))
    data["features"][2]["geometry"]["coordinates"] = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    path.write_text(json.dumps(data), "utf-8")
    with pytest.raises(InvalidDigitizationError, match="vértice"):
        CuratedHistoricFiles(root).read_trails(UNIT)


def _set_municipality(root: Path, value: object) -> None:
    path = root / UNIT / "trazados.geojson"
    data = json.loads(path.read_text("utf-8"))
    data["features"][0]["properties"]["municipality_code"] = value
    path.write_text(json.dumps(data), "utf-8")


def test_trazado_lee_su_municipality_code_y_sin_el_queda_none(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    assert all(t.municipality_code is None for t in CuratedHistoricFiles(root).read_trails(UNIT))
    _set_municipality(root, "28043")
    trails = CuratedHistoricFiles(root).read_trails(UNIT)
    assert trails[0].municipality_code == "28043"
    assert all(t.municipality_code is None for t in trails[1:])


@pytest.mark.parametrize("bad", ["2804", "abcde", "280430", 28043])
def test_municipality_code_mal_formado_se_rechaza(tmp_path: Path, bad: object) -> None:
    root = _copy(tmp_path)
    _set_municipality(root, bad)
    with pytest.raises(InvalidDigitizationError):
        CuratedHistoricFiles(root).read_trails(UNIT)
