"""Historia #236: peticiones reales a Catastro por fecha (TIME, FECHAALTA/FECHABAJA), en local.

Historia `fuera_de_ci`: las peticiones las hizo el fundador en local el 2026-11-28 y las respuestas
están en `data/raw/catastro_fecha/` (fuera de git). Estos tests leen lo que quedó en REGISTRY.md y
comprueban que en git no hay nada crudo. No llaman a red.
"""

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
FIXTURES = REPO / "tests" / "fixtures" / "catastro_historico"
REF_14 = re.compile(r"\b\d{7}[A-Z]{2}\d{4}[A-Z]\b|\b\d{7}[A-Z]{2}\d{4}[A-Z]\d{4}[A-Z]{2}\b")


def _seccion() -> str:
    texto = REGISTRY.read_text(encoding="utf-8")
    inicio = texto.index("### Peticiones reales (#236")
    return texto[inicio : texto.index("\n### ", inicio + 1)]


def _fila(clave: str) -> str:
    return next(ln for ln in _seccion().splitlines() if ln.startswith("| ") and clave in ln)


def test_ca1_wms_con_time_respuesta_diferencias_y_fecha_mas_antigua() -> None:
    """CA1. Dado un tramo en Colmenar de Oreja, cuando se pide el WMS con `TIME` de 2005 y de hoy,
    entonces REGISTRY.md dice si responde, si las imágenes difieren y desde qué fecha hay datos."""
    fila = _fila("WMS con `TIME`")
    assert "`confirmado` (2026-11-28)" in fila
    s = _seccion()
    assert "TIME=AAAA-MM-DD" in s and "ServidorWMS.aspx" in s and "PARCELA" in s
    assert "28.436 píxeles distintos" in s  # 2005 frente a hoy
    assert "2001-12-01" in s and "2001-12-31" in s  # fecha más antigua con datos
    assert "Un `200` no prueba que haya datos" in s


def test_ca2_fechaalta_fechabaja_formato_y_bajas() -> None:
    """CA2. Dado el WFS de parcelas de #37, cuando se inspeccionan los atributos, entonces
    REGISTRY.md dice si hay `FECHAALTA`/`FECHABAJA`, su formato, y si las dadas de baja siguen en
    la descarga."""
    fila = _fila("FECHAALTA")
    assert "`descartado`" in fila and "(2026-11-28)" in fila
    s = _seccion()
    assert "beginLifespanVersion" in s and "endLifespanVersion" in s
    assert "AAAAMMDD" in s and "99999999" in s
    assert "Solo trae parcelas vigentes" in s


def test_ca3_nada_crudo_en_git_y_fixtures_sinteticas() -> None:
    """CA3. Dado el resultado, entonces no hay en git ninguna respuesta cruda, geometría ni
    referencia catastral reales; si procede, se ajustan las fixtures sintéticas de #209 al formato
    observado."""
    rastreados = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert not any(r.startswith("data/") for r in rastreados)
    assert not any("catastro_fecha" in r for r in rastreados)
    xml = (FIXTURES / "parcelas_fechas_sintetico.xml").read_text(encoding="utf-8")
    assert "cp:beginLifespanVersion" in xml and "FECHAALTA" not in xml
    dbf = (FIXTURES / "parcela_dbf_fechas_sintetico.csv").read_text(encoding="utf-8")
    assert "FECHAALTA,FECHABAJA" in dbf and "99999999" in dbf
    for p in FIXTURES.iterdir():
        texto = p.read_text(encoding="utf-8")
        assert not REF_14.search(texto), p.name
        assert "posList" not in texto, p.name
    assert "observado" in (FIXTURES / "README.md").read_text(encoding="utf-8")


def test_ca4_ninguna_fila_pendiente() -> None:
    """CA4. La issue se cierra solo cuando las filas `TIME` y `FECHAALTA`/`FECHABAJA` de
    REGISTRY.md pasan de `pendiente` a `confirmado` o `descartado`."""
    for clave in ("WMS con `TIME`", "FECHAALTA"):
        fila = _fila(clave)
        assert "`pendiente`" not in fila
        assert "`confirmado`" in fila or "`descartado`" in fila
