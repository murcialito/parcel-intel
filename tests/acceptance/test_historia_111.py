"""Historia #111: comando `medir-candidatos` con informe agregado. Todo sintético y sin red."""

import json
import re
import socket
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.domain.candidate_evaluation import has_cadastral_reference_shape
from tests.medir_candidatos_support import (
    CONGELADO_EN,
    escribir_candidatos,
    escribir_casos,
    medir,
)

pytestmark = pytest.mark.acceptance

SRC = Path(__file__).resolve().parents[2] / "src" / "parcel_intel"


def _informe(ruta: Path) -> dict[str, Any]:
    datos: dict[str, Any] = json.loads(ruta.read_text(encoding="utf-8"))
    return datos


def _preparar(tmp_path: Path, con_candidatos: bool = True) -> tuple[Path, Path, Path]:
    casos = escribir_casos(tmp_path / "validacion")
    entrada = tmp_path / "candidatos"
    if con_candidatos:
        escribir_candidatos(entrada)
    return casos, entrada, tmp_path / "salida" / "medicion.json"


def test_ca1_informe_con_cobertura_y_precision(tmp_path: Path) -> None:
    """CA1. Dados casos y candidatos sintéticos en directorios temporales, cuando se ejecuta
    `medir-candidatos`, entonces escribe un informe con cobertura y precisión (y sus recuentos)
    sobre los casos evaluables y sale con 0."""
    casos, entrada, salida = _preparar(tmp_path)
    assert medir(casos, entrada, salida) == 0
    informe = _informe(salida)
    assert informe["cobertura"]["valor"] == 1.0
    assert informe["cobertura"]["casos_senalados"] == 1
    assert informe["cobertura"]["casos_evaluables"] == 1
    assert informe["precision"]["valor"] == 0.5
    assert informe["precision"]["candidatos_acertados"] == 1
    assert informe["precision"]["candidatos_evaluables"] == 2


def test_ca2_no_evaluables_con_motivo_y_sin_contar_como_fallo(tmp_path: Path) -> None:
    """CA2. Dado un caso no evaluable, cuando se genera el informe, entonces aparece en el
    recuento de no evaluables con su motivo y no cuenta como fallo en cobertura ni precisión."""
    casos, entrada, salida = _preparar(tmp_path)
    medir(casos, entrada, salida)
    informe = _informe(salida)
    motivos = {item["caso"]: item["motivo"] for item in informe["no_evaluables"]["casos"]}
    assert motivos["chinchon-sin-geometria"] == "sin_geometria"
    assert motivos["fuera-uno"] == "fuera_del_ambito"
    assert informe["no_evaluables"]["total"] == 5
    assert informe["cobertura"]["casos_evaluables"] == 1  # los 5 no evaluables no entran
    assert informe["cobertura"]["valor"] == 1.0


def test_ca3_sin_fichero_sin_capas_y_fichero_ilegible_falla(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA3. Dado que falta el fichero de candidatos de un municipio con casos en el ámbito,
    cuando se ejecuta, entonces esos casos salen `sin_capas` y el informe lo dice; y dado un
    fichero ilegible o inválido (`CutCandidateFileError`), entonces sale con 1, nombra el fichero
    y no escribe informe."""
    casos, entrada, salida = _preparar(tmp_path)
    assert medir(casos, entrada, salida) == 0
    motivos = {i["caso"]: i["motivo"] for i in _informe(salida)["no_evaluables"]["casos"]}
    assert motivos["aranjuez-sin-informe"] == "sin_capas"

    roto = tmp_path / "roto"
    roto.mkdir()
    (roto / "28043.geojson").write_text("no es json", encoding="utf-8")
    otra_salida = tmp_path / "otra" / "medicion.json"
    assert medir(casos, roto, otra_salida) == 1
    assert "28043.geojson" in capsys.readouterr().err
    assert not otra_salida.exists()


def test_ca4_el_informe_recoge_etiqueta_huella_fecha_y_versiones(tmp_path: Path) -> None:
    """CA4. Dado `casos.json` con huella igual a la de `CONGELADO*.md` vigente, cuando se
    ejecuta, entonces el informe recoge la etiqueta (`validacion-v1`), la huella, la fecha de
    ejecución y las versiones del método de candidatos (la de los informes leídos) y del
    criterio de casamiento."""
    casos, entrada, salida = _preparar(tmp_path)
    medir(casos, entrada, salida)
    informe = _informe(salida)
    assert informe["etiqueta"] == "validacion-v1"
    assert informe["congelado"] is True
    assert re.fullmatch(r"[0-9a-f]{64}", informe["sha256"])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", informe["fecha"])
    assert informe["metodo_candidatos"] == ["candidato_corte@1"]
    assert informe["criterio_casamiento"]["identificador"] == "casamiento_candidato_caso"
    assert informe["criterio_casamiento"]["version"] == 1
    assert CONGELADO_EN.isoformat() in (casos.parent / "CONGELADO.md").read_text(encoding="utf-8")


def test_ca5_casos_modificado_avisa_y_marca_no_congelado(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA5. Dado `casos.json` modificado sin nueva congelación, cuando se ejecuta, entonces
    avisa de que la huella no coincide y marca el informe como "conjunto no congelado".
    Decisión por defecto: no falla, pero el aviso consta en el informe y en stderr. Un
    `casos.json` que no pasa el validador sí hace salir con 1 sin escribir informe."""
    casos, entrada, salida = _preparar(tmp_path)
    datos = json.loads(casos.read_text(encoding="utf-8"))
    datos["casos"][3]["tramo_descripcion"] = "camino modificado"
    casos.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    assert medir(casos, entrada, salida) == 0
    informe = _informe(salida)
    assert informe["congelado"] is False
    assert informe["etiqueta"] is None
    assert "no congelado" in informe["aviso"]
    assert "no congelado" in capsys.readouterr().err

    datos["casos"][3].pop("municipio")
    casos.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    invalida = tmp_path / "invalida" / "medicion.json"
    assert medir(casos, entrada, invalida) == 1
    assert not invalida.exists()


def test_ca6_el_informe_no_lleva_ids_de_candidato_ni_referencias_ni_descripciones(
    tmp_path: Path,
) -> None:
    """CA6. Dado el informe, cuando se inspecciona, entonces no contiene nombres de fincas ni
    de propietarios, referencias catastrales ni ids de candidato; solo ids de caso y
    agregados."""
    casos, entrada, salida = _preparar(tmp_path)
    medir(casos, entrada, salida)
    texto = salida.read_text(encoding="utf-8")
    assert "abababababababab" not in texto
    base = json.loads((entrada / "28043.geojson").read_text(encoding="utf-8"))
    for feature in base["features"]:
        assert feature["properties"]["candidate_id"] not in texto
    assert "camino entre dos puntos" not in texto  # descripción del tramo
    assert "ejemplo.es" not in texto  # URL de la fuente
    assert not has_cadastral_reference_shape(texto)


def test_ca7_dos_ejecuciones_dan_informes_identicos(tmp_path: Path) -> None:
    """CA7. Dados los mismos datos de entrada, cuando se ejecuta dos veces el mismo día,
    entonces los informes son idénticos (orden estable)."""
    casos, entrada, salida = _preparar(tmp_path)
    medir(casos, entrada, salida)
    segunda = tmp_path / "segunda.json"
    medir(casos, entrada, segunda)
    assert salida.read_bytes() == segunda.read_bytes()


def test_ca8_sin_red_y_sin_adapters_fuera_del_composition_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CA8. Dado el comando, cuando se ejecuta, entonces no hace ninguna llamada de red y no
    instancia nada concreto fuera de `cli/main.py`."""

    def sin_red(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("medir-candidatos intentó abrir una conexión de red")

    monkeypatch.setattr(socket.socket, "connect", sin_red)
    casos, entrada, salida = _preparar(tmp_path)
    assert medir(casos, entrada, salida) == 0
    for capa in ("application", "domain", "ports"):
        for fichero in (SRC / capa).rglob("*.py"):
            assert "parcel_intel.adapters" not in fichero.read_text(encoding="utf-8"), fichero


def test_ca9_hay_un_test_de_aceptacion_por_criterio() -> None:
    """CA9. Dado el cambio, entonces `uv run lint-imports`, `mypy`, `ruff` y `pytest` siguen
    en verde. Hay un test de aceptación por criterio en `tests/acceptance/test_historia_111.py`."""
    texto = Path(__file__).read_text(encoding="utf-8")
    for numero in range(1, 10):
        assert re.search(rf"^def test_ca{numero}_", texto, re.MULTILINE)
