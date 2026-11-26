"""Tests unitarios del validador de `docs/validacion/casos.json` (historia #51). No llaman a red."""

import json
from pathlib import Path

from tests.validacion.casos_schema import validar_casos

REPO = Path(__file__).resolve().parents[2]
CASOS = REPO / "docs" / "validacion" / "casos.json"


def _caso() -> dict[str, object]:
    return {
        "id": "caso-prueba-1",
        "fuente_url": "https://www.ejemplo.es/noticia-camino",
        "fuente_tipo": "prensa",
        "fecha_consulta": "2026-11-26",
        "municipio": "Colmenar de Oreja",
        "ambito": "hito",
        "tramo_descripcion": "camino entre la carretera de Ocaña y el arroyo del Soto",
        "cierre_fecha_aproximada": "2019-05",
    }


def test_fichero_real_arranca_sin_errores() -> None:
    datos: object = json.loads(CASOS.read_text(encoding="utf-8"))
    assert validar_casos(datos) == []


def test_top_level_sin_clave_casos_es_error() -> None:
    assert validar_casos([]) != []
    assert validar_casos({"otra": []}) != []
    assert validar_casos({"casos": {}}) != []


def test_caso_valido_no_da_errores() -> None:
    assert validar_casos({"casos": [_caso()]}) == []


def test_ids_duplicados_se_senalan_con_el_id() -> None:
    errores = validar_casos({"casos": [_caso(), _caso()]})
    assert any("duplicado" in e and "caso-prueba-1" in e for e in errores)


def test_fecha_cierre_con_mes_fuera_de_rango_es_error() -> None:
    caso = _caso()
    caso["cierre_fecha_aproximada"] = "2019-13"
    assert validar_casos({"casos": [caso]}) != []


def test_tramo_linea_valido_no_da_errores() -> None:
    caso = _caso()
    caso["tramo_linea"] = [[430000, 4450000], [431000, 4451000], [432000, 4450500]]
    assert validar_casos({"casos": [caso]}) == []


def test_cierre_fecha_tipo_ausente_se_trata_como_explicita() -> None:
    assert validar_casos({"casos": [_caso()]}) == []


def test_cierre_fecha_tipo_explicita_es_valido() -> None:
    caso = _caso()
    caso["cierre_fecha_tipo"] = "explicita"
    assert validar_casos({"casos": [caso]}) == []


def test_cierre_fecha_tipo_desconocido_es_error() -> None:
    caso = _caso()
    caso["cierre_fecha_tipo"] = "aproximada"
    errores = validar_casos({"casos": [caso]})
    assert any("cierre_fecha_tipo" in e for e in errores)


def test_documentado_desde_sin_nota_fecha_es_error() -> None:
    caso = _caso()
    caso["cierre_fecha_tipo"] = "documentado_desde"
    errores = validar_casos({"casos": [caso]})
    assert any("nota_fecha" in e for e in errores)


def test_documentado_desde_con_nota_fecha_es_valido() -> None:
    caso = _caso()
    caso["cierre_fecha_tipo"] = "documentado_desde"
    caso["nota_fecha"] = "Fecha de la nota de prensa citada como fuente."
    assert validar_casos({"casos": [caso]}) == []


def test_nota_fecha_vacia_es_error() -> None:
    caso = _caso()
    caso["nota_fecha"] = "  "
    assert validar_casos({"casos": [caso]}) != []


def test_nota_fecha_se_revisa_contra_sociedades() -> None:
    caso = _caso()
    caso["nota_fecha"] = "según Fulana S.L."
    assert validar_casos({"casos": [caso]}) != []
