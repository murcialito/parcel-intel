"""Historia #178: imágenes de comparación en la ficha del visor (trazo SVG y atribución).

Un test por criterio. La lógica se prueba en Node (`tests/site/visor.test.mjs`, casos
`H178 CA<n>:`) con documento falso y `L` falso, sobre la fixture sintética
`tests/fixtures/site/candidatos_comparacion_28043.geojson` (forma de #172). Aquí van las
comprobaciones estáticas y el lanzamiento de esos casos. Ninguna prueba toca la red.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from parcel_intel.domain.public_card import BANNED_WORDS
from parcel_intel.domain.published_discrepancy import CADASTRAL_REFERENCE_RE
from tests.site.nodo import CANDIDATOS_IMG, SITE, assert_node_tests_pass

pytestmark = pytest.mark.acceptance


def _sin_comentarios(texto: str) -> str:
    return re.sub(r"^\s*//.*$", "", texto, flags=re.MULTILINE)


def test_ca1_imagenes_en_orden_con_periodo_atribucion_y_lazy(tmp_path: Path) -> None:
    """CA1. Dada la ficha de un tramo con `imagenes_comparacion`, cuando se abre, entonces se
    ven las imágenes de cada ventana en orden cronológico, con año/periodo y la atribución
    «Obra derivada de …» visibles junto a cada una, cargadas con `loading="lazy"` desde la URL
    publicada."""
    assert_node_tests_pass("^H178 CA1:", tmp_path)
    vista = (SITE / "vista.js").read_text(encoding="utf-8")
    assert '"loading", "lazy"' in vista


def test_ca2_trazo_svg_con_createelementns_y_control_accesible(tmp_path: Path) -> None:
    """CA2. Dada una imagen, cuando se muestra, entonces el trazo se dibuja como `svg` encima
    (`viewBox="0 0 ancho_px alto_px"`, `polyline` con `trazo_px`, todas las partes), construido
    con `createElementNS` y atributos, nunca con `innerHTML` (ADR 0042 §6), y puede ocultarse
    con un control accesible."""
    assert_node_tests_pass("^H178 CA2:", tmp_path, minimum=2)
    vista = _sin_comentarios((SITE / "vista.js").read_text(encoding="utf-8"))
    for etiqueta in ("svg", "polyline"):
        assert f'createElementNS(SVG_NS, "{etiqueta}")' in vista
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML", vista)


def test_ca3_imagen_que_falla_dice_no_disponible_y_conserva_atribucion(tmp_path: Path) -> None:
    """CA3. Dada una imagen que no carga, cuando falla, entonces la ficha dice «imagen no
    disponible» conservando su atribución, y el resto de la ficha y de las capas siguen
    funcionando."""
    assert_node_tests_pass("^H178 CA3:", tmp_path, minimum=2)
    assert "Imagen no disponible" in (SITE / "config.js").read_text(encoding="utf-8")


def test_ca4_huecos_y_omitidas_con_el_texto_publicado(tmp_path: Path) -> None:
    """CA4. Dados los `huecos` y las franjas omitidas del fichero, cuando se abre la ficha,
    entonces se muestran con el texto publicado, sin recomponerlo."""
    assert_node_tests_pass("^H178 CA4:", tmp_path)


def test_ca5_tramo_sin_imagenes_se_ve_como_antes(tmp_path: Path) -> None:
    """CA5. Dado un tramo sin `imagenes_comparacion` (fichero anterior a #172), cuando se abre
    la ficha, entonces se muestra como antes, sin error."""
    assert_node_tests_pass("^H178 CA5:", tmp_path)


def test_ca6_textos_sin_palabras_vetadas_ni_referencias_catastrales(tmp_path: Path) -> None:
    """CA6. Ningún texto visible nuevo contiene palabras de `BANNED_WORDS` ni una referencia
    catastral (test sobre el visor y el fichero publicado de fixtures)."""
    assert_node_tests_pass("^H178 CA6:", tmp_path)
    config = (SITE / "config.js").read_text(encoding="utf-8")
    nuevos = re.findall(
        r'(?:tituloComparacion|mostrarTrazo|imagenNoDisponible):\s*"([^"]+)"', config
    )
    assert len(nuevos) == 3
    texto_fichero = CANDIDATOS_IMG.read_text(encoding="utf-8")
    assert "imagenes_comparacion" in json.loads(texto_fichero)["features"][0]["properties"]
    for texto in [*nuevos, texto_fichero]:
        minuscula = texto.lower()
        assert not [p for p in BANNED_WORDS if p in minuscula], texto
        assert not CADASTRAL_REFERENCE_RE.search(texto), texto


def test_ca7_sin_librerias_nuevas_y_solo_mapa_js_importa_leaflet() -> None:
    """CA7. Dado el visor con las imágenes, cuando se comprueba, entonces no añade ninguna
    librería y `mapa.js` sigue siendo el único que importa Leaflet (ADR 0037)."""
    patron = re.compile(r"\bL\s*[.\[]|window\.L\b|globalThis\.L\b")
    for nombre in ("vista.js", "controlador.js", "config.js", "estilo.css", "index.html"):
        assert not patron.search((SITE / nombre).read_text(encoding="utf-8")), nombre
    assert patron.search((SITE / "mapa.js").read_text(encoding="utf-8"))
    for nombre in ("vista.js", "controlador.js"):
        codigo = _sin_comentarios((SITE / nombre).read_text(encoding="utf-8"))
        assert not re.search(r"^\s*import\b|\bimport\s*\(|\brequire\s*\(", codigo, re.MULTILINE)
    assert sorted(p.name for p in (SITE / "vendor").iterdir()) == ["leaflet"]
