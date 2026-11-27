"""Las fixtures versionadas de #168 son las que genera `generar.py` (no se editan a mano)."""

from tests.fixtures.candidatos_revision import generar


def test_los_ficheros_versionados_son_los_generados() -> None:
    for relative, text in generar.texts().items():
        path = generar.DIRECTORY / relative
        assert path.read_text(encoding="utf-8") == text, relative
