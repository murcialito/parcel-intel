"""Tests unitarios del visor (historia #85): la suite completa de `visor.test.mjs` en Node,
y comprobaciones estáticas que no son de ningún criterio en concreto."""

from __future__ import annotations

import re
from pathlib import Path

from tests.site.nodo import SITE, assert_node_tests_pass

PROPIOS = sorted(p for p in SITE.glob("*.js"))


def test_suite_node_del_visor_completa_en_verde(tmp_path: Path) -> None:
    # Todos los tests (CA y unidades) deben pasar; hay más de 30.
    assert_node_tests_pass(".*", tmp_path, minimum=30)


def test_tests_unitarios_del_visor_en_verde(tmp_path: Path) -> None:
    assert_node_tests_pass("^unidad:", tmp_path, minimum=5)


def test_ningun_modulo_propio_usa_innerhtml_ni_eval() -> None:
    patron = re.compile(r"\binnerHTML\b|\bouterHTML\b|insertAdjacentHTML|\beval\s*\(|new Function")
    assert len(PROPIOS) >= 5
    for fichero in PROPIOS:
        assert not patron.search(fichero.read_text(encoding="utf-8")), fichero.name


def _sin_comentarios(texto: str) -> str:
    return re.sub(r"^\s*//.*$", "", texto, flags=re.MULTILINE)


def test_controlador_y_config_no_importan_nada_ni_tocan_el_dom() -> None:
    for nombre in ("controlador.js", "config.js"):
        codigo = _sin_comentarios((SITE / nombre).read_text(encoding="utf-8"))
        hallazgos = [
            patron
            for patron in (r"^\s*import\b", r"\bdocument\b", r"\bwindow\b", r"\bfetch\s*\(")
            if re.search(patron, codigo, re.MULTILINE)
        ]
        assert hallazgos == [], nombre


def test_solo_app_js_usa_fetch_y_document_global() -> None:
    for fichero in PROPIOS:
        texto = fichero.read_text(encoding="utf-8")
        if fichero.name != "app.js":
            assert "fetch(" not in texto, fichero.name
            assert not re.search(r"\bdocument\.", texto), fichero.name


def test_site_no_lleva_package_json() -> None:
    # Sería un `.json` sin procedencia y rompería construir_sitio.py (CA8).
    assert not (SITE / "package.json").exists()
