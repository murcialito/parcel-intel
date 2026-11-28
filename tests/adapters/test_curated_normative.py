"""Tests unitarios del lector de `curated/normativa/catalogo.json` (historia #187).
Fixtures sintéticas de `tests/fixtures/normativa/`."""

from pathlib import Path
from typing import Any

import pytest

from parcel_intel.adapters.curated_normative import CuratedNormativeCatalogFile
from parcel_intel.ports.errors import NormativeCatalogFileError
from parcel_intel.ports.normative_catalog_source import NormativeCatalogSource
from tests.fixtures.normativa import generar


def _write(tmp_path: Path, content: str | bytes) -> CuratedNormativeCatalogFile:
    path = tmp_path / "catalogo.json"
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return CuratedNormativeCatalogFile(tmp_path)


def _doc_with(index: int, key: str, value: Any) -> str:
    cites = generar.citations()
    cites[index][key] = value
    return generar.render(generar.document(cites))


def test_implementa_el_port() -> None:
    source: NormativeCatalogSource = CuratedNormativeCatalogFile(generar.VALID_DIR)
    assert len(source.catalog().citations) == 3


def test_nota_null_cuenta_como_ausente(tmp_path: Path) -> None:
    catalog = _write(tmp_path, _doc_with(0, "nota", None)).catalog()
    assert all(c.note is None for c in catalog.citations if c.citation_id == "sintetica-art-10")


def test_tipos_de_fuente_desordenados_en_el_fichero_se_ordenan(tmp_path: Path) -> None:
    content = _doc_with(2, "tipos_fuente", ["via_pecuaria_oficial", "catastro_vt"])
    catalog = _write(tmp_path, content).catalog()
    assert catalog.citations[1].source_kinds == ("catastro_vt", "via_pecuaria_oficial")


@pytest.mark.parametrize(
    ("content", "detail"),
    [
        (b"\xff\xfe", "no es UTF-8"),
        ("[]", "el documento debe ser un objeto JSON"),
        ('{"version": 1, "huella_catalogo": "x"}', "faltan citas"),
        (
            '{"version": 1, "huella_catalogo": "x", "citas": {}}',
            "citas: debe ser una lista",
        ),
        ('{"version": 0, "huella_catalogo": "x", "citas": []}', "version: debe ser un entero >= 1"),
        ('{"version": true, "huella_catalogo": "x", "citas": []}', "version: debe ser un entero"),
        ('{"version": 1, "huella_catalogo": "x", "citas": [3]}', "cita 1 debe ser un objeto"),
    ],
)
def test_documento_no_valido(content: str | bytes, detail: str, tmp_path: Path) -> None:
    with pytest.raises(NormativeCatalogFileError, match=detail):
        _write(tmp_path, content).catalog()


@pytest.mark.parametrize(
    ("key", "value", "detail"),
    [
        ("fecha_norma", "2090-3-23", "fecha_norma: debe ser una fecha AAAA-MM-DD"),
        ("consultado", "2099-02-30", "consultado: debe ser una fecha AAAA-MM-DD"),
        ("texto", 3, "texto: debe ser texto"),
        ("version_catalogo", "1", "version_catalogo: debe ser un entero"),
        ("tipos_fuente", "catastro_vt", "tipos_fuente: debe ser una lista"),
        ("norma", None, "norma: debe ser texto"),
    ],
)
def test_campos_de_tipo_erroneo(key: str, value: Any, detail: str, tmp_path: Path) -> None:
    with pytest.raises(NormativeCatalogFileError) as info:
        _write(tmp_path, _doc_with(1, key, value)).catalog()
    assert f"sintetica-art-01: {detail}" in str(info.value)


def test_mensaje_nombra_el_fichero(tmp_path: Path) -> None:
    with pytest.raises(NormativeCatalogFileError) as info:
        _write(tmp_path, "{").catalog()
    assert info.value.path == str(tmp_path / "catalogo.json")
    assert str(tmp_path / "catalogo.json") in str(info.value)
