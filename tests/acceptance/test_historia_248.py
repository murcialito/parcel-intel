"""Historia #248: mostrar la tabla de convergencia de fuentes en la ficha del visor.

Un test por criterio. La lógica se prueba en Node (`tests/site/visor.test.mjs`, casos
`H248 CA<n>:`) con documento falso y fixtures sintéticas (textos inventados, y el fichero
publicado sintético de #208 que ya lleva `convergencia`). Ninguna prueba toca la red.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.site.nodo import SITE, TEST_FILE, assert_node_tests_pass

pytestmark = pytest.mark.acceptance

_NODE_TESTS = TEST_FILE.read_text(encoding="utf-8")


def _casos(ca: int) -> list[str]:
    return re.findall(rf'test\("(H248 CA{ca}:[^"]*)"', _NODE_TESTS)


def test_ca1_titulo_filas_en_orden_y_aviso_bajo_la_tabla(tmp_path: Path) -> None:
    """CA1. Dada una ficha de indicio o de tramo a verificar cuya feature lleva `convergencia`,
    cuando se abre, entonces se ve el título, una fila por entrada de `filas` en el orden del
    fichero (rótulo, texto del valor y año o «Sin cobertura»), y el aviso de la tabla bajo ella."""
    assert len(_casos(1)) == 2
    assert_node_tests_pass("^H248 CA1:", tmp_path, minimum=2)


def test_ca2_enlaces_externos_seguros(tmp_path: Path) -> None:
    """CA2. Dada una fila con `enlaces`, cuando se muestra, entonces ofrece cada enlace como
    enlace externo seguro (solo URL que pasan `ENLACE_SEGURO`, `rel="noopener noreferrer"`); un
    enlace que no pasa se omite sin romper la fila."""
    assert len(_casos(2)) == 1
    assert_node_tests_pass("^H248 CA2:", tmp_path)
    assert 'setAttribute("rel", "noopener noreferrer")' in (SITE / "vista.js").read_text("utf-8")


def test_ca3_imagen_no_disponible(tmp_path: Path) -> None:
    """CA3. Dada una tabla con `imagenes` = «Imagen no disponible», cuando se muestra, entonces
    la tabla lleva esa nota tal cual y no falla."""
    assert len(_casos(3)) == 1
    assert_node_tests_pass("^H248 CA3:", tmp_path)


def test_ca4_sin_convergencia_o_forma_inesperada(tmp_path: Path) -> None:
    """CA4. Dada una ficha cuyo fichero no lleva `convergencia`, o con una forma inesperada,
    cuando se abre, entonces no se muestra el bloque, el resto de la ficha queda igual y no hay
    error."""
    assert len(_casos(4)) == 2
    assert_node_tests_pass("^H248 CA4:", tmp_path, minimum=2)


def test_ca5_atribucion_y_fecha_tal_cual_con_textcontent(tmp_path: Path) -> None:
    """CA5. Dada una fila, cuando se muestra, entonces lleva su `atribucion` (cada texto, tal
    cual) y, si existe, la fecha de consulta; el visor no calcula, reordena ni modifica valores
    ni textos, y los inserta con `textContent` (nunca HTML)."""
    assert len(_casos(5)) == 1
    assert_node_tests_pass("^H248 CA5:", tmp_path)
    vista = re.sub(r"^\s*//.*$", "", (SITE / "vista.js").read_text("utf-8"), flags=re.MULTILINE)
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML", vista)


def test_ca6_sin_identificadores_internos(tmp_path: Path) -> None:
    """CA6. Dado un indicio o un tramo a verificar, cuando se abre la ficha, entonces no se
    muestra ningún identificador interno, referencia catastral ni localizador de parcela (el
    visor solo copia las claves de la lista blanca de la tabla y de la fila)."""
    assert len(_casos(6)) == 1
    assert_node_tests_pass("^H248 CA6:", tmp_path)


def test_ca7_tabla_semantica_y_sin_desborde(tmp_path: Path) -> None:
    """CA7. Dada la ficha en pantalla estrecha (móvil, hoja inferior) y en escritorio, entonces
    la tabla es legible y operable con teclado y lector de pantalla (encabezados semánticos, sin
    depender solo del color) y no desborda horizontalmente; el aviso nunca queda plegado."""
    assert len(_casos(7)) == 1
    assert_node_tests_pass("^H248 CA7:", tmp_path)
    css = (SITE / "estilo.css").read_text(encoding="utf-8")
    assert re.search(r"\.pc-convergencia__tabla\s*\{[^}]*table-layout:\s*fixed", css)
    assert re.search(r"\.pc-convergencia__tabla\s*\{[^}]*width:\s*100%", css)
    assert "overflow-wrap: anywhere" in css


def test_ca8_los_tests_del_visor_pasan_sin_romper_los_anteriores(tmp_path: Path) -> None:
    """CA8. Dados los tests del visor y un test de aceptación por criterio con fixtures
    sintéticas, entonces pasan sin red y sin romper los de #95, #171, #178 y #185."""
    assert_node_tests_pass("^H248", tmp_path, minimum=9)
    assert_node_tests_pass("^(H95|H171|H178|H185)", tmp_path, minimum=20)
