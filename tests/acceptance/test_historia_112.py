"""Historia #112: validacion-v2 con tramo_linea en los casos localizables. Sin red."""

import fnmatch
import json
import math
import re
from pathlib import Path

import pytest

from tests.validacion.casos_schema import validar_casos
from tests.validacion.congelacion import (
    calcular_huella,
    comprobar_integridad,
    contar_casos,
    leer_congelado,
)

pytestmark = pytest.mark.acceptance

RAIZ = Path(__file__).resolve().parents[2]
VALIDACION = RAIZ / "docs" / "validacion"
CASOS = VALIDACION / "casos.json"
V1 = RAIZ / "tests" / "fixtures" / "validacion" / "casos-v1.json"
V2 = VALIDACION / "CONGELADO-v2.md"
OCANA = "aranjuez-camino-de-ocana-a-la-barca"
CLAVES_INTACTAS = (
    "id",
    "fuente_url",
    "fuente_tipo",
    "fecha_consulta",
    "municipio",
    "ambito",
    "tramo_descripcion",
    "cierre_fecha_aproximada",
    "cierre_fecha_tipo",
    "nota_fecha",
)


def _casos(path: Path) -> list[dict[str, object]]:
    return list(json.loads(path.read_text(encoding="utf-8"))["casos"])


def _longitud(linea: list[list[float]]) -> float:
    return sum(math.dist(a, b) for a, b in zip(linea, linea[1:], strict=False))


def test_ca1_valida_y_lineas_del_ambito_abiertas() -> None:
    """Dado casos.json tras el cambio, cuando se valida con validar_casos, entonces no hay
    errores y los casos ambito hito que tengan tramo_linea lo traen como línea abierta."""
    assert validar_casos(json.loads(CASOS.read_text(encoding="utf-8"))) == []
    con_linea = [c for c in _casos(CASOS) if "tramo_linea" in c]
    assert con_linea
    for c in con_linea:
        assert c["ambito"] == "hito"
        linea = c["tramo_linea"]
        assert isinstance(linea, list) and len(linea) >= 2 and linea[0] != linea[-1]


def test_ca2_solo_cambia_tramo_linea_en_el_ambito() -> None:
    """Dado casos.json v2 comparado con v1, cuando se comparan caso a caso, entonces los 6
    casos conservan idénticas las claves y la única diferencia es tramo_linea en el ámbito."""
    v1, v2 = _casos(V1), _casos(CASOS)
    assert len(v1) == len(v2) == 6
    for antes, despues in zip(v1, v2, strict=True):
        for clave in CLAVES_INTACTAS:
            assert antes.get(clave) == despues.get(clave)
        assert set(despues) - set(antes) <= {"tramo_linea"}
        assert set(antes) <= set(despues)
        if "tramo_linea" in despues:
            assert despues["ambito"] == "hito"


def test_ca3_comunidad_sin_tramo_linea() -> None:
    """Dado casos.json v2, cuando se inspeccionan los 4 casos ambito comunidad, entonces
    ninguno lleva tramo_linea."""
    comunidad = [c for c in _casos(CASOS) if c["ambito"] == "comunidad"]
    assert len(comunidad) == 4
    assert all("tramo_linea" not in c for c in comunidad)


def test_ca4_longitud_del_tramo_de_ocana() -> None:
    """Dado el caso aranjuez-camino-de-ocana-a-la-barca, cuando se calcula la longitud de su
    tramo_linea, entonces está entre 100 m y 250 m."""
    caso = next(c for c in _casos(CASOS) if c["id"] == OCANA)
    linea = caso["tramo_linea"]
    assert isinstance(linea, list)
    assert 100 <= _longitud(linea) <= 250


def test_ca5_congelado_v2() -> None:
    """Dado CONGELADO-v2.md, cuando lo lee leer_congelado, entonces declara versión 2, fecha,
    casos_total 6, casos_ambito 2, la huella de casos.json, etiqueta validacion-v2 y motivo."""
    c = leer_congelado(V2)
    assert c.version == 2
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", c.fecha)
    assert (c.casos_total, c.casos_ambito) == (6, 2)
    assert c.sha256 == calcular_huella(CASOS)
    assert c.etiqueta == "validacion-v2"
    assert (c.motivo or "").strip()


def test_ca6_motivo_explica_origen_sin_titularidad() -> None:
    """Dado el motivo de CONGELADO-v2.md, cuando se lee, entonces dice que solo se añade
    tramo_linea a los casos localizables, por qué, el origen de cada línea y que no procede
    del polígono de ninguna finca; sin nombres de propietarios ni referencias catastrales."""
    motivo = leer_congelado(V2).motivo or ""
    assert "Solo se añade tramo_linea" in motivo
    assert "porque" in motivo
    assert "vías pecuarias" in motivo and "2026-11-26" in motivo
    assert "no procede del polígono de ninguna finca" in motivo
    assert re.search(r"\b[0-9A-Z]{14}(?:[0-9A-Z]{6})?\b", motivo) is None
    assert re.search(r"\bS\.?L\.?U?\b|\bS\.?A\.?\b", motivo) is None


def test_ca7_integridad_con_v2_vigente_y_v1_intacto() -> None:
    """Dado el repo con CONGELADO.md (v1) y CONGELADO-v2.md, cuando corre la integridad,
    entonces pasa tratando la v2 como vigente y CONGELADO.md no se modifica."""
    assert comprobar_integridad(VALIDACION, CASOS) == []
    assert contar_casos(_casos(CASOS)) == (6, 2)
    v1 = leer_congelado(VALIDACION / "CONGELADO.md")
    assert v1.sha256 == calcular_huella(V1)


def test_ca8_patron_del_workflow_casa_con_v2() -> None:
    """Dado el workflow etiquetar-validacion.yml, cuando se añade CONGELADO-v2.md, entonces
    el paths docs/validacion/CONGELADO*.md ya lo cubre [integración: solo en Actions]."""
    flujo = (RAIZ / ".github" / "workflows" / "etiquetar-validacion.yml").read_text(
        encoding="utf-8"
    )
    assert '"docs/validacion/CONGELADO*.md"' in flujo
    assert fnmatch.fnmatch("docs/validacion/CONGELADO-v2.md", "docs/validacion/CONGELADO*.md")


def test_ca9_readme_lista_los_no_evaluables() -> None:
    """Dado el README de docs/validacion, cuando se lee, entonces explica que los casos sin
    tramo_linea son «no evaluables» y lista cuáles y por qué."""
    readme = (VALIDACION / "README.md").read_text(encoding="utf-8")
    assert "no evaluables" in readme
    for caso in _casos(CASOS):
        if "tramo_linea" not in caso:
            assert str(caso["id"]) in readme
