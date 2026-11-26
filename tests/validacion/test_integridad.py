"""Integridad del conjunto de validación real (historia #54).

Lee el repo real: si no hay ningún `docs/validacion/CONGELADO*.md` solo exige que `casos.json`
sea válido (no bloquea CI mientras se recopila). Una vez congelado, es estricto.
"""

from pathlib import Path

from tests.validacion.congelacion import comprobar_integridad

VALIDACION = Path(__file__).resolve().parents[2] / "docs" / "validacion"


def test_casos_json_es_integro_respecto_a_su_ultima_congelacion() -> None:
    assert comprobar_integridad(VALIDACION, VALIDACION / "casos.json") == []
